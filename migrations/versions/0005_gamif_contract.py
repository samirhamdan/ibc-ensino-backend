"""feat(TEN-01) grupo 1 gamificação — CONTRACT: NOT NULL + FK + uniques por tenant

Revision ID: 0005_gamif_contract
Revises: 0004_gamif_backfill
Create Date: 2026-07-08

Fecha o expand/contract do grupo:
- tenant_id vira NOT NULL + FK para tenants em todas as tabelas do grupo
- user_points: o UNIQUE global de user_id vira UNIQUE (tenant_id, user_id) —
  o mesmo usuário pode ter pontuação separada em cada tenant
- badge.code e achievements.code: UNIQUE global vira UNIQUE (tenant_id, code)
  — cada tenant tem seu próprio catálogo (GAM-01)

Guardas por introspecção (banco novo já nasce contratado via baseline).
batch_alter_table para compatibilidade SQLite (rebuild) e Postgres (ALTER).
"""
from alembic import op
import sqlalchemy as sa

revision = '0005_gamif_contract'
down_revision = '0004_gamif_backfill'
branch_labels = None
depends_on = None

GRUPO = ['user_points', 'badge', 'user_badge', 'achievements',
         'user_achievements', 'certificates', 'activity_feed']


def _col_nullable(insp, tabela):
    for c in insp.get_columns(tabela):
        if c['name'] == 'tenant_id':
            return c['nullable']
    return None


def _tem_fk_tenants(insp, tabela):
    return any(fk['referred_table'] == 'tenants' and fk['constrained_columns'] == ['tenant_id']
               for fk in insp.get_foreign_keys(tabela))


def _nome_fk_tenants(insp, tabela):
    """Nome da FK para tenants, ou None se for inline/sem nome (SQLite via
    baseline) — FK sem nome não pode ser derrubada por drop_constraint."""
    for fk in insp.get_foreign_keys(tabela):
        if fk['referred_table'] == 'tenants' and fk['constrained_columns'] == ['tenant_id']:
            return fk.get('name')
    return None


# uniques que deixam de ser globais e passam a ser por tenant
_UNIQUES_POR_TENANT = {
    'user_points': ('user_id', 'uq_user_points_tenant_user'),
    'badge': ('code', 'uq_badge_tenant_code'),
    'achievements': ('code', 'uq_achievements_tenant_code'),
}


def _uniques_globais(insp, tabela, coluna):
    uniques = {u['name']: u['column_names'] for u in insp.get_unique_constraints(tabela)}
    indexes = {i['name']: list(i['column_names']) for i in insp.get_indexes(tabela) if i.get('unique')}
    return ([nome for nome, cols in {**uniques, **indexes}.items() if cols == [coluna]],
            set(uniques))


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    for tabela in GRUPO:
        precisa_notnull = _col_nullable(insp, tabela)
        precisa_fk = not _tem_fk_tenants(insp, tabela)
        conv = _UNIQUES_POR_TENANT.get(tabela)
        if not (precisa_notnull or precisa_fk or conv):
            continue
        with op.batch_alter_table(tabela) as batch:
            if precisa_notnull:
                batch.alter_column('tenant_id', existing_type=sa.Uuid(), nullable=False)
            if precisa_fk:
                batch.create_foreign_key(f'fk_{tabela}_tenant', 'tenants',
                                         ['tenant_id'], ['id'])
            if conv:
                coluna, nome_novo = conv
                globais, uniques_existentes = _uniques_globais(insp, tabela, coluna)
                for nome in globais:
                    if nome is None:
                        # UNIQUE inline sem nome (SQLite de dev antigo) não é
                        # dropável por nome; no Postgres de produção os uniques
                        # têm nome automático (ex.: badge_code_key). Em dev,
                        # recrie o banco (seed.py) se precisar de multi-tenant.
                        print(f'  aviso: unique sem nome em {tabela}.{coluna} mantido (SQLite legado)')
                        continue
                    batch.drop_constraint(nome, type_='unique')
                if nome_novo not in uniques_existentes:
                    batch.create_unique_constraint(nome_novo, ['tenant_id', coluna])


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for tabela in reversed(GRUPO):
        with op.batch_alter_table(tabela) as batch:
            conv = _UNIQUES_POR_TENANT.get(tabela)
            if conv:
                _, nome_novo = conv
                uniques = {u['name'] for u in insp.get_unique_constraints(tabela)}
                if nome_novo in uniques:
                    batch.drop_constraint(nome_novo, type_='unique')
            nome_fk = _nome_fk_tenants(insp, tabela)
            if nome_fk:
                batch.drop_constraint(nome_fk, type_='foreignkey')
            # FK sem nome (inline do baseline SQLite): fica — inofensiva com
            # a coluna nullable; no Postgres a FK criada aqui é nomeada.
            if _col_nullable(insp, tabela) is False:
                batch.alter_column('tenant_id', existing_type=sa.Uuid(), nullable=True)
