"""TOTP (RFC 6238) — compatível com Google Authenticator, Authy e similares."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

PASSO = 30
DIGITOS = 6


def gerar_segredo():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def _codigo(segredo, contador):
    chave = base64.b32decode(segredo + '=' * (-len(segredo) % 8), casefold=True)
    digest = hmac.new(chave, struct.pack('>Q', contador), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    valor = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(valor % 10 ** DIGITOS).zfill(DIGITOS)


def contador_atual(agora=None):
    return int((agora if agora is not None else time.time()) // PASSO)


def verificar(segredo, codigo, ultimo_contador_usado=None, agora=None):
    """Aceita o passo atual e ±1 (relógio do celular adiantado/atrasado).
    Devolve o contador usado (para impedir reuso do mesmo código) ou None."""
    codigo = (codigo or '').strip().replace(' ', '')
    if not segredo or len(codigo) != DIGITOS or not codigo.isdigit():
        return None
    atual = contador_atual(agora)
    for contador in (atual - 1, atual, atual + 1):
        if ultimo_contador_usado is not None and contador <= ultimo_contador_usado:
            continue
        if hmac.compare_digest(_codigo(segredo, contador), codigo):
            return contador
    return None


def uri_otpauth(segredo, conta, emissor='XR Educação'):
    rotulo = quote(f'{emissor}:{conta}')
    return f'otpauth://totp/{rotulo}?secret={segredo}&issuer={quote(emissor)}&digits={DIGITOS}&period={PASSO}'
