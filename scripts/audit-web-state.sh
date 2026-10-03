#!/usr/bin/env bash
# =============================================================================
# audit-web-state.sh  —  SOST public-web consistency audit (section 13)
# =============================================================================
# READ-ONLY. Scans the public website/*.html against the single source of truth
# website/protocol-status.json and flags content that would misrepresent the
# live protocol if deployed:
#
#   1. Manifest validity + invariants (the source of truth must be well-formed)
#   2. "current release" strings that contradict the manifest release
#   3. Release-candidate / RC tags that must never ship on a public page
#   4. V30000-gated features bound to the wrong activation height
#   5. Public-trading / public-access asserted ENABLED while the manifest says
#      public_trading=false (admin-gated)
#   6. The SOST L1 / mainnet mislabelled as testnet or "not yet live"
#
# Exit 0 = PASS (safe to deploy).  Exit 1 = FAIL (fix before deploying).
# The script NEVER edits any file; it only reports. Run before every deploy:
#     scripts/audit-web-state.sh
# =============================================================================
set -uo pipefail

# --- Locate the website dir relative to this script (repo-root independent) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/website"
MANIFEST="$WEB_DIR/protocol-status.json"

FAIL=0
pass(){ printf '  [PASS] %s\n' "$1"; }
fail(){ FAIL=1; printf '  [FAIL] %s\n' "$1"; }
note(){ printf '         %s\n' "$1"; }

echo "========================================================================"
echo " SOST WEB STATE AUDIT"
echo " web dir : $WEB_DIR"
echo " manifest: $MANIFEST"
echo "========================================================================"

if [ ! -d "$WEB_DIR" ]; then
  echo "  [FAIL] website directory not found: $WEB_DIR"
  echo "RESULT: FAIL"
  exit 1
fi

cd "$WEB_DIR" || { echo "  [FAIL] cannot cd to website dir"; echo "RESULT: FAIL"; exit 1; }

# ----------------------------------------------------------------------------
# CHECK 1 — manifest validity + expected invariants
# ----------------------------------------------------------------------------
echo
echo "[1] MANIFEST (single source of truth)"
REL=""; RELTAG=""; ACT=""
if [ ! -f "$MANIFEST" ]; then
  fail "protocol-status.json missing"
else
  MAN_JSON="$(python3 - "$MANIFEST" <<'PY'
import json,sys
try:
    d=json.load(open(sys.argv[1]))
except Exception as e:
    print("PARSE_ERROR:%s"%e); sys.exit(0)
req=["release","release_tag","activation_height","dex_protocol_status",
     "tokenization_status","public_trading","admin_gate","S14",
     "native_assets","jackpot_v2","security_mode","last_updated"]
miss=[k for k in req if k not in d]
if miss:
    print("MISSING:%s"%(",".join(miss)))
