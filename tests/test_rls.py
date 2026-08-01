"""Etapa 4.1 — teste de DEFESA EM PROFUNDIDADE (doc 02 §5.3, item 4).

Prova que, mesmo com uma query DELIBERADAMENTE sem filtro de aplicação, o
RLS impede ver linhas de outro tenant. Exige PostgreSQL real com uma role
SEM BYPASSRLS — roda apenas no CI (TEST_DATABASE_URL Postgres); em SQLite
é pulado (a defesa em dev é o filtro de aplicação + suíte de isolamento).
"""
import os
import subprocess
import sys
import uuid as uuid_mod

import pytest
from sqlalchemy import create_engine, text

PG_URL = os.getenv('TEST_DATABASE_URL', '')
pytestmark = pytest.mark.skipif(
    not PG_URL.startswith('postgres'),
    reason='defesa em profundidade exige PostgreSQL (CI)')

ROLE = 'app_rls_test'
ROLE_PWD = 'app_rls_test_pwd'


def _url_com_role(url, user, pwd):
    """troca credenciais na URL postgres://user:pwd@host/db"""
    resto = url.split('@', 1)[1]
    scheme = url.split('://', 1)[0]
    return f'{scheme}://{user}:{pwd}@{resto}'


@pytest.fixture(scope='module')
def rls_env():
    """Aplica as migrações (RLS incluso), cria role sem BYPASSRLS e dados
    em dois tenants."""
    # migra o banco do CI com o Alembic real
    r = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                       capture_output=True, text=True,
                       env={**os.environ, 'DATABASE_URL': PG_URL,
                            'ALEMBIC_DATABASE_URL': PG_URL})
    assert r.returncode == 0, r.stderr

    admin = create_engine(PG_URL)
    tid_a, tid_b = uuid_mod.uuid4(), uuid_mod.uuid4()
    with admin.begin() as c:
        c.execute(text(f"DROP ROLE IF EXISTS {ROLE}"))
        c.execute(text(f"CREATE ROLE {ROLE} LOGIN PASSWORD '{ROLE_PWD}' NOBYPASSRLS"))
        c.execute(text(f"GRANT USAGE ON SCHEMA public TO {ROLE}"))
        c.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ROLE}"))
        # dois tenants + um curso em cada
        c.execute(text(
            "INSERT INTO tenants (id, slug, nome, subdominio, plano, status, criado_em) "
            "VALUES (:a, 'rls-a', 'RLS A', 'rls-a', 'semente', 'active', now()), "
            "       (:b, 'rls-b', 'RLS B', 'rls-b', 'semente', 'active', now()) "
            "ON CONFLICT DO NOTHING"), {'a': tid_a, 'b': tid_b})
        c.execute(text(
            "INSERT INTO courses (name, acesso, status, tenant_id) "
            "VALUES ('Curso RLS A', 'publico', 'published', :a), "
            "       ('Curso RLS B', 'publico', 'published', :b)"),
            {'a': tid_a, 'b': tid_b})

    app_engine = create_engine(_url_com_role(PG_URL, ROLE, ROLE_PWD))
    yield {'admin': admin, 'app': app_engine, 'a': tid_a, 'b': tid_b}

    with admin.begin() as c:
        c.execute(text("DELETE FROM courses WHERE name LIKE 'Curso RLS %'"))
        c.execute(text("DELETE FROM tenants WHERE slug IN ('rls-a','rls-b')"))
        c.execute(text(f"DROP OWNED BY {ROLE}"))
        c.execute(text(f"DROP ROLE IF EXISTS {ROLE}"))


def test_query_sem_filtro_nao_ve_outro_tenant(rls_env):
    """A prova: SELECT sem NENHUM filtro de aplicação, com app.tenant_id = A,
    retorna só as linhas de A — o RLS segura o resto."""
    with rls_env['app'].begin() as c:
        c.execute(text("SELECT set_config('app.tenant_id', :t, true)"),
                  {'t': str(rls_env['a'])})
        nomes = {r[0] for r in c.execute(
            text("SELECT name FROM courses"))}   # deliberadamente sem WHERE
    assert 'Curso RLS A' in nomes
    assert 'Curso RLS B' not in nomes


def test_sem_guc_fail_closed_zero_linhas(rls_env):
    """Sem app.tenant_id definido, a role de app não vê NENHUMA linha."""
    with rls_env['app'].begin() as c:
        total = c.execute(text('SELECT count(*) FROM courses')).scalar()
    assert total == 0


def test_role_nao_escreve_em_outro_tenant(rls_env):
    """UPDATE sem filtro só alcança as linhas do tenant da transação."""
    with rls_env['app'].begin() as c:
        c.execute(text("SELECT set_config('app.tenant_id', :t, true)"),
                  {'t': str(rls_env['a'])})
        alteradas = c.execute(text(
            "UPDATE courses SET resumo = 'tocado' WHERE name LIKE 'Curso RLS %'"
        )).rowcount
    assert alteradas == 1   # só o curso de A

    with rls_env['admin'].begin() as c:
        resumo_b = c.execute(text(
            "SELECT resumo FROM courses WHERE name = 'Curso RLS B'")).scalar()
    assert resumo_b != 'tocado'


def test_superuser_bypassa_rls_por_isso_a_role_importa(rls_env):
    """Documenta a armadilha: a conexão ADMIN (superuser/owner com bypass)
    enxerga tudo mesmo com RLS — é por isso que a app PRECISA da role
    própria (runbook)."""
    with rls_env['admin'].begin() as c:
        nomes = {r[0] for r in c.execute(
            text("SELECT name FROM courses WHERE name LIKE 'Curso RLS %'"))}
    assert nomes == {'Curso RLS A', 'Curso RLS B'}
