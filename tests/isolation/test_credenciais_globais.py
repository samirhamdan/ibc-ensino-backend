"""Correção HIGH-1/HIGH-2 (revisão Fable 5 pós-AUTH-03): credenciais globais
do User (senha/e-mail/is_active) nunca são alteráveis por um admin de
tenant, e login NUNCA recria tenant_users.

TESTE 1–7 do pedido de correção.
"""
import pytest

from tests.isolation.conftest import TenantClient, HOST_A, HOST_B


def _login(client, host, email, password='senha123'):
    return client.post('/api/auth/login', headers={'Host': host},
                       json={'email': email, 'password': password})


@pytest.fixture()
def usuario_admin_em_ab(iso_app, seeded):
    """Usuário compartilhado, admin em A (via seeded) e admin em B (vínculo
    explícito, simulando convite) — o cenário exato do achado HIGH-1."""
    from extensions import db
    from core.tenancy import Tenant, TenantUser
    uid = seeded['users']['admin']
    with iso_app.app_context():
        b_id = Tenant.query.filter_by(slug='demo').first().id
        if not TenantUser.query.filter_by(tenant_id=b_id, user_id=uid).first():
            db.session.add(TenantUser(tenant_id=b_id, user_id=uid, papel='admin'))
            db.session.commit()
    yield uid
    with iso_app.app_context():
        b_id = Tenant.query.filter_by(slug='demo').first().id
        TenantUser.query.filter_by(tenant_id=b_id, user_id=uid).delete()
        db.session.commit()


@pytest.fixture()
def admin_a_logado(iso_app, usuario_admin_em_ab):
    c = TenantClient(iso_app.test_client(), HOST_A)
    assert _login(c, HOST_A, 'admin@test.com').status_code == 200
    return c


# ── TESTE 1: admin A não altera senha (reset-password administrativo) ────

def test_admin_nao_altera_senha_de_usuario_compartilhado(iso_app, admin_a_logado, usuario_admin_em_ab):
    from models import User
    with iso_app.app_context():
        hash_antes = User.query.get(usuario_admin_em_ab).password_hash

    r = admin_a_logado.post(f'/api/admin/users/{usuario_admin_em_ab}/reset-password',
                            json={'new_password': 'senhaNova123'})
    assert r.status_code == 403

    with iso_app.app_context():
        assert User.query.get(usuario_admin_em_ab).password_hash == hash_antes

    # a senha antiga continua válida em B (a conta não foi sequestrada)
    c_b = TenantClient(iso_app.test_client(), HOST_B)
    assert _login(c_b, HOST_B, 'admin@test.com').status_code == 200


# ── TESTE 2: admin A não altera e-mail ────────────────────────────────────

def test_admin_nao_altera_email_de_usuario_compartilhado(iso_app, admin_a_logado, usuario_admin_em_ab):
    from models import User
    with iso_app.app_context():
        email_antes = User.query.get(usuario_admin_em_ab).email

    r = admin_a_logado.put(f'/api/admin/users/{usuario_admin_em_ab}',
                           json={'name': 'Admin', 'email': 'sequestrado@test.com', 'role': 'admin'})
    # a rota não aceita mais 'email' — sucesso (200) sem qualquer efeito no
    # e-mail, OU rejeição explícita; em nenhum caso o e-mail global muda
    assert r.status_code in (200, 400)

    with iso_app.app_context():
        assert User.query.get(usuario_admin_em_ab).email == email_antes


# ── TESTE 3: admin A não altera is_active global ─────────────────────────

def test_admin_nao_altera_is_active_de_usuario_compartilhado(iso_app, admin_a_logado, usuario_admin_em_ab):
    from models import User
    with iso_app.app_context():
        ativo_antes = User.query.get(usuario_admin_em_ab).is_active

    r = admin_a_logado.post(f'/api/admin/users/{usuario_admin_em_ab}/toggle-active')
    assert r.status_code == 403

    with iso_app.app_context():
        assert User.query.get(usuario_admin_em_ab).is_active == ativo_antes


