#!/bin/bash
# deploy-auth.sh — Deploy SOST Auth Gateway on VPS
# Run on VPS: cd /opt/sost && bash deploy/deploy-auth.sh
set -e

echo "=== SOST Auth Gateway Deployment ==="
echo ""

# 1. Install dependencies
echo "--- Installing Python dependencies ---"
pip3 install fastapi uvicorn pyotp --break-system-packages 2>/dev/null || pip3 install fastapi uvicorn pyotp
echo ""

# 2. Check auth.env exists
if [ ! -f /etc/sost/auth.env ]; then
    echo "ERROR: /etc/sost/auth.env not found!"
    echo "Run first: python3 -m auth.setup_admin"
    echo "Then create /etc/sost/auth.env with the output values."
    exit 1
fi
echo "--- /etc/sost/auth.env found ---"
chmod 600 /etc/sost/auth.env
echo ""

# 3. Test auth server starts
echo "--- Testing auth server ---"
timeout 3 python3 -c "
import sys; sys.path.insert(0, '.')
from auth.gateway import create_auth_app
app = create_auth_app()
print('Auth gateway created OK')
" || { echo "ERROR: Auth gateway failed to initialize"; exit 1; }
echo ""

# 4. Install systemd service
echo "--- Installing systemd service ---"
cp deploy/sost-auth.service /etc/systemd/system/sost-auth.service
systemctl daemon-reload
systemctl enable sost-auth
systemctl restart sost-auth
sleep 2
systemctl status sost-auth --no-pager -l | head -15
echo ""

# 5. Test auth endpoint
echo "--- Testing auth endpoint ---"
RESP=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8200/status 2>/dev/null)
if [ "$RESP" = "200" ]; then
    echo "Auth gateway responding on port 8200: OK"
    curl -s http://127.0.0.1:8200/status | python3 -m json.tool
else
    echo "WARNING: Auth gateway not responding (HTTP $RESP)"
    echo "Check logs: journalctl -u sost-auth -n 20"
fi
echo ""

# 6. Nginx config reminder
echo "--- Nginx Configuration ---"
echo "Add the contents of deploy/nginx-auth.conf to BOTH server blocks:"
echo "  /etc/nginx/sites-enabled/sost (sostcore.com)"
echo "  /etc/nginx/sites-enabled/sost (sostprotocol.com)"
echo ""
echo "Then run: sudo nginx -t && sudo systemctl reload nginx"
echo ""

# 7. Test via nginx (after manual nginx config)
echo "--- Quick Test Commands ---"
echo 'curl -s -X GET http://127.0.0.1:8200/status | python3 -m json.tool'
echo 'curl -s -X POST http://127.0.0.1:8200/login -H "Content-Type: application/json" -d '\''{"username":"test","password":"test"}'\'' | python3 -m json.tool'
echo ""
echo "=== Deployment Complete ==="
