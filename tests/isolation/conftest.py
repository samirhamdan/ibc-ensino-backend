"""Fixtures da suíte de isolamento: dois tenants (A=ibc, B=demo) e clientes
autenticados "dentro" de cada um via subdomínio."""
import os

import pytest

from core.tenancy import Tenant, clear_tenant_cache

BASE = 'xr.test'
HOST_A = f'ibc.{BASE}'
HOST_B = f'demo.{BASE}'


@pytest.fixture(scope='session')
def iso_app(app):
    """App com domínio-base ativo, tenants A e B criados. Reusa o banco da
    sessão (o fixture `app` de tests/conftest.py já apontou DATABASE_URL)."""
    from app import create_app
    anterior = os.environ.get('TENANT_BASE_DOMAIN')
    os.environ['TENANT_BASE_DOMAIN'] = BASE
    try:
        application = create_app('development')
        application.config['TESTING'] = True
        with application.app_context():
            from seed import seed_tenants
            seed_tenants()   # cria ibc e demo (idempotente)
        yield application
    finally:
        if anterior is None:
            os.environ.pop('TENANT_BASE_DOMAIN', None)
        else:
            os.environ['TENANT_BASE_DOMAIN'] = anterior


class TenantClient:
    """Cliente que faz TODA requisição a partir do host de um tenant —
    environ_base['HTTP_HOST'] é sobrescrito pelo EnvironBuilder do Werkzeug,
    então o Host vai por header em cada chamada."""

    def __init__(self, client, host):
        self._client = client
        self.host = host

    def _com_host(self, kw):
        headers = dict(kw.pop('headers', {}) or {})
        headers.setdefault('Host', self.host)
        kw['headers'] = headers
        return kw

    def get(self, path, **kw):
        return self._client.get(path, **self._com_host(kw))

    def post(self, path, **kw):
        return self._client.post(path, **self._com_host(kw))

    def put(self, path, **kw):
        return self._client.put(path, **self._com_host(kw))

    def delete(self, path, **kw):
        return self._client.delete(path, **self._com_host(kw))


@pytest.fixture()
def tenant_a(iso_app):
    clear_tenant_cache()
    return TenantClient(iso_app.test_client(), HOST_A)


@pytest.fixture()
def tenant_b(iso_app):
    clear_tenant_cache()
    return TenantClient(iso_app.test_client(), HOST_B)


@pytest.fixture()
def tenants_ab(iso_app):
    with iso_app.app_context():
        a = Tenant.query.filter_by(slug='ibc').first()
        b = Tenant.query.filter_by(slug='demo').first()
        return {'a_id': a.id, 'b_id': b.id}
