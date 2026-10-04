"""feat(TEN-04): operadores da plataforma (papel global, 2FA TOTP)

Revision ID: 0022_operadores
Revises: 0021_config_tenant
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = '0022_operadores'
down_revision = '0021_config_tenant'
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    tabelas = set(insp.get_table_names())
    if 'operadores_plataforma' in tabelas or 'users' not in tabelas:
        return  # banco novo: db.create_all cria junto com users
    op.create_table(
        'operadores_plataforma',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False, unique=True),
        sa.Column('totp_segredo', sa.String(64), nullable=True),
        sa.Column('totp_ativo', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('totp_ultimo_contador', sa.BigInteger(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('criado_em', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('criado_por', sa.Integer(), nullable=True),
    )


def downgrade():
    if 'operadores_plataforma' in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table('operadores_plataforma')
