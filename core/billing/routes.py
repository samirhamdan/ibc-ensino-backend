"""
Webhook do Asaas — BIL-02 (doc 02-ARQUITETURA.md §7), PR 2 de 4.

Endpoint público (verificado por header, não por sessão/tenant de
subdomínio — ver PUBLIC_INFRA/registro de isolamento em
tests/isolation/registry.py). Roda FORA da resolução de tenant por
subdomínio (o Asaas chama um único endpoint, não `<slug>.dominio/...`), por
isso resolve o tenant explicitamente a partir do payload — nunca do
fallback de tenant padrão (docs/DEBITOS.md #24).
"""
import hmac
import logging
import os
import uuid as uuid_mod

from flask import Blueprint, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from extensions import db
from core.billing.models import Subscription, WebhookEvent
from core.tenancy import Tenant
from core.tenancy.context import set_current_tenant
from shared.events import publish_event

billing_bp = Blueprint('billing', __name__)

logger = logging.getLogger(__name__)

# Eventos Asaas tratados nesta PR (doc 02 §7: 'pagamento.confirmado/falhou').
# PAYMENT_OVERDUE/PAYMENT_DELETED só registram o evento — a régua real
# (D+10 leitura / D+30 suspensão) é a PR 3 (job separado que lê o estado
# gravado aqui, não este handler).
_EVENTO_ASAAS_PARA_STATUS = {
    'PAYMENT_CONFIRMED': 'active',
    'PAYMENT_RECEIVED': 'active',
    'PAYMENT_OVERDUE': 'overdue',
    'PAYMENT_DELETED': 'canceled',
}
_EVENTO_ASAAS_PARA_BILLING_STATUS = {
    'PAYMENT_CONFIRMED': 'ativo',
    'PAYMENT_RECEIVED': 'ativo',
    'PAYMENT_OVERDUE': 'leitura',
    'PAYMENT_DELETED': 'suspenso',
}
_EVENTO_ASAAS_PARA_DOMAIN_EVENT = {
    'PAYMENT_CONFIRMED': 'pagamento.confirmado',
    'PAYMENT_RECEIVED': 'pagamento.confirmado',
    'PAYMENT_OVERDUE': 'pagamento.falhou',
    'PAYMENT_DELETED': 'pagamento.falhou',
}


def _token_valido():
    """Compara o header `Asaas-Access-Token` contra ASAAS_WEBHOOK_TOKEN com
    `hmac.compare_digest` (tempo constante) — mesmo cuidado documentado em
    routes/auth.py::forgot_password contra side-channel de timing, aplicado
    aqui à validação do token do webhook em vez de enumeração de e-mail."""
    esperado = os.environ.get('ASAAS_WEBHOOK_TOKEN', '')
    recebido = request.headers.get('Asaas-Access-Token', '')
    if not esperado:
        # Sem token configurado no ambiente, NENHUM header "acerta" —
        # compare_digest com string vazia nunca é True para entrada não
        # vazia, mas deixamos explícito: não há como este handler aceitar
        # webhooks sem ASAAS_WEBHOOK_TOKEN configurada.
        return False
    return hmac.compare_digest(recebido, esperado)


