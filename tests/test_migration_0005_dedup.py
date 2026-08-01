"""Correção da migração 0005 (achado no ensaio de staging, Fase 5):
UniqueViolation ao criar uq_badge_tenant_code contra dado real de produção
com badges duplicados. Testa _deduplicar_e_reapontar isoladamente — schema
mínimo pré-0005 (sem o índice único, tenant_id já preenchido pelo backfill
0004), sem depender da cadeia completa do Alembic.
"""
import importlib
import uuid

import pytest
from sqlalchemy import create_engine, text

migracao = importlib.import_module('migrations.versions.0005_gamif_contract')


@pytest.fixture()
def engine():
    eng = create_engine('sqlite:///:memory:')
    with eng.begin() as conn:
        conn.execute(text(
            'CREATE TABLE badge (id INTEGER PRIMARY KEY, tenant_id TEXT, '
            'code TEXT, name TEXT)'))
        conn.execute(text(
            'CREATE TABLE user_badge (id INTEGER PRIMARY KEY, tenant_id TEXT, '
            'user_id INTEGER, badge_id INTEGER, '
            'UNIQUE(user_id, badge_id))'))
    return eng


def test_sem_duplicata_nao_faz_nada(engine):
    tid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO badge (id, tenant_id, code, name) "
                          "VALUES (1, :t, 'novo_discipulo', 'Novo Discípulo')"), {'t': tid})
        migracao._deduplicar_e_reapontar(conn, 'badge', 'code')
        n = conn.execute(text('SELECT COUNT(*) FROM badge')).scalar()
        assert n == 1


def test_mantem_menor_id_remove_duplicatas(engine):
    """Cenário exato do achado: dois badges com o mesmo (tenant_id, code)
    em produção — mantém o de menor id, remove os outros."""
    tid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO badge (id, tenant_id, code, name) VALUES "
                          "(5, :t, 'novo_discipulo', 'Novo Discípulo (antigo)'), "
                          "(9, :t, 'novo_discipulo', 'Novo Discípulo (duplicado)'), "
                          "(12, :t, 'novo_discipulo', 'Novo Discípulo (duplicado 2)')"),
                    {'t': tid})
        migracao._deduplicar_e_reapontar(conn, 'badge', 'code')

        restantes = conn.execute(text('SELECT id FROM badge')).fetchall()
        assert [r[0] for r in restantes] == [5]


def test_reaponta_user_badge_para_o_registro_mantido(engine):
    """Um aluno que desbloqueou a versão DUPLICADA do badge não pode perder
    a conquista — user_badge.badge_id é reapontado pro id mantido."""
    tid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO badge (id, tenant_id, code, name) VALUES "
                          "(5, :t, 'novo_discipulo', 'a'), (9, :t, 'novo_discipulo', 'b')"),
                    {'t': tid})
        conn.execute(text("INSERT INTO user_badge (id, tenant_id, user_id, badge_id) "
                          "VALUES (1, :t, 42, 9)"), {'t': tid})
        migracao._deduplicar_e_reapontar(conn, 'badge', 'code')

        badge_ids = conn.execute(text('SELECT id FROM badge')).fetchall()
        assert [r[0] for r in badge_ids] == [5]
        vinculo = conn.execute(text(
            'SELECT badge_id FROM user_badge WHERE id = 1')).scalar()
        assert vinculo == 5


def test_conflito_no_filho_descarta_a_linha_redundante(engine):
    """O aluno já tinha a conquista via o registro MANTIDO e TAMBÉM via o
    duplicado (dado inconsistente pré-tenancy) — repontar criaria uma
    violação de uq_user_badge (user_id, badge_id); a linha redundante do
    filho é descartada, a conquista real (a do keeper) sobrevive."""
    tid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO badge (id, tenant_id, code, name) VALUES "
                          "(5, :t, 'novo_discipulo', 'a'), (9, :t, 'novo_discipulo', 'b')"),
                    {'t': tid})
        conn.execute(text("INSERT INTO user_badge (id, tenant_id, user_id, badge_id) VALUES "
                          "(1, :t, 42, 5), (2, :t, 42, 9)"), {'t': tid})
        migracao._deduplicar_e_reapontar(conn, 'badge', 'code')

        vinculos = conn.execute(text(
            'SELECT user_id, badge_id FROM user_badge')).fetchall()
        assert vinculos == [(42, 5)]


def test_dedup_nao_mistura_tenants_diferentes(engine):
    """(tenant_id, code) é a chave — mesmo code em tenants DIFERENTES não é
    duplicata, cada tenant tem seu próprio catálogo (GAM-01)."""
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO badge (id, tenant_id, code, name) VALUES "
                          "(1, :t1, 'novo_discipulo', 'a'), (2, :t2, 'novo_discipulo', 'b')"),
                    {'t1': t1, 't2': t2})
        migracao._deduplicar_e_reapontar(conn, 'badge', 'code')
        n = conn.execute(text('SELECT COUNT(*) FROM badge')).scalar()
        assert n == 2


def test_apos_dedup_o_indice_unico_pode_ser_criado(engine):
    """Fim a fim: reproduz o UniqueViolation do ensaio de staging e prova
    que ele deixa de acontecer depois da deduplicação."""
    tid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO badge (id, tenant_id, code, name) VALUES "
                          "(5, :t, 'novo_discipulo', 'a'), (9, :t, 'novo_discipulo', 'b')"),
                    {'t': tid})

    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(text(
                'CREATE UNIQUE INDEX uq_badge_tenant_code ON badge (tenant_id, code)'))

    with engine.begin() as conn:
        migracao._deduplicar_e_reapontar(conn, 'badge', 'code')
        conn.execute(text(
            'CREATE UNIQUE INDEX uq_badge_tenant_code ON badge (tenant_id, code)'))
        n = conn.execute(text('SELECT COUNT(*) FROM badge')).scalar()
        assert n == 1


def test_idempotente_segunda_chamada_nao_faz_nada(engine):
    tid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO badge (id, tenant_id, code, name) VALUES "
                          "(5, :t, 'novo_discipulo', 'a'), (9, :t, 'novo_discipulo', 'b')"),
                    {'t': tid})
        migracao._deduplicar_e_reapontar(conn, 'badge', 'code')
        migracao._deduplicar_e_reapontar(conn, 'badge', 'code')   # 2ª vez, sem erro
        n = conn.execute(text('SELECT COUNT(*) FROM badge')).scalar()
        assert n == 1
