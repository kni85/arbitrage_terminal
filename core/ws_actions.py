"""Бизнес-операции, которые раньше были реализованы прямо в WebSocket-хендлере.
Сюда вынесены функции подписки на котировки и отправки ордеров, чтобы
backend.api.ws только маршрутизировал сообщения.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Tuple

from core.broker import Broker
# for TRANS_ID generation and mapping
from db.database import AsyncSessionLocal
from backend.trading.order_service import get_next_trans_id
from config import container

# Тип callback котировки
QuoteCallback = Callable[[Dict[str, Any]], None]


# ---------------------------------------------------------------------------
# Подписка на котировки
# ---------------------------------------------------------------------------

def _get_broker() -> Broker:
    """Ленивое получение брокера из DI-контейнера."""
    return container.broker()


def start_quotes(class_code: str, sec_code: str, cb: QuoteCallback, broker: Broker | None = None) -> None:  # noqa: D401
    """Подписаться на стакан L2."""
    (broker or _get_broker()).subscribe_quotes(class_code, sec_code, cb)


def stop_quotes(class_code: str, sec_code: str, cb: QuoteCallback, broker: Broker | None = None) -> None:  # noqa: D401
    (broker or _get_broker()).unsubscribe_quotes(class_code, sec_code, cb)


# ---------------------------------------------------------------------------
# Отправка одиночного ордера
# ---------------------------------------------------------------------------

async def send_order(data: Dict[str, Any], broker: Broker | None = None) -> Dict[str, Any]:  # noqa: D401
    """Отправляет одиночный лимитный или рыночный ордер через QuikConnector."""
    order_type = data.get("order_type", "L")  # 'L' | 'M'
    
    # Безопасно получаем количество и цену
    quantity = data.get("quantity", 0)
    price = data.get("price", 0)
    
    order = {
        "ACTION": "NEW_ORDER",
        "CLASSCODE": data.get("class_code"),
        "SECCODE": data.get("sec_code"),
        "ACCOUNT": data.get("account"),
        "CLIENT_CODE": data.get("client_code"),
        "OPERATION": data.get("operation"),
        "QUANTITY": str(quantity) if quantity is not None else "0",
    }
    if order_type == "M":
        order.update({"PRICE": "0", "TYPE": "M"})
    else:
        order.update({"PRICE": str(price) if price is not None else "0", "TYPE": "L"})

    async with AsyncSessionLocal() as sess:
        next_id = await get_next_trans_id(sess)
    order["TRANS_ID"] = str(next_id)

    # --- register mapping in OrderManager so callbacks find ORM ----
    try:
        om = container.order_manager()
        om._register_trans_mapping(next_id, -1)  # -1: no ORM row yet
    except Exception:
        pass

    broker = broker or _get_broker()
    if order_type == "M":
        return await broker.place_market_order(order)  # type: ignore[return-value]
    return await broker.place_limit_order(order)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Отправка парного ордера (арбитраж)
# ---------------------------------------------------------------------------

async def send_pair_order(data: Dict[str, Any], broker: Broker | None = None) -> Tuple[bool, str]:  # noqa: D401
    """Отправляет два синхронных рыночных ордера (парный арбитраж) и сохраняет их в БД."""
    try:
        from db.models import Order, OrderStatus, Side, Instrument, PortfolioConfig
        from sqlalchemy import select
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Безопасно получаем обязательные поля
        class_code_1 = data.get("class_code_1")
        sec_code_1 = data.get("sec_code_1")
        class_code_2 = data.get("class_code_2")
        sec_code_2 = data.get("sec_code_2")
        side_1 = data.get("side_1")
        side_2 = data.get("side_2")
        pair_id = data.get("pair_id")  # Database ID of the trading pair
        
        logger.info(f"[SEND_PAIR_ORDER] Получен запрос: pair_id={pair_id}, {sec_code_1}/{sec_code_2}")
        
        # Проверяем обязательные поля
        if not all([class_code_1, sec_code_1, class_code_2, sec_code_2, side_1, side_2]):
            missing_fields = []
            if not class_code_1: missing_fields.append("class_code_1")
            if not sec_code_1: missing_fields.append("sec_code_1") 
            if not class_code_2: missing_fields.append("class_code_2")
            if not sec_code_2: missing_fields.append("sec_code_2")
            if not side_1: missing_fields.append("side_1")
            if not side_2: missing_fields.append("side_2")
            return False, f"Missing required fields: {', '.join(missing_fields)}"
        
        qty1 = int(data.get("qty_ratio_1", 0))
        qty2 = int(data.get("qty_ratio_2", 0))
        account1, client1 = data.get("account_1"), data.get("client_code_1")
        account2, client2 = data.get("account_2"), data.get("client_code_2")
        op1 = "B" if str(side_1).upper().startswith("B") else "S"
        op2 = "B" if str(side_2).upper().startswith("B") else "S"
        
        async with AsyncSessionLocal() as sess:
            trans1 = await get_next_trans_id(sess)
            trans2 = trans1 + 1
            
            # Получаем или создаём инструменты
            stmt1 = select(Instrument).where(
                Instrument.ticker == sec_code_1,
                Instrument.board == class_code_1
            )
            result1 = await sess.execute(stmt1)
            instrument1 = result1.scalar_one_or_none()
            if not instrument1:
                instrument1 = Instrument(
                    ticker=sec_code_1, board=class_code_1, 
                    lot_size=1, price_precision=2
                )
                sess.add(instrument1)
                await sess.flush()
            
            stmt2 = select(Instrument).where(
                Instrument.ticker == sec_code_2,
                Instrument.board == class_code_2
            )
            result2 = await sess.execute(stmt2)
            instrument2 = result2.scalar_one_or_none()
            if not instrument2:
                instrument2 = Instrument(
                    ticker=sec_code_2, board=class_code_2,
                    lot_size=1, price_precision=2
                )
                sess.add(instrument2)
                await sess.flush()
            
            # Получаем или создаём дефолтный портфель
            stmt_port = select(PortfolioConfig).where(PortfolioConfig.active == True).limit(1)
            result_port = await sess.execute(stmt_port)
            portfolio = result_port.scalar_one_or_none()
            if not portfolio:
                portfolio = PortfolioConfig(
                    name="Default Portfolio",
                    config_json={},
                    active=True
                )
                sess.add(portfolio)
                await sess.flush()
            
            # Создаём записи Order в БД
            order_rec_1 = Order(
                trans_id=trans1,
                portfolio_id=portfolio.id,
                pair_id=pair_id,  # Связываем с парой
                instrument_id=instrument1.id,
                side=Side.LONG if op1 == "B" else Side.SHORT,
                price=0.0,  # Рыночная заявка
                qty=qty1,
                status=OrderStatus.NEW
            )
            order_rec_2 = Order(
                trans_id=trans2,
                portfolio_id=portfolio.id,
                pair_id=pair_id,  # Связываем с парой
                instrument_id=instrument2.id,
                side=Side.LONG if op2 == "B" else Side.SHORT,
                price=0.0,  # Рыночная заявка
                qty=qty2,
                status=OrderStatus.NEW
            )
            sess.add(order_rec_1)
            sess.add(order_rec_2)
            await sess.commit()
            
            logger.info(f"[SEND_PAIR_ORDER] Созданы Order ID={order_rec_1.id} и ID={order_rec_2.id} с pair_id={pair_id}")
            
            # Регистрируем маппинг в OrderManager
            om = container.order_manager()
            om._register_trans_mapping(trans1, order_rec_1.id)
            om._register_trans_mapping(trans2, order_rec_2.id)

        order1 = {
            "ACTION": "NEW_ORDER","CLASSCODE": class_code_1,"SECCODE": sec_code_1,
            "ACCOUNT": account1,"CLIENT_CODE": client1,"OPERATION": op1,
            "QUANTITY": str(qty1),"PRICE": "0","TYPE": "M","TRANS_ID": str(trans1),
        }
        order2 = {
            "ACTION": "NEW_ORDER","CLASSCODE": class_code_2,"SECCODE": sec_code_2,
            "ACCOUNT": account2,"CLIENT_CODE": client2,"OPERATION": op2,
            "QUANTITY": str(qty2),"PRICE": "0","TYPE": "M","TRANS_ID": str(trans2),
        }
        broker = broker or _get_broker()
        res1 = await broker.place_market_order(order1)
        res2 = await broker.place_market_order(order2)
        ok = (str(res1.get("result", "0")) != "-1") and (str(res2.get("result", "0")) != "-1")
        msg_text = "" if ok else f"Order errors: {res1}, {res2}"
        return ok, msg_text
    except Exception as exc:  # pragma: no cover
        import traceback
        traceback.print_exc()
        return False, str(exc)
