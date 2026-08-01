"""feat(TEN-01) grupo 2 progresso — CONTRACT: NOT NULL + FK + unique por tenant

Revision ID: 0008_prog_contract
Revises: 0007_prog_backfill
Create Date: 2026-07-09

- tenant_id NOT NULL + FK em todas as tabelas do grupo
- onboarding_answers: UNIQUE global de user_id vira (tenant_id, user_id) —
  o usuário responde o onboarding em cada tenant separadamente

Os uniques compostos existentes (uq_user_module, uq_user_course,
uq_user_trail) NÃO mudam: módulo/curso/trilha pertencem a um único tenant,
então a chave por usuário já é naturalmente escopada.
"""
from alembic import op
import sqlalchemy as sa

revision = '0008_prog_contract'
down_revision = '0007_prog_backfill'
branch_labels = None
depends_on = None

GRUPO = ['lesson_progress', 'progress', 'study_sessions',
         'user_trails', 'onboarding_answers']

_UNIQUES_POR_TENANT = {
    'onboarding_answers': ('user_id', 'uq_onboarding_tenant_user'),
}


def _col_nullable(insp, tabela):
    for c in insp.get_columns(tabela):
        if c['name'] == 'tenant_id':
            return c['nullable']
    return None


def _tem_fk_tenants(insp, tabela):
    return any(fk['referred_table'] == 'tenants' and fk['constrained_columns'] == ['tenant_id']
               for fk in insp.get_foreign_keys(tabela))


def _nome_fk_tenants(insp, tabela):
    for fk in insp.get_foreign_keys(tabela):
        if fk['referred_table'] == 'tenants' and fk['constrained_columns'] == ['tenant_id']:
            return fk.get('name')
    return None


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
            if _col_nullable(insp, tabela) is False:
                batch.alter_column('tenant_id', existing_type=sa.Uuid(), nullable=True)
