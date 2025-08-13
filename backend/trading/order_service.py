from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Order  # type: ignore

__all__ = ["get_next_trans_id"]


async def get_next_trans_id(session: AsyncSession) -> int:
    """Возвращает следующий TRANS_ID для текущего дня.

    Алгоритм:
    1. Берём максимальный trans_id среди ордеров, созданных **сегодня**.
    2. Если записей нет — возвращаем 1.
    3. Иначе — max + 1.
    """
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    stmt = (
        select(func.max(Order.trans_id))
        .where(Order.created_at >= today_start)
    )
    result = await session.execute(stmt)
    max_trans_id: int | None = result.scalar()
    return (max_trans_id or 0) + 1 