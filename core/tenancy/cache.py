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
_redis_proxima_tentativa = 0.0
_REDIS_RETRY_COOLDOWN = 30  # segundos


def _get_redis():
    """Conexão Redis (lazy, cacheada). None quando não configurado.

    Se a conexão falhar, tenta de novo a cada _REDIS_RETRY_COOLDOWN segundos
    em vez de desistir para sempre — sem isso, um Redis que piscou uma vez
    no boot deixava aquele worker preso em memória permanentemente, e a
    invalidação via cache_clear() de outro worker nunca alcançava ele.
    """
    global _redis, _redis_proxima_tentativa
    if _redis is not None:
        return _redis
    url = os.getenv('REDIS_URL')
    if not url:
        return None
    agora = time.monotonic()
    if agora < _redis_proxima_tentativa:
        return None
    try:
        import redis
        cliente = redis.from_url(url, socket_connect_timeout=2,
                                 socket_timeout=2, decode_responses=True)
        cliente.ping()
        _redis = cliente
        return _redis
    except Exception as exc:   # indisponível → cai para memória, sem derrubar o app
        print(f'aviso: REDIS_URL configurada mas inacessível ({exc}); '
              f'cache de tenant seguirá em memória (nova tentativa em '
              f'{_REDIS_RETRY_COOLDOWN}s).')
        _redis_proxima_tentativa = agora + _REDIS_RETRY_COOLDOWN
        return None


def reset_redis_para_testes():
    global _redis, _redis_proxima_tentativa
    _redis = None
    _redis_proxima_tentativa = 0.0


# ── API usada pelo middleware ────────────────────────────────────────────

_mem = {}   # fallback: chave -> (valor, expira_em)
_MEM_MAX_ENTRIES = 5000


def cache_get(chave):
    """Retorna o valor cacheado (dict) ou None se ausente/expirado. Um
    resultado NEGATIVO cacheado (ex.: subdomínio inexistente) vem como o
    dict {'__negativo__': True} — quem chama decide o que fazer com isso."""
    r = _get_redis()
    if r is not None:
        try:
            bruto = r.get(_PREFIX + chave)
            return json.loads(bruto) if bruto is not None else None
        except Exception:
            pass   # falha transitória de Redis → tenta memória
    hit = _mem.get(chave)
    if hit is None:
        return None
    valor, expira_em = hit
    if expira_em <= time.monotonic():
        _mem.pop(chave, None)   # evicção na leitura — expirado não fica para sempre
        return None
    return valor


def cache_set(chave, valor, ttl):
    r = _get_redis()
    if r is not None:
        try:
            r.setex(_PREFIX + chave, ttl, json.dumps(valor))
            return
        except Exception:
            pass
    if len(_mem) >= _MEM_MAX_ENTRIES:
        _evict_memoria()
    _mem[chave] = (valor, time.monotonic() + ttl)


def _evict_memoria():
    """Teto de tamanho do fallback em memória (só relevante sem Redis): sem
    isto, martelar hosts inválidos — cada um cacheado como resultado
    negativo — infla _mem sem limite (DoS de memória por worker). Remove
    primeiro os expirados; se ainda acima do teto, remove os mais antigos."""
    agora = time.monotonic()
    expiradas = [k for k, (_, exp) in _mem.items() if exp <= agora]
    for k in expiradas:
        _mem.pop(k, None)
    if len(_mem) >= _MEM_MAX_ENTRIES:
        mais_antigas = sorted(_mem.items(), key=lambda kv: kv[1][1])[:max(1, len(_mem) // 4)]
        for k, _ in mais_antigas:
            _mem.pop(k, None)


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
