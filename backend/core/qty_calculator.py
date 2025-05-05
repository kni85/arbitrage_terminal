"""
Модуль qty_calculator — расчёт объёмов (qty) для арбитражных стратегий.

* Позволяет вычислять объёмы по первой ноге и пропорционально остальным.
* Учитывает qty_ratio (число или формула) и lot_size инструмента.
"""

from typing import List, Dict, Any

class QtyCalculator:
    """
    Калькулятор объёмов для арбитражных стратегий.
    """
    def __init__(self, legs: List[Dict[str, Any]]):
        """
        legs — список ног, каждая нога: dict с ключами:
            - qty_ratio: коэффициент объёма (число или формула)
            - lot_size: размер лота инструмента
            - (опционально) другие параметры
        """
        self.legs = legs

    def calc_qtys(self, base_qty: int) -> List[int]:
        """
        Вычисляет объёмы для всех ног, исходя из объёма первой ноги (base_qty).
        Возвращает список qty для каждой ноги.
        """
        qtys = []
        for i, leg in enumerate(self.legs):
            if i == 0:
                qty = base_qty
            else:
                ratio = leg.get("qty_ratio", 1)
                if isinstance(ratio, str):
                    # Пробуем вычислить формулу (например, 'base_qty * 1000')
                    try:
                        qty = int(eval(ratio, {"base_qty": base_qty}))
                    except Exception:
                        qty = base_qty
                else:
                    qty = int(base_qty * float(ratio))
            # Округляем до целого числа лотов
            lot_size = leg.get("lot_size", 1)
            qty = max((qty // lot_size) * lot_size, lot_size)
            qtys.append(qty)
        return qtys 