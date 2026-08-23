// Archived from website/sost-app/index.html on 2026-08-09 (GeaSpirit separation, phase 1/2).
// Was lines 2362-2415: SectionRenderers.geaspirit
// ── GEASPIRIT ──────────────────────────────────────────────────
SectionRenderers.geaspirit = function(el) {
  el.style.padding = '16px';
  el.style.overflow = 'auto';
  el.innerHTML = `
    <div class="pip-panel" style="text-align:center">
      <img src="https://sostcore.com/geaspirit-logo.png" alt="GeaSpirit logo" style="width:88px;height:88px;margin:4px auto 8px auto;display:block;filter:drop-shadow(0 0 12px rgba(0,255,65,.35))">
      <h2 style="border:0;justify-content:center">// GEASPIRIT</h2>
      <p style="color:var(--pip)">Second-Chance Mining Intelligence</p>
      <p style="margin-top:8px;font-size:12px;color:var(--pip-dim)">Open-data intelligence for overlooked, abandoned, historic, tailings and care-and-maintenance mining assets. Explainable scoring, on-demand reports — prioritization, <b>not</b> a guaranteed discovery.</p>
      <a href="https://geaspirit.com/?from=sost-app" target="_blank" rel="noopener noreferrer" class="pip-btn" style="display:block;margin-top:14px;text-align:center;padding:11px;font-weight:700;letter-spacing:1px;text-decoration:none">OPEN GEASPIRIT PLATFORM ↗</a>
      <a href="https://geaspirit.com/reports/demo-geaspirit-asset-intelligence-report.html" target="_blank" rel="noopener noreferrer" style="display:block;margin-top:10px;text-align:center;padding:10px;border:1px solid var(--pip-dim);border-radius:4px;color:var(--pip);text-decoration:none;font-weight:700;letter-spacing:1px;font-size:13px">READ DEMO REPORT ↗</a>
    </div>
    <div class="pip-panel">
      <h2>// WHAT IT COVERS</h2>
      <div class="stat-row"><span class="stat-label">ABANDONED / HISTORIC</span><span class="stat-value stat-ok">closed on price, not geology</span></div>
      <div class="stat-row"><span class="stat-label">TAILINGS / WASTE</span><span class="stat-value">residual-value signal</span></div>
      <div class="stat-row"><span class="stat-label">CARE &amp; MAINTENANCE</span><span class="stat-value">dormant projects</span></div>
      <div class="stat-row"><span class="stat-label">UNDERUSED CONCESSIONS</span><span class="stat-value">held but inactive</span></div>
      <div class="stat-row"><span class="stat-label">DATA</span><span class="stat-value stat-ok">open satellite + geoscience</span></div>
      <div class="stat-row"><span class="stat-label">LANGUAGES</span><span class="stat-value">16</span></div>
    </div>
    <div class="pip-panel">
      <h2>// GEASPIRIT SCORE</h2>
      <p style="font-size:12px;color:var(--pip-dim);margin-bottom:8px">A transparent 0–100 triage score — not a probability of ore, not a discovery guarantee.</p>
      <div class="stat-row"><span class="stat-label">SIGNAL</span><span class="stat-value">spectral + geological favourability</span></div>
      <div class="stat-row"><span class="stat-label">ACCESS / DEPTH</span><span class="stat-value">reachability + infrastructure</span></div>
      <div class="stat-row"><span class="stat-label">PRECISION</span><span class="stat-value">spatial tightness of target</span></div>
      <div class="stat-row"><span class="stat-label">CERTAINTY</span><span class="stat-value">validation, missing-data penalty</span></div>
      <div class="stat-row"><span class="stat-label">CONFIDENCE</span><span class="stat-value stat-ok">HIGH / MEDIUM / LOW band</span></div>
    </div>
    <div class="pip-panel">
      <h2>// REPORTS</h2>
      <ul style="padding-left:20px">
        <li>Asset Scan — single-asset four-dimension breakdown</li>
        <li>Comparative Asset Ranking — portfolio prioritization</li>
        <li>Mining Opportunity Brief — region-level overview</li>
        <li>Tailings / Abandoned Mine Review</li>
      </ul>
    </div>
    <div class="pip-panel">
      <h2>// SOST ECOSYSTEM &amp; LIMITS</h2>
      <p style="font-size:12px;color:var(--pip-dim)">Powered by the GeaSpirit Engine and connected to the SOST ecosystem. SOST may support future payment / verification — but GeaSpirit is fully usable <b>without</b> any blockchain, and holding SOST is <b>not</b> required.</p>
      <h3 style="margin-top:10px">NOT:</h3>
      <ul style="padding-left:20px">
        <li>Not a guaranteed discovery — only drilling confirms a deposit</li>
        <li>Not investment or legal advice</li>
        <li>Not a marketplace; no ownership verification</li>
      </ul>
      <a href="https://geaspirit.com/?from=sost-app" target="_blank" rel="noopener noreferrer" class="pip-btn" style="display:block;margin-top:12px;text-align:center;padding:11px;font-weight:700;letter-spacing:1px;text-decoration:none">LAUNCH GEASPIRIT.COM ↗</a>
    </div>
  `;
  AudioEngine.ambient_scan();
};
