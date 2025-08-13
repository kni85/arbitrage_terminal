"""Root routes for Arbitrage Terminal GUI."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

# Используем HTML_PAGE, определённый в frontend.gui.server (пока остаётся там)
from frontend.gui import server as gui_server  # type: ignore

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:  # noqa: D401
    """Главная страница GUI."""
    return HTMLResponse(gui_server.HTML_PAGE)
