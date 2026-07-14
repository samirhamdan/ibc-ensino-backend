"""feat(BIL-02): billing_webhook_events (idempotência do webhook Asaas)

Revision ID: 0016_billing_webhook_events
Revises: 0015_billing
Create Date: 2026-07-14

PR 2 de 4 do módulo de billing (Release 1.0, doc 02-ARQUITETURA.md §7):
tabela de idempotência para o handler `POST /billing/webhook/asaas`
(core/billing/routes.py) — ver JUDGMENT CALL no docstring de
`core/billing/models.py::WebhookEvent` sobre a chave `event_id`.

Tabela nova, sem backfill (mesmo racional de 0015): uma migração só.
"""
from alembic import op
import sqlalchemy as sa

revision = '0016_billing_webhook_events'
down_revision = '0015_billing'
branch_labels = None
depends_on = None

TABELA = 'billing_webhook_events'


def _tem_tabela(nome):
    return sa.inspect(op.get_bind()).has_table(nome)


def _ativar_rls():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        print('  aviso: RLS é PostgreSQL-only — no-op neste banco '
              f'({bind.dialect.name}); a defesa em dev é o filtro de aplicação.')
        return
    op.execute(f'ALTER TABLE {TABELA} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE {TABELA} FORCE ROW LEVEL SECURITY')
    op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON {TABELA}')
    op.execute(
        f"CREATE POLICY tenant_isolation ON {TABELA} "
        f"USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
    )


def _desativar_rls():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON {TABELA}')
    op.execute(f'ALTER TABLE {TABELA} NO FORCE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE {TABELA} DISABLE ROW LEVEL SECURITY')


def upgrade():
    if not _tem_tabela(TABELA):
        op.create_table(
            TABELA,
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('tenant_id', sa.Uuid(),
                      sa.ForeignKey('tenants.id', name='fk_billing_webhook_events_tenant'),
                      nullable=False),
            sa.Column('event_id', sa.String(160), nullable=False),
            sa.Column('tipo', sa.String(60), nullable=False),
            sa.Column('criado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('event_id', name='uq_billing_webhook_events_event_id'),
        )
        op.create_index('ix_billing_webhook_events_tenant_id_id', TABELA, ['tenant_id', 'id'])
    _ativar_rls()


def downgrade():
    _desativar_rls()
    if _tem_tabela(TABELA):
        op.drop_index('ix_billing_webhook_events_tenant_id_id', table_name=TABELA)
        op.drop_table(TABELA)
