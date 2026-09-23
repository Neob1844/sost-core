// SOST V16 — DTD Jackpot V2 advance notice — site-wide collapsible banner
//
// One source of truth for the miner / node-operator advance notice about the
// DTD Jackpot V2 activation at block #30,000. Included on every page.
//
// Placement:
//   - if the page contains <div id="sost-v16-notice-mount"></div> the banner is
//     rendered inside that element (used by the explorer, which wants it above
//     the community-channels banner);
//   - otherwise it is inserted at the top of <body>, just below the developer
//     note strip when that strip is present.
//
// Collapsed by default. To edit the wording, change NOTICE_HTML below.

(function () {
  'use strict';

  if (window.__sostV16NoticeInjected) return;
  window.__sostV16NoticeInjected = true;

  var CSS = `
.sost-v16{--v16-gold:#fbbf24;--v16-mag:#e879f9;--v16-cyan:#22d3ee;--v16-green:#4ade80;
  position:relative;z-index:8900;max-width:1400px;margin:10px auto;padding:2px;border-radius:12px;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
  background:linear-gradient(115deg,#fbbf24,#e879f9 28%,#22d3ee 52%,#4ade80 74%,#fbbf24);
  background-size:300% 300%;animation:sost-v16-flow 9s linear infinite;
  box-shadow:0 0 22px rgba(232,121,249,.30),0 0 46px rgba(34,211,238,.16);}
@keyframes sost-v16-flow{0%{background-position:0% 50%}100%{background-position:300% 50%}}
.sost-v16-inner{background:linear-gradient(150deg,#120a1d 0%,#0a0f1c 55%,#140f06 100%);border-radius:10px;overflow:hidden}
.sost-v16-head{display:flex;align-items:center;gap:13px;width:100%;padding:13px 16px;
  background:transparent;border:0;color:#e8e8e8;font-family:inherit;text-align:left;cursor:pointer}
.sost-v16-head:hover{background:rgba(232,121,249,.06)}
.sost-v16-head:focus-visible{outline:1px dashed var(--v16-mag);outline-offset:-3px}
.sost-v16-icon{font-size:24px;line-height:1;flex:0 0 auto;filter:drop-shadow(0 0 10px rgba(251,191,36,.65));
  animation:sost-v16-bob 2.6s ease-in-out infinite}
@keyframes sost-v16-bob{0%,100%{transform:translateY(0) rotate(-3deg)}50%{transform:translateY(-3px) rotate(3deg)}}
.sost-v16-titles{flex:1 1 auto;min-width:0}
.sost-v16-title{display:block;font-size:15px;font-weight:900;letter-spacing:.4px;
  background:linear-gradient(90deg,#fbbf24,#e879f9 45%,#22d3ee);background-size:220% 100%;
  -webkit-background-clip:text;background-clip:text;color:transparent;animation:sost-v16-flow 7s linear infinite}
.sost-v16-sub{display:block;font-size:11px;color:#a9b6c7;letter-spacing:.3px;margin-top:3px;line-height:1.5}
.sost-v16-sub b{color:var(--v16-green)}
.sost-v16-chip{flex:0 0 auto;padding:5px 11px;border-radius:6px;font-size:10.5px;font-weight:900;letter-spacing:1.1px;
  color:#0a0a0a;background:linear-gradient(90deg,#fbbf24,#f59e0b);box-shadow:0 0 14px rgba(251,191,36,.45);white-space:nowrap}
.sost-v16-cta{flex:0 0 auto;display:inline-flex;align-items:center;gap:6px;padding:5px 11px;border-radius:6px;
  border:1px solid var(--v16-mag);background:rgba(232,121,249,.10);color:#f5d0fe;
  font-size:10.5px;font-weight:800;letter-spacing:1px;text-transform:uppercase;white-space:nowrap}
.sost-v16-head[aria-expanded="false"] .sost-v16-cta{animation:sost-v16-pulse 2.4s ease-in-out infinite}
@keyframes sost-v16-pulse{0%,100%{box-shadow:0 0 0 0 rgba(232,121,249,.45)}50%{box-shadow:0 0 0 5px rgba(232,121,249,0)}}
.sost-v16-chev{display:inline-block;transition:transform .18s ease}
.sost-v16-head[aria-expanded="true"] .sost-v16-chev{transform:rotate(180deg)}
.sost-v16-body{padding:4px 18px 18px;border-top:1px dashed rgba(232,121,249,.35);
  font-size:12.5px;line-height:1.7;color:#dfe6ee;max-height:72vh;overflow-y:auto}
.sost-v16-body p{margin:.5em 0}
.sost-v16-body b{color:#fff}
.sost-v16-alert{margin:12px 0 0;padding:11px 14px;border-radius:8px;border:1px solid rgba(74,222,128,.6);
  background:linear-gradient(135deg,rgba(74,222,128,.13),rgba(34,211,238,.07));color:#d9ffe8;font-size:12.5px;line-height:1.65}
.sost-v16-alert .k{color:var(--v16-green);font-weight:900;letter-spacing:.6px}
.sost-v16-nums{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:9px;margin:13px 0 0}
.sost-v16-num{background:rgba(34,211,238,.06);border:1px solid rgba(34,211,238,.32);border-radius:8px;padding:9px 11px}
.sost-v16-num .n{display:block;font-size:17px;font-weight:900;color:var(--v16-cyan);letter-spacing:.5px}
.sost-v16-num .l{display:block;font-size:10px;color:#9fb6c4;letter-spacing:.5px;margin-top:2px;line-height:1.45}
.sost-v16-h{margin:18px 0 6px;font-size:11px;font-weight:900;letter-spacing:1.4px;text-transform:uppercase;color:var(--v16-gold)}
.sost-v16-h.mag{color:var(--v16-mag)}
.sost-v16-h.cy{color:var(--v16-cyan)}
.sost-v16-rule{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin:10px 0 0}
.sost-v16-rule div{border-radius:8px;padding:11px 13px;font-size:12px;line-height:1.6}
.sost-v16-rule .gate{background:rgba(232,121,249,.08);border:1px solid rgba(232,121,249,.45)}
.sost-v16-rule .gate b{color:var(--v16-mag)}
.sost-v16-rule .weight{background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.45)}
.sost-v16-rule .weight b{color:var(--v16-gold)}
.sost-v16-cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin:10px 0 0}
.sost-v16-card{background:rgba(255,255,255,.025);border:1px solid rgba(255,255,255,.10);border-radius:8px;padding:12px 14px}
.sost-v16-card h4{margin:0 0 7px;font-size:12px;font-weight:900;letter-spacing:.8px;color:#fff;text-transform:uppercase}
.sost-v16-card.miner{border-color:rgba(251,191,36,.45)}
.sost-v16-card.miner h4{color:var(--v16-gold)}
.sost-v16-card.node{border-color:rgba(34,211,238,.45)}
.sost-v16-card.node h4{color:var(--v16-cyan)}
.sost-v16-body ol,.sost-v16-body ul{margin:.4em 0 .2em 1.25em;padding:0}
.sost-v16-body li{margin:.3em 0;font-size:12px;line-height:1.6}
.sost-v16-code{margin:10px 0 0;padding:10px 13px;border-radius:8px;background:#07090e;border:1px solid rgba(255,255,255,.10);
  color:#bfe9ff;font-size:11.5px;line-height:1.65;white-space:pre;overflow-x:auto}
.sost-v16-blink{margin:12px 0 0;padding:12px 14px;border-radius:8px;border:2px solid #fb010d;
  background:linear-gradient(135deg,rgba(251,1,13,.20),rgba(251,1,13,.06));color:#ffe3e3;
  font-size:13px;line-height:1.7;animation:sost-v16-blink 1.1s steps(1,end) infinite}
.sost-v16-blink b{color:#fff}
.sost-v16-blink .hdr{display:block;color:#ff3b3b;font-weight:900;letter-spacing:1.3px;text-transform:uppercase;font-size:12px;margin-bottom:5px}
.sost-v16-blink .win{color:#ff6b6b;font-weight:900}
@keyframes sost-v16-blink{
  0%,49%{border-color:#fb010d;box-shadow:0 0 20px rgba(251,1,13,.55);background:linear-gradient(135deg,rgba(251,1,13,.24),rgba(251,1,13,.08))}
  50%,100%{border-color:rgba(251,1,13,.35);box-shadow:0 0 0 rgba(251,1,13,0);background:linear-gradient(135deg,rgba(251,1,13,.07),rgba(251,1,13,.02))}}
.sost-v16-redchip{flex:0 0 auto;padding:5px 11px;border-radius:6px;font-size:10.5px;font-weight:900;letter-spacing:1px;
  color:#fff;background:#fb010d;border:1px solid #ff6b6b;white-space:nowrap;
  animation:sost-v16-chipblink 1.1s steps(1,end) infinite}
@keyframes sost-v16-chipblink{0%,49%{opacity:1;box-shadow:0 0 16px rgba(251,1,13,.75)}50%,100%{opacity:.32;box-shadow:0 0 0 rgba(251,1,13,0)}}
@media (prefers-reduced-motion:reduce){
  .sost-v16-blink,.sost-v16-redchip,.sost-v16-icon,.sost-v16-title,.sost-v16{animation:none !important}
  .sost-v16-blink{border-color:#fb010d;box-shadow:0 0 16px rgba(251,1,13,.45)}
  .sost-v16-redchip{opacity:1}
}
.sost-v16-warn{margin:13px 0 0;padding:11px 14px;border-radius:8px;border:1px solid rgba(251,1,13,.65);
  background:linear-gradient(135deg,rgba(251,1,13,.12),rgba(251,1,13,.04));color:#ffdede;font-size:12px;line-height:1.65}
.sost-v16-warn b{color:#ff6b6b}
.sost-v16-links{display:flex;flex-wrap:wrap;gap:8px;margin:13px 0 0}
.sost-v16-links a{display:inline-flex;align-items:center;gap:6px;padding:7px 12px;border-radius:6px;
  background:rgba(34,211,238,.08);border:1px solid rgba(34,211,238,.45);color:#a5f3fc;text-decoration:none;
  font-size:11px;font-weight:700;letter-spacing:.4px}
.sost-v16-links a:hover{background:rgba(34,211,238,.18)}
.sost-v16-foot{margin:14px 0 0;padding-top:10px;border-top:1px dashed rgba(255,255,255,.12);
  font-size:10.5px;line-height:1.6;color:#8b98a8}
@media (max-width:760px){
  .sost-v16{margin:8px auto}
  .sost-v16-head{flex-wrap:wrap;gap:9px;padding:11px 12px}
  .sost-v16-titles{flex-basis:100%;order:3}
  .sost-v16-title{font-size:13.5px}
  .sost-v16-chip{font-size:9.5px;padding:4px 9px}
  .sost-v16-body{padding:4px 12px 15px;font-size:12px}
}`;

  var NOTICE_HTML = `
<div class="sost-v16" role="region" aria-label="SOST V16 DTD Jackpot V2 advance notice">
 <div class="sost-v16-inner">
  <button type="button" class="sost-v16-head" aria-expanded="false" aria-controls="sostV16Body" title="Open the DTD Jackpot V2 advance notice">
    <span class="sost-v16-icon" aria-hidden="true">🏆</span>
    <span class="sost-v16-titles">
      <span class="sost-v16-title">SOST V16.2.3 &mdash; DTD Eligibility + Jackpot V2 &middot; Miner &amp; Node Operator Notice</span>
      <span class="sost-v16-sub">Install the new binaries on your <b>node AND your miner</b> &mdash; <b>after block #29,900 and before #30,000</b> &middot; Normal DTD eligibility DOES change</span>
    </span>
    <span class="sost-v16-chip">ACTIVATION #30,000</span>
    <span class="sost-v16-redchip">&#9888; UPDATE WINDOW &mdash; AFTER #29,900, BEFORE #30,000</span>
    <span class="sost-v16-cta"><span class="sost-v16-cta-label" data-when="closed">Read</span><span class="sost-v16-cta-label" data-when="open" hidden>Hide</span><span class="sost-v16-chev" aria-hidden="true">&#9662;</span></span>
  </button>

  <div class="sost-v16-body" id="sostV16Body" hidden>

    <div class="sost-v16-blink">
      <span class="hdr">&#9888; Mandatory action for every miner and node operator</span>
      Install the <b>new V16.2.3 binaries on your node AND on your miner</b> and restart both &mdash;
      <span class="win">after block #29,900 and before block #30,000</span>. That is the coordinated
      update window for the network: everyone switches inside the same ~16&ndash;17&nbsp;hour stretch, so
      the whole network crosses the activation running the same code. Get the binaries and verify their
      SHA256 <b>before</b> the window opens, so the window itself is only stop, install, restart.
      A validating node still on older consensus software at #30,000 <b>may diverge from the V16 chain</b>.
      <br><a href="sost-upgrade-v1622.html" style="color:#39ff14;font-weight:700;text-decoration:underline">&#9654; Full upgrade guide &mdash; commands, verification, rollback</a>
      &nbsp;&middot;&nbsp;<a href="https://github.com/Neob1844/sost-core/releases/tag/v16.2.3" target="_blank" rel="noopener" style="color:#22d3ee;font-weight:700;text-decoration:underline">Official release &amp; SHA-256</a>
    </div>

    <div class="sost-v16-alert">
      <span class="k">CORRECTION &mdash; V16.1 ALSO CHANGES NORMAL DTD ELIGIBILITY.</span><br>
      An earlier version of this notice said normal DTD would not change. That is no longer true. Normal DTD keeps its <b>payout logic, its every-block cadence, its uniform selection and its seed</b>, and it still needs <b>no NODE_BIND and no heartbeats</b> &mdash; but from #30,000 <b>who qualifies</b> changes: the activity window drops to <b>288 blocks</b> (~2 days), the 6-block cooldown <b>yields if applying it would leave nobody eligible</b>, and the 10%/288 anti-dominance gate is <b>armed only at 11 or more distinct miners</b>. While a single miner is active it can therefore take 100% of the block (50% miner + 50% DTD). An active SbPoW miner keeps participating in normal DTD exactly as today.
      <b>DTD Jackpot V2</b> becomes a separate, independent draw that rewards miners who contribute <b>real Proof-of-Work</b> <i>and</i> <b>verified node participation</b>.
    </div>

    <div class="sost-v16-nums">
      <div class="sost-v16-num"><span class="n">#29,900 &rarr; #30,000</span><span class="l"><b>Update window</b> &mdash; install the new binaries here</span></div>
      <div class="sost-v16-num"><span class="n">#30,000</span><span class="l">V16 activates automatically by block height</span></div>
      <div class="sost-v16-num"><span class="n">#30,186</span><span class="l">First DTD Jackpot V2 draw</span></div>
      <div class="sost-v16-num"><span class="n">v16.2.3</span><span class="l">The binaries to install &mdash; node AND miner</span></div>
      <div class="sost-v16-num"><span class="n">288</span><span class="l">Jackpot cadence &amp; heartbeat epoch (unchanged)</span></div>
      <div class="sost-v16-num"><span class="n">100 &rarr; 500</span><span class="l">Jackpot base SOST, rollover cap &mdash; existing historical reserve, <b>no new emission</b></span></div>
    </div>

    <div class="sost-v16-h mag">The core rule</div>
    <div class="sost-v16-rule">
      <div class="gate"><b>NODE PARTICIPATION &rarr; ELIGIBILITY.</b><br>A node does not give you Jackpot tickets. It lets you enter the eligibility set. Running 10 nodes gives exactly the same weight as running 1.</div>
      <div class="weight"><b>PROOF-OF-WORK &rarr; WEIGHT.</b><br>1 valid SbPoW block in the previous 2,016 blocks = 1 unit of weight. Splitting your work across many addresses does not create extra weight &mdash; 100 blocks is weight 100 either way.</div>
    </div>

    <div class="sost-v16-h">Eligibility from block #30,000 (ALL four required)</div>
    <ol>
      <li>A valid <b>SbPoW mining identity</b> (the signed mining key in your blocks).</li>
      <li>At least <b>3 valid mined blocks</b> in the previous <b>2,016 blocks</b> (~14 days).</li>
      <li>A <b>NODE_BIND</b>: your node key cryptographically authorised by your mining key, on-chain. No registry, no whitelist, no approval.</li>
      <li>Verified node participation through periodic signed <b>NODE_HEARTBEAT</b> messages (~every 288 blocks, referencing recent chain state).</li>
    </ol>
    <p>Then: <b>Jackpot weight = number of valid SbPoW blocks you mined in the previous 2,016 blocks.</b> A miner with 10 eligible blocks has twice the probability of one with 5 &mdash; not a guaranteed win. DTD Jackpot V2 has <b>no cooldown and no anti-dominance</b> on purpose: ~20% of eligible work should mean ~20% of the probability. With no eligible participants the prize <b>rolls over</b> (up to the 500 SOST cap) &mdash; no fallback winner is invented.</p>

    <div class="sost-v16-h cy">What you actually have to do</div>
    <div class="sost-v16-cols">
      <div class="sost-v16-card miner">
        <h4>&#9935; If you mine</h4>
        <ol>
          <li><b>Before the window:</b> get <b>v16.2.3</b> &mdash; official binaries at <a href="https://github.com/Neob1844/sost-core/releases/tag/v16.2.3" target="_blank" rel="noopener">github.com/Neob1844/sost-core/releases</a> (<code>sost-node</code>, <code>sost-miner</code>, <code>sost-cli</code>, <code>SHA256SUMS</code>). Compiling is optional; a downloaded binary whose <b>SHA256 matches</b> is equally valid. If you do build it, use <code>-B build</code>: the published hashes only reproduce from a build directory with that name.</li>
          <li>Verify the version and the official <b>SHA256</b>.</li>
          <li><b>In the window (after #29,900, before #30,000):</b> stop your node and your miner, install the v16.2.3 binaries on <b>both</b>, restart both. Step-by-step, with the commands for systemd / manual / WSL: <a href="sost-upgrade-v1622.html" style="color:#39ff14;font-weight:700">OPERATOR UPGRADE GUIDE</a>.</li>
          <li>Keep mining normally &mdash; V16 activates by itself at #30,000. No command, no config switch, no restart exactly at the activation height.</li>
          <li>Register your <b>NODE_BIND</b> once V2 is active.</li>
          <li>Check your eligibility and PoW weight in the Explorer.</li>
        </ol>
      </div>
      <div class="sost-v16-card node">
        <h4>&#9881; If you run a node</h4>
        <ol>
          <li>The V16 upgrade is <b>mandatory for validating nodes</b>: below #30,000 it follows current V15 rules, from #30,000 it follows V16 rules.</li>
          <li>Install the <b>v16.2.3</b> node binary in the update window: <b>after #29,900, before #30,000</b>.</li>
          <li>Nodes still running the old consensus software after #30,000 <b>may diverge from the V16 chain</b>.</li>
          <li>Create/configure your <b>node identity</b> and keep the node running.</li>
          <li>Maintain the signed <b>heartbeats</b> (the guide will cover automatic maintenance).</li>
          <li>Only needed for the Jackpot &mdash; normal DTD requires none of this.</li>
        </ol>
      </div>
    </div>

    <div class="sost-v16-h">First-Jackpot bootstrap &mdash; not another fork</div>
    <p>NODE_BIND only becomes available once V2 activates, so there is no completed heartbeat epoch for the first draw. The requirement ramps deterministically from the number of completed V2 epochs:</p>
    <div class="sost-v16-code">#30,186   NODE_BIND required   heartbeats 0/0
#30,474   NODE_BIND required   heartbeats 1/1
#30,762   NODE_BIND required   heartbeats 2/2
#31,050   NODE_BIND required   heartbeats 3/3
#31,338+  NODE_BIND required   heartbeats 3 of the previous 4</div>

    <div class="sost-v16-h">What a heartbeat does and does not prove</div>
    <p>It proves that an authorised node identity participated cryptographically relative to the canonical chain state. It does <b>not</b> prove a unique physical machine, a unique country or 24/7 uptime &mdash; hence <b>verified node participation</b>, not "verified independent physical node". This limitation grants no extra Jackpot weight, because extra nodes give no weighting advantage.</p>

    <div class="sost-v16-h">What does NOT change</div>
    <ul>
      <li>Normal DTD: <b>payout logic, every-block cadence, uniform selection and seed</b> &mdash; untouched. Its <b>eligibility</b> does change (288-block window, conditional cooldown, conditional anti-dominance) &mdash; see the correction above.</li>
      <li>The 50% miner / 50% DTD emission structure.</li>
      <li>The DTD Jackpot cadence of 288 blocks.</li>
      <li>The Jackpot funding source: the existing historical reserve. <b>No new emission is created.</b></li>
    </ul>
    <p>Normal DTD and DTD Jackpot are independent draws at a Jackpot height &mdash; the two winners may be different miners, or the same one. Nothing prevents that.</p>

    <div class="sost-v16-warn">
      <b>&#9888; Operational notice.</b> DTD Jackpot V2 is in final release preparation (unit, deterministic-selection, Sybil-invariance, node-participation, activation, connect/disconnect, reorg, reindex, restart and devnet end-to-end payout tests are done). Final binaries, consensus commit, SHA256 hashes and a simple step-by-step operator guide will be published <b>before</b> the update window. <b>Do not update from unofficial binaries or unverified sources.</b> SOST is experimental MIT-licensed software provided without warranty; mining, node operation and any market activity are at the participant's own risk.
    </div>

    <div class="sost-v16-links">
      <a href="https://github.com/Neob1844/sost-core" target="_blank" rel="noopener">&#8997; Source (MIT)</a>
      <a href="/sost-explorer.html">&#9639; Explorer</a>
      <a href="https://bitcointalk.org/index.php?topic=5579432" target="_blank" rel="noopener">&#8383; BitcoinTalk &mdash; official upgrade thread</a>
      <a href="https://t.me/SOSTProtocolOfficial" target="_blank" rel="noopener">&#9992; Telegram</a>
      <a href="mailto:sost@sostcore.com">&#9993; sost@sostcore.com</a>
    </div>

    <div class="sost-v16-foot">Sovereign Stock Token &middot; ConvergenceX native L1 Proof-of-Work &middot; Open source (MIT). Use the official BitcoinTalk thread as the primary reference for the #30,000 network upgrade. &mdash; NeoB</div>
  </div>
 </div>
</div>`;

  function inject() {
    if (document.querySelector('.sost-v16')) return;

    var style = document.createElement('style');
    style.setAttribute('data-sost-v16', '1');
    style.appendChild(document.createTextNode(CSS));
    document.head.appendChild(style);

    var wrap = document.createElement('div');
    wrap.innerHTML = NOTICE_HTML;
    var node = wrap.firstElementChild;

    var mount = document.getElementById('sost-v16-notice-mount');
    if (mount) {
      mount.appendChild(node);
    } else {
      var devnote = document.querySelector('.sost-devnote-strip');
      if (devnote && devnote.parentNode) {
        devnote.parentNode.insertBefore(node, devnote.nextSibling);
      } else if (document.body.firstChild) {
        document.body.insertBefore(node, document.body.firstChild);
      } else {
        document.body.appendChild(node);
      }
      // standalone placement needs its own side padding
      node.style.width = 'calc(100% - 32px)';
      node.style.marginLeft = 'auto';
      node.style.marginRight = 'auto';
    }

    var btn = node.querySelector('.sost-v16-head');
    var body = node.querySelector('.sost-v16-body');
    var closed = node.querySelector('.sost-v16-cta-label[data-when="closed"]');
    var open = node.querySelector('.sost-v16-cta-label[data-when="open"]');

    btn.addEventListener('click', function () {
      var isOpen = btn.getAttribute('aria-expanded') === 'true';
      var next = !isOpen;
      btn.setAttribute('aria-expanded', next ? 'true' : 'false');
      btn.setAttribute('title', next ? 'Hide the DTD Jackpot V2 advance notice' : 'Open the DTD Jackpot V2 advance notice');
      if (next) {
        body.removeAttribute('hidden');
        if (closed) closed.setAttribute('hidden', '');
        if (open) open.removeAttribute('hidden');
      } else {
        body.setAttribute('hidden', '');
        if (open) open.setAttribute('hidden', '');
        if (closed) closed.removeAttribute('hidden');
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();
