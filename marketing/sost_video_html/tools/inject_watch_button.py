#!/usr/bin/env python3
"""
Inject the ▶ WATCH button (4th nav icon, cyan, 72×72, exactly the
shape used in sost-explorer.html) right after every PoPC DEX nav
icon in every page of website/, and the matching sv-modal player
just before </body>. Idempotent: if a page already has sv-modal
the file is left untouched.

Run from anywhere; paths are absolute. No network, no sudo.
"""
import re
import sys
from pathlib import Path

REPO     = Path(__file__).resolve().parents[3]
WEBSITE  = REPO / "website"

# ───────────────────────────────────────────────────────────────
# Markup snippets — both copied verbatim from sost-explorer.html
# so every page renders the same button + modal.
# ───────────────────────────────────────────────────────────────

WATCH_BUTTON = (
    '\n      '
    '<!-- 4th nav icon: open the SOST 2-minute intro video in a modal -->\n      '
    '<a href="javascript:void(0)" onclick="openSv()" '
    'style="display:inline-flex;flex-direction:column;align-items:center;'
    'justify-content:center;width:72px;height:72px;min-width:72px;'
    'border-radius:20%;background:linear-gradient(135deg,#0a1a22,#0e2530);'
    'border:1px solid rgba(34,211,238,.55);'
    'box-shadow:0 0 14px rgba(34,211,238,.40),0 0 22px rgba(34,211,238,.15);'
    'text-decoration:none;line-height:1;flex:0 0 auto;" '
    'title="Watch · SOST in 2 minutes">'
    '<span style="color:#22d3ee;font-size:26px;font-weight:900;'
    'text-shadow:0 0 8px rgba(34,211,238,.6);margin-bottom:2px">&#9654;</span>'
    '<span style="color:#22d3ee;font-size:9px;font-weight:700;'
    'letter-spacing:1px">WATCH</span>'
    '</a>'
)

MODAL_BLOCK = '''<!-- ════════════════════════════════════════════════════════════ -->
<!-- SOST intro video modal player (1:58, 1920x1080, H.264 / AAC) -->
<!-- ════════════════════════════════════════════════════════════ -->
<div id="sv-modal" class="sv-modal" aria-hidden="true" onclick="closeSv(event)">
  <div class="sv-content" onclick="event.stopPropagation()">
    <button class="sv-close" type="button" onclick="closeSv(null,true)" aria-label="Close">&times;</button>
    <video id="sv-video" class="sv-video" controls preload="metadata" playsinline>
      <source src="sost-intro.mp4" type="video/mp4">
      Your browser does not support HTML5 video.
    </video>
    <div class="sv-caption">SOST in 2 Minutes &middot; Sovereign by Design</div>
  </div>
</div>
<style>
  .sv-modal{
    display:none; position:fixed; inset:0; z-index:9999;
    background:rgba(0,0,0,.92); -webkit-backdrop-filter:blur(8px); backdrop-filter:blur(8px);
    align-items:center; justify-content:center;
  }
  .sv-modal.open{ display:flex; }
  .sv-content{ position:relative; max-width:92vw; max-height:88vh;
    display:flex; flex-direction:column; gap:14px; align-items:center; }
  .sv-video{ max-width:92vw; max-height:80vh; background:#000;
    border-radius:10px; box-shadow:0 0 60px rgba(251,1,13,.18); outline:none; }
  .sv-close{
    position:absolute; top:-46px; right:-2px;
    background:rgba(0,0,0,.8); border:1px solid rgba(255,255,255,.22);
    color:#fff; width:38px; height:38px; border-radius:50%;
    font-size:22px; line-height:1; cursor:pointer; padding:0;
    display:flex; align-items:center; justify-content:center;
  }
  .sv-close:hover{ background:rgba(251,1,13,.4); border-color:#fb010d; }
  .sv-caption{ text-align:center; font-size:11px; letter-spacing:3px;
    color:#94a3b8; font-family:'JetBrains Mono','IBM Plex Mono',monospace;
    text-transform:uppercase; }
</style>
<script>
  function openSv(){
    var m=document.getElementById('sv-modal');
    m.classList.add('open'); m.setAttribute('aria-hidden','false');
    document.body.style.overflow='hidden';
    var v=document.getElementById('sv-video');
    try{ v.currentTime=0; v.play().catch(function(){}); }catch(e){}
  }
  function closeSv(evt, force){
    if(evt && !force && evt.target.id!=='sv-modal') return;
    var m=document.getElementById('sv-modal');
    m.classList.remove('open'); m.setAttribute('aria-hidden','true');
    document.body.style.overflow='';
    var v=document.getElementById('sv-video');
    try{ v.pause(); }catch(e){}
  }
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape') closeSv(null,true);
  });
</script>
'''

# The unique anchor that closes the PoPC DEX rainbow button. It's
# the same across every page because the button HTML is copy-pasted
# everywhere. We pin the closing tag to avoid hitting any unrelated
# `</span></a>` sequence.
POPC_DEX_CLOSE_RE = re.compile(
    r'(letter-spacing:-1px;text-shadow:0 1px 0 rgba\(255,255,255,0\.18\)">'
    r'DEX</span></a>)',
    re.DOTALL,
)

BODY_CLOSE_RE = re.compile(r'</body>', re.IGNORECASE)


def patch(path: Path) -> str:
    """Return one of: 'ok', 'already', 'no-popc', 'no-body'."""
    src = path.read_text(encoding="utf-8")

    if "sv-modal" in src or "WATCH" in src and "Watch · SOST in 2 minutes" in src:
        # Already patched. Be conservative — do nothing.
        return "already"

    if not POPC_DEX_CLOSE_RE.search(src):
        return "no-popc"

    if not BODY_CLOSE_RE.search(src):
        return "no-body"

    # 1) Insert the WATCH button immediately after the PoPC DEX </a>.
    new_src, n_btn = POPC_DEX_CLOSE_RE.subn(r"\1" + WATCH_BUTTON, src, count=1)
    if n_btn != 1:
        return "no-popc"

    # 2) Insert the modal block immediately before </body>.
    new_src, n_mod = BODY_CLOSE_RE.subn(MODAL_BLOCK + "</body>", new_src, count=1)
    if n_mod != 1:
        return "no-body"

    path.write_text(new_src, encoding="utf-8")
    return "ok"


def main() -> int:
    pages = sorted(WEBSITE.glob("*.html"))
    if not pages:
        print(f"ERROR: no HTML pages in {WEBSITE}", file=sys.stderr)
        return 2

    counts = {"ok": 0, "already": 0, "no-popc": 0, "no-body": 0}
    rows   = []
    for p in pages:
        status = patch(p)
        counts[status] += 1
        rows.append((status, p.name))

    # Concise table grouped by status.
    for status_label, marker in (("ok", "+"), ("already", "·"),
                                  ("no-popc", "—"), ("no-body", "!")):
        names = [name for s, name in rows if s == status_label]
        if not names:
            continue
        print(f"\n[{marker}] {status_label}  ({len(names)} files)")
        for n in names:
            print(f"    {n}")

    print(f"\nTOTAL: +injected={counts['ok']}  "
          f"·already={counts['already']}  "
          f"—no-popc-button={counts['no-popc']}  "
          f"!no-body-tag={counts['no-body']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
