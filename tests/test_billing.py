"""BIL-01 (PR 1 de 4): planos, modelos de billing/shared e migração 0015.

Testes de ESPECIFICAÇÃO (não de caracterização) — mesmo racional de
tests/test_tenancy.py.
"""
import os
import subprocess
import sys
import tempfile

import pytest
from sqlalchemy.exc import IntegrityError

from core.billing.plans import PLANOS, get_plan
from core.billing.models import Subscription, AiUsage
from shared.events import DomainEvent, publish_event
from shared.audit import AuditLog, registrar_auditoria
from core.tenancy import Tenant
from core.tenancy.context import default_tenant_id


# ── Planos ───────────────────────────────────────────────────────────────

def test_quatro_planos_existem():
    assert set(PLANOS) == {'semente', 'crescimento', 'comunidade', 'enterprise'}


def test_planos_pagos_tem_valores_sensatos():
    for chave in ('semente', 'crescimento', 'comunidade'):
        plano = PLANOS[chave]
        assert plano.limite_alunos and plano.limite_alunos > 0
        assert plano.cota_interacoes_ia_mes and plano.cota_interacoes_ia_mes > 0
        assert plano.preco_mensal_brl and plano.preco_mensal_brl > 0

    # Ordenação crescente de alunos/preço/cota entre os planos pagos
    semente, crescimento, comunidade = (PLANOS['semente'], PLANOS['crescimento'],
                                         PLANOS['comunidade'])
    assert semente.limite_alunos < crescimento.limite_alunos < comunidade.limite_alunos
    assert semente.preco_mensal_brl < crescimento.preco_mensal_brl < comunidade.preco_mensal_brl
    assert (semente.cota_interacoes_ia_mes < crescimento.cota_interacoes_ia_mes
            < comunidade.cota_interacoes_ia_mes)


def test_plano_enterprise_e_sob_consulta_ilimitado():
    ent = PLANOS['enterprise']
    assert ent.limite_alunos is None
    assert ent.cota_interacoes_ia_mes is None
    assert ent.preco_mensal_brl is None


def test_get_plan_case_insensitive():
    assert get_plan('SEMENTE') is PLANOS['semente']
    assert get_plan(' crescimento ') is PLANOS['crescimento']


def test_get_plan_nome_desconhecido_levanta_erro_claro():
    with pytest.raises(KeyError, match='Plano desconhecido'):
        get_plan('platina')


# ── Modelos (tenant_id obrigatório — TenantScopedModel) ────────────────────

def _novo_tenant(db, slug):
    t = Tenant(slug=slug, nome=slug, subdominio=slug)
    db.session.add(t)
    db.session.commit()
    return t


def test_subscription_tenant_id_nao_aceita_null_em_db(app):
    """A coluna é NOT NULL (nullable=False) no schema — a proteção real do
    mixin. Em Python, omitir tenant_id não levanta erro na hora: o
    `default=_tenant_default` do TenantScopedModel (core/tenancy/models.py)
    cai no tenant padrão (modo de compatibilidade mono-tenant documentado em
    core/tenancy/context.py) em vez de deixar a coluna nula — é assim que
    todo o código legado (que ainda não resolve tenant por request) continua
    funcionando. Este teste cobre as duas metades: (1) a coluna é NOT NULL no
    schema; (2) omitir tenant_id preenche com o tenant padrão, não None."""
    with app.app_context():
        from extensions import db
        tenant_col = Subscription.__table__.c.tenant_id
        assert tenant_col.nullable is False

        tenant = _novo_tenant(db, 'bil-sub')
        sub = Subscription(tenant_id=tenant.id, plano='semente')
        db.session.add(sub)
        db.session.commit()
        assert sub.id is not None
        assert sub.status == 'pending'
        assert sub.ciclo == 'mensal'

        sub_sem_tenant = Subscription(plano='crescimento')
        db.session.add(sub_sem_tenant)
        db.session.commit()
        assert sub_sem_tenant.tenant_id == default_tenant_id()
        db.session.delete(sub_sem_tenant)
        db.session.commit()


