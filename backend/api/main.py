"""Unified FastAPI application – new entrypoint for Arbitrage Terminal.

Run with:
    uvicorn backend.api.main:app --reload
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from config import container
from backend.api.routes import router as root_router
from backend.api.ws import router as ws_router
from db.database import ensure_tables_exist
from backend.quik_connector.core.quik_connector import QuikConnector  # type: ignore

logger = logging.getLogger(__name__)

app = FastAPI(title="Arbitrage Terminal")
app.container = container  # type: ignore[attr-defined]

# Подключаем HTTP и WebSocket маршруты
app.include_router(root_router)
app.include_router(ws_router)


# --- events ---------------------------------------------------------------

@app.on_event("startup")
async def _on_startup() -> None:  # noqa: D401
    await ensure_tables_exist()
    logger.info("[startup] DB tables ensured. App ready.")


@app.on_event("shutdown")
async def _on_shutdown() -> None:  # noqa: D401
    try:
        qc = QuikConnector._instance  # type: ignore[attr-defined]
        if qc is not None:
            qc.close()
    except Exception as exc:  # pragma: no cover
        logger.error("Error while shutdown: %s", exc)
