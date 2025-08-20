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
from typing import Any, Callable, Dict, Optional

from infra.quik.vendor.QuikPy import QuikPy  # type: ignore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
QuoteCallback = Callable[[dict[str, Any]], None]
TradeCallback = Callable[[dict[str, Any]], None]
OrderCallback = Callable[[dict[str, Any]], None]

class QuikConnector:
    """Асинхронная обёртка над QuikPy (singleton)."""

    _instance: Optional["QuikConnector"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        host: str = "localhost",
        requests_port: int = 34130,
        callbacks_port: int = 34131,
    ):
        # Защита от повторной инициализации singleton
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self._host = host
        self._requests_port = requests_port
        self._callbacks_port = callbacks_port

        # Асинхронная очередь событий для стратегий
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)

        # Подключение к QuikPy
        logger.info(
            "Connecting to QuikPy: host=%s, req_port=%s, cb_port=%s",
            self._host,
            self._requests_port,
            self._callbacks_port,
        )
        
        self._qp = QuikPy(
            host=self._host,
            requests_port=self._requests_port,
            callbacks_port=self._callbacks_port,
        )

        # --- Привязываем callback-методы QuikPy к локальным обработчикам ---
        # Это позволяет OrderManager получать события OnOrder / OnTrade / OnTransReply
        # сразу после их прихода из QUIK.
        self._qp.on_trade = self._on_trade  # type: ignore[attr-defined]
        self._qp.on_trans_reply = self._on_trans_reply  # type: ignore[attr-defined]

        # Подписки на инструменты
        self._subscribed_quotes: set[tuple[str, str]] = set()
        self._subscribed_trades: set[tuple[str, str]] = set()

        logger.info("QuikConnector initialized successfully")

    # -----------------------------------------------------------------------
    # Callback-методы для QuikPy
    # -----------------------------------------------------------------------
    def _on_trade(self, trade_data: dict[str, Any]) -> None:
        """Callback для событий сделок от QuikPy."""
        try:
            # Нормализуем событие и отправляем в очередь
            event = {"type": "trade", **trade_data}
            self._event_queue.put_nowait(event)
            logger.debug("Trade event queued: %s", event)
        except asyncio.QueueFull:
            logger.warning("Event queue full — dropping trade event")
        except Exception as exc:
            logger.exception("Error in _on_trade: %s", exc)

    def _on_trans_reply(self, trans_reply: dict[str, Any]) -> None:
        """Callback для ответов на транзакции от QuikPy."""
        try:
            # Нормализуем событие и отправляем в очередь
            event = {"type": "trans_reply", **trans_reply}
            self._event_queue.put_nowait(event)
            logger.debug("Trans reply event queued: %s", event)
        except asyncio.QueueFull:
            logger.warning("Event queue full — dropping trans reply event")
        except Exception as exc:
            logger.exception("Error in _on_trans_reply: %s", exc)

    def _on_quote(self, quote_data: dict[str, Any]) -> None:
        """Callback для котировок от QuikPy."""
        try:
            # Нормализуем событие и отправляем в очередь
            event = {"type": "quote", **quote_data}
            self._event_queue.put_nowait(event)
            logger.debug("Quote event queued: %s", event)
        except asyncio.QueueFull:
            logger.warning("Event queue full — dropping quote event")
        except Exception as exc:
            logger.exception("Error in _on_quote: %s", exc)

    # -----------------------------------------------------------------------
    # Публичные методы для подписок
    # -----------------------------------------------------------------------
    def subscribe_quotes(self, class_code: str, sec_code: str, callback: QuoteCallback = None) -> None:
        """Подписка на котировки L2."""
        key = (class_code, sec_code)
        if key in self._subscribed_quotes:
            logger.debug("Already subscribed to quotes: %s %s", class_code, sec_code)
            return

        try:
            # Устанавливаем callback если передан
            if callback:
                self._qp.on_quote = callback
            
            self._qp.subscribe_level2_quotes(class_code, sec_code)
            self._subscribed_quotes.add(key)
            logger.info("Subscribed to quotes: %s %s", class_code, sec_code)
        except Exception as exc:
            logger.exception("Failed to subscribe to quotes %s %s: %s", class_code, sec_code, exc)

    def unsubscribe_quotes(self, class_code: str, sec_code: str, callback: QuoteCallback = None) -> None:
        """Отписка от котировок L2."""
        key = (class_code, sec_code)
        if key not in self._subscribed_quotes:
            logger.debug("Not subscribed to quotes: %s %s", class_code, sec_code)
            return

        try:
            self._qp.unsubscribe_level2_quotes(class_code, sec_code)
            self._subscribed_quotes.discard(key)
            logger.info("Unsubscribed from quotes: %s %s", class_code, sec_code)
        except Exception as exc:
            logger.exception("Failed to unsubscribe from quotes %s %s: %s", class_code, sec_code, exc)

    def subscribe_trades(self, class_code: str, sec_code: str) -> None:
        """Подписка на сделки."""
        key = (class_code, sec_code)
        if key in self._subscribed_trades:
            logger.debug("Already subscribed to trades: %s %s", class_code, sec_code)
            return

        try:
            self._qp.subscribe_trades(class_code, sec_code)
            self._subscribed_trades.add(key)
            logger.info("Subscribed to trades: %s %s", class_code, sec_code)
        except Exception as exc:
            logger.exception("Failed to subscribe to trades %s %s: %s", class_code, sec_code, exc)

    def unsubscribe_trades(self, class_code: str, sec_code: str) -> None:
        """Отписка от сделок."""
        key = (class_code, sec_code)
        if key not in self._subscribed_trades:
            logger.debug("Not subscribed to trades: %s %s", class_code, sec_code)
            return

        try:
            self._qp.unsubscribe_trades(class_code, sec_code)
            self._subscribed_trades.discard(key)
            logger.info("Unsubscribed from trades: %s %s", class_code, sec_code)
        except Exception as exc:
            logger.exception("Failed to unsubscribe from trades %s %s: %s", class_code, sec_code, exc)

    # -----------------------------------------------------------------------
    # Торговые операции
    # -----------------------------------------------------------------------
    async def _send_transaction(self, tr: dict[str, Any]) -> dict[str, Any]:
        """Отправка транзакции в QUIK."""
        try:
            # QuikPy.send_transaction может быть синхронным, вызываем в executor
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._qp.send_transaction, tr)
            return result
        except Exception as exc:
            logger.exception("Error sending transaction: %s", exc)
            return {"result": -1, "message": str(exc)}

    async def place_limit_order(
        self,
        class_code: str,
        sec_code: str,
        account: str,
        client_code: str,
        operation: str,  # "B" или "S"
        quantity: int,
        price: float,
        trans_id: int,
    ) -> dict[str, Any]:
        """Выставление лимитной заявки."""
        tr = {
            "ACTION": "NEW_ORDER",
            "CLASSCODE": class_code,
            "SECCODE": sec_code,
            "ACCOUNT": account,
            "CLIENT_CODE": client_code,
            "OPERATION": operation,
            "QUANTITY": str(quantity),
            "PRICE": str(price),
            "TYPE": "L",  # Лимитная заявка
            "TRANS_ID": str(trans_id),
        }
        logger.info("Placing limit order: %s", tr)
        return await self._send_transaction(tr)

    async def place_market_order(self, tr: dict[str, Any]) -> dict[str, Any]:
        """Отправка рыночного ордера."""
        print(f"===> Отправка заявки: {tr}")
        try:
            result = await self._send_transaction(tr)
            # Логируем ответ так же, как в place_limit_order – это полезно для отладки
            print(f"===> Ответ QUIK: {result}")
            logger.info(f"Ответ QUIK на маркет-ордер: {result}")
            return result
        except Exception as exc:
            logger.exception("Ошибка при отправке рыночного ордера: %s", exc)
            error_event = {"type": "error", "message": str(exc), "details": {"order": tr}}
            try:
                self._event_queue.put_nowait(error_event)
            except asyncio.QueueFull:
                logger.debug("Event queue full — dropping error event")
            return {"result": -1, "message": str(exc)}

    async def cancel_order(self, class_code: str, sec_code: str, order_key: str) -> dict[str, Any]:
        """Отмена заявки."""
        tr = {
            "ACTION": "KILL_ORDER",
            "CLASSCODE": class_code,
            "SECCODE": sec_code,
            "ORDER_KEY": order_key,
        }
        logger.info("Cancelling order: %s", tr)
        return await self._send_transaction(tr)

    # -----------------------------------------------------------------------
    # Асинхронная очередь событий
    # -----------------------------------------------------------------------
    async def events(self) -> dict[str, Any]:
        """Получение событий из очереди (для стратегий)."""
        return await self._event_queue.get()

    def events_nowait(self) -> dict[str, Any] | None:
        """Получение событий без ожидания (может вернуть None)."""
        try:
            return self._event_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    # -----------------------------------------------------------------------
    # Информационные методы
    # -----------------------------------------------------------------------
    def get_security_info(self, class_code: str, sec_code: str) -> dict[str, Any]:
        """Получение информации по инструменту."""
        try:
            return self._qp.get_security_info(class_code, sec_code)
        except Exception as exc:
            logger.exception("Failed to get security info %s %s: %s", class_code, sec_code, exc)
            return {}

    def get_money(self, client_code: str, firm_id: str, limit_kind: int = 0) -> dict[str, Any]:
        """Получение информации о денежных средствах."""
        try:
            return self._qp.get_money(client_code, firm_id, limit_kind)
        except Exception as exc:
            logger.exception("Failed to get money info: %s", exc)
            return {}

    # -----------------------------------------------------------------------
    # Управление жизненным циклом
    # -----------------------------------------------------------------------
    def close(self) -> None:
        """Закрытие соединения и очистка ресурсов."""
        logger.info("Closing QuikConnector...")

        # Отписываемся от всех подписок
        for class_code, sec_code in list(self._subscribed_quotes):
            self.unsubscribe_quotes(class_code, sec_code)

        for class_code, sec_code in list(self._subscribed_trades):
            self.unsubscribe_trades(class_code, sec_code)

        # Закрываем QuikPy соединение
        try:
            self._qp.close_connection_and_thread()
            logger.info("QuikPy connection closed")
        except Exception as exc:
            logger.exception("Error closing QuikPy connection: %s", exc)

        logger.info("QuikConnector closed")

    def __del__(self):
        """Деструктор для автоматической очистки ресурсов."""
        try:
            self.close()
        except Exception:
            pass  # Игнорируем ошибки в деструкторе


# ---------------------------------------------------------------------------
# Singleton instance getter
# ---------------------------------------------------------------------------
def get_quik_connector(
    host: str = "localhost",
    requests_port: int = 34130,
    callbacks_port: int = 34131,
) -> QuikConnector:
    """Получение singleton экземпляра QuikConnector."""
    return QuikConnector(host=host, requests_port=requests_port, callbacks_port=callbacks_port)