"""
Eventos de domínio (outbox) — doc 02-ARQUITETURA.md §4 e §7.

`domain_events` é a tabela de outbox: produtores (courses, ai, billing, ...)
inserem uma linha via `publish_event`; workers RQ (fora de escopo desta PR —
entram na PR 2 do módulo de billing / futuros módulos) consomem as linhas
com `processado = False` e marcam como processadas. Esta PR só cria a tabela
e o helper de inserção — nenhum consumidor é implementado aqui.
"""
from datetime import datetime

from extensions import db
from core.tenancy.models import TenantScopedModel


class DomainEvent(TenantScopedModel, db.Model):
    """Linha de outbox (doc 02 §7): tipo do evento + payload livre em JSON.
    `processado` fica False até um worker consumir o evento."""
    __tablename__ = 'domain_events'

    id = db.Column(db.Integer, primary_key=True)
    # tipo: 'licao.publicada' | 'quiz.respondido' | 'tutor.interacao' | ... (doc 02 §7)
    tipo = db.Column(db.String(60), nullable=False)
    payload_json = db.Column(db.JSON, nullable=False, default=dict)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    processado = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        db.Index('ix_domain_events_tenant_id_id', 'tenant_id', 'id'),
        db.Index('ix_domain_events_tipo_processado', 'tipo', 'processado'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': str(self.tenant_id),
            'tipo': self.tipo,
            'payload': self.payload_json or {},
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
            'processado': self.processado,
        }


def publish_event(tenant_id, tipo, payload=None):
    """Insere um evento de domínio na outbox (não processa — isso é
    responsabilidade de um worker, fora de escopo desta PR). Não faz commit:
    o chamador decide o limite de transação (o evento deve entrar na mesma
    transação que a mudança de estado que o originou)."""
    evento = DomainEvent(
        tenant_id=tenant_id,
        tipo=tipo,
        payload_json=payload or {},
    )
    db.session.add(evento)
    return evento
