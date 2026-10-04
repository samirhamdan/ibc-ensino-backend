#!/bin/sh
# Restaura um backup gerado por backup.sh.
# Uso: ./restore.sh 2026-10-04
# ATENÇÃO: substitui o banco xr e os arquivos enviados pelos do dia informado.
set -e
cd "$(dirname "$0")"
DATA="$1"
[ -n "$DATA" ] || { echo "Uso: $0 AAAA-MM-DD"; ls backups; exit 1; }
[ -f "backups/xr-$DATA.dump" ] || { echo "Não achei backups/xr-$DATA.dump"; exit 1; }

printf 'Isto substitui o banco e os arquivos atuais pelos de %s. Digite RESTAURAR para continuar: ' "$DATA"
read -r ok
[ "$ok" = "RESTAURAR" ] || { echo "Cancelado."; exit 1; }

docker compose stop app
docker exec -i alessio_postgres pg_restore -U alessio -d xr --clean --if-exists --no-owner --role=xr < "backups/xr-$DATA.dump"
if [ -f "backups/uploads-$DATA.tgz" ]; then
  docker run --rm -v xr-educacao_uploads:/data -v "$PWD/backups:/b:ro" alpine \
    sh -c "rm -rf /data/* && tar xzf /b/uploads-$DATA.tgz -C /data"
fi
docker compose start app
echo "Restaurado: $DATA"
