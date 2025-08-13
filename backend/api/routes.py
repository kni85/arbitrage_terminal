"""Root routes for Arbitrage Terminal GUI."""

# noqa: D401
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pathlib import Path

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index():
    """Главная страница GUI – читаем шаблон как статический HTML."""

    tpl_path = Path("frontend/templates/index.html")
    if tpl_path.exists():
        content = tpl_path.read_text(encoding="utf-8")
        return HTMLResponse(content)

    return HTMLResponse("<h3>index.html not found</h3>")
