#!/usr/bin/env bash
# Driver-level tests for V15_NODE_CUTOVER.sh using an ssh/scp shim.
# Exercises the REAL driver, including the unknown-binary abort, against a fake
# VPS. Never contacts production.
set -uo pipefail

SIM="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${DEPLOY:-$(cd "$SIM/.." && pwd)}"
REAL_BUILD="${REAL_BUILD:-$(cd "$SIM/../../.." && pwd)/build-final}"
PASS=0; FAIL=0
chk() { if [ "$2" = "$3" ]; then echo "  [PASS] $1 ($2)"; PASS=$((PASS+1)); else echo "  [FAIL] $1: expected '$3' got '$2'"; FAIL=$((FAIL+1)); fi; }

D="$SIM/driver"; rm -rf "$D"; mkdir -p "$D/bin"

# ---- ssh / scp shims --------------------------------------------------------
cat > "$D/bin/ssh" <<'EOS'
#!/usr/bin/env bash
# args: [-o ...] [-i key] host  command...
cmd=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o|-i) shift 2;;
    *) if [ -z "${host:-}" ]; then host="$1"; shift; else cmd="$*"; break; fi;;
  esac
done
echo "SSH: $cmd" >> "$SHIMLOG"
case "$cmd" in
  ""|true) exit 0;;
  *getblockcount*)   printf '{"jsonrpc":"2.0","id":1,"result":%s}\n' "$(cat "$SHIMDIR/height")"; exit 0;;
  *"list-units"*)    echo 0; exit 0;;
  *sha256sum*sost-node*) cat "$SHIMDIR/installed_node_sha"; exit 0;;
  *"stat -c %s"*)    echo "    chain.json             341570789 bytes"; exit 0;;
  *"du -sk"*)        echo 340000; exit 0;;
  *"df -Pk"*)        echo 80000000; exit 0;;
  *mkdir*)           echo "WRITE:mkdir" >> "$SHIMLOG"; exit 0;;
  *chmod*)           echo "WRITE:chmod" >> "$SHIMLOG"; exit 0;;
  *sha256sum\ -c*|*REMOTE_SHA*) echo "WRITE:stage-verify" >> "$SHIMLOG"; echo REMOTE_SHA_OK; exit 0;;
  *systemd-run*)     echo "WRITE:systemd-run" >> "$SHIMLOG"; exit 0;;
  *grep*state*)      exit 0;;
  *) exit 0;;
esac
EOS
cat > "$D/bin/scp" <<'EOS'
#!/usr/bin/env bash
echo "WRITE:scp $*" >> "$SHIMLOG"
exit 0
EOS
chmod +x "$D/bin/ssh" "$D/bin/scp"

run_driver() {                 # run_driver <installed_sha> <args...>
  local sha="$1"; shift
  rm -f "$D/shim.log"; : > "$D/shim.log"
  echo "$sha"  > "$D/installed_node_sha"
  echo "22037" > "$D/height"
  PATH="$D/bin:$PATH" SHIMLOG="$D/shim.log" SHIMDIR="$D" \
  VPS_SSH_KEY="$D/fake.key" BUILD_DIR="$REAL_BUILD" \
  bash "$DEPLOY/V15_NODE_CUTOVER.sh" "$@" > "$D/out.txt" 2>&1
  echo $?
}
touch "$D/fake.key"
writes() { awk '/^WRITE:/{n++} END{print n+0}' "$D/shim.log" 2>/dev/null; }

RELEASE_SHA="8c8ff89740d1b43a8c925d7d9ec398e4989a3d4de5759785aa84e3945b79bc4c"
PRE_SHA="f7c625fd7b203fd140f0142208ab1184fd69358187ececf36d13e9962d0e6661"
UNKNOWN_SHA="deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

echo "=============================================================="
echo "V15 driver tests (ssh/scp shimmed — no production contact)"
echo "=============================================================="

echo; echo "D1: UNKNOWN installed binary + --yes  -> MUST ABORT"
rc="$(run_driver "$UNKNOWN_SHA" --yes)"
chk "exit non-zero" "$rc" "1"
chk "says UNRECOGNISED" "$(grep -c 'UNRECOGNISED' "$D/out.txt")" "1"
chk "mentions --force-unknown-binary" "$(grep -c 'force-unknown-binary' "$D/out.txt")" "1"
chk "NO writes to the VPS" "$(writes)" "0"

echo; echo "D2: UNKNOWN installed binary + --yes --dry-run -> STILL ABORTS"
rc="$(run_driver "$UNKNOWN_SHA" --yes --dry-run)"
chk "exit non-zero" "$rc" "1"
chk "NO writes to the VPS" "$(writes)" "0"

echo; echo "D3: UNKNOWN + explicit --force-unknown-binary --dry-run -> proceeds"
rc="$(run_driver "$UNKNOWN_SHA" --yes --dry-run --force-unknown-binary)"
chk "exit 0" "$rc" "0"
chk "warned about the override" "$(grep -c 'force-unknown-binary given' "$D/out.txt")" "1"
chk "dry-run still wrote NOTHING" "$(writes)" "0"

echo; echo "D4: expected pre-cutover binary + --dry-run -> READ-ONLY, exit 0"
rc="$(run_driver "$PRE_SHA" --yes --dry-run)"
chk "exit 0" "$rc" "0"
chk "declares read-only" "$(grep -c 'READ-ONLY and nothing was written' "$D/out.txt")" "1"
chk "NO writes to the VPS" "$(writes)" "0"

echo; echo "D5: release already installed -> idempotent no-op"
rc="$(run_driver "$RELEASE_SHA" --yes)"
chk "exit 0" "$rc" "0"
chk "reports already installed" "$(grep -c 'ALREADY installed' "$D/out.txt")" "1"
chk "NO writes to the VPS" "$(writes)" "0"

echo; echo "D6: unreadable installed hash -> refuses to proceed blind"
rc="$(run_driver "" --yes)"
chk "exit non-zero" "$rc" "1"
chk "refuses blind" "$(grep -c 'refusing to proceed blind' "$D/out.txt")" "1"
chk "NO writes to the VPS" "$(writes)" "0"

echo; echo "D7: local binaries verified against the manifest (real build-final)"
chk "hash gate ran on real binaries" "$(grep -c 'sost-node sha256 verified' "$D/out.txt")" "1"

echo
echo "=============================================================="
echo "  driver results: $PASS passed, $FAIL failed"
echo "=============================================================="
[ "$FAIL" -eq 0 ]
