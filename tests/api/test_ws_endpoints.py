import pytest
import asyncio

pytest.importorskip("httpx")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.ws import router as ws_router


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(ws_router)
    return TestClient(app)


def test_ws_metrics_stream(client: TestClient):
    """Должны приходить несколько сообщений с нужными полями и типами."""
    with client.websocket_connect("/ws/strategies/demo/metrics") as ws:
        for _ in range(3):  # читаем три сообщения подряд
            msg = ws.receive_json()
            assert msg["strategy_id"] == "demo"
            # поля присутствуют и являются числовыми/None
            for fld in ("spread_bid", "spread_ask", "pnl"):
                assert fld in msg
                assert isinstance(msg[fld], (float, int))
            for fld in ("position_qty",):
                assert isinstance(msg[fld], int)


def test_ws_metrics_required_fields(client: TestClient):
    """Проверяем что поток содержит ключевые поля spread и статус/позицию."""
    with client.websocket_connect("/ws/strategies/check/metrics") as ws:
        first = ws.receive_json()
        # spread fields
        assert "spread_bid" in first and "spread_ask" in first
        # статус косвенно через position_qty и pnl
        assert "position_qty" in first and "pnl" in first 