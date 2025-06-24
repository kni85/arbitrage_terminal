"""
`core.quik_connector` – асинхронная обёртка (singleton) над **QuikPy**.

Особенности
-----------
* Один экземпляр на приложение (singleton).
* Подписка/отписка на стакан L2 (`best bid/ask`).
* Подписка/отписка на сделки (trades).
* Подписка/отписка на заявки (orders).
* Асинхронная очередь событий для стратегий (`await connector.events()`).
* Методы выставления/отмены заявок (лимит / маркет).
* Автоподстройка под разные имена методов `QuikPy` (camelCase vs snake_case).
* Работает оф‑лайн через `DummyQuikPy` – полезно для разработки без терминала.

Структура событий в очереди:
---------------------------
Каждое событие — dict с ключом `type`:
- `type: 'quote'` — обновление стакана (L2): {class_code, sec_code, bid, ask, ...}
- `type: 'trade'` — новая сделка: {class_code, sec_code, price, qty, side, ...}
- `type: 'order'` — обновление заявки: {order_id, status, filled, ...}
- `type: 'error'` — ошибка: {message, details, ...}

"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Импортируем QuikPy (или создаём заглушку)
# ---------------------------------------------------------------------------
try:
    from QuikPy import QuikPy  # type: ignore
except ImportError as exc:  # pragma: no cover – офлайн‑режим
    print(f"!!! ВНИМАНИЕ: QuikPy не найден ({exc}) — используется DummyQuikPy.")
    logger.warning("QuikPy не найден (%s) — используется DummyQuikPy.", exc)

    class QuikPy:  # type: ignore[override]
        """Заглушка: только логирует вызовы."""

        def __init__(
            self,
            host: str | None = None,
            requests_port: int = 34130,
            callbacks_port: int = 34131,
        ) -> None:
            self.host = host or "localhost"
            self.requests_port = requests_port
            self.callbacks_port = callbacks_port
            logger.info(
                "DummyQuikPy:init host=%s req_port=%s cb_port=%s",
                self.host,
                self.requests_port,
                self.callbacks_port,
            )

        # --- Подписки ---------------------------------------------------
        def subscribe_level2_quotes(self, class_code: str, sec_code: str):
            logger.info("DummyQuikPy: subscribe L2 %s %s", class_code, sec_code)

        def unsubscribe_level2_quotes(self, class_code: str, sec_code: str):
            logger.info("DummyQuikPy: unsubscribe L2 %s %s", class_code, sec_code)

        # --- Подписки на сделки (trades) ---
        def subscribe_trades(self, class_code: str, sec_code: str):
            logger.info("DummyQuikPy: subscribe trades %s %s", class_code, sec_code)

        def unsubscribe_trades(self, class_code: str, sec_code: str):
            logger.info("DummyQuikPy: unsubscribe trades %s %s", class_code, sec_code)

        # --- Торговля ----------------------------------------------------
        def send_transaction(self, tr: dict[str, Any]):
            print(f"!!! DummyQuikPy: send_transaction {tr}")
            logger.info("DummyQuikPy: send_transaction %s", tr)
            return {"result": 0, "message": "stub"}

        # --- Завершение --------------------------------------------------
        def close_connection_and_thread(self):
            logger.info("DummyQuikPy: close connection")

# ---------------------------------------------------------------------------
QuoteCallback = Callable[[dict[str, Any]], None]
TradeCallback = Callable[[dict[str, Any]], None]
OrderCallback = Callable[[dict[str, Any]], None]

class QuikConnector:
    """Асинхронная обёртка над QuikPy (singleton)."""

    _instance: Optional["QuikConnector"] = None
    _lock = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------
    # Инициализация
    # ------------------------------------------------------------------

    def __init__(
        self,
        host: str | None = None,
        requests_port: int = 34130,
        callbacks_port: int = 34131,
    ) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        host_real = host or "127.0.0.1"
        self._qp: Any = QuikPy(
            host=host_real,
            requests_port=requests_port,
            callbacks_port=callbacks_port,
        )

        # --- Привязываем callback-методы QuikPy к локальным обработчикам ---
        # Это позволяет OrderManager получать события OnOrder / OnTrade / OnTransReply
        # сразу после их прихода из QUIK.
        # Если пользователь уже настроил свои обработчики, их можно обернуть, но
        # для текущей цели достаточно прямого назначения.
        self._qp.on_order = self._on_order  # type: ignore[attr-defined]
        self._qp.on_trade = self._on_trade  # type: ignore[attr-defined]
        self._qp.on_trans_reply = self._on_trans_reply  # type: ignore[attr-defined]

        self._quote_callbacks: Dict[str, list[QuoteCallback]] = {}
        self._trade_callbacks: Dict[str, list[TradeCallback]] = {}
        self._order_callbacks: Dict[str, list[OrderCallback]] = {}
        self._event_queue: "asyncio.Queue[dict[str, Any]]" = asyncio.Queue(maxsize=1000)
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

        self._stop_quote_thread = threading.Event()
        self._quote_thread = threading.Thread(
            target=self._quote_listener_loop,
            name="QP-quotes",
            daemon=True,
        )
        self._quote_thread.start()

        logger.info(
            "QuikConnector initialised (host=%s, req_port=%s, cb_port=%s)",
            host_real,
            requests_port,
            callbacks_port,
        )

    # ------------------------------------------------------------------
    # Вспомогательные вызовы с fallback имён методов
    # ------------------------------------------------------------------

    def _call(self, *names: str, default: Any = None, **kwargs: Any) -> Any:  # noqa: ANN401
        """Попытаться вызвать первый доступный метод `QuikPy` из списка имён."""
        for name in names:
            func = getattr(self._qp, name, None)
            if func is not None:
                return func(**kwargs) if kwargs else func(*())
        raise AttributeError(f"None of methods {names} found in QuikPy")

    # ------------------------------------------------------------------
    # Подписки на стакан L2
    # ------------------------------------------------------------------

    def subscribe_quotes(self, class_code: str, sec_code: str, cb: QuoteCallback) -> None:
        key = f"{class_code}.{sec_code}"
        self._quote_callbacks.setdefault(key, []).append(cb)
        if len(self._quote_callbacks[key]) == 1:
            self._qp.subscribe_level2_quotes(class_code, sec_code)
            logger.info("Subscribed L2 %s", key)

    def unsubscribe_quotes(self, class_code: str, sec_code: str, cb: QuoteCallback) -> None:
        key = f"{class_code}.{sec_code}"
        callbacks = self._quote_callbacks.get(key)
        if not callbacks:
            return
        if cb in callbacks:
            callbacks.remove(cb)
        if not callbacks:
            self._qp.unsubscribe_level2_quotes(class_code, sec_code)
            del self._quote_callbacks[key]
            logger.info("Unsubscribed L2 %s", key)

    # ------------------------------------------------------------------
    # Подписки на сделки (trades)
    # ------------------------------------------------------------------
    def subscribe_trades(self, class_code: str, sec_code: str, cb: TradeCallback) -> None:
        key = f"{class_code}.{sec_code}"
        self._trade_callbacks.setdefault(key, []).append(cb)
        if len(self._trade_callbacks[key]) == 1:
            try:
                self._call("subscribe_trades", "SubscribeTrades", "subscribeTrades", class_code=class_code, sec_code=sec_code)
            except Exception as exc:  # pragma: no cover
                logger.warning("subscribe_trades fallback failed: %s", exc)
            logger.info("Subscribed trades %s", key)

    def unsubscribe_trades(self, class_code: str, sec_code: str, cb: TradeCallback) -> None:
        key = f"{class_code}.{sec_code}"
        callbacks = self._trade_callbacks.get(key)
        if not callbacks:
            return
        if cb in callbacks:
            callbacks.remove(cb)
        if not callbacks:
            try:
                self._call("unsubscribe_trades", "UnsubscribeTrades", "unsubscribeTrades", class_code=class_code, sec_code=sec_code)
            except Exception as exc:  # pragma: no cover
                logger.warning("unsubscribe_trades fallback failed: %s", exc)
            del self._trade_callbacks[key]
            logger.info("Unsubscribed trades %s", key)

    # ------------------------------------------------------------------
    # Асинхронный интерфейс (получение очереди событий)
    # ------------------------------------------------------------------

    async def events(self) -> asyncio.Queue:  # noqa: D401
        if self._main_loop is None:
            self._main_loop = asyncio.get_running_loop()
            logger.debug("QuikConnector: main loop registered (%s)", self._main_loop)
        return self._event_queue

    # ------------------------------------------------------------------
    # Торговые операции (вызовы через ThreadPoolExecutor)
    # ------------------------------------------------------------------

    async def _send_transaction(self, tr: dict[str, Any]) -> dict[str, Any]:
        """Универсальный вызов SendTransaction/Send_Transaction c fallback аргументов.

        Проблема: в разных версиях QuikPy доступна либо `send_transaction(self, transaction)`,
        либо `SendTransaction(self, transaction)`, а иногда – свободная функция, которая
        ожидает **именованный** аргумент `transaction`. Этот хелпер пытается вызвать все варианты
        (positional + keyword) до первого успешного ответа.
        """
        loop = asyncio.get_running_loop()

        def _try(func, *f_args, **f_kwargs):  # noqa: ANN001
            try:
                return loop.run_in_executor(None, func, *f_args, **f_kwargs)
            except TypeError:
                return None

        # Перебираем возможные имена метода
        for name in ("send_transaction", "sendTransaction", "SendTransaction"):
            func = getattr(self._qp, name, None)
            if func is None:
                continue
            # 1. Пытаемся передать позиционный аргумент
            fut = _try(func, tr)
            if fut:
                return await fut
            # 2. Пробуем именованный параметр
            fut = _try(func, transaction=tr)
            if fut:
                return await fut

        # Если ни один вариант не подошёл, генерируем исключение
        raise AttributeError("Не найден совместимый метод send_transaction в QuikPy")

    async def place_limit_order(self, tr: dict[str, Any]) -> dict[str, Any]:
        print(f"===> Отправка заявки: {tr}")
        try:
            result = await self._send_transaction(tr)
            print(f"===> Ответ QUIK: {result}")
            logger.info(f"Ответ QUIK на заявку: {result}")
            return result
        except Exception as exc:
            print(f"===> Ошибка при отправке заявки: {exc}")
            logger.exception(f"Ошибка при отправке лимитного ордера: {exc}")
            error_event = {"type": "error", "message": str(exc), "details": {"order": tr}}
            try:
                self._event_queue.put_nowait(error_event)
            except asyncio.QueueFull:
                logger.warning("Event queue full — dropping error event")
            return {"result": -1, "message": str(exc)}

    async def place_market_order(self, tr: dict[str, Any]) -> dict[str, Any]:
        print(f"===> Отправка заявки: {tr}")
        try:
            result = await self._send_transaction(tr)
            return result
        except Exception as exc:
            logger.exception("Ошибка при отправке рыночного ордера: %s", exc)
            error_event = {"type": "error", "message": str(exc), "details": {"order": tr}}
            try:
                self._event_queue.put_nowait(error_event)
            except asyncio.QueueFull:
                logger.warning("Event queue full — dropping error event")
            return {"result": -1, "message": str(exc)}

    async def cancel_order(
        self,
        order_id: str,
        class_code: str,
        sec_code: str,
        trans_id: int | None = None,
    ) -> dict[str, Any]:
        """Отправляет транзакцию отмены заявки (KILL_ORDER)."""
        tr = {
            "ACTION": "KILL_ORDER",
            "CLASSCODE": class_code,
            "SECCODE": sec_code,
            "ORDER_KEY": order_id,
        }
        if trans_id is not None:
            tr["TRANS_ID"] = str(trans_id)
        print(f"===> Отправка заявки: {tr}")
        try:
            result = await self._send_transaction(tr)
            return result
        except Exception as exc:
            logger.exception("Ошибка при отмене ордера: %s", exc)
            error_event = {"type": "error", "message": str(exc), "details": {"order_id": order_id}}
            try:
                self._event_queue.put_nowait(error_event)
            except asyncio.QueueFull:
                logger.warning("Event queue full — dropping error event")
            return {"result": -1, "message": str(exc)}

    async def modify_order(
        self,
        order_id: str,
        class_code: str,
        sec_code: str,
        price: float | int,
        qty: int | None = None,
        operation: str | None = None,
        order_type: str | None = None,
        trans_id: int | None = None,
        account: str | None = None,
        client_code: str | None = None,
    ) -> dict[str, Any]:
        """Отправляет транзакцию изменения параметров заявки (MOVE_ORDERS).

        В QUIK PRICE и QUANTITY должны быть строками. Изменяем только указанные параметры.
        """
        logger.warning("MODIFY_ORDER: Попытка изменить заявку %s в %s.%s, цена: %s -> %s", 
                      order_id, class_code, sec_code, price, qty)
        tr: Dict[str, Any] = {
            "ACTION": "MOVE_ORDERS",
            "CLASSCODE": class_code,
            "SECCODE": sec_code,
            "ORDER_KEY": order_id,
            "PRICE": str(price),
        }
        # OPERATION ('B'/'S') и TYPE ('L'/'M') повышают вероятность приёма брокером
        if operation is not None:
            tr["OPERATION"] = operation
        if order_type is not None:
            tr["TYPE"] = order_type
        if account is not None:
            tr["ACCOUNT"] = account
        if client_code is not None:
            tr["CLIENT_CODE"] = client_code
        if qty is not None:
            tr["QUANTITY"] = str(qty)
        if trans_id is not None:
            tr["TRANS_ID"] = str(trans_id)
        logger.warning("MODIFY_ORDER: Финальная транзакция = %s", tr)
        print(f"===> Отправка заявки: {tr}")
        try:
            result = await self._send_transaction(tr)
            logger.warning("MODIFY_ORDER: Ответ QUIK = %s", result)
            return result
        except Exception as exc:
            logger.exception("Ошибка при изменении ордера: %s", exc)
            error_event = {"type": "error", "message": str(exc), "details": {"order_id": order_id}}
            try:
                self._event_queue.put_nowait(error_event)
            except asyncio.QueueFull:
                logger.warning("Event queue full — dropping error event")
            return {"result": -1, "message": str(exc)}

    # ------------------------------------------------------------------
    # Поток‑эмулятор котировок (офлайн)
    # ------------------------------------------------------------------

    def _quote_listener_loop(self) -> None:
        import random, time

        while not self._stop_quote_thread.is_set():
            for key, callbacks in list(self._quote_callbacks.items()):
                class_code, sec_code = key.split(".")
                quote = {
                    "class_code": class_code,
                    "sec_code": sec_code,
                    "bid": round(random.uniform(100, 110), 2),
                    "ask": round(random.uniform(100, 110), 2),
                    "time": time.time(),
                }
                try:
                    self._event_queue.put_nowait(quote)
                except asyncio.QueueFull:
                    logger.warning("Event queue full — dropping quote")

                for cb in callbacks:
                    try:
                        if asyncio.iscoroutinefunction(cb) and self._main_loop:
                            asyncio.run_coroutine_threadsafe(cb(quote), self._main_loop)
                        else:
                            cb(quote)
                    except Exception as exc:  # pragma: no cover
                        logger.exception("Callback error: %s", exc)
            time.sleep(0.5)

    # ------------------------------------------------------------------
    # Вызов колбэков для trades и orders (шаблон для интеграции)
    # ------------------------------------------------------------------
    def _on_trade(self, event):
        from backend.core.order_manager import OrderManager
        payload = event.get("data", event)
        payload["type"] = "trade"
        payload["cmd"] = event.get("cmd")
        OrderManager._get_instance_for_connector(self).on_trade_event(payload)

    def _on_order(self, event):
        # debug logging removed
        print(f"========== DEBUG OnOrder Event: {event}")
        logger.warning("DEBUG OnOrder Event: %s", event)
        from backend.core.order_manager import OrderManager
        payload = event.get("data", event)
        payload["type"] = "order"
        payload["cmd"] = event.get("cmd")
        OrderManager._get_instance_for_connector(self).on_order_event(payload)

    def _on_trans_reply(self, event):
        # debug logging removed
        from backend.core.order_manager import OrderManager
        payload = event.get("data", event)
        payload["type"] = "trans_reply"
        payload["cmd"] = event.get("cmd")
        OrderManager._get_instance_for_connector(self).on_trans_reply_event(payload)

    # ------------------------------------------------------------------
    # Закрытие соединения
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._stop_quote_thread.set()
        if hasattr(self, "_quote_thread") and self._quote_thread.is_alive():
            self._quote_thread.join(timeout=2)
        # Стандартное закрытие QuikPy
        if hasattr(self._qp, "close_connection_and_thread"):
            self._qp.close_connection_and_thread()
        elif hasattr(self._qp, "CloseConnectionAndThread"):
            self._qp.CloseConnectionAndThread()
        # Monkey-patch: гарантированное завершение CallbackThread
        if hasattr(self._qp, "callback_exit_event"):
            self._qp.callback_exit_event.set()
        if hasattr(self._qp, "callback_thread") and hasattr(self._qp.callback_thread, "is_alive"):
            try:
                if self._qp.callback_thread.is_alive():
                    self._qp.callback_thread.join(timeout=2)
            except Exception:
                pass
        logger.info("QuikConnector closed")
        QuikConnector._instance = None

    # ------------------------------------------------------------------
    # Реализация reconnect: пересоздание соединения и повторная подписка
    # ------------------------------------------------------------------
    def reconnect(self) -> None:
        """
        Пересоздаёт соединение с QuikPy и повторно подписывается на все активные инструменты.
        """
        logger.warning("Выполняется reconnect QuikConnector!")
        self.close()
        # Пересоздаём QuikPy
        self._qp = QuikPy()
        # Повторно подписываемся на все активные инструменты
        for key in self._quote_callbacks:
            class_code, sec_code = key.split(".")
            self._qp.subscribe_level2_quotes(class_code, sec_code)
            logger.info("Reconnect: подписка L2 %s", key)
        for key in self._trade_callbacks:
            class_code, sec_code = key.split(".")
            self._qp.subscribe_trades(class_code, sec_code)
            logger.info("Reconnect: подписка trades %s", key)


# ---------------------------------------------------------------------------
# Демо‑запуск
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    connector = QuikConnector()  # dummy если QuikPy нет

    async def _demo() -> None:
        async def async_cb(q: dict[str, Any]):
            print("async:", q)

        connector.subscribe_quotes("TQBR", "SBER", async_cb)
        queue = await connector.events()
        for _ in range(3):
            evt = await queue.get()
            print("queue:", evt)
        connector.unsubscribe_quotes("TQBR", "SBER", async_cb)
        connector.close()

    # --- Тест новых подписок на trades и orders ---
    async def test_trades_and_orders():
        trade_events = []
        order_events = []

        def trade_cb(event):
            print("trade event:", event)
            trade_events.append(event)

        def order_cb(event):
            print("order event:", event)
            order_events.append(event)

        # Подписка на сделки
        connector.subscribe_trades("TQBR", "SBER", trade_cb)

        # Эмулируем приход событий (в реальном режиме это QuikPy вызывает _on_trade/_on_order)
        connector._on_trade({"price": 123.45, "qty": 10, "side": "buy"})
        connector._on_order({"order_id": 42, "status": "FILLED", "filled": 10})

        await asyncio.sleep(0.2)

        # Проверяем, что события дошли до колбэков
        assert trade_events and trade_events[0]["type"] == "trade"
        assert order_events and order_events[0]["type"] == "order"

        # Отписка
        connector.unsubscribe_trades("TQBR", "SBER", trade_cb)
        print("Trade/order subscription test passed.")

    asyncio.run(test_trades_and_orders())

    sys.exit(0)
