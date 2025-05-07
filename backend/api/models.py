"""api.models – Pydantic-схемы для REST-слоя.

Все схемы имеют `orm_mode=True`, чтобы их можно было напрямую
сериализовать из ORM-объектов SQLAlchemy.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ConfigDict

# ---------------------------------------------------------------------------
# Общие helper-классы
# ---------------------------------------------------------------------------

class SideEnum(str, Enum):
    """Направление сделки / ордера."""

    LONG = "LONG"
    SHORT = "SHORT"


class OrderStatusEnum(str, Enum):
    """Статус ордера, дублирует OrderStatus из ORM."""

    NEW = "NEW"
    ACTIVE = "ACTIVE"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class StrategyConfig(BaseModel):
    """Конфигурация стратегии (портфеля), хранится/передаётся как JSON."""

    strategy_id: Optional[int] = Field(None, description="ID стратегии (заполняется при ответе)")
    name: str = Field(..., description="Название стратегии для UI")

    instrument_leg1: str = Field(..., description="Тикер инструмента ноги 1, формат CLASS.SEC")
    instrument_leg2: str = Field(..., description="Тикер инструмента ноги 2, формат CLASS.SEC")

    price_ratio1: float = Field(1.0, description="Коэффициент цены ноги 1")
    price_ratio2: float = Field(1.0, description="Коэффициент цены ноги 2")

    qty_ratio: float = Field(1.0, gt=0, description="Коэффициент объёма между ногами")

    threshold_long: float = Field(..., description="Порог входа (лонг базиса)")
    threshold_short: float = Field(..., description="Порог входа (шорт базиса)")

    mode: str = Field("shooter", description="Режим: shooter | market_maker")
    active: bool = Field(True, description="Флаг активности стратегии")

    model_config = ConfigDict(from_attributes=True, json_schema_extra={
        "example": {
            "name": "Pair SBER vs GAZP",
            "instrument_leg1": "TQBR.SBER",
            "instrument_leg2": "TQBR.GAZP",
            "price_ratio1": 1,
            "price_ratio2": 1,
            "qty_ratio": 1,
            "threshold_long": -0.5,
            "threshold_short": 0.6,
            "mode": "market_maker",
            "active": True,
        }
    })


class StrategyStatus(BaseModel):
    """Текущий статус стратегии – отдаётся фронтенду для отображения."""

    strategy_id: int
    running: bool

    spread_bid: Optional[float] = None
    spread_ask: Optional[float] = None

    position_qty: Optional[int] = None
    position_price: Optional[float] = None
    pnl: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Order / Trade
# ---------------------------------------------------------------------------

class OrderSchema(BaseModel):
    """Представление ордера для API."""

    id: int
    quik_num: Optional[int]
    trans_id: Optional[int]
    instrument_id: int

    side: SideEnum
    price: float
    qty: int
    filled: int
    leaves_qty: Optional[int] = Field(None)
    status: OrderStatusEnum

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TradeSchema(BaseModel):
    """Представление сделки для API."""

    id: int
    instrument_id: int
    ts: datetime

    price: float
    qty: int
    side: str

    model_config = ConfigDict(from_attributes=True) 