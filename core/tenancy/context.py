"""
Contexto de tenant por request (TEN-01 parcial).

Nesta etapa (2.1) apenas a infraestrutura: g.tenant + require_tenant().
Quem POPULA o contexto é o middleware de resolução por subdomínio da
Etapa 2.2 (TEN-02) — nenhuma rota existente muda de comportamento ainda.
"""
from flask import g, abort


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
