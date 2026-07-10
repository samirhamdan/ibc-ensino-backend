"""Correções de segurança da revisão da Fase 4 (RLS/auth/Redis).

Cobre especificamente os achados CRÍTICOS e ALTOS:
1. /api/auth/users e /api/admin/users listavam usuários de TODOS os tenants
2. DELETE de usuário alcançava qualquer tenant
3. signup/invite com role='admin' escalava privilégio para o tenant padrão
4. role_no_tenant() herdava o papel global fora do tenant padrão
5. grandfathering de sessão legada religava a QUALQUER tenant
6. vincular_usuario_ao_tenant() sem tratamento de corrida (login concorrente)
"""
import pytest

from tests.isolation.conftest import TenantClient, HOST_A, HOST_B, BASE


def _login(client, host, email, password='senha123'):
    return client.post('/api/auth/login', headers={'Host': host},
                       json={'email': email, 'password': password})


@pytest.fixture()
def admin_a(iso_app, seeded):
    c = TenantClient(iso_app.test_client(), HOST_A)
    assert _login(c, HOST_A, 'admin@test.com').status_code == 200
    return c


@pytest.fixture()
def admin_b(iso_app, seeded):
    """Cria (se preciso) e loga um admin próprio do tenant B, sem depender
    do admin global herdar privilégio em B (o que seria o próprio bug)."""
    with iso_app.app_context():
        from extensions import db
        from core.tenancy import Tenant, TenantUser
        from models import User
        b_id = Tenant.query.filter_by(slug='demo').first().id
        u = User.query.filter_by(email='admin-b@test.com').first()
        if u is None:
            u = User(name='Admin B', email='admin-b@test.com', role='aluno')
            u.set_password('senha123')
            db.session.add(u)
            db.session.flush()
        if not TenantUser.query.filter_by(tenant_id=b_id, user_id=u.id).first():
            db.session.add(TenantUser(tenant_id=b_id, user_id=u.id, papel='admin'))
        db.session.commit()
    c = TenantClient(iso_app.test_client(), HOST_B)
    assert _login(c, HOST_B, 'admin-b@test.com').status_code == 200
    return c


# ── #1: listagem de usuários não vaza entre tenants ──────────────────────

def test_admin_users_nao_lista_usuario_de_outro_tenant(admin_a, admin_b):
    """Um usuário que só existe (só tem vínculo) no tenant B não aparece na
    listagem do admin do tenant A, e vice-versa."""
    ids_a = {u['id'] for u in admin_a.get('/api/admin/users').get_json()}
    ids_b = {u['id'] for u in admin_b.get('/api/admin/users').get_json()}

    admin_b_info = admin_b.get('/api/auth/user').get_json()
    assert admin_b_info['id'] not in ids_a   # admin-b@test.com só existe em B
    assert admin_b_info['id'] in ids_b


def test_auth_users_endpoint_tambem_escopado(admin_a, admin_b):
    ids_a = {u['id'] for u in admin_a.get('/api/auth/users').get_json()}
    admin_b_info = admin_b.get('/api/auth/user').get_json()
    assert admin_b_info['id'] not in ids_a


# ── #1: DELETE de usuário não alcança outro tenant ───────────────────────

def test_delete_user_de_outro_tenant_e_404(admin_a, admin_b, iso_app):
    admin_b_info = admin_b.get('/api/auth/user').get_json()
    admin_b_id = admin_b_info['id']

    # admin de A tenta apagar o admin de B por ID direto → 404 (nunca 403:
    # não revela se o id existe em outro tenant)
    r = admin_a.delete(f'/api/auth/users/{admin_b_id}')
    assert r.status_code == 404

    # o usuário sobrevive intacto, ainda vinculado a B
    with iso_app.app_context():
        from models import User
        from core.tenancy import TenantUser, Tenant
        assert User.query.get(admin_b_id) is not None
        b_id = Tenant.query.filter_by(slug='demo').first().id
        assert TenantUser.query.filter_by(tenant_id=b_id, user_id=admin_b_id).first() is not None