# invariants expected for the current (V30000) truth
inv=[]
if str(d.get("release"))!="V30000": inv.append("release!=V30000(%s)"%d.get("release"))
if str(d.get("release_tag"))!="v30000": inv.append("release_tag!=v30000(%s)"%d.get("release_tag"))
if d.get("activation_height")!=30000: inv.append("activation_height!=30000(%s)"%d.get("activation_height"))
if d.get("public_trading") is not False: inv.append("public_trading not false(%s)"%d.get("public_trading"))
if d.get("admin_gate") is not True: inv.append("admin_gate not true(%s)"%d.get("admin_gate"))
if str(d.get("security_mode"))!="SEC2": inv.append("security_mode!=SEC2(%s)"%d.get("security_mode"))
for i in inv: print("INV:%s"%i)
print("OK release=%s release_tag=%s activation=%s"%(d.get("release"),d.get("release_tag"),d.get("activation_height")))
PY
)"
  if echo "$MAN_JSON" | grep -q '^PARSE_ERROR:'; then
    fail "protocol-status.json does not parse"
    note "$(echo "$MAN_JSON" | grep '^PARSE_ERROR:')"
  else
    if echo "$MAN_JSON" | grep -q '^MISSING:'; then
      fail "protocol-status.json missing required field(s)"
      note "$(echo "$MAN_JSON" | grep '^MISSING:')"
    fi
    if echo "$MAN_JSON" | grep -q '^INV:'; then
      fail "protocol-status.json invariant mismatch"
      echo "$MAN_JSON" | grep '^INV:' | while read -r l; do note "${l#INV:}"; done
    fi
    if echo "$MAN_JSON" | grep -q '^OK '; then
      pass "manifest parses and matches expected V30000 invariants"
      note "$(echo "$MAN_JSON" | grep '^OK ')"
    fi
    REL="$(python3 -c 'import json;print(json.load(open("'"$MANIFEST"'"))["release"])' 2>/dev/null)"
    RELTAG="$(python3 -c 'import json;print(json.load(open("'"$MANIFEST"'"))["release_tag"])' 2>/dev/null)"
    ACT="$(python3 -c 'import json;print(json.load(open("'"$MANIFEST"'"))["activation_height"])' 2>/dev/null)"
  fi
fi
[ -z "$REL" ] && REL="V30000"
[ -z "$RELTAG" ] && RELTAG="v30000"
[ -z "$ACT" ] && ACT="30000"

# ----------------------------------------------------------------------------
# CHECK 2 — "current release" strings must agree with the manifest release
# ----------------------------------------------------------------------------
echo
echo "[2] CURRENT-RELEASE STRINGS vs manifest ($REL)"
# Only flag a "current release" line that NAMES a version token (Vnn / vnn.n)
# which is not the manifest release. A line that merely uses the phrase
# "current release" without a version (e.g. "not tradeable in the current
# release") is not a contradiction and is not flagged.
CR_HITS="$(grep -rniE 'current release' -- *.html 2>/dev/null \
            | grep -iE 'V[0-9]{2,}|v[0-9]+\.[0-9]' \
            | grep -viE "$REL" || true)"
if [ -n "$CR_HITS" ]; then
  fail "a 'current release' string names a version other than the manifest release ($REL)"
  echo "$CR_HITS" | while IFS= read -r l; do note "$l"; done
else
  pass "every version-naming 'current release' string names $REL"
fi

# ----------------------------------------------------------------------------
# CHECK 3 — release-candidate tags that must never ship publicly
#   (historical '<tag>-rc1' on spec/release-notes pages for OLD versions such
#    as v13-rc1 are legitimate; we only forbid an RC of the CURRENT release)
# ----------------------------------------------------------------------------
echo
echo "[3] RELEASE-CANDIDATE TAGS ($RELTAG must be final, not an RC)"
RC_HITS="$(grep -rniE "${RELTAG}[- ]?rc[0-9]*|${REL}[- ]?rc[0-9]*|${RELTAG}[- ]?rc-final" -- *.html 2>/dev/null || true)"
if [ -n "$RC_HITS" ]; then
  fail "a release-candidate tag of the current release appears on a public page"
  echo "$RC_HITS" | while IFS= read -r l; do note "$l"; done
else
  pass "no ${RELTAG}-rc* / ${REL}-rc* tokens on any public page"
fi

