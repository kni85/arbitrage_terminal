"""Бизнес-операции, которые раньше были реализованы прямо в WebSocket-хендлере.
Сюда вынесены функции подписки на котировки и отправки ордеров, чтобы
backend.api.ws только маршрутизировал сообщения.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, Tuple

from infra.quik_adapter import QuikBrokerAdapter
from core.broker import Broker
# for TRANS_ID generation and mapping
from db.database import AsyncSessionLocal
from backend.trading.order_service import get_next_trans_id
from config import container

logger = logging.getLogger(__name__)

# Тип callback котировки
QuoteCallback = Callable[[Dict[str, Any]], None]


# ---------------------------------------------------------------------------
# Подписка на котировки
# ---------------------------------------------------------------------------

_default_broker: Broker = QuikBrokerAdapter()


def start_quotes(class_code: str, sec_code: str, cb: QuoteCallback, broker: Broker | None = None) -> None:  # noqa: D401
    """Подписаться на стакан L2."""
    (broker or _default_broker).subscribe_quotes(class_code, sec_code, cb)


def stop_quotes(class_code: str, sec_code: str, cb: QuoteCallback, broker: Broker | None = None) -> None:  # noqa: D401
    (broker or _default_broker).unsubscribe_quotes(class_code, sec_code, cb)


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

    broker = broker or _default_broker
    if order_type == "M":
        return await broker.place_market_order(order)  # type: ignore[return-value]
    return await broker.place_limit_order(order)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Отправка парного ордера (арбитраж)
# ---------------------------------------------------------------------------

async def send_pair_order(data: Dict[str, Any], broker: Broker | None = None) -> Tuple[bool, str]:  # noqa: D401
    """Отправляет два синхронных рыночных ордера (парный арбитраж)."""
    try:
        # Безопасно получаем обязательные поля
        class_code_1 = data.get("class_code_1")
        sec_code_1 = data.get("sec_code_1")
        class_code_2 = data.get("class_code_2")
        sec_code_2 = data.get("sec_code_2")
        side_1 = data.get("side_1")
        side_2 = data.get("side_2")
        
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

        # зарегистрируем оба trans_id, чтобы callbacks нашлись
        try:
            om = container.order_manager()
            om._register_trans_mapping(trans1, -1)
            om._register_trans_mapping(trans2, -1)
        except Exception:
            pass
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
        broker = broker or _default_broker
        res1 = await broker.place_market_order(order1)
        res2 = await broker.place_market_order(order2)
        ok = (str(res1.get("result", "0")) != "-1") and (str(res2.get("result", "0")) != "-1")
        msg_text = "" if ok else f"Order errors: {res1}, {res2}"
        return ok, msg_text
    except Exception as exc:  # pragma: no cover
        return False, str(exc)


def force_quote_request(class_code: str, sec_code: str, callback, broker=None):
    """
    Принудительный запрос актуальных котировок для инструмента.
    Используется когда данные устарели.
    """
    try:
        if not broker:
            broker = container.broker()
        
        logger.info(f"Force requesting fresh quotes for {class_code}.{sec_code}")
        
        # Получаем текущий стакан напрямую из QUIK
        # Это гарантирует получение актуальных данных даже если стакан не изменился
        if hasattr(broker, '_quik') and broker._quik:
            quote_data = broker._quik.get_quote_level2(class_code, sec_code)
            
            if quote_data and quote_data.get('result'):
                # Добавляем временную метку для обновления md_dt (используем местное время)
                quote_data['time'] = datetime.now().isoformat()
                quote_data['class_code'] = class_code
                quote_data['sec_code'] = sec_code
                quote_data['is_force_request'] = True
                
                # Вызываем callback с полученными данными
                callback(quote_data)
                logger.info(f"Force quote received and processed for {class_code}.{sec_code}")
            else:
                logger.warning(f"Failed to get force quote for {class_code}.{sec_code}: {quote_data}")
        else:
            # Fallback: переподписка если прямой запрос недоступен
            logger.warning(f"Direct quote request not available, resubscribing for {class_code}.{sec_code}")
            broker.unsubscribe_quotes(class_code, sec_code, callback)
            broker.subscribe_quotes(class_code, sec_code, callback)
        
    except Exception as e:
        logger.exception(f"Error in force_quote_request for {class_code}.{sec_code}: {e}")
