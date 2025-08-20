"""WebSocket обработчики для Arbitrage Terminal."""

from __future__ import annotations

import asyncio
from typing import Optional, Tuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core import ws_actions as actions
from config import container

router = APIRouter()


@router.websocket("/ws")
async def ws_quotes(ws: WebSocket) -> None:  # noqa: D401
    await ws.accept()
    current_sub: Optional[Tuple[str, str]] = None  # (class, sec)
    loop = asyncio.get_running_loop()
    # Брокер-коннектор используется внутри core.ws_actions

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

    broker = container.broker()

    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action")
            if action == "start":
                class_code = msg["class_code"].strip(); sec_code = msg["sec_code"].strip()
                if current_sub:
                    actions.stop_quotes(*current_sub, quote_callback, broker=broker)
                actions.start_quotes(class_code, sec_code, quote_callback, broker=broker)
                current_sub = (class_code, sec_code)
            elif action == "stop":
                if current_sub:
                    actions.stop_quotes(*current_sub, quote_callback, broker=broker)
                    current_sub = None
            elif action == "send_pair_order":
                ok, msg_text = await actions.send_pair_order(msg, broker=broker)
                await send_json_safe({"type": "pair_order_reply", "row_id": msg.get("row_id"), "ok": ok, "message": msg_text})
            elif action == "send_order":
                resp = await actions.send_order(msg, broker=broker)
                await send_json_safe({"type": "order_reply", "data": resp})
    except WebSocketDisconnect:
        pass
    finally:
        if current_sub:
            actions.stop_quotes(*current_sub, quote_callback, broker=broker)
