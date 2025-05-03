import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import pytest
import asyncio
from backend.core.data_recorder import DataRecorder
from backend.db.models import Trade, Quote, Instrument
from backend.db.database import AsyncSessionLocal, Base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from sqlalchemy.orm import selectinload

@pytest.mark.asyncio
async def test_data_recorder_trades():
    # Настраиваем in-memory БД
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    global AsyncSessionLocal
    AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    import backend.core.data_recorder
    backend.core.data_recorder.AsyncSessionLocal = AsyncSessionLocal
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # ВНЕ блока begin: добавляем инструмент через отдельную сессию
    async with AsyncSessionLocal() as session:
        await session.execute(
            Instrument.__table__.insert().values(
                ticker="SBER", board="TQBR", lot_size=10, price_precision=2
            )
        )
        await session.commit()

    # Теперь создаём DataRecorder и запускаем его
    recorder = DataRecorder([("TQBR", "SBER")], period=0.5)
    await recorder.start()

    # Эмулируем приход сделки (trade)
    recorder._on_trade({
        "class_code": "TQBR",
        "sec_code": "SBER",
        "time": 1234567890,
        "price": 100.5,
        "qty": 2,
        "side": "buy"
    })

    # Ждём, чтобы DataRecorder успел записать сделку
    await asyncio.sleep(0.6)
    await recorder.stop()

    # Проверяем, что сделка записалась в БД
    async with AsyncSessionLocal() as ses:
        trades = (await ses.execute(
            select(Trade).options(selectinload(Trade.instrument))
        )).scalars().all()
        assert len(trades) == 1
        assert trades[0].price == 100.5
        assert trades[0].qty == 2
        assert trades[0].side == "buy"
        assert trades[0].instrument.ticker == "SBER" 