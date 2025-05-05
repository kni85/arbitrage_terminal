"""
`core.order_manager` – менеджер ордеров для стратегий.

* Выставляет/отменяет ордера через QuikConnector.
* Ведёт маппинг QUIK ID ↔ ORM Order.
* Обновляет статусы ордеров в базе.
* Предоставляет единый интерфейс для стратегий (стратегии не работают напрямую с QuikConnector).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from .quik_connector import QuikConnector
from ..db.database import AsyncSessionLocal
from ..db.models import Order, OrderStatus

logger = logging.getLogger(__name__)

class OrderManager:
    """Менеджер ордеров: выставление, отмена, отслеживание статусов."""

    def __init__(self):
        self._connector = QuikConnector()
        # Маппинг QUIK ID (quik_num) ↔ id ORM Order
        self._quik_to_orm: Dict[int, int] = {}
        self._orm_to_quik: Dict[int, int] = {}
        # Подписка на заявки больше не требуется, rely on OnOrder/OnTrade/OnTransReply events

    @staticmethod
    def _get_instance_for_connector(connector):
        # singleton для интеграции с QuikConnector
        if not hasattr(connector, "_order_manager_instance"):
            connector._order_manager_instance = OrderManager()
        return connector._order_manager_instance

    async def place_limit_order(self, order_data: dict, orm_order_id: int, strategy_id: int = None) -> Optional[int]:
        """
        Выставляет лимитный ордер через QuikConnector.
        order_data — dict с параметрами для QUIK (ACTION, CLASSCODE, SECCODE, PRICE, QUANTITY, ...)
        orm_order_id — id ORM Order, который будет связан с QUIK ID
        strategy_id — id стратегии (если требуется связка)
        Возвращает QUIK ID (quik_num) или None.
        """
        resp = await self._connector.place_limit_order(order_data)
        quik_num = resp.get("order_num") or resp.get("order_id")
        if quik_num is not None:
            self._quik_to_orm[quik_num] = orm_order_id
            self._orm_to_quik[orm_order_id] = quik_num
            # Обновляем quik_num и strategy_id в БД
            await self._update_order_quik_num(orm_order_id, quik_num, strategy_id)
        return quik_num

    async def cancel_order(self, orm_order_id: int) -> None:
        """Отменяет ордер по внутреннему id (через маппинг на QUIK ID)."""
        quik_num = self._orm_to_quik.get(orm_order_id)
        if quik_num is None:
            logger.warning(f"Нет QUIK ID для ORM Order {orm_order_id}")
            return
        await self._connector.cancel_order(str(quik_num))

    async def _update_order_quik_num(self, orm_order_id: int, quik_num: int, strategy_id: int = None) -> None:
        """Обновляет поле quik_num и strategy_id в ORM Order."""
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, orm_order_id)
            if order:
                order.quik_num = quik_num
                if strategy_id is not None:
                    order.strategy_id = strategy_id
                await session.commit()

    async def _update_order_status(self, orm_order_id: int, status: OrderStatus, filled: int = None) -> None:
        """Обновляет статус, исполненный объём и leaves_qty ордера в БД."""
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, orm_order_id)
            if order:
                order.status = status
                if filled is not None:
                    order.filled = filled
                    # Корректно рассчитываем leaves_qty
                    order.leaves_qty = max(order.qty - order.filled, 0)
                await session.commit()

    def _on_order_event(self, event: dict) -> None:
        """
        Обработчик событий по заявкам от QuikConnector.
        event — dict с полями order_id (QUIK), status, filled и др.
        """
        quik_num = event.get("order_id") or event.get("order_num")
        status = event.get("status")
        filled = event.get("filled")
        orm_order_id = self._quik_to_orm.get(quik_num)
        if orm_order_id is None:
            logger.warning(f"Не найден ORM Order для QUIK ID {quik_num}")
            return
        # Асинхронно обновляем статус в БД
        asyncio.create_task(self._update_order_status(orm_order_id, status, filled))

    def on_order_event(self, event: dict):
        self._on_order_event(event)

    def on_trade_event(self, event: dict):
        # Здесь можно реализовать обновление filled, status и т.д. по сделке
        pass

    def on_trans_reply_event(self, event: dict):
        # Здесь можно реализовать обработку REJECTED, ошибок, подтверждений
        pass 