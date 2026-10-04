"""feat(TUT-02): dúvida guarda a aula de origem (questions.module_id)

Revision ID: 0023_questions_module
Revises: 0022_operadores
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = '0023_questions_module'
down_revision = '0022_operadores'
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if 'questions' not in insp.get_table_names():
        return  # banco novo: db.create_all cria com a coluna
    if 'module_id' in {c['name'] for c in insp.get_columns('questions')}:
        return
    with op.batch_alter_table('questions') as batch:
        batch.add_column(sa.Column('module_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_questions_module', 'modules', ['module_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_questions_tenant_module', 'questions', ['tenant_id', 'module_id'])


def downgrade():
    insp = sa.inspect(op.get_bind())
    if 'questions' not in insp.get_table_names():
        return
    if 'module_id' not in {c['name'] for c in insp.get_columns('questions')}:
        return
    if 'ix_questions_tenant_module' in {i['name'] for i in insp.get_indexes('questions')}:
        op.drop_index('ix_questions_tenant_module', table_name='questions')
    fks = [fk['name'] for fk in insp.get_foreign_keys('questions') if fk['referred_table'] == 'modules' and fk['name']]
    with op.batch_alter_table('questions') as batch:
        for nome in fks:
            batch.drop_constraint(nome, type_='foreignkey')
        batch.drop_column('module_id')
