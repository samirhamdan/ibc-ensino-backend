"""TEN-01 (Etapa 2.1): uuid7, models de tenancy, mixin e contexto de request.

Diferente dos testes de caracterização, estes são testes de ESPECIFICAÇÃO do
comportamento novo (critérios de aceite do PRD TEN-01/AUTH-01).
"""
import subprocess
import sys
import tempfile
import os

import pytest

from core.tenancy import uuid7, Tenant, TenantUser, TenantScopedModel
from core.tenancy import set_current_tenant, current_tenant, require_tenant
from werkzeug.exceptions import NotFound, Forbidden


# ── uuid7 ────────────────────────────────────────────────────────────────

def test_uuid7_versao_e_variante():
    u = uuid7()
    assert u.version == 7
    assert u.variant == 'specified in RFC 4122'


def test_uuid7_ordenavel_por_tempo():
    import time
    a = uuid7()
    time.sleep(0.002)  # garante ms distinto
    b = uuid7()
    assert a.bytes[:6] <= b.bytes[:6]
    assert a != b


# ── Models ───────────────────────────────────────────────────────────────

def test_seed_cria_tenants_ibc_e_demo(app):
    with app.app_context():
        from extensions import db
        from seed import seed_tenants
        seed_tenants()

        ibc = Tenant.query.filter_by(slug='ibc').first()
        demo = Tenant.query.filter_by(slug='demo').first()
        assert ibc and demo
        assert ibc.status == 'active'
        assert ibc.subdominio == 'ibc'
        assert ibc.tema_json['cor_primaria'] == '#008ea8'
        assert ibc.id.version == 7  # PK é UUIDv7

        # idempotente: rodar de novo não duplica
        seed_tenants()
        assert Tenant.query.filter_by(slug='ibc').count() == 1


def test_tenant_user_papel_por_tenant(app, seeded):
    """AUTH-01: mesmo usuário, papéis diferentes em tenants diferentes."""
    with app.app_context():
        from extensions import db
        from seed import seed_tenants
        seed_tenants()
        ibc = Tenant.query.filter_by(slug='ibc').first()
        demo = Tenant.query.filter_by(slug='demo').first()

        uid = seeded['users']['aluno']
        # Etapa 4.2: o LOGIN cria o vínculo no tenant da sessão — limpa
        # vínculos de testes anteriores antes de montar o cenário manual
        TenantUser.query.filter_by(user_id=uid).delete()
        db.session.add(TenantUser(tenant_id=ibc.id, user_id=uid, papel='aluno'))
        db.session.add(TenantUser(tenant_id=demo.id, user_id=uid, papel='admin_tenant'))
        db.session.commit()

        papeis = {tu.tenant.slug: tu.papel
                  for tu in TenantUser.query.filter_by(user_id=uid).all()}
        assert papeis == {'ibc': 'aluno', 'demo': 'admin_tenant'}

        # PK composta impede vínculo duplicado no mesmo tenant
        from sqlalchemy.exc import IntegrityError
        db.session.add(TenantUser(tenant_id=ibc.id, user_id=uid, papel='instrutor'))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        # Restaura o baseline do fixture `seeded` (vínculo 'aluno' no tenant
        # padrão) em vez de só apagar — `aluno` é compartilhado (session-
        # scoped) por toda a suíte; sem isto, login de aluno@test.com em
        # QUALQUER teste que rodar depois deste (em qualquer arquivo) falha
        # com 403 "sem acesso ao tenant" (achado real: só apareceu quando um
        # teste de outro arquivo, alfabeticamente depois, tentou logar).
        TenantUser.query.filter_by(user_id=uid).delete()
        db.session.add(TenantUser(tenant_id=ibc.id, user_id=uid, papel='aluno'))
        db.session.commit()


# ── Mixin TenantScopedModel ──────────────────────────────────────────────

def test_mixin_adiciona_tenant_id_e_indice_composto(app):
    with app.app_context():
        from extensions import db

        class _CoisaScoped(TenantScopedModel, db.Model):
            __tablename__ = 'test_coisas_scoped'
            id = db.Column(db.Integer, primary_key=True)
            nome = db.Column(db.String(50))

        db.create_all()  # cria só a tabela nova

        cols = {c.name for c in _CoisaScoped.__table__.columns}
        assert 'tenant_id' in cols
        tenant_col = _CoisaScoped.__table__.c.tenant_id
        assert tenant_col.nullable is False
        assert any(fk.column.table.name == 'tenants' for fk in tenant_col.foreign_keys)

        idx = {i.name: [c.name for c in i.columns] for i in _CoisaScoped.__table__.indexes}
        assert idx.get('ix_test_coisas_scoped_tenant_id_id') == ['tenant_id', 'id']


# ── Contexto de request ──────────────────────────────────────────────────

def test_require_tenant_sem_tenant_404(app):
    with app.test_request_context('/'):
        assert current_tenant() is None
        with pytest.raises(NotFound):
            require_tenant()


def test_require_tenant_ativo_retorna(app):
    with app.test_request_context('/'):
        t = Tenant(slug='x', nome='X', subdominio='x', status='active')
        set_current_tenant(t)
        assert require_tenant() is t
        assert current_tenant() is t


def test_require_tenant_suspenso_403(app):
    with app.test_request_context('/'):
        set_current_tenant(Tenant(slug='y', nome='Y', subdominio='y', status='suspended'))
        with pytest.raises(Forbidden):
            require_tenant()


def test_contexto_nao_vaza_entre_requests(app):
    with app.test_request_context('/'):
        set_current_tenant(Tenant(slug='z', nome='Z', subdominio='z'))
        assert current_tenant() is not None
    with app.test_request_context('/'):
        assert current_tenant() is None


# ── Migração Alembic reversível ──────────────────────────────────────────

def test_migracao_0001_reversivel():
    """upgrade → downgrade → upgrade em banco limpo (regra 3 do playbook).
    O CI repete isto em Postgres; aqui roda em SQLite."""
    fd, path = tempfile.mkstemp(suffix='.db', prefix='alembic_test_')
    os.close(fd)
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{path}'}
    try:
        for cmd in (['upgrade', 'head'], ['downgrade', 'base'], ['upgrade', 'head']):
            r = subprocess.run([sys.executable, '-m', 'alembic'] + cmd,
                               capture_output=True, text=True, env=env,
                               cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            assert r.returncode == 0, f'alembic {cmd}: {r.stderr}'
        # após o ciclo, as tabelas existem
        import sqlite3
        con = sqlite3.connect(path)
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        assert {'tenants', 'tenant_users', 'alembic_version'} <= tables
    finally:
        os.unlink(path)
