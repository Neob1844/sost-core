"""
HTML dossier renderer for opportunity campaigns.

Takes a campaign summary canonical JSON (the one
``opportunity_campaign.py`` writes) and produces a single
self-contained HTML file. The HTML is intentionally:

* dependency-free — no JavaScript, no external CSS, no remote fonts;
* printable — the layout collapses to print width and the per-AOI
  cards are kept together with ``page-break-inside: avoid``;
* honest — the editorial guardrail enforced on the backend is
  surfaced as visible disclaimer text on the page, and the
  Protocol Registry capsule line for the campaign is rendered
  verbatim so a recipient can re-verify the SHA-256 against the
  canonical JSON the dossier was built from.

This module never touches the network, never calls ``sost-cli`` and
never invokes a PDF engine — a printable HTML is the contract. The
operator can open it in any browser and "Save as PDF" if they want a
PDF.

The output passes the same forbidden-phrase guardrail used by the
contracts module: rendering aborts with :class:`ValueError` if any
``thesis`` / ``next_step`` field in the campaign payload contains a
banned promotional phrase. That makes it impossible to ship a
"polished" dossier that promises reserves.
"""
from __future__ import annotations

import datetime as _dt
import html as _html
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .canonical import canonical_json, sha256_of_canonical, pretty_json
from .contracts import FORBIDDEN_PHRASES
from .registry import (
    SCORECARD_CAPSULE_PREFIX,
    CAMPAIGN_CAPSULE_PREFIX,
    build_campaign_capsule,
    build_scorecard_capsule,
    sha256_hex_of_file,
)


DOSSIER_SCHEMA_VERSION = "opportunity_dossier.v1"


# ─── editorial guardrail ───────────────────────────────────────────

def _scan_forbidden(text: str, where: str) -> None:
    if not text:
        return
    low = text.lower()
    for bad in FORBIDDEN_PHRASES:
        if bad in low:
            raise ValueError(
                f"dossier: forbidden phrase {bad!r} detected in {where}. "
                f"The dossier renderer refuses to publish promotional "
                f"claims. Fix the input JSON before re-rendering."
            )


def _check_summary_language(summary: Dict[str, Any]) -> None:
    """Best-effort scan of every text-ish field we will render."""
    for key in ("campaign_name", "campaign_description"):
        _scan_forbidden(str(summary.get(key) or ""), key)
    for rec in summary.get("scorecards") or []:
        _scan_forbidden(str(rec.get("thesis") or ""), f"scorecards[].thesis")
        _scan_forbidden(str(rec.get("next_step") or ""), f"scorecards[].next_step")


# ─── helpers ───────────────────────────────────────────────────────

_CLASS_COLOR = {
    "extraction_led":   "#0ea5e9",
    "remediation_led":  "#f59e0b",
    "reactivation_led": "#a855f7",
    "partnership_led":  "#22c55e",
    "mixed":            "#94a3b8",
    "blocked":          "#ef4444",
}

_GRADE_LABEL = {
    "A":  "outstanding desk candidate",
    "B+": "strong desk candidate",
    "B":  "solid desk candidate",
    "C":  "marginal — extra verification advised",
    "F":  "park; not a desk candidate",
}


def _esc(value: Any) -> str:
    return _html.escape(str(value), quote=True)


def _format_subscore_bar(label: str, value: int, color: str) -> str:
    pct = max(0, min(100, int(value)))
    return (
        f'<div class="sub"><span class="sub-l">{_esc(label)}</span>'
        f'<span class="sub-bar">'
        f'<span class="sub-fill" style="width:{pct}%;background:{color}"></span>'
        f'</span>'
        f'<span class="sub-v">{pct}</span></div>'
    )


def _format_redaction(aoi: Dict[str, Any], redact: bool) -> str:
    if redact:
        return ('<span class="red">coordinates redacted</span>')
    lat = aoi.get("lat")
    lon = aoi.get("lon")
    if lat is None or lon is None:
        return '<span class="red">coordinates redacted</span>'
    return f'{float(lat):.4f}°N, {float(lon):.4f}°E'


