"""
`db.models` – ORM‑модели проекта для SQLAlchemy.

Содержит базовые сущности:
* **Instrument** – справочник инструментов (тикер, биржа, точность цены).
* **PortfolioConfig** – таблица конфигураций портфелей в JSON‑виде.
* **Quote** – история котировок (bid/ask) раз в секунду.

> **Важно**: все модели наследуются от `Base`, экспортированного в
> `db.database`. При первом импорте `db.models` файл должен быть доступен,
> иначе `db.database.init_db()` не создаст таблицы.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base

# ---------------------------------------------------------------------------
# Таблица инструментов
# ---------------------------------------------------------------------------

class Instrument(Base):
    """Справочник торговых инструментов."""

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    board: Mapped[str] = mapped_column(String(16), default="")
    lot_size: Mapped[int] = mapped_column(Integer, default=1)
    price_precision: Mapped[int] = mapped_column(Integer, default=2)

    def __repr__(self) -> str:  # noqa: D401
        return f"<Instrument {self.ticker} ({self.board})>"


# ---------------------------------------------------------------------------
# Таблица конфигураций портфелей
# ---------------------------------------------------------------------------

class PortfolioConfig(Base):
    """Хранит JSON‑конфигурацию портфеля (legs, ratios, уровни …)."""

    __tablename__ = "portfolio_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    config_json: Mapped[Dict[str, Any]] = mapped_column(JSON)  # хранит сырой dict
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:  # noqa: D401
        return f"<PortfolioConfig {self.pid} ({self.name})>"


# ---------------------------------------------------------------------------
# История котировок (bid/ask)
# ---------------------------------------------------------------------------

class Quote(Base):
    """Запись котировки `bid` / `ask` инструмента на момент времени."""

    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    instrument: Mapped[str] = mapped_column(String(32), index=True)
    bid: Mapped[float] = mapped_column(Float)
    ask: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint("timestamp", "instrument", name="uq_quote_time_instr"),
    )

    def __repr__(self) -> str:  # noqa: D401
        return f"<Quote {self.instrument} {self.timestamp} bid={self.bid} ask={self.ask}>"


# ---------------------------------------------------------------------------
# Простой тест‑скрипт: создаём in‑memory базу, таблицы, пару записей
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio
    import sys

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy import select

    from db.database import Base

    async def _demo() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        Session = async_sessionmaker(bind=engine, expire_on_commit=False)

        # Добавляем инструмент и котировку
        async with Session() as ses:
            ses.add(Instrument(ticker="EURUSD", board="FORTS", lot_size=1, price_precision=4))
            ses.add(
                Quote(
                    timestamp=datetime.utcnow(),
                    instrument="EURUSD",
                    bid=1.1234,
                    ask=1.1236,
                )
            )
            await ses.commit()

        # Выводим содержимое таблицы quotes
        async with Session() as ses:
            rows = (await ses.execute(select(Quote))).scalars().all()
            for row in rows:
                print(row)

        await engine.dispose()

    asyncio.run(_demo())
    sys.exit(0)
