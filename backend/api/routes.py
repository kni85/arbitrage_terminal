"""Root routes for Arbitrage Terminal GUI."""

# noqa: D401
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

templates = Jinja2Templates(directory="frontend/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница GUI.

    Пока полноразмерный шаблон ещё не отлажен, пробуем сначала отдать
    HTML_PAGE из legacy `server.py`. Если его нет – рендерим шаблон.
    """
    try:
        import server as legacy_server  # type: ignore

        html = getattr(legacy_server, "HTML_PAGE", None)
        if html:
            return HTMLResponse(html)
    except Exception:  # pragma: no cover – не критично
        pass

    return templates.TemplateResponse("index.html", {"request": request})
