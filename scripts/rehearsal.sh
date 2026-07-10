#!/usr/bin/env bash
#
# Ensaio geral de migração (Fase 5 do playbook 0.9, docs/PLAYBOOK-MIGRACAO-0.9.md).
# Roda contra o STAGING com backup fresco de produção já restaurado — este
# script NÃO restaura o backup por você (passo 1 do playbook é manual,
# depende de como você tira o backup no Railway/Postgres gerenciado).
#
# O que faz, nesta ordem, abortando no primeiro erro (set -e):
#   1. Backup lógico do staging ANTES do upgrade (pg_dump), para poder
#      comparar/recuperar se o ensaio bagunçar o banco.
#   2. `alembic upgrade head`, cronometrado (você precisa saber quanto
#      tempo o backfill leva com dados reais de produção).
#   3. `pytest -m smoke` — as 5 jornadas críticas do aluno real do IBC
#      (tests/test_smoke.py), rodando contra o staging pós-migração.
#   4. `alembic downgrade` até o ponto pré-tenancy (0002_legacy_baseline)
#      e `alembic upgrade head` de novo — prova que o rollback funciona
#      de verdade, não só "no papel".
#   5. Relatório final com os tempos de cada etapa.
#
# Uso:
#   DATABASE_URL=postgresql://... ./scripts/rehearsal.sh
#   (ou ALEMBIC_DATABASE_URL separado, se a role de migração for diferente
#   da role de runtime sem BYPASSRLS — ver .env.example e docs/RUNBOOK-RLS.md)
#
# Gate de saída (playbook §5): ensaio completo sem intervenção manual;
# tempo total conhecido; plano de rollback provado, não hipotético.

set -euo pipefail

REV_PRE_TENANCY='0002_legacy_baseline'
RELATORIO="rehearsal-$(date -u +%Y%m%dT%H%M%SZ).log"
INICIO_TOTAL=$(date +%s)

log() { echo "[rehearsal] $*" | tee -a "$RELATORIO"; }

falhou() {
    log "❌ ENSAIO ABORTADO na etapa: $1"
    log ""
    log "Plano de rollback (staging não fica sujo para o próximo ensaio):"
    log "  1. alembic downgrade ${REV_PRE_TENANCY}"
    log "  2. Restaure o backup lógico gerado no início deste ensaio:"
    log "     pg_restore --clean --if-exists -d \"\$DATABASE_URL\" \"$BACKUP_FILE\""
    log "  3. Investigue o erro acima antes de tentar de novo — NÃO repita"
    log "     o ensaio sobre um staging que falhou no meio."
    exit 1
}
trap 'falhou "inesperada (ver saída acima)"' ERR

if [ -z "${DATABASE_URL:-}" ] && [ -z "${ALEMBIC_DATABASE_URL:-}" ]; then
    echo "Defina DATABASE_URL (ou ALEMBIC_DATABASE_URL) apontando para o STAGING." >&2
    echo "NUNCA rode este script contra produção." >&2
    exit 2
fi

log "Ensaio de migração — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "Alvo: ${ALEMBIC_DATABASE_URL:-$DATABASE_URL}"
log ""

# ── 1. Backup lógico prévio ────────────────────────────────────────────────
BACKUP_FILE="rehearsal-backup-$(date -u +%Y%m%dT%H%M%SZ).dump"
log "1/5 Backup lógico prévio → $BACKUP_FILE"
T0=$(date +%s)
pg_dump --format=custom --file="$BACKUP_FILE" "${DATABASE_URL:-$ALEMBIC_DATABASE_URL}" \
    || falhou "backup lógico (pg_dump)"
T1=$(date +%s)
log "    ok ($((T1 - T0))s)"
log ""

# ── 2. Upgrade cronometrado, revisão por revisão ────────────────────────────
log "2/5 alembic upgrade head (cronometrado por revisão)"
T0=$(date +%s)
python -m alembic upgrade head 2>&1 | tee -a "$RELATORIO" || falhou "alembic upgrade head"
T1=$(date +%s)
UPGRADE_S=$((T1 - T0))
log "    upgrade completo em ${UPGRADE_S}s"
log ""

# ── 3. Suíte completa + smoke das 5 jornadas ────────────────────────────────
log "3/5 Suíte completa"
T0=$(date +%s)
python -m pytest 2>&1 | tee -a "$RELATORIO" || falhou "suíte completa (pytest)"
T1=$(date +%s)
log "    ok ($((T1 - T0))s)"
log ""

log "3/5 Smoke das 5 jornadas do aluno (tests/test_smoke.py)"
T0=$(date +%s)
python -m pytest -m smoke -v 2>&1 | tee -a "$RELATORIO" || falhou "smoke das 5 jornadas"
T1=$(date +%s)
SMOKE_S=$((T1 - T0))
log "    ok (${SMOKE_S}s)"
log ""

# ── 4. Downgrade até pré-tenancy e upgrade de novo ──────────────────────────
log "4/5 alembic downgrade ${REV_PRE_TENANCY} (prova o rollback)"
T0=$(date +%s)
python -m alembic downgrade "$REV_PRE_TENANCY" 2>&1 | tee -a "$RELATORIO" \
    || falhou "alembic downgrade ${REV_PRE_TENANCY}"
T1=$(date +%s)
DOWNGRADE_S=$((T1 - T0))
log "    downgrade completo em ${DOWNGRADE_S}s"

log "    alembic upgrade head (de novo, confirma que sobe limpo depois do downgrade)"
T0=$(date +%s)
python -m alembic upgrade head 2>&1 | tee -a "$RELATORIO" || falhou "alembic upgrade head (2ª vez)"
T1=$(date +%s)
UPGRADE2_S=$((T1 - T0))
log "    ok (${UPGRADE2_S}s)"
log ""

# ── 5. Relatório final ──────────────────────────────────────────────────────
FIM_TOTAL=$(date +%s)
TOTAL_S=$((FIM_TOTAL - INICIO_TOTAL))

log "5/5 Relatório final"
log "════════════════════════════════════════════════════════════"
log "  upgrade head (1ª vez):        ${UPGRADE_S}s"
log "  smoke (5 jornadas):           ${SMOKE_S}s"
log "  downgrade → ${REV_PRE_TENANCY}: ${DOWNGRADE_S}s"
log "  upgrade head (2ª vez):        ${UPGRADE2_S}s"
log "  TOTAL do ensaio:              ${TOTAL_S}s"
log "════════════════════════════════════════════════════════════"
log "✅ Ensaio completo sem intervenção manual — gate de saída da Fase 5 atendido."
log "Backup gerado (guarde ou descarte): $BACKUP_FILE"
log "Relatório completo: $RELATORIO"
