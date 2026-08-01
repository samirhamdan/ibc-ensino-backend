"""feat(TEN-01) grupo 2 progresso — BACKFILL: tenant_id = tenant ibc

Revision ID: 0007_prog_backfill
Revises: 0006_prog_expand
Create Date: 2026-07-09

Idempotente (WHERE tenant_id IS NULL), lotes de 5.000, mesmo padrão da 0004.
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = '0007_prog_backfill'
down_revision = '0006_prog_expand'
branch_labels = None
depends_on = None

GRUPO = ['lesson_progress', 'progress', 'study_sessions',
         'user_trails', 'onboarding_answers']

LOTE = 5000


def _uuid7():
    import os, time
    raw = bytearray((time.time_ns() // 1_000_000).to_bytes(6, 'big') + os.urandom(10))
    raw[6] = (raw[6] & 0x0F) | 0x70
    raw[8] = (raw[8] & 0x3F) | 0x80
    return uuid.UUID(bytes=bytes(raw))


def _tenant_padrao_id(bind):
    """Lê DEFAULT_TENANT_SLUG (mesma env var que core.tenancy.context usa em
    runtime) em vez de hardcodar 'ibc' — sem isso, um ambiente com o slug
    padrão diferente faria esta migração criar/usar um tenant 'ibc' que a
    aplicação em runtime nunca enxerga (dado legado ficaria preso a um
    tenant fantasma que ninguém resolve)."""
    import os
    slug = os.getenv('DEFAULT_TENANT_SLUG', 'ibc')
    row = bind.execute(sa.text("SELECT id FROM tenants WHERE slug = :slug"),
                       {'slug': slug}).fetchone()
    if row:
        # SQLite devolve o UUID como string hex — normaliza para uuid.UUID,
        # que é o que o bindparam tipado (sa.Uuid) espera.
        return row[0] if isinstance(row[0], uuid.UUID) else uuid.UUID(str(row[0]))
    novo = _uuid7()
    bind.execute(sa.text(
        "INSERT INTO tenants (id, slug, nome, subdominio, plano, status, criado_em) "
        "VALUES (:id, :slug, :slug, :slug, 'semente', 'active', CURRENT_TIMESTAMP)"
    ).bindparams(sa.bindparam('id', type_=sa.Uuid())), {'id': novo, 'slug': slug})
    return novo


def upgrade():
    bind = op.get_bind()
    ibc_id = _tenant_padrao_id(bind)
    for tabela in GRUPO:
        total = 0
        while True:
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
