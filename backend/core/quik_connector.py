"""
`core.quik_connector` – тонкая асинхронная обёртка над библиотекой **QuikPy**.

Цель: предоставить единый интерфейс для стратегий и менеджеров, скрывающий
детали работы с API терминала QUIK. Реальная торговля и подписки будут
осуществляться через QuikPy, но чтобы можно было запускать проект без
установленного QUIK, в модуле предусмотрена **заглушка `DummyQuikPy`**.

Основные возможности `QuikConnector`:
* подключение к QuikPy и контроль соединения;
* подписка на поток котировок (best bid/ask) с доставкой через callback;
* выставление лимитных и рыночных ордеров;
* отмена ордеров; (заглушка – лишь логирует вызов)
* единичный (singleton) доступ – стратегий много, соединение одно.

> **Внимание**: QuikPy работает синхронно (блокирующие вызовы через sockets).
> Варианты интеграции:
> 1. Оставить вызовы в потоках `ThreadPoolExecutor` (для не‐блокировки event‐loop).
> 2. Воспользоваться примером MultiScripts из репозитория QuikPy – он тоже
>    запускает отдельные python-скрипты, каждый общается с QUIK.
>
> Для MVP достаточно варианта 1 – каждый запрос к QuikPy исполняем в pool,
> подписки – в отдельном потоке, перекидываем события в asyncio.Queue.
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
    _lock = threading.Lock()  # для потокобезопасного singleton

    # ------------------------ Factory / Singleton --------------------------

    def __new__(cls, *args: Any, **kwargs: Any):  # noqa: D401, ANN401
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, host: str | None = None, port: int = 34130):
        if hasattr(self, "_initialized") and self._initialized:
            return  # уже инициализировано
        self._initialized = True

        self._qp = QuikPy(host=host, port=port)
        self._quote_callbacks: Dict[str, list[QuoteCallback]] = {}

        # Очередь для передачи событий в asyncio‑мир
        self._event_queue: "asyncio.Queue[dict[str, Any]]" = asyncio.Queue()

        # Поток, слушающий костыльно прибывающие данные (эмуляция)
        self._quote_listener_thread = threading.Thread(
            target=self._quote_listener_loop, daemon=True
        )
        self._quote_listener_thread.start()

        logger.info("QuikConnector initialised (host=%s, port=%s)", host, port)

    # ------------------------------------------------------------------
    # Подписки на стакан (Level2). Реальный QUIK вызывает функцию Lua
    # callback OnQuote() – библиотека QuikPy транслирует в python.
    # Здесь мы подписываем callback и дальше кладём событие в очередь.
    # ------------------------------------------------------------------

    def subscribe_quotes(self, class_code: str, sec_code: str, cb: QuoteCallback) -> None:
        key = f"{class_code}.{sec_code}"
        self._quote_callbacks.setdefault(key, []).append(cb)
        # Вызываем системную подписку один раз на key
        if len(self._quote_callbacks[key]) == 1:
            self._qp.Subscribe_Level_II_Quotes(class_code, sec_code)
            logger.info("Subscribed L2 %s", key)

    def unsubscribe_quotes(self, class_code: str, sec_code: str, cb: QuoteCallback) -> None:
        key = f"{class_code}.{sec_code}"
        cbs = self._quote_callbacks.get(key)
        if not cbs:
            return
        cbs.remove(cb)
        if not cbs:
            # Больше нет слушателей – отменяем подписку
            self._qp.Unsubscribe_Level_II_Quotes(class_code, sec_code)
            del self._quote_callbacks[key]
            logger.info("Unsubscribed L2 %s", key)

    # ------------------------------------------------------------------
    # Асинхронные события – стратегии могут `await connector.events()` и
    # получать котировки без блокировки.
    # ------------------------------------------------------------------

    async def events(self) -> asyncio.Queue:  # noqa: D401
        return self._event_queue

    # ------------------------------------------------------------------
    # Торговые операции (упрощённо). Реальный QUIK требует заполнения формы
    # транзакции. Ниже приведены примеры транзакций для лимитного и рыночного
    # ордера. Возвращается ответ QuikPy.
    # ------------------------------------------------------------------

    async def place_limit_order(
        self,
        class_code: str,
        sec_code: str,
        account: str,
        action: str,  # BUY / SELL
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
        # В QUIK рыночный ордер – лимитный с ценой 0 или маркет-кодом «MP»
        tr = {
            "CLASSCODE": class_code,
            "SECCODE": sec_code,
            "ACTION": "NEW_ORDER",
            "ACCOUNT": account,
            "OPERATION": action.upper(),
            "PRICE": 0,  # рыночная
            "QUANTITY": quantity,
        }
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._qp.SendTransaction, tr)

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        tr = {"ACTION": "KILL_ORDER", "ORDER_KEY": order_id}
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._qp.SendTransaction, tr)

    # ------------------------------------------------------------------
    # Внутренний: слушаем поток (эмуляция) и диспатчим слушателям.
    # В реальности QuikPy вызывает callback, здесь – просто демонстрация.
    # ------------------------------------------------------------------

    def _quote_listener_loop(self) -> None:
        """Симуляция поступления котировки каждые 0.5 сек."""
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
                # Кладём событие в очередь asyncio
                try:
                    self._event_queue.put_nowait(quote)
                except asyncio.QueueFull:  # pragma: no cover
                    logger.warning("Event queue full – dropping quote")
                for cb in callbacks:
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            # если callback – coroutine, исполняем его в event‑loop
                            asyncio.run_coroutine_threadsafe(cb(quote), asyncio.get_event_loop())
                        else:
                            cb(quote)
                    except Exception as exc:  # pragma: no cover, pylint: disable=broad-except
                        logger.exception("Callback error: %s", exc)
            time.sleep(0.5)

    # ------------------------------------------------------------------
    # Завершение работы
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._qp.CloseConnectionAndThread()
        logger.info("QuikConnector closed")


# ---------------------------------------------------------------------------
# Демонстрационный запуск
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    q = QuikConnector()

    # Подписываемся и выводим 3 события из очереди
    async def _demo() -> None:
        async def _print_cb(data: dict[str, Any]) -> None:  # noqa: D401
            print("Callback: ", data)

        q.subscribe_quotes("TQBR", "SBER", _print_cb)

        ev_q = await q.events()
        for _ in range(3):
            evt = await ev_q.get()
            print("Async queue: ", evt)

        q.unsubscribe_quotes("TQBR", "SBER", _print_cb)
        q.close()

    asyncio.run(_demo())
    sys.exit(0)
