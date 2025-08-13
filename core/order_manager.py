"""OrderManager – управление жизненным циклом заявок.

Перенесён из `backend.quik_connector.core.order_manager`, адаптирован
к новой структуре (infra.quik, Broker-интерфейс).
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, Optional

from infra.quik_adapter import QuikBrokerAdapter
from core.broker import Broker
from infra.quik import QuikConnector

# ORM
from db.database import AsyncSessionLocal
from backend.trading.order_service import get_next_trans_id  # noqa: E501 – сохранён старый путь
from db.models import Order, OrderStatus, Side, Instrument


logger = logging.getLogger(__name__)


class OrderManager:  # noqa: D101
    def __init__(self, broker: Broker | None = None):
        # Broker через DI; fallback – создать адаптер QUIK
        self._broker: Broker = broker or QuikBrokerAdapter()

        # Для совместимости оставляем ссылку _connector
        self._connector = self._broker  # type: ignore

        # если underlying QuikConnector доступен, регистрируемся для callbacks
        underlying_qc = getattr(self._broker, "_connector", None)
        if isinstance(underlying_qc, QuikConnector):
            underlying_qc._order_manager_instance = self  # type: ignore[attr-defined]

        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

        self._quik_to_orm: Dict[int, int] = {}
        self._orm_to_quik: Dict[int, int] = {}
        self._trans_to_orm: Dict[Any, int] = {}
        self._orm_to_contract: Dict[int, tuple[str, str]] = {}
        self._orm_to_account: Dict[int, str] = {}
        self._orm_to_client: Dict[int, str] = {}
        self._orm_to_order_key: Dict[int, str] = {}

    # -------------------- helpers -------------------------------------
    @staticmethod
    def _to_int(value):
        try:
            return int(value) if value is not None else None
        except (ValueError, TypeError):
            return value

    # -------------------- API -----------------------------------------
    async def place_limit_order(self, order_data: dict, orm_order_id: int, strategy_id: int | None = None):  # noqa: E501
        trans_id = order_data.get("TRANS_ID")
        if trans_id is None:
            async with AsyncSessionLocal() as sess:
                trans_id = await get_next_trans_id(sess)
            order_data["TRANS_ID"] = str(trans_id)

        self._register_trans_mapping(trans_id, orm_order_id)

        result = await self._broker.place_limit_order(order_data)
        quik_num_raw = result.get("order_num") or result.get("order_id")
        if quik_num_raw:
            quik_num = int(quik_num_raw)
            self._register_quik_mapping(quik_num, orm_order_id)
            await self._update_order_quik_num(orm_order_id, quik_num, strategy_id)
        return result

    # ---- cancel / modify (kept minimal, same logic) ------------------

    async def cancel_order(self, orm_order_id: int):  # noqa: D401
        # simplistic version: call broker.cancel_order by quik_num if mapped
        quik_num = self._orm_to_quik.get(orm_order_id)
        if quik_num is None:
            logger.warning("cancel_order: no quik id mapped for orm %s", orm_order_id)
            return
        await self._broker.cancel_order(str(quik_num))  # type: ignore[arg-type]

    # -------------------- internal mapping helpers --------------------
    def _register_trans_mapping(self, trans_id: Any, orm_id: int):
        if trans_id is None:
            return
        self._trans_to_orm[trans_id] = orm_id
        self._trans_to_orm[str(trans_id)] = orm_id

    def _register_quik_mapping(self, quik_num: Any, orm_id: int):
        self._quik_to_orm[quik_num] = orm_id
        self._quik_to_orm[str(quik_num)] = orm_id
        self._orm_to_quik[orm_id] = quik_num

    # -------------------- ORM updates (simplified) ---------------------
    async def _update_order_quik_num(self, orm_id: int, quik_num: int, strategy_id: int | None):
        async with AsyncSessionLocal() as sess:
            order = await sess.get(Order, orm_id)
            if order:
                order.quik_num = quik_num
                if strategy_id is not None:
                    order.strategy_id = strategy_id
                await sess.commit()

    # -------------------- callbacks (minimal stubs) -------------------
    def on_order_event(self, event: dict):  # noqa: D401
        pass  # detailed implementation can be restored later

    def on_trade_event(self, event: dict):  # noqa: D401
        pass

    def on_trans_reply_event(self, event: dict):  # noqa: D401
        pass

    # -------------------- util ----------------------------------------
    def _schedule(self, coro):
        try:
            loop = asyncio.get_running_loop()
            return loop.create_task(coro)
        except RuntimeError:
            if self._loop and self._loop.is_running():
                return asyncio.run_coroutine_threadsafe(coro, self._loop)
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()

__all__ = ["OrderManager"]
