"""API endpoints для работы со сделками (trades)."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.database import get_session
from db.models import Trade, Pair
from core.trade_calculator import get_trade_stats, clear_trades

router = APIRouter(prefix="/api/pairs", tags=["trades"])


@router.get("/{pair_id}/trades")
async def get_pair_trades(
    pair_id: int,
    session: AsyncSession = Depends(get_session)
) -> List[dict]:
    """Получить все сделки для торговой пары."""
    # Проверяем, существует ли пара
    pair_result = await session.execute(select(Pair).where(Pair.id == pair_id))
    pair = pair_result.scalar_one_or_none()
    if not pair:
        raise HTTPException(status_code=404, detail="Pair not found")
    
    # Получаем сделки
    stmt = select(Trade).where(Trade.pair_id == pair_id).order_by(Trade.timestamp.desc())
    result = await session.execute(stmt)
    trades = result.scalars().all()
    
    return [
        {
            "id": trade.id,
            "side": trade.side,
            "qty": trade.qty,
            "price": float(trade.price),
            "asset_code": trade.asset_code,
            "quik_trade_id": trade.quik_trade_id,
            "timestamp": trade.timestamp.isoformat()
        }
        for trade in trades
    ]


@router.get("/{pair_id}/stats")
async def get_pair_trade_stats(
    pair_id: int,
    session: AsyncSession = Depends(get_session)
) -> dict:
    """Получить статистику сделок для торговой пары."""
    # Проверяем, существует ли пара
    pair_result = await session.execute(select(Pair).where(Pair.id == pair_id))
    pair = pair_result.scalar_one_or_none()
    if not pair:
        raise HTTPException(status_code=404, detail="Pair not found")
    
    # Получаем статистику
    stats = await get_trade_stats(session, pair_id)
    return stats


@router.delete("/{pair_id}/trades")
async def clear_pair_trades(
    pair_id: int,
    session: AsyncSession = Depends(get_session)
) -> dict:
    """Очистить все сделки для торговой пары (Reset)."""
    # Проверяем, существует ли пара
    pair_result = await session.execute(select(Pair).where(Pair.id == pair_id))
    pair = pair_result.scalar_one_or_none()
    if not pair:
        raise HTTPException(status_code=404, detail="Pair not found")
    
    # Очищаем сделки
    deleted_count = await clear_trades(session, pair_id)
    
    # Обнуляем exec_price и exec_qty в самой паре
    pair.exec_price = None
    pair.exec_qty = 0
    await session.commit()
    
    return {
        "message": f"Cleared {deleted_count} trades for pair {pair_id}",
        "deleted_count": deleted_count
    }
