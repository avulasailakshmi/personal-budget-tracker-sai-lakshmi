const state = { accounts: [], transactions: [], budgets: [], preview: null, categoryChart: null, trendChart: null };
const $ = (selector) => document.querySelector(selector);
const money = (value) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(Number(value || 0));
const today = new Date().toISOString().slice(0, 10);
const currentMonth = today.slice(0, 7);

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || 'Something went wrong.');
  return data;
}

function notify(message, type = 'success') {
  const alert = $('#alert');
  alert.textContent = message;
  alert.className = `alert show ${type}`;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => alert.className = 'alert', 4500);
}

function jsonOptions(data, method = 'POST') {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) };
}

function showView(name) {
  document.querySelectorAll('.view').forEach(view => view.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === name));
  $(`#${name}View`).classList.add('active');
  $('#pageTitle').textContent = name === 'import' ? 'Import CSV' : name[0].toUpperCase() + name.slice(1);
  $('.sidebar').classList.remove('open');
}

function accountOptions(selected = '') {
  return `<option value="">Select account</option>` + state.accounts.map(a => `<option value="${a.id}" ${String(a.id) === String(selected) ? 'selected' : ''}>${escapeHtml(a.name)}</option>`).join('');
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
}

async function loadAccounts() {
  state.accounts = await api('/api/accounts');
  const options = accountOptions();
  ['#transactionAccount', '#transferFrom', '#transferTo'].forEach(id => $(id).innerHTML = options);
  $('#balanceTotal').textContent = money(state.accounts.reduce((sum, a) => sum + Number(a.balance), 0));
  $('#accountCards').innerHTML = state.accounts.length ? state.accounts.map(a => `
    <article class="account-card">
      <span class="type">${escapeHtml(a.type)} account</span>
      <h3>${escapeHtml(a.name)}</h3>
      <footer><strong>${money(a.balance)}</strong><button class="icon-button danger-button" onclick="removeAccount(${a.id})">Delete</button></footer>
    </article>`).join('') : '<p class="empty">No accounts yet. Add your first account.</p>';
}

async function loadTransactions() {
  const month = $('#globalMonth').value;
  state.transactions = await api(`/api/transactions?month=${month}`);
  $('#transactionCount').textContent = `${state.transactions.length} records`;
  $('#transactionRows').innerHTML = state.transactions.length ? state.transactions.map(t => {
    const normal = ['income', 'expense'].includes(t.type);
    const sign = ['income', 'transfer_in'].includes(t.type) ? '+' : '-';
    return `<tr>
      <td>${escapeHtml(t.transaction_date)}</td><td>${escapeHtml(t.type.replace('_', ' '))}</td>
      <td>${escapeHtml(t.category)}</td><td>${escapeHtml(t.account_name)}</td><td class="note-cell" title="${escapeHtml(t.note)}">${escapeHtml(t.note || '—')}</td>
      <td class="amount-${t.type}">${sign}${money(t.amount)}</td>
      <td>${normal ? `<button class="icon-button" onclick="editTransaction(${t.id})">Edit</button>` : ''}<button class="icon-button danger-button" onclick="removeTransaction(${t.id})">Delete</button></td>
    </tr>`;
  }).join('') : '<tr><td colspan="7" class="empty">No transactions for this month.</td></tr>';
}

function budgetMarkup(items, removable = true) {
  if (!items.length) return '<p class="empty">No budgets set for this month.</p>';
  return items.map(b => {
    const width = Math.min(b.percentage, 100);
    const message = b.status === 'danger' ? 'Budget reached or exceeded' : b.status === 'warning' ? 'Warning: more than 80% used' : `${Math.max(0, 80 - b.percentage).toFixed(1)}% until warning`;
    return `<div class="budget-item">
      <div class="budget-line"><strong>${escapeHtml(b.category)}</strong><span>${money(b.spent)} / ${money(b.amount)}</span></div>
      <div class="progress"><span class="${b.status}" style="width:${width}%"></span></div>
      <div class="budget-message ${b.status}">${b.percentage}% used · ${message}</div>
      ${removable ? `<button class="text-button danger-button" onclick="removeBudget(${b.id})">Remove</button>` : ''}
    </div>`;
  }).join('');
}

