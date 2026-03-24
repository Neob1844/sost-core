#!/bin/bash
# diagnose-domains.sh — Run on VPS to diagnose why sostprotocol.com lacks CRT/sounds
# Usage: ssh your-vps 'bash -s' < deploy/diagnose-domains.sh

echo "=== SOST Domain Diagnostic ==="
echo ""

echo "--- 1. Nginx sites-enabled ---"
ls -la /etc/nginx/sites-enabled/ 2>/dev/null || echo "No sites-enabled directory"

echo ""
echo "--- 2. Server blocks (server_name + root) ---"
for f in /etc/nginx/sites-enabled/*; do
    echo ""
    echo "=== $f ==="
    grep -E "server_name|root " "$f" 2>/dev/null
done

echo ""
echo "--- 3. Webroot contents ---"
echo "sostcore.com root:"
ls -la /var/www/sostcore.com/ 2>/dev/null | head -8 || echo "NOT FOUND"
echo ""
echo "sostprotocol root (if separate):"
ls -la /var/www/sostprotocol/ 2>/dev/null | head -8 || ls -la /var/www/sostprotocol.com/ 2>/dev/null | head -8 || echo "NOT FOUND"
echo ""
echo "opt/sost/website:"
ls -la /opt/sost/website/ 2>/dev/null | head -8 || echo "NOT FOUND"

echo ""
echo "--- 4. CRT files check ---"
echo "sostcore.com:"
ls -la /var/www/sostcore.com/css/crt-effects.css /var/www/sostcore.com/js/crt-effects.js /var/www/sostcore.com/js/retro-sounds.js 2>/dev/null || echo "MISSING CRT FILES"
echo ""
echo "sostprotocol (check both possible roots):"
for root in /var/www/sostprotocol /var/www/sostprotocol.com /var/www/html; do
    if [ -d "$root" ]; then
        echo "  $root:"
        ls -la "$root/css/crt-effects.css" "$root/js/crt-effects.js" "$root/js/retro-sounds.js" 2>/dev/null || echo "    MISSING CRT FILES in $root"
    fi
done

echo ""
echo "--- 5. Fix instructions ---"
echo ""
echo "IF sostprotocol.com uses a DIFFERENT root than sostcore.com:"
echo "  Option A (recommended): Change nginx root to match sostcore.com"
echo "    Edit /etc/nginx/sites-enabled/sostprotocol (or similar)"
echo "    Change: root /var/www/whatever;"
echo "    To:     root /var/www/sostcore.com;"
echo "    Then:   sudo nginx -t && sudo systemctl reload nginx"
echo ""
echo "  Option B: Symlink"
echo "    ln -sf /var/www/sostcore.com /var/www/sostprotocol.com"
echo "    sudo nginx -t && sudo systemctl reload nginx"
echo ""
echo "IF they already share the same root:"
echo "  The issue is stale files. Run:"
echo "    cd /opt/sost && git pull origin main"
echo "    cp -r website/* /var/www/sostcore.com/"
echo "    sudo systemctl reload nginx"
echo ""
echo "=== END DIAGNOSTIC ==="
