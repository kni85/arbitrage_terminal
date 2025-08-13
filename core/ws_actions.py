"""Бизнес-операции, которые раньше были реализованы прямо в WebSocket-хендлере.
Сюда вынесены функции подписки на котировки и отправки ордеров, чтобы
backend.api.ws только маршрутизировал сообщения.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Tuple

from backend.quik_connector.core.quik_connector import QuikConnector  # type: ignore
from db.database import AsyncSessionLocal
from backend.trading.order_service import get_next_trans_id

# Тип callback котировки
QuoteCallback = Callable[[Dict[str, Any]], None]


# ---------------------------------------------------------------------------
# Подписка на котировки
# ---------------------------------------------------------------------------

_connector = QuikConnector()


def start_quotes(class_code: str, sec_code: str, cb: QuoteCallback, broker: QuikConnector | None = None) -> None:  # noqa: D401
    """Подписаться на стакан L2."""
    (broker or _connector).subscribe_quotes(class_code, sec_code, cb)


def stop_quotes(class_code: str, sec_code: str, cb: QuoteCallback, broker: QuikConnector | None = None) -> None:  # noqa: D401
    (broker or _connector).unsubscribe_quotes(class_code, sec_code, cb)


# ---------------------------------------------------------------------------
# Отправка одиночного ордера
# ---------------------------------------------------------------------------

async def send_order(data: Dict[str, Any], broker: QuikConnector | None = None) -> Dict[str, Any]:  # noqa: D401
    """Отправляет одиночный лимитный или рыночный ордер через QuikConnector."""
    order_type = data.get("order_type", "L")  # 'L' | 'M'
    order = {
        "ACTION": "NEW_ORDER",
        "CLASSCODE": data.get("class_code"),
        "SECCODE": data.get("sec_code"),
        "ACCOUNT": data.get("account"),
        "CLIENT_CODE": data.get("client_code"),
        "OPERATION": data.get("operation"),
        "QUANTITY": str(data.get("quantity")),
    }
    if order_type == "M":
        order.update({"PRICE": "0", "TYPE": "M"})
    else:
        order.update({"PRICE": str(data.get("price")), "TYPE": "L"})

    async with AsyncSessionLocal() as sess:
        next_id = await get_next_trans_id(sess)
    order["TRANS_ID"] = str(next_id)

    broker = broker or _connector
    if order_type == "M":
        return await broker.place_market_order(order)  # type: ignore[return-value]
    return await broker.place_limit_order(order)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Отправка парного ордера (арбитраж)
# ---------------------------------------------------------------------------

async def send_pair_order(data: Dict[str, Any], broker: QuikConnector | None = None) -> Tuple[bool, str]:  # noqa: D401
    """Отправляет два синхронных рыночных ордера (парный арбитраж)."""
    try:
        class_code_1, sec_code_1 = data["class_code_1"], data["sec_code_1"]
        class_code_2, sec_code_2 = data["class_code_2"], data["sec_code_2"]
        side_1, side_2 = data["side_1"], data["side_2"]
        qty1 = int(data.get("qty_ratio_1", 0))
        qty2 = int(data.get("qty_ratio_2", 0))
        account1, client1 = data.get("account_1"), data.get("client_code_1")
        account2, client2 = data.get("account_2"), data.get("client_code_2")
        op1 = "B" if str(side_1).upper().startswith("B") else "S"
        op2 = "B" if str(side_2).upper().startswith("B") else "S"
        async with AsyncSessionLocal() as sess:
            trans1 = await get_next_trans_id(sess)
            trans2 = trans1 + 1
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
        broker = broker or _connector
        res1 = await broker.place_market_order(order1)
        res2 = await broker.place_market_order(order2)
        ok = (str(res1.get("result", "0")) != "-1") and (str(res2.get("result", "0")) != "-1")
        msg_text = "" if ok else f"Order errors: {res1}, {res2}"
        return ok, msg_text
    except Exception as exc:  # pragma: no cover
        return False, str(exc)
