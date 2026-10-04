"""TEN-04 / UX_OPERADOR_SAAS P0: painel do operador — 2FA, ciclo de vida de
tenants e auditoria de toda ação."""
import time

import pytest

from core.plataforma import totp


@pytest.fixture()
def relogio(monkeypatch):
    """Controla o passo TOTP atual (cada ação destrutiva consome um código novo)."""
    estado = {'contador': totp.contador_atual()}
    monkeypatch.setattr(totp, 'contador_atual', lambda agora=None: estado['contador'])
    return estado


@pytest.fixture()
def operador(app, seeded):
    from extensions import db
    from models import User
    from core.tenancy import TenantUser, default_tenant_id
    from core.plataforma.models import OperadorPlataforma
    with app.app_context():
        u = User.query.filter_by(email='op@test.com').first()
        if u is None:
            u = User(name='Operador', email='op@test.com', role='aluno')
            u.set_password('senha123')
            db.session.add(u)
            db.session.flush()
            db.session.add(TenantUser(tenant_id=default_tenant_id(), user_id=u.id, papel='aluno'))
        OperadorPlataforma.query.filter_by(user_id=u.id).delete()
        db.session.add(OperadorPlataforma(user_id=u.id))
        db.session.commit()
        return u.id


def _codigo(segredo, relogio, avancar=True):
    if avancar:
        relogio['contador'] += 1
    return totp._codigo(segredo, relogio['contador'])


@pytest.fixture()
def ops(app, operador, relogio):
    c = app.test_client()
    assert c.post('/api/auth/login', json={'email': 'op@test.com', 'password': 'senha123'}).status_code == 200
    segredo = c.post('/api/ops/2fa/configurar').get_json()['segredo']
    assert c.post('/api/ops/2fa/verificar', json={'codigo': _codigo(segredo, relogio, False)}).status_code == 200
    c.segredo = segredo
    return c


