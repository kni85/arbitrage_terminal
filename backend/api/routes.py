"""Root routes for Arbitrage Terminal GUI."""

# noqa: D401
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index():
    """Главная страница GUI: отдаём HTML_PAGE из legacy server.py."""

    import importlib

    legacy = importlib.import_module("server")  # type: ignore
    html = getattr(legacy, "HTML_PAGE", None)
    if not html:
        return HTMLResponse("<h3>HTML_PAGE not found in server.py</h3>")
    return HTMLResponse(html)
