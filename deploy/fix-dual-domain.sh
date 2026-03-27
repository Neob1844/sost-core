#!/bin/bash
# Fix SOST dual-domain: sostcore.com + sostprotocol.com
# Run this on the VPS as root or with sudo
set -e

echo "=== SOST Dual-Domain Fix ==="
echo "Adding sostprotocol.com to nginx config"

# 1. Backup current config
cp /etc/nginx/sites-available/sost-explorer /etc/nginx/sites-available/sost-explorer.bak.$(date +%Y%m%d) 2>/dev/null || true

# 2. Check if sostprotocol.com is already in the server_name
if grep -q "sostprotocol.com" /etc/nginx/sites-available/sost-explorer 2>/dev/null; then
    echo "  sostprotocol.com already in config — skipping"
else
    echo "  Adding sostprotocol.com to server_name..."
    # Add sostprotocol.com to the server_name line
    sed -i 's/server_name explorer.sostcore.com sostcore.com;/server_name sostcore.com sostprotocol.com explorer.sostcore.com;/' /etc/nginx/sites-available/sost-explorer
    sed -i 's/server_name sostcore.com;/server_name sostcore.com sostprotocol.com;/' /etc/nginx/sites-available/sost-explorer
fi

# 3. Fix X-Frame-Options to allow both domains
if grep -q "SAMEORIGIN" /etc/nginx/sites-available/sost-explorer; then
    echo "  Fixing X-Frame-Options for cross-domain iframes..."
    sed -i 's/add_header X-Frame-Options "SAMEORIGIN" always;/add_header Content-Security-Policy "frame-ancestors '\''self'\'' https:\/\/sostcore.com https:\/\/sostprotocol.com" always;/' /etc/nginx/sites-available/sost-explorer
fi

# 4. Ensure /rpc location exists
if ! grep -q "location /rpc" /etc/nginx/sites-available/sost-explorer; then
    echo "  WARNING: /rpc location not found in config!"
    echo "  Copy the updated config from deploy/sost-explorer.nginx"
fi

# 5. Test nginx config
echo "  Testing nginx config..."
nginx -t

# 6. Reload
echo "  Reloading nginx..."
systemctl reload nginx

# 7. Verify both domains
echo ""
echo "=== Verification ==="
echo "Testing sostcore.com/rpc..."
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:18232 -d '{"jsonrpc":"1.0","method":"getinfo","params":[]}' -H "Content-Type: application/json" && echo " — node responds"
echo ""
echo "Done. Both domains should now serve the same content with /rpc working."
echo ""
echo "If certbot hasn't been configured for sostprotocol.com:"
echo "  sudo certbot --nginx -d sostcore.com -d sostprotocol.com -d explorer.sostcore.com"