def test_rfc6238_vetores():
    s = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
    assert totp._codigo(s, 59 // 30) == '287082'
    assert totp._codigo(s, 1111111109 // 30) == '081804'


def test_2fa_obrigatorio_antes_de_qualquer_dado(app, operador, relogio):
    c = app.test_client()
    c.post('/api/auth/login', json={'email': 'op@test.com', 'password': 'senha123'})
    me = c.get('/api/ops/me').get_json()
    assert me['operador'] and not me['2fa_configurado']
    r = c.get('/api/ops/pulso')
    assert r.status_code == 428 and r.get_json()['precisa_2fa']

    segredo = c.post('/api/ops/2fa/configurar').get_json()['segredo']
    assert c.post('/api/ops/2fa/verificar', json={'codigo': '000000'}).status_code == 400
    codigo = _codigo(segredo, relogio, False)
    assert c.post('/api/ops/2fa/verificar', json={'codigo': codigo}).status_code == 200
    assert c.get('/api/ops/pulso').status_code == 200
    # o mesmo código não serve duas vezes
    assert c.post('/api/ops/2fa/verificar', json={'codigo': codigo}).status_code == 400


def test_sessao_expira_apos_30_min_de_inatividade(ops):
    with ops.session_transaction() as s:
        s['ops_ultimo'] = time.time() - 31 * 60
    assert ops.get('/api/ops/pulso').status_code == 428


def test_criar_tenant_completo_e_auditado(app, ops):
    assert ops.post('/api/ops/tenants', json={'nome': 'X', 'slug': 'www', 'admin_email': 'a@b.com'}).status_code == 400
    assert ops.post('/api/ops/tenants', json={'nome': 'X', 'slug': 'A B', 'admin_email': 'a@b.com'}).status_code == 400

    r = ops.post('/api/ops/tenants', json={'nome': 'Escola Nova', 'slug': 'escola-nova', 'plano': 'crescimento',
                                            'admin_nome': 'Diretora', 'admin_email': 'diretora@escola.com'})
    assert r.status_code == 201, r.get_json()
    dados = r.get_json()
    assert dados['senha_temporaria']
    assert ops.get('/api/ops/tenants/disponibilidade?slug=escola-nova').get_json()['disponivel'] is False
    assert ops.post('/api/ops/tenants', json={'nome': 'Outra', 'slug': 'escola-nova',
                                              'admin_email': 'x@y.com'}).status_code == 400

    with app.app_context():
        from core.tenancy import Tenant, TenantUser
        from models import PlatformConfig, Level, Badge, Category, User
        from shared.audit import AuditLog
        t = Tenant.query.filter_by(slug='escola-nova').first()
        assert t.plano == 'crescimento' and t.status == 'active'
        admin = User.query.filter_by(email='diretora@escola.com').first()
        assert TenantUser.query.filter_by(tenant_id=t.id, user_id=admin.id).first().papel == 'admin'
        assert PlatformConfig.query.filter_by(tenant_id=t.id).first().platform_name == 'Escola Nova'
        assert Level.query.filter_by(tenant_id=t.id).count() > 0
        assert Badge.query.filter_by(tenant_id=t.id).count() > 0
        assert Category.query.filter_by(tenant_id=t.id).count() > 0
        assert AuditLog.query.filter_by(tenant_id=t.id, acao='operador.tenant_criado').count() == 1
        tid = str(t.id)

    lista = ops.get('/api/ops/tenants?busca=escola').get_json()
    assert any(x['slug'] == 'escola-nova' for x in lista['tenants'])
    perfil = ops.get(f'/api/ops/tenants/{tid}').get_json()
    assert perfil['admins'][0]['email'] == 'diretora@escola.com'
    assert ops.get('/api/ops/auditoria').get_json()['total'] >= 1


def test_suspender_exige_codigo_novo_e_motivo(app, ops, relogio):
    r = ops.post('/api/ops/tenants', json={'nome': 'Para Suspender', 'slug': 'para-suspender',
                                            'admin_email': 'adm@suspender.com'})
    tid = r.get_json()['tenant']['id']
    url = f'/api/ops/tenants/{tid}/status'

    assert ops.post(url, json={'status': 'suspended', 'motivo': 'Inadimplente'}).status_code == 400
    assert ops.post(url, json={'status': 'suspended', 'motivo': 'x',
                               'codigo': _codigo(ops.segredo, relogio)}).status_code == 400
    r = ops.post(url, json={'status': 'suspended', 'motivo': 'Pedido do cliente',
                            'codigo': _codigo(ops.segredo, relogio)})
    assert r.status_code == 200 and r.get_json()['tenant']['status'] == 'suspended'
    r = ops.post(url, json={'status': 'active', 'codigo': _codigo(ops.segredo, relogio)})
    assert r.status_code == 200 and r.get_json()['tenant']['status'] == 'active'

    assert ops.patch(f'/api/ops/tenants/{tid}', json={'plano': 'comunidade'}).status_code == 200
    assert ops.patch(f'/api/ops/tenants/{tid}', json={'plano': 'inexistente'}).status_code == 400

    with app.app_context():
        from shared.audit import AuditLog
        acoes = [a.acao for a in AuditLog.query.filter_by(tenant_id=__import__('uuid').UUID(tid)).all()]
        assert 'operador.tenant_suspended' in acoes
        assert 'operador.tenant_active' in acoes
        assert 'operador.tenant_atualizado' in acoes


def test_tenant_padrao_nao_pode_ser_suspenso(app, ops, relogio):
    with app.app_context():
        from core.tenancy import default_tenant_id
        tid = str(default_tenant_id())
    r = ops.post(f'/api/ops/tenants/{tid}/status', json={'status': 'suspended', 'motivo': 'teste de bloqueio',
                                                         'codigo': _codigo(ops.segredo, relogio)})
    assert r.status_code == 400


def test_admin_de_tenant_nao_e_operador(admin):
    assert admin.get('/api/ops/me').status_code == 403
    assert admin.get('/api/ops/tenants').status_code == 403


def test_flag_operador_vem_nos_dados_do_usuario(app, operador, admin):
    """O menu do operador é decidido pelo payload do usuário (sem request extra que gera 403)."""
    c = app.test_client()
    r = c.post('/api/auth/login', json={'email': 'op@test.com', 'password': 'senha123'})
    assert r.get_json()['operador'] is True
    assert c.get('/api/auth/user').get_json()['operador'] is True
    assert admin.get('/api/auth/user').get_json()['operador'] is False
