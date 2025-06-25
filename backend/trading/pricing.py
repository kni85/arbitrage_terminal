"""pricing.py – утилиты для расчёта цены исполнения объёмом.

Функции рассчитывают средневзвешенную цену, по которой будет
исполнен рыночный ордер указанного объёма, исходя из текущего
стакана заявок.

Стакан передаётся как список уровней `[price, qty]`:
    bids – цены и лоты на покупку (сортировка не важна)
    asks – цены и лоты на продажу

Никакого округления на выходе не выполняется – возвращается float.
"""
from __future__ import annotations

from typing import List, Sequence

__all__ = [
    "avg_price_to_sell",
    "avg_price_to_buy",
]


def _avg_price(levels: Sequence[Sequence[float]], qty: float, reverse: bool) -> float | None:  # noqa: D401
    """Вычисляет средневзвешенную цену для сделки *qty* лотов.

    Параметры
    ---------
    levels : [[price, qty], ...]
        Уровни стакана: цена, доступный объём (лоты).
    qty : float
        Сколько лотов хотим купить/продать.
    reverse : bool
        Порядок обхода уровней:
            • False – от лучшей цены к худшей (asks для покупки)
            • True  – от худшей цены к лучшей (bids для продажи)
    """
    if qty <= 0:
        return 0.0

    # сортируем уровни нужным образом
    levels_sorted = sorted(levels, key=lambda x: x[0], reverse=reverse)

    need = qty
    cost = 0.0  # сумма price * exec_qty

    for price, avail in levels_sorted:
        exec_qty = min(avail, need)
        cost += price * exec_qty
        need -= exec_qty
        if need <= 0:
            break

    if need > 0:  # стакан «тонкий» – объёма не хватило
        return None

    return cost / qty


def avg_price_to_sell(bids: List[List[float]], qty: float) -> float | None:  # noqa: D401
    """Средневзвешенная цена исполнения *рыночной продажи* qty лотов."""
    return _avg_price(bids, qty, reverse=False)


def avg_price_to_buy(asks: List[List[float]], qty: float) -> float | None:  # noqa: D401
    """Средневзвешенная цена исполнения *рыночной покупки* qty лотов."""
    return _avg_price(asks, qty, reverse=True) 