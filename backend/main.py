"""
Точка входа (entry‑point) серверной части арбитражного терминала.

* Создаём экземпляр FastAPI.
* Инициализируем базу данных.
* Запускаем/останавливаем `PortfolioManager` при запуске и завершении приложения.

Запуск для разработки:

```bash
uvicorn backend.main:create_app --reload --factory
```

> **Примечание**: модуль опирается на пакеты `api.server`, `core.portfolio_manager` и
> `db.database`, которые будут созданы на следующих шагах. Если сейчас их нет,
> скрипт выдаст `ImportError`.
"""

from __future__ import annotations

import logging
from typing import Optional

import uvicorn
from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Локальные импорты (будут реализованы далее)
# ---------------------------------------------------------------------------
try:
    from api.server import api_router  # все REST‑эндпоинты
    from core.portfolio_manager import PortfolioManager  # диспетчер стратегий
    from db.database import init_db, close_db  # вспомогательные функции БД
except ImportError as exc:  # позволяют запускать файл, пока зависимостей нет
    logging.warning(
        "Некоторые внутренние модули пока отсутствуют (%s). "
        "Файл можно запускать, но функциональность ограничена.",
        exc,
    )

    # Заглушки, чтобы код запускался до появления реальных модулей
    class _Stub:  # pylint: disable=too-few-public-methods
        async def start(self):
            pass

        async def stop(self):
            pass

    api_router = None  # type: ignore
    PortfolioManager = _Stub  # type: ignore

    async def init_db():  # type: ignore
        pass

    async def close_db():  # type: ignore
        pass

# ---------------------------------------------------------------------------
# Настройка логирования
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Фабрика приложения
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Создаём и настраиваем экземпляр FastAPI."""

    app = FastAPI(
        title="Arbitrage Trading Engine",
        version="0.1.0",
        docs_url="/",  # Swagger UI будет доступен по корневому URL
        redoc_url=None,
    )

    # Инициализируем подключение к базе данных
    app.add_event_handler("startup", init_db)
    app.add_event_handler("shutdown", close_db)

    # Создаём и сохраняем менеджер портфелей
    manager: PortfolioManager | _Stub = PortfolioManager()  # type: ignore[arg-type]
    app.state.portfolio_manager = manager

    # Подключаем REST‑эндоинты, если они уже доступны
    if api_router is not None:
        app.include_router(api_router, prefix="/api")

    # При старте приложения – запускаем менеджер стратегий
    @app.on_event("startup")
    async def _start_manager() -> None:  # noqa: D401
        logger.info("[startup] Запуск PortfolioManager …")
        await manager.start()
        logger.info("[startup] PortfolioManager запущен.")

    # При завершении – останавливаем
    @app.on_event("shutdown")
    async def _stop_manager() -> None:  # noqa: D401
        logger.info("[shutdown] Остановка PortfolioManager …")
        await manager.stop()
        logger.info("[shutdown] PortfolioManager остановлен.")

    return app


# ---------------------------------------------------------------------------
# Быстрый тест / запуск скрипта напрямую
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Позволяет быстро проверить, что файл корректно создаёт приложение.

    1. Запускаем `create_app()`.
    2. Выводим список маршрутов.
    3. Далее – опционально запускаем Uvicorn, чтобы можно было потыкать в Swagger.
    """

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app_instance: FastAPI = create_app()

    # Проверочный вывод маршрутов
    print("\nСписок зарегистрированных маршрутов:")
    for route in app_instance.routes:
        if hasattr(route, "methods"):
            methods = ",".join(route.methods)
            print(f"{methods:<10} {route.path}")

    # Запускаем Uvicorn, если в аргументах не передано 'no-server'.
    import sys

    if "no-server" not in sys.argv:
        uvicorn.run(
            "backend.main:create_app",
            host="0.0.0.0",
            port=8000,
            reload=False,  # Внутренний запуск – без авто‑перезагрузки
            factory=True,
        )
