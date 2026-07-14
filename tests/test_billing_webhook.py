"""BIL-02 (PR 2 de 4): webhook POST /billing/webhook/asaas.

Cobre docs/DEBITOS.md #24 (resolução explícita de tenant, sem fallback pro
tenant padrão) e a idempotência exigida pela especificação da PR 2.
"""
import os

import pytest

os.environ.setdefault('ASAAS_WEBHOOK_TOKEN', 'token-de-teste-webhook-asaas')

from core.billing.models import Subscription, WebhookEvent
from core.tenancy import Tenant
from core.tenancy.context import default_tenant_id
from shared.events import DomainEvent
from shared.audit import AuditLog

TOKEN = 'token-de-teste-webhook-asaas'
HEADER = 'Asaas-Access-Token'


@pytest.fixture()
def billing_client(app):
    return app.test_client()


def _novo_tenant_com_subscription(db, slug, customer_id):
    tenant = Tenant(slug=slug, nome=slug, subdominio=slug)
    db.session.add(tenant)
    db.session.flush()
    sub = Subscription(tenant_id=tenant.id, plano='semente',
                        asaas_customer_id=customer_id, status='pending')
    db.session.add(sub)
    db.session.commit()
    return tenant, sub


def _payload(evento, customer_id, payment_id='pay_000001'):
    return {
        'event': evento,
        'payment': {
            'id': payment_id,
            'customer': customer_id,
            'value': 149.0,
        },
    }


def test_webhook_confirmado_atualiza_status_e_publica_um_evento(app, billing_client):
    with app.app_context():
        from extensions import db
        tenant, sub = _novo_tenant_com_subscription(db, 'wh-confirma', 'cus_confirma_1')

    resp = billing_client.post('/billing/webhook/asaas',
                                json=_payload('PAYMENT_CONFIRMED', 'cus_confirma_1', payment_id='pay_confirma_1'),
                                headers={HEADER: TOKEN})
    assert resp.status_code == 200

    with app.app_context():
        from extensions import db
        db.session.expire_all()
        sub_db = Subscription.query.filter_by(asaas_customer_id='cus_confirma_1').first()
        assert sub_db.status == 'active'
        tenant_db = Tenant.query.get(sub_db.tenant_id)
        assert tenant_db.billing_status == 'ativo'

        eventos = DomainEvent.query.filter_by(tenant_id=sub_db.tenant_id, tipo='pagamento.confirmado').all()
        assert len(eventos) == 1


def test_webhook_processado_duas_vezes_e_idempotente(app, billing_client):
    with app.app_context():
        from extensions import db
        tenant, sub = _novo_tenant_com_subscription(db, 'wh-idempotente', 'cus_idempotente_1')

    payload = _payload('PAYMENT_CONFIRMED', 'cus_idempotente_1', payment_id='pay_idem_1')

    r1 = billing_client.post('/billing/webhook/asaas', json=payload, headers={HEADER: TOKEN})
    r2 = billing_client.post('/billing/webhook/asaas', json=payload, headers={HEADER: TOKEN})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.get_json()['status'] == 'ja_processado'

    with app.app_context():
        from extensions import db
        db.session.expire_all()
        sub_db = Subscription.query.filter_by(asaas_customer_id='cus_idempotente_1').first()
        assert sub_db.status == 'active'

        eventos = DomainEvent.query.filter_by(tenant_id=sub_db.tenant_id, tipo='pagamento.confirmado').all()
        assert len(eventos) == 1   # não duplicou

        registros = WebhookEvent.query.filter_by(tenant_id=sub_db.tenant_id).all()
        assert len(registros) == 1


def test_webhook_sem_token_e_401_sem_efeito(app, billing_client):
    with app.app_context():
        from extensions import db
        tenant, sub = _novo_tenant_com_subscription(db, 'wh-sem-token', 'cus_sem_token_1')

    resp = billing_client.post('/billing/webhook/asaas',
                                json=_payload('PAYMENT_CONFIRMED', 'cus_sem_token_1', payment_id='pay_sem_token_1'))
    assert resp.status_code == 401

    with app.app_context():
        from extensions import db
        db.session.expire_all()
        sub_db = Subscription.query.filter_by(asaas_customer_id='cus_sem_token_1').first()
        assert sub_db.status == 'pending'
        assert DomainEvent.query.filter_by(tenant_id=sub_db.tenant_id).count() == 0
        assert WebhookEvent.query.filter_by(tenant_id=sub_db.tenant_id).count() == 0


def test_webhook_token_errado_e_401_sem_efeito(app, billing_client):
    with app.app_context():
        from extensions import db
        tenant, sub = _novo_tenant_com_subscription(db, 'wh-token-errado', 'cus_token_errado_1')

    resp = billing_client.post('/billing/webhook/asaas',
                                json=_payload('PAYMENT_CONFIRMED', 'cus_token_errado_1', payment_id='pay_token_errado_1'),
                                headers={HEADER: 'token-invalido'})
    assert resp.status_code == 401

    with app.app_context():
        sub_db = Subscription.query.filter_by(asaas_customer_id='cus_token_errado_1').first()
        assert sub_db.status == 'pending'


