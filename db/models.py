"""
ORM-схема проекта (пакет `db`).

•   PK/FK/индексы → исключаем дубляж и ускоряют джоины
•   __repr__      → удобнее читать логи / отладку
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import List

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    Float,  # Добавлено для PairsColumn.width
    ForeignKey,
    Numeric,
    Enum,
    UniqueConstraint,
    Index,
    inspect,
)
from sqlalchemy.dialects.sqlite import JSON  # заменится на JSONB/JSON для PostgreSQL
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Text

from .database import Base

# -- справочники -------------------------------------------------------------


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    board: Mapped[str] = mapped_column(String(16), nullable=False)
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False)
    price_precision: Mapped[int] = mapped_column(Integer, nullable=False)

    quotes = relationship("Quote", back_populates="instrument", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # noqa: D401
        return f"<Instr {self.ticker} ({self.board})>"

# ===========================================================================
#  GUI reference & settings tables (centralised storage instead of localStorage)
# ===========================================================================


class Account(Base):
    """Список торговых счетов (accounts_table в old localStorage)."""

    __tablename__ = "accounts_table"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Разрешаем NULL для поддержки черновиков строк
    alias: Mapped[str | None] = mapped_column(String(64), nullable=True)
    broker: Mapped[str | None] = mapped_column(String(64), nullable=True)  # Добавлено поле broker
    account_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_code: Mapped[str | None] = mapped_column(String(32), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:  # noqa: D401
        return f"<Account {self.alias} acc={self.account_number}>"


class Asset(Base):
    """Справочник инструментов (assets_table).

    Поле *code* соответствует системному алиасу, который использует GUI.
    """

    __tablename__ = "assets_table"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Разрешаем NULL/пустые значения для поддержки «черновиков»
    code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str | None] = mapped_column(String(128))

    class_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sec_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    price_step: Mapped[float | None] = mapped_column(Numeric(18, 6))

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:  # noqa: D401
        return f"<Asset {self.code} {self.class_code}.{self.sec_code}>"


class Pair(Base):
    """Пара для арбитража (pairs_table). Поля повторяют UI."""

    __tablename__ = "pairs_table"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Все бизнес-поля делаем nullable=True для черновиков
    asset_1: Mapped[str | None] = mapped_column(String(32), nullable=True)
    asset_2: Mapped[str | None] = mapped_column(String(32), nullable=True)

    account_1: Mapped[str | None] = mapped_column(String(64))
    account_2: Mapped[str | None] = mapped_column(String(64))

    side_1: Mapped[str | None] = mapped_column(String(4))  # 'BUY'/'SELL'
    side_2: Mapped[str | None] = mapped_column(String(4))

    qty_ratio_1: Mapped[float | None] = mapped_column(Numeric(18, 6))
    qty_ratio_2: Mapped[float | None] = mapped_column(Numeric(18, 6))

    price_ratio_1: Mapped[float | None] = mapped_column(Numeric(18, 6))
    price_ratio_2: Mapped[float | None] = mapped_column(Numeric(18, 6))

    price: Mapped[float | None] = mapped_column(Numeric(18, 6))
    target_qty: Mapped[int | None] = mapped_column(Integer)

    exec_price: Mapped[float | None] = mapped_column(Numeric(18, 6))
    exec_qty: Mapped[int | None] = mapped_column(Integer)
    leaves_qty: Mapped[int | None] = mapped_column(Integer)

    strategy_name: Mapped[str | None] = mapped_column(String(64))

    price_1: Mapped[float | None] = mapped_column(Numeric(18, 6))
    price_2: Mapped[float | None] = mapped_column(Numeric(18, 6))
    hit_price: Mapped[float | None] = mapped_column(Numeric(18, 6))

    get_mdata: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    started: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)

    error: Mapped[str | None] = mapped_column(String(256))

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связь с сделками
    trades: Mapped[List["Trade"]] = relationship("Trade", back_populates="pair", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # noqa: D401
        return f"<Pair {self.asset_1}/{self.asset_2} id={self.id}>"


class PairsColumn(Base):
    """Порядок и ширина столбцов pairs_table (GUI)."""

    __tablename__ = "pairs_columns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[float | None] = mapped_column(Float)  # Изменено с Integer на Float

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:  # noqa: D401
        return f"<PairsColumn {self.name} pos={self.position} w={self.width}>"


class Trade(Base):
    """Лог реальных сделок для расчёта exec_price по фактическим исполнениям."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pair_id: Mapped[int] = mapped_column(Integer, ForeignKey("pairs_table.id"), nullable=False)
    
    # Данные сделки
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # 'BUY' или 'SELL'
    qty: Mapped[int] = mapped_column(Integer, nullable=False)     # Количество лотов
    price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)  # Цена исполнения
    
    # Метаданные
    quik_trade_id: Mapped[str | None] = mapped_column(String(64))  # ID сделки в QUIK
    asset_code: Mapped[str | None] = mapped_column(String(32))     # Какой актив (asset_1 или asset_2)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Связь с парой
    pair: Mapped["Pair"] = relationship("Pair", back_populates="trades")

    def __repr__(self) -> str:  # noqa: D401
        return f"<Trade pair_id={self.pair_id} {self.side} {self.qty}@{self.price}>"


