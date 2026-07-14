"""BIL-02 (PR 3 de 4): middleware de billing (core/billing/middleware.py).

Testes diretos de billing_status, sem passar pela régua — usam o override
`X-Tenant-Slug` (só ativo fora de produção, ver core/tenancy/middleware.py)
para simular tenant resolvido, e um tenant dedicado por teste para não
interferir na suíte de caracterização (que usa o tenant padrão).
"""
import pytest

from core.tenancy import Tenant


@pytest.fixture(scope='module')
def tenant_ativo(app):
    with app.app_context():
        from extensions import db
        t = Tenant(slug='mw-ativo', nome='mw-ativo', subdominio='mw-ativo', billing_status='ativo')
        db.session.add(t)
        db.session.commit()
        return t.slug


@pytest.fixture(scope='module')
def tenant_leitura(app):
    with app.app_context():
        from extensions import db
        t = Tenant(slug='mw-leitura', nome='mw-leitura', subdominio='mw-leitura', billing_status='leitura')
        db.session.add(t)
        db.session.commit()
        return t.slug


@pytest.fixture(scope='module')
def tenant_suspenso(app):
    with app.app_context():
        from extensions import db
        t = Tenant(slug='mw-suspenso', nome='mw-suspenso', subdominio='mw-suspenso', billing_status='suspenso')
        db.session.add(t)
        db.session.commit()
        return t.slug


def test_ativo_e_no_op(app, tenant_ativo):
    client = app.test_client()
    resp = client.post('/api/auth/login', json={'email': 'x@x.com', 'password': 'x'},
                        headers={'X-Tenant-Slug': tenant_ativo})
    assert resp.status_code != 402


def test_leitura_bloqueia_post_com_402(app, tenant_leitura):
    client = app.test_client()
    resp = client.post('/api/auth/login', json={'email': 'x@x.com', 'password': 'x'},
                        headers={'X-Tenant-Slug': tenant_leitura})
    assert resp.status_code == 402
    assert 'error' in resp.get_json()


def test_leitura_permite_get(app, tenant_leitura):
    client = app.test_client()
    resp = client.get('/api/theme', headers={'X-Tenant-Slug': tenant_leitura})
    assert resp.status_code != 402


def test_leitura_bloqueia_put_delete_patch(app, tenant_leitura):
    client = app.test_client()
    for metodo in ('put', 'delete', 'patch'):
        resp = getattr(client, metodo)('/api/auth/profile', headers={'X-Tenant-Slug': tenant_leitura})
        assert resp.status_code == 402, metodo


def test_suspenso_bloqueia_get_tambem(app, tenant_suspenso):
    client = app.test_client()
    resp = client.get('/api/auth/user', headers={'X-Tenant-Slug': tenant_suspenso})
    assert resp.status_code == 402


def test_suspenso_bloqueia_post(app, tenant_suspenso):
    client = app.test_client()
    resp = client.post('/api/auth/login', json={'email': 'x@x.com', 'password': 'x'},
                        headers={'X-Tenant-Slug': tenant_suspenso})
    assert resp.status_code == 402


def test_suspenso_excecoes_sempre_livres(app, tenant_suspenso):
    client = app.test_client()
    headers = {'X-Tenant-Slug': tenant_suspenso}
    assert client.get('/health', headers=headers).status_code != 402
    assert client.get('/api/theme', headers=headers).status_code != 402
    resp_webhook = client.post('/billing/webhook/asaas', json={'event': 'PAYMENT_CONFIRMED'},
                                headers={**headers, 'Asaas-Access-Token': 'token-invalido'})
    # 401 (token inválido) prova que chegou no handler do webhook, não 402.
    assert resp_webhook.status_code == 401


def test_webhook_nao_e_afetado_por_billing_status(app, tenant_suspenso):
    """O webhook não é acessado por subdomínio de tenant de qualquer forma
    (ver core/billing/routes.py) — sem X-Tenant-Slug, current_tenant() é
    None e o middleware cai no tenant padrão/efetivo; mesmo assim /billing/*
    está na lista de exceções e nunca é bloqueado por billing_status de
    NENHUM tenant."""
    client = app.test_client()
    resp = client.post('/billing/webhook/asaas', json={'event': 'PAYMENT_CONFIRMED'},
                        headers={'Asaas-Access-Token': 'token-invalido'})
    assert resp.status_code == 401   # chegou no handler, não foi bloqueado em 402