# ─── HTML pieces ───────────────────────────────────────────────────

_CSS = """\
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
     font-size:13px;line-height:1.55;color:#1f2937;background:#f8fafc;padding:32px}
.wrap{max-width:980px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;
      box-shadow:0 1px 3px rgba(0,0,0,0.04)}
.header{padding:28px 32px 20px;border-bottom:1px solid #e2e8f0;background:#0f172a;color:#f1f5f9}
.header h1{font-size:22px;font-weight:700;margin-bottom:6px;letter-spacing:.5px}
.header .meta{font-size:11px;color:#94a3b8;letter-spacing:1px;text-transform:uppercase}
.section{padding:24px 32px;border-bottom:1px solid #e2e8f0}
.section h2{font-size:14px;font-weight:700;letter-spacing:1.2px;color:#475569;
            text-transform:uppercase;margin-bottom:14px}
.disclaimer{background:#fef2f2;border-left:4px solid #ef4444;padding:14px 18px;
            margin:18px 0;font-size:12px;color:#991b1b;line-height:1.7}
.disclaimer b{color:#7f1d1d}
.summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:8px}
.summary-cell{background:#f1f5f9;border:1px solid #e2e8f0;padding:10px 12px}
.summary-cell .k{font-size:10px;color:#64748b;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:4px}
.summary-cell .v{font-size:18px;font-weight:700;color:#0f172a}
table.rk{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}
table.rk th{background:#f1f5f9;color:#475569;font-weight:600;text-align:left;padding:8px 10px;
            border-bottom:2px solid #e2e8f0;font-size:11px;letter-spacing:.5px;text-transform:uppercase}
table.rk td{padding:8px 10px;border-bottom:1px solid #f1f5f9}
table.rk td.rank{font-weight:700;color:#0f172a;text-align:center;width:36px}
table.rk td.cls{font-weight:600}
table.rk td.com{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
table.rk td.sha{font-family:Consolas,"SF Mono",monospace;color:#64748b;font-size:10px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:16px;margin-top:6px}
.card{border:1px solid #e2e8f0;background:#fff;padding:16px;border-radius:4px;
      page-break-inside:avoid;break-inside:avoid}
.card .hd{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;gap:8px}
.card .nm{font-weight:700;color:#0f172a;font-size:14px;line-height:1.3}
.card .gr{font-weight:700;font-size:11px;color:#fff;padding:2px 8px;border-radius:3px;letter-spacing:.5px}
.card .pos{font-size:10px;color:#64748b;margin-bottom:10px}
.card .cls-bar{font-weight:600;font-size:11px;padding:4px 8px;display:inline-block;color:#fff;border-radius:3px;margin-bottom:12px}
.card .red{color:#94a3b8;font-style:italic}
.sub{display:flex;align-items:center;gap:8px;margin-bottom:4px;font-size:11px}
.sub-l{width:90px;color:#64748b;letter-spacing:.5px;text-transform:lowercase}
.sub-bar{flex:1;height:8px;background:#f1f5f9;border-radius:2px;overflow:hidden;position:relative}
.sub-fill{display:block;height:100%}
.sub-v{width:30px;text-align:right;font-variant-numeric:tabular-nums;color:#0f172a;font-weight:600}
.tags{margin-top:10px;font-size:10px;color:#64748b}
.tags .t{display:inline-block;background:#f1f5f9;border:1px solid #e2e8f0;
         padding:1px 6px;margin:1px;border-radius:2px}
.thesis{margin-top:10px;font-size:11.5px;color:#334155;line-height:1.55;
        background:#f8fafc;padding:8px 10px;border-left:3px solid #e2e8f0}
.next-step{margin-top:8px;font-size:11px;color:#475569;line-height:1.55}
.next-step b{color:#0f172a}
.capsule{font-family:Consolas,"SF Mono",monospace;font-size:10.5px;color:#0f172a;
         background:#fef9c3;border:1px solid #fde68a;padding:10px 12px;
         word-break:break-all;line-height:1.65;margin-top:14px;border-radius:3px}
.capsule .lbl{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
              font-size:10px;color:#78350f;letter-spacing:1.5px;text-transform:uppercase;
              font-weight:700;margin-bottom:4px;display:block}
.footer{padding:18px 32px;background:#f1f5f9;color:#64748b;font-size:10.5px;line-height:1.7}
.footer b{color:#0f172a}
@media print{
  body{background:#fff;padding:0}
  .wrap{box-shadow:none;border:none}
  .section{page-break-inside:avoid;break-inside:avoid}
  .header{background:#fff;color:#0f172a;border-bottom:3px solid #0f172a}
  .header .meta{color:#475569}
  .cards{display:block}
  .card{margin-bottom:14px}
}
"""


