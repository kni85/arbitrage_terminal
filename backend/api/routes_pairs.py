from __future__ import annotations

"""Pairs CRUD API (SYNC-6).

POST   /api/pairs          – создать пару
GET    /api/pairs          – список
GET    /api/pairs/{id}     – получить по id
PUT    /api/pairs/{id}     – полное обновление (optimistic lock)
PATCH  /api/pairs/{id}     – частичное обновление (optimistic lock)
DELETE /api/pairs/{id}     – удалить (optimistic lock)

Для оптимистичной блокировки клиент должен передавать актуальное поле
`updated_at` (ISO 8601) через заголовок `If-Unmodified-Since`.
Если значение не совпадает с текущим в базе – возвращается 409 Conflict.
"""

from datetime import datetime
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_session
from db.models import Pair as PairModel
from backend.api.schemas import (
    PairCreate,
    PairRead,
    PairUpdate,
)

router = APIRouter(prefix="/api/pairs", tags=["pairs"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_pair_or_404(session: AsyncSession, pair_id: int) -> PairModel:  # noqa: D401
    pair = await session.get(PairModel, pair_id)
    if not pair:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pair not found")
    return pair


def _check_lock(pair: PairModel, if_unmodified_since: str | None):  # noqa: D401
    if if_unmodified_since is None:
        return
    try:
        ts = datetime.fromisoformat(if_unmodified_since)
    except ValueError:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid If-Unmodified-Since header")
    if abs((pair.updated_at - ts).total_seconds()) > 1e-3:  # allow ms diff
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pair has been modified by another client")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[PairRead], response_model_exclude_none=True)
async def list_pairs(session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(PairModel))
    return res.scalars().all()


@router.post("/", response_model=PairRead, status_code=status.HTTP_201_CREATED)
async def create_pair(payload: PairCreate, session: AsyncSession = Depends(get_session)):
    pair = PairModel(**payload.model_dump())
    session.add(pair)
    await session.commit()
    await session.refresh(pair)
    return pair


@router.get("/{pair_id}", response_model=PairRead)
async def retrieve_pair(pair_id: int, session: AsyncSession = Depends(get_session)):
    return await _get_pair_or_404(session, pair_id)


@router.put("/{pair_id}", response_model=PairRead)
async def update_pair_full(
    pair_id: int,
    payload: PairCreate,
    session: AsyncSession = Depends(get_session),
    if_unmodified_since: str | None = Header(None, convert_underscores=False),
):
    pair = await _get_pair_or_404(session, pair_id)
    _check_lock(pair, if_unmodified_since)
    for field, value in payload.model_dump().items():
        setattr(pair, field, value)
    await session.commit()
    await session.refresh(pair)
    return pair


@router.patch("/{pair_id}", response_model=PairRead)
async def update_pair_partial(
    pair_id: int,
    payload: PairUpdate,
    session: AsyncSession = Depends(get_session),
    if_unmodified_since: str | None = Header(None, convert_underscores=False),
):
    pair = await _get_pair_or_404(session, pair_id)
    _check_lock(pair, if_unmodified_since)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(pair, field, value)
    await session.commit()
    await session.refresh(pair)
    return pair


@router.delete("/{pair_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pair(
    pair_id: int,
    session: AsyncSession = Depends(get_session),
    if_unmodified_since: str | None = Header(None, convert_underscores=False),
):
    pair = await _get_pair_or_404(session, pair_id)
    _check_lock(pair, if_unmodified_since)
    await session.delete(pair)
    await session.commit()
    return None
