"""feat(TEN-01) grupo 1 gamificação — BACKFILL: tenant_id = tenant ibc

Revision ID: 0004_gamif_backfill
Revises: 0003_gamif_expand
Create Date: 2026-07-08

Idempotente e re-executável (só toca linhas com tenant_id IS NULL), em lotes
de 5.000 para não segurar lock em produção. Garante o tenant 'ibc' antes
(todo dado legado pertence ao IBC — doc 02 §4).

Downgrade: devolve tenant_id a NULL (reversível sem perda — a informação
"pertence ao ibc" é reconstituível re-executando o upgrade).
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = '0004_gamif_backfill'
down_revision = '0003_gamif_expand'
branch_labels = None
depends_on = None

GRUPO = ['user_points', 'badge', 'user_badge', 'achievements',
         'user_achievements', 'certificates', 'activity_feed']

LOTE = 5000


def _uuid7():
    import os, time
    raw = bytearray((time.time_ns() // 1_000_000).to_bytes(6, 'big') + os.urandom(10))
    raw[6] = (raw[6] & 0x0F) | 0x70
    raw[8] = (raw[8] & 0x3F) | 0x80
    return uuid.UUID(bytes=bytes(raw))


def _tenant_ibc_id(bind):
    row = bind.execute(sa.text("SELECT id FROM tenants WHERE slug = 'ibc'")).fetchone()
    if row:
        return row[0]
    novo = _uuid7()
    bind.execute(sa.text(
        "INSERT INTO tenants (id, slug, nome, subdominio, plano, status, criado_em) "
        "VALUES (:id, 'ibc', 'IBC Ensino', 'ibc', 'semente', 'active', CURRENT_TIMESTAMP)"
    ).bindparams(sa.bindparam('id', type_=sa.Uuid())), {'id': novo})
    return novo


def upgrade():
    bind = op.get_bind()
    ibc_id = _tenant_ibc_id(bind)
    for tabela in GRUPO:
        total = 0
        while True:
            # lotes por PK para não varrer/lockar a tabela inteira de uma vez
            ids = bind.execute(sa.text(
                f'SELECT id FROM {tabela} WHERE tenant_id IS NULL LIMIT {LOTE}'
            )).fetchall()
            if not ids:
                break
            id_list = [r[0] for r in ids]
            bind.execute(
                sa.text(f'UPDATE {tabela} SET tenant_id = :tid WHERE id IN :ids')
                .bindparams(sa.bindparam('ids', expanding=True),
                            sa.bindparam('tid', type_=sa.Uuid())),
                {'tid': ibc_id, 'ids': id_list})
            total += len(id_list)
        print(f'  backfill {tabela}: {total} linha(s) atribuída(s) ao tenant ibc')


def downgrade():
    bind = op.get_bind()
    for tabela in reversed(GRUPO):
        bind.execute(sa.text(f'UPDATE {tabela} SET tenant_id = NULL'))
