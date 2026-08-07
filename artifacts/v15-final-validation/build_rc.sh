#!/usr/bin/env bash
# P8 — V15 Release Candidate build (NO merge, NO production tag). Clean Release build of the
# MAINNET-profile production binaries from the current branch HEAD, with SHA-256 manifest, build
# metadata, and a dev-symbol leak check. Reproducible: pins commit + compiler + flags.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
RC=build-rc
OUT=artifacts/v15-final-validation
COMMIT="$(git rev-parse HEAD)"
CXXV="$(g++ --version | head -1)"
echo "[rc] configuring clean Release build ($RC) — mainnet profile (no DEVNET/TESTNET flags)"
rm -rf "$RC"
nice -n 19 ionice -c3 cmake -S . -B "$RC" -DCMAKE_BUILD_TYPE=Release > "$OUT/rc-configure.log" 2>&1
echo "[rc] building node/cli/miner/signtx…"
nice -n 19 ionice -c3 cmake --build "$RC" --target sost-node sost-cli sost-miner sost-signtx -j2 \
  > "$OUT/rc-build.log" 2>&1
echo "[rc] === dev-symbol leak check (MUST be empty in every production binary) ==="
LEAK=0
for b in sost-node sost-cli sost-miner sost-signtx; do
  [[ -x "$RC/$b" ]] || { echo "  MISSING $b"; LEAK=1; continue; }
  hit=$(strings "$RC/$b" | grep -E 'devjackpotstate|devsetreorgfailpoint|devchainstate|inject-tx-at1|attack-jackpot|dump-block' | head)
  if [[ -n "$hit" ]]; then echo "  LEAK in $b: $hit"; LEAK=1; else echo "  $b clean"; fi
done
echo "[rc] === manifest ==="
{
  echo "SOST V15 Release Candidate manifest"
  echo "commit:   $COMMIT"
  echo "branch:   $(git branch --show-current)"
  echo "built:    (stamp at run time — see file mtime)"
  echo "compiler: $CXXV"
  echo "cmake:    $(cmake --version | head -1)"
  echo "profile:  MAINNET (SOST_DEVNET_FORKS=OFF, SOST_TESTNET_FORKS=OFF)  V15_HEIGHT=25000"
  echo "build:    cmake -S . -B build-rc -DCMAKE_BUILD_TYPE=Release && cmake --build build-rc --target sost-node sost-cli sost-miner sost-signtx"
  echo "dev-symbol-leak-check: $([[ $LEAK -eq 0 ]] && echo CLEAN || echo FAILED)"
  echo ""
  echo "SHA-256:"
  ( cd "$RC" && sha256sum sost-node sost-cli sost-miner sost-signtx )
} | tee "$OUT/RC_MANIFEST.txt"
echo "[rc] RESULT: $([[ $LEAK -eq 0 ]] && echo RC_ARTIFACTS_READY || echo LEAK_DETECTED)"
exit $LEAK
