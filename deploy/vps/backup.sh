#!/bin/sh
# Backup diário do Postgres (cron: 0 3 * * * /opt/xr-educacao/deploy/vps/backup.sh)
set -e
cd "$(dirname "$0")"
docker compose exec -T db pg_dump -U xr -Fc xr > "backups/xr-$(date +%F).dump"
find backups -name 'xr-*.dump' -mtime +14 -delete
