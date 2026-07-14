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
        }
