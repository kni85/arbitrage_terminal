"""WebSocket обработчики для Arbitrage Terminal."""

from __future__ import annotations

import asyncio
from typing import Optional, Tuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from db.database import AsyncSessionLocal
from backend.quik_connector.core.quik_connector import QuikConnector
from backend.trading.order_service import get_next_trans_id

router = APIRouter()


@router.websocket("/ws")
async def ws_quotes(ws: WebSocket) -> None:  # noqa: D401
    await ws.accept()
    current_sub: Optional[Tuple[str, str]] = None  # (class, sec)
    loop = asyncio.get_running_loop()
    connector = QuikConnector()

    async def send_json_safe(payload):
        try:
            await ws.send_json(payload)
        except Exception:
            pass

    def quote_callback(data):
        bids_raw = data.get("bid") or data.get("bids") or data.get("bid_levels")
        asks_raw = data.get("ask") or data.get("asks") or data.get("offer") or data.get("offers")

        def _to_list(raw, reverse=False):
            parsed = []
            if not isinstance(raw, (list, tuple)):
                return parsed
            for el in raw:
                if isinstance(el, (list, tuple)) and len(el) >= 2:
                    try:
                        parsed.append([float(el[0]), float(el[1])])
                    except (TypeError, ValueError):
                        continue
                elif isinstance(el, dict):
                    price = el.get("price") or el.get("p") or el.get("bid") or el.get("offer") or el.get("value")
                    qty = el.get("qty") or el.get("quantity") or el.get("vol") or el.get("volume")
                    try:
                        if price is not None and qty is not None:
                            parsed.append([float(price), float(qty)])
                    except (TypeError, ValueError):
                        continue
            parsed = [x for x in parsed if x[0] is not None and x[1] is not None]
            return sorted(parsed, key=lambda x: x[0], reverse=reverse)

        bids = _to_list(bids_raw, reverse=True)
        asks = _to_list(asks_raw, reverse=False)
        loop.call_soon_threadsafe(
            asyncio.create_task,
            send_json_safe({"orderbook": {"bids": bids, "asks": asks}, "time": data.get("time")}),
        )

    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action")
            if action == "start":
                class_code = msg["class_code"].strip(); sec_code = msg["sec_code"].strip()
                if current_sub:
                    connector.unsubscribe_quotes(*current_sub, quote_callback)
                connector.subscribe_quotes(class_code, sec_code, quote_callback)
                current_sub = (class_code, sec_code)
            elif action == "stop":
                if current_sub:
                    connector.unsubscribe_quotes(*current_sub, quote_callback)
                    current_sub = None
            elif action == "send_pair_order":
                try:
                    class_code_1 = msg.get("class_code_1"); sec_code_1 = msg.get("sec_code_1")
                    class_code_2 = msg.get("class_code_2"); sec_code_2 = msg.get("sec_code_2")
                    side_1 = msg.get("side_1"); side_2 = msg.get("side_2")
                    qty1 = int(msg.get("qty_ratio_1", 0)); qty2 = int(msg.get("qty_ratio_2", 0))
                    account1 = msg.get("account_1"); client1 = msg.get("client_code_1")
                    account2 = msg.get("account_2"); client2 = msg.get("client_code_2")
                    op1 = 'B' if str(side_1).upper().startswith('B') else 'S'
                    op2 = 'B' if str(side_2).upper().startswith('B') else 'S'

                    async with AsyncSessionLocal() as db_sess:
                        trans1 = await get_next_trans_id(db_sess)
                        trans2 = trans1 + 1

                    order1 = {"ACTION": "NEW_ORDER", "CLASSCODE": class_code_1, "SECCODE": sec_code_1,
                              "ACCOUNT": account1, "CLIENT_CODE": client1, "OPERATION": op1,
                              "QUANTITY": str(qty1), "PRICE": "0", "TYPE": "M", "TRANS_ID": str(trans1)}
                    order2 = {"ACTION": "NEW_ORDER", "CLASSCODE": class_code_2, "SECCODE": sec_code_2,
                              "ACCOUNT": account2, "CLIENT_CODE": client2, "OPERATION": op2,
                              "QUANTITY": str(qty2), "PRICE": "0", "TYPE": "M", "TRANS_ID": str(trans2)}
                    res1 = await connector.place_market_order(order1)
                    res2 = await connector.place_market_order(order2)
                    ok = (str(res1.get("result", "0")) != "-1") and (str(res2.get("result", "0")) != "-1")
                    msg_text = "" if ok else f"Order errors: {res1}, {res2}"
                except Exception as exc:  # pragma: no cover
                    ok = False; msg_text = str(exc)
                await send_json_safe({"type": "pair_order_reply", "row_id": msg.get("row_id"), "ok": ok, "message": msg_text})
            elif action == "send_order":
                order_type = msg.get("order_type", "L")
                order_data = {"ACTION": "NEW_ORDER", "CLASSCODE": msg.get("class_code"), "SECCODE": msg.get("sec_code"),
                              "ACCOUNT": msg.get("account"), "CLIENT_CODE": msg.get("client_code"), "OPERATION": msg.get("operation"),
                              "QUANTITY": str(msg.get("quantity"))}
                if order_type == "M":
                    order_data["PRICE"] = "0"; order_data["TYPE"] = "M"
                else:
                    order_data["PRICE"] = str(msg.get("price")); order_data["TYPE"] = "L"
                async with AsyncSessionLocal() as db_sess:
                    next_id = await get_next_trans_id(db_sess)
                order_data["TRANS_ID"] = str(next_id)
                resp = await (connector.place_market_order(order_data) if order_type == "M" else connector.place_limit_order(order_data))
                await send_json_safe({"type": "order_reply", "data": resp})
    except WebSocketDisconnect:
        pass
    finally:
        if current_sub:
            connector.unsubscribe_quotes(*current_sub, quote_callback)
