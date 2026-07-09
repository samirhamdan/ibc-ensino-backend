"""baseline do schema legado (pré-requisito da Fase 3)

Revision ID: 0002_legacy_baseline
Revises: 0001_ten01
Create Date: 2026-07-08

O schema legado nasceu de db.create_all() e nunca teve migração. Este
baseline cria as tabelas legadas que não existirem (checkfirst) a partir do
metadata dos models — em banco NOVO (CI) cria tudo; em produção (tabelas já
existentes) é um no-op que apenas registra o ponto de partida.

ATENÇÃO (runbook): o downgrade DERRUBA as tabelas legadas — existe para a
reversibilidade em ambientes descartáveis (CI). Em produção, o rollback da
Release 0.9 é `alembic downgrade 0002_legacy_baseline` (nunca abaixo disso);
voltar além do baseline é restauração de backup, não migração.
"""
from alembic import op

revision = '0002_legacy_baseline'
down_revision = '0001_ten01'
branch_labels = None
depends_on = None

# Tabelas de tenancy já são gerenciadas pela 0001
_TENANCY = {'tenants', 'tenant_users'}


def _legacy_tables():
    from extensions import db
    import models  # noqa: F401 — registra as tabelas legadas no metadata
    return [t for name, t in db.metadata.tables.items() if name not in _TENANCY]


def upgrade():
    from extensions import db
    db.metadata.create_all(bind=op.get_bind(), tables=_legacy_tables(),
                           checkfirst=True)


def downgrade():
    from extensions import db
    db.metadata.drop_all(bind=op.get_bind(), tables=_legacy_tables(),
                         checkfirst=True)
