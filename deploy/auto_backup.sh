#!/bin/bash
# SOST Auto Backup — daily via cron
# crontab: 0 3 * * * /opt/sost/deploy/auto_backup.sh
BACKUP_DIR=/opt/sost/backups
DATE=$(date +%Y%m%d)
mkdir -p $BACKUP_DIR

# Chain state
cp /opt/sost/build/chain.json $BACKUP_DIR/chain_$DATE.json 2>/dev/null

# Auth config
cp /etc/sost/auth.env $BACKUP_DIR/auth_$DATE.env 2>/dev/null

# Nginx config
cp /etc/nginx/sites-enabled/sost* $BACKUP_DIR/nginx_$DATE.conf 2>/dev/null
cp /etc/nginx/sites-enabled/default $BACKUP_DIR/nginx_default_$DATE.conf 2>/dev/null

# Website snapshot (compressed)
tar czf $BACKUP_DIR/website_$DATE.tar.gz -C /opt/sost website/ 2>/dev/null

# Retention: delete backups older than 30 days
find $BACKUP_DIR -name "chain_*" -mtime +30 -delete 2>/dev/null
find $BACKUP_DIR -name "auth_*" -mtime +30 -delete 2>/dev/null
find $BACKUP_DIR -name "nginx_*" -mtime +30 -delete 2>/dev/null
find $BACKUP_DIR -name "website_*" -mtime +30 -delete 2>/dev/null

echo "$(date): Backup completed → $BACKUP_DIR/*_$DATE.*" >> /var/log/sost-backup.log
