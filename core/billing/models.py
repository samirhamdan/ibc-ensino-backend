"""
Modelos de billing — BIL-01/02/03, doc 02-ARQUITETURA.md §4.

JUDGMENT CALL (uma assinatura por tenant): o PRD usa "planos" no singular
por tenant ("Planos Semente/Crescimento/.../Enterprise" — BIL-01 — e
`tenants.plano` em core/tenancy/models.py já é uma coluna única, não uma
lista). `Subscription.tenant_id` é UNIQUE: um tenant tem no máximo uma
assinatura ativa por vez (trocar de plano atualiza a linha existente, não
cria uma segunda). Add-ons de créditos de IA (BIL-03) não são modelados
nesta PR.

JUDGMENT CALL (formato de `periodo` em AiUsage): string `'YYYY-MM'` (ex.:
`'2026-07'`) em vez de `Date` truncado — é o formato natural para agrupar e
comparar períodos de fechamento mensal (BIL-03 "relatório mensal") sem
depender de convenção de "dia 1" e sem ambiguidade de fuso horário na
truncagem. `UniqueConstraint(tenant_id, periodo)` garante um agregado por
tenant por mês.
"""
from datetime import datetime

from extensions import db
from core.tenancy.models import TenantScopedModel

# PR 3 (BIL-02, régua de inadimplência): status 'overdue' por si só não diz
# HÁ QUANTOS DIAS a subscription está inadimplente — core/billing/regua.py
# precisa disso pros limiares D+10/D+30. `overdue_desde` (migração 0017) é
# setada pelo webhook (core/billing/routes.py) na transição PARA 'overdue' e
# limpa na transição de volta pra 'active'/'canceled' (pagamento resolvido —
# ver JUDGMENT CALL no webhook: não faz sentido a régua olhar uma data de
# inadimplência de um ciclo de cobrança já encerrado).

# status: pending | active | overdue | suspended | canceled (BIL-02: webhooks
# Asaas atualizam este campo; >10 dias inadimplente -> 'overdue' (leitura),
# >30 dias -> 'suspended', espelhando tenants.billing_status)
_STATUS_LEN = 20
_CICLO_LEN = 20


class Subscription(TenantScopedModel, db.Model):
    __tablename__ = 'subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    # plano: chave de core.billing.plans.PLANOS ('semente' | 'crescimento' | ...)
    plano = db.Column(db.String(20), nullable=False)
    asaas_customer_id = db.Column(db.String(60), nullable=True)
    asaas_subscription_id = db.Column(db.String(60), nullable=True)
    status = db.Column(db.String(_STATUS_LEN), nullable=False, default='pending')
    # ciclo de cobrança: 'mensal' | 'anual' (Asaas: MONTHLY/YEARLY)
    ciclo = db.Column(db.String(_CICLO_LEN), nullable=False, default='mensal')
    proximo_vencimento = db.Column(db.Date, nullable=True)
    # data em que o status virou 'overdue' pela última vez (None se nunca
    # esteve/não está mais overdue) — ver nota no topo do arquivo.
    overdue_desde = db.Column(db.Date, nullable=True)
    # PR 4 (BIL-03): override manual do operador (docs/OPS-BILLING.md
    # "pausar a régua para negociação") — enquanto True, core/billing/
    # regua.py::_candidatos_overdue ignora este tenant mesmo estando
    # 'overdue' há mais de D+10/D+30. NÃO altera billing_status/status por
    # si só (só impede a régua de agir); voltar a False não reaplica
    # retroativamente nenhuma transição perdida — a régua reavalia a partir
    # do estado ATUAL na próxima execução, mesma idempotência de sempre.
    regua_pausada = db.Column(db.Boolean, nullable=False, default=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                              onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('tenant_id', name='uq_subscriptions_tenant'),
        db.Index('ix_subscriptions_tenant_id_id', 'tenant_id', 'id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': str(self.tenant_id),
            'plano': self.plano,
            'status': self.status,
            'ciclo': self.ciclo,
            'proximo_vencimento': self.proximo_vencimento.isoformat() if self.proximo_vencimento else None,
            'overdue_desde': self.overdue_desde.isoformat() if self.overdue_desde else None,
            'regua_pausada': self.regua_pausada,
        }


class WebhookEvent(TenantScopedModel, db.Model):
    """Idempotência de webhooks Asaas (BIL-02, PR 2) — doc 02 §7.

    JUDGMENT CALL: o payload clássico de webhook do Asaas não traz um id de
    evento dedicado (não confundir com o id do pagamento, que se repete a
    cada notificação do MESMO pagamento em estados diferentes). A chave de
    idempotência usada é `f"{evento}:{payment_id}"` — reentrega do MESMO
    evento para o MESMO pagamento (retry do Asaas, replay manual) cai na
    mesma linha; evento diferente (ex.: CONFIRMED depois OVERDUE) para o
    mesmo pagamento é uma chave diferente, processado normalmente.
    `event_id` é UNIQUE globalmente (não por tenant): o id do pagamento no
    Asaas já é globalmente único, então a chave também é — não há por que
    permitir a mesma chave em tenants diferentes (seria, na prática,
    impossível: o pagamento pertence a um customer de um tenant só)."""
    __tablename__ = 'billing_webhook_events'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(160), nullable=False, unique=True)
    tipo = db.Column(db.String(60), nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_billing_webhook_events_tenant_id_id', 'tenant_id', 'id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': str(self.tenant_id),
            'event_id': self.event_id,
            'tipo': self.tipo,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
        }


class AiUsage(TenantScopedModel, db.Model):
    """Medição de consumo de IA por tenant (BIL-03). `periodo` é
    'YYYY-MM' — ver nota de JUDGMENT CALL no topo do arquivo."""
    __tablename__ = 'ai_usage'

    id = db.Column(db.Integer, primary_key=True)
    periodo = db.Column(db.String(7), nullable=False)  # 'YYYY-MM'
    interacoes = db.Column(db.Integer, nullable=False, default=0)
    tokens_entrada = db.Column(db.Integer, nullable=False, default=0)
    tokens_saida = db.Column(db.Integer, nullable=False, default=0)
    custo_estimado = db.Column(db.Numeric(10, 4), nullable=False, default=0)
    # PR 4 (BIL-03): já publicamos 'ai.cota_80pct' PARA ESTE período? Evita
    # reenviar o evento a cada interação subsequente enquanto o tenant segue
    # entre 80% e 100% da cota — ver core/billing/metering.py::checar_cota.
    # Por linha de `ai_usage` (1 por tenant+período): reseta sozinho a cada
    # novo mês, já que um período novo é uma linha nova (default False).
    alerta_80pct_enviado = db.Column(db.Boolean, nullable=False, default=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'periodo', name='uq_ai_usage_tenant_periodo'),
        db.Index('ix_ai_usage_tenant_id_id', 'tenant_id', 'id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': str(self.tenant_id),
            'periodo': self.periodo,
            'interacoes': self.interacoes,
            'tokens_entrada': self.tokens_entrada,
            'tokens_saida': self.tokens_saida,
            'custo_estimado': float(self.custo_estimado or 0),
            'alerta_80pct_enviado': self.alerta_80pct_enviado,
        }
