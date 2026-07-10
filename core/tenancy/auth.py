"""
Etapa 4.2 (AUTH-03 parcial, doc 02 §6): papéis por tenant + vínculo da
sessão ao tenant.

Adaptação documentada: o app usa sessão de cookie (não JWT ainda — o JWT
com refresh rotativo entra com o módulo auth/ da Release 1.0). A REGRA DURA
do doc é a mesma: credencial emitida no tenant A não vale no tenant B
(403) — aqui aplicada à sessão, no middleware.

Papéis: a fonte passa a ser tenant_users.papel (AUTH-01: papéis diferentes
por tenant). Fallback para User.role cobre sessões/linhas antigas durante a
transição — a migração 0013 backfilla o tenant padrão.
"""
from flask import g

from extensions import db
from core.tenancy.context import current_tenant_id


def role_no_tenant(user):
    """Papel do usuário NO TENANT ATUAL (cacheado por request).

    tenant_users.papel quando existe; senão User.role (legado/transição).
    Vocabulário continua o legado (admin|tutor|aluno) — o mapeamento para os
    papéis do PRD (admin_tenant|instrutor|...) acontece na Release 1.0 junto
    com o frontend.
    """
    if user is None:
        return None
    cache = getattr(g, '_papel_cache', None)
    if cache is None:
        cache = g._papel_cache = {}
    key = user.id
    if key in cache:
        return cache[key]

    from core.tenancy.models import TenantUser
    tu = TenantUser.query.filter_by(tenant_id=current_tenant_id(),
                                    user_id=user.id).first()
    papel = tu.papel if tu else user.role
    cache[key] = papel
    return papel


def vincular_usuario_ao_tenant(user):
    """Garante o vínculo tenant_users no login (idempotente).

    Papel inicial: no tenant PADRÃO o usuário herda o papel global (paridade
    mono-tenant); em qualquer outro tenant entra como 'aluno' — privilégio em
    outro tenant é concessão explícita do admin daquele tenant, nunca herança.
    """
    from core.tenancy.models import TenantUser
    from core.tenancy.context import default_tenant_id
    tid = current_tenant_id()
    tu = TenantUser.query.filter_by(tenant_id=tid, user_id=user.id).first()
    if tu is None:
        papel = user.role if tid == default_tenant_id() else 'aluno'
        db.session.add(TenantUser(tenant_id=tid, user_id=user.id, papel=papel))
        db.session.commit()