def _resolver_tenant_id(payload):
    """Resolve o tenant a partir do `asaas_customer_id`/`asaas_subscription_id`
    do payload — NUNCA usa current_tenant_id()/default_tenant_id()
    (docs/DEBITOS.md #24). Retorna (subscription_id, tenant_id) ou
    (None, None) se não encontrar.

    Achado da revisão Fable 5 (Critical): esta busca precisa enxergar
    `subscriptions` de QUALQUER tenant (é assim que descobrimos qual é o
    tenant — o webhook não vem de um subdomínio) — mas `subscriptions` tem
    RLS (correção H1 da revisão da PR 1). A sessão ORM (`db.session`) só
    fixa o GUC `app.tenant_id` na abertura da transação a partir de
    `g.tenant`, que ainda não existe aqui (é o que estamos tentando
    descobrir) — sem isto, o listener de core/tenancy/rls.py cairia no
    modo mono-tenant (tenant PADRÃO) pra essa consulta, e webhooks de
    qualquer tenant que não seja o padrão nunca resolveriam, mesmo
    existindo a Subscription certa no banco (achado real, não hipotético:
    reproduzido lendo core/tenancy/rls.py::_tenant_id_para_transacao).

    Fix: consulta via conexão RAW (db.engine.connect(), fora do ciclo de
    vida da Session ORM) — o listener `after_begin` está registrado em
    `Session`, não em `Engine`/`Connection`, então esta consulta nunca
    passa pelo SET LOCAL de tenant. Em produção, isto só é seguro enquanto
    a app conectar com role SEM BYPASSRLS ainda não trocada (documentado
    em core/tenancy/rls.py — RLS é inócuo até a troca de role no Railway);
    quando essa troca acontecer, esta consulta específica vai precisar da
    role operador/admin (BYPASSRLS), o mesmo padrão que doc
    02-ARQUITETURA.md §5.3 já reserva pro "painel do operador" — registrado
    em docs/DEBITOS.md."""
    payment = payload.get('payment') or {}
    customer_id = payment.get('customer')
    subscription_id = payment.get('subscription')
    if not customer_id and not subscription_id:
        return None, None

    with db.engine.connect() as conn:
        row = None
        if customer_id:
            row = conn.execute(
                text('SELECT id, tenant_id FROM subscriptions WHERE asaas_customer_id = :cid'),
                {'cid': customer_id},
            ).first()
        if row is None and subscription_id:
            row = conn.execute(
                text('SELECT id, tenant_id FROM subscriptions WHERE asaas_subscription_id = :sid'),
                {'sid': subscription_id},
            ).first()

    if row is None:
        return None, None
    # A conexão raw devolve tenant_id como veio do driver (string no SQLite,
    # possivelmente já uuid.UUID ou string no Postgres dependendo do driver)
    # — normaliza pra uuid.UUID, que é o que o tipo da coluna (sa.Uuid) do
    # ORM espera ao usar este valor num Tenant.query.get()/filtro adiante.
    tenant_id = row[1] if isinstance(row[1], uuid_mod.UUID) else uuid_mod.UUID(str(row[1]))
    return row[0], tenant_id


def _event_id(evento, payload):
    """Chave de idempotência: evento + id do pagamento. Se o payload não
    trouxer id de pagamento, retorna None — chamador precisa tratar como
    "não deduplicável" (achado da revisão Fable 5, Medium: uma chave tipo
    "EVENTO:" sem id degeneraria pra uma única chave global, fazendo o
    PRIMEIRO evento desse tipo "consumir" a deduplicação de todos os
    seguintes, de qualquer tenant/pagamento, silenciosamente)."""
    payment = payload.get('payment') or {}
    payment_id = payment.get('id')
    if not payment_id:
        return None
    return f'{evento}:{payment_id}'


