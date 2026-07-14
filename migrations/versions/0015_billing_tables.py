"""feat(BIL-01): domain_events, audit_log, subscriptions, ai_usage + tenants.billing_status

Revision ID: 0015_billing
Revises: 0014_streak
Create Date: 2026-07-14

PR 1 de 4 do módulo de billing (Release 1.0, doc 02-ARQUITETURA.md §4):
- domain_events / audit_log: infraestrutura compartilhada (shared/) que
  o billing já depende (outbox de eventos e log de auditoria imutável).
- subscriptions / ai_usage: modelo de dados de billing (core/billing/models.py).
  (shared/ e core/billing/ — não app/shared, app/core/billing — pelo motivo
  documentado em core/__init__.py: app.py ainda existe e um pacote `app/`
  sombrearia `app:create_app`.)
- tenants.billing_status: estado de pagamento do tenant (BIL-02), separado
  do `status` operacional existente.

Todas as tabelas são novas (sem backfill de dado existente) e a coluna nova
em `tenants` nasce com server_default — por isso uma migração única basta
(mesmo racional do doc 02 §3 aplicado a 0001/0014: expand/contract só é
necessário quando há dado pré-existente para migrar). Guardas por
introspecção seguem o padrão de 0001/0014 (idempotente/re-executável).
"""
from alembic import op
import sqlalchemy as sa

revision = '0015_billing'
down_revision = '0014_streak'
branch_labels = None
depends_on = None

# Achado da revisão Fable 5 (PR 1): CLAUDE.md regra 1 exige política RLS na
# migração de toda tabela com tenant_id — 0012_rls.py fez isso pras tabelas
# que existiam até então; as 4 novas tabelas deste módulo ficaram de fora.
# Mesmo padrão fail-closed de 0012 (RLS é PostgreSQL-only, no-op em SQLite;
# só tem efeito real quando a app conecta sem BYPASSRLS — ver
# docs/RUNBOOK-RLS.md).
TABELAS_RLS = ['domain_events', 'audit_log', 'subscriptions', 'ai_usage']


def _tem_tabela(nome):
    return sa.inspect(op.get_bind()).has_table(nome)


def _tem_coluna(tabela, coluna):
    cols = {c['name'] for c in sa.inspect(op.get_bind()).get_columns(tabela)}
    return coluna in cols


def _ativar_rls():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        print('  aviso: RLS é PostgreSQL-only — no-op neste banco '
              f'({bind.dialect.name}); a defesa em dev é o filtro de aplicação.')
        return
    for t in TABELAS_RLS:
        op.execute(f'ALTER TABLE {t} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {t} FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON {t}')
        op.execute(
            f"CREATE POLICY tenant_isolation ON {t} "
            f"USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
        )


def _desativar_rls():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    for t in reversed(TABELAS_RLS):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON {t}')
        op.execute(f'ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {t} DISABLE ROW LEVEL SECURITY')


def upgrade():
    if not _tem_tabela('domain_events'):
        _criar_domain_events()
    if not _tem_tabela('audit_log'):
        _criar_audit_log()
    if not _tem_tabela('subscriptions'):
        _criar_subscriptions()
    if not _tem_tabela('ai_usage'):
        _criar_ai_usage()
    if not _tem_coluna('tenants', 'billing_status'):
        with op.batch_alter_table('tenants') as batch:
            batch.add_column(sa.Column('billing_status', sa.String(20),
                                       nullable=False, server_default='ativo'))
    _ativar_rls()


def _criar_domain_events():
    op.create_table(
        'domain_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Uuid(),
                  sa.ForeignKey('tenants.id', name='fk_domain_events_tenant'),
                  nullable=False),
        sa.Column('tipo', sa.String(60), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('processado', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index('ix_domain_events_tenant_id_id', 'domain_events', ['tenant_id', 'id'])
    op.create_index('ix_domain_events_tipo_processado', 'domain_events', ['tipo', 'processado'])


def _criar_audit_log():
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Uuid(),
                  sa.ForeignKey('tenants.id', name='fk_audit_log_tenant'),
                  nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('acao', sa.String(60), nullable=False),
        sa.Column('alvo', sa.String(120), nullable=True),
        sa.Column('payload_json', sa.JSON(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_audit_log_tenant_id_id', 'audit_log', ['tenant_id', 'id'])


def _criar_subscriptions():
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Uuid(),
                  sa.ForeignKey('tenants.id', name='fk_subscriptions_tenant'),
                  nullable=False),
        sa.Column('plano', sa.String(20), nullable=False),
        sa.Column('asaas_customer_id', sa.String(60), nullable=True),
        sa.Column('asaas_subscription_id', sa.String(60), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('ciclo', sa.String(20), nullable=False, server_default='mensal'),
        sa.Column('proximo_vencimento', sa.Date(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id', name='uq_subscriptions_tenant'),
    )
    op.create_index('ix_subscriptions_tenant_id_id', 'subscriptions', ['tenant_id', 'id'])


def _criar_ai_usage():
    op.create_table(
        'ai_usage',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Uuid(),
                  sa.ForeignKey('tenants.id', name='fk_ai_usage_tenant'),
                  nullable=False),
        sa.Column('periodo', sa.String(7), nullable=False),
        sa.Column('interacoes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tokens_entrada', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tokens_saida', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('custo_estimado', sa.Numeric(10, 4), nullable=False, server_default='0'),
        sa.Column('criado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id', 'periodo', name='uq_ai_usage_tenant_periodo'),
    )
    op.create_index('ix_ai_usage_tenant_id_id', 'ai_usage', ['tenant_id', 'id'])


def downgrade():
    _desativar_rls()
    if _tem_coluna('tenants', 'billing_status'):
        with op.batch_alter_table('tenants') as batch:
            batch.drop_column('billing_status')
    if _tem_tabela('ai_usage'):
        op.drop_index('ix_ai_usage_tenant_id_id', table_name='ai_usage')
        op.drop_table('ai_usage')
    if _tem_tabela('subscriptions'):
        op.drop_index('ix_subscriptions_tenant_id_id', table_name='subscriptions')
        op.drop_table('subscriptions')
    if _tem_tabela('audit_log'):
        op.drop_index('ix_audit_log_tenant_id_id', table_name='audit_log')
        op.drop_table('audit_log')
    if _tem_tabela('domain_events'):
        op.drop_index('ix_domain_events_tipo_processado', table_name='domain_events')
        op.drop_index('ix_domain_events_tenant_id_id', table_name='domain_events')
        op.drop_table('domain_events')