# ─── per-AOI card rendering ────────────────────────────────────────

def _render_card(rec: Dict[str, Any], redact: bool) -> str:
    aoi = rec.get("aoi") or {}
    name = _esc(aoi.get("name") or "Unnamed AOI")
    grade = rec.get("class_grade") or "?"
    opp_class = rec.get("opportunity_class") or "unknown"
    cls_color = _CLASS_COLOR.get(opp_class, "#475569")
    pos = _format_redaction(aoi, redact)
    metals = ", ".join(aoi.get("metals_of_interest") or []) or "—"
    country = _esc(aoi.get("country") or "—")
    radius_km = aoi.get("radius_km") or "—"
    grade_desc = _GRADE_LABEL.get(grade, "")
    subs = rec.get("subscores") or {}
    canonical_sha = rec.get("canonical_sha256") or "—"
    short_sha = canonical_sha[:12] if canonical_sha else "—"

    # Capsule body for this card (compact: not the full sost-cli line)
    capsule = (
        f"{SCORECARD_CAPSULE_PREFIX} "
        f"sha256={canonical_sha} "
        f"aoi=[{aoi.get('name','')}] "
        f"class={opp_class} grade={grade} "
        f"commercial={int(rec.get('score', subs.get('commercial', 0)))} "
        f"schema=opportunity_scorecard.v1 not_resource_estimate=true"
    )
    if redact:
        capsule = capsule.replace(f"aoi=[{aoi.get('name','')}]", "aoi=redacted")

    return f"""
    <div class="card">
      <div class="hd">
        <span class="nm">#{_esc(rec.get('rank',''))} · {name}</span>
        <span class="gr" style="background:{cls_color}">{_esc(grade)}</span>
      </div>
      <div class="pos">{pos} · radius {_esc(radius_km)} km · metals: {_esc(metals)} · country: {country}</div>
      <div class="cls-bar" style="background:{cls_color}">{_esc(opp_class)}</div>
      {_format_subscore_bar('geological',    subs.get('geological',    0), '#3b82f6')}
      {_format_subscore_bar('logistics',     subs.get('logistics',     0), '#10b981')}
      {_format_subscore_bar('environmental', subs.get('environmental', 0), '#22c55e')}
      {_format_subscore_bar('legal',         subs.get('legal',         0), '#a855f7')}
      {_format_subscore_bar('commercial',    subs.get('commercial',    0), cls_color)}
      <div class="thesis"><b>Thesis</b> · {_esc(rec.get('thesis') or '—')}</div>
      <div class="next-step"><b>Next step:</b> {_esc(rec.get('next_step') or '—')}</div>
      <div class="tags">tags: {''.join(f'<span class="t">{_esc(t)}</span>' for t in (rec.get('evidence_tags') or [])) or '<span class="red">no evidence tags reported</span>'}</div>
      <div class="capsule"><span class="lbl">Protocol Registry capsule (per-AOI)</span>{_esc(capsule)}</div>
      <div style="margin-top:6px;font-size:10px;color:#64748b">canonical sha-256 ·
        <span style="font-family:monospace">{_esc(short_sha)}…</span> ·
        grade hint: <i>{_esc(grade_desc)}</i>
      </div>
    </div>
    """


