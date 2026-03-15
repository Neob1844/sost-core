(function() {
  'use strict';

  var EXPLORER = 'https://explorer.sostcore.com/sost-explorer.html';

  var PAGES = [
    { title: 'Home', desc: 'SOST Protocol overview — Sovereign Stock Token', url: 'index.html', kw: 'home protocol gold pow sovereign stock token' },
    { title: 'Genesis Block', desc: 'Block zero — genesis parameters, constitutional addresses, raw data', url: 'sost-genesis.html', kw: 'genesis block zero origin first block constitutional addresses parameters verification founder vault' },
    { title: 'Technology', desc: 'ConvergenceX PoW, cASERT unified difficulty', url: 'sost-technology.html', kw: 'convergencex algorithm mining cpu asert casert difficulty pow proof work' },
    { title: 'Tokenomics', desc: 'Supply, emission, epoch decay, stocks', url: 'sost-tokenomics.html', kw: 'supply emission epoch decay stocks tokenomics monetary policy' },
    { title: 'PoPC', desc: 'Proof of Personal Custody — gold bond and escrow', url: 'sost-popc.html', kw: 'proof custody gold bond escrow model a model b popc audit slash' },
    { title: 'Gold Reserve', desc: 'Heritage Reserve, Gold Funding Vault, XAUT, PAXG', url: 'sost-gold-reserve.html', kw: 'reserve heritage funding vault xaut paxg gold metals' },
    { title: 'Foundation', desc: 'Foundation constitution and commitments', url: 'sost-foundation.html', kw: 'foundation constitution commitment governance rules' },
    { title: 'Quick Start', desc: 'Mine, build, install, wallet CLI', url: 'sost-quickstart.html', kw: 'mine start build install wallet cli quick' },
    { title: 'Getting Started', desc: 'Technical guide — node, miner, RPC', url: 'sost-getting-started.html', kw: 'technical node miner rpc getting started setup' },
    { title: 'Wallet', desc: 'Wallet operations — send, receive, keys', url: 'sost-wallet.html', kw: 'wallet send receive keys address transaction' },
    { title: 'Explorer', desc: 'Block explorer — blocks, transactions, addresses', url: 'sost-explorer.html', kw: 'explorer blocks transactions addresses search' },
    { title: 'Roadmap', desc: 'Development phases and timeline', url: 'sost-roadmap.html', kw: 'roadmap phases timeline milestones development' },
    { title: 'Whitepaper', desc: 'Technical whitepaper — full specification', url: 'sost-whitepaper.html', kw: 'whitepaper paper specification technical document' },
    { title: 'Security', desc: 'Security model, license, MIT', url: 'sost-security.html', kw: 'security license mit audit vulnerability' },
    { title: 'FAQ', desc: 'Frequently asked questions', url: 'sost-faq.html', kw: 'faq questions help answers' },
    { title: 'Community', desc: 'Telegram, BitcoinTalk, community links', url: 'sost-community.html', kw: 'community telegram btctalk social links' },
    { title: 'Contact', desc: 'Contact and support', url: 'sost-contact.html', kw: 'contact email support' },
    { title: 'Foundation Balances', desc: 'Foundation transparency and reserve balances', url: 'sost-foundation-balances.html', kw: 'balances transparency foundation audit reserve' },
    { title: 'PoPC Contracts', desc: 'Public registry of all PoPC contracts', url: 'sost-popc-contracts.html', kw: 'popc contracts registry active completed slashed bond escrow model a model b' },
    { title: 'Infrastructure', desc: 'VPS, nodes, deployment infrastructure', url: 'sost-infrastructure.html', kw: 'infrastructure vps nodes deployment server' },
    { title: 'Metals Reserve', desc: 'Multi-metal reserve — silver, platinum, palladium', url: 'sost-metals-reserve.html', kw: 'metals silver platinum palladium multi-metal reserve' },
    { title: 'BTCTalk Announcement', desc: 'Official BTCTalk ANN thread — pre-genesis draft', url: 'sost-btctalk-ann.html', kw: 'btctalk announcement ann launch genesis mining pow' },
    { title: 'Markets', desc: 'Live forex, gold prices, SOST in 21 currencies + 10 cryptos', url: 'sost-markets.html', kw: 'markets forex gold price currency exchange rates crypto bitcoin ethereum live dashboard' }
  ];

  function init() {
    var nav = document.querySelector('nav .container');
    if (!nav) return;

    var wrap = document.createElement('div');
    wrap.className = 'sost-search';
    wrap.innerHTML =
      '<button class="sost-search-toggle" aria-label="Search">' +
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
          '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>' +
        '</svg>' +
      '</button>' +
      '<div class="sost-search-box">' +
        '<input type="text" class="sost-search-input" placeholder="Search or sost1 address..." autocomplete="off" spellcheck="false">' +
        '<div class="sost-search-results"></div>' +
      '</div>';

    nav.appendChild(wrap);

    var toggle = wrap.querySelector('.sost-search-toggle');
    var box = wrap.querySelector('.sost-search-box');
    var input = wrap.querySelector('.sost-search-input');
    var results = wrap.querySelector('.sost-search-results');
    var activeIdx = -1;

    toggle.addEventListener('click', function(e) {
      e.stopPropagation();
      box.classList.toggle('open');
      if (box.classList.contains('open')) {
        input.focus();
      }
    });

    input.addEventListener('input', function() {
      var q = input.value.trim();
      activeIdx = -1;
      if (!q) { results.innerHTML = ''; results.classList.remove('visible'); return; }

      // sost1 address
      if (/^sost1[0-9a-fA-F]{40}$/i.test(q)) {
        showHint(results, 'Open address in Explorer', function() {
          window.location.href = EXPLORER + '#address=' + q;
        });
        return;
      }
      if (/^sost1/i.test(q) && q.length < 45) {
        showHint(results, 'Type full sost1 address (45 chars)...', null);
        return;
      }

      // block height
      if (/^\d+$/.test(q)) {
        showHint(results, 'Open block #' + q + ' in Explorer', function() {
          window.location.href = EXPLORER + '#block=' + q;
        });
        return;
      }

      // hex hash (64 chars)
      if (/^[0-9a-fA-F]{64}$/.test(q)) {
        showHint(results, 'Look up hash in Explorer', function() {
          window.location.href = EXPLORER + '#hash=' + q;
        });
        return;
      }

      // text search
      var words = q.toLowerCase().split(/\s+/);
      var matches = PAGES.filter(function(p) {
        var hay = (p.title + ' ' + p.desc + ' ' + p.kw).toLowerCase();
        for (var i = 0; i < words.length; i++) {
          if (hay.indexOf(words[i]) === -1) return false;
        }
        return true;
      });

      if (matches.length === 0) {
        results.innerHTML = '<div class="sost-search-item sost-search-empty">No results</div>';
      } else {
        results.innerHTML = matches.map(function(m, i) {
          return '<a class="sost-search-item" href="' + m.url + '" data-idx="' + i + '">' +
            '<span class="sost-search-title">' + m.title + '</span>' +
            '<span class="sost-search-desc">' + m.desc + '</span>' +
          '</a>';
        }).join('');
      }
      results.classList.add('visible');
    });

    input.addEventListener('keydown', function(e) {
      var items = results.querySelectorAll('a.sost-search-item');
      if (!items.length) {
        if (e.key === 'Enter') {
          var btn = results.querySelector('.sost-search-item');
          if (btn && btn._onclick) btn._onclick();
        }
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        activeIdx = Math.min(activeIdx + 1, items.length - 1);
        updateActive(items, activeIdx);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        activeIdx = Math.max(activeIdx - 1, 0);
        updateActive(items, activeIdx);
      } else if (e.key === 'Enter' && activeIdx >= 0 && items[activeIdx]) {
        e.preventDefault();
        items[activeIdx].click();
      } else if (e.key === 'Escape') {
        input.value = '';
        results.innerHTML = '';
        results.classList.remove('visible');
        box.classList.remove('open');
      }
    });

    document.addEventListener('click', function(e) {
      if (!wrap.contains(e.target)) {
        results.innerHTML = '';
        results.classList.remove('visible');
        box.classList.remove('open');
      }
    });
  }

  function showHint(container, text, onclick) {
    var div = document.createElement('div');
    div.className = 'sost-search-item' + (onclick ? ' sost-search-action' : ' sost-search-empty');
    div.textContent = text;
    if (onclick) {
      div._onclick = onclick;
      div.addEventListener('click', onclick);
      div.style.cursor = 'pointer';
    }
    container.innerHTML = '';
    container.appendChild(div);
    container.classList.add('visible');
  }

  function updateActive(items, idx) {
    for (var i = 0; i < items.length; i++) {
      items[i].classList.toggle('active', i === idx);
    }
  }

  // inject styles
  var style = document.createElement('style');
  style.textContent =
    '.sost-search { position: relative; display: flex; align-items: center; margin-left: 8px; }' +
    '.sost-search-toggle { background: none; border: 1px solid var(--border-dim, #1a1a1a); color: var(--text-dim, #64748b); cursor: pointer; padding: 6px 8px; border-radius: 4px; display: flex; align-items: center; transition: all 0.2s; }' +
    '.sost-search-toggle:hover { color: var(--text-primary, #e2e8f0); border-color: var(--border-med, #2a2a2a); }' +
    '.sost-search-box { position: absolute; right: 0; top: 100%; margin-top: 8px; width: 320px; display: none; }' +
    '.sost-search-box.open { display: block; }' +
    '.sost-search-input { width: 100%; background: var(--bg-card, #0a0a0a); border: 1px solid var(--red-dim, #8b1a22); color: var(--text-primary, #e2e8f0); font-family: inherit; font-size: 12px; padding: 8px 12px; border-radius: 4px; outline: none; }' +
    '.sost-search-input:focus { border-color: var(--red-primary, #fb010d); box-shadow: 0 0 0 1px var(--red-glow, #fb010d33); }' +
    '.sost-search-input::placeholder { color: var(--text-muted, #475569); }' +
    '.sost-search-results { display: none; margin-top: 4px; background: var(--bg-card, #0a0a0a); border: 1px solid var(--border-med, #2a2a2a); border-radius: 4px; max-height: 320px; overflow-y: auto; }' +
    '.sost-search-results.visible { display: block; }' +
    '.sost-search-item { display: block; padding: 8px 12px; text-decoration: none; border-bottom: 1px solid var(--border-dim, #1a1a1a); transition: background 0.15s; }' +
    '.sost-search-item:last-child { border-bottom: none; }' +
    '.sost-search-item:hover, .sost-search-item.active { background: var(--bg-hover, #111111); }' +
    '.sost-search-action { color: var(--red-bright, #ff2d3b); }' +
    '.sost-search-action:hover { background: var(--bg-hover, #111111); }' +
    '.sost-search-empty { color: var(--text-muted, #475569); font-size: 12px; }' +
    '.sost-search-title { display: block; color: var(--text-primary, #e2e8f0); font-size: 12px; font-weight: 500; }' +
    '.sost-search-desc { display: block; color: var(--text-dim, #64748b); font-size: 11px; margin-top: 2px; }' +
    '@media (min-width: 769px) { .sost-search-box { width: 340px; } }' +
    '@media (max-width: 768px) { .sost-search-box { width: calc(100vw - 48px); right: -12px; } }';
  document.head.appendChild(style);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
