"""
ORM-схема проекта.

•   PK/FK/индексы → исключаем размножение дублей и ускоряем джоины
•   __repr__      → удобнее читать логи / отладку
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey, Numeric, Enum,
    UniqueConstraint, Index
)
from sqlalchemy.dialects.sqlite import JSON  # заменится на JSONB/JSON для PostgreSQL
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# -- справочники -------------------------------------------------------------

class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int]         = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str]     = mapped_column(String(32), unique=True, nullable=False)
    board:  Mapped[str]     = mapped_column(String(16), nullable=False)
    lot_size: Mapped[int]   = mapped_column(Integer, nullable=False)
    price_precision: Mapped[int] = mapped_column(Integer, nullable=False)

    quotes = relationship("Quote", back_populates="instrument", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Instr {self.ticker} ({self.board})>"


# -- поток котировок ---------------------------------------------------------

class Quote(Base):
    """
    1-секундный снэпшот best bid/ask.
    """
    __tablename__ = "quotes"
    __table_args__ = (
        Index("ix_quotes_inst_ts", "instrument_id", "ts"),
    )

    id: Mapped[int]           = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    ts: Mapped[datetime]      = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    bid: Mapped[float]        = mapped_column(Numeric(18, 6))
    bid_qty: Mapped[int]      = mapped_column(Integer)
    ask: Mapped[float]        = mapped_column(Numeric(18, 6))
    ask_qty: Mapped[int]      = mapped_column(Integer)

    instrument = relationship("Instrument", back_populates="quotes")

    def __repr__(self) -> str:
        return f"<Quote {self.instrument.ticker} {self.ts:%H:%M:%S} bid={self.bid} ask={self.ask}>"


# -- портфели / стратегии ----------------------------------------------------

class PortfolioConfig(Base):
    """
    Храним «паспорт» стратегии (как она была сконфигурирована).
    • `pid` — публичный UUID (используется в API/фронте)
    • `id`   — суррогатный PK, не светится наружу
    """
    __tablename__ = "portfolio_configs"
    __table_args__ = (
        UniqueConstraint("pid", name="uq_portfolio_pid"),
        Index("ix_portfolio_active", "active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pid: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid.uuid4()), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)

    # --- Новые поля для конфигурирования стратегии ---
    strategy_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="ID стратегии (тип)")
    mode: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="Режим работы (shooter, market_maker и др.)")
    qty_ratio: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="Коэффициенты объёма (формула или число)")
    price_ratio: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="Коэффициенты цены (формула или число)")
    threshold: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True, comment="Порог входа (уровень отклонения базиса)")
    leaves_qty: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Остаток объёма для исполнения (leaves_qty)")
    # ---

    config_json = Column(JSON, nullable=False)            # raw-конфиг (legs, ratios…)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    positions = relationship("PortfolioPosition", back_populates="portfolio",
                             cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="portfolio",
                          cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Portfolio {self.name} pid={self.pid} active={self.active}>"



class Side(StrEnum):
    LONG  = "LONG"
    SHORT = "SHORT"


class PortfolioPosition(Base):
    """
    Актуальные позиции портфеля по каждому инструменту.
    """
    __tablename__ = "portfolio_positions"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "instrument_id",
                         name="uq_position_portfolio_instrument"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolio_configs.id"), nullable=False)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), nullable=False)

    side: Mapped[Side] = mapped_column(Enum(Side), nullable=False)
    qty:  Mapped[int]  = mapped_column(Integer, nullable=False)
    avg_price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)

    portfolio = relationship("PortfolioConfig", back_populates="positions")
    instrument = relationship("Instrument")

    def __repr__(self) -> str:
        return f"<Pos {self.portfolio.name}:{self.instrument.ticker} {self.side} {self.qty}>"


# -- ордера / сделки ---------------------------------------------------------

class OrderStatus(StrEnum):
    NEW       = "NEW"
    ACTIVE    = "ACTIVE"
    PARTIAL   = "PARTIAL"
    FILLED    = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED  = "REJECTED"


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_portfolio_status", "portfolio_id", "status"),
        Index("ix_orders_trans_id", "trans_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)      # внутренний id
    quik_num: Mapped[int | None] = mapped_column(Integer)                      # № заявки в QUIK
    trans_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="ID транзакции QUIK (TRANS_ID)")
    portfolio_id:  Mapped[int]  = mapped_column(ForeignKey("portfolio_configs.id"), nullable=False)
    strategy_id:   Mapped[int | None] = mapped_column(Integer, nullable=True, comment="ID стратегии (если нужно)")
    instrument_id: Mapped[int]  = mapped_column(ForeignKey("instruments.id"), nullable=False)

    side:    Mapped[Side]        = mapped_column(Enum(Side), nullable=False)
    price:   Mapped[float]       = mapped_column(Numeric(18, 6), nullable=False)
    qty:     Mapped[int]         = mapped_column(Integer, nullable=False)
    filled:  Mapped[int]         = mapped_column(Integer, default=0)
    leaves_qty: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Остаток объёма для исполнения (leaves_qty)")

    status:  Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.NEW)

    created_at:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime)

    portfolio = relationship("PortfolioConfig", back_populates="orders")
    instrument = relationship("Instrument")

    def __repr__(self) -> str:
        return (f"<Order {self.id}/{self.quik_num} {self.instrument.ticker} "
                f"{self.side} {self.qty}@{self.price} {self.status}>")


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_inst_ts", "instrument_id", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # 'buy'/'sell'

    instrument = relationship("Instrument")

    def __repr__(self) -> str:
        return f"<Trade {self.instrument.ticker} {self.ts:%H:%M:%S} {self.side} {self.qty}@{self.price}>"
