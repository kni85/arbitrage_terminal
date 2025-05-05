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
async def test_live_order_manager_sber_buy_and_cancel():
    """
    Интеграционный тест: выставление и отмена лимитного ордера на покупку SBER через реальный QUIK.
    ВНИМАНИЕ: тест реально отправляет заявку на биржу! Используйте только на тестовом/демо-счёте.
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

    # Формируем данные для QUIK
    order_data = {
        "ACTION": "NEW_ORDER",
        "CLASSCODE": "TQBR",
        "SECCODE": "SBER",
        "ACCOUNT": ACCOUNT,   # Ваш торговый счёт
        "OPERATION": "B",   # Покупка
        "PRICE": 230,
        "QUANTITY": 1,
        # Добавьте CLIENT_CODE, TRANS_ID и др. если требуется вашим брокером
    }

    # Отправляем заявку
    quik_id = await manager.place_limit_order(order_data, orm_order_id)
    print(f"Order sent, QUIK ID: {quik_id}")

    # Дадим время заявке появиться в QUIK
    await asyncio.sleep(2)

    # Снимаем заявку
    await manager.cancel_order(orm_order_id)
    print("Order cancel requested.")

    # Дадим время QUIK обработать отмену
    await asyncio.sleep(2)

    # Проверяем статус ордера в БД
    async with AsyncSessionLocal() as session:
        order = await session.get(Order, orm_order_id)
        print(f"Order status after cancel: {order.status}, filled: {order.filled}")

    # ВНИМАНИЕ: этот тест реально выставляет и снимает заявку на бирже! 

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

    # Формируем данные для QUIK
    order_data = {
        "ACTION": "NEW_ORDER",
        "CLASSCODE": "TQBR",
        "SECCODE": "SBER",
        "ACCOUNT": ACCOUNT,   # Ваш торговый счёт
        "OPERATION": "B",   # Покупка
        "PRICE": 230,
        "QUANTITY": 1,
        # Добавьте CLIENT_CODE, TRANS_ID и др. если требуется вашим брокером
    }

    # Отправляем заявку
    quik_id = await manager.place_limit_order(order_data, orm_order_id)
    print(f"Order sent, QUIK ID: {quik_id}")

    # Ждем 30 секунд
    await asyncio.sleep(30)

    # Снимаем заявку
    await manager.cancel_order(orm_order_id)
    print("Order cancel requested after 30 seconds.")

    # Дадим время QUIK обработать отмену
    await asyncio.sleep(2)

    # Проверяем статус ордера в БД
    async with AsyncSessionLocal() as session:
        order = await session.get(Order, orm_order_id)
        print(f"Order status after cancel: {order.status}, filled: {order.filled}")

    # ВНИМАНИЕ: этот тест реально выставляет и снимает заявку на бирже! 