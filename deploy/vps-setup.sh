#!/bin/bash
# ===========================================================================
# SOST Protocol — VPS Deployment Script
# Run on a fresh Ubuntu 24.04 VPS (4GB+ RAM)
# ===========================================================================
set -e

echo "=== SOST VPS Deployment ==="
echo "This script sets up a SOST seed node + explorer on Ubuntu 24.04"
echo ""

# ---------- 1. System dependencies ----------
echo "[1/7] Installing dependencies..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential cmake libssl-dev libsecp256k1-dev \
    nginx certbot python3-certbot-nginx ufw git

# ---------- 2. Create sost user ----------
echo "[2/7] Creating sost user..."
sudo useradd -r -m -d /opt/sost -s /bin/bash sost || true

# ---------- 3. Clone and build ----------
echo "[3/7] Cloning and building sost-core..."
sudo -u sost bash -c '
    cd /opt/sost
    git clone https://github.com/Neob1844/sost-core.git repo
    cd repo
    mkdir -p build && cd build
    cmake .. -DCMAKE_BUILD_TYPE=Release
    make -j$(nproc)
'

# Create symlinks for convenience
sudo -u sost bash -c '
    ln -sf /opt/sost/repo/build /opt/sost/build
    ln -sf /opt/sost/repo/genesis_block.json /opt/sost/genesis_block.json
'

# ---------- 4. Configure credentials ----------
echo "[4/7] Configuring RPC credentials..."
echo ""
echo "  ⚠️  IMPORTANT: Edit the systemd service files and replace CHANGE_ME"
echo "  with your actual RPC username and password BEFORE starting services."
echo ""
read -p "  RPC username: " RPC_USER
read -sp "  RPC password: " RPC_PASS
echo ""

# ---------- 5. Install systemd services ----------
echo "[5/7] Installing systemd services..."
sudo cp /opt/sost/repo/deploy/sost-node.service /etc/systemd/system/
sudo cp /opt/sost/repo/deploy/sost-miner.service /etc/systemd/system/

# Replace credentials
sudo sed -i "s/CHANGE_ME/${RPC_USER}/1" /etc/systemd/system/sost-node.service
sudo sed -i "s/CHANGE_ME/${RPC_PASS}/2" /etc/systemd/system/sost-node.service
sudo sed -i "s/CHANGE_ME/${RPC_USER}/1" /etc/systemd/system/sost-miner.service
sudo sed -i "s/CHANGE_ME/${RPC_PASS}/2" /etc/systemd/system/sost-miner.service

sudo systemctl daemon-reload

# ---------- 6. Firewall ----------
echo "[6/7] Configuring firewall..."
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 19333/tcp   # P2P
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
# NOTE: RPC port 18232 is NOT opened — only accessible via localhost
sudo ufw --force enable

# ---------- 7. Explorer deployment ----------
echo "[7/7] Deploying explorer..."
sudo mkdir -p /var/www/sost
sudo cp /opt/sost/repo/explorer.html /var/www/sost/
sudo cp /opt/sost/repo/deploy/sost-explorer.nginx /etc/nginx/sites-available/sost-explorer
sudo ln -sf /etc/nginx/sites-available/sost-explorer /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# ---------- Done ----------
echo ""
echo "=========================================="
echo "  SOST VPS Setup Complete!"
echo "=========================================="
echo ""
echo "  Next steps:"
echo "  1. Copy chain.json from local machine:"
echo "     scp chain.json sost@YOUR_VPS:/opt/sost/"
echo ""
echo "  2. Create/copy wallet.json:"
echo "     scp wallet.json sost@YOUR_VPS:/opt/sost/"
echo ""
echo "  3. Start node:"
echo "     sudo systemctl start sost-node"
echo "     sudo systemctl enable sost-node"
echo ""
echo "  4. Start miner:"
echo "     sudo systemctl start sost-miner"
echo "     sudo systemctl enable sost-miner"
echo ""
echo "  5. Get SSL certificate:"
echo "     sudo certbot --nginx -d explorer.sostcore.com"
echo ""
echo "  6. Connect local node to VPS:"
echo "     ./sost-node --connect YOUR_VPS_IP:19333 ..."
echo ""
echo "  7. Check status:"
echo "     sudo systemctl status sost-node"
echo "     sudo journalctl -u sost-node -f"
echo "     curl -s -u ${RPC_USER}:${RPC_PASS} -X POST \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"getinfo\",\"params\":[]}' \\"
echo "       http://127.0.0.1:18232"
echo ""