class Setting(Base):
    """Глобальные key-value настройки GUI (active_tab, sub_c1 и др.)."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    value: Mapped[str | None] = mapped_column(Text)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:  # noqa: D401
        return f"<Setting {self.key}={self.value}>"


# -- поток котировок ---------------------------------------------------------


class Quote(Base):
    """1-секундный снэпшот best bid/ask."""

    __tablename__ = "quotes"
    __table_args__ = (
        Index("ix_quotes_inst_ts", "instrument_id", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    bid: Mapped[float] = mapped_column(Numeric(18, 6))
    bid_qty: Mapped[int] = mapped_column(Integer)
    ask: Mapped[float] = mapped_column(Numeric(18, 6))
    ask_qty: Mapped[int] = mapped_column(Integer)

    instrument = relationship("Instrument", back_populates="quotes")

    def __repr__(self) -> str:  # noqa: D401
        return f"<Quote {self.instrument.ticker} {self.ts:%H:%M:%S} bid={self.bid} ask={self.ask}>"


# -- портфели / стратегии ----------------------------------------------------


class PortfolioConfig(Base):
    """Паспорт стратегии (как она сконфигурирована)."""

    __tablename__ = "portfolio_configs"
    __table_args__ = (
        UniqueConstraint("pid", name="uq_portfolio_pid"),
        Index("ix_portfolio_active", "active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pid: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid.uuid4()), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)

    # --- Доп. поля конфигурации ---
    strategy_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    qty_ratio: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price_ratio: Mapped[str | None] = mapped_column(String(64), nullable=True)
    threshold: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    leaves_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)

    config_json = Column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    positions = relationship("PortfolioPosition", back_populates="portfolio", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="portfolio", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # noqa: D401
        return f"<Portfolio {self.name} pid={self.pid} active={self.active}>"


class Side(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class PortfolioPosition(Base):
    """Актуальные позиции портфеля по каждому инструменту."""

    __tablename__ = "portfolio_positions"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "instrument_id", name="uq_position_portfolio_instrument"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolio_configs.id"), nullable=False)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), nullable=False)

    side: Mapped[Side] = mapped_column(Enum(Side), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)

    portfolio = relationship("PortfolioConfig", back_populates="positions")
    instrument = relationship("Instrument")

    def __repr__(self) -> str:  # noqa: D401
        return f"<Pos {self.portfolio.name}:{self.instrument.ticker} {self.side} {self.qty}>"


# -- ордера / сделки ---------------------------------------------------------


class OrderStatus(StrEnum):
    NEW = "NEW"
    ACTIVE = "ACTIVE"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_portfolio_status", "portfolio_id", "status"),
        Index("ix_orders_trans_id", "trans_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    quik_num: Mapped[int | None] = mapped_column(Integer)
    trans_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolio_configs.id"), nullable=False)
    strategy_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), nullable=False)

    side: Mapped[Side] = mapped_column(Enum(Side), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    filled: Mapped[int] = mapped_column(Integer, default=0)
    leaves_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.NEW)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime)

    portfolio = relationship("PortfolioConfig", back_populates="orders")
    instrument = relationship("Instrument")

    def __repr__(self) -> str:  # noqa: D401
        return f"<Order {self.id}/{self.quik_num} {self.instrument.ticker} {self.side} {self.qty}@{self.price} {self.status}>"





if __name__ == "__main__":
    # Простейшая проверка nullable-столбцов в основных таблицах GUI
    from sqlalchemy import create_engine
    eng = create_engine("sqlite:///arbitrage.db")
    insp = inspect(eng)
    for table in ("assets_table", "accounts_table", "pairs_table"):
        try:
            cols = {c['name']: c['nullable'] for c in insp.get_columns(table)}
            print(f"{table} nullable:", cols)
        except Exception as e:  # pragma: no cover
            print(f"inspect {table} failed:", e)
