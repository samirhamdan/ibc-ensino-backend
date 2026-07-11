"""Casos de isolamento das tabelas de tenancy (Fase 2: tenants/tenant_users).

Padrão do framework (doc 02 §5.4): criar dados em A e B, operar "dentro" de A
e tentar alcançar recursos de B — por ID direto, listagem e contexto —
exigindo 404/403 e zero linhas. Na Fase 3, cada grupo de tabelas migradas
adiciona seus casos aqui seguindo este mesmo padrão.
"""
from core.tenancy import Tenant, TenantUser
from tests.isolation.conftest import HOST_A, BASE


# ── tenants: contexto por subdomínio ─────────────────────────────────────

def test_tenant_current_nao_vaza_outro_tenant(tenant_a, tenant_b):
    """Cada subdomínio só enxerga o próprio tenant — por construção, o
    contexto vem do host, nunca de parâmetro manipulável pelo cliente."""
    a = tenant_a.get('/api/tenant/current')
    b = tenant_b.get('/api/tenant/current')
    assert a.status_code == b.status_code == 200
    da, db_ = a.get_json(), b.get_json()
    assert da['slug'] == 'ibc' and db_['slug'] == 'demo'
    assert da['id'] != db_['id']
    # payload de A não contém NADA de B (zero linhas cruzadas)
    assert 'demo' not in str(da)


def test_contexto_nao_aceita_id_de_tenant_via_request(tenant_a, tenants_ab):
    """Tentativas de apontar para B a partir de A via query/header não têm
    efeito: o contexto é derivado exclusivamente do subdomínio."""
    bid = str(tenants_ab['b_id'])
    r = tenant_a.get(f'/api/tenant/current?tenant_id={bid}')
    assert r.get_json()['slug'] == 'ibc'
    # header X-Tenant-Slug até existe em dev, mas o middleware o processa
    # ANTES do host — quando presente, ele resolve, então o caso relevante
    # de produção (override desligado) é coberto em
    # tests/test_tenancy_middleware.py::test_header_override_ignorado_em_producao


def test_subdominio_de_tenant_inexistente_404(iso_app):
    from tests.isolation.conftest import TenantClient
    c = TenantClient(iso_app.test_client(), f'invasor.{BASE}')
    assert c.get('/api/tenant/current').status_code == 404
    assert c.get('/api/courses').status_code == 404


# ── tenant_users: papéis não vazam entre tenants ─────────────────────────

def test_tenant_users_zero_linhas_cruzadas(iso_app, tenants_ab, seeded):
    """Consulta escopada por tenant A retorna zero vínculos de B — o padrão
    de repositório que TODA tabela com tenant_id seguirá."""
    with iso_app.app_context():
        from extensions import db
        uid = seeded['users']['aluno']
        a_id, b_id = tenants_ab['a_id'], tenants_ab['b_id']

        TenantUser.query.filter_by(user_id=uid).delete()
        db.session.add(TenantUser(tenant_id=a_id, user_id=uid, papel='aluno'))
        db.session.add(TenantUser(tenant_id=b_id, user_id=uid, papel='admin_tenant'))
        db.session.commit()

        so_de_a = TenantUser.query.filter_by(tenant_id=a_id, user_id=uid).all()
        assert len(so_de_a) == 1
        assert all(tu.tenant_id == a_id for tu in so_de_a)

        # zero linhas de B numa consulta escopada em A
        vazadas = TenantUser.query.filter(TenantUser.tenant_id == a_id,
                                          TenantUser.papel == 'admin_tenant').count()
        assert vazadas == 0

        # Restaura o baseline do fixture `seeded` (vínculo 'aluno' no
        # tenant padrão) em vez de só apagar — outros testes dependem dele
        # via usuarios_do_tenant_query/get_user_scoped_or_404.
        TenantUser.query.filter_by(user_id=uid).delete()
        db.session.add(TenantUser(tenant_id=a_id, user_id=uid, papel='aluno'))
        db.session.commit()


def test_suspensao_de_b_nao_afeta_a(iso_app, tenant_a):
    """Suspender o tenant B não pode respingar no tenant A (TEN-04)."""
    from core.tenancy import clear_tenant_cache
    with iso_app.app_context():
        from extensions import db
        b = Tenant.query.filter_by(slug='demo').first()
        b.status = 'suspended'
        db.session.commit()
    clear_tenant_cache()
    try:
        assert tenant_a.get('/api/tenant/current').status_code == 200
        from tests.isolation.conftest import TenantClient
        c = TenantClient(iso_app.test_client(), f'demo.{BASE}')
        assert c.get('/api/tenant/current').status_code == 403
    finally:
        with iso_app.app_context():
            from extensions import db
            b = Tenant.query.filter_by(slug='demo').first()
            b.status = 'active'
            db.session.commit()
        clear_tenant_cache()
