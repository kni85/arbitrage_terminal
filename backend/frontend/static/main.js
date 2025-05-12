// main.js – frontend logic for strategies table

const API_BASE = '';

async function fetchStrategies() {
  const resp = await axios.get(`${API_BASE}/strategies`);
  return resp.data;
}

function fmt(val, digits = 4) {
  if (val === null || val === undefined) return '';
  return typeof val === 'number' ? val.toFixed(digits) : val;
}

function rowHtml(row) {
  return `
    <td>${row.strategy_id}</td>
    <td>${row.name || ''}</td>
    <td>${row.mode || ''}</td>
    <td>${fmt(row.spread_bid)}</td>
    <td>${fmt(row.spread_ask)}</td>
    <td>${row.position_qty ?? ''}</td>
    <td>${fmt(row.pnl, 2)}</td>
    <td class="${row.running ? 'status-running' : 'status-stopped'}">${row.running ? 'RUNNING' : 'STOPPED'}</td>
    <td>
      <button class="btn btn-sm ${row.running ? 'btn-outline-danger' : 'btn-outline-success'} action-btn"
              data-id="${row.strategy_id}" data-action="${row.running ? 'stop' : 'start'}">
        ${row.running ? 'Stop' : 'Start'}
      </button>
    </td>`;
}

function renderTable(data) {
  const tbody = document.querySelector('#tbl-strategies tbody');
  tbody.innerHTML = '';
  Object.values(data).forEach(row => {
    const tr = document.createElement('tr');
    tr.innerHTML = rowHtml(row);
    tbody.appendChild(tr);
  });
}

async function handleAction(e) {
  const btn = e.target.closest('.action-btn');
  if (!btn) return;
  const id = btn.dataset.id;
  const action = btn.dataset.action;
  try {
    await axios.post(`${API_BASE}/strategies/${id}/${action}`);
    await refresh();
  } catch (err) {
    alert('Request failed: ' + err);
  }
}

document.addEventListener('click', handleAction);

async function refresh() {
  const data = await fetchStrategies();
  renderTable(data);
}

refresh();
setInterval(refresh, 5000); 