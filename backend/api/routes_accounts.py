"""Accounts CRUD API (SYNC-4).

POST   /api/accounts          – создать счёт
GET    /api/accounts          – список
GET    /api/accounts/{id}     – получить по id
PUT    /api/accounts/{id}     – полное обновление
PATCH  /api/accounts/{id}     – частичное обновление
DELETE /api/accounts/{id}     – удалить
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_session
from db.models import Account as AccountModel
from backend.api.schemas import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_account_or_404(session: AsyncSession, acc_id: int) -> AccountModel:  # noqa: D401
    acc = await session.get(AccountModel, acc_id)
    if not acc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return acc


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[AccountRead], response_model_exclude_none=True)
async def list_accounts(session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(AccountModel))
    return res.scalars().all()


@router.post("/", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(payload: AccountCreate, session: AsyncSession = Depends(get_session)):
    acc = AccountModel(**payload.model_dump())
    session.add(acc)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists")
    await session.refresh(acc)
    return acc


@router.get("/{acc_id}", response_model=AccountRead)
async def retrieve_account(acc_id: int, session: AsyncSession = Depends(get_session)):
    return await _get_account_or_404(session, acc_id)


@router.put("/{acc_id}", response_model=AccountRead)
async def update_account_full(acc_id: int, payload: AccountCreate, session: AsyncSession = Depends(get_session)):
    acc = await _get_account_or_404(session, acc_id)
    for field, value in payload.model_dump().items():
        setattr(acc, field, value)
    await session.commit()
    await session.refresh(acc)
    return acc


@router.patch("/{acc_id}", response_model=AccountRead)
async def update_account_partial(acc_id: int, payload: AccountUpdate, session: AsyncSession = Depends(get_session)):
    acc = await _get_account_or_404(session, acc_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(acc, field, value)
    await session.commit()
    await session.refresh(acc)
    return acc


@router.delete("/{acc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(acc_id: int, session: AsyncSession = Depends(get_session)):
    acc = await _get_account_or_404(session, acc_id)
    await session.delete(acc)
    await session.commit()
    return None