# ─── ranking table ─────────────────────────────────────────────────

def _render_ranking_table(ranking: List[Dict[str, Any]]) -> str:
    rows: List[str] = []
    for row in ranking:
        cls = row.get("opportunity_class") or "—"
        cls_color = _CLASS_COLOR.get(cls, "#475569")
        rows.append(
            f"<tr>"
            f"<td class='rank'>{_esc(row.get('rank',''))}</td>"
            f"<td>{_esc(row.get('aoi_name',''))}</td>"
            f"<td>{_esc(row.get('country',''))}</td>"
            f"<td>{_esc(row.get('metals',''))}</td>"
            f"<td class='cls' style='color:{cls_color}'>{_esc(cls)}</td>"
            f"<td>{_esc(row.get('class_grade',''))}</td>"
            f"<td class='com'>{_esc(row.get('commercial',''))}</td>"
            f"<td class='com'>{_esc(row.get('geological',''))}</td>"
            f"<td class='com'>{_esc(row.get('logistics',''))}</td>"
            f"<td class='com'>{_esc(row.get('environmental',''))}</td>"
            f"<td class='com'>{_esc(row.get('legal',''))}</td>"
            f"<td class='sha'>{_esc((row.get('canonical_sha256') or '')[:16])}…</td>"
            f"</tr>"
        )
    return (
        "<table class='rk'>"
        "<thead><tr>"
        "<th>#</th><th>AOI</th><th>cc</th><th>metals</th><th>class</th>"
        "<th>gr</th><th>com</th><th>geo</th><th>log</th><th>env</th><th>leg</th>"
        "<th>canonical sha-256</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


# ─── top-level renderer ────────────────────────────────────────────

def render_dossier(
    summary: Dict[str, Any],
    *,
    redact_coordinates: bool = False,
    campaign_capsule: Optional[str] = None,
    source_canonical_sha256: Optional[str] = None,
    source_canonical_path: Optional[str] = None,
) -> str:
    """Render the full HTML body. ``summary`` is the parsed campaign
    summary canonical JSON (dict). ``campaign_capsule`` is the literal
    string the operator would anchor on chain; computed from
    ``source_canonical_sha256`` + summary fields when not supplied."""
    _check_summary_language(summary)
    name = summary.get("campaign_name") or "Opportunity campaign"
    desc = summary.get("campaign_description") or ""
    version = summary.get("campaign_version") or "1"
    aoi_count = int(summary.get("aoi_count") or 0)
    generated_at = summary.get("generated_at") or ""
    ranking = summary.get("ranking") or []
    scorecards = summary.get("scorecards") or []

    if campaign_capsule is None and source_canonical_sha256:
        campaign_capsule = (
            f"{CAMPAIGN_CAPSULE_PREFIX} "
            f"sha256={source_canonical_sha256} "
            f"name={'redacted' if redact_coordinates else f'[{name}]'} "
            f"count={aoi_count} "
            f"schema={summary.get('schema_version', 'opportunity_campaign.v1')} "
            f"not_resource_estimate=true"
        )

    rendered_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    ranking_html = _render_ranking_table(ranking)
    cards_html = "".join(_render_card(rec, redact_coordinates) for rec in scorecards)

    capsule_block = ""
    if campaign_capsule:
        capsule_block = (
            f"<div class='capsule'>"
            f"<span class='lbl'>Protocol Registry capsule (campaign)</span>"
            f"{_esc(campaign_capsule)}"
            f"</div>"
        )

    source_line = ""
    if source_canonical_path:
        source_line = (
            f"<div style='font-size:10.5px;color:#64748b;margin-top:6px;font-family:Consolas,monospace'>"
            f"source canonical file: {_esc(Path(source_canonical_path).name)}</div>"
        )

    redacted_badge = ""
    if redact_coordinates:
        redacted_badge = (
            "<span style='background:#fef2f2;color:#7f1d1d;border:1px solid #fecaca;"
            "padding:2px 8px;font-size:10px;letter-spacing:1px;margin-left:8px;"
            "border-radius:3px;text-transform:uppercase'>coordinates redacted</span>"
        )

    return f"""\
<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>{_esc(name)} — Opportunity Dossier</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <h1>{_esc(name)} {redacted_badge}</h1>
    <div class="meta">opportunity dossier · schema {_esc(DOSSIER_SCHEMA_VERSION)} · rendered {_esc(rendered_at)}</div>
  </div>

  <div class="section">
    <h2>Editorial guardrail</h2>
    <div class="disclaimer">
      <b>This dossier is a desk-stage ranking of opportunity candidates.</b>
      It is <b>NOT a resource estimate.</b> It is <b>NOT a financial promise.</b>
      Each ranked AOI requires a legal title check and accredited sampling
      before any commercial action. The backend dataclass refuses to
      publish a scorecard whose thesis or next-step contains promotional
      language defined in <code>geaspirit/opportunity/contracts.py</code>.
    </div>
    {source_line}
    {capsule_block}
  </div>

  <div class="section">
    <h2>Campaign summary</h2>
    <div class="summary-grid">
      <div class="summary-cell"><div class="k">AOIs scored</div><div class="v">{aoi_count}</div></div>
      <div class="summary-cell"><div class="k">campaign version</div><div class="v">{_esc(version)}</div></div>
      <div class="summary-cell"><div class="k">generated at</div><div class="v" style="font-size:13px">{_esc(generated_at or '—')}</div></div>
      <div class="summary-cell"><div class="k">redacted</div><div class="v">{'yes' if redact_coordinates else 'no'}</div></div>
    </div>
    <div style="font-size:11.5px;color:#475569;margin-top:14px;line-height:1.7">{_esc(desc) if desc else '<i>(no description provided in the campaign file)</i>'}</div>
  </div>

  <div class="section">
    <h2>Ranking</h2>
    {ranking_html}
  </div>

  <div class="section">
    <h2>Per-AOI scorecards</h2>
    <div class="cards">{cards_html}</div>
  </div>

  <div class="footer">
    <b>How to verify this dossier:</b>
    re-compute the SHA-256 of the canonical campaign JSON the dossier was built
    from; the digest in the campaign capsule above must match byte-for-byte.
    Each per-AOI capsule similarly anchors that AOI's canonical scorecard.
    The SOST Protocol Registry stores the capsule body verbatim; the chain
    proves the timestamp, the operator proves the artefact.
    <br><br>
    <b>This dossier never claims confirmed mineralisation, reserves, JORC-compliance,
    NI 43-101 status, recovery rates or financial returns.</b>
    Anything in here is a candidate that merits desk validation, nothing more.
  </div>

</div>
</body></html>
"""


# ─── file I/O entry point ──────────────────────────────────────────

def render_from_path(
    campaign_summary_path: Path,
    *,
    redact_coordinates: bool = False,
) -> str:
    """Read a campaign summary canonical JSON from disk and return the
    full HTML body. Helper for the CLI and the tests."""
    p = Path(campaign_summary_path)
    payload = json.loads(p.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError(
            f"dossier: {p} must be a JSON object (got {type(payload).__name__})"
        )
    if not str(payload.get("schema_version", "")).startswith("opportunity_campaign"):
        raise ValueError(
            f"dossier: {p} does not look like an opportunity campaign summary "
            f"(schema_version={payload.get('schema_version')!r}); pass the "
            f"campaign_summary.canonical.json, not a per-AOI scorecard."
        )
    sha = sha256_hex_of_file(p)
    return render_dossier(
        payload,
        redact_coordinates=redact_coordinates,
        source_canonical_sha256=sha,
        source_canonical_path=str(p),
    )
