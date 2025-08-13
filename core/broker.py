"""Broker interface definition for trading operations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable, Callable, Any

QuoteCb = Callable[[dict[str, Any]], None]


@runtime_checkable
class Broker(Protocol):
    """Minimal broker interface used by strategies / services."""

    # --- market data
    def subscribe_quotes(self, class_code: str, sec_code: str, cb: QuoteCb) -> None: ...

    def unsubscribe_quotes(self, class_code: str, sec_code: str, cb: QuoteCb) -> None: ...

    # --- trading
    async def place_market_order(self, tr: dict[str, Any]) -> dict[str, Any]: ...

    async def place_limit_order(self, tr: dict[str, Any]) -> dict[str, Any]: ...

    async def cancel_order(self, order_id: str, class_code: str | None = None, sec_code: str | None = None, *, trans_id: int | None = None) -> dict[str, Any]: ...

    # --- maintenance
    def close(self) -> None: ...
