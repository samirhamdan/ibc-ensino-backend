"""Etapa 4.2 (AUTH-03 parcial): sessão presa ao tenant + papéis por tenant.

Regra dura (doc 02 §5.2/§6): credencial emitida no tenant A não vale no
tenant B → 403. Papéis vêm de tenant_users (AUTH-01), com fallback ao
User.role global durante a transição.
"""
import pytest

from tests.isolation.conftest import TenantClient, HOST_A, HOST_B, BASE


@pytest.fixture()
def cliente_bruto(iso_app, seeded):
    return iso_app.test_client()


def _login(client, host, email='aluno@test.com', password='senha123'):
    return client.post('/api/auth/login', headers={'Host': host},
                       json={'email': email, 'password': password})


def test_sessao_de_a_nao_vale_em_b(cliente_bruto):
    """Cookie de sessão emitido em A, apresentado em B → 403.

    O cookie é host-only, então o browser não o envia para outro subdomínio
    sozinho — aqui simulamos o cookie roubado/replicado (ou um futuro cookie
    de domínio-base): o guard do middleware é a defesa em profundidade."""
    assert _login(cliente_bruto, HOST_A).status_code == 200
    # em A funciona
    r = cliente_bruto.get('/api/auth/user', headers={'Host': HOST_A})
    assert r.status_code == 200

    # copia o cookie de A para o domínio de B (simulação de replay)
    cookie = cliente_bruto.get_cookie('session', domain=HOST_A)
    assert cookie is not None
    cliente_bruto.set_cookie('session', cookie.value, domain=HOST_B)

    r = cliente_bruto.get('/api/auth/user', headers={'Host': HOST_B})
    assert r.status_code == 403
    assert 'outro ambiente' in r.get_json()['error']
    # página HTML também
    r = cliente_bruto.get('/', headers={'Host': HOST_B})
    assert r.status_code == 403


def test_relogar_em_b_rebind_a_sessao(cliente_bruto):
    """Login em B emite sessão nova presa a B: replicá-la para A → 403
    (uma sessão pertence a UM tenant)."""
    assert _login(cliente_bruto, HOST_B).status_code == 200
    assert cliente_bruto.get('/api/auth/user', headers={'Host': HOST_B}).status_code == 200

    cookie = cliente_bruto.get_cookie('session', domain=HOST_B)
    cliente_bruto.set_cookie('session', cookie.value, domain=HOST_A)
    assert cliente_bruto.get('/api/auth/user', headers={'Host': HOST_A}).status_code == 403


def test_login_cria_vinculo_tenant_users(iso_app, seeded, cliente_bruto):
    with iso_app.app_context():
        from extensions import db
        from core.tenancy import TenantUser
        TenantUser.query.filter_by(user_id=seeded['users']['aluno']).delete()
        db.session.commit()

    assert _login(cliente_bruto, HOST_A).status_code == 200

    with iso_app.app_context():
        from core.tenancy import TenantUser, Tenant
        a_id = Tenant.query.filter_by(slug='ibc').first().id
        tu = TenantUser.query.filter_by(user_id=seeded['users']['aluno'],
                                        tenant_id=a_id).first()
        assert tu is not None
        assert tu.papel == 'aluno'


def test_admin_global_e_aluno_em_outro_tenant(iso_app, seeded):
    """Privilégio NÃO é herdado entre tenants: o admin do ibc entra no demo
    como aluno — admin em outro tenant é concessão explícita, nunca herança."""
    c = iso_app.test_client()
    assert _login(c, HOST_B, email='admin@test.com').status_code == 200
    # endpoint de admin no tenant B nega acesso (papel efetivo: aluno)
    r = c.get('/api/admin/users', headers={'Host': HOST_B})
    assert r.status_code == 403

    # no tenant padrão (ibc) o mesmo usuário segue admin
    c2 = iso_app.test_client()
    assert _login(c2, HOST_A, email='admin@test.com').status_code == 200
    assert c2.get('/api/admin/users', headers={'Host': HOST_A}).status_code == 200

    with iso_app.app_context():
        from extensions import db
        from core.tenancy import TenantUser, Tenant
        b_id = Tenant.query.filter_by(slug='demo').first().id
        TenantUser.query.filter_by(user_id=seeded['users']['admin'],
                                   tenant_id=b_id).delete()
        db.session.commit()


def test_papel_concedido_no_tenant_vale_so_la(iso_app, seeded):
    """Admin do tenant B promove o usuário LÁ; no ibc ele continua aluno."""
    uid = seeded['users']['aluno']
    with iso_app.app_context():
        from extensions import db
        from core.tenancy import TenantUser, Tenant
        b_id = Tenant.query.filter_by(slug='demo').first().id
        TenantUser.query.filter_by(user_id=uid, tenant_id=b_id).delete()
        db.session.add(TenantUser(tenant_id=b_id, user_id=uid, papel='admin'))
        db.session.commit()

    # no demo, é admin
    c = iso_app.test_client()
    assert _login(c, HOST_B).status_code == 200
    assert c.get('/api/admin/users', headers={'Host': HOST_B}).status_code == 200

    # no ibc, segue aluno
    c2 = iso_app.test_client()
    assert _login(c2, HOST_A).status_code == 200
    assert c2.get('/api/admin/users', headers={'Host': HOST_A}).status_code == 403

    with iso_app.app_context():
        from extensions import db
        from core.tenancy import TenantUser
        TenantUser.query.filter_by(user_id=uid).delete()
        db.session.commit()
