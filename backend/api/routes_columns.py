from __future__ import annotations

"""PairsColumn CRUD API (SYNC-7).

POST   /api/columns          – создать запись (позиция/ширина столбца)
GET    /api/columns          – список, отсортированный по position
GET    /api/columns/{id}     – получить по id
PUT    /api/columns/{id}     – полное обновление
PATCH  /api/columns/{id}     – частичное обновление
DELETE /api/columns/{id}     – удалить
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_session
from db.models import PairsColumn as ColumnModel
from backend.api.schemas import (
    PairsColumnCreate,
    PairsColumnRead,
    PairsColumnUpdate,
)

router = APIRouter(prefix="/api/columns", tags=["columns"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_column_or_404(session: AsyncSession, col_id: int) -> ColumnModel:  # noqa: D401
    col = await session.get(ColumnModel, col_id)
    if not col:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Column not found")
    return col


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[PairsColumnRead])
async def list_columns(session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(ColumnModel).order_by(ColumnModel.position))
    return res.scalars().all()


@router.post("/", response_model=PairsColumnRead, status_code=status.HTTP_201_CREATED)
async def create_column(payload: PairsColumnCreate, session: AsyncSession = Depends(get_session)):
    col = ColumnModel(**payload.model_dump())
    session.add(col)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    await session.refresh(col)
    return col


@router.get("/{col_id}", response_model=PairsColumnRead)
async def retrieve_column(col_id: int, session: AsyncSession = Depends(get_session)):
    return await _get_column_or_404(session, col_id)


@router.put("/{col_id}", response_model=PairsColumnRead)
async def update_column_full(col_id: int, payload: PairsColumnCreate, session: AsyncSession = Depends(get_session)):
    col = await _get_column_or_404(session, col_id)
    for field, value in payload.model_dump().items():
        setattr(col, field, value)
    await session.commit()
    await session.refresh(col)
    return col


@router.patch("/{col_id}", response_model=PairsColumnRead)
async def update_column_partial(col_id: int, payload: PairsColumnUpdate, session: AsyncSession = Depends(get_session)):
    col = await _get_column_or_404(session, col_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(col, field, value)
    await session.commit()
    await session.refresh(col)
    return col


@router.delete("/{col_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_column(col_id: int, session: AsyncSession = Depends(get_session)):
    col = await _get_column_or_404(session, col_id)
    await session.delete(col)
    await session.commit()
    return None
