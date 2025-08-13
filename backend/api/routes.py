"""Root routes for Arbitrage Terminal GUI."""

# noqa: D401
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

templates = Jinja2Templates(directory="frontend/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница GUI (рендерится из шаблона templates/index.html)."""
    return templates.TemplateResponse("index.html", {"request": request})
