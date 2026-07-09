"""
Contexto de tenant por request (TEN-01).

g.tenant é populado pelo middleware de subdomínio (TEN-02). Enquanto a
produção não vira subdomínio (Fase 6), current_tenant_id() cai no TENANT
PADRÃO (slug em DEFAULT_TENANT_SLUG, default 'ibc') — modo de
compatibilidade mono-tenant: todo dado novo é escopado ao IBC sem que as
rotas legadas precisem de contexto resolvido.
"""
import os

from flask import g, abort

_default_tenant_id_cache = None


def set_current_tenant(tenant):
    """Define o tenant do request atual (chamado pelo middleware)."""
    g.tenant = tenant


def current_tenant():
    """Tenant do request atual, ou None fora de contexto de tenant."""
    return getattr(g, 'tenant', None)


def require_tenant():
    """Retorna o tenant ativo do request ou aborta.

    - Sem tenant resolvido → 404 (página institucional na Etapa 2.2 — um
      subdomínio inexistente não deve revelar que a plataforma existe ali).
    - Tenant suspenso → 403 (TEN-04: suspensão bloqueia acesso com página
      explicativa; modo read_only é tratado por rota, não aqui).
    """
    tenant = current_tenant()
    if tenant is None:
        abort(404)
    if tenant.status == 'suspended':
        abort(403)
    return tenant


def current_tenant_id():
    """tenant_id efetivo do request: o tenant resolvido (subdomínio/override)
    ou, fora de contexto de tenant, o tenant padrão. É o valor usado para
    escopar TODA leitura/escrita das tabelas com tenant_id."""
    tenant = current_tenant()
    if tenant is not None:
        return tenant.id
    return default_tenant_id()


def default_tenant_id():
    """Id do tenant padrão (cacheado por processo). Falha alto se não existir:
    rodar com tabelas tenant-scoped sem o tenant padrão é erro de setup —
    rode `python seed.py` (dev) ou a migração 0004 (produção)."""
    global _default_tenant_id_cache
    if _default_tenant_id_cache is None:
        from core.tenancy.models import Tenant
        slug = os.getenv('DEFAULT_TENANT_SLUG', 'ibc')
        tenant = Tenant.query.filter_by(slug=slug).first()
        if tenant is None:
            raise RuntimeError(
                f"Tenant padrão '{slug}' não existe. Rode `python seed.py` "
                "(dev) ou `alembic upgrade head` (produção) antes de usar "
                "dados tenant-scoped.")
        _default_tenant_id_cache = tenant.id
    return _default_tenant_id_cache


def clear_default_tenant_cache():
    global _default_tenant_id_cache
    _default_tenant_id_cache = None
