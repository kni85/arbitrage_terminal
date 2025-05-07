import datetime

from backend.api.models import (
    StrategyConfig,
    StrategyStatus,
    OrderSchema,
    TradeSchema,
    SideEnum,
    OrderStatusEnum,
)


def test_strategy_config_validation():
    cfg = StrategyConfig(
        name="Pair SBER vs GAZP",
        instrument_leg1="TQBR.SBER",
        instrument_leg2="TQBR.GAZP",
        price_ratio1=1,
        price_ratio2=1,
        qty_ratio=1,
        threshold_long=-0.5,
        threshold_short=0.6,
        mode="market_maker",
        active=True,
    )
    assert cfg.instrument_leg1 == "TQBR.SBER"
    assert cfg.qty_ratio == 1


def test_strategy_status_serialization():
    status = StrategyStatus(
        strategy_id=1,
        running=True,
        spread_bid=0.1,
        spread_ask=-0.2,
        position_qty=100,
        position_price=5.67,
        pnl=123.45,
    )
    dumped = status.model_dump()
    assert dumped["running"] is True
    assert dumped["pnl"] == 123.45


def test_order_schema_enum_fields():
    now = datetime.datetime.utcnow()
    order = OrderSchema(
        id=1,
        quik_num=123,
        trans_id=55,
        instrument_id=1,
        side=SideEnum.LONG,
        price=278.0,
        qty=1,
        filled=0,
        status=OrderStatusEnum.NEW,
        created_at=now,
        updated_at=now,
    )
    assert order.side == SideEnum.LONG
    assert order.status == OrderStatusEnum.NEW


def test_trade_schema_creation():
    ts = datetime.datetime.utcnow()
    trade = TradeSchema(
        id=1,
        instrument_id=1,
        ts=ts,
        price=10.5,
        qty=3,
        side="buy",
    )
    assert trade.qty == 3 