"""Fase 1 de segurança: cabeçalhos, /health real, recuperação de senha sem SMTP,
limite de tentativas por conta."""
import pytest

from extensions import limiter


def test_cabecalhos_de_seguranca(client):
    r = client.get('/')
    csp = r.headers.get('Content-Security-Policy', '')
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'self'" in csp
    assert r.headers.get('X-Content-Type-Options') == 'nosniff'
    assert r.headers.get('X-Frame-Options') == 'SAMEORIGIN'


def test_health_consulta_o_banco(client):
    r = client.get('/health')
    assert r.status_code == 200
    assert r.get_json()['db'] == 'connected'


def test_esqueci_senha_sem_smtp_retorna_503(client, monkeypatch):
    monkeypatch.delenv('SMTP_USER', raising=False)
    monkeypatch.delenv('SMTP_PASS', raising=False)
    r = client.post('/api/auth/forgot-password', json={'email': 'x@y.com'})
    assert r.status_code == 503
    assert 'administrador' in r.get_json()['error']


@pytest.fixture
def limiter_ligado():
    limiter.enabled = True
    limiter.reset()
    yield
    limiter.reset()
    limiter.enabled = False


def test_login_limita_tentativas_por_conta(client, limiter_ligado):
    codigos = [
        client.post('/api/auth/login', json={'email': 'alvo@x.com', 'password': 'errada'}).status_code
        for _ in range(6)
    ]
    assert codigos[-1] == 429
    # outra conta não é afetada pelo limite por conta
    r = client.post('/api/auth/login', json={'email': 'outra@x.com', 'password': 'errada'})
    assert r.status_code != 429