def test_delete_user_remove_vinculo_local_preserva_conta_em_outros_tenants(
        admin_a, iso_app, seeded):
    """Usuário com vínculo em DOIS tenants: apagar em A remove só o vínculo
    de A; a conta e o vínculo em B sobrevivem (multi-tenant real)."""
    uid = seeded['users']['aluno']
    with iso_app.app_context():
        from extensions import db
        from core.tenancy import Tenant, TenantUser
        b_id = Tenant.query.filter_by(slug='demo').first().id
        if not TenantUser.query.filter_by(tenant_id=b_id, user_id=uid).first():
            db.session.add(TenantUser(tenant_id=b_id, user_id=uid, papel='aluno'))
            db.session.commit()

    r = admin_a.delete(f'/api/auth/users/{uid}')
    assert r.status_code == 200

    with iso_app.app_context():
        from models import User
        from core.tenancy import TenantUser, Tenant
        a_id = Tenant.query.filter_by(slug='ibc').first().id
        b_id = Tenant.query.filter_by(slug='demo').first().id
        assert User.query.get(uid) is not None   # conta global sobrevive
        assert TenantUser.query.filter_by(tenant_id=a_id, user_id=uid).first() is None
        assert TenantUser.query.filter_by(tenant_id=b_id, user_id=uid).first() is not None
        # limpeza
        TenantUser.query.filter_by(user_id=uid, tenant_id=b_id).delete()
        db.session.add(TenantUser(tenant_id=a_id, user_id=uid, papel='aluno'))
        db.session.commit()


# ── #2: signup com role elevado não escala para outro tenant ────────────

def test_signup_admin_por_admin_b_nao_vale_no_tenant_padrao(admin_b, iso_app):
    """admin_b cria um usuário com role=admin — só deve valer no tenant B.
    Ao logar pela primeira vez no tenant PADRÃO (A), o mesmo usuário não
    pode vir como admin (a falha original: User.role global gravava
    'admin', e o fallback de role_no_tenant o herdava em qualquer tenant)."""
    r = admin_b.post('/api/auth/signup', json={
        'name': 'Novo Admin', 'email': 'novo-admin@test.com',
        'password': 'senha123', 'role': 'admin',
    })
    assert r.status_code == 201
    assert r.get_json()['role'] == 'admin'   # efetivo EM B

    with iso_app.app_context():
        from models import User
        u = User.query.filter_by(email='novo-admin@test.com').first()
        assert u.role == 'aluno'   # global NUNCA vira admin

    # primeiro login no tenant padrão (A): sem vínculo lá ainda — desde a
    # correção HIGH-2 (login nunca cria tenant_users), nega acesso; mesmo
    # que recriasse, seria como 'aluno' (o global agora é 'aluno'), nunca
    # herdando o admin concedido só em B.
    c = TenantClient(iso_app.test_client(), HOST_A)
    assert _login(c, HOST_A, 'novo-admin@test.com').status_code == 403


def test_admin_update_user_nao_grava_role_global(admin_a, iso_app, seeded):
    """update_user concede o papel só em tenant_users — User.role global
    não muda (antes: u.role = role, escalando/vazando para outros tenants)."""
    uid = seeded['users']['aluno']
    with iso_app.app_context():
        from models import User
        role_global_antes = User.query.get(uid).role

    r = admin_a.put(f'/api/admin/users/{uid}',
                    json={'name': 'Aluno Teste', 'email': 'aluno@test.com', 'role': 'admin'})
    assert r.status_code == 200
    assert r.get_json()['role'] == 'admin'

    with iso_app.app_context():
        from models import User
        from core.tenancy import TenantUser, Tenant
        assert User.query.get(uid).role == role_global_antes   # global intocado
        a_id = Tenant.query.filter_by(slug='ibc').first().id
        assert TenantUser.query.filter_by(tenant_id=a_id, user_id=uid).first().papel == 'admin'
        # restaura
        TenantUser.query.filter_by(tenant_id=a_id, user_id=uid).first().papel = 'aluno'
        from extensions import db
        db.session.commit()


# ── #2 (unitário): role_no_tenant não herda fora do tenant padrão ───────

