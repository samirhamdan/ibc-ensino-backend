"""
Etapa 4.1 (doc 02 §5.3): SET LOCAL app.tenant_id na abertura de cada
transação — a segunda camada do isolamento (a primeira é o filtro de
aplicação; a terceira, os testes).

- SET LOCAL (escopo de TRANSAÇÃO) e nunca SET de sessão: conexões voltam ao
  pool sem vazar o tenant do request anterior (armadilha do playbook).
- Usa set_config(..., true) parametrizado — equivalente a SET LOCAL, sem
  interpolar string em SQL.
- PostgreSQL-only; em SQLite (dev) o listener é registrado mas não faz nada.
- Fail-closed: se nenhum tenant é resolvível, NADA é setado e as políticas
  RLS retornam zero linhas para a role de aplicação.
"""
from sqlalchemy import event, text
from sqlalchemy.orm import Session

_instalado = False


def _tenant_id_para_transacao(connection):
    """Resolve o tenant_id SEM passar pelo ORM (o listener roda dentro do
    ciclo da própria Session — usar ORM aqui recursionaria)."""
    from flask import g, has_app_context
    if not has_app_context():
        return None

    tenant = getattr(g, 'tenant', None)
    if tenant is not None:
        return tenant.id

    # modo mono-tenant: tenant padrão, com o mesmo cache do contexto
    from core.tenancy import context as ctx
    if ctx._default_tenant_id_cache is not None:
        return ctx._default_tenant_id_cache

    import os
    slug = os.getenv('DEFAULT_TENANT_SLUG', 'ibc')
    try:
        row = connection.execute(
            text('SELECT id FROM tenants WHERE slug = :slug'), {'slug': slug}
        ).fetchone()
    except Exception:
        return None   # tabela tenants ainda não existe (bootstrap/testes)
    if row is None:
        return None
    tid = row[0]
    ctx._default_tenant_id_cache = tid
    return tid


def init_rls():
    """Registra o listener global de Session (idempotente)."""
    global _instalado
    if _instalado:
        return
    _instalado = True

    @event.listens_for(Session, 'after_begin')
    def _set_tenant_guc(session, transaction, connection):
        if connection.dialect.name != 'postgresql':
            return
        tid = _tenant_id_para_transacao(connection)
        if tid is None:
            return   # fail-closed: RLS sem GUC → zero linhas
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {'tid': str(tid)})