async function loadBudgets() {
  const month = $('#globalMonth').value;
  state.budgets = await api(`/api/budgets?month=${month}`);
  $('#budgetList').innerHTML = budgetMarkup(state.budgets, true);
  $('#dashboardBudgets').innerHTML = budgetMarkup(state.budgets, false);
}

async function loadDashboard() {
  const month = $('#globalMonth').value;
  const data = await api(`/api/dashboard?month=${month}`);
  $('#incomeTotal').textContent = money(data.income);
  $('#expenseTotal').textContent = money(data.expense);
  $('#netTotal').textContent = money(data.net);
  drawCharts(data);
}

function drawCharts(data) {
  if (!window.Chart) return setTimeout(() => drawCharts(data), 100);
  state.categoryChart?.destroy();
  state.trendChart?.destroy();
  state.categoryChart = new Chart($('#categoryChart'), {
    type: 'doughnut',
    data: { labels: data.categories.map(c => c.category), datasets: [{ data: data.categories.map(c => c.amount), backgroundColor: ['#4f6bed','#18a681','#ef7d58','#f2b84b','#8b6bc4','#4aa6c7','#d95a8a'] }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }
  });
  state.trendChart = new Chart($('#trendChart'), {
    type: 'bar',
    data: { labels: data.trend.map(t => t.month), datasets: [{ label: 'Income', data: data.trend.map(t => t.income), backgroundColor: '#18a681' }, { label: 'Expense', data: data.trend.map(t => t.expense), backgroundColor: '#ef6670' }] },
    options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } }
  });
}

async function refreshAll() {
  try {
    await loadAccounts();
    await Promise.all([loadTransactions(), loadBudgets(), loadDashboard()]);
  } catch (error) { notify(error.message, 'error'); }
}

$('#accountForm').addEventListener('submit', async event => {
  event.preventDefault();
  try {
    await api('/api/accounts', jsonOptions({ name: $('#accountName').value, type: $('#accountType').value, opening_balance: $('#openingBalance').value }));
    event.target.reset(); $('#openingBalance').value = 0; notify('Account added.'); await refreshAll();
  } catch (error) { notify(error.message, 'error'); }
});

$('#transactionForm').addEventListener('submit', async event => {
  event.preventDefault();
  const id = $('#transactionId').value;
  const payload = { type: $('#transactionType').value, amount: $('#transactionAmount').value, date: $('#transactionDate').value, category: $('#transactionCategory').value, account_id: $('#transactionAccount').value, note: $('#transactionNote').value };
  try {
    await api(id ? `/api/transactions/${id}` : '/api/transactions', jsonOptions(payload, id ? 'PUT' : 'POST'));
    resetTransactionForm(); notify(id ? 'Transaction updated.' : 'Transaction added.'); await refreshAll();
  } catch (error) { notify(error.message, 'error'); }
});

$('#transferForm').addEventListener('submit', async event => {
  event.preventDefault();
  try {
    await api('/api/transfers', jsonOptions({ from_account_id: $('#transferFrom').value, to_account_id: $('#transferTo').value, amount: $('#transferAmount').value, date: $('#transferDate').value, note: $('#transferNote').value }));
    event.target.reset(); $('#transferDate').value = today; notify('Transfer completed.'); await refreshAll();
  } catch (error) { notify(error.message, 'error'); }
});

$('#budgetForm').addEventListener('submit', async event => {
  event.preventDefault();
  try {
    await api('/api/budgets', jsonOptions({ month: $('#budgetMonth').value, category: $('#budgetCategory').value, amount: $('#budgetAmount').value }));
    $('#budgetCategory').value = ''; $('#budgetAmount').value = ''; notify('Budget saved.'); await loadBudgets();
  } catch (error) { notify(error.message, 'error'); }
});

