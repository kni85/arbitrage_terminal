"""
Модуль `db.database` – единая точка доступа к базе данных проекта.

* Используется **SQLAlchemy 2.x** в асинхронном режиме (`AsyncSession`).
* В качестве СУБД по умолчанию – SQLite (файл `arbitrage.db` в корне). При
  желании можно задать переменную окружения `DATABASE_URL`, например
  `postgresql+asyncpg://user:pwd@localhost/dbname`.
* Экспортируются:
  - `async_engine` – объект `AsyncEngine` (для прямых запросов при низком уровне).
  - `AsyncSessionLocal` – фабрика `async_sessionmaker` для создания сессий.
  - `Base` – базовый класс для ORM‑моделей (используется в модулях `db.models`).
  - Функции `init_db()` и `close_db()` – вызываются FastAPI при старте/выключении.
  - Зависимость `get_session()` – удобна в роутах FastAPI.

Важно: здесь **не** описываются конкретные таблицы (модели). Они будут
созданы в модуле `db.models` и должны наследоваться от `Base`. Если такой
модуль отсутствует, при инициализации базы будет создана пустая схема.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Конфигурация подключения
# ---------------------------------------------------------------------------

DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./arbitrage.db"
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_SQLITE_URL)

async_engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,  # можно включить True для подробного логирования SQL
    future=True,
)

# Фабрика сессий
AsyncSessionLocal = async_sessionmaker(  # noqa: N816 (snake_case допускается)
    bind=async_engine,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# Базовый класс ORM-моделей
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Базовый класс для ORM‑моделей SQLAlchemy."""


# ---------------------------------------------------------------------------
# Инициализация / закрытие БД (вызывается FastAPI в lifecycle‑хендлерах)
# ---------------------------------------------------------------------------

async def init_db() -> None:  # noqa: D401
    """Создание таблиц, если их ещё нет.

    Вызывается при старте приложения. Если модуль `db.models` существует, он
    будет импортирован для регистрации моделей.
    """

    logger.info("[db] Инициализация БД (%s)…", DATABASE_URL)

    # Импортируем модели, если они определены (иначе Base.metadata пустая)
    try:
        import importlib

        importlib.import_module("db.models")
    except ModuleNotFoundError:
        logger.warning("Модуль db.models не найден – создаём пустую схему.")

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("[db] Инициализация завершена.")


async def close_db() -> None:  # noqa: D401
    """Корректное закрытие connection‑пула при завершении приложения."""

    logger.info("[db] Закрытие AsyncEngine…")
    await async_engine.dispose()
    logger.info("[db] Соединения закрыты.")


# ---------------------------------------------------------------------------
# Зависимость для FastAPI – выдаёт контекстную асинхронную сессию
# ---------------------------------------------------------------------------

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:  # noqa: D401
    """Контекстный менеджер‑генератор, возвращающий `AsyncSession`.

    Пример использования в роут‑хендлере FastAPI:

    ```python
    @router.get("/quotes")
    async def list_quotes(session: AsyncSession = Depends(get_session)):
        result = await session.execute(select(Quote))
        return result.scalars().all()
    ```
    """

    async with AsyncSessionLocal() as session:  # type: AsyncSession
        try:
            yield session
        finally:
            # Закрываем сессию (возврат в пул)
            await session.close()


# ---------------------------------------------------------------------------
# Тестирование модуля (запуск `python db/database.py`)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """Автоматический тест: создаём временную in‑memory SQLite, пишем/читаем."""

    import sys
    from sqlalchemy import Column, Integer, String, select

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Переопределим DATABASE_URL на in‑memory, чтобы не портить файл
    DATABASE_URL = "sqlite+aiosqlite:///:memory:"
    test_engine = create_async_engine(DATABASE_URL, echo=False, future=True)
    TestSession = async_sessionmaker(bind=test_engine, expire_on_commit=False)

    class Person(Base):  # type: ignore[misc]
        __tablename__ = "persons"
        id = Column(Integer, primary_key=True)
        name = Column(String(50))

    async def _demo() -> None:
        # Создаём таблицы
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Добавляем запись
        async with TestSession() as ses:
            ses.add(Person(name="Alice"))
            await ses.commit()

        # Читаем запись
        async with TestSession() as ses:
            result = await ses.execute(select(Person))
            people = result.scalars().all()
            print("Содержимое таблицы persons:", people)

        # Закрываем движок
        await test_engine.dispose()

    asyncio.run(_demo())

    sys.exit(0)
