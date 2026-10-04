#!/bin/sh
# Backup diário: banco + arquivos enviados (PDFs, logos), com cópia externa opcional.
# cron: 0 3 * * * /opt/xr-educacao/deploy/vps/backup.sh >> /var/log/xr-backup.log 2>&1
#
# Cópia fora da VPS (recomendado): instale e configure o rclone e defina
# BACKUP_REMOTE no .env, ex.: BACKUP_REMOTE=gdrive:xr-backups
set -e
cd "$(dirname "$0")"
mkdir -p backups
DATA=$(date +%F)
[ -f .env ] && BACKUP_REMOTE=${BACKUP_REMOTE:-$(grep -E '^BACKUP_REMOTE=' .env | cut -d= -f2-)}

# 1. Banco
docker exec alessio_postgres pg_dump -U alessio -Fc xr > "backups/xr-$DATA.dump"
[ -s "backups/xr-$DATA.dump" ] || { echo "ERRO: dump do banco vazio"; exit 1; }

# 2. Arquivos enviados (volume do compose)
docker run --rm -v xr-educacao_uploads:/data:ro -v "$PWD/backups:/b" alpine \
  tar czf "/b/uploads-$DATA.tgz" -C /data .

# 3. Retenção local: 14 dias
find backups -name 'xr-*.dump' -mtime +14 -delete
find backups -name 'uploads-*.tgz' -mtime +14 -delete

# 4. Cópia externa
if [ -n "$BACKUP_REMOTE" ] && command -v rclone >/dev/null 2>&1; then
  rclone copy "backups/xr-$DATA.dump" "$BACKUP_REMOTE"
  rclone copy "backups/uploads-$DATA.tgz" "$BACKUP_REMOTE"
  rclone delete --min-age 30d "$BACKUP_REMOTE" || true
  echo "$(date '+%F %T') backup ok + cópia externa em $BACKUP_REMOTE"
else
  echo "$(date '+%F %T') backup ok (SÓ LOCAL — configure BACKUP_REMOTE e rclone para cópia externa)"
fi
