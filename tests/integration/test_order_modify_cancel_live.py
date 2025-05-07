import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import pytest
import asyncio
from backend.core.order_manager import OrderManager
from backend.db.models import Order, OrderStatus, Side
from backend.db.database import AsyncSessionLocal


@pytest.mark.asyncio
async def test_live_order_modify_and_cancel():
    """Интеграционный тест:
    1) выставляется лимитный ордер SBER по 278;
    2) через 10 сек. цена изменяется на 280 (MOVE_ORDERS);
    3) ещё через 10 сек. заявка снимается.

    ВНИМАНИЕ: тест реально отправляет транзакции в QUIK! Запускайте на тестовом/боевом счёте осознанно.
    Перед запуском заполните значения ACCOUNT / PORTFOLIO_ID / INSTRUMENT_ID.
    """
    # === Замените на реальные значения для вашего терминала/БД ===
    ACCOUNT = "L01-00000F00"
    PORTFOLIO_ID = 1
    INSTRUMENT_ID = 1  # SBER
    # ============================================================

    manager = OrderManager()

    # Шаг 1. Добавляем ордер в БД
    async with AsyncSessionLocal() as session:
        order = Order(
            portfolio_id=PORTFOLIO_ID,
            instrument_id=INSTRUMENT_ID,
            side=Side.LONG,
            price=278,
            qty=1,
            filled=0,
            status=OrderStatus.NEW,
        )
        session.add(order)
        await session.commit()
        orm_order_id = order.id
        print(f"Created ORM Order: {orm_order_id}")

    order_data = {
        "ACTION": "NEW_ORDER",
        "CLASSCODE": "TQBR",
        "SECCODE": "SBER",
        "ACCOUNT": ACCOUNT,
        "OPERATION": "B",
        "PRICE": "278",
        "QUANTITY": "1",
        "TRANS_ID": "8",  # замените, если нужно уникальность
        "CLIENT_CODE": "1360W2",
    }

    quik_num_resp = await manager.place_limit_order(order_data, orm_order_id)
    print(f"Order placed, response: {quik_num_resp}")

    # Ждём, пока появится QUIK ID
    async def wait_for_quik_id(timeout=10):
        for _ in range(timeout * 10):
            qid = manager._orm_to_quik.get(orm_order_id)
            if qid:
                return qid
            await asyncio.sleep(0.1)
        raise TimeoutError("QUIK ID не появился в течение таймаута")

    quik_id = await wait_for_quik_id()
    print(f"QUIK ID mapped: {quik_id}")

    # Шаг 2. Ждём 10 сек. и меняем цену на 280
    await asyncio.sleep(10)
    await manager.modify_order(orm_order_id, new_price=280)
    print("Order price modify requested to 280")

    # Шаг 3. Ждём ещё 10 сек. и снимаем заявку
    await asyncio.sleep(10)
    await manager.cancel_order(orm_order_id)
    print("Order cancel requested")

    # Даем QUIK время обновить статус
    await asyncio.sleep(2)

    async with AsyncSessionLocal() as session:
        order = await session.get(Order, orm_order_id)
        print(f"Final order status: {order.status}, price: {order.price}") 