# ----------------------------------------------------------------------------
# CHECK 4 — V30000-gated features bound to the wrong activation height
#   The height is matched ONLY when it is directly bound to the feature's
#   activation verb, so multi-topic paragraphs that also mention historical
#   heights (#25,000, #16,000, ...) do not false-positive.
# ----------------------------------------------------------------------------
echo
echo "[4] V30000 FEATURE ACTIVATION HEIGHT (must be #$ACT)"
ACT_FMT="$(printf '%s' "$ACT" | sed -E 's/([0-9]+)([0-9]{3})$/\1,\2/')"   # 30000 -> 30,000
FEAT_RE='(SOST-layer DEX|native[- ]asset layer|four tokenization modalit[a-z]*|DTD Accumulated Reward V2)'
BIND_RE="${FEAT_RE}[^.<]{0,45}activat[a-z]* (at|by|from)?[ a-z]*(block )?#?[0-9]{1,3},?[0-9]{3}"
# lines where a feature is bound to an activation height != the manifest height
FEAT_BAD="$(grep -rnoiE "$BIND_RE" -- *.html 2>/dev/null | grep -viE "#?${ACT}([^0-9]|$)|#?${ACT_FMT}([^0-9]|$)" || true)"
if [ -n "$FEAT_BAD" ]; then
  fail "a V30000 feature is bound to an activation height other than #$ACT_FMT"
  echo "$FEAT_BAD" | while IFS= read -r l; do note "$l"; done
else
  pass "every V30000 feature activation is bound to #$ACT_FMT"
fi
# first V2 draw must be #30,186
V2_BAD="$(grep -rnoiE 'first V2 draw[^.<]{0,15}#?[0-9]{1,3},?[0-9]{3}' -- *.html 2>/dev/null | grep -viE '#?30,?186' || true)"
if [ -n "$V2_BAD" ]; then
  fail "'first V2 draw' bound to a height other than #30,186"
  echo "$V2_BAD" | while IFS= read -r l; do note "$l"; done
else
  pass "'first V2 draw' is #30,186 wherever bound"
fi

# ----------------------------------------------------------------------------
# CHECK 5 — public trading / public access asserted ENABLED
#   Manifest: public_trading=false, admin_gate=true (S14 restricted). Any page
#   claiming trading/public access is enabled/live/open is a contradiction.
# ----------------------------------------------------------------------------
echo
echo "[5] PUBLIC TRADING / PUBLIC ACCESS (manifest public_trading=false)"
PT_HITS="$(grep -rniE 'public[ -](access|trading)[^.]{0,30}(enabled|is live|now live|is open|now open|available now)' -- *.html 2>/dev/null | grep -viE 'disabled|not (yet )?(enabled|live|open|available)' || true)"
if [ -n "$PT_HITS" ]; then
  fail "public trading/access asserted ENABLED while manifest says it is off"
  echo "$PT_HITS" | while IFS= read -r l; do note "$l"; done
else
  pass "no page asserts public trading/access is enabled"
fi

# ----------------------------------------------------------------------------
# CHECK 6 — SOST L1 / mainnet mislabelled as testnet or "not yet live"
#   The protocol has been live (mainnet) since genesis. Legitimate protocol
#   descriptions of the network-byte ("mainnet vs testnet", "mainnet/testnet/
#   dev") and the historical Sepolia escrow alpha are excluded.
# ----------------------------------------------------------------------------
echo
echo "[6] TESTNET / FUTURE MISLABEL of the live mainnet"
TN_HITS="$(grep -rniE 'SOST[^.]{0,25}(is (still )?(on |a )?testnet|testnet only|testnet phase)|mainnet[^.]{0,30}(coming soon|not yet live|has not launched|launching soon|is a testnet)' -- *.html 2>/dev/null | grep -viE 'sepolia|escrow|mainnet vs testnet|mainnet/testnet|mainnet or testnet' || true)"
if [ -n "$TN_HITS" ]; then
  fail "the live SOST mainnet is mislabelled as testnet / not-yet-live"
  echo "$TN_HITS" | while IFS= read -r l; do note "$l"; done
else
  pass "no mislabel of the live mainnet as testnet / future"
fi

# ----------------------------------------------------------------------------
echo
echo "========================================================================"
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS  — website is consistent with protocol-status.json ($REL)"
  echo "========================================================================"
  exit 0
else
  echo "RESULT: FAIL  — fix the issues above before deploying"
  echo "========================================================================"
  exit 1
fi
