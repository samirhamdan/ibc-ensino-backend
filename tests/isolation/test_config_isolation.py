"""TEN-03: configuração (nome, contatos, pontuação), níveis e marca são por
tenant — o admin de A nunca altera o que B vê."""
import pytest

from tests.isolation.conftest import TenantClient, HOST_A, HOST_B
from tests.isolation.test_credenciais_globais import usuario_admin_em_ab  # noqa: F401


def _login(client, host):
    r = client.post('/api/auth/login', headers={'Host': host},
                    json={'email': 'admin@test.com', 'password': 'senha123'})
    assert r.status_code == 200


@pytest.fixture()
def admins(iso_app, usuario_admin_em_ab):  # noqa: F811
    a = TenantClient(iso_app.test_client(), HOST_A)
    b = TenantClient(iso_app.test_client(), HOST_B)
    _login(a, HOST_A)
    _login(b, HOST_B)
    return a, b


def test_config_e_niveis_por_tenant(admins):
    a, b = admins
    assert a.put('/api/admin/config', json={'platform_name': 'Escola A', 'whatsapp': '111'}).status_code == 200
    assert b.put('/api/admin/config', json={'platform_name': 'Escola B'}).status_code == 200

    assert a.get('/api/config/public').get_json()['platform_name'] == 'Escola A'
    pub_b = b.get('/api/config/public').get_json()
    assert pub_b['platform_name'] == 'Escola B'
    assert pub_b['whatsapp'] != '111'

    niveis_a = [{'number': 1, 'name': 'Semente A', 'min_points': 0},
                {'number': 2, 'name': 'Broto A', 'min_points': 100}]
    niveis_b = [{'number': 1, 'name': 'Início B', 'min_points': 0}]
    assert a.put('/api/admin/levels', json={'levels': niveis_a}).status_code == 200
    assert b.put('/api/admin/levels', json={'levels': niveis_b}).status_code == 200

    # salvar os níveis de B não apaga os de A
    assert [lv['name'] for lv in a.get('/api/admin/levels').get_json()] == ['Semente A', 'Broto A']
    assert [lv['name'] for lv in b.get('/api/admin/levels').get_json()] == ['Início B']
    assert [lv['name'] for lv in b.get('/api/config/gamification').get_json()['levels']] == ['Início B']


def test_marca_por_tenant(admins):
    a, b = admins
    from core.tenancy.cache import cache_clear
    cache_clear()
    try:
        r = a.put('/api/admin/branding', json={'nome_exibido': 'Escola A', 'primary': '#f0a500',
                                               'login_titulo': 'Bem-vindo à A'})
        assert r.status_code == 200

        ja = a.get('/api/theme.json').get_json()
        jb = b.get('/api/theme.json').get_json()
        assert ja['_meta']['nome_exibido'] == 'Escola A'
        assert ja['_meta']['login_titulo'] == 'Bem-vindo à A'
        assert jb['_meta']['nome_exibido'] != 'Escola A'
        assert jb['_meta']['login_titulo'] != 'Bem-vindo à A'
        assert ja['--brand-primary'] != jb['--brand-primary']
    finally:
        a.put('/api/admin/branding', json={'nome_exibido': '', 'primary': '', 'login_titulo': ''})
        cache_clear()
