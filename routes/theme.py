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


@theme_bp.route('/theme', methods=['GET'])
def get_theme():
    chave = f'theme:{current_tenant_id()}'

    cacheado = cache_get(chave)
    if cacheado is not None:
        return Response(cacheado['css'], mimetype='text/css')

    tema, nome = _tema_e_nome_do_tenant_atual()
    tokens = construir_tokens(tema, nome)
    css = tokens_para_css(tokens)
    cache_set(chave, {'css': css}, _TTL_SEGUNDOS)
    return Response(css, mimetype='text/css')


@theme_bp.route('/theme.json', methods=['GET'])
def get_theme_json():
    """Mesmos tokens em JSON — usado pelo painel admin (preview ao vivo,
    incluindo o aviso de cor ajustada por contraste) e por testes."""
    tema, nome = _tema_e_nome_do_tenant_atual()
    tokens = construir_tokens(tema, nome)
    return jsonify(tokens), 200
