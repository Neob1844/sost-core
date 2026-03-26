#!/bin/bash
# Install SOST cron jobs — run ONCE on VPS as root
# Usage: sudo bash /opt/sost/deploy/setup_cron.sh

echo "Installing SOST cron jobs..."

(crontab -l 2>/dev/null; cat << 'CRON'
# SOST Health Check — every 5 minutes
*/5 * * * * /opt/sost/deploy/health_check.sh
# SOST Node Status JSON — every minute
* * * * * /opt/sost/deploy/node-status.sh
# SOST Backup — daily at 3 AM UTC
0 3 * * * /opt/sost/deploy/auto_backup.sh
# SOST Log Rotation — weekly Sunday 4 AM UTC
0 4 * * 0 /opt/sost/deploy/log_rotate.sh
CRON
) | sort -u | crontab -

echo ""
echo "Cron jobs installed:"
crontab -l
echo ""
echo "Done. Verify with: crontab -l"
