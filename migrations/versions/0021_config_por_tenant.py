"""fix(TEN-03): platform_config e levels passam a ser por tenant

Revision ID: 0021_config_tenant
Revises: 0016_course_meta
Create Date: 2026-10-04

Antes eram globais: o admin de um tenant alterava nome, contatos e pontuação
de TODOS os tenants, e salvar os níveis apagava os níveis de todos. Os dados
existentes ficam com o tenant padrão; os níveis são copiados para os demais
tenants (a config é criada sob demanda por tenant).
"""
import os

from alembic import op
import sqlalchemy as sa

revision = '0021_config_tenant'
down_revision = '0016_course_meta'
branch_labels = None
depends_on = None

TABELAS = ('platform_config', 'levels')
UNIQUES = {
    'platform_config': ('uq_platform_config_tenant', ['tenant_id']),
    'levels': ('uq_levels_tenant_number', ['tenant_id', 'number']),
}


def _tenant_padrao_id(bind):
    slug = os.getenv('DEFAULT_TENANT_SLUG', 'ibc')
    row = bind.execute(sa.text('SELECT id FROM tenants WHERE slug = :s'), {'s': slug}).first()
    return row[0] if row else None


def _colunas(insp, tabela):
    return {c['name']: c for c in insp.get_columns(tabela)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existentes = set(insp.get_table_names())
    padrao = _tenant_padrao_id(bind)

    for tabela in TABELAS:
        if tabela not in existentes:
            continue  # banco novo: db.create_all cria já com o schema novo
        if 'tenant_id' not in _colunas(insp, tabela):
            with op.batch_alter_table(tabela) as batch:
                batch.add_column(sa.Column('tenant_id', sa.Uuid(), nullable=True))

        if padrao is not None:
            bind.execute(sa.text(f'UPDATE {tabela} SET tenant_id = :t WHERE tenant_id IS NULL'),
                         {'t': padrao})
        else:
            bind.execute(sa.text(f'DELETE FROM {tabela} WHERE tenant_id IS NULL'))

    if 'platform_config' in existentes:
        # uma linha por tenant: mantém a mais antiga
        bind.execute(sa.text(
            'DELETE FROM platform_config WHERE id NOT IN '
            '(SELECT MIN(id) FROM platform_config GROUP BY tenant_id)'))

    insp = sa.inspect(bind)
    for tabela in TABELAS:
        if tabela not in existentes:
            continue
        uniques = insp.get_unique_constraints(tabela)
        nome_novo, cols = UNIQUES[tabela]
        tem_fk = any(fk['referred_table'] == 'tenants' for fk in insp.get_foreign_keys(tabela))
        with op.batch_alter_table(tabela) as batch:
            batch.alter_column('tenant_id', existing_type=sa.Uuid(), nullable=False)
            if not tem_fk:
                batch.create_foreign_key(f'fk_{tabela}_tenant', 'tenants', ['tenant_id'], ['id'])
            if tabela == 'levels':
                for u in uniques:
                    if u['column_names'] == ['number'] and u['name']:
                        batch.drop_constraint(u['name'], type_='unique')
            if nome_novo not in {u['name'] for u in uniques}:
                batch.create_unique_constraint(nome_novo, cols)
        indices = {i['name'] for i in sa.inspect(bind).get_indexes(tabela)}
        if f'ix_{tabela}_tenant_id_id' not in indices:
            op.create_index(f'ix_{tabela}_tenant_id_id', tabela, ['tenant_id', 'id'])

    if 'levels' in existentes and padrao is not None and bind.dialect.name == 'postgresql':
        bind.execute(sa.text(
            'INSERT INTO levels (number, name, min_points, color, tenant_id) '
            'SELECT l.number, l.name, l.min_points, l.color, t.id '
            'FROM levels l CROSS JOIN tenants t '
            'WHERE l.tenant_id = :p AND t.id <> :p '
            'AND NOT EXISTS (SELECT 1 FROM levels x WHERE x.tenant_id = t.id AND x.number = l.number)'),
            {'p': padrao})

    if bind.dialect.name == 'postgresql':
        for tabela in TABELAS:
            if tabela not in existentes:
                continue
            op.execute(f'ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE {tabela} FORCE ROW LEVEL SECURITY')
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON {tabela}')
            op.execute(
                f"CREATE POLICY tenant_isolation ON {tabela} "
                f"USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)")


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existentes = set(insp.get_table_names())
    padrao = _tenant_padrao_id(bind)

    for tabela in reversed(TABELAS):
        if tabela not in existentes or 'tenant_id' not in _colunas(insp, tabela):
            continue
        if bind.dialect.name == 'postgresql':
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON {tabela}')
            op.execute(f'ALTER TABLE {tabela} NO FORCE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE {tabela} DISABLE ROW LEVEL SECURITY')
        # volta a ser global: só os dados do tenant padrão sobrevivem
        if padrao is not None:
            bind.execute(sa.text(f'DELETE FROM {tabela} WHERE tenant_id <> :p'), {'p': padrao})

        indices = {i['name'] for i in insp.get_indexes(tabela)}
        if f'ix_{tabela}_tenant_id_id' in indices:
            op.drop_index(f'ix_{tabela}_tenant_id_id', table_name=tabela)
        uniques = {u['name'] for u in insp.get_unique_constraints(tabela)}
        fks = [fk['name'] for fk in insp.get_foreign_keys(tabela)
               if fk['referred_table'] == 'tenants' and fk['name']]
        with op.batch_alter_table(tabela) as batch:
            nome_novo, _ = UNIQUES[tabela]
            if nome_novo in uniques:
                batch.drop_constraint(nome_novo, type_='unique')
            for nome in fks:
                batch.drop_constraint(nome, type_='foreignkey')
            if tabela == 'levels':
                batch.create_unique_constraint('levels_number_key', ['number'])
            batch.drop_column('tenant_id')
