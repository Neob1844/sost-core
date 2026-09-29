#!/usr/bin/env bash
# Install a SOST mainnet RELAY node (official v16.3.0, no mining). Idempotent.
# Does NOT start anything unless --start is given.
#   sudo ./install-relay-node.sh            # install + verify only
#   sudo ./install-relay-node.sh --start    # install, verify, enable and start
#   sudo ./install-relay-node.sh --uninstall
set -euo pipefail
REL=v16.3.0
NODE_SHA=304d056d504960b4179543672f14bee28146788b985363a5e95d476cc6b1492e
GEN_SHA=4e66143cbb49574e2681cf44f4c94ab8f5246ed1b5880640dd9c3c8d3020cdd0
BASE=https://github.com/Neob1844/sost-core/releases/download/$REL
GEN_URL=https://raw.githubusercontent.com/Neob1844/sost-core/$REL/genesis_block.json
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN=/usr/local/lib/sost/$REL; DATA=/var/lib/sost-relay; LOGD=/var/log/sost-relay

[[ $EUID -eq 0 ]] || { echo "run as root (it creates the 'sost' service user)"; exit 1; }

if [[ "${1:-}" == "--uninstall" ]]; then
  systemctl disable --now sost-relay-watchdog.timer sost-relay-node.service 2>/dev/null || true
  rm -f /etc/systemd/system/sost-relay-node.service /etc/systemd/system/sost-relay-watchdog.{service,timer}
  systemctl daemon-reload
  echo "units removed. Data kept in $DATA, config in /etc/sost/relay.env (delete by hand if wanted)."
  exit 0
fi

id sost >/dev/null 2>&1 || useradd --system --home "$DATA" --shell /usr/sbin/nologin sost
install -d -o sost -g sost -m 0750 "$DATA" "$LOGD" /var/lib/sost-relay-watchdog
install -d -m 0755 "$BIN" /etc/sost

fetch(){ curl -fsSL --retry 3 -o "$2" "$1"; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
fetch "$BASE/sost-node" "$tmp/sost-node"
got=$(sha256sum "$tmp/sost-node" | awk '{print $1}')
[[ "$got" == "$NODE_SHA" ]] || { echo "REFUSING: sost-node sha256 $got != $NODE_SHA"; exit 1; }
install -m 0755 "$tmp/sost-node" "$BIN/sost-node"
fetch "$GEN_URL" "$tmp/genesis_block.json"
got=$(sha256sum "$tmp/genesis_block.json" | awk '{print $1}')
[[ "$got" == "$GEN_SHA" ]] || { echo "REFUSING: genesis sha256 $got != $GEN_SHA"; exit 1; }
install -o sost -g sost -m 0640 "$tmp/genesis_block.json" "$DATA/genesis_block.json"
echo "verified: sost-node $NODE_SHA / genesis $GEN_SHA"

[[ -f /etc/sost/relay.env ]] || install -o root -g sost -m 0640 "$HERE/relay.env.example" /etc/sost/relay.env
if [[ ! -f /etc/sost/rpc.pass ]]; then
  ( umask 077; head -c 32 /dev/urandom | base64 | tr -d '/+=' > /etc/sost/rpc.pass )
fi
chown root:sost /etc/sost/rpc.pass; chmod 0640 /etc/sost/rpc.pass
install -m 0755 "$HERE/sost-relay-watchdog.sh" /usr/local/lib/sost/sost-relay-watchdog.sh
install -m 0644 "$HERE/sost-relay-node.service" /etc/systemd/system/sost-relay-node.service
install -m 0644 "$HERE/sost-relay-watchdog.service" /etc/systemd/system/sost-relay-watchdog.service
install -m 0644 "$HERE/sost-relay-watchdog.timer" /etc/systemd/system/sost-relay-watchdog.timer
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/sost-relay-node.service 2>&1 | grep -v "^$" || true

if [[ "${1:-}" == "--start" ]]; then
  systemctl enable --now sost-relay-node.service
  systemctl enable --now sost-relay-watchdog.timer
  echo "started. Follow: tail -f $LOGD/node.log"
else
  echo "installed, NOT started. Review /etc/sost/relay.env, then: $0 --start"
fi
