from __future__ import annotations

"""Assets CRUD API (SYNC-5).

POST   /api/assets          – создать инструмент
GET    /api/assets          – список
GET    /api/assets/{id}     – получить по id
PUT    /api/assets/{id}     – полное обновление
PATCH  /api/assets/{id}     – частичное обновление
DELETE /api/assets/{id}     – удалить
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from db.database import get_session
from db.models import Asset as AssetModel
from backend.api.schemas import (
    AssetCreate,
    AssetRead,
    AssetUpdate,
)

router = APIRouter(prefix="/api/assets", tags=["assets"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_asset_or_404(session: AsyncSession, asset_id: int) -> AssetModel:  # noqa: D401
    asset = await session.get(AssetModel, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[AssetRead])
async def list_assets(session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(AssetModel))
    return res.scalars().all()


@router.post("/", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
async def create_asset(payload: AssetCreate, session: AsyncSession = Depends(get_session)):
    asset = AssetModel(**payload.model_dump())
    session.add(asset)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset already exists")
    await session.refresh(asset)
    return asset


@router.get("/{asset_id}", response_model=AssetRead)
async def retrieve_asset(asset_id: int, session: AsyncSession = Depends(get_session)):
    return await _get_asset_or_404(session, asset_id)


@router.put("/{asset_id}", response_model=AssetRead)
async def update_asset_full(asset_id: int, payload: AssetCreate, session: AsyncSession = Depends(get_session)):
    asset = await _get_asset_or_404(session, asset_id)
    for field, value in payload.model_dump().items():
        setattr(asset, field, value)
    await session.commit()
    await session.refresh(asset)
    return asset


@router.patch("/{asset_id}", response_model=AssetRead)
async def update_asset_partial(asset_id: int, payload: AssetUpdate, session: AsyncSession = Depends(get_session)):
    asset = await _get_asset_or_404(session, asset_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(asset, field, value)
    await session.commit()
    await session.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(asset_id: int, session: AsyncSession = Depends(get_session)):
    asset = await _get_asset_or_404(session, asset_id)
    await session.delete(asset)
    await session.commit()
    return None
