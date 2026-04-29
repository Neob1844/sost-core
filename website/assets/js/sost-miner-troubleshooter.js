// SOST Miner Troubleshooter — local-only log analyzer.
//
// Loads the deterministic rule set from data/miner_troubleshooting.json
// (same-origin fetch, no external services) and matches the user's
// pasted log against the rules. The log is NEVER uploaded — analysis
// is performed entirely in the browser using string regular
// expressions defined in the rule set.

(function () {
  'use strict';

  if (window.__sostMinerTroubleInit) return;
  window.__sostMinerTroubleInit = true;

  var _rules = null;
  var _safetyNotes = [];

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function renderFinding(rule, snippet) {
    var sevClass = 'sev-' + (rule.severity || 'info');
    var html = [
      '<article class="trouble-card ' + sevClass + '">',
      '  <header><span class="sev">' + escapeHtml((rule.severity || 'info').toUpperCase()) + '</span>',
      '    <h3>' + escapeHtml(rule.title) + '</h3></header>',
      '  <p class="trouble-explanation">' + escapeHtml(rule.explanation) + '</p>',
    ];
    if (rule.actions && rule.actions.length) {
      html.push('<h4>What to try</h4><ol class="trouble-actions">');
      for (var i = 0; i < rule.actions.length; i++) {
        html.push('<li><code>' + escapeHtml(rule.actions[i]) + '</code></li>');
      }
      html.push('</ol>');
    }
    if (rule.safety_note) {
      html.push('<p class="trouble-safety">&#9888; ' + escapeHtml(rule.safety_note) + '</p>');
    }
    if (snippet) {
      html.push('<p class="trouble-match">Matched line: <code>' +
                escapeHtml(snippet.slice(0, 200)) + '</code></p>');
    }
    html.push('</article>');
    return html.join('\n');
  }

  function analyse(text) {
    if (!_rules || !text) return [];
    var lines = text.split(/\r?\n/);
    var hits = [];
    var seen = {};
    for (var r = 0; r < _rules.length; r++) {
      var rule = _rules[r];
      if (!rule.patterns) continue;
      for (var p = 0; p < rule.patterns.length; p++) {
        var re;
        try { re = new RegExp(rule.patterns[p], 'i'); } catch (e) { continue; }
        for (var i = 0; i < lines.length; i++) {
          if (re.test(lines[i])) {
            if (!seen[rule.id]) {
              hits.push({ rule: rule, snippet: lines[i] });
              seen[rule.id] = true;
            }
            break;
          }
        }
      }
    }
    var sevOrder = { critical: 0, warning: 1, info: 2 };
    hits.sort(function (a, b) {
      return (sevOrder[a.rule.severity] || 99) - (sevOrder[b.rule.severity] || 99);
    });
    return hits;
  }

  function renderResults(hits) {
    var box = document.getElementById('trouble-results');
    if (!box) return;
    if (!hits.length) {
      box.innerHTML = '<p class="trouble-empty">No known patterns matched. ' +
        'See the <a href="sost-help.html">Help Center</a> or paste a different ' +
        'section of the log. Remember the analysis runs locally — your log ' +
        'has not been uploaded.</p>';
      return;
    }
    var parts = [];
    for (var i = 0; i < hits.length; i++) {
      parts.push(renderFinding(hits[i].rule, hits[i].snippet));
    }
    box.innerHTML = parts.join('\n');
  }

  function bind() {
    var btn = document.getElementById('trouble-analyze');
    var ta = document.getElementById('trouble-input');
    var box = document.getElementById('trouble-results');
    if (!btn || !ta || !box) return;
    btn.addEventListener('click', function () {
      var hits = analyse(ta.value || '');
      renderResults(hits);
    });
    var clearBtn = document.getElementById('trouble-clear');
    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        ta.value = '';
        box.innerHTML = '';
      });
    }
  }

  function fetchJSON(url) {
    return fetch(url, { credentials: 'omit' }).then(function (r) {
      if (!r.ok) throw new Error('http_' + r.status);
      return r.json();
    });
  }

  function init() {
    fetchJSON('data/miner_troubleshooting.json').then(function (payload) {
      _rules = payload.rules || [];
      _safetyNotes = payload.safety_notes || [];
      // Render safety notes if a target is present.
      var notes = document.getElementById('trouble-safety-notes');
      if (notes && _safetyNotes.length) {
        var parts = ['<ul class="trouble-safety-list">'];
        for (var i = 0; i < _safetyNotes.length; i++) {
          parts.push('<li>&#9888; ' + escapeHtml(_safetyNotes[i]) + '</li>');
        }
        parts.push('</ul>');
        notes.innerHTML = parts.join('\n');
      }
      bind();
    }).catch(function () {
      var box = document.getElementById('trouble-results');
      if (box) {
        box.innerHTML = '<p class="trouble-empty">Troubleshooter rules unavailable. ' +
                        'See the <a href="sost-mine.html">mining guide</a>.</p>';
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
