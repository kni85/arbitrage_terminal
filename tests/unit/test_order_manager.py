import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from backend.core.order_manager import OrderManager
from backend.db.models import Order, OrderStatus, Side
from backend.db.database import AsyncSessionLocal, Base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

@pytest.mark.asyncio
async def test_order_manager_place_and_cancel(monkeypatch):
    # Настраиваем in-memory БД
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    global AsyncSessionLocal
    AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    import backend.core.order_manager
    backend.core.order_manager.AsyncSessionLocal = AsyncSessionLocal
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Добавляем тестовый ордер в БД
    async with AsyncSessionLocal() as session:
        order = Order(
            portfolio_id=1,
            instrument_id=1,
            side=Side.LONG,  # или Side.SHORT
            price=100,
            qty=1,
            filled=0,
            status=OrderStatus.NEW
        )
        session.add(order)
        await session.commit()
        orm_order_id = order.id

    # Мокаем QuikConnector внутри OrderManager
    mock_connector = MagicMock()
    mock_connector.place_limit_order = AsyncMock(return_value={"order_num": 12345})
    mock_connector.cancel_order = AsyncMock()
    mock_connector.subscribe_orders = MagicMock()

    # Подменяем QuikConnector в OrderManager
    monkeypatch.setattr("backend.core.order_manager.QuikConnector", lambda: mock_connector)

    manager = OrderManager()

    # Тестируем выставление лимитного ордера
    quik_id = await manager.place_limit_order({"ACTION": "NEW_ORDER"}, orm_order_id)
    assert quik_id == 12345
    assert manager._quik_to_orm[12345] == orm_order_id
    assert manager._orm_to_quik[orm_order_id] == 12345

    # Проверяем, что quik_num обновился в БД
    async with AsyncSessionLocal() as session:
        order = await session.get(Order, orm_order_id)
        assert order.quik_num == 12345

    # Тестируем отмену ордера
    await manager.cancel_order(orm_order_id)
    mock_connector.cancel_order.assert_awaited_with(str(12345))

    # Тестируем обновление статуса по событию
    event = {"order_id": 12345, "status": OrderStatus.FILLED, "filled": 1}
    manager._on_order_event(event)
    await asyncio.sleep(0.1)  # Дать время на асинхронную задачу
    async with AsyncSessionLocal() as session:
        order = await session.get(Order, orm_order_id)
        assert order.status == OrderStatus.FILLED
        assert order.filled == 1 