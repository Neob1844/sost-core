#!/usr/bin/env bash
#
# check_dashboard_separation.sh
#
# Guards the user-facing dashboard separation between the Atomic Swap DEX and
# PoPC Bond Staking. While PoPC contract/position trading is disabled in V15
# (POPC_DEX_ENABLED stays false), none of the legacy "PoPC position trading"
# UI strings may appear as *visible* markup on the public pages.
#
# It checks the VISIBLE body only: <script>...</script> blocks and HTML
# comments (<!-- ... -->) are stripped before grepping, so gated/commented
# legacy code that never renders is allowed. Any forbidden string left in the
# rendered markup fails the check (exit != 0).
#
# Usage:  scripts/check_dashboard_separation.sh
#
set -u

# Resolve the website directory relative to this script (repo-root/website).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)/website"

PAGES=(
  "sost-dex.html"
  "sost-deal-channel.html"
  "sost-popc.html"
  "sost-wallet.html"
)

# Legacy PoPC position-trading strings that must NOT be visible while
# POPC_DEX_ENABLED is false.
FORBIDDEN=(
  "PoPC DEX"
  "Sell Full"
  "Sell Reward"
  "full_position"
  "Position Trades"
  "Live position data from PoPC escrow"
  "SOSTEscrow V2"
)

fail=0

for page in "${PAGES[@]}"; do
  path="${WEB_DIR}/${page}"
  if [[ ! -f "${path}" ]]; then
    echo "MISSING: ${path}"
    fail=1
    continue
  fi

  # Strip <script>...</script> and <!-- ... --> so only visible markup remains.
  visible="$(python3 - "${path}" <<'PY'
import re, sys
src = open(sys.argv[1], encoding="utf-8", errors="replace").read()
src = re.sub(r"<script\b[^>]*>.*?</script>", " ", src, flags=re.S | re.I)
src = re.sub(r"<!--.*?-->", " ", src, flags=re.S)
sys.stdout.write(src)
PY
)"

  for s in "${FORBIDDEN[@]}"; do
    if printf '%s' "${visible}" | grep -qF "${s}"; then
      echo "FAIL: ${page} -> visible legacy string: \"${s}\""
      fail=1
    fi
  done
done

if [[ "${fail}" -ne 0 ]]; then
  echo ""
  echo "Dashboard separation check FAILED: legacy PoPC position-trading UI is still visible."
  exit 1
fi

echo "OK: dashboard separation clean — no legacy PoPC position-trading strings in visible UI."
echo "    pages checked: ${PAGES[*]}"
exit 0
