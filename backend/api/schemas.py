"""Pydantic набор схем для REST-API.

Схемы разделены на три группы для каждой сущности:
• *Create*  – данные, которые принимает POST-запрос при создании записи.
• *Read*    – данные, которые возвращаются клиенту.
• *Update*  – частичное обновление (все поля Optional).  

При необходимости версионирования можно добавлять поле `version` в Read/Update, 
но пока используем `updated_at`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
#  Account
# ---------------------------------------------------------------------------

class AccountBase(BaseModel):
    alias: str = Field(..., max_length=64)
    account_number: str = Field(..., max_length=32)
    client_code: str = Field(..., max_length=32)


class AccountCreate(AccountBase):
    pass


class AccountRead(AccountBase):
    id: int
    updated_at: datetime


class AccountUpdate(BaseModel):
    alias: Optional[str] = Field(None, max_length=64)
    account_number: Optional[str] = Field(None, max_length=32)
    client_code: Optional[str] = Field(None, max_length=32)


# ---------------------------------------------------------------------------
#  Asset
# ---------------------------------------------------------------------------

class AssetBase(BaseModel):
    code: str = Field(..., max_length=32)
    name: Optional[str] = Field(None, max_length=128)
    class_code: str = Field(..., max_length=16)
    sec_code: str = Field(..., max_length=32)
    price_step: Optional[float] = None


class AssetCreate(AssetBase):
    pass


class AssetRead(AssetBase):
    id: int
    updated_at: datetime


class AssetUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    class_code: Optional[str] = Field(None, max_length=16)
    sec_code: Optional[str] = Field(None, max_length=32)
    price_step: Optional[float] = None


# ---------------------------------------------------------------------------
#  Pair (pair_arbitrage row)
# ---------------------------------------------------------------------------

class PairBase(BaseModel):
    asset_1: str
    asset_2: str

    account_1: Optional[str] = None
    account_2: Optional[str] = None

    side_1: Optional[str] = None  # 'BUY'/'SELL'
    side_2: Optional[str] = None

    qty_ratio_1: Optional[float] = None
    qty_ratio_2: Optional[float] = None

    price_ratio_1: Optional[float] = None
    price_ratio_2: Optional[float] = None

    price: Optional[float] = None
    target_qty: Optional[int] = None

    strategy_name: Optional[str] = None

    # runtime / calculated
    exec_price: Optional[float] = None
    exec_qty: Optional[int] = None
    leaves_qty: Optional[int] = None

    price_1: Optional[float] = None
    price_2: Optional[float] = None
    hit_price: Optional[float] = None

    get_mdata: Optional[bool] = False
    started: Optional[bool] = False

    error: Optional[str] = None


class PairCreate(PairBase):
    pass


class PairRead(PairBase):
    id: int
    updated_at: datetime


class PairUpdate(BaseModel):
    asset_1: Optional[str] = None
    asset_2: Optional[str] = None
    account_1: Optional[str] = None
    account_2: Optional[str] = None
    side_1: Optional[str] = None
    side_2: Optional[str] = None
    qty_ratio_1: Optional[float] = None
    qty_ratio_2: Optional[float] = None
    price_ratio_1: Optional[float] = None
    price_ratio_2: Optional[float] = None
    price: Optional[float] = None
    target_qty: Optional[int] = None
    strategy_name: Optional[str] = None
    exec_price: Optional[float] = None
    exec_qty: Optional[int] = None
    leaves_qty: Optional[int] = None
    price_1: Optional[float] = None
    price_2: Optional[float] = None
    hit_price: Optional[float] = None
    get_mdata: Optional[bool] = None
    started: Optional[bool] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
#  PairsColumn
# ---------------------------------------------------------------------------

class PairsColumnBase(BaseModel):
    name: str = Field(..., max_length=32)
    position: int
    width: Optional[int] = None


class PairsColumnCreate(PairsColumnBase):
    pass


class PairsColumnRead(PairsColumnBase):
    id: int
    updated_at: datetime


class PairsColumnUpdate(BaseModel):
    position: Optional[int] = None
    width: Optional[int] = None


# ---------------------------------------------------------------------------
#  Setting (key-value)
# ---------------------------------------------------------------------------

class SettingBase(BaseModel):
    key: str = Field(..., max_length=64)
    value: Optional[str] = None


class SettingCreate(SettingBase):
    pass


class SettingRead(SettingBase):
    id: int
    updated_at: datetime


class SettingUpdate(BaseModel):
    value: Optional[str] = None
