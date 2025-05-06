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
        # Новый маппинг: trans_id -> orm_order_id
        self._trans_to_orm: Dict[int, int] = {}
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
        trans_id_raw = order_data.get("TRANS_ID")
        # Приводим trans_id к int, чтобы тип совпадал с тем, что приходит в событиях QUIK
        try:
            trans_id = int(trans_id_raw) if trans_id_raw is not None else None
        except ValueError:
            trans_id = None
        if trans_id is not None:
            self._trans_to_orm[trans_id] = orm_order_id
            # Сохраняем trans_id в ORM Order
            async with AsyncSessionLocal() as session:
                order = await session.get(Order, orm_order_id)
                if order:
                    order.trans_id = trans_id
                    await session.commit()
        resp = await self._connector.place_limit_order(order_data)
        quik_num_raw = resp.get("order_num") or resp.get("order_id")
        quik_num = int(quik_num_raw) if quik_num_raw is not None else None
        if quik_num is not None:
            self._quik_to_orm[quik_num] = orm_order_id
            self._orm_to_quik[orm_order_id] = quik_num
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

    def _find_orm_order_id(self, event: dict) -> Optional[int]:
        """
        Универсальный поиск ORM Order ID по event: сначала по trans_id, потом по quik_num.
        """
        trans_id = event.get("trans_id") or event.get("TRANS_ID")
        quik_num = event.get("order_num") or event.get("order_id")
        if quik_num is not None and quik_num in self._quik_to_orm:
            return self._quik_to_orm[quik_num]
        if trans_id is not None and trans_id in self._trans_to_orm:
            return self._trans_to_orm[trans_id]
        return None

    def on_order_event(self, event: dict):
        """
        Если есть order_num и trans_id, связываем их.
        Если ордер найден только по trans_id, обновляем его QUIK_ID.
        """
        quik_num = event.get("order_id") or event.get("order_num")
        trans_id = event.get("trans_id") or event.get("TRANS_ID")
        orm_order_id = None
        if quik_num is not None and quik_num in self._quik_to_orm:
            orm_order_id = self._quik_to_orm[quik_num]
        elif trans_id is not None and trans_id in self._trans_to_orm:
            orm_order_id = self._trans_to_orm[trans_id]
            # Если появился новый quik_num, связываем с ORM-ордером
            if quik_num is not None and quik_num not in self._quik_to_orm:
                self._quik_to_orm[quik_num] = orm_order_id
                self._orm_to_quik[orm_order_id] = quik_num
                asyncio.create_task(self._update_order_quik_num(orm_order_id, quik_num))
        if orm_order_id is None:
            logger.warning(f"[ORDER_EVENT] Не найден ORM Order для QUIK ID {quik_num} или TRANS_ID {trans_id}")
            return
        status = event.get("status")
        filled = event.get("filled")
        asyncio.create_task(self._update_order_status(orm_order_id, status, filled))

    def on_trade_event(self, event: dict):
        """
        Ищем по QUIK_ID, если нет — по trans_id.
        """
        quik_num = event.get("order_num") or event.get("order_id")
        trans_id = event.get("trans_id") or event.get("TRANS_ID")
        orm_order_id = None
        if quik_num is not None and quik_num in self._quik_to_orm:
            orm_order_id = self._quik_to_orm[quik_num]
        elif trans_id is not None and trans_id in self._trans_to_orm:
            orm_order_id = self._trans_to_orm[trans_id]
        if orm_order_id is None:
            logger.warning(f"[TRADE] Не найден ORM Order для QUIK ID {quik_num} или TRANS_ID {trans_id}")
            return
        async def update():
            async with AsyncSessionLocal() as session:
                order = await session.get(Order, orm_order_id)
                if order:
                    qty = event.get("qty") or 0
                    order.filled = (order.filled or 0) + qty
                    order.leaves_qty = max(order.qty - order.filled, 0)
                    # PARTIAL или FILLED
                    if order.filled >= order.qty:
                        order.status = OrderStatus.FILLED
                    else:
                        order.status = OrderStatus.PARTIAL
                    await session.commit()
                    logger.info(f"[TRADE] Order {order.id} обновлён: filled={order.filled}, leaves_qty={order.leaves_qty}, status={order.status}")
        asyncio.create_task(update())

    def on_trans_reply_event(self, event: dict):
        """
        Обработка события OnTransReply: ошибки, REJECTED, CANCELLED и др.
        Если есть TRANS_ID, ищем ORM-ордер по нему.
        Если есть ошибка — обновляем статус ордера.
        """
        trans_id = event.get("trans_id") or event.get("TRANS_ID")
        quik_num = event.get("order_num") or event.get("order_id")
        orm_order_id = None
        if trans_id is not None and trans_id in self._trans_to_orm:
            orm_order_id = self._trans_to_orm[trans_id]
        elif quik_num is not None and quik_num in self._quik_to_orm:
            orm_order_id = self._quik_to_orm[quik_num]
        if orm_order_id is None:
            logger.warning(f"[TRANS_REPLY] Не найден ORM Order для QUIK ID {quik_num} или TRANS_ID {trans_id}")
            return
        # Если появился новый quik_num, связываем с ORM-ордером
        if quik_num is not None and quik_num not in self._quik_to_orm:
            self._quik_to_orm[quik_num] = orm_order_id
            self._orm_to_quik[orm_order_id] = quik_num
            asyncio.create_task(self._update_order_quik_num(orm_order_id, quik_num))
        status = event.get("status")
        error_code = event.get("error_code")
        error_msg = event.get("error_msg")
        async def update():
            async with AsyncSessionLocal() as session:
                order = await session.get(Order, orm_order_id)
                if order:
                    if error_code or (status and status.upper() == "REJECTED"):
                        order.status = OrderStatus.REJECTED
                        logger.error(f"[TRANS_REPLY] Order {order.id} REJECTED: {error_code} {error_msg}")
                    elif status and status.upper() == "CANCELLED":
                        order.status = OrderStatus.CANCELLED
                        logger.info(f"[TRANS_REPLY] Order {order.id} CANCELLED")
                    await session.commit()
        asyncio.create_task(update()) 