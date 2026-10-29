#!/usr/bin/env bash
# =============================================================================
# setup_sost_seed_node.sh — one-shot to stand up a SOST seed node (V14.5) on a
# CLEAN Ubuntu 24.04 VPS.
#
# Seed = P2P bootstrap/relay node. It does NOT mine, holds NO wallet, NO private
# keys, and exposes NO public RPC (RPC binds to 127.0.0.1 only). Run as root on a
# fresh machine intended to be a regional seed (US / APAC / community).
#
#   curl -fsSL https://raw.githubusercontent.com/Neob1844/sost-core/main/scripts/setup_sost_seed_node.sh | sudo bash
#   # or: scp it over, then: sudo bash setup_sost_seed_node.sh
#
# Does NOT touch consensus, web, or any wallet. P2P seed only.
# =============================================================================
set -euo pipefail

# ===== CONFIG =====
SOST_DIR=/opt/sost
SVC_USER=sost
REPO=https://github.com/Neob1844/sost-core.git
# RPC is localhost-only; random creds (the node requires them even on loopback):
RPC_USER="seed_$(head -c4 /dev/urandom | od -An -tx1 | tr -d ' ')"
RPC_PASS="$(head -c24 /dev/urandom | od -An -tx1 | tr -d ' ')"

echo "== SOST seed node setup (V14.5) =="

# ===== 1) DEPENDENCIES =====
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y build-essential cmake git pkg-config libssl-dev libsecp256k1-dev ufw curl

# ===== 2) SERVICE USER (no login) =====
id -u "$SVC_USER" &>/dev/null || useradd --system --create-home --shell /usr/sbin/nologin "$SVC_USER"

# ===== 3) CLONE + main =====
if [ -d "$SOST_DIR/.git" ]; then cd "$SOST_DIR"; git fetch origin; else git clone "$REPO" "$SOST_DIR"; cd "$SOST_DIR"; fi
git checkout main
git pull origin main

# ===== 4) BUILD (flags are MANDATORY — exactly these three) =====
cmake -S . -B build \
  -DSOST_ENABLE_PHASE2_SBPOW=ON \
  -DSOST_TESTNET_FORKS=OFF \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build --target sost-node sost-cli -j"$(nproc)"
# sanity: binary carries the V14.5 multi-seed list (PR #33)
strings build/sost-node | grep -q seed-apac.sostcore.com && echo "[ok] binary carries multi-seed V14.5"

# ===== 5) OWNERSHIP =====
chown -R "$SVC_USER":"$SVC_USER" "$SOST_DIR"

# ===== 6) FIREWALL — allow SSH FIRST so you don't lock yourself out =====
ufw allow 22/tcp           # SSH — must precede 'ufw enable'
ufw allow 19333/tcp        # SOST P2P — the only public port a seed needs
# RPC 18232 is NOT opened (and binds to 127.0.0.1 by default — double-safe)
yes | ufw enable

# ===== 7) SYSTEMD SERVICE (seed: localhost RPC, no wallet, no miner) =====
cat >/etc/systemd/system/sost-seed.service <<EOF
[Unit]
Description=SOST seed node (P2P, mainnet)
After=network-online.target
Wants=network-online.target
[Service]
User=$SVC_USER
WorkingDirectory=$SOST_DIR/build
ExecStart=$SOST_DIR/build/sost-node --genesis $SOST_DIR/genesis_block.json --chain chain.json --rpc-user $RPC_USER --rpc-pass $RPC_PASS --profile mainnet
Restart=always
RestartSec=5
LimitNOFILE=8192
[Install]
WantedBy=multi-user.target
EOF

# ===== 8) START + ENABLE AT BOOT =====
systemctl daemon-reload
systemctl enable --now sost-seed

# ===== 9) VERIFY =====
sleep 10
echo "--- service:";       systemctl is-active sost-seed
echo "--- P2P 19333:";     ss -ltnp | grep ':19333' && echo "  listening" || echo "  NOT listening (check: journalctl -u sost-seed -n 50)"
echo "--- RPC private:";   ss -ltnp | grep ':18232' | grep -q '127.0.0.1' && echo "  127.0.0.1 only (private) OK" || echo "  check bind"
echo "--- node:";          curl -s --max-time 8 --user "$RPC_USER:$RPC_PASS" \
  --data-binary '{"jsonrpc":"2.0","id":1,"method":"getinfo","params":[]}' http://127.0.0.1:18232/ \
  | python3 -c "import sys,json;d=json.load(sys.stdin)['result'];print('  blocks=%s testnet=%s profile=%s peers=%s'%(d['blocks'],d['testnet'],d['profile'],d['connections']))" 2>/dev/null \
  || echo "  (still starting; retry in ~30s)"
echo
echo ">>> RPC_USER=$RPC_USER  RPC_PASS=$RPC_PASS   (localhost only — keep them)"
echo ">>> The node is syncing from peers; 'blocks' rises until it reaches the tip."
echo
cat <<'NEXT'
NEXT STEPS
  - From another machine, confirm the P2P port is reachable:
        nc -vz <THIS_VPS_PUBLIC_IP> 19333      # expect 'succeeded' / 'open'
  - Point a regional DNS A-record at this VPS's public IP:
        seed-us.sostcore.com    A   <IP>       # North America
        seed-apac.sostcore.com  A   <IP>       # Asia-Pacific (or a community node)
    No binary change needed — new nodes pick it up once DNS resolves.
  - Changing VPS/IP later: just update the A-record; nothing to edit on the node.

FUTURE UPDATE (new binary):
  cd /opt/sost && git checkout main && git pull origin main
  cmake -S . -B build -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF -DCMAKE_BUILD_TYPE=Release
  cmake --build build --target sost-node sost-cli -j"$(nproc)"
  chown -R sost:sost /opt/sost
  systemctl restart sost-seed && systemctl status sost-seed --no-pager | head -5
NEXT