def test_webhook_customer_desconhecido_400_sem_fallback_para_tenant_padrao(app, billing_client):
    with app.app_context():
        from extensions import db
        contagem_domain_events_antes = DomainEvent.query.filter_by(tenant_id=default_tenant_id()).count()
        contagem_audit_antes = AuditLog.query.filter_by(tenant_id=default_tenant_id()).count()
        contagem_subs_antes = Subscription.query.filter_by(tenant_id=default_tenant_id()).count()

    resp = billing_client.post('/billing/webhook/asaas',
                                json=_payload('PAYMENT_CONFIRMED', 'cus_que_nao_existe_em_nenhum_tenant',
                                              payment_id='pay_desconhecido_1'),
                                headers={HEADER: TOKEN})
    assert resp.status_code == 400

    with app.app_context():
        # docs/DEBITOS.md #24: nenhuma escrita no tenant padrão (nem em
        # nenhum outro) quando o tenant não é resolvível.
        assert DomainEvent.query.filter_by(tenant_id=default_tenant_id()).count() == contagem_domain_events_antes
        assert AuditLog.query.filter_by(tenant_id=default_tenant_id()).count() == contagem_audit_antes
        assert Subscription.query.filter_by(tenant_id=default_tenant_id()).count() == contagem_subs_antes
        assert WebhookEvent.query.filter_by(event_id='PAYMENT_CONFIRMED:pay_desconhecido_1').count() == 0


def test_webhook_sem_payment_id_e_rejeitado_sem_gravar(app, billing_client):
    """Achado Medium da revisão Fable 5: payload sem payment.id não pode
    virar chave de idempotência degenerada ('EVENTO:', igual pra qualquer
    tenant/pagamento) — rejeita explicitamente em vez de processar sem
    proteção de idempotência real."""
    with app.app_context():
        from extensions import db
        tenant, _sub = _novo_tenant_com_subscription(db, 'sem-payment-id', 'cus_sem_payment_id_1')
        tenant_id = tenant.id

    payload = _payload('PAYMENT_CONFIRMED', 'cus_sem_payment_id_1')
    del payload['payment']['id']
    resp = billing_client.post('/billing/webhook/asaas', json=payload, headers={HEADER: TOKEN})
    assert resp.status_code == 400

    with app.app_context():
        assert Subscription.query.filter_by(tenant_id=tenant_id).first().status == 'pending'
        assert WebhookEvent.query.filter_by(tenant_id=tenant_id).count() == 0
        assert DomainEvent.query.filter_by(tenant_id=tenant_id).count() == 0


def test_webhook_isola_por_tenant(app, billing_client):
    """Webhook de um customer do tenant A nunca toca Subscription/billing_status
    do tenant B (mesma verificação de isolamento das outras suítes, aplicada
    ao mecanismo de resolução explícita deste endpoint)."""
    with app.app_context():
        from extensions import db
        tenant_a, sub_a = _novo_tenant_com_subscription(db, 'wh-isola-a', 'cus_isola_a')
        tenant_b, sub_b = _novo_tenant_com_subscription(db, 'wh-isola-b', 'cus_isola_b')
        tenant_a_id, tenant_b_id = tenant_a.id, tenant_b.id

    resp = billing_client.post('/billing/webhook/asaas',
                                json=_payload('PAYMENT_CONFIRMED', 'cus_isola_a', payment_id='pay_isola_a'),
                                headers={HEADER: TOKEN})
    assert resp.status_code == 200

    with app.app_context():
        from extensions import db
        db.session.expire_all()
        sub_a_db = Subscription.query.filter_by(asaas_customer_id='cus_isola_a').first()
        sub_b_db = Subscription.query.filter_by(asaas_customer_id='cus_isola_b').first()
        tenant_a_db = Tenant.query.get(tenant_a_id)
        tenant_b_db = Tenant.query.get(tenant_b_id)

        assert sub_a_db.status == 'active'
        assert tenant_a_db.billing_status == 'ativo'

        # tenant B intocado
        assert sub_b_db.status == 'pending'
        assert tenant_b_db.billing_status == 'ativo'  # default inalterado, não setado por este webhook
        assert DomainEvent.query.filter_by(tenant_id=tenant_b_id).count() == 0
        assert WebhookEvent.query.filter_by(tenant_id=tenant_b_id).count() == 0


def test_webhook_overdue_registra_sem_implementar_regua(app, billing_client):
    with app.app_context():
        from extensions import db
        tenant, sub = _novo_tenant_com_subscription(db, 'wh-overdue', 'cus_overdue_1')

    resp = billing_client.post('/billing/webhook/asaas',
                                json=_payload('PAYMENT_OVERDUE', 'cus_overdue_1', payment_id='pay_overdue_1'),
                                headers={HEADER: TOKEN})
    assert resp.status_code == 200

    with app.app_context():
        db_sub = Subscription.query.filter_by(asaas_customer_id='cus_overdue_1').first()
        assert db_sub.status == 'overdue'
        eventos = DomainEvent.query.filter_by(tenant_id=db_sub.tenant_id, tipo='pagamento.falhou').all()
        assert len(eventos) == 1
