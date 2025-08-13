"""Root routes for Arbitrage Terminal GUI."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

# Следим, чтобы не создавать циклический импорт: HTML_PAGE берём лениво.

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:  # noqa: D401
    """Главная страница GUI."""
    from frontend.gui import server as gui_server  # local import to avoid circular
    return HTMLResponse(gui_server.HTML_PAGE)
