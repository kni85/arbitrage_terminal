"""Root routes for Arbitrage Terminal GUI."""

# noqa: D401
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index():
    """Главная страница GUI: отдаём HTML_PAGE из legacy server.py."""

    import importlib, re, pathlib, sys

    try:
        legacy = importlib.import_module("server")  # type: ignore
        html = getattr(legacy, "HTML_PAGE", None)
        if isinstance(html, str):
            return HTMLResponse(html)
    except ModuleNotFoundError:
        # server.py импортируется, но внутри есть старые пути.
        pass

    # Fallback: читаем файл server.py и вытаскиваем строку HTML_PAGE = """..."""
    srv_path = pathlib.Path("server.py")
    if srv_path.exists():
        text = srv_path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"HTML_PAGE\s*=\s*([\'\"]{3})([\s\S]*?)\1", text)
        if m:
            html_raw = m.group(2)
            return HTMLResponse(html_raw)

    return HTMLResponse("<h3>Cannot load HTML_PAGE from server.py</h3>")
