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
from ..db.models import Order, OrderStatus, Side
from ..db.models import Instrument

logger = logging.getLogger(__name__)

class OrderManager:
    """Менеджер ордеров: выставление, отмена, отслеживание статусов."""

    @staticmethod
    def _to_int(value):
        """Пробует привести значение к int, иначе возвращает как есть."""
        try:
            return int(value) if value is not None else None
        except (ValueError, TypeError):
            return value

    def __init__(self):
        self._connector = QuikConnector()
        # Регистрируем себя в QuikConnector (перезаписываем), чтобы callbacks шли именно в текущий экземпляр
        self._connector._order_manager_instance = self  # type: ignore[attr-defined]
        # Сохраняем текущий event-loop (нужен для вызовов из CallbackThread)
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        # Маппинг QUIK ID (quik_num) ↔ id ORM Order
        self._quik_to_orm: Dict[int, int] = {}
        self._orm_to_quik: Dict[int, int] = {}
        # Новый маппинг: trans_id -> orm_order_id
        self._trans_to_orm: Dict[Any, int] = {}
        # Сохраняем CLASSCODE & SECCODE для каждого ORM-ордера
        self._orm_to_contract: Dict[int, tuple[str, str]] = {}
        # Сохраняем ACCOUNT для каждой заявки (нужно для MOVE_ORDERS)
        self._orm_to_account: Dict[int, str] = {}
        # Сохраняем CLIENT_CODE, если есть – нужен для MOVE_ORDERS
        self._orm_to_client: Dict[int, str] = {}
        # Сохраняем ORDER_KEY (внутренний ключ QUIK), который нужен для MOVE_ORDERS
        self._orm_to_order_key: Dict[int, str] = {}
        # Подписка на заявки больше не требуется, rely on OnOrder/OnTrade/OnTransReply events

        # Совместимость с ранними тестами, где вызываются приватные методы
        self._on_order_event = self.on_order_event  # type: ignore[attr-defined]
        self._on_trade_event = self.on_trade_event  # type: ignore[attr-defined]
        self._on_trans_reply_event = self.on_trans_reply_event  # type: ignore[attr-defined]

    @staticmethod
    def _get_instance_for_connector(connector):
        # Возвращаем уже привязанный экземпляр
        return connector._order_manager_instance  # type: ignore[attr-defined]

    def _register_trans_mapping(self, trans_id: Any, orm_order_id: int):
        """Сохраняет привязку trans_id → orm_order_id для int и str форматов."""
        if trans_id is None:
            return
        self._trans_to_orm[trans_id] = orm_order_id
        self._trans_to_orm[str(trans_id)] = orm_order_id

    def _register_quik_mapping(self, quik_num: Any, orm_order_id: int):
        """Сохраняет привязку quik_num → orm_order_id для int и str форматов."""
        if quik_num is None:
            return
        self._quik_to_orm[quik_num] = orm_order_id
        self._quik_to_orm[str(quik_num)] = orm_order_id
        self._orm_to_quik[orm_order_id] = quik_num

    async def place_limit_order(self, order_data: dict, orm_order_id: int, strategy_id: int = None) -> Optional[int]:
        """
        Выставляет лимитный ордер через QuikConnector.
        order_data — dict с параметрами для QUIK (ACTION, CLASSCODE, SECCODE, PRICE, QUANTITY, ...)
        orm_order_id — id ORM Order, который будет связан с QUIK ID
        strategy_id — id стратегии (если требуется связка)
        Возвращает QUIK ID (quik_num) или None.
        """
        # Получаем/вычисляем TRANS_ID
        trans_id_raw = order_data.get("TRANS_ID")
        if trans_id_raw is None:
            from sqlalchemy.ext.asyncio import AsyncSession
            from backend.trading.order_service import get_next_trans_id
            async with AsyncSessionLocal() as session:  # type: AsyncSession
                trans_id_generated = await get_next_trans_id(session)
            order_data["TRANS_ID"] = str(trans_id_generated)
            trans_id_raw = trans_id_generated
        try:
            trans_id = int(trans_id_raw) if trans_id_raw is not None else None
        except ValueError:
            trans_id = None
        if trans_id is not None:
            self._register_trans_mapping(trans_id, orm_order_id)
        # Сохраняем контракт
        class_code = order_data.get("CLASSCODE") or order_data.get("CLASS_CODE")
        sec_code = order_data.get("SECCODE") or order_data.get("SEC_CODE")
        if class_code and sec_code:
            self._orm_to_contract[orm_order_id] = (class_code, sec_code)

        # Сохраняем торговый счёт
        account = order_data.get("ACCOUNT") or order_data.get("ACCOUNT_ID")
        if account:
            self._orm_to_account[orm_order_id] = str(account)

        # Сохраняем CLIENT_CODE, если есть – нужен для MOVE_ORDERS
        client_code = order_data.get("CLIENT_CODE")
        if client_code:
            self._orm_to_client[orm_order_id] = str(client_code)

        resp = await self._connector.place_limit_order(order_data)
        quik_num_raw = resp.get("order_num") or resp.get("order_id")
        if quik_num_raw is not None:
            quik_num = int(quik_num_raw)
            self._register_quik_mapping(quik_num, orm_order_id)
            await self._update_order_quik_num(orm_order_id, quik_num, strategy_id)
            return quik_num
        # QUIK не вернул order_num — ждём события OnOrder/OnTransReply, где он придёт.
        logger.info("place_limit_order: QUIK не вернул order_num, ждём callback-событие")
        return None

    async def cancel_order(self, orm_order_id: int) -> None:
        """Отменяет ордер по внутреннему id (через маппинг на QUIK ID).

        Создаём новый TRANS_ID для операции отмены, чтобы можно было отследить
        подтверждение OnTransReply даже если в событии не придёт order_num.
        """
        order_key = self._orm_to_order_key.get(orm_order_id)
        quik_num = self._orm_to_quik.get(orm_order_id)
        if order_key is None and quik_num is None:
            logger.warning("Нет ORDER_KEY/QUIK ID для ORM Order %s", orm_order_id)
            return

        # Получаем CLASSCODE / SECCODE из ORM
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, orm_order_id)
            if not order:
                logger.error("Order %s not found while cancelling", orm_order_id)
                return
            instrument = await session.get(Instrument, order.instrument_id)
            if instrument:
                class_code = instrument.board
                sec_code = instrument.ticker
            else:
                # Fallback: используем сохранённый контракт
                contract = self._orm_to_contract.get(orm_order_id)
                if contract:
                    class_code, sec_code = contract
                else:
                    # Нет данных контракта – пытаемся отменить только по ORDER_KEY (подходит для моков/Dummy)
                    await self._connector.cancel_order(str(order_key or quik_num))  # type: ignore[arg-type]
                    await self._update_order_status(orm_order_id, OrderStatus.CANCELLED)
                    return

        import random
        # TRANS_ID должен быть положительным 32-битным int (≤ 2_147_483_647)
        trans_id = random.randint(1, 2_000_000_000)
        self._register_trans_mapping(trans_id, orm_order_id)
        resp = await self._connector.cancel_order(
            str(order_key or quik_num),
            class_code,
            sec_code,
            trans_id=trans_id,
        )
        logger.info(f"Cancel order response: {resp}")
        # Обновим статус локально – если QUIK подтвердил приём транзакции (resp['data'] == True)
        if resp.get("data") in (True, 1, "1", "True"):
            # status изменится на CANCELLED; filled не трогаем
            await self._update_order_status(orm_order_id, OrderStatus.CANCELLED)

    async def modify_order(self, orm_order_id: int, new_price: float, new_qty: int | None = None) -> None:
        """Изменяет цену (и при необходимости объём) активного ордера через транзакцию MOVE_ORDERS.

        В QUIK изменение заявки выполняется через MOVE_ORDERS с указанием ORDER_KEY и новых параметров.
        """
        order_key = self._orm_to_order_key.get(orm_order_id)
        quik_num = self._orm_to_quik.get(orm_order_id)
        if order_key is None and quik_num is None:
            logger.warning("Нет ORDER_KEY/QUIK ID для ORM Order %s", orm_order_id)
            return

        # Определяем CLASSCODE / SECCODE
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, orm_order_id)
            if not order:
                logger.error("Order %s not found while modifying", orm_order_id)
                return
            instrument = await session.get(Instrument, order.instrument_id)
            if instrument:
                class_code = instrument.board
                sec_code = instrument.ticker
            else:
                contract = self._orm_to_contract.get(orm_order_id)
                if not contract:
                    logger.error("Не удалось определить CLASS/SECCODE для ордера %s", orm_order_id)
                    return
                class_code, sec_code = contract

        account = self._orm_to_account.get(orm_order_id)
        client_code = self._orm_to_client.get(orm_order_id)

        import random
        trans_id = random.randint(1, 2_000_000_000)
        self._register_trans_mapping(trans_id, orm_order_id)

        qty_for_move: int | None = new_qty if new_qty is not None else (order.qty if order else None)

        # Определяем операцию: 'B' — покупка, 'S' — продажа
        operation = "B" if order and order.side == Side.LONG else "S"

        # --- Решаем, как менять цену ---
        # На акциях (класс кода начинается с 'TQ') биржа не поддерживает MOVE_ORDERS,
        # поэтому делаем «отмена + новая заявка». На срочном рынке (SPBFUT, etc.)
        # MOVE_ORDERS сработает быстрее.
        use_move_orders = bool(class_code) and not str(class_code).upper().startswith("TQ")

        if use_move_orders:
            resp = await self._connector.modify_order(
                order_id=str(order_key or quik_num),
                class_code=class_code,
                sec_code=sec_code,
                price=new_price,
                qty=qty_for_move,
                operation=operation,
                order_type="L",  # изменяем лимитную заявку
                account=account,
                client_code=client_code,
                trans_id=trans_id,
            )
            logger.info("Modify order response: %s", resp)

            # Проверяем, принята ли транзакция: result == 0 и data == True
            move_ok = False
            if isinstance(resp, dict):
                move_ok = resp.get("result") in (0, None) and resp.get("data") not in (False, 0, "0", "False")

            if move_ok:
                # Обновляем локально цену/объём
                await self._update_order_price(orm_order_id, new_price, qty_for_move)
                return  # DONE – биржа приняла MOVE_ORDERS

            logger.warning("MOVE_ORDERS не принят брокером – fallback to cancel + new")

        # --- Fallback / Stock market: cancel + new ------------------------------------------------
        await self.cancel_order(orm_order_id)

        # Формируем данные для новой заявки (используем тот же ORM ID)
        new_order_data = {
            "ACTION": "NEW_ORDER",
            "CLASSCODE": class_code,
            "SECCODE": sec_code,
            "ACCOUNT": account,
            "OPERATION": operation,
            "PRICE": str(new_price),
            "QUANTITY": str(qty_for_move or order.qty),
            "CLIENT_CODE": client_code,
        }

        import random, asyncio as _aio
        new_order_data["TRANS_ID"] = str(random.randint(1, 2_000_000_000))

        # Дадим бирже время обработать отмену (обычно сотни миллисекунд)
        await _aio.sleep(0.2)

        await self.place_limit_order(new_order_data, orm_order_id)

        # Локально обновляем цену/кол-во сразу
        await self._update_order_price(orm_order_id, new_price, qty_for_move)

        return

    async def _update_order_price(self, orm_order_id: int, price: float, qty: int | None = None) -> None:
        """Обновляет цену и/или объём ордера в БД."""
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, orm_order_id)
            if order:
                order.price = price
                if qty is not None:
                    order.qty = qty
                await session.commit()

    async def _update_order_quik_num(self, orm_order_id: int, quik_num: int, strategy_id: int = None) -> None:
        """Обновляет поле quik_num и strategy_id в ORM Order."""
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, orm_order_id)
            if order:
                order.quik_num = quik_num
                if strategy_id is not None:
                    order.strategy_id = strategy_id
                await session.commit()

    async def _update_order_status(self, orm_order_id: int, status: OrderStatus | None, filled: int = None) -> None:
        """Обновляет статус, исполненный объём и leaves_qty ордера в БД.

        Если `status` равен None, статус ордера не изменяется (некоторые события OnOrder не
        содержат поля status).
        """
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, orm_order_id)
            if order:
                if status is not None:  # обновляем только если передан
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
        order_key_val = event.get("order_key") or event.get("ORDER_KEY")
        quik_num = self._to_int(event.get("order_id") or event.get("order_num"))
        trans_id = self._to_int(event.get("trans_id") or event.get("TRANS_ID"))
        orm_order_id = None
        if order_key_val is not None and order_key_val in self._quik_to_orm:
            orm_order_id = self._quik_to_orm[order_key_val]
        elif quik_num is not None and quik_num in self._quik_to_orm:
            orm_order_id = self._quik_to_orm[quik_num]
        elif trans_id is not None and trans_id in self._trans_to_orm:
            orm_order_id = self._trans_to_orm[trans_id]
            # Если появился новый quik_num, связываем с ORM-ордером
            if quik_num is not None and quik_num not in self._quik_to_orm:
                self._register_quik_mapping(quik_num, orm_order_id)
        if orm_order_id is None:
            logger.warning(f"[ORDER_EVENT] Не найден ORM Order для QUIK ID {quik_num} или TRANS_ID {trans_id}")
            return
        status = event.get("status")
        filled = event.get("filled")

        # --- сохраняем ACCOUNT / CLIENT_CODE, если появились в callback'е ---
        if orm_order_id is not None:
            acc = event.get("ACCOUNT") or event.get("ACCOUNT_ID") or event.get("account")
            if acc and orm_order_id not in self._orm_to_account:
                self._orm_to_account[orm_order_id] = str(acc)

            client_code_cb = event.get("CLIENT_CODE") or event.get("client_code")
            if client_code_cb and orm_order_id not in self._orm_to_client:
                self._orm_to_client[orm_order_id] = str(client_code_cb)

            # ORDER_KEY
            if order_key_val:
                self._orm_to_order_key.setdefault(orm_order_id, str(order_key_val))

        self._schedule(self._update_order_status(orm_order_id, status, filled))

    def on_trade_event(self, event: dict):
        """
        Ищем по QUIK_ID, если нет — по trans_id.
        """
        quik_num = self._to_int(event.get("order_num") or event.get("order_id"))
        trans_id = self._to_int(event.get("trans_id") or event.get("TRANS_ID"))
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
        self._schedule(update())

    def on_trans_reply_event(self, event: dict):
        """
        Обработка события OnTransReply: ошибки, REJECTED, CANCELLED и др.
        Если есть TRANS_ID, ищем ORM-ордер по нему.
        Если есть ошибка — обновляем статус ордера.
        """
        trans_id = self._to_int(event.get("trans_id") or event.get("TRANS_ID"))
        quik_num = self._to_int(event.get("order_num") or event.get("order_id"))
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
            self._register_quik_mapping(quik_num, orm_order_id)
        status_raw = event.get("status")
        status_norm = str(status_raw).upper() if status_raw is not None else ""
        error_code = event.get("error_code")
        error_msg = event.get("error_msg")
        async def update():
            async with AsyncSessionLocal() as session:
                order = await session.get(Order, orm_order_id)
                if order:
                    if (error_code not in (0, None, "0", "")) or status_norm == "REJECTED":
                        order.status = OrderStatus.REJECTED
                        logger.error(f"[TRANS_REPLY] Order {order.id} REJECTED: {error_code} {error_msg}")
                    elif status_norm == "CANCELLED":
                        order.status = OrderStatus.CANCELLED
                        logger.info(f"[TRANS_REPLY] Order {order.id} CANCELLED")
                    await session.commit()
        self._schedule(update())

    def _schedule(self, coro):
        """Безопасно запускает coroutine из любого потока."""
        try:
            # Если уже внутри работающего цикла
            loop = asyncio.get_running_loop()
            return loop.create_task(coro)
        except RuntimeError:
            # Мы в другом потоке; используем сохранённый loop
            if self._loop and self._loop.is_running():
                return asyncio.run_coroutine_threadsafe(coro, self._loop)
            # Fallback: выполняем синхронно в отдельном временном цикле (нежелательно, но надёжно)
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close() 