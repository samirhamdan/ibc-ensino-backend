"""
Log de auditoria imutável por tenant — AUTH-04 / doc 02-ARQUITETURA.md §4.

Ações administrativas (criação de curso, alteração de matrícula, exportação,
mudanças de billing, ...) são registradas aqui. Nenhuma rota deve fazer
UPDATE/DELETE sobre linhas desta tabela (imutabilidade é responsabilidade da
aplicação nesta etapa; RLS/permissões de banco endurecem isso em fase
posterior, como as demais tabelas do doc 02 §5.3).
"""
from datetime import datetime

from extensions import db
from core.tenancy.models import TenantScopedModel


class AuditLog(TenantScopedModel, db.Model):
    __tablename__ = 'audit_log'

    id = db.Column(db.Integer, primary_key=True)
    # user_id referencia users.id SEM FK: users ainda está fora do Alembic
    # (mesmo racional de core/tenancy/models.py:TenantUser — baseline na Fase 3).
    user_id = db.Column(db.Integer, nullable=True)
    acao = db.Column(db.String(60), nullable=False)
    alvo = db.Column(db.String(120), nullable=True)
    payload_json = db.Column(db.JSON, nullable=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_audit_log_tenant_id_id', 'tenant_id', 'id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': str(self.tenant_id),
            'user_id': self.user_id,
            'acao': self.acao,
            'alvo': self.alvo,
            'payload': self.payload_json or {},
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
        }


def registrar_auditoria(tenant_id, user_id, acao, alvo=None, payload=None):
    """Insere uma linha de auditoria. Não faz commit (mesma convenção de
    publish_event): o chamador decide o limite de transação."""
    entrada = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        acao=acao,
        alvo=alvo,
        payload_json=payload,
    )
    db.session.add(entrada)
    return entrada
