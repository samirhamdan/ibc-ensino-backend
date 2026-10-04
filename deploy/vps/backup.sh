#!/bin/sh
# Backup diário do banco xr (cron: 0 3 * * * /opt/xr-educacao/deploy/vps/backup.sh)
set -e
cd "$(dirname "$0")"
mkdir -p backups
docker exec alessio_postgres pg_dump -U alessio -Fc xr > "backups/xr-$(date +%F).dump"
find backups -name 'xr-*.dump' -mtime +14 -delete
