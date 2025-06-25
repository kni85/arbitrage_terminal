from __future__ import annotations

import asyncio
from typing import Optional, Tuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from backend.quik_connector.core.quik_connector import QuikConnector

app = FastAPI(title="QUIK Quotes GUI")

# ---------------------------------------------------------------------------
# Встраиваем простую HTML-страницу (без шаблонов), JS внутри
# ---------------------------------------------------------------------------
HTML_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <title>Quotes GUI</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        label { display: inline-block; width: 88px; }
        input { width: 100px; margin-right: 10px; }
        .quotes span { display: inline-block; width: 120px; }
        button { padding: 6px 14px; margin-right: 6px; }
        .tabs button { padding: 6px 18px; margin-right: 8px; }
        .tab-content { display: none; margin-top: 18px; }
        .tab-content.active { display: block; }
    </style>
</head>
<body>
    <h2>Лучшие Bid / Ask (два инструмента)</h2>

    <!-- Навигация вкладок -->
    <div class="tabs">
        <button id="btnTab1">Инструмент 1</button>
        <button id="btnTab2">Инструмент 2</button>
    </div>

    <!-- Вкладка 1 -->
    <div id="tab1" class="tab-content active">
        <div>
            <label>CLASSCODE:</label><input id="c1_class" value="TQBR" />
            <label>SECCODE:</label><input id="c1_sec" value="SBER" />
            <button id="c1_start">Старт</button>
            <button id="c1_stop" disabled>Стоп</button>
        </div>
        <div class="quotes">
            <span><b>Bid:</b> <span id="c1_bid">---</span></span>
            <span><b>Ask:</b> <span id="c1_ask">---</span></span>
        </div>
    </div>

    <!-- Вкладка 2 -->
    <div id="tab2" class="tab-content">
        <div>
            <label>CLASSCODE:</label><input id="c2_class" value="TQBR" />
            <label>SECCODE:</label><input id="c2_sec" value="GAZP" />
            <button id="c2_start">Старт</button>
            <button id="c2_stop" disabled>Стоп</button>
        </div>
        <div class="quotes">
            <span><b>Bid:</b> <span id="c2_bid">---</span></span>
            <span><b>Ask:</b> <span id="c2_ask">---</span></span>
        </div>
    </div>

<script>
// --- переключение вкладок -------------------------------------------
function activate(tab){
    document.querySelectorAll('.tab-content').forEach(e=>e.classList.remove('active'));
    document.getElementById('tab'+tab).classList.add('active');
}
document.getElementById('btnTab1').onclick = ()=>activate(1);
document.getElementById('btnTab2').onclick = ()=>activate(2);

// --- фабрика для обработки одной вкладки ----------------------------
function init(prefix){
    let ws=null;
    const el=(id)=>document.getElementById(prefix+'_'+id);

    el('start').onclick=()=>{
        const classcode=el('class').value.trim();
        const seccode =el('sec').value.trim();
        if(!classcode||!seccode){alert('Укажите CLASSCODE и SECCODE');return;}

        ws=new WebSocket(`ws://${location.host}/ws`);
        ws.onopen=()=>{
            ws.send(JSON.stringify({action:'start',class_code:classcode,sec_code:seccode}));
            el('start').disabled=true; el('stop').disabled=false;
        };
        ws.onmessage=(ev)=>{
            const msg=JSON.parse(ev.data);
            if(msg.bid!==undefined) el('bid').textContent=msg.bid;
            if(msg.ask!==undefined) el('ask').textContent=msg.ask;
        };
        ws.onclose=()=>{el('start').disabled=false; el('stop').disabled=true;};
        ws.onerror=(e)=>console.error(e);
    };

    el('stop').onclick=()=>{ if(ws&&ws.readyState===1){ws.send(JSON.stringify({action:'stop'})); ws.close();} };
}

init('c1');
init('c2');
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:  # noqa: D401
    """Главная страница с GUI."""
    return HTMLResponse(HTML_PAGE)


@app.websocket("/ws")
async def ws_quotes(ws: WebSocket):  # noqa: D401
    await ws.accept()
    current_sub: Optional[Tuple[str, str]] = None  # (class, sec)
    loop = asyncio.get_running_loop()

    # Получаем (или создаём) singleton-коннектор «на лету», чтобы импорт приложения
    # не блокировался, когда QUIK недоступен
    connector = QuikConnector()

    async def send_json_safe(payload):  # helper-корутина
        try:
            await ws.send_json(payload)
        except Exception:
            pass

    def quote_callback(data):  # вызывается из другого потока
        # пробрасываем в event-loop
        bids_raw = data.get("bid") or data.get("bids") or data.get("bid_levels")
        asks_raw = data.get("ask") or data.get("asks") or data.get("offer") or data.get("offers")

        def _best_price(side_raw, choose_max: bool):
            """Возвращает лучшую цену из массива/структуры стакана."""
            if side_raw is None:
                return None

            # Приводим к списку элементов (list-like)
            elements = list(side_raw) if isinstance(side_raw, (list, tuple)) else [side_raw]

            prices: list[float] = []
            for el in elements:
                price = None
                # вложенный list/tuple → первый элемент
                if isinstance(el, (list, tuple)) and el:
                    price = el[0]
                elif isinstance(el, dict):
                    for key in ("price", "p", "offer", "bid", "value"):
                        if key in el:
                            price = el[key]
                            break
                elif isinstance(el, (int, float)):
                    price = el
                if price is not None:
                    prices.append(float(price))

            if not prices:
                return None
            return max(prices) if choose_max else min(prices)

        bid_val = _best_price(bids_raw, choose_max=True)
        ask_val = _best_price(asks_raw, choose_max=False)

        loop.call_soon_threadsafe(
            asyncio.create_task,
            send_json_safe({
                "bid": bid_val,
                "ask": ask_val,
                "time": data.get("time"),
            }),
        )

    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action")
            if action == "start":
                class_code = msg["class_code"].strip()
                sec_code = msg["sec_code"].strip()
                # если уже была подписка – отписываемся
                if current_sub:
                    connector.unsubscribe_quotes(*current_sub, quote_callback)
                connector.subscribe_quotes(class_code, sec_code, quote_callback)
                current_sub = (class_code, sec_code)
            elif action == "stop":
                if current_sub:
                    connector.unsubscribe_quotes(*current_sub, quote_callback)
                    current_sub = None
    except WebSocketDisconnect:
        pass
    finally:
        if current_sub:
            connector.unsubscribe_quotes(*current_sub, quote_callback)

# -----------------------------------------------------------
# Graceful shutdown: закрываем QuikConnector, чтобы потоки
# (callback_thread, quote_listener и т.д.) не держали процесс.
# -----------------------------------------------------------


@app.on_event("shutdown")
async def _on_shutdown() -> None:  # noqa: D401
    try:
        # Если коннектор создавался, корректно его закрываем.
        qc = QuikConnector._instance  # type: ignore[attr-defined]
        if qc is not None:
            qc.close()
    except Exception:  # pragma: no cover – защита от падения при выключении
        pass 