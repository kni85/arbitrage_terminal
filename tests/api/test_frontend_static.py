import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from backend.api.server import app

def test_frontend_assets_served():
    client = TestClient(app)

    # index page should load and reference main.js
    r = client.get("/")
    assert r.status_code == 200
    assert b"/static/main.js" in r.content

    # main.js static file should be served
    js = client.get("/static/main.js")
    assert js.status_code == 200
    assert b"frontend logic for strategies table" in js.content 