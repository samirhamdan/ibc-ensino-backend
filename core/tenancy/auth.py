"""
Etapa 4.2 (AUTH-03 parcial, doc 02 §6): papéis por tenant + vínculo da
sessão ao tenant.

Adaptação documentada: o app usa sessão de cookie (não JWT ainda — o JWT
com refresh rotativo entra com o módulo auth/ da Release 1.0). A REGRA DURA
do doc é a mesma: credencial emitida no tenant A não vale no tenant B
(403) — aqui aplicada à sessão, no middleware.

Papéis: a fonte é tenant_users.papel (AUTH-01: papéis diferentes por
tenant). O fallback para User.role só se aplica DENTRO do tenant padrão —
fora dele, ausência de vínculo é sempre 'aluno' (nunca herda privilégio
global). Ver correção de segurança no docstring de role_no_tenant.

users é GLOBAL por design (identidade única, e-mail único) — mas isso NUNCA
deve significar que um admin de um tenant lista, edita ou remove usuários
de outro tenant. Este módulo também fornece os helpers de escopo
(usuarios_do_tenant_query, get_user_scoped_or_404) que TODA rota de gestão
de usuário deve usar em vez de User.query direto.
"""
from flask import abort, g

from extensions import db
from core.tenancy.context import current_tenant_id


def role_no_tenant(user):
    """Papel do usuário NO TENANT ATUAL (cacheado por request).

    tenant_users.papel quando existe; na ausência de vínculo, SEMPRE 'aluno'
    — em QUALQUER tenant, inclusive o padrão. (Correção de segurança
    original: o fallback usava user.role em qualquer tenant, permitindo
    escalada de privilégio cruzada. Correção HIGH-2 de continuidade: o
    fallback para User.role no tenant padrão foi removido de vez — desde que
    login() passou a exigir um vínculo pré-existente e a migração 0013
    garante vínculo para todo usuário legado, aquele fallback só continuava
    ativo como um caminho residual: uma sessão de admin já aberta sobrevivia
    à remoção do vínculo do tenant padrão — DELETE /api/auth/users/<id> não
    revogava a sessão, e a próxima requisição, sem achar tenant_users,
    devolvia o papel global de novo. Sem vínculo explícito, o papel é sempre
    'aluno', ponto.)

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
    tid = current_tenant_id()
    tu = TenantUser.query.filter_by(tenant_id=tid, user_id=user.id).first()
    papel = tu.papel if tu is not None else 'aluno'
    cache[key] = papel
    return papel


def invalidar_cache_papel(user_id):
    """Limpa o cache de papel (por request, em g) de um usuário — chamar
    sempre depois de gravar/alterar tenant_users.papel, para que uma leitura
    de role_no_tenant() mais adiante no MESMO request não devolva o valor
    antigo (cache era só escrito por vínculo criado no login; escrita de
    papel por um admin no mesmo request não invalidava)."""
    cache = getattr(g, '_papel_cache', None)
    if cache is not None:
        cache.pop(user_id, None)


def vincular_usuario_ao_tenant(user, papel=None):
    """Cria o vínculo tenant_users no tenant atual (idempotente, seguro sob
    concorrência).

    IMPORTANTE (correção HIGH-2): esta função NUNCA deve ser chamada pelo
    fluxo de login — login apenas autentica e verifica um vínculo
    PRÉ-EXISTENTE (ver routes/auth.py::login). Vínculo se cria só por ação
    explícita: signup/convite (admin escolhe o papel), auto-cadastro
    (/register, dentro do tenant do subdomínio) ou um admin adicionando o
    usuário. Se login recriasse o vínculo automaticamente, remover um
    usuário do tenant (delete_user) não teria efeito nenhum: bastaria logar
    de novo para o vínculo voltar — e, no tenant padrão, um ex-admin
    recuperaria o papel global sozinho.

    Papel: se `papel` não for informado, o padrão é o mesmo de sempre — no
    tenant PADRÃO herda o papel global (paridade mono-tenant), em qualquer
    outro tenant entra como 'aluno'. Quando `papel` É informado (ex.: um
    admin criando um usuário via signup/convite), ele vale APENAS no tenant
    atual — nunca é escrito em User.role (global).

    Concorrência: duas chamadas simultâneas (ex.: convite + auto-cadastro)
    podem colidir no INSERT (unique tenant_id+user_id) — tratado com
    savepoint + rollback, sem propagar IntegrityError como 500.
    """
    from sqlalchemy.exc import IntegrityError
    from core.tenancy.models import TenantUser
    from core.tenancy.context import default_tenant_id

    tid = current_tenant_id()
    if TenantUser.query.filter_by(tenant_id=tid, user_id=user.id).first() is not None:
        return

    if papel is None:
        papel = user.role if tid == default_tenant_id() else 'aluno'

    try:
        with db.session.begin_nested():
            db.session.add(TenantUser(tenant_id=tid, user_id=user.id, papel=papel))
            db.session.flush()
    except IntegrityError:
        # Corrida: outro request já criou o vínculo (unique tenant_id+user_id).
        db.session.rollback()
        return
    db.session.commit()


def definir_papel_no_tenant(user_id, papel):
    """Concede/atualiza o papel de um usuário NO TENANT ATUAL (upsert em
    tenant_users). Usado pelas rotas de admin ao criar/editar usuário — o
    papel NUNCA é escrito em User.role (que ficaria visível/efetivo em
    todos os tenants do usuário)."""
    from core.tenancy.models import TenantUser
    tid = current_tenant_id()
    tu = TenantUser.query.filter_by(tenant_id=tid, user_id=user_id).first()
    if tu is None:
        db.session.add(TenantUser(tenant_id=tid, user_id=user_id, papel=papel))
    else:
        tu.papel = papel
    invalidar_cache_papel(user_id)


def tenant_user_ou_none(user_id):
    """Vínculo (TenantUser) do usuário no tenant atual, ou None — leitura
    pura, NUNCA cria. Usado pelo login para decidir 403 sem efeito colateral
    (correção HIGH-2: login não pode recriar tenant_users)."""
    from core.tenancy.models import TenantUser
    tid = current_tenant_id()
    return TenantUser.query.filter_by(tenant_id=tid, user_id=user_id).first()


def usuarios_do_tenant_query():
    """Query base de User restrita a quem tem vínculo no tenant atual —
    substitui User.query em TODA rota de listagem/gestão de usuários.
    (Sem isso, um admin de um tenant lista/gerencia usuários de todos os
    outros — o vazamento mais grave encontrado na revisão de segurança.)"""
    from core.tenancy.models import TenantUser
    from models import User
    return User.query.join(
        TenantUser,
        (TenantUser.user_id == User.id) & (TenantUser.tenant_id == current_tenant_id())
    )


def get_user_scoped_or_404(user_id):
    """Busca um User garantindo vínculo no tenant atual — 404 (nunca 403)
    se o usuário existe mas pertence a outro tenant, para não revelar
    existência (mesmo padrão de core.tenancy.context.get_scoped_or_404)."""
    from models import User
    user = usuarios_do_tenant_query().filter(User.id == user_id).first()
    if user is None:
        abort(404)
    return user
