"""
`api.server` – определяет REST‑эндпоинты FastAPI для управления портфелями.

Поддерживаемые маршруты:

* **GET  /api/portfolios**                – список всех портфелей.
* **POST /api/portfolios**                – создать и запустить новый портфель.
* **GET  /api/portfolios/{pid}**          – подробная информация о портфеле.
* **POST /api/portfolios/{pid}/stop**     – остановить и удалить портфель.

Все операции опираются на экземпляр `PortfolioManager`, который хранится в
`app.state.portfolio_manager` (см. `backend.main`).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Попытка импортировать настоящие классы. Если их нет – заглушки для тестов.
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


# ---------------------------------------------------------------------------
# Pydantic‑модели
# ---------------------------------------------------------------------------

class PortfolioConfig(BaseModel):
    """Входная конфигурация портфеля (произвольная структура)."""

    name: str = Field(..., description="Произвольное имя портфеля")

    class Config:
        extra = "allow"  # разрешаем произвольные поля (legs, ratios, levels и т.д.)


class PortfolioCreateResponse(BaseModel):
    pid: str = Field(..., description="Идентификатор созданного портфеля")


class PortfolioSummary(BaseModel):
    running: bool
    config: Dict[str, Any]


# ---------------------------------------------------------------------------
# Зависимость для получения PortfolioManager из объекта приложения
# ---------------------------------------------------------------------------

def get_pm(request: Request) -> PortfolioManager:  # noqa: D401
    manager: Optional[PortfolioManager] = getattr(request.app.state, "portfolio_manager", None)  # type: ignore[attr-defined]
    if manager is None:
        raise HTTPException(status_code=500, detail="PortfolioManager не инициализирован")
    return manager


# ---------------------------------------------------------------------------
# APIRouter – регистрируется в приложении в backend.main
# ---------------------------------------------------------------------------

api_router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@api_router.get("/", response_model=Dict[str, PortfolioSummary])
async def list_portfolios(manager: PortfolioManager = Depends(get_pm)) -> Any:  # noqa: D401
    """Список всех портфелей и их краткое состояние."""
    return await manager.list_portfolios()


@api_router.post("/", response_model=PortfolioCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    config: PortfolioConfig,
    manager: PortfolioManager = Depends(get_pm),
) -> Any:  # noqa: D401
    """Создать и запустить портфель. Возвращает его идентификатор."""
    pid = await manager.add_portfolio(config.dict())
    return PortfolioCreateResponse(pid=pid)


@api_router.get("/{pid}", response_model=PortfolioSummary)
async def get_portfolio(
    pid: str,
    manager: PortfolioManager = Depends(get_pm),
) -> Any:  # noqa: D401
    """Получить подробную информацию о портфеле."""
    summary = await manager.list_portfolios()
    if pid not in summary:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    return summary[pid]


@api_router.post("/{pid}/stop", status_code=status.HTTP_204_NO_CONTENT)
async def stop_portfolio(
    pid: str,
    manager: PortfolioManager = Depends(get_pm),
) -> None:  # noqa: D401
    """Остановить и удалить портфель."""
    await manager.stop_portfolio(pid)


# ---------------------------------------------------------------------------
# Тестирование модуля локально – создаём мини‑приложение и запускаем Uvicorn
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """Запускает небольшой FastAPI‑сервер только с единственным роутером.

    Можно протестировать:

    ```bash
    curl -X POST http://127.0.0.1:8001/portfolios -H "Content-Type: application/json" \
         -d '{"name": "Test", "legs": 2}'
    ```
    """

    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = FastAPI(title="API test")
    pm = PortfolioManager()
    app.state.portfolio_manager = pm  # type: ignore[attr-defined]
    app.include_router(api_router, prefix="/")

    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
