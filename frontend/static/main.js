// JavaScript logic extracted from legacy server.py HTML_PAGE
// Due to length, content retained as-is.

// ---------------- Tabs switching ---------------------------
// ---------------- Tabs switching ---------------------------
const TAB_NAMES = {1:'asset_1',2:'asset_2',3:'order',4:'assets_codes',5:'pair_arbitrage',6:'accounts_codes'};

function activate(tab){
    document.querySelectorAll('.tab-content').forEach(e=>e.classList.remove('active'));
    document.getElementById('tab'+tab).classList.add('active');
    document.getElementById('page_title').textContent = TAB_NAMES[tab] || '';
    localStorage.setItem('active_tab', tab);
    if(typeof syncSetting==='function') syncSetting('active_tab', tab);
}
document.getElementById('btnTab1').onclick = ()=>activate(1);
document.getElementById('btnTab2').onclick = ()=>activate(2);
document.getElementById('btnTab3').onclick = ()=>activate(3);
document.getElementById('btnTab4').onclick = ()=>activate(4);
document.getElementById('btnTab5').onclick = ()=>activate(5);
document.getElementById('btnTab6').onclick = ()=>activate(6);

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

// Общий обработчик ответов от backend для одиночных и парных ордеров
const handleWsOrderMessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if(msg.type==='order_reply'){
        document.getElementById('ord_result').textContent = JSON.stringify(msg,null,2);
        return;
    }
    if(msg.type==='pair_order_reply'){
        const rowIdx = msg.row_id;
        const ok = msg.ok;
        const row = pairsTbody.rows[rowIdx];
        if(!row) return;
        row._inFlight=false;
        if(ok){
            // обновляем exec_qty
            const execQtyCell = cellById(row,'exec_qty');
            const prevQty = parseInt(execQtyCell.textContent)||0;
            const newQty = prevQty+1;
            execQtyCell.textContent = newQty.toString();
            // exec_price (среднее) – используем текущий hit_price
            const hit = parseFloat(cellById(row,'hit_price').textContent)||0;
            const execPriceCell = cellById(row,'exec_price');
            const prevPrice = parseFloat(execPriceCell.textContent)||0;
            const newPrice = prevQty===0? hit : ((prevPrice*prevQty + hit)/newQty);
            execPriceCell.textContent = newPrice ? newPrice.toFixed(4): '';
            // пересчёт leaves_qty
            updateLeaves(row);
            // auto-stop
            const leaves = parseInt(cellById(row,'leaves_qty').textContent)||0;
            if(leaves<=0){
                const chk = cellById(row,'started').querySelector('input');
                chk.checked=false;
                cellById(row,'error').textContent='Bot stopped because leaves_qty is 0';
            }
        } else {
            // ошибка – останавливаем бота
            const chk = cellById(row,'started').querySelector('input');
            chk.checked=false;
            cellById(row,'error').textContent = msg.message || 'Order error';
        }
        savePairsTable();
        // Немедленно проверяем возможность взять следующий лот
        checkRowForTrade(row);
    }
};

function ensureWsOrderAndSend(payload){
    if(!wsOrder||wsOrder.readyState!==1){
        wsOrder = new WebSocket(`ws://${location.host}/ws`);
        wsOrder.onopen = () => wsOrder.send(JSON.stringify(payload));
        wsOrder.onmessage = handleWsOrderMessage;
        wsOrder.onerror = console.error;
    } else {
        wsOrder.send(JSON.stringify(payload));
    }
}

// Disable PRICE input for market orders
const typeSel = document.getElementById('ord_type');
const priceInp = document.getElementById('ord_price');
function togglePrice(){ priceInp.disabled = typeSel.value === 'M'; }
typeSel.onchange = togglePrice;
togglePrice();

