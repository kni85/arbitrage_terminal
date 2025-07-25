from __future__ import annotations

import asyncio
from typing import Optional, Tuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from backend.quik_connector.core.quik_connector import QuikConnector
from backend.quik_connector.db.database import AsyncSessionLocal

app = FastAPI(title="QUIK Quotes GUI")

# ---------------------------------------------------------------------------
# Встраиваем простую HTML-страницу (без шаблонов), JS внутри
# ---------------------------------------------------------------------------
HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Quotes GUI</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        label { display: inline-block; width: 88px; }
        input { width: 100px; margin-right: 10px; }

        /* Order-book tables */
        .orderbook-table { border-collapse: collapse; margin-top: 18px; }
        .orderbook-table th, .orderbook-table td { border: 1px solid #aaa; padding: 4px 10px; text-align: right; font-size: 1.1em; }
        .orderbook-table th { background: #f0f0f0; }
        .orderbook-table td.price { font-weight: bold; background: #f8f8ff; }
        .orderbook-table td.buy { color: #1a7f37; }
        .orderbook-table td.sell { color: #b22222; }

        /* Generic */
        button { padding: 6px 14px; margin-right: 6px; }
        .tabs button { padding: 6px 18px; margin-right: 8px; }
        .tab-content { display: none; margin-top: 18px; }
        .tab-content.active { display: block; }

        /* Assets codes table */
        .codes-table { border-collapse: collapse; margin-top: 18px; }
        .codes-table th, .codes-table td { border: 1px solid #aaa; padding: 4px 10px; text-align: left; }
        .codes-table th { cursor: move; }

        /* Context menu */
        .context-menu { position: absolute; background: #fff; border: 1px solid #ccc; z-index: 1000; display: none; box-shadow: 2px 2px 6px rgba(0,0,0,0.2); }
        .context-menu button { display: block; width: 100%; padding: 4px 10px; border: none; background: none; text-align: left; }
        .context-menu button:hover { background: #f0f0f0; }
    </style>
</head>
<body>
    <h2 id="page_title">asset_1</h2>

    <!-- Tabs navigation -->
    <div class="tabs">
        <button id="btnTab1">asset_1</button>
        <button id="btnTab2">asset_2</button>
        <button id="btnTab3">order</button>
        <button id="btnTab4">assets_codes</button>
        <button id="btnTab5">pair_arbitrage</button>
    </div>

    <!-- Tab 1: Asset 1 quotes -->
    <div id="tab1" class="tab-content active">
        <div>
            <label>CLASSCODE:</label><input id="c1_class" value="TQBR" />
            <label>SECCODE:</label><input id="c1_sec" value="SBER" />
            <button id="c1_start">Start</button>
            <button id="c1_stop" disabled>Stop</button>
        </div>
        <div style="margin-bottom:10px;">
          <input id="c1_qty_sell" type="number" value="100" style="width:90px;"/>
          <output id="c1_avg_sell" style="width:110px;display:inline-block;text-align:right;"></output>
          <output id="c1_avg_buy" style="width:110px;display:inline-block;text-align:right;"></output>
          <input id="c1_qty_buy" type="number" value="100" style="width:90px;"/>
        </div>
        <div class="quotes">
            <table class="orderbook-table" id="c1_ob">
                <thead>
                    <tr>
                        <th>Lots (buy)</th><th>Price (buy)</th><th>Price (sell)</th><th>Lots (sell)</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
    </div>

    <!-- Tab 2: Asset 2 quotes -->
    <div id="tab2" class="tab-content">
    <div>
            <label>CLASSCODE:</label><input id="c2_class" value="TQBR" />
            <label>SECCODE:</label><input id="c2_sec" value="GAZP" />
            <button id="c2_start">Start</button>
            <button id="c2_stop" disabled>Stop</button>
        </div>
        <div style="margin-bottom:10px;">
          <input id="c2_qty_sell" type="number" value="100" style="width:90px;"/>
          <output id="c2_avg_sell" style="width:110px;display:inline-block;text-align:right;"></output>
          <output id="c2_avg_buy" style="width:110px;display:inline-block;text-align:right;"></output>
          <input id="c2_qty_buy" type="number" value="100" style="width:90px;"/>
        </div>
        <div class="quotes">
            <table class="orderbook-table" id="c2_ob">
                <thead>
                    <tr>
                        <th>Lots (buy)</th><th>Price (buy)</th><th>Price (sell)</th><th>Lots (sell)</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
    </div>

    <!-- Tab 3: Send order -->
    <div id="tab3" class="tab-content">
        <h3>Send limit order</h3>
        <div style="margin-bottom:12px;">
          <label>CLASSCODE:</label><input id="ord_class" value="TQBR" />
          <label>SECCODE:</label><input id="ord_sec" value="SBER" /><br/><br/>
          <label>ACCOUNT:</label><input id="ord_account" />
          <label>CLIENT:</label><input id="ord_client" /><br/><br/>
          <label>OPERATION:</label>
            <select id="ord_side"><option value="B">BUY</option><option value="S">SELL</option></select><br/><br/>
          <label>PRICE:</label><input id="ord_price" type="number" step="0.01" />
          <label>QUANTITY:</label><input id="ord_qty" type="number" value="100" />
        </div>
        <button id="ord_send">Send Order</button>
        <pre id="ord_result" style="margin-top:14px;background:#f8f8f8;padding:8px;"></pre>
    </div>

    <!-- Tab 4: Assets codes directory -->
    <div id="tab4" class="tab-content">
        <h3>Assets codes directory</h3>
        <table id="assets_table" class="codes-table">
            <thead>
                <tr>
                    <th>System Code</th>
                    <th>Exchange</th>
                    <th>CLASSCODE</th>
                    <th>SECCODE</th>
                </tr>
            </thead>
            <tbody id="assets_tbody"></tbody>
        </table>
    </div>

    <!-- Tab 5: Pair arbitrage -->
    <div id="tab5" class="tab-content">
        <h3>Pair arbitrage configurations</h3>
        <table id="pairs_table" class="codes-table">
            <thead>
                <tr>
                    <th data-col="asset_1">asset_1</th>
                    <th data-col="asset_2">asset_2</th>
                    <th data-col="side_1">side_1</th>
                    <th data-col="side_2">side_2</th>
                    <th data-col="qty_ratio_1">qty_ratio_1</th>
                    <th data-col="qty_ratio_2">qty_ratio_2</th>
                    <th data-col="price_ratio_1">price_ratio_1</th>
                    <th data-col="price_ratio_2">price_ratio_2</th>
                    <th data-col="strategy_name">strategy_name</th>
                    <th data-col="price_1">price_1</th>
                    <th data-col="price_2">price_2</th>
                    <th data-col="hit_price">hit_price</th>
                    <th data-col="get_mdata">get_mdata</th>
                </tr>
            </thead>
            <tbody id="pairs_tbody"></tbody>
        </table>
    </div>

    <!-- Context menu for assets table -->
    <div id="assets_menu" class="context-menu">
        <button id="menu_add">Add row</button>
        <button id="menu_del">Delete row</button>
    </div>

    <!-- Context menu for pairs table -->
    <div id="pairs_menu" class="context-menu">
        <button id="pairs_add">Add row</button>
        <button id="pairs_del">Delete row</button>
    </div>

<script>
// ---------------- Tabs switching ---------------------------
const TAB_NAMES = {1:'asset_1',2:'asset_2',3:'order',4:'assets_codes',5:'pair_arbitrage'};

function activate(tab){
    document.querySelectorAll('.tab-content').forEach(e=>e.classList.remove('active'));
    document.getElementById('tab'+tab).classList.add('active');
    document.getElementById('page_title').textContent = TAB_NAMES[tab] || '';
    localStorage.setItem('active_tab', tab);
}
document.getElementById('btnTab1').onclick = ()=>activate(1);
document.getElementById('btnTab2').onclick = ()=>activate(2);
document.getElementById('btnTab3').onclick = ()=>activate(3);
document.getElementById('btnTab4').onclick = ()=>activate(4);
document.getElementById('btnTab5').onclick = ()=>activate(5);

// ---------------- Quotes tabs factory ----------------------
function init(prefix){
let ws = null;
    const el = (id) => document.getElementById(prefix + '_' + id);

    const SUB_KEY = 'sub_' + prefix; // flag in localStorage

    function openWs(classcode, seccode){
        if(ws && (ws.readyState === 0 || ws.readyState === 1)) return; // already connecting/connected

    ws = new WebSocket(`ws://${location.host}/ws`);

    ws.onopen = () => {
            ws.send(JSON.stringify({ action: 'start', class_code: classcode, sec_code: seccode }));
            el('start').disabled = true;
            el('stop').disabled  = false;
            localStorage.setItem(SUB_KEY, JSON.stringify({classcode, seccode}));
        };

    ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
            if (msg.orderbook) {
                renderOrderbook(el('ob'), msg.orderbook);
                recalc(prefix, msg.orderbook);
            }
        };

        ws.onclose = () => {
            // If subscription flag still exists -> attempt reconnect after delay
            const saved = localStorage.getItem(SUB_KEY);
            if (saved) {
                setTimeout(() => {
                    const info = JSON.parse(saved);
                    openWs(info.classcode, info.seccode);
                }, 1000);
            } else {
                el('start').disabled = false;
                el('stop').disabled  = true;
            }
        };

        ws.onerror = (e) => console.error(e);
    }

    // --- Start button handler -----------------------------
    el('start').onclick = () => {
        const classcode = el('class').value.trim();
        const seccode   = el('sec').value.trim();
        if (!classcode || !seccode) {
            alert('Specify CLASSCODE and SECCODE');
            return;
        }
        openWs(classcode, seccode);
    };

    // --- Stop button handler ------------------------------
    el('stop').onclick = () => {
        localStorage.removeItem(SUB_KEY);
        if (ws && ws.readyState === 1) {
            ws.send(JSON.stringify({ action: 'stop' }));
            ws.close();
        }
        el('start').disabled = false;
        el('stop').disabled  = true;
    };

    // --- Restore running subscription (if any) ------------
    const savedSub = localStorage.getItem(SUB_KEY);
    if (savedSub) {
        try {
            const info = JSON.parse(savedSub);
            // restore fields if they differ
            el('class').value = info.classcode;
            el('sec').value   = info.seccode;
            openWs(info.classcode, info.seccode);
        } catch (e) { console.error(e); }
    }
}

// ------------- Order-book rendering ------------------------
function renderOrderbook(table, ob){
    const bids = (ob.bids||[]).slice().sort((a,b)=>b[0]-a[0]);
    const asks = (ob.asks||[]).slice().sort((a,b)=>a[0]-b[0]);
    const maxRows = Math.max(bids.length, asks.length, 10);
    let html = '';
    for(let i=0;i<maxRows;i++){
        const bid = bids[i]||[];
        const ask = asks[i]||[];
        html += `<tr>`+
            `<td class='buy'>${bid[1]||''}</td>`+
            `<td class='price'>${bid[0]||''}</td>`+
            `<td class='price'>${ask[0]||''}</td>`+
            `<td class='sell'>${ask[1]||''}</td>`+
            `</tr>`;
    }
    table.querySelector('tbody').innerHTML = html;
}

function recalc(prefix, ob){
  const qtySell = parseFloat(document.getElementById(prefix+'_qty_sell').value)||0;
  const qtyBuy  = parseFloat(document.getElementById(prefix+'_qty_buy').value)||0;

  const bids = (ob.bids||[]);
  const asks = (ob.asks||[]);

  const avgSell = averagePrice(bids, qtySell, false);
  const avgBuy  = averagePrice(asks, qtyBuy, true);

  document.getElementById(prefix+'_avg_sell').textContent = avgSell ? avgSell.toFixed(2) : '';
  document.getElementById(prefix+'_avg_buy').textContent  = avgBuy ?  avgBuy.toFixed(2)  : '';
}

function averagePrice(levels, qty, isBuy){
  if(qty<=0)return null;
  const sorted = levels.slice().sort((a,b)=> isBuy? a[0]-b[0]: b[0]-a[0]);
  let need=qty, cost=0;
  for(const [price,vol] of sorted){
      const exec = Math.min(vol, need);
      cost += price*exec;
      need -= exec;
      if(need<=0) break;
  }
  if(need>0) return null; // not enough volume
  return cost/qty;
}

init('c1');
init('c2');

// ---------------- Order sending ----------------------------
const btnSend = document.getElementById('ord_send');
let wsOrder = null;
btnSend.onclick = () => {
    const classcode = document.getElementById('ord_class').value.trim();
    const seccode   = document.getElementById('ord_sec').value.trim();
    const account   = document.getElementById('ord_account').value.trim();
    const client    = document.getElementById('ord_client').value.trim();
    const side      = document.getElementById('ord_side').value;
    const price     = parseFloat(document.getElementById('ord_price').value);
    const qty       = parseInt(document.getElementById('ord_qty').value);
    if(!classcode||!seccode||!price||!qty){alert('Fill CLASSCODE, SECCODE, PRICE, QUANTITY');return;}

    const payload = {action:'send_order', class_code:classcode, sec_code:seccode, account:account, client_code:client, operation:side, price:price, quantity:qty };

    if(!wsOrder||wsOrder.readyState!==1){
        wsOrder = new WebSocket(`ws://${location.host}/ws`);
        wsOrder.onopen = () => wsOrder.send(JSON.stringify(payload));
        wsOrder.onmessage = (ev) => {
            const msg = JSON.parse(ev.data);
            if(msg.type==='order_reply'){
                document.getElementById('ord_result').textContent = JSON.stringify(msg,null,2);
            }
        };
        wsOrder.onerror = console.error;
    } else {
        wsOrder.send(JSON.stringify(payload));
    }
};

// ---------------- Assets codes table ----------------------
const assetsTbody = document.getElementById('assets_tbody');
const menu = document.getElementById('assets_menu');
let currentRow = null;

// Hide menu on any click outside
document.body.addEventListener('click', ()=> menu.style.display='none');

// Show menu on right click inside table
document.getElementById('assets_table').addEventListener('contextmenu', (e)=>{
    e.preventDefault();
    // locate row (may be header <tr> which we ignore)
    currentRow = e.target.closest('tbody tr');
    menu.style.top = e.pageY + 'px';
    menu.style.left = e.pageX + 'px';
    menu.style.display = 'block';
});

// Add row
document.getElementById('menu_add').onclick = ()=>{
    const row = assetsTbody.insertRow(-1);
    for(let i=0;i<4;i++){
        const cell = row.insertCell(i);
        cell.contentEditable = 'true';
    }
    menu.style.display='none';
};

// Delete row
document.getElementById('menu_del').onclick = ()=>{
    if(currentRow){
        currentRow.parentNode.removeChild(currentRow);
        currentRow = null;
        saveAssetsTable();
    }
    menu.style.display='none';
};

// ---------------- Pair arbitrage table ----------------------
const pairsTbody = document.getElementById('pairs_tbody');
const pairsMenu  = document.getElementById('pairs_menu');
let currentPairRow = null;

// ---------- column helpers --------------------------------
function colIndexById(id){
    const ths = document.querySelectorAll('#pairs_table thead th');
    for(let i=0;i<ths.length;i++){
        if(ths[i].dataset.col===id) return i;
    }
    return -1;
}

function cellById(row,id){
    const idx = colIndexById(id);
    return idx>=0 ? row.cells[idx] : null;
}

function updateHitPrice(row){
    const p1 = parseFloat(cellById(row,'price_1').textContent)||0;
    const p2 = parseFloat(cellById(row,'price_2').textContent)||0;
    const r1 = parseFloat(cellById(row,'price_ratio_1').textContent)||0;
    const r2 = parseFloat(cellById(row,'price_ratio_2').textContent)||0;
    const hit = p1*r1 - p2*r2;
    cellById(row,'hit_price').textContent = hit ? hit.toFixed(2): '';
}

// ----- Utilities ---------------------------------------

function lookupClassSec(systemCode){
    const data = localStorage.getItem('assets_table');
    if(!data) return null;
    let rows;
    try { rows = JSON.parse(data);} catch(e){return null;}
    for(const r of rows){
        if(r[0]===systemCode){
            return {classcode:r[2], seccode:r[3]};
        }
    }
    return null;
}

function calcAvgPrice(ob, qty, isBuy){
    return averagePrice(isBuy? (ob.asks||[]): (ob.bids||[]), qty, isBuy);
}

// Store WebSocket refs per row per asset index (1 or 2)
function setRowWs(row, idx, ws){
    row._ws = row._ws||{};
    row._ws[idx] = ws;
}

function closeRowWs(row){
    if(row._ws){
        Object.values(row._ws).forEach(ws=>{ try{ ws.close(); } catch(e){} });
        row._ws = {};
    }
}

// -------------------- Add row helper --------------------
function addPairsRow(data){
    const row = pairsTbody.insertRow(-1);

    const order = Array.from(document.querySelectorAll('#pairs_table thead th')).map(th=>th.dataset.col);

    // helpers
    const makeEditable = (value='')=>{ const td=document.createElement('td'); td.contentEditable='true'; td.textContent=value; return td; };
    const makeSelect = (val)=>{ const td=document.createElement('td'); const s=document.createElement('select'); s.innerHTML='<option value="BUY">BUY</option><option value="SELL">SELL</option>'; s.value=val; td.appendChild(s); return [td,s]; };

    let sel1, sel2, cb;

    order.forEach((colId, idx)=>{
        let td;
        switch(colId){
            case 'asset_1': td = makeEditable(data?data[0]:''); break;
            case 'asset_2': td = makeEditable(data?data[1]:''); break;
            case 'side_1': [td,sel1] = makeSelect(data? data[2] || 'BUY':'BUY'); break;
            case 'side_2': [td,sel2] = makeSelect(data? data[3] || 'BUY':'BUY'); break;
            case 'qty_ratio_1': td = makeEditable(data?data[4]:''); break;
            case 'qty_ratio_2': td = makeEditable(data?data[5]:''); break;
            case 'price_ratio_1': td = makeEditable(data?data[6]:''); break;
            case 'price_ratio_2': td = makeEditable(data?data[7]:''); break;
            case 'strategy_name': td = makeEditable(data?data[8]:''); break;
            case 'price_1': td = document.createElement('td'); td.textContent = data? data[9]||'':''; break;
            case 'price_2': td = document.createElement('td'); td.textContent = data? data[10]||'':''; break;
            case 'hit_price': td = document.createElement('td'); td.textContent = data? data[11]||'':''; break;
            case 'get_mdata':
                td = document.createElement('td');
                cb = document.createElement('input'); cb.type='checkbox'; cb.checked = data? !!data[12]: false; td.appendChild(cb);
                break;
            default:
                td = document.createElement('td');
        }
        row.appendChild(td);
    });

    // listeners
    row.querySelectorAll('td[contenteditable="true"]').forEach(c=> c.addEventListener('input', ()=>{ savePairsTable(); updateHitPrice(row);}));
    if(sel1) sel1.addEventListener('change', savePairsTable);
    if(sel2) sel2.addEventListener('change', savePairsTable);
    if(cb){
        cb.addEventListener('change', ()=>{ savePairsTable(); if(cb.checked){ startRowFeeds(row);} else { stopRowFeeds(row);} });
        if(cb.checked) row._pendingStart = true;
    }

    // initial hit price
    updateHitPrice(row);
}

// Hide menu on any click outside
document.body.addEventListener('click', ()=> pairsMenu.style.display='none');

// Show menu on right click inside table
document.getElementById('pairs_table').addEventListener('contextmenu', (e)=>{
    e.preventDefault();
    currentPairRow = e.target.closest('tbody tr');
    pairsMenu.style.top = e.pageY + 'px';
    pairsMenu.style.left = e.pageX + 'px';
    pairsMenu.style.display = 'block';
});

// Add row
document.getElementById('pairs_add').onclick = ()=>{
    addPairsRow();
    pairsMenu.style.display='none';
    savePairsTable();
};

// Delete row via menu
document.getElementById('pairs_del').onclick = ()=>{
    if(currentPairRow){
        currentPairRow.parentNode.removeChild(currentPairRow);
        currentPairRow = null;
        savePairsTable();
    }
    pairsMenu.style.display='none';
};

function savePairsTable(){
    const COLS = ['asset_1','asset_2','side_1','side_2','qty_ratio_1','qty_ratio_2','price_ratio_1','price_ratio_2','strategy_name','price_1','price_2','hit_price','get_mdata'];
    const rows = Array.from(pairsTbody.rows).map(r=>{
        return COLS.map(col=>{
            const cell = cellById(r,col);
            if(!cell) return '';
            if(col.startsWith('side_')){
                return cell.querySelector('select').value;
            }
            if(col==='get_mdata'){
                return cell.querySelector('input').checked;
            }
            return cell.textContent;
        });
    });
    localStorage.setItem('pairs_table', JSON.stringify(rows));
}

function restorePairsTable(){
    const data = localStorage.getItem('pairs_table');
    if(!data) return;
    let rows;
    try { rows = JSON.parse(data); } catch (e) { console.error(e); return; }
    pairsTbody.innerHTML='';
    rows.forEach(rowData=> addPairsRow(rowData));
}

// On-the-fly input
pairsTbody.addEventListener('input', e=>{ if(e.target.closest('td')) savePairsTable(); });

// ----------- Live market data per row ----------------------

function startRowFeeds(row){
    // Asset 1
    const asset1 = cellById(row,'asset_1').textContent.trim();
    const asset2 = cellById(row,'asset_2').textContent.trim();

    const cfg1 = lookupClassSec(asset1);
    const cfg2 = lookupClassSec(asset2);

    if(cfg1) connectAsset(row,1,cfg1);
    if(cfg2) connectAsset(row,2,cfg2);
}

function stopRowFeeds(row){
    closeRowWs(row);
}

function connectAsset(row, idx, cfg){
    const side = cellById(row, idx===1 ? 'side_1' : 'side_2').querySelector('select').value;
    const qty  = parseFloat(cellById(row, idx===1 ? 'qty_ratio_1' : 'qty_ratio_2').textContent)||0;
    if(!qty){ return; }

    const ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = ()=>{
        ws.send(JSON.stringify({action:'start', class_code:cfg.classcode, sec_code:cfg.seccode}));
    };
    ws.onmessage = (ev)=>{
        const msg = JSON.parse(ev.data);
        if(msg.orderbook){
            const price = calcAvgPrice(msg.orderbook, qty, side==='BUY');
            cellById(row, idx===1? 'price_1':'price_2').textContent = price ? price.toFixed(2): '';
            updateHitPrice(row);
        }
    };
    ws.onclose = ()=>{
        // auto-reconnect if checkbox still checked
        if(cellById(row,'get_mdata').querySelector('input').checked){
            setTimeout(()=> connectAsset(row, idx, cfg), 1000);
        }
    };
    ws.onerror = console.error;
    setRowWs(row, idx, ws);
}

// ---------- Drag & drop column reorder ----------------------
function enablePairsDragDrop(){
    const table = document.getElementById('pairs_table');
    const headers = table.querySelectorAll('thead th');
    headers.forEach(th=>{
        th.draggable = true;
        th.addEventListener('dragstart', e=>{
            e.dataTransfer.setData('colIndex', th.cellIndex);
        });
        th.addEventListener('dragover', e=> e.preventDefault());
        th.addEventListener('drop', e=>{
            e.preventDefault();
            const from = parseInt(e.dataTransfer.getData('colIndex'));
            const to   = th.cellIndex;
            if(isNaN(from) || from===to) return;
            movePairsColumn(from, to);
            savePairsTable();
            savePairsOrder();
        });
    });
}

function movePairsColumn(from, to){
    const table = document.getElementById('pairs_table');
    Array.from(table.rows).forEach(row=>{
        if(from < to){
            row.insertBefore(row.cells[from], row.cells[to].nextSibling);
        } else {
            row.insertBefore(row.cells[from], row.cells[to]);
        }
    });
}

function savePairsOrder(){
    const order = Array.from(document.querySelectorAll('#pairs_table thead th')).map(th=>th.dataset.col);
    localStorage.setItem('pairs_col_order', JSON.stringify(order));
}

function restorePairsOrder(){
    const saved = localStorage.getItem('pairs_col_order');
    if(!saved) return;
    let order;
    try{ order = JSON.parse(saved);}catch(e){ return; }
    order.forEach((colId,targetIdx)=>{
        const cur = colIndexById(colId);
        if(cur>=0 && cur!==targetIdx){
            movePairsColumn(cur, targetIdx);
        }
    });
}

// ---------------- Persistence (localStorage) --------------

function saveField(el){
    const key = 'fld_'+el.id;
    if(el.type==='checkbox'){
        localStorage.setItem(key, el.checked);
    } else {
        localStorage.setItem(key, el.value);
    }
}

function restoreFields(){
    document.querySelectorAll('input, select').forEach(el=>{
        const key = 'fld_'+el.id;
        const stored = localStorage.getItem(key);
        if(stored!==null){
            if(el.type==='checkbox'){
                el.checked = stored==='true';
            }else{
                el.value = stored;
            }
        }
        // save on change
        el.addEventListener('change', ()=> saveField(el));
    });
}

function saveAssetsTable(){
    const rows = Array.from(assetsTbody.rows).map(r=>Array.from(r.cells).map(c=>c.textContent));
    localStorage.setItem('assets_table', JSON.stringify(rows));
}

function restoreAssetsTable(){
    const data = localStorage.getItem('assets_table');
    if(!data) return;
    let rows;
    try { rows = JSON.parse(data); } catch (e) { console.error(e); return; }
    assetsTbody.innerHTML='';
    rows.forEach(rowData=>{
        const row = assetsTbody.insertRow(-1);
        rowData.forEach(cellText=>{
            const cell = row.insertCell(-1);
            cell.textContent = cellText;
            cell.contentEditable = 'true';
            cell.addEventListener('input', saveAssetsTable);
        });
    });
}

// Attach input listeners to existing table cells (initially none)
assetsTbody.addEventListener('input', e=>{ if(e.target.closest('td')) saveAssetsTable(); });

// On load restore everything
window.addEventListener('load', ()=>{
    restoreFields();
    restoreAssetsTable();
    restorePairsTable();
    restorePairsOrder();
    enablePairsDragDrop();
    // Start feeds for rows marked
    Array.from(pairsTbody.rows).forEach(r=>{ if(r._pendingStart){ delete r._pendingStart; startRowFeeds(r);} });
    const savedTab = parseInt(localStorage.getItem('active_tab')||'1');
    activate(isNaN(savedTab)?1:savedTab);
});
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
        # Пробрасываем в event-loop
        bids_raw = data.get("bid") or data.get("bids") or data.get("bid_levels")
        asks_raw = data.get("ask") or data.get("asks") or data.get("offer") or data.get("offers")

        def _to_list(raw, reverse=False):
            # Преобразует в [[price, qty], ...]
            arr = []
            if isinstance(raw, (list, tuple)):
                for el in raw:
                    if isinstance(el, (list, tuple)) and len(el) >= 2:
                        arr.append([float(el[0]), float(el[1])])
                    elif isinstance(el, dict):
                        price = el.get("price") or el.get("p") or el.get("bid") or el.get("offer") or el.get("value")
                        qty = el.get("qty") or el.get("quantity") or el.get("vol") or el.get("volume")
                        if price is not None and qty is not None:
                            arr.append([float(price), float(qty)])
                arr = [x for x in arr if x[0] is not None and x[1] is not None]
            return sorted(arr, key=lambda x: x[0], reverse=reverse)

        bids = _to_list(bids_raw, reverse=True)
        asks = _to_list(asks_raw, reverse=False)

        loop.call_soon_threadsafe(
            asyncio.create_task,
            send_json_safe({
                "orderbook": {"bids": bids, "asks": asks},
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
            elif action == "send_order":
                # Формируем транзакцию NEW_ORDER
                order_data = {
                    "ACTION": "NEW_ORDER",
                    "CLASSCODE": msg.get("class_code"),
                    "SECCODE": msg.get("sec_code"),
                    "ACCOUNT": msg.get("account"),
                    "CLIENT_CODE": msg.get("client_code"),
                    "OPERATION": msg.get("operation"),  # 'B' / 'S'
                    "PRICE": str(msg.get("price")),
                    "QUANTITY": str(msg.get("quantity")),
                }

                # генерируем TRANS_ID через сервис
                from sqlalchemy.ext.asyncio import AsyncSession
                from backend.trading.order_service import get_next_trans_id
                async with AsyncSessionLocal() as db_sess:  # type: AsyncSession
                    next_id = await get_next_trans_id(db_sess)
                order_data["TRANS_ID"] = str(next_id)

                # Отправляем напрямую через connector
                resp = await connector.place_limit_order(order_data)

                await send_json_safe({"type": "order_reply", "data": resp})
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