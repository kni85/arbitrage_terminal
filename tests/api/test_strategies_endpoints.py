import uuid
import pytest
from typing import Dict, Any

# гарантируем наличие httpx для TestClient; если нет – пропускаем весь файл
pytest.importorskip("httpx")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import server as api_server


class FakePortfolioManager:
    """Простейший ин-мемори менеджер портфелей для тестов."""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}

    # --- public API, имитирующий core.portfolio_manager.PortfolioManager ---

    async def list_portfolios(self) -> Dict[str, Dict[str, Any]]:  # noqa: D401
        return self._store

    async def add_portfolio(self, cfg: Dict[str, Any]) -> str:  # noqa: D401
        pid = str(uuid.uuid4())
        self._store[pid] = {"running": True, "config": cfg}
        return pid

    async def stop_portfolio(self, pid: str) -> None:  # noqa: D401
        if pid in self._store:
            self._store[pid]["running"] = False

    async def update_portfolio(self, pid: str, cfg: Dict[str, Any]) -> None:  # noqa: D401
        if pid in self._store:
            self._store[pid]["config"].update(cfg)
            self._store[pid]["running"] = True


# ----------------------------------------------------------------------------
# Test fixtures
# ----------------------------------------------------------------------------

@pytest.fixture()
def client() -> TestClient:
    app = FastAPI(title="test-app")
    # attach fake PM
    app.state.portfolio_manager = FakePortfolioManager()  # type: ignore[attr-defined]
    # include routers from real server module
    app.include_router(api_server.strategies_router)
    # no need for /portfolios router here
    return TestClient(app)


# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------

def test_strategies_crud_flow(client: TestClient):
    # 1. список пуст
    resp = client.get("/strategies")
    assert resp.status_code == 200
    assert resp.json() == {}

    # 2. создаём стратегию
    payload = {
        "name": "Pair SBER-GAZP",
        "instrument_leg1": "TQBR.SBER",
        "instrument_leg2": "TQBR.GAZP",
        "price_ratio1": 1,
        "price_ratio2": 1,
        "qty_ratio": 1,
        "threshold_long": -0.5,
        "threshold_short": 0.6,
        "mode": "shooter",
        "active": True,
    }
    resp = client.post("/strategies", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    sid = body["strategy_id"]
    assert body["running"] is True

    # 3. список содержит созданную стратегию
    resp = client.get("/strategies")
    assert resp.status_code == 200
    data = resp.json()
    assert sid in data

    # 4. get конкретной стратегии
    resp = client.get(f"/strategies/{sid}")
    assert resp.status_code == 200
    assert resp.json()["strategy_id"] == sid

    # 5. частичное обновление (PATCH)
    patch_data = {"threshold_long": -0.3}
    resp = client.patch(f"/strategies/{sid}", json=patch_data)
    assert resp.status_code == 200

    # 6. stop стратегия
    resp = client.post(f"/strategies/{sid}/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"

    # 7. start снова
    resp = client.post(f"/strategies/{sid}/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "started" 