btnSend.onclick = () => {
    const classcode = document.getElementById('ord_class').value.trim();
    const seccode   = document.getElementById('ord_sec').value.trim();
    const account   = document.getElementById('ord_account').value.trim();
    const client    = document.getElementById('ord_client').value.trim();
    const comment   = document.getElementById('ord_comment').value.trim();
    const side      = document.getElementById('ord_side').value;
    const ordType   = typeSel.value; // 'L' or 'M'
    const priceStr  = priceInp.value;
    const priceVal  = parseFloat(priceStr);
    const qty       = parseInt(document.getElementById('ord_qty').value);

    if(!classcode||!seccode||!client||!qty){alert('Fill CLASSCODE, SECCODE, CLIENT, QUANTITY');return;}
    if(ordType==='L' && !priceStr){alert('Fill PRICE for limit order');return;}

    // Формируем client_code с комментариям: client//comment  или client/
    const clientCombined = comment ? `${client}//${comment}` : `${client}/`;

    const payload = {action:'send_order', class_code:classcode, sec_code:seccode, account:account, client_code:clientCombined, operation:side, order_type:ordType, quantity:qty };
    if(ordType==='L'){ payload.price = priceVal; }


    ensureWsOrderAndSend(payload);
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

function attachEditableHandlers(row, tableType){
    row.querySelectorAll('td[contenteditable="true"]').forEach(td=>{
        if(td.dataset.value===undefined){ td.dataset.value = (td.textContent||'').trim(); }
        td.addEventListener('keydown', (e)=>{
            if(e.key==='Enter'){
                e.preventDefault();
                const newVal = (td.textContent||'').trim();
                td.textContent = newVal;
                td.dataset.value = newVal;
                if(tableType==='pairs'){
                    const r = row; savePairsTable(); updateHitPrice(r); updateLeaves(r); checkRowForTrade(r);
                } else if(tableType==='assets'){
                    // сначала коммитим строку в БД
                    const tr = td.closest('tr');
                    ensureRowPersisted('assets', tr).then(()=>{ saveAssetsTable(); });
                    return td.blur();
                } else if(tableType==='accounts'){
                    const tr = td.closest('tr');
                    ensureRowPersisted('accounts', tr).then(()=>{ saveAccountsTable(); });
                    return td.blur();
                }
                td.blur();
            }
        });
        td.addEventListener('blur', ()=>{
            const accepted = td.dataset.value||'';
            const current = (td.textContent||'').trim();
            if(current!==accepted){ td.textContent = accepted; }
            // сохраняем при уходе фокуса, если значение уже принято
            if(tableType==='assets'){
                const tr = td.closest('tr');
                ensureRowPersisted('assets', tr).then(()=>{ saveAssetsTable(); });
            } else if(tableType==='accounts'){
                const tr = td.closest('tr');
                ensureRowPersisted('accounts', tr).then(()=>{ saveAccountsTable(); });
            }
        });
    });
}

function initAssetsRow(row){
    // ensure 5 editable cells
    for(let i=0;i<5;i++){
        const cell = row.cells[i] || row.insertCell(i);
        cell.contentEditable = 'true';
        cell.dataset.value = (cell.textContent||'').trim();
    }
    attachEditableHandlers(row,'assets');
}

// Add row
document.getElementById('menu_add').onclick = ()=>{
    const row = assetsTbody.insertRow(-1);
    initAssetsRow(row);
    menu.style.display='none';
    saveAssetsTable();
};

// Delete row
document.getElementById('menu_del').onclick = ()=>{
    if(currentRow){
        const id = currentRow.dataset && currentRow.dataset.id ? parseInt(currentRow.dataset.id,10): null;
        if(id){ deleteJson(`${API_BASE}/assets/${id}`); }
        removeRowFromLocalStorage('assets', id, currentRow);
        currentRow.parentNode.removeChild(currentRow);
        currentRow = null;
        // saveAssetsTable(); // LS уже обновили точечно
    }
    menu.style.display='none';
};

 // ---------------- Accounts codes table ----------------------
 const accountsTbody = document.getElementById('accounts_tbody');
 const accountsMenu  = document.getElementById('accounts_menu');
 let currentAccRow = null;

 // Hide menu on any click outside
 document.body.addEventListener('click', ()=> accountsMenu.style.display='none');

 // Show menu on right click inside table
 document.getElementById('accounts_table').addEventListener('contextmenu', (e)=>{
     e.preventDefault();
     currentAccRow = e.target.closest('tbody tr');
     accountsMenu.style.top = e.pageY + 'px';
     accountsMenu.style.left = e.pageX + 'px';
     accountsMenu.style.display = 'block';
 });

 // Add row
 document.getElementById('accounts_add').onclick = ()=>{
     const row = accountsTbody.insertRow(-1);
     for(let i=0;i<4;i++){
         const cell = row.insertCell(i);
         cell.contentEditable = 'true';
         cell.dataset.value = (cell.textContent||'').trim();
     }
     attachEditableHandlers(row,'accounts');
     accountsMenu.style.display='none';
     saveAccountsTable();
 };

 // Delete row
 document.getElementById('accounts_del').onclick = ()=>{
     if(currentAccRow){
         const id = currentAccRow.dataset && currentAccRow.dataset.id ? parseInt(currentAccRow.dataset.id,10): null;
         if(id){ deleteJson(`${API_BASE}/accounts/${id}`); }
         removeRowFromLocalStorage('accounts', id, currentAccRow);
         currentAccRow.parentNode.removeChild(currentAccRow);
         currentAccRow = null;
         // saveAccountsTable(); // LS уже обновили точечно
     }
     accountsMenu.style.display='none';
 };

 // --- Autosave on each keystroke in accounts table --------------------

 function saveAccountsTable(){
     const rows = Array.from(accountsTbody.rows).map(r=>Array.from(r.cells).map(c=>c.textContent));
     localStorage.setItem('accounts_table', JSON.stringify(rows));
 }

 function restoreAccountsTable(){
     const data = localStorage.getItem('accounts_table');
     if(!data) return;
     let rows;
     try { rows = JSON.parse(data);}catch(e){ console.error(e); return; }
     accountsTbody.innerHTML='';
     rows.forEach(item=>{
         const row = accountsTbody.insertRow(-1);
         const cells = Array.isArray(item)
             ? item
             : [item.alias||'', '', item.account_number||'', item.client_code||''];
         if(item && item.id) row.dataset.id = String(item.id);
         cells.forEach(cellText=>{
             const cell = row.insertCell(-1);
             cell.textContent = cellText;
             cell.contentEditable='true';
             cell.dataset.value = String(cellText||'').trim();
         });
         attachEditableHandlers(row,'accounts');
     });
 }

 // Изменения принимаются по Enter в ячейке

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

function updateLeaves(row){
    const tgt = parseInt(cellById(row,'target_qty').textContent)||0;
    const exec = parseInt(cellById(row,'exec_qty').textContent)||0;
    const leaves = tgt - exec;
    cellById(row,'leaves_qty').textContent = leaves>0? leaves.toString(): (tgt? '0':'');
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
    if(window._assetIdMap && window._assetIdMap[systemCode]){
        const a = window._assetIdMap[systemCode];
        return {classcode:a.class_code, seccode:a.sec_code, price_step:a.price_step};
    }
    // fallback to LocalStorage (offline cache)
    const data = localStorage.getItem('assets_table');
    if(!data) return null;
    try{
        const rows = JSON.parse(data);
        const r = rows.find(x=>x[0]===systemCode);
        return r? {classcode:r[2], seccode:r[3], price_step:r[4]}: null;
    }catch(_){ return null; }
}

function lookupAccount(alias){
    if(window._accountIdMap && window._accountIdMap[alias]){
        const acc = window._accountIdMap[alias];
        return {account: acc.account_number, client: acc.client_code};
    }
    // fallback LocalStorage
    const data = localStorage.getItem('accounts_table');
    if(!data) return null;
    try{
        const rows = JSON.parse(data);
        const r = rows.find(x=>x[0]===alias);
        return r? {account:r[2], client:r[3]}: null;
    }catch(_){ return null; }
}

function decimalsFromStep(step){
    if(!step) return 2;
    const s = step.toString();
    const idx = s.indexOf('.')
    return idx>=0 ? (s.length-idx-1) : 0;
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
    const makeReadonly = (value='')=>{ const td=document.createElement('td'); td.textContent=value; return td; };
    const makeSelect = (val)=>{ const td=document.createElement('td'); const s=document.createElement('select'); s.innerHTML='<option value="BUY">BUY</option><option value="SELL">SELL</option>'; s.value=val; td.appendChild(s); return [td,s]; };

    let sel1, sel2, cb;

    order.forEach((colId, idx)=>{
        let td;
        switch(colId){
            case 'asset_1': td = makeEditable(data?data[0]:''); break;
            case 'asset_2': td = makeEditable(data?data[1]:''); break;
            case 'account_1': td = makeEditable(data?data[2]:''); break;
            case 'account_2': td = makeEditable(data?data[3]:''); break;
            case 'side_1': [td,sel1] = makeSelect(data? (data[4] || 'BUY') :'BUY'); break;
            case 'side_2': [td,sel2] = makeSelect(data? (data[5] || 'BUY') :'BUY'); break;
            case 'qty_ratio_1': td = makeEditable(data?data[6]:''); break;
            case 'qty_ratio_2': td = makeEditable(data?data[7]:''); break;
            case 'price_ratio_1': td = makeEditable(data?data[8]:''); break;
            case 'price_ratio_2': td = makeEditable(data?data[9]:''); break;
            case 'price': td = makeEditable(data?data[10]:''); break;
            case 'target_qty': td = makeEditable(data?data[11]:''); break;
            case 'exec_price': td = makeReadonly(data? data[12]||'' : ''); break;
            case 'exec_qty': td = makeReadonly(data? data[13]||'' : '0'); break;
            case 'leaves_qty': td = makeReadonly(data? data[14]||'' : ''); break;
            case 'strategy_name': td = makeEditable(data?data[15]:''); break;
            case 'price_1': td = document.createElement('td'); td.textContent = data? data[16]||'' : ''; break;
            case 'price_2': td = document.createElement('td'); td.textContent = data? data[17]||'' : ''; break;
            case 'hit_price': td = document.createElement('td'); td.textContent = data? data[18]||'' : ''; break;
            case 'get_mdata':
                td = document.createElement('td');
                cb = document.createElement('input'); cb.type='checkbox'; cb.checked = data? !!data[19] : false; td.appendChild(cb);
                break;
            case 'reset':
                td = document.createElement('td');
                const btn = document.createElement('button'); btn.textContent='Reset'; td.appendChild(btn);
                btn.addEventListener('click', ()=>{ cellById(row,'exec_price').textContent=''; cellById(row,'exec_qty').textContent='0'; updateLeaves(row); savePairsTable(); });
                break;
            case 'started':
                td = document.createElement('td');
                const chk = document.createElement('input'); chk.type='checkbox'; chk.checked = data? !!data[21] : false; td.appendChild(chk);
                chk.addEventListener('change', ()=>{
                    if(chk.checked){
                        // включаем торговлю: очищаем ошибку и сбрасываем внутренние флаги
                        cellById(row,'error').textContent='';
                        row._inFlight = false;
                    } else {
                        // выключаем торговлю
                        row._inFlight = false;
                    }
                    savePairsTable();
                });
                break;
            case 'error': td = document.createElement('td'); td.textContent = data? data[22]||'' : ''; break;
            default:
                td = document.createElement('td');
        }
        row.appendChild(td);
    });

    // listeners (ввод принимается по Enter; см. attachEditableHandlers)
    attachEditableHandlers(row,'pairs');
    if(sel1) sel1.addEventListener('change', savePairsTable);
    if(sel2) sel2.addEventListener('change', savePairsTable);
    if(cb){
        cb.addEventListener('change', ()=>{ savePairsTable(); if(cb.checked){ startRowFeeds(row);} else { stopRowFeeds(row);} });
        if(cb.checked) row._pendingStart = true;
    }

    // initial hit price
    updateHitPrice(row);
    return row;
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
        const id = currentPairRow.dataset && currentPairRow.dataset.id ? parseInt(currentPairRow.dataset.id,10): null;
        if(id){ deleteJson(`${API_BASE}/pairs/${id}`); }
        closeRowWs(currentPairRow);
        removeRowFromLocalStorage('pairs', id, currentPairRow);
        currentPairRow.parentNode.removeChild(currentPairRow);
        currentPairRow = null;
        // savePairsTable(); // LS уже обновили точечно
    }
    pairsMenu.style.display='none';
};

