"""
TEN-01 (parcial): modelos de tenancy e mixin TenantScopedModel.

Nenhuma tabela existente é alterada nesta etapa (Fase 2, Etapa 2.1 do
playbook). As tabelas novas são gerenciadas por Alembic (migração 0001);
em testes/dev o db.create_all() também as cria, o que é inofensivo
(create_all pula tabelas existentes).
"""
import os
import time
import uuid
from datetime import datetime

from sqlalchemy.orm import declared_attr

from extensions import db


def uuid7():
    """UUID v7 (RFC 9562): 48 bits de timestamp ms + aleatório.
    Ordenável por tempo — evita o vazamento indireto de IDs sequenciais
    (doc 02 §5.5) sem perder localidade de índice. Python 3.12 não tem
    uuid.uuid7 nativo; implementação própria com teste de bits/ordenação."""
    ts_ms = time.time_ns() // 1_000_000
    raw = bytearray(ts_ms.to_bytes(6, 'big') + os.urandom(10))
    raw[6] = (raw[6] & 0x0F) | 0x70   # version = 7
    raw[8] = (raw[8] & 0x3F) | 0x80   # variant = RFC
    return uuid.UUID(bytes=bytes(raw))


class Tenant(db.Model):
    __tablename__ = 'tenants'

    id = db.Column(db.Uuid, primary_key=True, default=uuid7)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    nome = db.Column(db.String(200), nullable=False)
    subdominio = db.Column(db.String(63), unique=True, nullable=False)
    plano = db.Column(db.String(20), nullable=False, default='semente')
    # status: active | read_only | suspended (TEN-04) — status OPERACIONAL
    status = db.Column(db.String(20), nullable=False, default='active')
    # billing_status: ativo | leitura | suspenso (BIL-02) — separado de
    # `status`: reflete exclusivamente o estado de pagamento (webhooks Asaas),
    # enquanto `status` é o estado operacional definido pelo operador (TEN-04).
    billing_status = db.Column(db.String(20), nullable=False, default='ativo')
    tema_json = db.Column(db.JSON, default=dict)   # TEN-03: logo, cor, nome exibido
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': str(self.id),
            'slug': self.slug,
            'nome': self.nome,
            'subdominio': self.subdominio,
            'plano': self.plano,
            'status': self.status,
            'billing_status': self.billing_status,
            'tema': self.tema_json or {},
        }


class TenantUser(db.Model):
    """Papéis por tenant (AUTH-01): um usuário pode ter papéis diferentes em
    tenants diferentes. user_id referencia users.id SEM FK no banco por ora:
    a tabela users ainda é criada por db.create_all (fora do Alembic), e a
    migração 0001 precisa aplicar em banco vazio no CI. A FK entra na Fase 3,
    quando o schema legado for baselineado no Alembic."""
    __tablename__ = 'tenant_users'

    tenant_id = db.Column(db.Uuid, db.ForeignKey('tenants.id'), primary_key=True)
    user_id = db.Column(db.Integer, primary_key=True)
    # papel: aluno | instrutor | admin_tenant | operador_plataforma (AUTH-01)
    papel = db.Column(db.String(30), nullable=False, default='aluno')
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    tenant = db.relationship('Tenant', backref=db.backref('tenant_users', lazy=True,
                                                          cascade='all, delete-orphan'))

    __table_args__ = (db.Index('ix_tenant_users_user_id', 'user_id'),)


def _tenant_default():
    """Default de INSERT: escopa toda escrita ao tenant do request (ou ao
    tenant padrão no modo mono-tenant) sem exigir mudança nos call sites."""
    from core.tenancy.context import current_tenant_id
    return current_tenant_id()


class TenantScopedModel:
    """Mixin obrigatório para TODO model de domínio a partir da Release 0.9
    (regra 1 do doc 02 §3 / CLAUDE.md): tenant_id (com default do contexto,
    escopando escritas automaticamente) + índice composto (tenant_id, id).
    A política RLS correspondente entra na migração de cada tabela (Fase 4).

    LEITURAS continuam responsabilidade do chamador: toda query em tabela
    tenant-scoped filtra por current_tenant_id() (a suíte de isolamento cobra).

    Nota: subclasse que declarar __table_args__ próprio deve incluir o índice
    composto manualmente (declared_attr não é herdado nesse caso).
    """

    @declared_attr
    def tenant_id(cls):
        return db.Column(db.Uuid, db.ForeignKey('tenants.id'), nullable=False,
                         default=_tenant_default)

    @declared_attr
    def __table_args__(cls):
        return (db.Index(f'ix_{cls.__tablename__}_tenant_id_id', 'tenant_id', 'id'),)
