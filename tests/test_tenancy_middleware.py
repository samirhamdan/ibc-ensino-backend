"""TEN-02 (Etapa 2.2): middleware de resolução de tenant por subdomínio.

Critérios de aceite (PRD TEN-02/TEN-04): subdomínio válido resolve o tenant;
inexistente → 404 institucional; suspenso → 403; hosts fora do domínio-base
mantêm o comportamento legado; X-Tenant-Slug como override de dev.
"""
import pytest

from core.tenancy import Tenant, clear_tenant_cache

BASE = 'xr.test'


@pytest.fixture(scope='module')
def tenant_app(app):
    """App com domínio-base configurado e tenants ibc/demo/suspensa criados.
    Reusa o mesmo banco da sessão de teste (DATABASE_URL já aponta pra ele)."""
    import os
    from app import create_app
    os.environ['TENANT_BASE_DOMAIN'] = BASE
    try:
        application = create_app('development')
        application.config['TESTING'] = True
        with application.app_context():
            from extensions import db
            from seed import seed_tenants
            seed_tenants()
            if not Tenant.query.filter_by(slug='suspensa').first():
                db.session.add(Tenant(slug='suspensa', nome='Igreja Suspensa',
                                      subdominio='suspensa', status='suspended'))
                db.session.commit()
        yield application
    finally:
        del os.environ['TENANT_BASE_DOMAIN']


@pytest.fixture()
def tc(tenant_app):
    clear_tenant_cache()
    return tenant_app.test_client()


def _get(client, path, host, **kw):
    return client.get(path, headers={'Host': host}, **kw)


# ── Resolução por subdomínio ─────────────────────────────────────────────

def test_subdominio_valido_resolve_tenant(tc):
    r = _get(tc, '/api/tenant/current', f'ibc.{BASE}')
    assert r.status_code == 200
    body = r.get_json()
    assert body['slug'] == 'ibc'
    assert body['status'] == 'active'
    assert body['tema']['cor_primaria'] == '#008ea8'   # TEN-03


def test_subdominio_inexistente_404_institucional(tc):
    # rota de página: HTML institucional sem vazar stack/plataforma
    r = _get(tc, '/', f'nao-existe.{BASE}')
    assert r.status_code == 404
    assert b'o encontrada' in r.data      # "Página não encontrada"
    assert b'Traceback' not in r.data
    # rota de API: JSON 404
    r = _get(tc, '/api/courses', f'nao-existe.{BASE}')
    assert r.status_code == 404
    assert r.get_json()['error']


def test_tenant_suspenso_403_pagina_explicativa(tc):
    r = _get(tc, '/', f'suspensa.{BASE}')
    assert r.status_code == 403
    assert b'suspensa' in r.data
    r = _get(tc, '/api/courses', f'suspensa.{BASE}')
    assert r.status_code == 403


def test_host_base_sem_subdominio_sem_tenant(tc):
    """O domínio-base em si não é tenant (página institucional futura)."""
    assert _get(tc, '/health', BASE).status_code == 200
    assert _get(tc, '/api/tenant/current', BASE).status_code == 404


def test_host_fora_do_dominio_base_mantem_legado(tc):
    """Railway/localhost seguem funcionando sem tenant — paridade atual."""
    for host in ('localhost', 'ibc-ensino.up.railway.app'):
        assert _get(tc, '/health', host).status_code == 200
        assert _get(tc, '/api/tenant/current', host).status_code == 404


def test_subdominio_aninhado_nao_resolve(tc):
    r = _get(tc, '/api/tenant/current', f'a.ibc.{BASE}')
    assert r.status_code == 404


# ── Override de desenvolvimento ──────────────────────────────────────────

def test_header_override_em_dev(tc):
    r = tc.get('/api/tenant/current',
               headers={'Host': 'localhost', 'X-Tenant-Slug': 'demo'})
    assert r.status_code == 200
    assert r.get_json()['slug'] == 'demo'


def test_header_override_slug_inexistente_404(tc):
    r = tc.get('/api/tenant/current',
               headers={'Host': 'localhost', 'X-Tenant-Slug': 'fantasma'})
    assert r.status_code == 404


def test_header_override_ignorado_em_producao(app, monkeypatch, tmp_path):
    """Em produção o override não existe: header é ignorado."""
    import os
    from app import create_app
    monkeypatch.setenv('SECRET_KEY', 'prod-secret')
    monkeypatch.setenv('TENANT_BASE_DOMAIN', BASE)
    prod_app = create_app('production')
    prod_app.config['TESTING'] = True
    c = prod_app.test_client()
    r = c.get('/api/tenant/current',
              headers={'Host': 'localhost', 'X-Tenant-Slug': 'ibc'})
    assert r.status_code == 404   # header ignorado → sem tenant no contexto


# ── Cache TTL ────────────────────────────────────────────────────────────

def test_cache_segura_mudanca_ate_invalidar(tc, tenant_app):
    # popula o cache
    assert _get(tc, '/api/tenant/current', f'demo.{BASE}').status_code == 200

    # suspende o tenant direto no banco
    with tenant_app.app_context():
        from extensions import db
        t = Tenant.query.filter_by(slug='demo').first()
        t.status = 'suspended'
        db.session.commit()

    # dentro do TTL o cache ainda responde 'active' (janela de até 60s)
    assert _get(tc, '/api/tenant/current', f'demo.{BASE}').status_code == 200

    # invalidação explícita → passa a bloquear
    clear_tenant_cache()
    assert _get(tc, '/', f'demo.{BASE}').status_code == 403

    # restaura para os demais testes
    with tenant_app.app_context():
        from extensions import db
        t = Tenant.query.filter_by(slug='demo').first()
        t.status = 'active'
        db.session.commit()
    clear_tenant_cache()
