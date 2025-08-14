from __future__ import annotations

"""Settings CRUD API (SYNC-8).

POST   /api/settings          – создать ключ
GET    /api/settings          – список
GET    /api/settings/{id}     – получить по id
PUT    /api/settings/{id}     – полное обновление (value)
PATCH  /api/settings/{id}     – частичное обновление (value)
DELETE /api/settings/{id}     – удалить

В будущем можно расширить фильтрацию (по key), но для MVP хватит базового CRUD.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_session
from db.models import Setting as SettingModel
from backend.api.schemas import (
    SettingCreate,
    SettingRead,
    SettingUpdate,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_setting_or_404(session: AsyncSession, set_id: int) -> SettingModel:  # noqa: D401
    setting = await session.get(SettingModel, set_id)
    if not setting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setting not found")
    return setting


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[SettingRead])
async def list_settings(session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(SettingModel).order_by(SettingModel.key))
    return res.scalars().all()


@router.post("/", response_model=SettingRead, status_code=status.HTTP_201_CREATED)
async def create_setting(payload: SettingCreate, session: AsyncSession = Depends(get_session)):
    setting = SettingModel(**payload.model_dump())
    session.add(setting)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Setting with this key already exists")
    await session.refresh(setting)
    return setting


@router.get("/{set_id}", response_model=SettingRead)
async def retrieve_setting(set_id: int, session: AsyncSession = Depends(get_session)):
    return await _get_setting_or_404(session, set_id)


@router.put("/{set_id}", response_model=SettingRead)
async def update_setting_full(set_id: int, payload: SettingCreate, session: AsyncSession = Depends(get_session)):
    setting = await _get_setting_or_404(session, set_id)
    # Полное обновление: можно изменить и key, и value
    for field, value in payload.model_dump().items():
        setattr(setting, field, value)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Setting with this key already exists")
    await session.refresh(setting)
    return setting


@router.patch("/{set_id}", response_model=SettingRead)
async def update_setting_partial(set_id: int, payload: SettingUpdate, session: AsyncSession = Depends(get_session)):
    setting = await _get_setting_or_404(session, set_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(setting, field, value)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Setting with this key already exists")
    await session.refresh(setting)
    return setting


@router.delete("/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_setting(set_id: int, session: AsyncSession = Depends(get_session)):
    setting = await _get_setting_or_404(session, set_id)
    await session.delete(setting)
    await session.commit()
    return None
