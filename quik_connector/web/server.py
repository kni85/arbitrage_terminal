from __future__ import annotations

import asyncio
from typing import Optional, Tuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from quik_connector.core.quik_connector import QuikConnector

app = FastAPI(title="QUIK Quotes GUI")
connector = QuikConnector()

# ---------------------------------------------------------------------------
# Встраиваем простую HTML-страницу (без шаблонов), JS внутри
# ---------------------------------------------------------------------------
HTML_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <title>QUOTES GUI</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        label { display: inline-block; width: 90px; }
        input { width: 100px; margin-right: 10px; }
        #quotes { margin-top: 20px; font-size: 1.2em; }
        #quotes span { display: inline-block; width: 120px; }
        button { padding: 6px 14px; margin-right: 6px; }
    </style>
</head>
<body>
    <h2>Подписка на лучшие bid / ask</h2>
    <div>
        <label>CLASSCODE:</label>
        <input id="classcode" value="TQBR" />
        <label>SECCODE:</label>
        <input id="seccode" value="SBER" />
        <button id="start">Старт</button>
        <button id="stop" disabled>Стоп</button>
    </div>
    <div id="quotes">
        <span><b>Bid:</b> <span id="bid">---</span></span>
        <span><b>Ask:</b> <span id="ask">---</span></span>
    </div>

<script>
let ws = null;
const btnStart = document.getElementById('start');
const btnStop  = document.getElementById('stop');

function log(msg){ console.log(msg); }

btnStart.onclick = () => {
    const classcode = document.getElementById('classcode').value.trim();
    const seccode   = document.getElementById('seccode').value.trim();
    if(!classcode || !seccode){ alert('Укажите CLASSCODE и SECCODE'); return; }

    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => {
        ws.send(JSON.stringify({action: 'start', class_code: classcode, sec_code: seccode}));
        btnStart.disabled = true;
        btnStop.disabled  = false;
    };
    ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if(msg.bid !== undefined){ document.getElementById('bid').textContent = msg.bid; }
        if(msg.ask !== undefined){ document.getElementById('ask').textContent = msg.ask; }
    };
    ws.onclose = () => {
        btnStart.disabled = false;
        btnStop.disabled  = true;
    };
    ws.onerror = (e) => { console.error(e); };
};

btnStop.onclick = () => {
    if(ws && ws.readyState === 1){ ws.send(JSON.stringify({action: 'stop'})); ws.close(); }
};
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

    async def send_json_safe(payload):  # helper-корутина
        try:
            await ws.send_json(payload)
        except Exception:
            pass

    def quote_callback(data):  # вызывается из другого потока
        # пробрасываем в event-loop
        loop.call_soon_threadsafe(asyncio.create_task, send_json_safe({
            "bid": data.get("bid"),
            "ask": data.get("ask"),
            "time": data.get("time"),
        }))

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