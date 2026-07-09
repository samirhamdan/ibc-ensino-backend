"""feat(TEN-01): tabelas tenants e tenant_users

Revision ID: 0001_ten01
Revises: None
Create Date: 2026-07-08

Fase 2, Etapa 2.1 do playbook — nenhuma tabela existente é alterada.
tenant_users.user_id fica SEM FK para users por ora: o schema legado ainda
está fora do Alembic (baseline na Fase 3) e esta migração precisa aplicar em
banco vazio no CI. Integridade garantida na aplicação até lá.

Guardas de introspecção: em bancos onde o app já rodou ANTES do primeiro
`alembic upgrade` (produção — db.create_all() no boot criou tenants/
tenant_users, mas não há carimbo em alembic_version), o CREATE TABLE batia
em DuplicateTable e derrubava o preDeployCommand. Com as guardas, a
migração reconhece o estado existente e só carimba.
"""
from alembic import op
import sqlalchemy as sa

revision = '0001_ten01'
down_revision = None
branch_labels = None
depends_on = None


def _tem_tabela(nome):
    return sa.inspect(op.get_bind()).has_table(nome)


def upgrade():
    if not _tem_tabela('tenants'):
        _criar_tenants()
    if not _tem_tabela('tenant_users'):
        _criar_tenant_users()


def _criar_tenants():
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


def _criar_tenant_users():
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
    if _tem_tabela('tenant_users'):
        idx = {i['name'] for i in sa.inspect(op.get_bind()).get_indexes('tenant_users')}
        if 'ix_tenant_users_user_id' in idx:
            op.drop_index('ix_tenant_users_user_id', table_name='tenant_users')
        op.drop_table('tenant_users')
    if _tem_tabela('tenants'):
        op.drop_table('tenants')
