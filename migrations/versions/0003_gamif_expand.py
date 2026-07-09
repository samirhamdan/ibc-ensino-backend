"""feat(TEN-01) grupo 1 gamificação — EXPAND: tenant_id NULL + índices

Revision ID: 0003_gamif_expand
Revises: 0002_legacy_baseline
Create Date: 2026-07-08

expand → backfill → contract (playbook Fase 3). Este passo só ADICIONA:
coluna tenant_id NULA + índice composto (tenant_id, id) em cada tabela do
grupo. Nenhuma linha muda; app antigo continua funcionando.

Guardas por introspecção: num banco NOVO o baseline (0002) já cria as
tabelas com tenant_id (metadata atual dos models) — aqui viram no-op. Em
produção (tabelas legadas sem a coluna) o caminho completo executa.

Nota sobre CONCURRENTLY: o playbook prevê CREATE INDEX CONCURRENTLY para
evitar lock; nas tabelas atuais do IBC (centenas de linhas) o lock de um
CREATE INDEX comum é de milissegundos e CONCURRENTLY exigiria autocommit
fora da transação da migração. Decisão consciente: índice comum agora;
reavaliar quando houver tenant com volume real.
"""
from alembic import op
import sqlalchemy as sa

revision = '0003_gamif_expand'
down_revision = '0002_legacy_baseline'
branch_labels = None
depends_on = None

GRUPO = ['user_points', 'badge', 'user_badge', 'achievements',
         'user_achievements', 'certificates', 'activity_feed']


def _tem_coluna(insp, tabela, coluna):
    return coluna in {c['name'] for c in insp.get_columns(tabela)}


def _tem_indice(insp, tabela, nome):
    return nome in {i['name'] for i in insp.get_indexes(tabela)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for tabela in GRUPO:
        if not _tem_coluna(insp, tabela, 'tenant_id'):
            op.add_column(tabela, sa.Column('tenant_id', sa.Uuid(), nullable=True))
        if not _tem_indice(sa.inspect(bind), tabela, f'ix_{tabela}_tenant_id_id'):
            op.create_index(f'ix_{tabela}_tenant_id_id', tabela, ['tenant_id', 'id'])


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for tabela in reversed(GRUPO):
        if _tem_indice(insp, tabela, f'ix_{tabela}_tenant_id_id'):
            op.drop_index(f'ix_{tabela}_tenant_id_id', table_name=tabela)
        if _tem_coluna(insp, tabela, 'tenant_id'):
            with op.batch_alter_table(tabela) as batch:
                batch.drop_column('tenant_id')