# ── TESTE 4: usuário removido do tenant não recupera acesso relogando ────

def test_usuario_removido_do_tenant_login_e_403_sem_recriar_vinculo(iso_app, seeded):
    from extensions import db
    from core.tenancy import Tenant, TenantUser
    uid = seeded['users']['aluno']

    admin_c = TenantClient(iso_app.test_client(), HOST_A)
    assert _login(admin_c, HOST_A, 'admin@test.com').status_code == 200
    assert admin_c.delete(f'/api/auth/users/{uid}').status_code == 200

    with iso_app.app_context():
        a_id = Tenant.query.filter_by(slug='ibc').first().id
        assert TenantUser.query.filter_by(tenant_id=a_id, user_id=uid).first() is None

    c = TenantClient(iso_app.test_client(), HOST_A)
    r = _login(c, HOST_A, 'aluno@test.com')
    assert r.status_code == 403

    with iso_app.app_context():
        a_id = Tenant.query.filter_by(slug='ibc').first().id
        # login não recriou o vínculo
        assert TenantUser.query.filter_by(tenant_id=a_id, user_id=uid).first() is None
        # restaura o baseline do fixture `seeded`
        db.session.add(TenantUser(tenant_id=a_id, user_id=uid, papel='aluno'))
        db.session.commit()


# ── TESTE 5: readicionar o usuário (convite) restaura o login ────────────

def test_admin_readiciona_usuario_e_login_volta_a_funcionar(iso_app, seeded):
    """Reconvidar via POST /admin/users/invite (não inserção direta no
    banco): a rota reconhece que já existe uma conta global com esse e-mail
    e só cria o vínculo — a senha antiga continua valendo (convite nunca
    grava credencial global, correção HIGH-1)."""
    from core.tenancy import Tenant, TenantUser
    uid = seeded['users']['aluno']

    admin_c = TenantClient(iso_app.test_client(), HOST_A)
    assert _login(admin_c, HOST_A, 'admin@test.com').status_code == 200
    assert admin_c.delete(f'/api/auth/users/{uid}').status_code == 200

    c = TenantClient(iso_app.test_client(), HOST_A)
    assert _login(c, HOST_A, 'aluno@test.com').status_code == 403

    r = admin_c.post('/api/admin/users/invite',
                     json={'name': 'Aluno', 'email': 'aluno@test.com',
                           'role': 'aluno', 'password': 'irrelevante123'})
    assert r.status_code == 201

    with iso_app.app_context():
        a_id = Tenant.query.filter_by(slug='ibc').first().id
        assert TenantUser.query.filter_by(tenant_id=a_id, user_id=uid).first().papel == 'aluno'

    c2 = TenantClient(iso_app.test_client(), HOST_A)
    # senha ORIGINAL ('senha123') continua válida — o convite não a trocou
    assert _login(c2, HOST_A, 'aluno@test.com').status_code == 200

    c2 = TenantClient(iso_app.test_client(), HOST_A)
    assert _login(c2, HOST_A, 'aluno@test.com').status_code == 200


# ── TESTE 6: usuário continua ativo normalmente em outro tenant ──────────

def test_remocao_de_um_tenant_nao_afeta_outro(iso_app, seeded):
    from extensions import db
    from core.tenancy import Tenant, TenantUser
    uid = seeded['users']['aluno']

    with iso_app.app_context():
        b_id = Tenant.query.filter_by(slug='demo').first().id
        db.session.add(TenantUser(tenant_id=b_id, user_id=uid, papel='aluno'))
        db.session.commit()

    admin_c = TenantClient(iso_app.test_client(), HOST_A)
    assert _login(admin_c, HOST_A, 'admin@test.com').status_code == 200
    assert admin_c.delete(f'/api/auth/users/{uid}').status_code == 200

    c_a = TenantClient(iso_app.test_client(), HOST_A)
    assert _login(c_a, HOST_A, 'aluno@test.com').status_code == 403

    c_b = TenantClient(iso_app.test_client(), HOST_B)
    assert _login(c_b, HOST_B, 'aluno@test.com').status_code == 200

    with iso_app.app_context():
        a_id = Tenant.query.filter_by(slug='ibc').first().id
        b_id = Tenant.query.filter_by(slug='demo').first().id
        TenantUser.query.filter_by(tenant_id=b_id, user_id=uid).delete()
        db.session.add(TenantUser(tenant_id=a_id, user_id=uid, papel='aluno'))
        db.session.commit()


