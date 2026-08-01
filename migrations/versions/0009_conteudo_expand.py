"""feat(TEN-01) grupo 3 conteúdo — EXPAND: tenant_id NULL + índices

Revision ID: 0009_conteudo_expand
Revises: 0008_prog_contract
Create Date: 2026-07-09

Mesmo padrão do grupo 1 (0003): só ADICIONA coluna nula + índice composto.
Guardas por introspecção cobrem o caminho de banco novo (baseline já traz a
coluna) e o de produção legada.
"""
from alembic import op
import sqlalchemy as sa

revision = '0009_conteudo_expand'
down_revision = '0008_prog_contract'
branch_labels = None
depends_on = None

GRUPO = ['categories', 'courses', 'modules', 'materials', 'quiz',
         'questions', 'trails', 'trail_courses', 'tutor_courses',
         'announcements', 'notifications', 'announcement_dismissals']


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
