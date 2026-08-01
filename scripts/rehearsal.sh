#!/usr/bin/env bash
#
# Ensaio geral de migração (Fase 5 do playbook 0.9, docs/PLAYBOOK-MIGRACAO-0.9.md
# + docs/OPS-STAGING.md). Roda contra o STAGING do Railway, usando um dump
# FRESCO de produção — este script FAZ o backup e a restauração (diferente
# da versão anterior, que exigia restauração manual prévia).
#
# Este script NUNCA embute credenciais. Ele lê:
#   DATABASE_URL_PROD      URL interna (.railway.internal) do Postgres de PRODUÇÃO
#   DATABASE_URL_STAGING   URL interna (.railway.internal) do Postgres de STAGING
#
# URLs .railway.internal só resolvem de DENTRO da rede do Railway — por
# isso TODO comando que toca banco roda via `railway run --environment X`,
# nunca diretamente neste shell. Use scripts/run_rehearsal.sh (fora do
# git, ver .gitignore) para exportar as URLs e chamar este script — NUNCA
# passe as URLs na linha de comando nem as deixe em texto versionado.
#
# O que faz, nesta ordem, abortando no primeiro erro (set -e):
#   1. pg_dump de PRODUÇÃO (via `railway run --environment production`),
#      formato texto plano (psql restaura sem precisar de pg_restore).
#   2. Restaura o dump em STAGING (via `railway run --environment staging`,
#      psql). Staging é sempre recriado do zero antes disto (ver
#      docs/OPS-STAGING.md) — este script não dropa nada, só popula.
#   3. `alembic upgrade head` em STAGING, cronometrado.
#   4. `pytest -m smoke` em STAGING (as 5 jornadas críticas do aluno real
#      do IBC, tests/test_smoke.py) — aponta TEST_DATABASE_URL para o
#      staging recém-migrado.
#   5. `alembic downgrade` até o ponto pré-tenancy (0002_legacy_baseline)
#      e `alembic upgrade head` de novo, em STAGING — prova o rollback.
#   6. Cria o tenant `demo` em STAGING via `flask shell` (idempotente) —
#      segundo tenant real, valida o isolamento a olho nu (playbook §5.5).
#   7. staging-rehearsal-report.txt com os tempos de cada etapa (fora do
#      git — pode conter nomes de host internos).
#
# Gate de saída (playbook §5): ensaio completo sem intervenção manual;
# tempo total conhecido; plano de rollback provado, não hipotético.

set -euo pipefail

REV_PRE_TENANCY='0002_legacy_baseline'
RELATORIO='staging-rehearsal-report.txt'
BACKUP_FILE="rehearsal-backup-$(date -u +%Y%m%dT%H%M%SZ).sql"
INICIO_TOTAL=$(date +%s)

log() { echo "[rehearsal] $*" | tee -a "$RELATORIO"; }

falhou() {
    log "❌ ENSAIO ABORTADO na etapa: $1"
    log ""
    log "Staging é DESCARTÁVEL — o plano de rollback aqui não é"
    log "downgrade+restore local, é recriar o ambiente do zero:"
    log "  1. Investigue o erro acima (log completo em $RELATORIO)."
    log "  2. Delete o serviço Postgres de staging no Railway e recrie"
    log "     (docs/OPS-STAGING.md, seção 'Recriar o ambiente')."
    log "  3. Rode o ensaio de novo do início — não tente continuar um"
    log "     staging que falhou no meio."
    log ""
    log "O dump de produção gerado neste ensaio foi mantido: $BACKUP_FILE"
    log "(apague-o manualmente depois de investigar — não é versionado,"
    log "mas contém dado real de produção, trate como sensível)."
    exit 1
}
trap 'falhou "inesperada (ver saída acima)"' ERR

if [ -z "${DATABASE_URL_PROD:-}" ] || [ -z "${DATABASE_URL_STAGING:-}" ]; then
    echo "Defina DATABASE_URL_PROD e DATABASE_URL_STAGING (URLs internas" >&2
    echo ".railway.internal dos dois bancos). Use scripts/run_rehearsal.sh" >&2
    echo "— nunca passe essas URLs direto na linha de comando." >&2
    exit 2
fi

if ! command -v railway >/dev/null 2>&1; then
    echo "Railway CLI não encontrado. Instale e rode 'railway login' +" >&2
    echo "'railway link' neste diretório antes de rodar o ensaio." >&2
    exit 2
fi

: > "$RELATORIO"   # relatório novo a cada ensaio
log "Ensaio de migração em staging — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log ""

# ── 1. Backup lógico de PRODUÇÃO ────────────────────────────────────────────
log "1/7 pg_dump de produção (railway run --environment production) → $BACKUP_FILE"
T0=$(date +%s)
railway run --environment production -- \
    pg_dump --no-owner --no-acl --format=plain --file="$BACKUP_FILE" "$DATABASE_URL_PROD" \
    || falhou "pg_dump de produção"
T1=$(date +%s)
log "    ok ($((T1 - T0))s)"
log ""