# ── TESTE extra (2ª rodada da Fable): sessão viva de admin removido ──────

def test_sessao_viva_de_admin_removido_do_tenant_padrao_perde_privilegio(iso_app, seeded):
    """Achado da 2ª revisão: DELETE /api/auth/users/<id> não revoga a sessão
    já aberta do usuário removido; se role_no_tenant() ainda caísse no
    fallback de User.role no tenant padrão, a PRÓXIMA requisição dessa
    sessão devolveria o papel global de novo — um admin removido recuperava
    admin sozinho, sem relogar. Como o fallback foi removido por completo,
    a sessão sobrevive (não é a sessão que é revogada) mas o papel efetivo
    cai para 'aluno' assim que o vínculo desaparece."""
    from extensions import db
    from core.tenancy import Tenant, TenantUser
    from models import User

    # Usuário DESCARTÁVEL (não o tutor/aluno/admin seedados, compartilhados
    # por toda a suíte) — delete_user também desvincula referências
    # possuídas noutro lugar (Course.tutor_id etc.), então reusar um usuário
    # seedado aqui poluiria fixtures de OUTROS testes.
    with iso_app.app_context():
        a_id = Tenant.query.filter_by(slug='ibc').first().id
        vitima_user = User(name='Vítima', email='vitima-high2@test.com', role='aluno')
        vitima_user.set_password('senha123')
        db.session.add(vitima_user)
        db.session.flush()
        uid = vitima_user.id
        db.session.add(TenantUser(tenant_id=a_id, user_id=uid, papel='admin'))
        db.session.commit()

    vitima = TenantClient(iso_app.test_client(), HOST_A)
    assert _login(vitima, HOST_A, 'vitima-high2@test.com').status_code == 200
    assert vitima.get('/api/admin/users').status_code == 200   # é admin

    # outro admin remove o vínculo do tenant padrão (sem derrubar a sessão)
    admin_c = TenantClient(iso_app.test_client(), HOST_A)
    assert _login(admin_c, HOST_A, 'admin@test.com').status_code == 200
    assert admin_c.delete(f'/api/auth/users/{uid}').status_code == 200

    # a MESMA sessão, na próxima requisição, não é mais admin
    r = vitima.get('/api/admin/users')
    assert r.status_code == 403

    with iso_app.app_context():
        db.session.delete(User.query.get(uid))
        db.session.commit()


# ── cache de papel invalidado após alteração (nota da Fable) ─────────────

def test_cache_de_papel_invalidado_apos_definir_papel_no_tenant(iso_app, seeded):
    """definir_papel_no_tenant muda o papel: uma leitura de role_no_tenant()
    depois, no MESMO request/contexto, não pode devolver o valor antigo."""
    from core.tenancy import (role_no_tenant, definir_papel_no_tenant, set_current_tenant,
                              Tenant)
    from models import User

    uid = seeded['users']['aluno']
    with iso_app.app_context():
        a = Tenant.query.filter_by(slug='ibc').first()
        with iso_app.test_request_context('/'):
            set_current_tenant(a)
            user = User.query.get(uid)
            assert role_no_tenant(user) == 'aluno'   # popula o cache em g
            definir_papel_no_tenant(uid, 'tutor')
            assert role_no_tenant(user) == 'tutor'   # não fica preso ao valor cacheado
        from extensions import db
        definir_papel_no_tenant(uid, 'aluno')
        db.session.commit()
