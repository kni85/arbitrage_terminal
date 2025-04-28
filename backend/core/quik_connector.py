"""
`core.quik_connector` – асинхронная обёртка (singleton) над библиотекой **QuikPy**.

* Подписки на стакан L2, очередь событий для стратегий.
* Методы выставления/отмены заявок (лимит, маркет).
* Работает даже без установленного QUIK – через `DummyQuikPy`.

### Главное изменение

Фикс `RuntimeError: There is no current event loop in thread ...`.
Теперь при первой асинхронной операции (``await connector.events()``)
коннектор запоминает текущий "главный" event‑loop и использует его для
выполнения корутинных callback‑ов из фонового потока приёма котировок.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Попытка импортировать QuikPy. Если не вышло – заглушка.
# ---------------------------------------------------------------------------
try:
    from QuikPy import QuikPy  # type: ignore
except ImportError as exc:  # pragma: no cover – для офлайн разработки

    logger.warning("QuikPy не найден (%s) – используется DummyQuikPy.", exc)

    class QuikPy:  # type: ignore[override]
        """Минимальная заглушка: имитирует методы, выводя лог."""

        def __init__(self, host: str | None = None, port: int = 34130):
            self.host = host or "localhost"
            self.port = port
            logger.info("DummyQuikPy:init host=%s port=%s", self.host, self.port)

        # ---- Подписки ----
        def Subscribe_Level_II_Quotes(self, class_code: str, sec_code: str):  # noqa: N802
            logger.info("DummyQuikPy: Subscribe L2 %s %s", class_code, sec_code)

        def Unsubscribe_Level_II_Quotes(self, class_code: str, sec_code: str):  # noqa: N802
            logger.info("DummyQuikPy: Unsubscribe L2 %s %s", class_code, sec_code)

        # ---- Торговля ----
        def SendTransaction(self, tr: dict[str, Any]):  # noqa: N802
            logger.info("DummyQuikPy: SendTransaction %s", tr)
            return {"result": 0, "message": "stub"}

        # ---- Закрытие ----
        def CloseConnectionAndThread(self):  # noqa: N802
            logger.info("DummyQuikPy: Close connection")


# ---------------------------------------------------------------------------
# Типы коллбеков
# ---------------------------------------------------------------------------

QuoteCallback = Callable[[dict[str, Any]], None]


# ---------------------------------------------------------------------------
# Singleton‑класс QuikConnector
# ---------------------------------------------------------------------------

class QuikConnector:
    """Singleton для доступа к QuikPy в асинхронном коде."""

    _instance: Optional["QuikConnector"] = None
    _lock = threading.Lock()

    # ------------------------ Factory / Singleton --------------------------

    def __new__(cls, *args: Any, **kwargs: Any):  # noqa: D401, ANN401
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------
    # Инициализация
    # ------------------------------------------------------------------

    def __init__(self, host: str | None = None, port: int = 34130):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        # QuikPy подключение (или Dummy)
        self._qp = QuikPy(host=host, port=port)

        # Коллбеки, подписанные на инструмент: key -> list(callback)
        self._quote_callbacks: Dict[str, list[QuoteCallback]] = {}

        # Очередь событий котировок -> asyncio‑мир
        self._event_queue: "asyncio.Queue[dict[str, Any]]" = asyncio.Queue(maxsize=1000)

        # Ссылка на "главный" event‑loop (присвоим при первом `await events()`)
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

        # Фоновый поток, имитирующий приём котировок (или слушающий QuikPy)
        self._quote_listener_thread = threading.Thread(
            target=self._quote_listener_loop, name="QP‑quotes", daemon=True
        )
        self._quote_listener_thread.start()

        logger.info("QuikConnector initialised (host=%s, port=%s)", host, port)

    # ------------------------------------------------------------------
    # Подписки на стакан L2
    # ------------------------------------------------------------------

    def subscribe_quotes(self, class_code: str, sec_code: str, cb: QuoteCallback) -> None:
        key = f"{class_code}.{sec_code}"
        self._quote_callbacks.setdefault(key, []).append(cb)
        if len(self._quote_callbacks[key]) == 1:
            self._qp.Subscribe_Level_II_Quotes(class_code, sec_code)
            logger.info("Subscribed L2 %s", key)

    def unsubscribe_quotes(self, class_code: str, sec_code: str, cb: QuoteCallback) -> None:
        key = f"{class_code}.{sec_code}"
        cbs = self._quote_callbacks.get(key)
        if not cbs:
            return
        if cb in cbs:
            cbs.remove(cb)
        if not cbs:
            self._qp.Unsubscribe_Level_II_Quotes(class_code, sec_code)
            del self._quote_callbacks[key]
            logger.info("Unsubscribed L2 %s", key)

    # ------------------------------------------------------------------
    # Асинхронный интерфейс для получения потока событий
    # ------------------------------------------------------------------

    async def events(self) -> asyncio.Queue:  # noqa: D401
        """Возвращает очередь событий котировок.

        При первом вызове запоминаем текущий event‑loop как "главный", чтобы
        из фонового потока публиковать coroutine‑callback-и без ошибки.
        """
        if self._main_loop is None:
            self._main_loop = asyncio.get_running_loop()
            logger.debug("QuikConnector: registered main event loop %s", self._main_loop)
        return self._event_queue

    # ------------------------------------------------------------------
    # Торговые операции (упрощённые)
    # ------------------------------------------------------------------

    async def place_limit_order(
        self,
        class_code: str,
        sec_code: str,
        account: str,
        action: str,
        price: float,
        quantity: int,
    ) -> dict[str, Any]:
        tr = {
            "CLASSCODE": class_code,
            "SECCODE": sec_code,
            "ACTION": "NEW_ORDER",
            "ACCOUNT": account,
            "OPERATION": action.upper(),
            "PRICE": price,
            "QUANTITY": quantity,
        }
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._qp.SendTransaction, tr)

    async def place_market_order(
        self,
        class_code: str,
        sec_code: str,
        account: str,
        action: str,
        quantity: int,
    ) -> dict[str, Any]:
        tr = {
            "CLASSCODE": class_code,
            "SECCODE": sec_code,
            "ACTION": "NEW_ORDER",
            "ACCOUNT": account,
            "OPERATION": action.upper(),
            "PRICE": 0,
            "QUANTITY": quantity,
        }
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._qp.SendTransaction, tr)

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        tr = {"ACTION": "KILL_ORDER", "ORDER_KEY": order_id}
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._qp.SendTransaction, tr)

    # ------------------------------------------------------------------
    # Внутренний поток: слушает QuikPy / эмулирует и диспатчит события
    # ------------------------------------------------------------------

    def _quote_listener_loop(self) -> None:
        import random
        import time

        while True:
            for key, callbacks in list(self._quote_callbacks.items()):
                class_code, sec_code = key.split(".")
                quote = {
                    "class_code": class_code,
                    "sec_code": sec_code,
                    "bid": round(random.uniform(100, 110), 2),
                    "ask": round(random.uniform(100, 110), 2),
                    "time": time.time(),
                }
                # Ставим в очередь (если не переполнена)
                try:
                    self._event_queue.put_nowait(quote)
                except asyncio.QueueFull:
                    logger.warning("Event queue full – dropping quote")

                # Рассылаем в callbacks
                for cb in callbacks:
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            if self._main_loop is None:
                                logger.debug("Coroutine callback %s пропущен – loop неизвестен", cb)
                                continue
                            asyncio.run_coroutine_threadsafe(cb(quote), self._main_loop)
                        else:
                            cb(quote)
                    except Exception as exc:  # pragma: no cover
                        logger.exception("Callback error: %s", exc)
            time.sleep(0.5)

    # ------------------------------------------------------------------
    # Завершение
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._qp.CloseConnectionAndThread()
        logger.info("QuikConnector closed")


# ---------------------------------------------------------------------------
# Демонстрация
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    connector = QuikConnector()

    async def _demo() -> None:
        async def async_cb(q: dict[str, Any]) -> None:  # noqa: D401
            print("async CB:", q)

        def sync_cb(q: dict[str, Any]) -> None:  # noqa: D401
            print("sync CB:", q)

        connector.subscribe_quotes("TQBR", "SBER", async_cb)
        connector.subscribe_quotes("TQBR", "SBER", sync_cb)

        evq = await connector.events()
        # Выводим 3 события из очереди
        for _ in range(3):
            evt = await evq.get()
            print("queue EVT:", evt)

        connector.unsubscribe_quotes("TQBR", "SBER", async_cb)
        connector.unsubscribe_quotes("TQBR", "SBER", sync_cb)
        connector.close()

    asyncio.run(_demo())
    sys.exit(0)
