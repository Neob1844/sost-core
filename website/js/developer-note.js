// SOST Developer Note — site-wide banner
//
// One-source-of-truth for the developer note that appears at the top of
// every page. The explorer page (sost-explorer.html) has its own embedded
// banner and skips this script (it never includes it).
//
// To edit the wording, change DEV_NOTE_HTML below. No other files need to
// change.

(function () {
  'use strict';

  if (window.__sostDeveloperNoteInjected) return;
  window.__sostDeveloperNoteInjected = true;

  var DEV_NOTE_HTML = [
    '<div class="sost-devnote-strip" role="region" aria-label="Developer Note">',
    '  <button type="button" class="sost-devnote-toggle" aria-expanded="false" title="Click to expand the full Developer Note">',
    '    <span class="sost-devnote-tag">Developer Note</span>',
    '    <span class="sost-devnote-summary">SOST is an experimental native Proof-of-Work project in pre-market testing &mdash; success, value, listings and adoption are not guaranteed.</span>',
    '    <span class="sost-devnote-cta" aria-hidden="true">',
    '      <span class="sost-devnote-cta-label" data-when="closed">Click to read more</span>',
    '      <span class="sost-devnote-cta-label" data-when="open" hidden>Hide</span>',
    '      <span class="sost-devnote-chevron">&#9662;</span>',
    '    </span>',
    '  </button>',
    '  <div class="sost-devnote-body" hidden>',
    '    <p>SOST is being built with a lot of work, but that does not guarantee success, future value, liquidity, exchange listings, or community adoption.</p>',
    '    <p>Right now, SOST is still an experimental native Proof-of-Work network in pre-market testing. Miners can participate with the current reference miner using CPU-oriented mining and approximately 8&nbsp;GB of RAM, but this does not mean that SOST will necessarily become valuable.</p>',
    '    <p>The future of the project depends on several important factors, none of which is guaranteed:</p>',
    '    <ol>',
    '      <li>That the project can comply with applicable crypto, tax, and possibly financial regulations in the places where it may operate.</li>',
    '      <li>That miners, node operators, developers, and the wider crypto community decide to support it.</li>',
    '      <li>That one or more exchanges may decide, at their own discretion, to list SOST in the future.</li>',
    '    </ol>',
    '    <p>ConvergenceX is a native and experimental Proof-of-Work system. It is different from traditional PoW designs and has been deployed directly on mainnet. Although the code has many internal tests and is being tested publicly, it has not yet been audited by an independent security firm.</p>',
    '    <p>For that reason, we are walking an unknown path together.</p>',
    '    <p>SOST may never obtain market value. It may never be listed. It may fail. This must be clear to everyone so that no false expectations are created.</p>',
    '    <p>Mine, run a node, test, and participate only if you understand that this is an experimental project.</p>',
    '    <p class="sost-devnote-sig">&mdash; NeoB</p>',
    '  </div>',
    '</div>'
  ].join('\n');

  var DEV_NOTE_CSS = [
    '.sost-devnote-strip{',
    '  position:relative;z-index:9000;',
    '  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;',
    '  background:#0a0a0a;color:#e6e6e6;',
    '  border-bottom:1px solid #fb010d;',
    '  box-shadow:0 1px 0 rgba(251,1,13,.25);',
    '}',
    '.sost-devnote-toggle{',
    '  display:flex;align-items:center;gap:10px;',
    '  width:100%;padding:8px 14px;',
    '  background:transparent;border:0;color:inherit;',
    '  font-family:inherit;font-size:12px;line-height:1.45;',
    '  text-align:left;cursor:pointer;',
    '}',
    '.sost-devnote-toggle:hover{background:#111}',
    '.sost-devnote-toggle:focus{outline:1px dashed #fb010d;outline-offset:-2px}',
    '.sost-devnote-tag{',
    '  display:inline-block;padding:2px 7px;',
    '  background:#fb010d;color:#fff;',
    '  font-weight:800;letter-spacing:1.2px;font-size:10px;',
    '  text-transform:uppercase;flex:0 0 auto;',
    '}',
    '.sost-devnote-summary{flex:1 1 auto;color:#cfcfcf}',
    '.sost-devnote-cta{',
    '  flex:0 0 auto;display:inline-flex;align-items:center;gap:6px;',
    '  padding:3px 9px;border:1px solid #fb010d;border-radius:3px;',
    '  background:rgba(251,1,13,.08);color:#fb010d;',
    '  font-weight:700;letter-spacing:.6px;font-size:10.5px;',
    '  text-transform:uppercase;',
    '  transition:background .15s ease;',
    '}',
    '.sost-devnote-toggle:hover .sost-devnote-cta{background:rgba(251,1,13,.18)}',
    '.sost-devnote-cta-label{display:inline-block}',
    '.sost-devnote-chevron{display:inline-block;transition:transform .15s ease}',
    '.sost-devnote-toggle[aria-expanded="true"] .sost-devnote-chevron{transform:rotate(180deg)}',
    '@keyframes sost-devnote-pulse{0%,100%{box-shadow:0 0 0 0 rgba(251,1,13,.45)}50%{box-shadow:0 0 0 4px rgba(251,1,13,0)}}',
    '.sost-devnote-toggle[aria-expanded="false"] .sost-devnote-cta{animation:sost-devnote-pulse 2.4s ease-in-out infinite}',
    '.sost-devnote-body{',
    '  padding:10px 18px 16px;',
    '  border-top:1px dashed rgba(251,1,13,.35);',
    '  font-size:12.5px;line-height:1.55;color:#d8d8d8;',
    '  max-height:60vh;overflow-y:auto;',
    '}',
    '.sost-devnote-body p{margin:.45em 0}',
    '.sost-devnote-body ol{margin:.5em 0 .5em 1.4em;padding:0}',
    '.sost-devnote-body li{margin:.25em 0}',
    '.sost-devnote-sig{color:#fb010d;font-weight:700;margin-top:.8em !important}',
    '@media (max-width:600px){',
    '  .sost-devnote-toggle{font-size:11px;padding:7px 10px;gap:8px;flex-wrap:wrap}',
    '  .sost-devnote-summary{font-size:11px;flex-basis:100%;order:3}',
    '  .sost-devnote-cta{font-size:10px;padding:2px 7px}',
    '  .sost-devnote-body{font-size:12px;padding:10px 12px 14px}',
    '}'
  ].join('\n');

  function inject() {
    if (document.querySelector('.sost-devnote-strip')) return;

    var style = document.createElement('style');
    style.setAttribute('data-sost-devnote', '1');
    style.appendChild(document.createTextNode(DEV_NOTE_CSS));
    document.head.appendChild(style);

    var wrap = document.createElement('div');
    wrap.innerHTML = DEV_NOTE_HTML;
    var node = wrap.firstElementChild;
    if (document.body.firstChild) {
      document.body.insertBefore(node, document.body.firstChild);
    } else {
      document.body.appendChild(node);
    }

    var btn = node.querySelector('.sost-devnote-toggle');
    var body = node.querySelector('.sost-devnote-body');
    var labelClosed = node.querySelector('.sost-devnote-cta-label[data-when="closed"]');
    var labelOpen = node.querySelector('.sost-devnote-cta-label[data-when="open"]');
    btn.addEventListener('click', function () {
      var open = btn.getAttribute('aria-expanded') === 'true';
      var nowOpen = !open;
      btn.setAttribute('aria-expanded', nowOpen ? 'true' : 'false');
      btn.setAttribute('title', nowOpen ? 'Click to hide the Developer Note' : 'Click to expand the full Developer Note');
      if (nowOpen) {
        body.removeAttribute('hidden');
        if (labelClosed) labelClosed.setAttribute('hidden', '');
        if (labelOpen) labelOpen.removeAttribute('hidden');
      } else {
        body.setAttribute('hidden', '');
        if (labelOpen) labelOpen.setAttribute('hidden', '');
        if (labelClosed) labelClosed.removeAttribute('hidden');
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();
