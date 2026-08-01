"""Etapa 4.3: cache de tenant plugável (Redis com fallback para memória)."""
import time

import pytest

from core.tenancy import cache as tc


@pytest.fixture(autouse=True)
def _cache_limpo(monkeypatch):
    monkeypatch.delenv('REDIS_URL', raising=False)
    tc.reset_redis_para_testes()
    tc.cache_clear()
    yield
    tc.reset_redis_para_testes()
    tc.cache_clear()


def test_fallback_memoria_set_get_clear():
    assert tc.cache_get('slug:x') is None
    tc.cache_set('slug:x', {'id': '1', 'slug': 'x'}, ttl=60)
    assert tc.cache_get('slug:x')['slug'] == 'x'
    tc.cache_clear()
    assert tc.cache_get('slug:x') is None


def test_fallback_memoria_respeita_ttl(monkeypatch):
    tc.cache_set('slug:y', {'slug': 'y'}, ttl=60)
    # avança o relógio monotônico além do TTL
    agora = time.monotonic()
    monkeypatch.setattr(time, 'monotonic', lambda: agora + 61)
    assert tc.cache_get('slug:y') is None


def test_redis_indisponivel_nao_derruba_o_app(monkeypatch, capsys):
    """REDIS_URL apontando para lugar nenhum → aviso e fallback, sem exceção."""
    monkeypatch.setenv('REDIS_URL', 'redis://127.0.0.1:1/0')
    tc.reset_redis_para_testes()
    tc.cache_set('slug:z', {'slug': 'z'}, ttl=60)
    assert tc.cache_get('slug:z')['slug'] == 'z'   # veio da memória
    assert 'inacessível' in capsys.readouterr().out


def test_redis_real_quando_disponivel():
    """Com um Redis de verdade (CI futuro), o ciclo completo funciona."""
    import os
    if not os.getenv('TEST_REDIS_URL'):
        pytest.skip('sem TEST_REDIS_URL')
    import importlib
    os.environ['REDIS_URL'] = os.environ['TEST_REDIS_URL']
    tc.reset_redis_para_testes()
    tc.cache_set('slug:r', {'slug': 'r'}, ttl=5)
    assert tc.cache_get('slug:r')['slug'] == 'r'
    tc.cache_clear()
    assert tc.cache_get('slug:r') is None
