"""Unified FastAPI application – new entrypoint for Arbitrage Terminal.

Run with:
    uvicorn backend.api.main:app --reload
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import container
from backend.api.routes import router as root_router
from backend.api.ws import router as ws_router
# CRUD routers
from backend.api.routes_accounts import router as accounts_router
from db.database import ensure_tables_exist

logger = logging.getLogger(__name__)

app = FastAPI(title="Arbitrage Terminal")
app.container = container  # type: ignore[attr-defined]

# serve static assets for GUI
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Wire DI to API modules (after import to avoid circular issues)
from backend.api import routes as _routes_module, ws as _ws_module  # noqa: E402
container.wire(modules=[_routes_module, _ws_module])

# Подключаем HTTP и WebSocket маршруты
app.include_router(root_router)
app.include_router(ws_router)
# Регистрация CRUD маршрутов
app.include_router(accounts_router)


# --- events ---------------------------------------------------------------

@app.on_event("startup")
async def _on_startup() -> None:  # noqa: D401
    await ensure_tables_exist()
    logger.info("[startup] DB tables ensured. App ready.")


@app.on_event("shutdown")
async def _on_shutdown() -> None:  # noqa: D401
    try:
        broker = container.broker()
        if broker is not None:
            broker.close()
    except Exception as exc:  # pragma: no cover
        logger.error("Error while shutdown: %s", exc)
