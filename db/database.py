"""
Модуль `db.database` — единая точка доступа к базе данных проекта.

* **SQLAlchemy 2.x** в асинхронном режиме (`AsyncSession`).
* По умолчанию используется SQLite-файл `arbitrage.db` в корне проекта;
  при необходимости задайте переменную окружения `DATABASE_URL`.
* Экспортируемые сущности:
  - `async_engine` — `AsyncEngine` (низкоуровневые запросы).
  - `AsyncSessionLocal` — фабрика `async_sessionmaker`.
  - `Base` — базовый класс моделей.
  - `init_db()` / `close_db()` — инициализация и корректное закрытие.
  - `ensure_tables_exist()` — idempotent-функция для ленивого создания таблиц.
  - `get_session()` — зависимость FastAPI.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Конфигурация подключения
# ---------------------------------------------------------------------------

DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./arbitrage.db"
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_SQLITE_URL)

async_engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Базовый класс для ORM-моделей."""


# ---------------------------------------------------------------------------
# Инициализация / закрытие БД
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Создать таблицы (если их ещё нет). Вызывается однократно."""

    logger.info("[db] Инициализация БД (%s)…", DATABASE_URL)

    # Импортируем db.models (относительный импорт внутри пакета)
    try:
        from . import models as _models  # noqa: F401
        logger.debug("Импортировано %s", _models.__name__)
    except ModuleNotFoundError:  # pragma: no cover
        logger.warning("Модуль db.models не найден — создаётся пустая схема.")

    async with async_engine.begin() as conn:
        # важное: checkfirst=True, иначе попытка создать уже существующую таблицу упадёт
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

    logger.info("[db] Таблицы готовы.")


async def close_db() -> None:
    """Закрыть connection-pool при завершении приложения."""

    logger.info("[db] Закрытие AsyncEngine…")
    await async_engine.dispose()
    logger.info("[db] Соединения закрыты.")


# ---------------------------------------------------------------------------
# ensure_tables_exist — ленивый одноразовый вызов init_db
# ---------------------------------------------------------------------------

_tables_created = False
_init_lock = asyncio.Lock()          # общий замок


async def ensure_tables_exist() -> None:
    """Idempotent-функция: один раз создаёт таблицы во всём приложении."""

    global _tables_created  # noqa: PLW0603
    if _tables_created:
        return
    await init_db()
    _tables_created = True


# ---------------------------------------------------------------------------
# Зависимость FastAPI — выдаёт `AsyncSession`
# ---------------------------------------------------------------------------

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:  # type: AsyncSession
        yield session


# ---------------------------------------------------------------------------
# Самотестирование модуля
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from sqlalchemy import Column, Integer, String, select

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Тестируем в in-memory SQLite
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    TestSession = async_sessionmaker(bind=test_engine, expire_on_commit=False)

    class Person(Base):  # type: ignore[misc]
        __tablename__ = "persons"
        id = Column(Integer, primary_key=True)
        name = Column(String(50))

    async def _demo() -> None:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with TestSession() as ses:
            ses.add(Person(name="Alice"))
            await ses.commit()

        async with TestSession() as ses:
            res = await ses.execute(select(Person))
            print("Таблица persons:", res.scalars().all())

        await test_engine.dispose()

    asyncio.run(_demo())
    sys.exit(0)
