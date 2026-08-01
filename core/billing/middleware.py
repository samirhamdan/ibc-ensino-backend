"""
Middleware de billing — BIL-02 (PR 3 de 4), doc 02-ARQUITETURA.md §4.8.

Bloqueia requests com base em `Tenant.billing_status` (setado pelo webhook
do Asaas na PR 2 e pela régua de inadimplência na PR 3, core/billing/regua.py):

  - 'leitura'  -> bloqueia métodos mutantes (POST/PUT/DELETE/PATCH) com
                  402 Payment Required + JSON; GET passa.
  - 'suspenso' -> bloqueia TUDO (qualquer método), 402/página de suspensão.
  - 'ativo'    -> no-op, passa direto.

Registro (app.py): DEPOIS de `init_tenant_middleware` (precisa de
`current_tenant()`/`g.tenant` já resolvido) e ANTES dos blueprints de
conteúdo — mesmo racional posicional de `core/maintenance.py`, mas o
inverso: manutenção roda ANTES de tudo (nem tenant é resolvido), billing
roda DEPOIS da resolução de tenant (precisa saber QUAL tenant).

Estilo/rigor espelha core/maintenance.py: um único `before_request`,
exceções em um set fixo, distinção JSON vs HTML por path (mesmo helper
`_quer_json` de lá, mas verificando `/api/` OU `/billing/` — o webhook em
si sempre responde JSON).

Exceções (SEMPRE passam, qualquer billing_status — task spec):
  - /billing/* (webhook e futuras rotas de billing — um tenant suspenso
    ainda precisa poder RECEBER o webhook que pode reativá-lo: o Asaas
    confirmando um pagamento atrasado é exatamente o evento que tira o
    tenant de 'suspenso'. Bloquear aqui criaria um estado sem saída.)
  - /health (monitoração externa)
  - /api/theme (tema/branding do tenant — precisa carregar mesmo suspenso,
    é o que a página de suspensão usa pra não quebrar visualmente)

Nota sobre alcance real: o webhook do Asaas (`POST /billing/webhook/asaas`)
NÃO passa por `init_tenant_middleware` no sentido em que a maioria das
rotas passa — ele não é acessado por subdomínio de tenant (é um único
endpoint global, ver core/billing/routes.py). Ainda assim, TODO
before_request registrado roda pra TODA request, incluindo essa — por
isso o path precisa estar na lista de exceções aqui também (senão, se por
qualquer motivo g.tenant estiver resolvido nesse request — não deveria,
mas o middleware não pode depender disso — o webhook seria bloqueado).
"""
from flask import request, jsonify, Response

from core.tenancy.context import current_tenant, default_tenant_id
from core.tenancy.models import Tenant

_ROTAS_SEMPRE_LIVRES_PREFIXOS = ('/billing/', '/api/theme')
_ROTAS_SEMPRE_LIVRES_EXATAS = {'/health'}

_METODOS_MUTANTES = {'POST', 'PUT', 'DELETE', 'PATCH'}

_PAGINA_SUSPENSO = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Acesso suspenso</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #0a0f1e; color: #f1f5f9;
         text-align: center; padding: 4rem 1.5rem; }}
  h1 {{ font-size: 1.6rem; margin-bottom: .5rem; }}
  p {{ color: #94a3b8; max-width: 32rem; margin: .5rem auto; }}
</style>
</head>
<body>
<h1>Acesso suspenso</h1>
<p>O acesso desta organização à plataforma foi suspenso por inadimplência.
Entre em contato com o financeiro para regularizar o pagamento e
restabelecer o acesso.</p>
</body>
</html>"""


def _rota_livre():
    if request.path in _ROTAS_SEMPRE_LIVRES_EXATAS:
        return True
    return request.path.startswith(_ROTAS_SEMPRE_LIVRES_PREFIXOS)


def _quer_json():
    return request.path.startswith('/api/') or request.path.startswith('/billing/')


def _tenant_efetivo():
    """Tenant do request, com `billing_status` FRESCO do banco.

    Achado ao implementar: `current_tenant()` (TEN-02) devolve um
    `TenantContext` — um snapshot leve, CACHEADO por TTL (core/tenancy/
    middleware.py), sem o campo `billing_status` (esse cache existe só
    pra resolução de subdomínio, que muda raramente; billing_status muda
    por webhook/régua e precisa refletir no PRÓXIMO request, não só depois
    do cache expirar). Por isso este middleware sempre busca o `Tenant` ORM
    fresco por id — `tenants` não tem RLS (só tabelas de domínio), seguro
    buscar direto independente do GUC."""
    tenant_ctx = current_tenant()
    tenant_id = tenant_ctx.id if tenant_ctx is not None else default_tenant_id()
    return Tenant.query.get(tenant_id)


def init_billing_middleware(app):
    @app.before_request
    def bloquear_por_billing_status():
        if _rota_livre():
            return None

        tenant = _tenant_efetivo()
        if tenant is None:
            return None

        status = tenant.billing_status

        if status == 'suspenso':
            if _quer_json():
                return jsonify({'error': 'Acesso suspenso por inadimplência.'}), 402
            return Response(_PAGINA_SUSPENSO, status=402, mimetype='text/html')

        if status == 'leitura' and request.method in _METODOS_MUTANTES:
            return jsonify({
                'error': 'Pagamento em atraso: esta organização está em modo leitura. '
                         'Regularize o pagamento para voltar a criar/alterar dados.',
            }), 402

        return None
