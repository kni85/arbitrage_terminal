"""Функции для расчёта exec_price по реальным сделкам."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Trade


async def calculate_exec_price(session: AsyncSession, pair_id: int) -> Optional[float]:
    """
    Рассчитывает средневзвешенную цену исполнения (exec_price) для пары
    на основе всех реальных сделок в базе данных.
    
    Args:
        session: Сессия базы данных
        pair_id: ID торговой пары
        
    Returns:
        Средневзвешенная цена исполнения или None, если сделок нет
    """
    # Получаем все сделки для данной пары
    stmt = select(Trade).where(Trade.pair_id == pair_id).order_by(Trade.timestamp)
    result = await session.execute(stmt)
    trades = result.scalars().all()
    
    if not trades:
        return None
    
    # Рассчитываем средневзвешенную цену
    total_cost = 0.0
    total_qty = 0
    
    for trade in trades:
        total_cost += trade.price * trade.qty
        total_qty += trade.qty
    
    if total_qty == 0:
        return None
        
    return total_cost / total_qty


async def get_trade_stats(session: AsyncSession, pair_id: int) -> dict:
    """
    Получает статистику сделок для пары.
    
    Args:
        session: Сессия базы данных
        pair_id: ID торговой пары
        
    Returns:
        Словарь со статистикой: exec_price, exec_qty, trade_count
    """
    # Получаем агрегированную статистику
    stmt = select(
        func.sum(Trade.qty).label('total_qty'),
        func.count(Trade.id).label('trade_count'),
        func.sum(Trade.price * Trade.qty).label('total_cost')
    ).where(Trade.pair_id == pair_id)
    
    result = await session.execute(stmt)
    row = result.first()
    
    if not row or not row.total_qty:
        return {
            'exec_price': None,
            'exec_qty': 0,
            'trade_count': 0
        }
    
    exec_price = row.total_cost / row.total_qty if row.total_cost else None
    
    return {
        'exec_price': exec_price,
        'exec_qty': int(row.total_qty),
        'trade_count': int(row.trade_count)
    }


async def clear_trades(session: AsyncSession, pair_id: int) -> int:
    """
    Очищает все сделки для пары (используется при Reset).
    
    Args:
        session: Сессия базы данных
        pair_id: ID торговой пары
        
    Returns:
        Количество удалённых записей
    """
    # Сначала получаем количество для возврата
    count_stmt = select(func.count(Trade.id)).where(Trade.pair_id == pair_id)
    result = await session.execute(count_stmt)
    count = result.scalar() or 0
    
    # Удаляем все сделки
    delete_stmt = delete(Trade).where(Trade.pair_id == pair_id)
    await session.execute(delete_stmt)
    await session.commit()
    
    return count
