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
from typing import Optional, Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
#  Account
# ---------------------------------------------------------------------------

class AccountBase(BaseModel):
    # Разрешаем пустые значения для черновиков -> Optional[str]
    alias: Optional[str] = Field(None, max_length=64)
    account_number: Optional[str] = Field(None, max_length=32)
    client_code: Optional[str] = Field(None, max_length=32)


class AccountCreate(BaseModel):
    # Все поля опциональны — разрешаем пустые/частичные строки
    alias: Optional[str] = Field(None, max_length=64)
    account_number: Optional[str] = Field(None, max_length=32)
    client_code: Optional[str] = Field(None, max_length=32)


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
    # Поля могут быть пустыми для черновиков -> Optional[str]
    code: Optional[str] = Field(None, max_length=32)
    name: Optional[str] = Field(None, max_length=128)
    class_code: Optional[str] = Field(None, max_length=16)
    sec_code: Optional[str] = Field(None, max_length=32)
    price_step: Optional[float] = None


class AssetCreate(BaseModel):
    # Все поля опциональны — разрешаем пустые/частичные строки
    code: Optional[str] = Field(None, max_length=32)
    name: Optional[str] = Field(None, max_length=128)
    class_code: Optional[str] = Field(None, max_length=16)
    sec_code: Optional[str] = Field(None, max_length=32)
    price_step: Optional[float] = None


class AssetRead(AssetBase):
    id: int
    updated_at: datetime


class AssetUpdate(BaseModel):
    code: Optional[str] = Field(None, max_length=32)
    name: Optional[str] = Field(None, max_length=128)
    class_code: Optional[str] = Field(None, max_length=16)
    sec_code: Optional[str] = Field(None, max_length=32)
    price_step: Optional[float] = None


# ---------------------------------------------------------------------------
#  Pair (pair_arbitrage row)
# ---------------------------------------------------------------------------

class PairBase(BaseModel):
    # Тоже могут быть не заполнены на этапе черновика
    asset_1: Optional[str] = None
    asset_2: Optional[str] = None

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


class PairCreate(BaseModel):
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
    # value может быть bool/number/str/object/null -> Any
    value: Any = None


class SettingCreate(SettingBase):
    pass


class SettingRead(SettingBase):
    id: int
    updated_at: datetime


class SettingUpdate(BaseModel):
    value: Optional[str] = None


if __name__ == "__main__":
    # Мини-тест: создаём пустые payload — валидатор не должен падать
    print("AssetCreate empty ok:", AssetCreate())
    print("AccountCreate empty ok:", AccountCreate())
    print("PairCreate empty ok:", PairCreate())
