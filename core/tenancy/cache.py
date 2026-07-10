"""
Etapa 4.3: cache de tenant com Redis (fallback gracioso para memória).

Com REDIS_URL configurada, o cache do middleware de resolução passa a ser
compartilhado entre workers/réplicas (pré-requisito para as 2× réplicas do
doc 02 §8) e a invalidação vale para o processo todo. Sem REDIS_URL, o
comportamento é o atual (dict com TTL por processo) — dev e o deploy de
1 worker seguem idênticos.

Chaves sempre prefixadas por namespace (doc 02 §5.5: cache é vetor de
vazamento indireto entre tenants quando a chave não é qualificada).
"""
import json
import os
import time

_PREFIX = 'xr:tenant:'
_redis = None
_redis_tentado = False


def _get_redis():
    """Conexão Redis (lazy, cacheada). None quando não configurado/indisponível."""
    global _redis, _redis_tentado
    if _redis_tentado:
        return _redis
    _redis_tentado = True
    url = os.getenv('REDIS_URL')
    if not url:
        return None
    try:
        import redis
        cliente = redis.from_url(url, socket_connect_timeout=2,
                                 socket_timeout=2, decode_responses=True)
        cliente.ping()
        _redis = cliente
    except Exception as exc:   # indisponível → cai para memória, sem derrubar o app
        print(f'aviso: REDIS_URL configurada mas inacessível ({exc}); '
              'cache de tenant seguirá em memória.')
        _redis = None
    return _redis


def reset_redis_para_testes():
    global _redis, _redis_tentado
    _redis = None
    _redis_tentado = False


# ── API usada pelo middleware ────────────────────────────────────────────

_mem = {}   # fallback: chave -> (valor_json, expira_em)


def cache_get(chave):
    """Retorna o dict cacheado, a string '__negativo__' (miss cacheado) ou
    None (não está no cache)."""
    r = _get_redis()
    if r is not None:
        try:
            bruto = r.get(_PREFIX + chave)
            if bruto is None:
                return None
            return json.loads(bruto)
        except Exception:
            pass   # falha transitória de Redis → tenta memória
    hit = _mem.get(chave)
    if hit and hit[1] > time.monotonic():
        return hit[0]
    return None


def cache_set(chave, valor, ttl):
    r = _get_redis()
    if r is not None:
        try:
            r.setex(_PREFIX + chave, ttl, json.dumps(valor))
            return
        except Exception:
            pass
    _mem[chave] = (valor, time.monotonic() + ttl)


def cache_clear():
    """Invalidação total do namespace (testes e painel do operador)."""
    global _mem
    _mem = {}
    r = _get_redis()
    if r is not None:
        try:
            chaves = list(r.scan_iter(_PREFIX + '*'))
            if chaves:
                r.delete(*chaves)
        except Exception:
            pass
