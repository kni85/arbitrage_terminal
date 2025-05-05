"""
`api.server` – REST‑эндпоинты FastAPI для управления портфелями.

Поддерживаемые маршруты:

* **GET  /api/portfolios**                – список всех портфелей.
* **POST /api/portfolios**                – создать и запустить портфель.
* **GET  /api/portfolios/{pid}**          – подробная информация.
* **POST /api/portfolios/{pid}/stop**     – остановить и удалить портфель
  (ответ 204 No Content).
* **PUT  /api/portfolios/{pid}**           – обновить параметры портфеля и перезапустить стратегию

Экземпляр `PortfolioManager` хранится в `app.state.portfolio_manager` и
передаётся через зависимость `get_pm()`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, List

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    status,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field
import random
import asyncio

# ---------------------------------------------------------------------------
# Попытка импортировать настоящий PortfolioManager. Если нет – заглушка.
# ---------------------------------------------------------------------------
try:
    from core.portfolio_manager import PortfolioManager
except ImportError as exc:  # pragma: no cover – до появления real модуля
    logging.warning("core.portfolio_manager не найден (%s) – используется заглушка.", exc)

    class PortfolioManager:  # type: ignore
        async def list_portfolios(self) -> Dict[str, Dict[str, Any]]:
            return {}

        async def add_portfolio(self, config: Dict[str, Any]) -> str:  # noqa: D401
            return "dummy-id"

        async def stop_portfolio(self, pid: str) -> None:  # noqa: D401
            pass

        async def update_portfolio(self, pid: str, config: Dict[str, Any]) -> None:  # noqa: D401
            pass

# ---------------------------------------------------------------------------
# Pydantic‑модели входа/выхода
# ---------------------------------------------------------------------------

class PortfolioConfig(BaseModel):
    """Конфигурация портфеля (минимум name, legs, type)."""
    name: str = Field(..., description="Имя портфеля в интерфейсе")
    type: str = Field(..., description="Тип стратегии (pair, triangular и др.)")
    leg1: Dict[str, Any] = Field(..., description="Первая нога")
    leg2: Dict[str, Any] = Field(..., description="Вторая нога")
    entry_levels: Optional[List[float]] = Field(None, description="Уровни входа")
    exit_level: Optional[float] = Field(None, description="Уровень выхода")
    poll_interval: Optional[float] = Field(None, description="Интервал опроса")
    mode: Optional[str] = Field(None, description="Режим работы (shooter, market_maker)")

    class Config:
        extra = "allow"  # разрешаем любые доп. поля: legs, ratios, ...


class PortfolioCreateResponse(BaseModel):
    """Ответ при создании портфеля."""

    pid: str = Field(..., description="Идентификатор портфеля")


class PortfolioSummary(BaseModel):
    """Сводка по портфелю в списке."""

    running: bool
    config: Dict[str, Any]


# ---------------------------------------------------------------------------
# Зависимость – достаём менеджер из state приложения
# ---------------------------------------------------------------------------

def get_pm(request: Request) -> PortfolioManager:  # noqa: D401
    manager: Optional[PortfolioManager] = getattr(request.app.state, "portfolio_manager", None)  # type: ignore[attr-defined]
    if manager is None:
        raise HTTPException(status_code=500, detail="PortfolioManager не инициализирован")
    return manager


# ---------------------------------------------------------------------------
# Основной роутер
# ---------------------------------------------------------------------------

api_router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@api_router.get("/", response_model=Dict[str, PortfolioSummary])
async def list_portfolios(manager: PortfolioManager = Depends(get_pm)) -> Any:  # noqa: D401
    """Список портфелей."""
    return await manager.list_portfolios()


@api_router.post("/", response_model=PortfolioCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    config: PortfolioConfig,
    manager: PortfolioManager = Depends(get_pm),
) -> Any:  # noqa: D401
    """Создать и запустить новый портфель."""
    pid = await manager.add_portfolio(config.dict())
    return PortfolioCreateResponse(pid=pid)


@api_router.get("/{pid}", response_model=PortfolioSummary)
async def get_portfolio(
    pid: str,
    manager: PortfolioManager = Depends(get_pm),
) -> Any:  # noqa: D401
    """Детали конкретного портфеля."""
    summary = await manager.list_portfolios()
    if pid not in summary:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    return summary[pid]


@api_router.post(
    "/{pid}/stop",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def stop_portfolio(
    pid: str,
    manager: PortfolioManager = Depends(get_pm),
) -> Response:  # noqa: D401
    """Остановить и удалить портфель. Ответ 204 без тела."""
    await manager.stop_portfolio(pid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@api_router.put("/{pid}", status_code=status.HTTP_200_OK)
async def update_portfolio(
    pid: str,
    config: PortfolioConfig,
    manager: PortfolioManager = Depends(get_pm),
) -> Any:
    """
    Обновить параметры портфеля и перезапустить стратегию.
    """
    summary = await manager.list_portfolios()
    if pid not in summary:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    try:
        await manager.update_portfolio(pid, config.dict())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Ошибка обновления портфеля: {exc}")
    return {"status": "updated"}


@api_router.get("/{pid}/spread")
async def get_portfolio_spread(pid: str, manager: PortfolioManager = Depends(get_pm)) -> Any:
    """
    Получить текущий spread (или spread_bid/ask) для стратегии (эмуляция).
    В реальной реализации — брать из DataRecorder или самой стратегии.
    """
    summary = await manager.list_portfolios()
    if pid not in summary:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    # Эмулируем spread
    spread_bid = round(random.uniform(-2, 2), 4)
    spread_ask = round(random.uniform(-2, 2), 4)
    return {"spread_bid": spread_bid, "spread_ask": spread_ask}


# --- WebSocket endpoint для push-обновлений spread ---
@api_router.websocket("/ws/portfolios/{pid}/spread")
async def ws_portfolio_spread(websocket: WebSocket, pid: str, manager: PortfolioManager = Depends(get_pm)):
    await websocket.accept()
    try:
        while True:
            # Эмулируем spread
            spread_bid = round(random.uniform(-2, 2), 4)
            spread_ask = round(random.uniform(-2, 2), 4)
            await websocket.send_json({"spread_bid": spread_bid, "spread_ask": spread_ask})
            await asyncio.sleep(1.0)  # обновление раз в секунду
    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# Локальный тест: `python api/server.py`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = FastAPI(title="API test")
    pm = PortfolioManager()
    app.state.portfolio_manager = pm  # type: ignore[attr-defined]
    app.include_router(api_router)  # без лишнего префикса

    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
