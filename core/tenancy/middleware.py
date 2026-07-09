"""
TEN-02: resolução de tenant por subdomínio (Fase 2, Etapa 2.2).

- subdomínio válido sob TENANT_BASE_DOMAIN → tenant no contexto (g.tenant)
- subdomínio inexistente → 404 institucional (não revela a plataforma)
- tenant suspenso → 403 com página explicativa (TEN-04)
- host FORA do domínio-base (ibc-ensino.up.railway.app, localhost) → nenhuma
  resolução: as rotas legadas seguem exatamente como hoje. A migração do IBC
  para subdomínio é a Fase 6 do playbook.
- em desenvolvimento/teste, header X-Tenant-Slug funciona como override.

Cache em memória com TTL de 60s (dict — Redis entra na Fase 4). O TTL de 60s
também satisfaz o aceite de TEN-04: suspensão passa a valer em <60s sem
invalidação explícita.
"""
import os
import time
from dataclasses import dataclass, field

from flask import request, jsonify, g

from core.tenancy.context import set_current_tenant


CACHE_TTL_SECONDS = 60
_cache = {}   # subdominio -> (TenantContext|None, expira_em)


@dataclass
class TenantContext:
    """Snapshot leve do tenant para o contexto de request — não é objeto ORM
    (objetos ORM não podem viver num cache entre requests/sessões)."""
    id: object
    slug: str
    nome: str
    subdominio: str
    plano: str
    status: str
    tema: dict = field(default_factory=dict)

    def to_dict(self):
        return {'id': str(self.id), 'slug': self.slug, 'nome': self.nome,
                'subdominio': self.subdominio, 'plano': self.plano,
                'status': self.status, 'tema': self.tema or {}}


def clear_tenant_cache():
    """Invalidação manual (testes e, futuramente, painel do operador)."""
    _cache.clear()


def _to_context(tenant):
    if tenant is None:
        return None
    return TenantContext(id=tenant.id, slug=tenant.slug, nome=tenant.nome,
                         subdominio=tenant.subdominio, plano=tenant.plano,
                         status=tenant.status, tema=tenant.tema_json or {})


def _lookup_by(campo, valor):
    """Busca com cache TTL. Cacheia também o resultado negativo (None) —
    senão um subdomínio inexistente martelado vira query a cada request."""
    from core.tenancy.models import Tenant
    key = f'{campo}:{valor}'
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[1] > now:
        return hit[0]
    tenant = Tenant.query.filter_by(**{campo: valor}).first()
    ctx = _to_context(tenant)
    _cache[key] = (ctx, now + CACHE_TTL_SECONDS)
    return ctx


def _subdomain_from_host(host, base_domain):
    """'ibc.xreducacao.com.br' → 'ibc' (sob o domínio-base); None fora dele."""
    host = (host or '').split(':')[0].lower()
    if not base_domain or host == base_domain or not host.endswith('.' + base_domain):
        return None
    sub = host[: -(len(base_domain) + 1)]
    # subdomínio aninhado (a.b.base) não é um slug válido
    if not sub or '.' in sub:
        return None
    return sub


def _wants_json():
    return request.path.startswith('/api/')


def _resposta_404_institucional():
    if _wants_json():
        return jsonify({'error': 'Não encontrado'}), 404
    return ('<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<title>Página não encontrada</title></head><body '
            'style="font-family:sans-serif;text-align:center;padding:4rem">'
            '<h1>Página não encontrada</h1>'
            '<p>O endereço acessado não existe ou não está mais disponível.</p>'
            '</body></html>'), 404


def _resposta_403_suspenso(ctx):
    if _wants_json():
        return jsonify({'error': 'Conta suspensa. Entre em contato com o suporte.'}), 403
    return (f'<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<title>Conta suspensa</title></head><body '
            f'style="font-family:sans-serif;text-align:center;padding:4rem">'
            f'<h1>{ctx.nome}</h1>'
            f'<p>Esta conta está temporariamente suspensa.</p>'
            f'<p>Entre em contato com o administrador da plataforma.</p>'
            '</body></html>'), 403


def init_tenant_middleware(app, allow_header_override=False):
    """Registra o before_request de resolução. TENANT_BASE_DOMAIN pode vir do
    config do app (testes) ou do ambiente; sem ele, só o override por header
    resolve tenant (estado atual de produção — nada muda até o DNS da Fase 6)."""
    base_domain = (app.config.get('TENANT_BASE_DOMAIN')
                   or os.getenv('TENANT_BASE_DOMAIN') or '').lower() or None
    app.config['TENANT_BASE_DOMAIN'] = base_domain

    @app.before_request
    def resolve_tenant():   # noqa: F811 (nome descritivo no traceback)
        # 1) Override de desenvolvimento/teste por header
        if allow_header_override:
            slug = request.headers.get('X-Tenant-Slug')
            if slug:
                ctx = _lookup_by('slug', slug.strip().lower())
                if ctx is None:
                    return _resposta_404_institucional()
                if ctx.status == 'suspended':
                    return _resposta_403_suspenso(ctx)
                set_current_tenant(ctx)
                return None

        # 2) Resolução por subdomínio sob o domínio-base
        sub = _subdomain_from_host(request.host, base_domain)
        if sub is None:
            return None   # host fora do domínio-base: comportamento legado
        ctx = _lookup_by('subdominio', sub)
        if ctx is None:
            return _resposta_404_institucional()
        if ctx.status == 'suspended':
            return _resposta_403_suspenso(ctx)
        set_current_tenant(ctx)
        return None

    @app.route('/api/tenant/current', methods=['GET'])
    def tenant_current():
        """Tenant do request atual (para o frontend aplicar tema TEN-03).
        404 fora de contexto de tenant."""
        ctx = getattr(g, 'tenant', None)
        if ctx is None:
            return jsonify({'error': 'Nenhum tenant no contexto'}), 404
        return jsonify(ctx.to_dict()), 200
