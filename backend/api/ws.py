"""api.ws – WebSocket endpoints for live updates (spread, position, status).

For the first iteration we broadcast demo data (random) each second.
Later it can be wired to Strategy/Portfolio events.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

try:
    from backend.core.portfolio_manager import PortfolioManager
except ImportError:  # pragma: no cover – fallback for unit tests
    logging.warning("core.portfolio_manager not found – using dummy PortfolioManager")

    class PortfolioManager:  # type: ignore
        async def list_portfolios(self) -> Dict[str, Dict[str, Any]]:  # noqa: D401
            return {}


router = APIRouter(prefix="/ws", tags=["ws"])


def get_pm() -> PortfolioManager:  # noqa: D401
    # импорт здесь, чтобы не тянуть FastAPI Request (router может подключаться в разных местах)
    from fastapi import Request, Depends

    async def _inner(request: Request) -> PortfolioManager:  # type: ignore[return-type]
        pm: PortfolioManager | None = getattr(request.app.state, "portfolio_manager", None)  # type: ignore[attr-defined]
        if pm is None:
            raise RuntimeError("PortfolioManager not initialised in app.state")
        return pm

    return Depends(_inner)  # type: ignore[return-value]


@router.websocket("/strategies/{sid}/metrics")
async def ws_strategy_metrics(websocket: WebSocket, sid: str):
    """Push random metrics for strategy (demo)."""
    await websocket.accept()
    try:
        while True:
            data = {
                "strategy_id": sid,
                "spread_bid": round(random.uniform(-1, 1), 4),
                "spread_ask": round(random.uniform(-1, 1), 4),
                "position_qty": random.randint(-10, 10),
                "pnl": round(random.uniform(-500, 500), 2),
            }
            await websocket.send_json(data)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass 