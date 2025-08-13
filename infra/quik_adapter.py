from __future__ import annotations

from typing import Any, Dict

from core.broker import Broker, QuoteCallback
from backend.quik_connector.core.quik_connector import QuikConnector

__all__ = ["QuikBrokerAdapter"]


class QuikBrokerAdapter(Broker):
    """Адаптер, реализующий интерфейс Broker поверх QuikConnector.

    Позволяет слою *core* работать исключительно с абстракцией ``Broker``.
    Все вызовы делегируются низкоуровневому :class:`QuikConnector`.
    """

    def __init__(self, connector: QuikConnector | None = None) -> None:  # noqa: D401
        # Используем уже инициализированный singleton, если передали.
        self._connector = connector or QuikConnector()

    # ------------------------------------------------------------------
    # Market-data (quotes)
    # ------------------------------------------------------------------
    def subscribe_quotes(self, class_code: str, sec_code: str, cb: QuoteCallback) -> None:  # noqa: D401
        self._connector.subscribe_quotes(class_code, sec_code, cb)

    def unsubscribe_quotes(self, class_code: str, sec_code: str, cb: QuoteCallback) -> None:  # noqa: D401
        self._connector.unsubscribe_quotes(class_code, sec_code, cb)

    # ------------------------------------------------------------------
    # Trading
    # ------------------------------------------------------------------
    async def place_market_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:  # noqa: D401
        return await self._connector.place_market_order(order_data)

    async def place_limit_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:  # noqa: D401
        return await self._connector.place_limit_order(order_data)

    async def cancel_order(self, orm_order_id: int) -> None:  # noqa: D401
        """Отмена заявки по внутреннему id.

        Пока эта операция осуществляется напрямую через :class:`OrderManager`.
        Здесь оставлена заглушка; будет реализована после перехода core на
        полноценное использование интерфейса *Broker* (S5-4).
        """
        raise NotImplementedError("cancel_order via BrokerAdapter ещё не реализован")

    # ------------------------------------------------------------------
    # House-keeping
    # ------------------------------------------------------------------
    def close(self) -> None:  # noqa: D401
        self._connector.close()