# ── 2. Restaura em STAGING ───────────────────────────────────────────────────
log "2/7 Restaura em staging (railway run --environment staging, psql)"
T0=$(date +%s)
railway run --environment staging -- \
    psql --set ON_ERROR_STOP=1 -f "$BACKUP_FILE" "$DATABASE_URL_STAGING" \
    || falhou "restauração em staging (psql)"
T1=$(date +%s)
RESTORE_S=$((T1 - T0))
log "    restauração completa em ${RESTORE_S}s"
log ""

# ── 3. Upgrade cronometrado ──────────────────────────────────────────────────
log "3/7 alembic upgrade head em staging (cronometrado)"
T0=$(date +%s)
railway run --environment staging -- \
    env DATABASE_URL="$DATABASE_URL_STAGING" python -m alembic upgrade head 2>&1 | tee -a "$RELATORIO" \
    || falhou "alembic upgrade head (staging)"
T1=$(date +%s)
UPGRADE_S=$((T1 - T0))
log "    upgrade completo em ${UPGRADE_S}s"
log ""

# ── 4. Smoke das 5 jornadas, contra o staging migrado ────────────────────────
log "4/7 pytest -m smoke em staging"
T0=$(date +%s)
railway run --environment staging -- \
    env TEST_DATABASE_URL="$DATABASE_URL_STAGING" python -m pytest -m smoke -v 2>&1 | tee -a "$RELATORIO" \
    || falhou "smoke das 5 jornadas (staging)"
T1=$(date +%s)
SMOKE_S=$((T1 - T0))
log "    ok (${SMOKE_S}s)"
log ""

# ── 5. Downgrade até pré-tenancy e upgrade de novo, em staging ───────────────
log "5/7 alembic downgrade ${REV_PRE_TENANCY} em staging (prova o rollback)"
T0=$(date +%s)
railway run --environment staging -- \
    env DATABASE_URL="$DATABASE_URL_STAGING" python -m alembic downgrade "$REV_PRE_TENANCY" 2>&1 | tee -a "$RELATORIO" \
    || falhou "alembic downgrade ${REV_PRE_TENANCY} (staging)"
T1=$(date +%s)
DOWNGRADE_S=$((T1 - T0))
log "    downgrade completo em ${DOWNGRADE_S}s"

log "    alembic upgrade head de novo (confirma que sobe limpo depois do downgrade)"
T0=$(date +%s)
railway run --environment staging -- \
    env DATABASE_URL="$DATABASE_URL_STAGING" python -m alembic upgrade head 2>&1 | tee -a "$RELATORIO" \
    || falhou "alembic upgrade head, 2ª vez (staging)"
T1=$(date +%s)
UPGRADE2_S=$((T1 - T0))
log "    ok (${UPGRADE2_S}s)"
log ""

# ── 6. Tenant demo via flask shell (idempotente) ─────────────────────────────
log "6/7 cria o tenant demo em staging (flask shell)"
T0=$(date +%s)
railway run --environment staging -- \
    env DATABASE_URL="$DATABASE_URL_STAGING" FLASK_APP=app.py python -m flask shell <<'PYEOF' 2>&1 | tee -a "$RELATORIO" \
    || falhou "criação do tenant demo (flask shell, staging)"
from extensions import db
from core.tenancy import Tenant
if not Tenant.query.filter_by(slug='demo').first():
    db.session.add(Tenant(slug='demo', nome='Tenant Demo', subdominio='demo',
                          tema_json={'cor_primaria': '#f0a500'}))
    db.session.commit()
    print('tenant demo criado')
else:
    print('tenant demo já existe (idempotente, nada a fazer)')
PYEOF
T1=$(date +%s)
TENANT_S=$((T1 - T0))
log "    ok (${TENANT_S}s)"
log ""

# ── 7. Relatório final ───────────────────────────────────────────────────────
FIM_TOTAL=$(date +%s)
TOTAL_S=$((FIM_TOTAL - INICIO_TOTAL))

log "7/7 Relatório final"
log "════════════════════════════════════════════════════════════"
log "  pg_dump produção:              (ver linha 'ok' acima)"
log "  restore em staging (psql):     ${RESTORE_S}s"
log "  upgrade head (1ª vez):         ${UPGRADE_S}s"
log "  smoke (5 jornadas):            ${SMOKE_S}s"
log "  downgrade → ${REV_PRE_TENANCY}: ${DOWNGRADE_S}s"
log "  upgrade head (2ª vez):         ${UPGRADE2_S}s"
log "  criação do tenant demo:        ${TENANT_S}s"
log "  TOTAL do ensaio:               ${TOTAL_S}s"
log "════════════════════════════════════════════════════════════"
log "✅ Ensaio completo sem intervenção manual — gate de saída da Fase 5 atendido."
log "Dump de produção mantido localmente (sensível, fora do git): $BACKUP_FILE"
log "Apague-o quando terminar de revisar o relatório."
log "Relatório completo: $RELATORIO"
log ""
log "Lembrete: delete o staging quando terminar (docs/OPS-STAGING.md,"
log "seção 'Deletar o staging após o ensaio') para economizar créditos Hobby."
