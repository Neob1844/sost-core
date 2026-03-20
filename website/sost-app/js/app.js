// SOST Protocol App — Unified Explorer + Wallet
// ================================================

const RPC_URL = '/rpc';
let rpcTimeout = 10000;
let currentTab = 'explorer';
let explorerRefreshTimer = null;
let walletState = { address: null, encrypted: null, unlocked: false };

// ==================== RPC ====================
async function rpc(method, params = []) {
  const body = JSON.stringify({ jsonrpc: '2.0', id: 1, method, params: Array.isArray(params) ? params : [params] });
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), rpcTimeout);
  try {
    const r = await fetch(RPC_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, signal: ctrl.signal });
    clearTimeout(t);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const j = await r.json();
    if (j.error) throw new Error(j.error.message || JSON.stringify(j.error));
    return j.result;
  } catch (e) {
    clearTimeout(t);
    if (e.name === 'AbortError') throw new Error('Timeout');
    throw e;
  }
}

// ==================== STATUS ====================
async function updateStatus() {
  const dot = document.getElementById('statusDot');
  const txt = document.getElementById('statusText');
  try {
    const info = await rpc('getinfo');
    dot.className = 'status-dot online';
    txt.textContent = '#' + (info.blocks || 0);
    return info;
  } catch (e) {
    dot.className = 'status-dot offline';
    txt.textContent = 'Offline';
    return null;
  }
}

// ==================== NAVIGATION ====================
function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + tab).classList.add('active');
  document.querySelector(`.nav-tab[data-tab="${tab}"]`).classList.add('active');
  if (tab === 'explorer') refreshExplorer();
  if (tab === 'wallet') refreshWallet();
}

// ==================== EXPLORER ====================
async function refreshExplorer() {
  try {
    const info = await rpc('getinfo');
    document.getElementById('exHeight').textContent = '#' + (info.blocks || 0);
    document.getElementById('exDiff').textContent = info.difficulty ? info.difficulty.toFixed(4) : '—';

    // Supply from subsidy calculation
    const supply = info.total_supply || info.supply || '—';
    document.getElementById('exSupply').textContent = typeof supply === 'number' ? supply.toFixed(2) : supply;

    // Peers
    document.getElementById('exPeers').textContent = info.connections || 0;

    // Load recent blocks
    await loadRecentBlocks(info.blocks || 0);
  } catch (e) {
    document.getElementById('exHeight').textContent = '—';
    document.getElementById('exDiff').textContent = '—';
  }
}

async function loadRecentBlocks(height) {
  const list = document.getElementById('blockList');
  if (!list || height < 1) return;
  let html = '';
  const count = Math.min(20, height);
  for (let h = height; h > height - count && h >= 0; h--) {
    try {
      const hash = await rpc('getblockhash', [String(h)]);
      const blk = await rpc('getblock', [hash]);
      const ago = formatTimeAgo(blk.time);
      const hashShort = hash.slice(0, 8) + '...' + hash.slice(-6);
      html += `<div class="block-item fade-in">
        <span class="block-height">${h}</span>
        <span class="block-hash">${hashShort}</span>
        <span class="block-time">${ago}</span>
      </div>`;
    } catch (e) { break; }
  }
  list.innerHTML = html || '<div class="notice">No blocks loaded</div>';
}

async function searchExplorer() {
  const q = document.getElementById('searchInput').value.trim();
  const out = document.getElementById('searchResults');
  if (!q) { out.innerHTML = ''; return; }
  out.innerHTML = '<div class="notice">Searching...</div>';
  try {
    // Try as block height
    if (/^\d+$/.test(q)) {
      const hash = await rpc('getblockhash', [q]);
      const blk = await rpc('getblock', [hash]);
      out.innerHTML = `<div class="card"><div class="card-label">BLOCK #${q}</div>
        <div style="font-size:11px;color:var(--text2);word-break:break-all">Hash: ${hash}<br>Time: ${new Date(blk.time*1000).toISOString()}<br>Difficulty: ${blk.bits_q}<br>Txs: ${blk.tx_count || blk.transactions?.length || '?'}</div></div>`;
      return;
    }
    // Try as address
    if (q.startsWith('sost1') && q.length === 45) {
      const info = await rpc('getaddressinfo', [q]);
      out.innerHTML = `<div class="card"><div class="card-label">ADDRESS</div>
        <div style="font-size:11px;word-break:break-all;color:var(--cyan)">${q}</div>
        <div style="margin-top:8px">Balance: <b>${info.balance}</b> SOST · ${info.utxo_count} UTXOs</div></div>`;
      return;
    }
    // Try as block hash
    const blk = await rpc('getblock', [q]);
    out.innerHTML = `<div class="card"><div class="card-label">BLOCK #${blk.height}</div>
      <div style="font-size:11px;color:var(--text2)">Time: ${new Date(blk.time*1000).toISOString()}</div></div>`;
  } catch (e) {
    out.innerHTML = `<div class="notice">Not found: ${e.message}</div>`;
  }
}

// ==================== WALLET ====================
const SAT = 100000000;
const WALLET_KEY = 'sost_wallet';

function formatSost(stocks) { return (stocks / SAT).toFixed(8); }

