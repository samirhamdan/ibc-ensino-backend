"""feat(BIL-03): ai_usage.alerta_80pct_enviado + subscriptions.regua_pausada

Revision ID: 0018_billing_metering_columns
Revises: 0017_subscription_overdue_desde
Create Date: 2026-07-14

PR 4 de 4 do módulo de billing (Release 1.0, doc 02-ARQUITETURA.md §4.8):

- `ai_usage.alerta_80pct_enviado` (Boolean, default False): rastreia se o
  evento de domínio `ai.cota_80pct` já foi publicado NESTE período, pra
  `core/billing/metering.py::checar_cota` não reenviar o evento a cada
  interação subsequente enquanto o consumo segue entre 80% e 100% da cota
  — só quando CRUZA o limiar pela primeira vez no período. Por linha
  (1 por tenant+período), reseta sozinho todo mês (linha nova = False).

- `subscriptions.regua_pausada` (Boolean, default False): override manual
  do operador pra pausar a régua de inadimplência (D+10/D+30) durante uma
  negociação com o tenant — capacidade exigida pelo spec original da
  Release 1.0 ("como pausar a régua para negociação (override via
  operador)"), que não existia até esta PR. `core/billing/regua.py::
  _candidatos_overdue` passa a excluir tenants com este flag True.

Duas colunas novas, sem backfill (nenhum dado existente precisa de valor
retroativo — mesmo racional de 0015/0016/0017), numa migração só por serem
do mesmo PR/módulo e não relacionadas entre si por FK/constraint.
"""
from alembic import op
import sqlalchemy as sa

revision = '0018_billing_metering_columns'
down_revision = '0017_subscription_overdue_desde'
branch_labels = None
depends_on = None


def _colunas(tabela):
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(tabela)}


def upgrade():
    if 'alerta_80pct_enviado' not in _colunas('ai_usage'):
        op.add_column(
            'ai_usage',
            sa.Column('alerta_80pct_enviado', sa.Boolean(), nullable=False,
                      server_default=sa.false()),
        )
    if 'regua_pausada' not in _colunas('subscriptions'):
        op.add_column(
            'subscriptions',
            sa.Column('regua_pausada', sa.Boolean(), nullable=False,
                      server_default=sa.false()),
        )


def downgrade():
    if 'regua_pausada' in _colunas('subscriptions'):
        op.drop_column('subscriptions', 'regua_pausada')
    if 'alerta_80pct_enviado' in _colunas('ai_usage'):
        op.drop_column('ai_usage', 'alerta_80pct_enviado')