function savePairsTable(){
    const COLS = ['asset_1','asset_2','account_1','account_2','side_1','side_2','qty_ratio_1','qty_ratio_2','price_ratio_1','price_ratio_2','price','target_qty','exec_price','exec_qty','leaves_qty','strategy_name','price_1','price_2','hit_price','get_mdata','reset','started','error'];
    const rows = Array.from(pairsTbody.rows).map(r=>{
        return COLS.map(col=>{
            const cell = cellById(r,col);
            if(!cell) return '';
            if(col.startsWith('side_')){
                return cell.querySelector('select').value;
            }
            if(col==='get_mdata' || col==='started'){
                return cell.querySelector('input').checked;
            }
            if(col==='reset'){
                return '';
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
    rows.forEach(item=>{
        if(Array.isArray(item)){
            addPairsRow(item);
        } else if(item && typeof item==='object'){
            const arr = [
                item.asset_1||'', item.asset_2||'', item.account_1||'', item.account_2||'', item.side_1||'BUY', item.side_2||'BUY',
                String(item.qty_ratio_1??''), String(item.qty_ratio_2??''), String(item.price_ratio_1??''), String(item.price_ratio_2??''), String(item.price??''),
                String(item.target_qty??''), String(item.exec_price??''), String(item.exec_qty??'0'), String(item.leaves_qty??''), item.strategy_name||'',
                String(item.price_1??''), String(item.price_2??''), String(item.hit_price??''), !!item.get_mdata, '', !!item.started, item.error||''
            ];
            const r = addPairsRow(arr);
            if(item.id) r.dataset.id = String(item.id);
        }
    });
    // после восстановления данных восстановим ширины столбцов
    restorePairsWidths();
}

// On-the-fly input
pairsTbody.addEventListener('input', e=>{ if(e.target.closest('td')) savePairsTable(); });

// ------------- Trading helpers ----------------------------
function checkRowForTrade(row){
    if(!cellById(row,'started').querySelector('input').checked) return; // выключено
    if(row._inFlight) return; // ждём предыдущий ответ

    const side1 = cellById(row,'side_1').querySelector('select').value;
    const priceTarget = parseFloat(cellById(row,'price').textContent);
    if(isNaN(priceTarget)) return;
    const hit = parseFloat(cellById(row,'hit_price').textContent);
    if(isNaN(hit)) return;

    const trigger = (side1==='BUY') ? (hit<=priceTarget) : (hit>=priceTarget);
    const leaves = parseInt(cellById(row,'leaves_qty').textContent)||0;

    if(trigger && leaves>0){
        sendPairOrder(row);
    }
}

function sendPairOrder(row){
    row._inFlight = true;
    const alias1 = cellById(row,'asset_1').textContent.trim();
    const alias2 = cellById(row,'asset_2').textContent.trim();
    const cfg1 = lookupClassSec(alias1) || {};
    const cfg2 = lookupClassSec(alias2) || {};
    const acc1 = lookupAccount(cellById(row,'account_1').textContent.trim()) || {};
    const acc2 = lookupAccount(cellById(row,'account_2').textContent.trim()) || {};

    const payload = {
        action:'send_pair_order',
        row_id: Array.from(pairsTbody.rows).indexOf(row),
        class_code_1: cfg1.classcode, sec_code_1: cfg1.seccode,
        class_code_2: cfg2.classcode, sec_code_2: cfg2.seccode,
        side_1 : cellById(row,'side_1').querySelector('select').value,
        side_2 : cellById(row,'side_2').querySelector('select').value,
        qty_ratio_1: parseFloat(cellById(row,'qty_ratio_1').textContent)||0,
        qty_ratio_2: parseFloat(cellById(row,'qty_ratio_2').textContent)||0,
        account_1: acc1.account, client_code_1: acc1.client,
        account_2: acc2.account, client_code_2: acc2.client,
    };
    // отправляем через общий wsOrder (создан ранее)
    ensureWsOrderAndSend(payload);
}

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
    const decimals = decimalsFromStep(cfg.price_step);
    if(!qty){ return; }

    const ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = ()=>{
        ws.send(JSON.stringify({action:'start', class_code:cfg.classcode, sec_code:cfg.seccode}));
    };
    ws.onmessage = (ev)=>{
        const msg = JSON.parse(ev.data);
        if(msg.orderbook){
            const price = calcAvgPrice(msg.orderbook, qty, side==='BUY');
            cellById(row, idx===1? 'price_1':'price_2').textContent = price ? price.toFixed(decimals): '';
            updateHitPrice(row);
            checkRowForTrade(row);
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
    // Ensure a colgroup is present for reliable column width control
    let colgroup = table.querySelector('colgroup');
    if(!colgroup){
        colgroup = document.createElement('colgroup');
        const thsInit = table.querySelectorAll('thead th');
        thsInit.forEach(()=>{
            const col = document.createElement('col');
            colgroup.appendChild(col);
        });
        table.insertBefore(colgroup, table.firstElementChild); // before thead
    }
    const headers = table.querySelectorAll('thead th');
    headers.forEach(th=>{
        th.draggable = true;
        // зафиксируем текущую ширину как стартовую, чтобы ресайз был видим
        const w = th.getBoundingClientRect().width;
        if(w){ const initW = Math.max(40, Math.floor(w)); th.style.width = initW + 'px'; th.style.maxWidth = initW + 'px'; }
        th.style.minWidth = '0';
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

        // Add column resizer
        const resizer = document.createElement('div');
        resizer.className = 'col-resizer';
        th.appendChild(resizer);
        let startX = 0; let startWidth = 0;
        const onMouseMove = (ev)=>{
            const dx = ev.clientX - startX;
            const newWidth = Math.max(10, startWidth + dx);
            th.style.width = newWidth + 'px';
            th.style.maxWidth = newWidth + 'px';
            th.style.minWidth = '0';
            // apply width to all body cells too (для корректного min-content браузера)
            const idx = th.cellIndex;
            if(colgroup && colgroup.children[idx]){
                colgroup.children[idx].style.width = newWidth + 'px';
            }
            document.querySelectorAll('#pairs_table tbody tr').forEach(tr=>{
                if(tr.cells[idx]){
                    tr.cells[idx].style.width = newWidth + 'px';
                    tr.cells[idx].style.maxWidth = newWidth + 'px';
                }
            });

        };
        const onMouseUp = ()=>{
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
            document.body.classList.remove('resizing');
            th.draggable = true; // вернуть DnD колонок
            savePairsWidths();
        };
        resizer.addEventListener('mousedown', (ev)=>{
            ev.preventDefault();
            ev.stopPropagation(); // не даём стартовать DnD заголовка
            startX = ev.clientX;
            startWidth = th.getBoundingClientRect().width;
            th.draggable = false; // временно выключаем DnD
            document.body.classList.add('resizing');
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
        resizer.addEventListener('dragstart', (e)=>{ e.preventDefault(); e.stopPropagation(); });
        resizer.addEventListener('click', (e)=>{ e.preventDefault(); e.stopPropagation(); });
    });
    // При инициализации, если есть сохранённые ширины – применим
    restorePairsWidths();
    // синхронизируем ширины тела при первой загрузке
    const thsInit = table.querySelectorAll('thead th');
    const rowsInit = table.querySelectorAll('#pairs_table tbody tr');
    rowsInit.forEach(tr=>{
        thsInit.forEach((th, i)=>{
            if(tr.cells[i]) tr.cells[i].style.width = th.style.width || '';
        });
    });
}

function movePairsColumn(from, to){
    const table = document.getElementById('pairs_table');
    const colgroup = table.querySelector('colgroup');
    Array.from(table.rows).forEach(row=>{
        if(from < to){
            row.insertBefore(row.cells[from], row.cells[to].nextSibling);
        } else {
            row.insertBefore(row.cells[from], row.cells[to]);
        }
    });
    if(colgroup){
        const cols = Array.from(colgroup.children);
        const moving = cols[from];
        if(moving){
            if(from < to){
                colgroup.insertBefore(moving, cols[to+1] || null);
            } else {
                colgroup.insertBefore(moving, cols[to] || null);
            }
        }
    }
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

function savePairsWidths(){
    const widths = Array.from(document.querySelectorAll('#pairs_table thead th')).map(th=> th.getBoundingClientRect().width);
    localStorage.setItem('pairs_col_widths', JSON.stringify(widths));
    const order = Array.from(document.querySelectorAll('#pairs_table thead th')).map(th=>th.dataset.col);
    syncColumns(order,widths);
}

function restorePairsWidths(){
    const saved = localStorage.getItem('pairs_col_widths');
    if(!saved) return;
    let widths; try{ widths = JSON.parse(saved);}catch(e){ return; }
    const ths = document.querySelectorAll('#pairs_table thead th');
    const table = document.getElementById('pairs_table');
    const colgroup = table.querySelector('colgroup');
    widths.forEach((w, idx)=>{
        const width = Math.max(10, parseInt(w)||0);
        if(ths[idx]){
            ths[idx].style.width = width+'px';
            ths[idx].style.maxWidth = width+'px';
            ths[idx].style.minWidth = '0';
        }
        if(colgroup && colgroup.children[idx]){
            colgroup.children[idx].style.width = width+'px';
        }
    });
    // apply to body cells

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

function restoreAssetsTable(){
    const data = localStorage.getItem('assets_table');
    if(!data) return;
    let rows;
    try { rows = JSON.parse(data); } catch (e) { console.error(e); return; }
    assetsTbody.innerHTML='';
    rows.forEach(item=>{
        const row = assetsTbody.insertRow(-1);
        // поддерживаем объектную и массивную форму
        const cells = Array.isArray(item)
            ? item
            : [item.code||'', item.name||'', item.class_code||'', item.sec_code||'', String(item.price_step??'')];
        if(item && item.id) row.dataset.id = String(item.id);
        cells.forEach(cellText=>{
            const cell = row.insertCell(-1);
            cell.textContent = cellText;
            cell.contentEditable = 'true';
            cell.dataset.value = String(cellText||'').trim();
        });
        attachEditableHandlers(row,'assets');
    });
}

// Attach input listeners removed: изменения принимаются по Enter в ячейке

// ---------------- Backend sync (API <-> localStorage) ----------------
const API_BASE = '/api';
const DEBUG_API = true; // set false in production
async function fetchJson(url){
    try{
        DEBUG_API && console.log('[GET]', url);
        const res = await fetch(url);
        DEBUG_API && console.log('  <=', res.status);
        if(!res.ok) return null;
        const json = await res.json();
        DEBUG_API && console.log('  JSON', json);
        return json;
    }catch(e){ DEBUG_API && console.error('GET error', e); return null; }
}
async function postJson(url,obj){
    try{
        console.log('[POST]', url, obj);
        DEBUG_API && console.log('[POST]', url, obj);
        const res = await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)});
        DEBUG_API && console.log('  <=', res.status);
        if(res.status===409){ alert('Запись уже существует (409)'); return false; }
        if(!res.ok){ alert(`POST ${url} -> ${res.status}`); return false; }
        return await res.json().catch(()=>true);
    }catch(e){ DEBUG_API && console.error('POST error', e); return false; }
}
async function patchJson(url,obj,extraHeaders={}){
    try{
        console.log('[PATCH]', url, obj);
        DEBUG_API && console.log('[PATCH]', url, obj, extraHeaders);
        const res = await fetch(url,{method:'PATCH',headers:{'Content-Type':'application/json',...extraHeaders},body:JSON.stringify(obj)});
        DEBUG_API && console.log('  <=', res.status);
        if(res.status===409){ alert('Конфликт при обновлении (409)'); return false; }
        if(!res.ok){ alert(`PATCH ${url} -> ${res.status}`); return false; }
        // Пытаемся вернуть JSON-ответ, если он есть (FastAPI возвращает PairRead)
        try{
            const json = await res.json();
            DEBUG_API && console.log('  JSON', json);
            return json;
        }catch(_){
            return true; // 204 No Content или пустой ответ
        }
    }catch(e){ DEBUG_API && console.error('PATCH error', e); return false; }
}
async function deleteJson(url){
    try{
        console.log('[DELETE]', url);
        const res = await fetch(url,{method:'DELETE'});
        if(!res.ok){ console.warn('DELETE failed', res.status); alert(`DELETE ${url} -> ${res.status}`); }
        return res.ok;
    }catch(e){ console.warn('DELETE error', e); return false; }
}
if(DEBUG_API) console.log('DEBUG_API enabled');
// ==== Helper HTTP methods reused ====
// ---------------------------------------------------------------------
// ==== SYNC-10: push changes to server on every save ===================
async function backendSync(){
    // Assets
    try{
        const server = await fetchJson(`${API_BASE}/assets`);
        if(server===null) throw new Error('no server');
        // Сохраняем как пришло (включая id)
        localStorage.setItem('assets_table', JSON.stringify(server));
        // build in-memory map for fast lookup and deletes
        window._assetIdMap = Object.fromEntries(server.map(a=>[a.code,a]));
        // дополнительно: универсальный кэш по ключу code||__id_<id>
        window._assetsByCode = Object.fromEntries((server||[]).map(a=>[(a.code||`__id_${a.id}`), a]));
    }catch(_){}
    // Accounts
    try{
        const server = await fetchJson(`${API_BASE}/accounts`);
        if(server===null) throw new Error('no server');
        localStorage.setItem('accounts_table', JSON.stringify(server));
        window._accountIdMap = Object.fromEntries(server.map(a=>[a.alias,a]));
        window._accountsByAlias = Object.fromEntries((server||[]).map(a=>[(a.alias||`__id_${a.id}`), a]));
    }catch(_){}
    // Columns (order & widths)
    try{
        const cols = await fetchJson(`${API_BASE}/columns`);
        if(cols!==null){
            if(cols.length){
                cols.sort((a,b)=> a.position - b.position);
                const order = cols.map(c=>c.name);
                const widths = cols.map(c=>c.width||0);
                localStorage.setItem('pairs_col_order', JSON.stringify(order));
                localStorage.setItem('pairs_col_widths', JSON.stringify(widths));
                // также сохраним полный список столбцов
                localStorage.setItem('pairs_columns', JSON.stringify(cols));
            }
        }
    }catch(_){}
    // Settings – load key-value pairs
    try{
        const settings = await fetchJson(`${API_BASE}/settings`);
        if(Array.isArray(settings)){
            settings.forEach(s=>{
                if(s.key && s.value!==undefined && s.value!==null){
                    localStorage.setItem(s.key, s.value);
                }
            });
            localStorage.setItem('settings', JSON.stringify(settings));
        }
    }catch(_){}
    // Pairs
    try{
        const server = await fetchJson(`${API_BASE}/pairs`);
        if(server===null) throw new Error('no server');
        // сохраняем как есть (включая id), даже если пусто
        localStorage.setItem('pairs_table', JSON.stringify(server));
        // build map asset1|asset2 -> pair object
        window._pairsIdMap = Object.fromEntries((server||[]).map(p=>[`${p.asset_1}|${p.asset_2}`, p]));
        // и кэш по ключу asset1|asset2|id, чтобы исключить коллизии
        window._pairsByKey = Object.fromEntries((server||[]).map(p=>[`${p.asset_1||''}|${p.asset_2||''}|${p.id}`, p]));
    }catch(_){}
}
// ---------------------------------------------------------------------

// ----- patched save functions ---------------------------------------
function saveAssetsTable(){
    const rows = Array.from(assetsTbody.rows).map(tr=>({
        id: tr.dataset.id ? parseInt(tr.dataset.id,10) : null,
        code: (tr.cells[0]?.textContent||'').trim()||'',
        name: (tr.cells[1]?.textContent||'').trim()||'',
        class_code: (tr.cells[2]?.textContent||'').trim()||'',
        sec_code: (tr.cells[3]?.textContent||'').trim()||'',
        price_step: (tr.cells[4] && tr.cells[4].textContent!==''? parseFloat(tr.cells[4].textContent): null),
    }));
    localStorage.setItem('assets_table', JSON.stringify(rows));
    syncAssets(rows);
}
function saveAccountsTable(){
    const rows = Array.from(accountsTbody.rows).map(tr=>({
        id: tr.dataset.id ? parseInt(tr.dataset.id,10) : null,
        alias: (tr.cells[0]?.textContent||'').trim()||'',
        account_number: (tr.cells[2]?.textContent||'').trim()||'',
        client_code: (tr.cells[3]?.textContent||'').trim()||'',
    }));
    localStorage.setItem('accounts_table', JSON.stringify(rows));
    syncAccounts(rows);
}
function savePairsTable(){
    const COLS = ['asset_1','asset_2','account_1','account_2','side_1','side_2','qty_ratio_1','qty_ratio_2','price_ratio_1','price_ratio_2','price','target_qty','exec_price','exec_qty','leaves_qty','strategy_name','price_1','price_2','hit_price','get_mdata','reset','started','error'];
    const rows = Array.from(pairsTbody.rows).map(tr=>{
        const obj = { id: tr.dataset.id ? parseInt(tr.dataset.id,10) : null };
        COLS.forEach(col=>{
            const cell = cellById(tr,col);
            if(!cell){ obj[col]=''; return; }
            if(col.startsWith('side_')){ obj[col] = cell.querySelector('select').value; return; }
            if(col==='get_mdata'||col==='started'){ obj[col] = cell.querySelector('input').checked; return; }
            if(col==='reset'){ obj[col] = ''; return; }
            obj[col] = cell.textContent;
        });
        return obj;
    });
    localStorage.setItem('pairs_table', JSON.stringify(rows));
    syncPairs(rows.map(r=>{
        // для совместимости с текущей syncPairs (ожидает массивы) отдадим как раньше
        return [r.asset_1,r.asset_2,r.account_1,r.account_2,r.side_1,r.side_2,r.qty_ratio_1,r.qty_ratio_2,r.price_ratio_1,r.price_ratio_2,r.price,r.target_qty,r.exec_price,r.exec_qty,r.leaves_qty,r.strategy_name,r.price_1,r.price_2,r.hit_price,r.get_mdata,'',r.started,r.error];
    }));
}
function savePairsOrder(){
    const order = Array.from(document.querySelectorAll('#pairs_table thead th')).map(th=>th.dataset.col);
    localStorage.setItem('pairs_col_order', JSON.stringify(order));
    // widths may not be known here; read current widths array
    const widths = Array.from(document.querySelectorAll('#pairs_table thead th')).map(th=> th.getBoundingClientRect().width);
    syncColumns(order,widths);
}
function savePairsWidths(){
    const widths = Array.from(document.querySelectorAll('#pairs_table thead th')).map(th=> th.getBoundingClientRect().width);
    localStorage.setItem('pairs_col_widths', JSON.stringify(widths));
    const order = Array.from(document.querySelectorAll('#pairs_table thead th')).map(th=>th.dataset.col);
    syncColumns(order,widths);
}
function saveField(el){
    const key = 'fld_'+el.id;
    const value = el.type==='checkbox'? el.checked.toString() : el.value;
    localStorage.setItem(key, value);
    syncSetting(key,value);
}
// ---------------------------------------------------------------------

// Helper sync functions (global, used by save*Table) ------------------
async function syncAssets(rows){ /* id-first, then fallback by code */
    const existing = await fetchJson(`${API_BASE}/assets`)||[];
    const byId = Object.fromEntries(existing.map(a=>[a.id, a]));
    const byCode = Object.fromEntries(existing.map(a=>[(a.code||`__id_${a.id}`), a]));
    // нормализуем вход в объекты; если rows не переданы или не массив массивов – читаем из LS
    let rowsObj = [];
    if(Array.isArray(rows) && rows.length && Array.isArray(rows[0])){
        rowsObj = rows.map(r=>({
            id: null,
            code: (r[0]||'').trim()||undefined,
            name: (r[1]||'').trim()||undefined,
            class_code: (r[2]||'').trim()||undefined,
            sec_code: (r[3]||'').trim()||undefined,
            price_step: r[4]!=='' && r[4]!==undefined ? parseFloat(r[4]) : undefined,
        }));
    } else {
        try{ rowsObj = JSON.parse(localStorage.getItem('assets_table')||'[]')||[]; }catch(_){ rowsObj=[]; }
    }
    for (const r of rowsObj){
        if(r && r.id && byId[r.id]){
            await patchJson(`${API_BASE}/assets/${r.id}`, r);
            byId[r.id] = { ...byId[r.id], ...r };
            continue;
        }
        const key = (r && r.code) ? r.code : `__id_${(r&&r.id)||crypto.randomUUID()}`;
        const ex = byCode[key];
        if(ex && ex.id){
            await patchJson(`${API_BASE}/assets/${ex.id}`, r);
            byId[ex.id] = { ...ex, ...r };
        } else {
            // Исключаем id из POST запроса
            const {id, ...postData} = r;
            const created = await postJson(`${API_BASE}/assets/`, postData);
            if(created && created.id){
                byId[created.id] = created;
                byCode[(r && r.code) ? r.code : `__id_${created.id}`] = created;
            }
        }
    }
    window._assetsByCode = Object.fromEntries(Object.values(byId).map(a => [a.code || `__id_${a.id}`, a]));
}

async function syncAccounts(rows){ /* id-first, then fallback by alias */
    const existing = await fetchJson(`${API_BASE}/accounts`)||[];
    const byId = Object.fromEntries(existing.map(a=>[a.id, a]));
    const byAlias = Object.fromEntries(existing.map(a=>[(a.alias||`__id_${a.id}`), a]));
    let rowsObj = [];
    if(Array.isArray(rows) && rows.length && Array.isArray(rows[0])){
        rowsObj = rows.map(r=>({
            id: null,
            alias: (r[0]||'').trim()||undefined,
            account_number: (r[2]||'').trim()||undefined,
            client_code: (r[3]||'').trim()||undefined,
        }));
    } else {
        try{ rowsObj = JSON.parse(localStorage.getItem('accounts_table')||'[]')||[]; }catch(_){ rowsObj=[]; }
    }
    for (const r of rowsObj){
        if(r && r.id && byId[r.id]){
            await patchJson(`${API_BASE}/accounts/${r.id}`, r);
            byId[r.id] = { ...byId[r.id], ...r };
            continue;
        }
        const key = (r && r.alias) ? r.alias : `__id_${(r&&r.id)||crypto.randomUUID()}`;
        const ex = byAlias[key];
        if(ex && ex.id){
            await patchJson(`${API_BASE}/accounts/${ex.id}`, r);
            byId[ex.id] = { ...ex, ...r };
        } else {
            // Исключаем id из POST запроса
            const {id, ...postData} = r;
            const created = await postJson(`${API_BASE}/accounts/`, postData);
            if(created && created.id){
                byId[created.id] = created;
                byAlias[(r && r.alias) ? r.alias : `__id_${created.id}`] = created;
            }
        }
    }
    window._accountsByAlias = Object.fromEntries(Object.values(byId).map(a => [a.alias || `__id_${a.id}`, a]));
}

async function syncColumns(order,widths){
    const existing = await fetchJson(`${API_BASE}/columns`)||[];
    const byName = Object.fromEntries(existing.map(c=>[c.name,c]));
    for(let i=0;i<order.length;i++){
        const name = order[i];
        const width = widths[i]||null;
        const ex = byName[name];
        if(!ex){ await postJson(`${API_BASE}/columns`,{name,position:i,width}); }
        else if(ex.position!==i||parseInt(ex.width||0)!==parseInt(width||0)){
            await patchJson(`${API_BASE}/columns/${ex.id}`,{position:i,width});
        }
    }
}

async function syncSetting(key,value){
    const existing = await fetchJson(`${API_BASE}/settings`)||[];
    const found = existing.find(s=>s.key===key);
    if(!found){ await postJson(`${API_BASE}/settings`,{key,value}); }
    else if(found.value!==value){ await patchJson(`${API_BASE}/settings/${found.id}`,{value}); }
}

async function syncPairs(rows){
    // Получаем список пар с сервера один раз – строим карту "asset1|asset2" -> {id, updated_at}
    let serverPairs = [];
    try{ serverPairs = await fetchJson(`${API_BASE}/pairs`)||[]; }catch(_){}
    const map = Object.fromEntries(serverPairs.map(p=>[`${p.asset_1}|${p.asset_2}`, p]));
    window._pairsIdMap = map; // для последующих шагов (ERR-2.2)

    // --- DELETE pairs that were removed on UI ---
    const uiKeys = new Set(rows.map(r=>`${r[0]?.trim()}|${r[1]?.trim()}`));
    for(const [k,p] of Object.entries(map)){
        if(!uiKeys.has(k)){
            await deleteJson(`${API_BASE}/pairs/${p.id}`);
            delete window._pairsIdMap[k];
        }
    }

    // --- CREATE / UPDATE current rows ---
    for(const r of rows){
        const a1 = r[0]?.trim();
        const a2 = r[1]?.trim();
        if(!a1||!a2) continue;
        const key = `${a1}|${a2}`;
        const payload = {
            asset_1: a1,
            asset_2: a2,
            account_1: r[2]?.trim()||null,
            account_2: r[3]?.trim()||null,
            side_1: r[4]||null,
            side_2: r[5]||null,
            qty_ratio_1: r[6]!==''? parseFloat(r[6]): null,
            qty_ratio_2: r[7]!==''? parseFloat(r[7]): null,
            price_ratio_1: r[8]!==''? parseFloat(r[8]): null,
            price_ratio_2: r[9]!==''? parseFloat(r[9]): null,
            price: r[10]!==''? parseFloat(r[10]): null,
            target_qty: r[11]!==''? parseInt(r[11]): null,
            exec_price: r[12]!==''? parseFloat(r[12]): null,
            exec_qty: r[13]!==''? parseInt(r[13]): 0,
            leaves_qty: r[14]!==''? parseInt(r[14]): null,
            strategy_name: r[15]?.trim()||null,
            price_1: r[16]!==''? parseFloat(r[16]): null,
            price_2: r[17]!==''? parseFloat(r[17]): null,
            hit_price: r[18]!==''? parseFloat(r[18]): null,
            get_mdata: !!r[19],
            started: !!r[21],
            error: r[22]?.trim()||null,
        };
        const payloadClean = {};
        Object.entries(payload).forEach(([k,v])=>{ if(v!==null && v!==undefined && v!=='') payloadClean[k]=v; });

        if(!map[key]){
            // create new pair
            if(!payloadClean.asset_1 || !payloadClean.asset_2){ continue; }
            const created = await postJson(`${API_BASE}/pairs/`, payloadClean);
            if(created && created.id){ map[key]=created; }
        } else {
            const id = map[key].id;
            // optimistic-lock header (optional)
            const hdr = map[key].updated_at ? {'If-Unmodified-Since': map[key].updated_at}: {};
            const patched = await patchJson(`${API_BASE}/pairs/${id}`, payloadClean, hdr);
            if(patched && patched.updated_at){ map[key].updated_at = patched.updated_at; }
        }
    }
}

// Заменяем старый обработчик загрузки на async для синхронизации с сервером
window.addEventListener('load', async ()=>{
    await backendSync();
    restoreFields();
    restorePairsOrder(); // сначала порядок колонок
    restoreAssetsTable();
    restoreAccountsTable();
    restorePairsTable(); // строки после порядка, внутри вызовет restorePairsWidths
    enablePairsDragDrop();
    Array.from(pairsTbody.rows).forEach(r=>{ if(r._pendingStart){ delete r._pendingStart; startRowFeeds(r);} });
    const savedTab = parseInt(localStorage.getItem('active_tab')||'1');
    activate(isNaN(savedTab)?1:savedTab);
});

// Коммит строки в БД (POST пустой/частичной строки, затем PATCH по id)
async function ensureRowPersisted(tableType, tr){
    if(!tr) return;
    const rowData = extractRowDataFromTr(tableType, tr);
    const id = tr.dataset.id ? parseInt(tr.dataset.id, 10) : null;
    const base = `${API_BASE}/${tableType}`;
    if(!id){
        // Если есть натуральный ключ – попробуем найти существующую запись и сделать PATCH вместо POST
        if(tableType==='assets' && rowData.code){
            const ex = window._assetsByCode && window._assetsByCode[rowData.code];
            if(ex && ex.id){
                tr.dataset.id = String(ex.id);
                await patchJson(`${base}/${ex.id}`, rowData);
                persistRowToLocalStorage(tableType, tr, { ...rowData, id: ex.id });
                return;
            }
        }
        if(tableType==='accounts' && rowData.alias){
            const ex = window._accountsByAlias && window._accountsByAlias[rowData.alias];
            if(ex && ex.id){
                tr.dataset.id = String(ex.id);
                await patchJson(`${base}/${ex.id}`, rowData);
                persistRowToLocalStorage(tableType, tr, { ...rowData, id: ex.id });
                return;
            }
        }
        // Проверяем, что есть хотя бы одно значимое поле для POST
        const hasData = Object.values(rowData).some(v => v !== null && v !== '' && v !== undefined && v !== 0);
        if(!hasData) {
            console.log('Skipping POST - no meaningful data:', rowData);
            return; // Не создаём пустые записи
        }
        
        const created = await postJson(`${base}/`, rowData);
        if(created && created.id){
            tr.dataset.id = String(created.id);
            persistRowToLocalStorage(tableType, tr, { ...rowData, id: created.id });
            if(tableType==='assets'){
                window._assetIdMap = window._assetIdMap||{};
                if(created.code){ window._assetIdMap[created.code] = created; }
            } else if(tableType==='accounts'){
                window._accountIdMap = window._accountIdMap||{};
                if(created.alias){ window._accountIdMap[created.alias] = created; }
            } else if(tableType==='pairs'){
                window._pairsIdMap = window._pairsIdMap||{};
                const key = `${created.asset_1||''}|${created.asset_2||''}`;
                window._pairsIdMap[key] = created;
            }
        }
    } else {
        const patched = await patchJson(`${base}/${id}`, rowData);
        if(patched && patched.id){
            persistRowToLocalStorage(tableType, tr, { ...rowData, id });
        }
    }
}

function extractRowDataFromTr(tableType, tr){
    if(tableType==='assets'){
        const c = tr.cells;
        const payload = {
            code: (c[0]?.textContent||'').trim() || null,
            name: (c[1]?.textContent||'').trim() || null,
            class_code: (c[2]?.textContent||'').trim() || null,
            sec_code: (c[3]?.textContent||'').trim() || null,
            price_step: (c[4] && c[4].textContent!==''? parseFloat(c[4].textContent): null),
        };
        // Для UNIQUE полей (code) - если null, то не отправляем вообще
        const clean={};
        Object.entries(payload).forEach(([k,v])=>{ 
            if(k==='code' && v===null && !tr.dataset.id) {
                // Для новых записей без id не отправляем пустой code
                return;
            }
            clean[k]=v; 
        });
        return clean;
    }
    if(tableType==='accounts'){
        const c = tr.cells;
        const payload = {
            alias: (c[0]?.textContent||'').trim() || null,
            account_number: (c[2]?.textContent||'').trim() || null,
            client_code: (c[3]?.textContent||'').trim() || null,
        };
        // Для UNIQUE полей (alias) - если null, то не отправляем вообще для новых записей
        const clean={};
        Object.entries(payload).forEach(([k,v])=>{ 
            if(k==='alias' && v===null && !tr.dataset.id) {
                // Для новых записей без id не отправляем пустой alias
                return;
            }
            clean[k]=v; 
        });
        return clean;
    }
    if(tableType==='pairs'){
        const val = (id)=>{ const cell = cellById(tr,id); if(!cell) return undefined; return cell.textContent?.trim()||undefined; };
        const num = (id)=>{ const t = (cellById(tr,id)?.textContent||'').trim(); return t===''? undefined: (id==='target_qty'||id==='exec_qty'||id==='leaves_qty'? parseInt(t): parseFloat(t)); };
        const bool = (id)=>{ const cell = cellById(tr,id); if(!cell) return undefined; const inp = cell.querySelector('input'); return inp? inp.checked: undefined; };
        const sel = (id)=>{ const cell = cellById(tr,id); if(!cell) return undefined; const s=cell.querySelector('select'); return s? s.value: undefined; };
        const payload = {
            asset_1: val('asset_1'),
            asset_2: val('asset_2'),
            account_1: val('account_1'),
            account_2: val('account_2'),
            side_1: sel('side_1'),
            side_2: sel('side_2'),
            qty_ratio_1: num('qty_ratio_1'),
            qty_ratio_2: num('qty_ratio_2'),
            price_ratio_1: num('price_ratio_1'),
            price_ratio_2: num('price_ratio_2'),
            price: num('price'),
            target_qty: num('target_qty'),
            exec_price: num('exec_price'),
            exec_qty: num('exec_qty'),
            leaves_qty: num('leaves_qty'),
            strategy_name: val('strategy_name'),
            price_1: num('price_1'),
            price_2: num('price_2'),
            hit_price: num('hit_price'),
            get_mdata: bool('get_mdata'),
            started: bool('started'),
            error: val('error'),
        };
        const clean={}; Object.entries(payload).forEach(([k,v])=>{ if(v!==undefined) clean[k]=v; });
        return clean;
    }
    return {};
}

function persistRowToLocalStorage(tableType, tr, obj){
    const key = tableType==='assets'? 'assets_table': tableType==='accounts'? 'accounts_table': 'pairs_table';
    let arr=[]; try{ arr = JSON.parse(localStorage.getItem(key)||'[]'); }catch(_){ arr=[]; }
    const tbody = tableType==='assets'? assetsTbody: tableType==='accounts'? accountsTbody: pairsTbody;
    const idx = Array.from(tbody.rows).indexOf(tr);
    if(idx>=0){ arr[idx] = obj; localStorage.setItem(key, JSON.stringify(arr)); }
}

// Helper: remove row from LS by id (preferred) or by index fallback
function removeRowFromLocalStorage(tableType, id, tr){
    const key = tableType==='assets'? 'assets_table' : tableType==='accounts'? 'accounts_table' : 'pairs_table';
    let arr=[]; try{ arr = JSON.parse(localStorage.getItem(key)||'[]'); }catch(_){ arr=[]; }
    if(id){
        // objects or arrays – if objects present, filter by id; if arrays, fall back to index
        if(arr.length && typeof arr[0]==='object' && arr[0]!==null && !Array.isArray(arr[0])){
            arr = arr.filter(x=> !x || x.id!==id);
        } else if(tr){
            const tbody = tableType==='assets'? assetsTbody: tableType==='accounts'? accountsTbody: pairsTbody;
            const idx = Array.from(tbody.rows).indexOf(tr);
            if(idx>=0){ arr.splice(idx,1); }
        }
    } else if(tr){
        const tbody = tableType==='assets'? assetsTbody: tableType==='accounts'? accountsTbody: pairsTbody;
        const idx = Array.from(tbody.rows).indexOf(tr);
        if(idx>=0){ arr.splice(idx,1); }
    }
    localStorage.setItem(key, JSON.stringify(arr));
}