window.editTransaction = id => {
  const t = state.transactions.find(item => item.id === id); if (!t) return;
  $('#transactionId').value = t.id; $('#transactionType').value = t.type; $('#transactionAmount').value = t.amount; $('#transactionDate').value = t.transaction_date; $('#transactionCategory').value = t.category; $('#transactionAccount').innerHTML = accountOptions(t.account_id); $('#transactionNote').value = t.note; $('#transactionFormTitle').textContent = 'Edit transaction'; $('#cancelEdit').classList.remove('hidden'); showView('transactions'); window.scrollTo({ top: 0, behavior: 'smooth' });
};
function resetTransactionForm() { $('#transactionForm').reset(); $('#transactionId').value = ''; $('#transactionDate').value = today; $('#transactionFormTitle').textContent = 'Add transaction'; $('#cancelEdit').classList.add('hidden'); }
$('#cancelEdit').addEventListener('click', resetTransactionForm);

window.removeTransaction = async id => { if (!confirm('Delete this transaction? A transfer will remove both sides.')) return; try { await api(`/api/transactions/${id}`, { method: 'DELETE' }); notify('Transaction deleted.'); await refreshAll(); } catch (e) { notify(e.message, 'error'); } };
window.removeAccount = async id => { if (!confirm('Delete this unused account?')) return; try { await api(`/api/accounts/${id}`, { method: 'DELETE' }); notify('Account deleted.'); await refreshAll(); } catch (e) { notify(e.message, 'error'); } };
window.removeBudget = async id => { if (!confirm('Remove this budget?')) return; try { await api(`/api/budgets/${id}`, { method: 'DELETE' }); notify('Budget removed.'); await loadBudgets(); } catch (e) { notify(e.message, 'error'); } };

$('#previewForm').addEventListener('submit', async event => {
  event.preventDefault(); const file = $('#csvFile').files[0]; if (!file) return;
  const form = new FormData(); form.append('file', file);
  try {
    state.preview = await api('/api/import/preview', { method: 'POST', body: form }); renderPreview(state.preview); notify(`Preview loaded: ${state.preview.total_rows} rows.`);
  } catch (e) { notify(e.message, 'error'); }
});

function renderPreview(data) {
  const fields = [['date','Date'],['amount','Amount'],['type','Type'],['category','Category'],['account','Account'],['note','Note (optional)']];
  $('#mappingFields').innerHTML = fields.map(([key,label]) => `<label>${label}<select id="map_${key}"><option value="">Select column</option>${data.columns.map(c => `<option value="${escapeHtml(c)}" ${c.toLowerCase() === key ? 'selected' : ''}>${escapeHtml(c)}</option>`).join('')}</select></label>`).join('');
  $('#previewHead').innerHTML = `<tr>${data.columns.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr>`;
  $('#previewRows').innerHTML = data.rows.map(row => `<tr>${data.columns.map(c => `<td>${escapeHtml(row[c])}</td>`).join('')}</tr>`).join('');
  $('#importMapping').classList.remove('hidden'); $('#importResults').innerHTML = '';
}

$('#importButton').addEventListener('click', async () => {
  const file = $('#csvFile').files[0]; if (!file || !state.preview) return;
  const form = new FormData(); form.append('file', file);
  ['date','amount','type','category','account','note'].forEach(key => form.append(key, $(`#map_${key}`).value));
  try {
    const result = await api('/api/import', { method: 'POST', body: form });
    $('#importResults').innerHTML = `<div class="result-box"><strong>${result.imported} imported</strong> · ${result.duplicates_skipped} duplicates skipped${result.errors.length ? `<div class="error-list"><p>${result.errors.length} invalid rows:</p>${result.errors.map(e => `<div>Row ${e.row}: ${escapeHtml(e.error)}</div>`).join('')}</div>` : '<p>No invalid rows.</p>'}</div>`;
    notify('CSV import finished.'); await refreshAll();
  } catch (e) { notify(e.message, 'error'); }
});

document.querySelectorAll('.nav-item').forEach(button => button.addEventListener('click', () => showView(button.dataset.view)));
document.querySelectorAll('[data-go]').forEach(button => button.addEventListener('click', () => showView(button.dataset.go)));
$('#menuButton').addEventListener('click', () => $('.sidebar').classList.toggle('open'));
$('#globalMonth').addEventListener('change', async event => { $('#budgetMonth').value = event.target.value; await Promise.all([loadTransactions(), loadBudgets(), loadDashboard()]); });

$('#globalMonth').value = currentMonth; $('#budgetMonth').value = currentMonth; $('#transactionDate').value = today; $('#transferDate').value = today; refreshAll();