def test_role_no_tenant_fallback_restrito_ao_tenant_padrao(iso_app, seeded):
    from core.tenancy import role_no_tenant, set_current_tenant, Tenant
    from core.tenancy.models import TenantUser
    from models import User

    with iso_app.app_context():
        admin_id = seeded['users']['admin']
        a_id = Tenant.query.filter_by(slug='ibc').first().id
        b_id = Tenant.query.filter_by(slug='demo').first().id
        # remove TAMBÉM o vínculo do tenant padrão (o fixture `seeded` cria
        # um, espelhando a migração 0013) para testar genuinamente o
        # FALLBACK — não um papel já explícito em tenant_users.
        TenantUser.query.filter_by(user_id=admin_id).delete()
        from extensions import db
        db.session.commit()

    # Cada bloco abaixo é independente (não aninhado em app_context externo)
    # para que role_no_tenant() ganhe um `g` novo por bloco — senão o cache
    # por-request (g._papel_cache) vaza entre os dois tenants testados,
    # já que ambos compartilhariam a mesma app-context caso aninhados.
    with iso_app.test_request_context('/'):
        user = User.query.get(admin_id)
        set_current_tenant(Tenant.query.get(b_id))   # tenant NÃO-padrão, sem vínculo
        assert role_no_tenant(user) == 'aluno'        # NÃO herda admin global

    with iso_app.test_request_context('/'):
        user = User.query.get(admin_id)
        set_current_tenant(Tenant.query.get(a_id))   # tenant PADRÃO, sem vínculo explícito
        assert role_no_tenant(user) == 'admin'        # paridade mono-tenant preservada

    # restaura o vínculo que o fixture `seeded` esperava
    with iso_app.app_context():
        from extensions import db
        db.session.add(TenantUser(tenant_id=a_id, user_id=admin_id, papel='admin'))
        db.session.commit()


# ── #3: grandfathering só liga sessão legada ao tenant padrão ───────────

def _sessao_legada(client, uid, host_do_cookie):
    """Cria uma sessão SEM 'tenant_id' (simula sessão pré-Etapa 4.2) e a
    vincula ao cookiejar do host indicado — o cookiejar do test client é
    escopado por domínio, então sem isso a sessão nunca seria enviada de
    volta numa requisição para outro Host (mesmo padrão de
    test_auth_isolation.py::test_sessao_de_a_nao_vale_em_b)."""
    with client.session_transaction() as sess:
        sess['user_id'] = uid
    cookie = client.get_cookie('session')
    assert cookie is not None
    client.set_cookie('session', cookie.value, domain=host_do_cookie)


def test_sessao_legada_sem_tenant_id_so_liga_no_padrao(iso_app, seeded):
    c = iso_app.test_client()
    _sessao_legada(c, seeded['users']['aluno'], HOST_A)

    # apresentada no tenant PADRÃO (A): religada normalmente
    r = c.get('/api/auth/user', headers={'Host': HOST_A})
    assert r.status_code == 200


def test_sessao_legada_sem_tenant_id_nao_liga_em_tenant_nao_padrao(iso_app, seeded):
    c = iso_app.test_client()
    _sessao_legada(c, seeded['users']['aluno'], HOST_B)

    # apresentada em B primeiro: NÃO deve ser aceita como se fosse de B
    r = c.get('/api/auth/user', headers={'Host': HOST_B})
    assert r.status_code == 401   # tratada como não-autenticada, não religada

    # a sessão foi invalidada (não religada) — nem repetir em B, nem
    # tentar em A depois autentica magicamente
    assert c.get('/api/auth/user', headers={'Host': HOST_B}).status_code == 401
    assert c.get('/api/auth/user', headers={'Host': HOST_A}).status_code == 401


# ── #5: vincular_usuario_ao_tenant é idempotente sob chamada repetida ───

def test_vincular_usuario_ao_tenant_idempotente(iso_app, seeded):
    from core.tenancy import vincular_usuario_ao_tenant, Tenant
    from core.tenancy.models import TenantUser
    from models import User

    with iso_app.app_context():
        uid = seeded['users']['tutor']
        a = Tenant.query.filter_by(slug='ibc').first()
        with iso_app.test_request_context('/'):
            from core.tenancy import set_current_tenant
            set_current_tenant(a)
            user = User.query.get(uid)
            vincular_usuario_ao_tenant(user)
            vincular_usuario_ao_tenant(user)   # segunda chamada não deve estourar
            vincular_usuario_ao_tenant(user)

        assert TenantUser.query.filter_by(tenant_id=a.id, user_id=uid).count() == 1
