"""feat(TEN-01): tabelas tenants e tenant_users

Revision ID: 0001_ten01
Revises: None
Create Date: 2026-07-08

Fase 2, Etapa 2.1 do playbook — nenhuma tabela existente é alterada.
tenant_users.user_id fica SEM FK para users por ora: o schema legado ainda
está fora do Alembic (baseline na Fase 3) e esta migração precisa aplicar em
banco vazio no CI. Integridade garantida na aplicação até lá.
"""
from alembic import op
import sqlalchemy as sa

revision = '0001_ten01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tenants',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('slug', sa.String(50), nullable=False, unique=True),
        sa.Column('nome', sa.String(200), nullable=False),
        sa.Column('subdominio', sa.String(63), nullable=False, unique=True),
        sa.Column('plano', sa.String(20), nullable=False, server_default='semente'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('tema_json', sa.JSON(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
    )

    op.create_table(
        'tenant_users',
        sa.Column('tenant_id', sa.Uuid(),
                  sa.ForeignKey('tenants.id', name='fk_tenant_users_tenant'),
                  primary_key=True),
        sa.Column('user_id', sa.Integer(), primary_key=True),
        sa.Column('papel', sa.String(30), nullable=False, server_default='aluno'),
        sa.Column('criado_em', sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index('ix_tenant_users_user_id', 'tenant_users', ['user_id'])


def downgrade():
    op.drop_index('ix_tenant_users_user_id', table_name='tenant_users')
    op.drop_table('tenant_users')
    op.drop_table('tenants')
