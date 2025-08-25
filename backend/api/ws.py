"""WebSocket обработчики для Arbitrage Terminal."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional, Tuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core import ws_actions as actions
from config import container

router = APIRouter()
logger = logging.getLogger(__name__)


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
        
        # Получаем информацию об инструменте из данных
        class_code = data.get("class_code") or data.get("classcode")
        sec_code = data.get("sec_code") or data.get("seccode")

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
        # Всегда добавляем timestamp - либо из данных QUIK, либо текущее время
        timestamp = data.get("time") or datetime.utcnow().isoformat()
        
        # Формируем ответ с котировками
        response = {
            "orderbook": {"bids": bids, "asks": asks}, 
            "time": timestamp
        }
        
        # Добавляем информацию об инструменте если есть
        if class_code:
            response["class_code"] = class_code
        if sec_code:
            response["sec_code"] = sec_code
            
        loop.call_soon_threadsafe(
            asyncio.create_task,
            send_json_safe(response),
        )

    broker = container.broker()

    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action")
            if action == "start":
                class_code_raw = msg.get("class_code")
                sec_code_raw = msg.get("sec_code")
                
                # Проверяем, что поля не None и не пустые
                if not class_code_raw or not sec_code_raw:
                    await send_json_safe({"type": "error", "message": "Missing class_code or sec_code"})
                    continue
                    
                class_code = class_code_raw.strip()
                sec_code = sec_code_raw.strip()
                
                if not class_code or not sec_code:
                    await send_json_safe({"type": "error", "message": "Empty class_code or sec_code"})
                    continue
                
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
            elif action == "force_quote":
                # Force quote request for stale market data
                class_code_raw = msg.get("class_code")
                sec_code_raw = msg.get("sec_code")
                
                if not class_code_raw or not sec_code_raw:
                    await send_json_safe({"type": "error", "message": "Missing class_code or sec_code for force_quote"})
                    continue
                    
                class_code = class_code_raw.strip()
                sec_code = sec_code_raw.strip()
                
                if not class_code or not sec_code:
                    await send_json_safe({"type": "error", "message": "Empty class_code or sec_code for force_quote"})
                    continue
                
                # Request fresh quote data
                actions.force_quote_request(class_code, sec_code, quote_callback, broker=broker)
                logger.info(f"Force quote request sent for {class_code}.{sec_code}")
            else:
                await send_json_safe({"type": "error", "message": f"Unknown action: {action}"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        # Логируем ошибку и отправляем клиенту, но не падаем
        logger.exception("WebSocket error: %s", e)
        try:
            await send_json_safe({"type": "error", "message": f"Server error: {str(e)}"})
        except Exception:
            pass  # Если даже отправка ошибки не удается, просто игнорируем
    finally:
        if current_sub:
            actions.stop_quotes(*current_sub, quote_callback, broker=broker)
