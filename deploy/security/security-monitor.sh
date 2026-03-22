#!/bin/bash
# SOST Security Monitor — run every 5 min via cron
# crontab: */5 * * * * /opt/sost/deploy/security/security-monitor.sh

LOG=/var/log/sost-security.log
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Node running?
if ! systemctl is-active --quiet sost-node 2>/dev/null; then
    echo "$DATE ALERT: sost-node is DOWN" >> $LOG
fi

# Nginx running?
if ! systemctl is-active --quiet nginx 2>/dev/null; then
    echo "$DATE ALERT: nginx is DOWN" >> $LOG
fi

# RPC connections (alert if >50)
CONN=$(ss -tn 2>/dev/null | grep :18232 | wc -l)
if [ "$CONN" -gt 50 ]; then
    echo "$DATE ALERT: $CONN connections to RPC port" >> $LOG
fi

# Disk usage (alert if >90%)
DISK=$(df / 2>/dev/null | tail -1 | awk '{print $5}' | tr -d '%')
if [ -n "$DISK" ] && [ "$DISK" -gt 90 ]; then
    echo "$DATE ALERT: Disk at ${DISK}%" >> $LOG
fi

# Web file integrity
HASH=$(find /var/www/html/ -name "*.html" -exec md5sum {} \; 2>/dev/null | md5sum | awk '{print $1}')
PREV=$(cat /opt/sost/deploy/security/.web_hash 2>/dev/null)
if [ -n "$PREV" ] && [ "$HASH" != "$PREV" ]; then
    echo "$DATE ALERT: Website files changed" >> $LOG
fi
echo "$HASH" > /opt/sost/deploy/security/.web_hash
