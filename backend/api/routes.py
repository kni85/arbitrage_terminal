"""Root routes for Arbitrage Terminal GUI."""

# noqa: D401
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


HTML_PLACEHOLDER = """<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'/><title>Arbitrage Terminal</title></head><body><h2>Arbitrage Terminal GUI</h2><p>Статический HTML_PAGE ещё не перенесён. Проверьте план S6-move-gui.</p></body></html>"""


@router.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Возвращает страницу GUI.

    В устаревшем коде HTML_PAGE находился в ``frontend.gui.server``.
    Этот файл удалён в ходе рефакторинга, поэтому возвращаем временный
    placeholder, чтобы сервер не падал с 500. Полноценный перенос GUI в
    шаблоны запланирован на последующие шаги (S6_move_gui).
    """
    return HTMLResponse(HTML_PLACEHOLDER)
