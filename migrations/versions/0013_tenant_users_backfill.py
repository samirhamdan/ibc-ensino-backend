"""feat(AUTH-03): papéis por tenant — backfill de tenant_users + FK para users

Revision ID: 0013_tenant_users
Revises: 0012_rls
Create Date: 2026-07-09

- Backfill: todo usuário existente ganha vínculo tenant_users no tenant
  padrão (ibc) com o papel global atual — paridade total pós-virada.
- FK tenant_users.user_id → users.id: ficou pendente desde a 0001 (users
  estava fora do Alembic); com o baseline 0002, agora pode existir.
  Introspecção: só cria se faltar e se ambos os lados existirem.

Idempotente (re-executável); downgrade remove só a FK — os vínculos ficam
(dado de produção legítimo; remover seria perda).
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = '0013_tenant_users'
down_revision = '0012_rls'
branch_labels = None
depends_on = None

FK = 'fk_tenant_users_user'


def _tenant_ibc_id(bind):
    row = bind.execute(sa.text("SELECT id FROM tenants WHERE slug = 'ibc'")).fetchone()
    if row is None:
        return None
    return row[0] if isinstance(row[0], uuid.UUID) else uuid.UUID(str(row[0]))


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    ibc = _tenant_ibc_id(bind)
    if ibc is not None and insp.has_table('users'):
        bind.execute(sa.text(
            "INSERT INTO tenant_users (tenant_id, user_id, papel, criado_em) "
            "SELECT :tid, u.id, u.role, CURRENT_TIMESTAMP FROM users u "
            "WHERE NOT EXISTS (SELECT 1 FROM tenant_users tu "
            "                  WHERE tu.tenant_id = :tid AND tu.user_id = u.id)"
        ).bindparams(sa.bindparam('tid', type_=sa.Uuid())), {'tid': ibc})

    fks = {fk.get('name') for fk in insp.get_foreign_keys('tenant_users')}
    if FK not in fks and insp.has_table('users'):
        with op.batch_alter_table('tenant_users') as batch:
            batch.create_foreign_key(FK, 'users', ['user_id'], ['id'])


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    fks = {fk.get('name') for fk in insp.get_foreign_keys('tenant_users')}
    if FK in fks:
        with op.batch_alter_table('tenant_users') as batch:
            batch.drop_constraint(FK, type_='foreignkey')
