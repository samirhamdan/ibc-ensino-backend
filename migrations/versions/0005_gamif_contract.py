"""feat(TEN-01) grupo 1 gamificação — CONTRACT: NOT NULL + FK + uniques por tenant

Revision ID: 0005_gamif_contract
Revises: 0004_gamif_backfill
Create Date: 2026-07-08

Fecha o expand/contract do grupo:
- tenant_id vira NOT NULL + FK para tenants em todas as tabelas do grupo
- user_points: o UNIQUE global de user_id vira UNIQUE (tenant_id, user_id) —
  o mesmo usuário pode ter pontuação separada em cada tenant. Essa conversão
  é sempre segura sem deduplicação: user_id já era único globalmente antes,
  então (tenant_id, user_id) não pode colidir (um valor menos restritivo
  nunca cria duplicata onde não havia).
- badge.code e achievements.code: UNIQUE global vira UNIQUE (tenant_id, code)
  — cada tenant tem seu próprio catálogo (GAM-01). Diferente de user_points,
  `code` NUNCA foi fisicamente único em produção (só no model, sem migração
  de backfill correspondente) — banco restaurado de produção real tem
  duplicatas genuínas (achado no ensaio de staging, Fase 5: UniqueViolation
  em uq_badge_tenant_code). Por isso este grupo dedupica ANTES de criar o
  índice único (ver _deduplicar_e_reapontar).

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

# Tabelas cuja conversão de UNIQUE pode colidir com duplicata real de
# produção (ver docstring do módulo) — dedupicar antes de criar o índice.
# Cada entrada: tabela -> filhos que referenciam a PK dela e precisam ser
# reapontados para o registro mantido antes do registro duplicado ser
# apagado (filho, coluna_fk, chave_natural_do_filho).
_FILHOS_PARA_REAPONTAR = {
    'badge': [('user_badge', 'badge_id', ['user_id', 'badge_id'])],
    'achievements': [('user_achievements', 'achievement_id', ['user_id', 'achievement_id'])],
}


def _deduplicar_e_reapontar(bind, tabela, coluna):
    """Remove duplicatas de (tenant_id, coluna) mantendo o de MENOR id (mais
    antigo — badge/achievements.id é autoincrement, então id menor ~ criado
    primeiro). Antes de apagar cada duplicata, reaponta as linhas filhas
    (ex.: user_badge.badge_id) para o registro mantido — senão a conquista
    do aluno para aquele badge desapareceria, não só a entrada duplicada do
    catálogo. Se o próprio filho colidir (o aluno já tinha a badge do
    registro mantido TAMBÉM), a linha redundante do filho é descartada.

    Idempotente: sem duplicatas, os SELECTs abaixo não retornam nada e a
    função não faz nada. Downgrade NÃO desfaz a deduplicação (dado
    inconsistente removido não volta) — só remove o índice único, como já
    fazia antes desta correção."""
    linhas = bind.execute(sa.text(
        f'SELECT id, tenant_id, {coluna} FROM {tabela} ORDER BY tenant_id, {coluna}, id'
    )).fetchall()

    grupos = {}
    for row_id, tenant_id, valor in linhas:
        grupos.setdefault((tenant_id, valor), []).append(row_id)

    filhos = _FILHOS_PARA_REAPONTAR.get(tabela, [])
    total_duplicatas = 0
    for ids in grupos.values():
        if len(ids) < 2:
            continue
        keeper_id, *duplicatas = ids   # já ordenado por id (mais antigo primeiro)
        for dup_id in duplicatas:
            for tabela_filha, coluna_fk, chave_natural in filhos:
                outras_colunas = [c for c in chave_natural if c != coluna_fk]
                condicao_conflito = ' AND '.join(
                    f'outro.{c} = alvo.{c}' for c in outras_colunas)
                bind.execute(sa.text(
                    f'UPDATE {tabela_filha} AS alvo SET {coluna_fk} = :keeper '
                    f'WHERE alvo.{coluna_fk} = :dup '
                    f'AND NOT EXISTS ('
                    f'  SELECT 1 FROM {tabela_filha} AS outro '
                    f'  WHERE outro.{coluna_fk} = :keeper AND {condicao_conflito})'
                ), {'keeper': keeper_id, 'dup': dup_id})
                # Sobrou apontando pro duplicado só quem já tinha a versão do
                # keeper também (o UPDATE acima pulou por causa do conflito
                # com uq_user_badge/uq_user_achievement) — essa linha é
                # redundante, a conquista real já existe via o keeper.
                bind.execute(sa.text(
                    f'DELETE FROM {tabela_filha} WHERE {coluna_fk} = :dup'
                ), {'dup': dup_id})
            bind.execute(sa.text(f'DELETE FROM {tabela} WHERE id = :dup'), {'dup': dup_id})
            total_duplicatas += 1

    if total_duplicatas:
        print(f'  {tabela}: {total_duplicatas} duplicata(s) de (tenant_id, {coluna}) '
              f'removida(s) antes do índice único (dado real de produção).')


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

        if conv and tabela in _FILHOS_PARA_REAPONTAR:
            # SEMPRE antes de abrir o batch_alter_table: em SQLite o batch
            # faz rebuild da tabela (copia para uma tabela nova) — DML cru
            # nas tabelas filhas precisa acontecer contra o schema estável,
            # não no meio de um rebuild. Em Postgres não há essa exigência,
            # mas rodar antes também é seguro (mesma transação da migração).
            _deduplicar_e_reapontar(bind, tabela, conv[0])

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
