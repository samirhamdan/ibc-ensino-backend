"""TEN-04 / UX_OPERADOR_SAAS §6: nenhum usuário de tenant — nem admin —
acessa qualquer rota do painel do operador."""
import uuid

from tests.isolation.conftest import TenantClient, HOST_A


def _rotas_ops(app):
    for regra in app.url_map.iter_rules():
        if regra.endpoint.startswith('ops.'):
            url = regra.rule.replace('<tenant_id>', str(uuid.uuid4()))
            for metodo in regra.methods - {'HEAD', 'OPTIONS'}:
                yield metodo, url


def test_admin_de_tenant_recebe_403_em_todas_as_rotas_ops(iso_app, seeded):
    c = TenantClient(iso_app.test_client(), HOST_A)
    r = c.post('/api/auth/login', json={'email': 'admin@test.com', 'password': 'senha123'})
    assert r.status_code == 200
    rotas = list(_rotas_ops(iso_app))
    assert len(rotas) >= 13
    for metodo, url in rotas:
        resp = getattr(c, metodo.lower())(url, json={})
        assert resp.status_code == 403, f'{metodo} {url} -> {resp.status_code}'


def test_anonimo_recebe_403_em_todas_as_rotas_ops(iso_app):
    c = TenantClient(iso_app.test_client(), HOST_A)
    for metodo, url in _rotas_ops(iso_app):
        resp = getattr(c, metodo.lower())(url, json={})
        assert resp.status_code == 403, f'{metodo} {url} -> {resp.status_code}'