async function refreshWallet() {
  const raw = localStorage.getItem(WALLET_KEY);
  if (!raw) {
    document.getElementById('walletMain').classList.add('hidden');
    document.getElementById('walletEmpty').classList.remove('hidden');
    return;
  }
  document.getElementById('walletEmpty').classList.add('hidden');
  document.getElementById('walletMain').classList.remove('hidden');

  try {
    const parsed = JSON.parse(raw);
    const addr = parsed.address || parsed.addr || '';
    if (!addr) return;
    document.getElementById('wAddr').textContent = addr;
    document.getElementById('wAddrRecv').textContent = addr;

    // QR
    try {
      if (typeof QRCode !== 'undefined') {
        const canvas = document.getElementById('wQr');
        QRCode.toCanvas(canvas, addr, { width: 180, margin: 2, color: { dark: '#000', light: '#fff' } });
      }
    } catch (e) { /* no QR lib */ }

    // Balance
    const [info, addrInfo] = await Promise.all([rpc('getinfo'), rpc('getaddressinfo', [addr])]);
    const chainHeight = info.blocks || 0;
    const utxos = addrInfo.utxos || [];
    let total = 0, spendable = 0, immature = 0;
    utxos.forEach(u => {
      const amt = Math.round((u.amount || 0) * SAT);
      total += amt;
      const confs = chainHeight - (u.height || 0);
      if (u.coinbase && confs < 1000) { immature += amt; } else { spendable += amt; }
    });

    document.getElementById('wBalance').textContent = formatSost(total);
    const brkEl = document.getElementById('wBreakdown');
    if (immature > 0) {
      brkEl.classList.remove('hidden');
      brkEl.innerHTML = `<span class="balance-spendable">SPENDABLE: ${formatSost(spendable)}</span>
        <span class="balance-immature">IMMATURE: ${formatSost(immature)}</span>`;
    } else {
      brkEl.classList.add('hidden');
    }

    // Maturity info
    const matEl = document.getElementById('wMaturity');
    const immatureUtxos = utxos.filter(u => u.coinbase && (chainHeight - (u.height||0)) < 1000);
    if (immatureUtxos.length > 0) {
      const earliest = Math.min(...immatureUtxos.map(u => (u.height||0) + 1000));
      const left = earliest - chainHeight;
      matEl.classList.remove('hidden');
      matEl.textContent = `Height #${chainHeight} · Matures at #${earliest} · ~${left} blocks (~${Math.ceil(left*10/60)}h)`;
    } else {
      matEl.classList.add('hidden');
    }

    // UTXOs
    const uList = document.getElementById('wUtxoList');
    if (utxos.length > 0) {
      uList.innerHTML = utxos.map(u => {
        const txid = u.txid || '';
        const confs = chainHeight - (u.height || 0);
        const mature = !u.coinbase || confs >= 1000;
        const status = u.coinbase ? `cb ${confs}/1000` : `${confs} confs`;
        return `<div class="utxo-row" style="border-left:3px solid ${mature?'var(--green)':'var(--orange)'}">
          <span class="utxo-txid"><a href="../sost-explorer.html?search=${txid}" target="_blank">${txid.slice(0,6)}...${txid.slice(-6)}:${u.vout||0}</a></span>
          <span class="utxo-amt">${u.amount} SOST</span>
          <span class="utxo-status">${status}</span>
        </div>`;
      }).join('');
    } else {
      uList.innerHTML = '<div class="notice">No UTXOs</div>';
    }
  } catch (e) {
    document.getElementById('wBalance').textContent = '—';
    document.getElementById('wMaturity').textContent = 'RPC: ' + e.message;
    document.getElementById('wMaturity').classList.remove('hidden');
  }
}

function copyAddress() {
  const addr = document.getElementById('wAddrRecv').textContent;
  navigator.clipboard.writeText(addr).catch(() => {});
}

// ==================== SETTINGS ====================
function openSettings() { document.getElementById('settingsOverlay').classList.add('open'); }
function closeSettings() { document.getElementById('settingsOverlay').classList.remove('open'); }

// ==================== HELPERS ====================
function formatTimeAgo(ts) {
  const s = Math.floor(Date.now() / 1000 - ts);
  if (s < 60) return s + 's ago';
  if (s < 3600) return Math.floor(s / 60) + 'm ago';
  if (s < 86400) return Math.floor(s / 3600) + 'h ago';
  return Math.floor(s / 86400) + 'd ago';
}

// ==================== INIT ====================
async function init() {
  // Register service worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js').catch(() => {});
  }

  // Tab navigation
  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
  });

  // Settings
  document.getElementById('settingsBtn').addEventListener('click', openSettings);
  document.getElementById('settingsClose').addEventListener('click', closeSettings);
  document.getElementById('settingsOverlay').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeSettings();
  });

  // Search
  document.getElementById('searchBtn').addEventListener('click', searchExplorer);
  document.getElementById('searchInput').addEventListener('keydown', e => { if (e.key === 'Enter') searchExplorer(); });

  // Copy
  document.getElementById('copyBtn')?.addEventListener('click', copyAddress);

  // Refresh buttons
  document.getElementById('refreshExplorer')?.addEventListener('click', refreshExplorer);
  document.getElementById('refreshWallet')?.addEventListener('click', refreshWallet);

  // Initial load
  await updateStatus();
  switchTab('explorer');

  // Auto-refresh
  setInterval(updateStatus, 30000);
  setInterval(() => { if (currentTab === 'explorer') refreshExplorer(); }, 60000);
}

init();
