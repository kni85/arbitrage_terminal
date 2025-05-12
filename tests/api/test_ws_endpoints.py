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
    with client.websocket_connect("/ws/strategies/demo/metrics") as ws:
        msg = ws.receive_json()
        assert msg["strategy_id"] == "demo"
        assert "spread_bid" in msg 