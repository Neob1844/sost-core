#!/bin/bash
# SOST Backup — daily at 3am via cron
# crontab: 0 3 * * * /opt/sost/deploy/security/backup.sh

DATE=$(date '+%Y%m%d')
DIR=/opt/sost/backups
mkdir -p $DIR

cp /opt/sost/build/chain.json $DIR/chain_$DATE.json 2>/dev/null
cp /etc/nginx/sites-enabled/sost $DIR/nginx_$DATE.conf 2>/dev/null

# Keep 7 days
find $DIR -mtime +7 -delete 2>/dev/null
