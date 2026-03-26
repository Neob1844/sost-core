#!/bin/bash
# SOST Log Rotation — weekly via cron
# crontab: 0 4 * * 0 /opt/sost/deploy/log_rotate.sh
MAX_SIZE=50  # MB

for LOG in /var/log/sost-node.log /var/log/sost-health.log /var/log/sost-backup.log /var/log/sost-recovery.log /var/log/sost-node-status.log; do
    if [ -f "$LOG" ]; then
        SIZE_MB=$(du -m "$LOG" 2>/dev/null | cut -f1)
        if [ "${SIZE_MB:-0}" -gt "$MAX_SIZE" ]; then
            mv "$LOG" "${LOG}.$(date +%Y%m%d).old"
            gzip "${LOG}.$(date +%Y%m%d).old" 2>/dev/null
            touch "$LOG"
            echo "$(date): Rotated $LOG (was ${SIZE_MB}MB)" >> /var/log/sost-health.log
        fi
    fi
done

find /var/log -name "sost-*.old.gz" -mtime +30 -delete 2>/dev/null
