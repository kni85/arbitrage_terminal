import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import random
import pytest
import asyncio
from backend.core.order_manager import OrderManager
from backend.db.models import Order, OrderStatus, Side
from backend.db.database import AsyncSessionLocal

@pytest.mark.asyncio
async def test_live_order_manager_sber_buy_and_cancel_30s():
    """
    Интеграционный тест: выставление лимитного ордера на покупку 1 лота SBER по 230 и снятие его через 30 секунд.
    ВНИМАНИЕ: тест реально отправляет заявку на биржу! Используйте только на тестовом/боевом счёте с осторожностью.
    Перед запуском укажите реальные значения ACCOUNT, portfolio_id, instrument_id.
    """
    # === Замените на ваши реальные значения ===
    ACCOUNT = "L01-00000F00"         # Например, L01-00000F00
    PORTFOLIO_ID = 1             # ID портфеля в вашей БД
    INSTRUMENT_ID = 1            # ID инструмента SBER в вашей БД
    # =========================================

    manager = OrderManager()

    # Добавляем ордер в БД (или используйте существующий ORM-Order)
    async with AsyncSessionLocal() as session:
        order = Order(
            portfolio_id=PORTFOLIO_ID,
            instrument_id=INSTRUMENT_ID,
            side=Side.LONG,
            price=230,
            qty=1,
            filled=0,
            status=OrderStatus.NEW
        )
        session.add(order)
        await session.commit()
        orm_order_id = order.id
        print(orm_order_id)

    # Формируем данные для QUIK
    order_data = {
        "ACTION": "NEW_ORDER",
        "CLASSCODE": "TQBR",
        "SECCODE": "SBER",
        "ACCOUNT": ACCOUNT,   # Ваш торговый счёт
        "OPERATION": "B",   # Покупка
        "PRICE": "278",
        "QUANTITY": "1",
        "TRANS_ID": "5",  # Уникальный идентификатор транзакции
        "CLIENT_CODE": "1360W2"
    # Добавьте CLIENT_CODE и др. если требуется вашим брокером
    }

    # Отправляем заявку
    quik_num = await manager.place_limit_order(order_data, orm_order_id)
    print(f"Order sent, QUIK ID: {quik_num}")

    # Ждём появления QUIK ID (order_num) в маппинге
    async def wait_for_quik_id(timeout=10):
        for _ in range(timeout * 10):
            quik_id = manager._orm_to_quik.get(orm_order_id)
            if quik_id:
                return quik_id
            await asyncio.sleep(0.1)
        raise TimeoutError("QUIK ID не появился в течение таймаута")

    quik_id = await wait_for_quik_id()
    print(f"QUIK ID for cancel: {quik_id}")

    # Ждём 30 секунд
    await asyncio.sleep(30)

    # Отменяем ордер
    await manager.cancel_order(orm_order_id)
    print("Order cancel requested.")

    # Дадим время QUIK обработать отмену
    await asyncio.sleep(2)

    # Проверяем статус ордера в БД
    async with AsyncSessionLocal() as session:
        order = await session.get(Order, orm_order_id)
        print(f"Order status after cancel: {order.status}, filled: {order.filled}")

    # ВНИМАНИЕ: этот тест реально выставляет и снимает заявку на бирже! 

    # ВНИМАНИЕ: этот тест реально выставляет и снимает заявку на бирже! 