@billing_bp.route('/webhook/asaas', methods=['POST'])
def webhook_asaas():
    if not _token_valido():
        logger.warning('billing.webhook_asaas: token ausente/inválido')
        return jsonify({'error': 'Token inválido'}), 401

    payload = request.get_json(silent=True) or {}
    evento = payload.get('event')
    if not evento or evento not in _EVENTO_ASAAS_PARA_STATUS:
        # Evento desconhecido/não mapeado: aceita (200) sem processar, para
        # não fazer o Asaas re-tentar pra sempre um tipo de evento que este
        # handler ainda não trata — mas não escreve nada.
        logger.info('billing.webhook_asaas: evento não tratado: %r', evento)
        return jsonify({'status': 'ignorado', 'event': evento}), 200

    sub_id, tenant_id = _resolver_tenant_id(payload)
    if tenant_id is None:
        # Regra dura de docs/DEBITOS.md #24: falhar alto, nunca cair no
        # tenant padrão. Nenhuma linha é escrita.
        logger.error('billing.webhook_asaas: tenant não resolvido para payload (event=%r, '
                      'customer=%r, subscription=%r) — rejeitado, nenhum dado gravado',
                      evento, (payload.get('payment') or {}).get('customer'),
                      (payload.get('payment') or {}).get('subscription'))
        return jsonify({'error': 'Não foi possível resolver o tenant do webhook'}), 400

    # tenants NÃO tem RLS (só tabelas de domínio, ver 0012_rls.py) — seguro
    # buscar por id direto independente do GUC ainda não estar setado.
    tenant = Tenant.query.get(tenant_id)
    if tenant is None:
        logger.error('billing.webhook_asaas: tenant_id %r resolvido mas não existe mais', tenant_id)
        return jsonify({'error': 'Tenant não encontrado'}), 400

    # A partir daqui, toda consulta/escrita ORM (Subscription, WebhookEvent,
    # DomainEvent) precisa do GUC correto — set_current_tenant preenche
    # g.tenant, que core/tenancy/rls.py::_tenant_id_para_transacao lê na
    # abertura da próxima transação da Session (correção do Critical da
    # revisão Fable 5: antes disso, essas consultas caíam no tenant padrão).
    set_current_tenant(tenant)
    # A consulta acima (Tenant.query.get) já abriu uma transação na Session
    # ANTES de g.tenant existir — SET LOCAL é por transação, então o GUC já
    # ficou fixado (errado/ausente) pra essa transação e set_current_tenant
    # sozinho não a corrige retroativamente. db.session.rollback() aqui
    # fecha essa transação (era só leitura, nada a desfazer) pra que a
    # PRÓXIMA consulta (WebhookEvent, Subscription, ...) abra uma nova via
    # after_begin com g.tenant já correto.
    db.session.rollback()

    chave = _event_id(evento, payload)
    if chave is None:
        # payload sem id de pagamento: não dá pra deduplicar com segurança
        # (achado Medium da revisão — uma chave "EVENTO:" vazia dedupicaria
        # TODOS os eventos futuros desse tipo, de qualquer tenant). Rejeita
        # sem escrever nada, em vez de processar sem proteção de idempotência.
        logger.error('billing.webhook_asaas: payload sem payment.id (event=%r, tenant=%r) — '
                      'sem chave de idempotência confiável, rejeitado', evento, tenant_id)
        return jsonify({'error': 'Payload sem id de pagamento'}), 400

    # Idempotência: se já processamos esta chave, responde 200 sem repetir
    # a mudança de estado nem publicar o evento de novo.
    ja_processado = WebhookEvent.query.filter_by(event_id=chave).first()
    if ja_processado is not None:
        return jsonify({'status': 'ja_processado', 'event': evento}), 200

    sub = Subscription.query.get(sub_id)
    if sub is None:
        logger.error('billing.webhook_asaas: subscription %r resolvida mas não existe mais', sub_id)
        return jsonify({'error': 'Subscription não encontrada'}), 400

    novo_status = _EVENTO_ASAAS_PARA_STATUS[evento]
    novo_billing_status = _EVENTO_ASAAS_PARA_BILLING_STATUS[evento]
    tipo_evento_dominio = _EVENTO_ASAAS_PARA_DOMAIN_EVENT[evento]

    try:
        sub.status = novo_status
        tenant.billing_status = novo_billing_status

        db.session.add(WebhookEvent(tenant_id=tenant_id, event_id=chave, tipo=evento))
        publish_event(tenant_id, tipo_evento_dominio, payload)

        db.session.commit()
    except IntegrityError:
        # Corrida entre duas entregas concorrentes do MESMO webhook (achado
        # Medium da revisão): a outra já ganhou a unique constraint de
        # event_id — trata como "já processado", não como erro (o Asaas não
        # deve reagir a 500 tentando de novo pra sempre).
        db.session.rollback()
        logger.info('billing.webhook_asaas: corrida de idempotência em %r (event=%r) — '
                    'outra entrega já processou', chave, evento)
        return jsonify({'status': 'ja_processado', 'event': evento}), 200
    except Exception:
        db.session.rollback()
        logger.exception('billing.webhook_asaas: falha ao processar evento %r', evento)
        return jsonify({'error': 'Falha ao processar webhook'}), 500

    return jsonify({'status': 'processado', 'event': evento}), 200