def test_subscription_unica_por_tenant(app):
    with app.app_context():
        from extensions import db
        tenant = _novo_tenant(db, 'bil-sub-unica')
        db.session.add(Subscription(tenant_id=tenant.id, plano='semente'))
        db.session.commit()

        db.session.add(Subscription(tenant_id=tenant.id, plano='crescimento'))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_ai_usage_tenant_id_not_null_e_unico_por_periodo(app):
    with app.app_context():
        from extensions import db
        assert AiUsage.__table__.c.tenant_id.nullable is False
        tenant = _novo_tenant(db, 'bil-ai-usage')

        uso = AiUsage(tenant_id=tenant.id, periodo='2026-07', interacoes=10)
        db.session.add(uso)
        db.session.commit()
        assert uso.id is not None

        # único por (tenant_id, periodo)
        db.session.add(AiUsage(tenant_id=tenant.id, periodo='2026-07'))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        # período diferente no mesmo tenant é permitido
        db.session.add(AiUsage(tenant_id=tenant.id, periodo='2026-08'))
        db.session.commit()


def test_domain_event_tenant_id_not_null_e_publish_event_helper(app):
    with app.app_context():
        from extensions import db
        assert DomainEvent.__table__.c.tenant_id.nullable is False
        tenant = _novo_tenant(db, 'bil-events')

        evento = publish_event(tenant.id, 'assinatura.criada', {'plano': 'semente'})
        db.session.commit()
        assert evento.id is not None
        assert evento.processado is False
        assert evento.payload_json == {'plano': 'semente'}
        assert evento.tenant_id == tenant.id


def test_audit_log_tenant_id_not_null_e_registrar_auditoria_helper(app):
    with app.app_context():
        from extensions import db
        assert AuditLog.__table__.c.tenant_id.nullable is False
        tenant = _novo_tenant(db, 'bil-audit')

        entrada = registrar_auditoria(tenant.id, user_id=1, acao='billing.plano_alterado',
                                       alvo='subscription:1', payload={'de': 'semente', 'para': 'crescimento'})
        db.session.commit()
        assert entrada.id is not None
        assert entrada.tenant_id == tenant.id


# ── tenants.billing_status ──────────────────────────────────────────────

def test_tenant_billing_status_default_ativo(app):
    with app.app_context():
        from extensions import db
        tenant = _novo_tenant(db, 'bil-status')
        assert tenant.billing_status == 'ativo'
        assert tenant.to_dict()['billing_status'] == 'ativo'


# ── Migração Alembic reversível (0015) ──────────────────────────────────

def test_migracao_0015_billing_reversivel():
    """upgrade → downgrade → upgrade em banco limpo, igual a
    test_migracao_0001_reversivel em tests/test_tenancy.py."""
    fd, path = tempfile.mkstemp(suffix='.db', prefix='alembic_test_billing_')
    os.close(fd)
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{path}'}
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        for cmd in (['upgrade', 'head'], ['downgrade', 'base'], ['upgrade', 'head']):
            r = subprocess.run([sys.executable, '-m', 'alembic'] + cmd,
                               capture_output=True, text=True, env=env, cwd=repo_root)
            assert r.returncode == 0, f'alembic {cmd}: {r.stderr}'

        import sqlite3
        con = sqlite3.connect(path)
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        cols = {row[1] for row in con.execute("PRAGMA table_info(tenants)")}
        con.close()
        assert {'domain_events', 'audit_log', 'subscriptions', 'ai_usage'} <= tables
        assert 'billing_status' in cols

        # downgrade -1 remove tudo de novo (ciclo completo)
        r = subprocess.run([sys.executable, '-m', 'alembic', 'downgrade', 'base'],
                           capture_output=True, text=True, env=env, cwd=repo_root)
        assert r.returncode == 0, r.stderr
        con = sqlite3.connect(path)
        tables_after = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        assert not ({'domain_events', 'audit_log', 'subscriptions', 'ai_usage'} & tables_after)
    finally:
        os.unlink(path)
