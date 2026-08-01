"""
Etapa 1 (GAM-04, doc UX_ALUNO_SAAS.md §2.2): tema derivado por tenant.

GET /api/theme devolve o bloco de CSS custom properties (identidade +
derivados) do tenant atual, cacheado por tenant (TTL 5 min, mesma cache de
core.tenancy.cache — chave já prefixada e namespace-safe). O SPA injeta a
resposta em <style id="tenant-theme"> no boot, antes do primeiro paint.
"""
from flask import Blueprint, Response, jsonify

from core.tenancy import current_tenant, current_tenant_id
from core.tenancy.cache import cache_get, cache_set
from core.theming import construir_tokens, tokens_para_css

theme_bp = Blueprint('theme', __name__)

_TTL_SEGUNDOS = 300


def _tema_e_nome_do_tenant_atual():
    """current_tenant() é None fora do domínio-base (produção pré-Fase 6,
    dev/CI sem TENANT_BASE_DOMAIN) — mesmo fallback de current_tenant_id():
    cai no tenant padrão, sem contexto de subdomínio resolvido."""
    ctx = current_tenant()
    if ctx is not None:
        return ctx.tema, ctx.nome
    from core.tenancy.models import Tenant
    tenant = Tenant.query.get(current_tenant_id())
    return tenant.tema_json, tenant.nome


def _tokens_do_tenant_atual():
    """Nunca deixa um tema_json malformado (cor fora do formato #RRGGBB —
    edição manual no banco, futuro editor de admin com bug) derrubar o
    boot inteiro da SPA com 500: cai no default da plataforma e segue.
    Diferente de um erro comum, aqui a falha é silenciosa de propósito —
    é literalmente melhor tema errado do que dashboard não carregar."""
    tema, nome = _tema_e_nome_do_tenant_atual()
    try:
        return construir_tokens(tema, nome)
    except ValueError:
        return construir_tokens(None, nome)


@theme_bp.route('/theme', methods=['GET'])
def get_theme():
    chave = f'theme:{current_tenant_id()}'

    cacheado = cache_get(chave)
    if cacheado is not None:
        return Response(cacheado['css'], mimetype='text/css')

    css = tokens_para_css(_tokens_do_tenant_atual())
    cache_set(chave, {'css': css}, _TTL_SEGUNDOS)
    return Response(css, mimetype='text/css')


@theme_bp.route('/theme.json', methods=['GET'])
def get_theme_json():
    """Mesmos tokens em JSON — usado pelo painel admin (preview ao vivo,
    incluindo o aviso de cor ajustada por contraste) e por testes."""
    return jsonify(_tokens_do_tenant_atual()), 200
