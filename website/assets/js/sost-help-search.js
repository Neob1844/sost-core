// SOST Help Center — client-side search.
//
// Loads the static index from data/public_help_index.json and the
// full payload from data/public_help_full.json (for detailed answers).
// Ranks results by token overlap against the query. Pure stdlib —
// no network calls beyond the two same-origin fetches and no
// external dependencies.
//
// The page is functional with JavaScript disabled too: it falls back
// to a static FAQ list rendered server-side. This script enhances
// search and category filtering when JS is available.

(function () {
  'use strict';

  if (window.__sostHelpSearchInit) return;
  window.__sostHelpSearchInit = true;

  var _index = null;
  var _full = null;
  var _byId = {};

  function tokenize(text) {
    if (!text) return [];
    var parts = String(text).toLowerCase().split(/[^a-z0-9]+/);
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      if (parts[i] && parts[i].length > 1) out.push(parts[i]);
    }
    return out;
  }

  function score(entry, query, qTokens) {
    var s = 0;
    var hay = (entry.title + ' ' + entry.short_answer + ' ' + entry.category).toLowerCase();
    if (query && hay.indexOf(query) !== -1) s += 5;
    var tokens = entry.tokens || [];
    var tset = {};
    for (var i = 0; i < tokens.length; i++) tset[tokens[i]] = true;
    for (var j = 0; j < qTokens.length; j++) {
      if (tset[qTokens[j]]) s += 2;
      if (entry.title.toLowerCase().indexOf(qTokens[j]) !== -1) s += 3;
      if (entry.category.toLowerCase().indexOf(qTokens[j]) !== -1) s += 1;
    }
    return s;
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function renderCard(entry) {
    var full = _byId[entry.item_id] || {};
    var detailed = full.detailed_answer || entry.short_answer;
    var warnings = full.warnings || [];
    var sources = full.source_refs || [];
    var html = [
      '<article class="help-card">',
      '  <header class="help-card-head">',
      '    <span class="help-cat">' + escapeHtml(entry.category) + '</span>',
      '    <h3>' + escapeHtml(entry.title) + '</h3>',
      '  </header>',
      '  <p class="help-short">' + escapeHtml(entry.short_answer) + '</p>',
      '  <details><summary>Read full answer</summary>',
      '    <p class="help-detail">' + escapeHtml(detailed) + '</p>',
    ];
    if (warnings.length) {
      html.push('<ul class="help-warnings">');
      for (var i = 0; i < warnings.length; i++) {
        html.push('  <li>&#9888; ' + escapeHtml(warnings[i]) + '</li>');
      }
      html.push('</ul>');
    }
    if (sources.length) {
      html.push('<p class="help-sources">References: ');
      var refs = [];
      for (var k = 0; k < sources.length; k++) {
        refs.push('<code>' + escapeHtml(sources[k]) + '</code>');
      }
      html.push(refs.join(' &middot; ') + '</p>');
    }
    html.push('  </details>', '</article>');
    return html.join('\n');
  }

  function renderResults(matches) {
    var box = document.getElementById('help-results');
    if (!box) return;
    if (!matches.length) {
      box.innerHTML = '<p class="help-empty">No results. Try a different keyword or browse the categories above.</p>';
      return;
    }
    var parts = [];
    for (var i = 0; i < matches.length; i++) parts.push(renderCard(matches[i]));
    box.innerHTML = parts.join('\n');
  }

  function search(query, category) {
    if (!_index) return;
    var qTokens = tokenize(query);
    var entries = _index.entries || [];
    var hits = [];
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      if (category && e.category !== category) continue;
      var s = (qTokens.length === 0) ? 1 : score(e, (query || '').toLowerCase(), qTokens);
      if (s > 0) hits.push({ entry: e, score: s });
    }
    hits.sort(function (a, b) { return b.score - a.score; });
    var top = hits.slice(0, 30).map(function (h) { return h.entry; });
    renderResults(top);
  }

  function bind() {
    var input = document.getElementById('help-search');
    var catSel = document.getElementById('help-category');
    function run() {
      var q = (input && input.value) || '';
      var c = (catSel && catSel.value) || '';
      search(q, c);
    }
    if (input) input.addEventListener('input', run);
    if (catSel) catSel.addEventListener('change', run);
    run();
  }

  function fetchJSON(url) {
    return fetch(url, { credentials: 'omit' }).then(function (r) {
      if (!r.ok) throw new Error('http_' + r.status);
      return r.json();
    });
  }

  function init() {
    Promise.all([
      fetchJSON('data/public_help_index.json'),
      fetchJSON('data/public_help_full.json').catch(function () { return null; }),
    ]).then(function (results) {
      _index = results[0];
      _full = results[1];
      if (_full && Array.isArray(_full.items)) {
        for (var i = 0; i < _full.items.length; i++) {
          _byId[_full.items[i].item_id] = _full.items[i];
        }
      }
      bind();
    }).catch(function (err) {
      var box = document.getElementById('help-results');
      if (box) {
        box.innerHTML = '<p class="help-empty">Static FAQ unavailable right now. ' +
                        'See the <a href="sost-mine.html">mining guide</a> or ' +
                        '<a href="sost-explorer.html">explorer</a>.</p>';
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
