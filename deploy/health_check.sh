#!/bin/bash
# SOST Health Check — every 5 min via cron
# crontab: */5 * * * * /opt/sost/deploy/health_check.sh
LOG=/var/log/sost-health.log
NOW=$(date '+%Y-%m-%d %H:%M:%S')

# 1. Check node RPC
if ! curl -sf -m 5 -d '{"method":"getinfo","params":[],"id":1}' http://127.0.0.1:18232/ > /dev/null 2>&1; then
    echo "[$NOW] CRITICAL — Node not responding, restarting..." >> $LOG
    systemctl restart sost-node 2>/dev/null
    sleep 10
    if curl -sf -m 5 -d '{"method":"getinfo","params":[],"id":1}' http://127.0.0.1:18232/ > /dev/null 2>&1; then
        echo "[$NOW] Node recovered after restart" >> $LOG
    else
        echo "[$NOW] CRITICAL — Node restart FAILED" >> $LOG
    fi
fi

# 2. Check nginx
if ! curl -sf -m 5 https://sostcore.com > /dev/null 2>&1; then
    echo "[$NOW] HIGH — Nginx not responding, restarting..." >> $LOG
    systemctl restart nginx 2>/dev/null
fi

# 3. Check auth gateway
if ! curl -sf -m 5 http://127.0.0.1:8200/health > /dev/null 2>&1; then
    echo "[$NOW] MEDIUM — Auth gateway down, restarting..." >> $LOG
    systemctl restart sost-auth 2>/dev/null
fi

# 4. Check disk usage
DISK_PCT=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$DISK_PCT" -gt 85 ]; then
    echo "[$NOW] WARNING — Disk usage at ${DISK_PCT}%" >> $LOG
    find /var/log -name "*.gz" -mtime +30 -delete 2>/dev/null
    journalctl --vacuum-time=7d 2>/dev/null
fi

# 5. Check SSL expiry
for DOMAIN in sostcore.com sostprotocol.com; do
    CERT="/etc/letsencrypt/live/$DOMAIN/cert.pem"
    if [ -f "$CERT" ]; then
        EXPIRY=$(openssl x509 -enddate -noout -in "$CERT" 2>/dev/null | cut -d= -f2)
        EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s 2>/dev/null)
        NOW_EPOCH=$(date +%s)
        DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
        if [ "$DAYS_LEFT" -lt 14 ]; then
            echo "[$NOW] HIGH — SSL $DOMAIN expires in $DAYS_LEFT days, renewing..." >> $LOG
            certbot renew --quiet 2>/dev/null
        fi
    fi
done
