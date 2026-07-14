"""feat(BIL-02): subscriptions.overdue_desde (régua de inadimplência)

Revision ID: 0017_subscription_overdue_desde
Revises: 0016_billing_webhook_events
Create Date: 2026-07-14

PR 3 de 4 do módulo de billing (Release 1.0, doc 02-ARQUITETURA.md §4.8):
a régua (core/billing/regua.py) precisa saber HÁ QUANTOS DIAS uma
Subscription está em 'overdue' para decidir D+10 (leitura) / D+30
(suspenso) — `Subscription` não guardava essa data. Coluna nova, nullable
(NULL enquanto a subscription nunca esteve overdue, ou depois que volta a
'active'/'canceled' — ver core/billing/routes.py::webhook_asaas, que agora
grava/limpa esta coluna na transição de status).

Coluna nova sem backfill de dado existente (nenhuma subscription overdue
hoje tem como saber retroativamente desde quando está inadimplente) — uma
migração só, mesmo racional de 0015/0016.
"""
from alembic import op
import sqlalchemy as sa

revision = '0017_subscription_overdue_desde'
down_revision = '0016_billing_webhook_events'
branch_labels = None
depends_on = None

TABELA = 'subscriptions'
COLUNA = 'overdue_desde'


def _tem_coluna():
    cols = {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABELA)}
    return COLUNA in cols


def upgrade():
    if not _tem_coluna():
        op.add_column(TABELA, sa.Column(COLUNA, sa.Date(), nullable=True))


def downgrade():
    if _tem_coluna():
        op.drop_column(TABELA, COLUNA)
