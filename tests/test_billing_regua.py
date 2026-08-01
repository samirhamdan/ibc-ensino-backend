"""BIL-02 (PR 3 de 4): régua de inadimplência (core/billing/regua.py).

D+10 -> billing_status='leitura', D+30 -> 'suspenso'. `hoje` é sempre
passado explicitamente (clock mockado) — nunca `date.today()` direto,
tornando os limiares testáveis com precisão de dia.
"""
import os
import subprocess
import sys
import tempfile
from datetime import date, timedelta

import pytest

from core.billing.models import Subscription
from core.billing.regua import executar_regua
from core.tenancy import Tenant, TenantUser
from shared.audit import AuditLog
from shared.events import DomainEvent

HOJE = date(2026, 7, 14)


def test_migracao_0017_overdue_desde_reversivel():
    """upgrade -> downgrade -> upgrade em banco limpo, mesmo padrão de
    test_billing.py::test_migracao_0015_billing_reversivel."""
    fd, path = tempfile.mkstemp(suffix='.db', prefix='alembic_test_billing_regua_')
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
        cols = {row[1] for row in con.execute("PRAGMA table_info(subscriptions)")}
        con.close()
        assert 'overdue_desde' in cols

        # Downgrade até a revisão IMEDIATAMENTE ANTERIOR a 0017 (não
        # `-1` relativo ao head atual — desde a PR 4, 0018 é o head, e
        # `-1` relativo pararia em 0017, que ainda TEM a coluna; o teste
        # é sobre a reversibilidade de 0017 especificamente).
        r = subprocess.run([sys.executable, '-m', 'alembic', 'downgrade',
                            '0016_billing_webhook_events'],
                           capture_output=True, text=True, env=env, cwd=repo_root)
        assert r.returncode == 0, r.stderr
        con = sqlite3.connect(path)
        cols_after = {row[1] for row in con.execute("PRAGMA table_info(subscriptions)")}
        con.close()
        assert 'overdue_desde' not in cols_after
    finally:
        os.unlink(path)


def _tenant_overdue(db, slug, dias_overdue, billing_status='ativo', com_admin=True):
    tenant = Tenant(slug=slug, nome=slug, subdominio=slug, billing_status=billing_status)
    db.session.add(tenant)
    db.session.flush()
    sub = Subscription(tenant_id=tenant.id, plano='semente', status='overdue',
                        overdue_desde=HOJE - timedelta(days=dias_overdue))
    db.session.add(sub)
    if com_admin:
        from models import User
        admin = User(name=f'Admin {slug}', email=f'admin-{slug}@example.com', role='admin')
        admin.set_password('senha123')
        db.session.add(admin)
        db.session.flush()
        db.session.add(TenantUser(tenant_id=tenant.id, user_id=admin.id, papel='admin_tenant'))
    db.session.commit()
    return tenant, sub


def test_d9_nao_transiciona(app):
    with app.app_context():
        from extensions import db
        tenant, sub = _tenant_overdue(db, 'regua-d9', dias_overdue=9)

        resumo = executar_regua(hoje=HOJE)

        db.session.expire_all()
        tenant_db = Tenant.query.get(tenant.id)
        assert tenant_db.billing_status == 'ativo'
        assert resumo['leitura'] == 0
        assert resumo['suspenso'] == 0


def test_d10_transiciona_para_leitura(app):
    with app.app_context():
        from extensions import db
        tenant, sub = _tenant_overdue(db, 'regua-d10', dias_overdue=10)

        resumo = executar_regua(hoje=HOJE)

        db.session.expire_all()
        tenant_db = Tenant.query.get(tenant.id)
        assert tenant_db.billing_status == 'leitura'
        assert resumo['leitura'] == 1

        auditorias = AuditLog.query.filter_by(tenant_id=tenant.id, acao='billing.leitura').all()
        assert len(auditorias) == 1

        eventos = DomainEvent.query.filter_by(tenant_id=tenant.id, tipo='billing.leitura').all()
        assert len(eventos) == 1


def test_d29_permanece_em_leitura(app):
    with app.app_context():
        from extensions import db
        tenant, sub = _tenant_overdue(db, 'regua-d29', dias_overdue=29, billing_status='leitura')

        resumo = executar_regua(hoje=HOJE)

        db.session.expire_all()
        tenant_db = Tenant.query.get(tenant.id)
        assert tenant_db.billing_status == 'leitura'
        assert resumo['suspenso'] == 0


def test_d30_transiciona_para_suspenso(app):
    with app.app_context():
        from extensions import db
        tenant, sub = _tenant_overdue(db, 'regua-d30', dias_overdue=30, billing_status='leitura')

        resumo = executar_regua(hoje=HOJE)

        db.session.expire_all()
        tenant_db = Tenant.query.get(tenant.id)
        assert tenant_db.billing_status == 'suspenso'
        assert resumo['suspenso'] == 1

        auditorias = AuditLog.query.filter_by(tenant_id=tenant.id, acao='billing.suspenso').all()
        assert len(auditorias) == 1


def test_tenant_que_pagou_antes_de_d10_e_ignorado(app):
    """Webhook (PR 2) já limpou overdue_desde e voltou status/billing_status
    ao normal — a régua não deve enxergar mais este tenant como candidato."""
    with app.app_context():
        from extensions import db
        tenant = Tenant(slug='regua-pagou', nome='regua-pagou', subdominio='regua-pagou',
                         billing_status='ativo')
        db.session.add(tenant)
        db.session.flush()
        sub = Subscription(tenant_id=tenant.id, plano='semente', status='active',
                            overdue_desde=None)
        db.session.add(sub)
        db.session.commit()

        resumo = executar_regua(hoje=HOJE)

        db.session.expire_all()
        tenant_db = Tenant.query.get(tenant.id)
        assert tenant_db.billing_status == 'ativo'
        # não usa `resumo['avaliados']` (a suíte inteira roda contra o mesmo
        # banco de sessão — outras subscriptions overdue de outros testes
        # deste arquivo continuam elegíveis à consulta bruta): a prova de
        # isolamento é este tenant especificamente não ter sido tocado.


def test_rodar_duas_vezes_no_mesmo_dia_nao_duplica(app):
    with app.app_context():
        from extensions import db
        tenant, sub = _tenant_overdue(db, 'regua-idempotente', dias_overdue=10)

        executar_regua(hoje=HOJE)
        executar_regua(hoje=HOJE)

        db.session.expire_all()
        tenant_db = Tenant.query.get(tenant.id)
        assert tenant_db.billing_status == 'leitura'

        auditorias = AuditLog.query.filter_by(tenant_id=tenant.id, acao='billing.leitura').all()
        assert len(auditorias) == 1

        eventos = DomainEvent.query.filter_by(tenant_id=tenant.id, tipo='billing.leitura').all()
        assert len(eventos) == 1


def test_webhook_ate_regua_fim_a_fim_sem_atalho(app):
    """Achado HIGH da revisão Fable 5 da PR 3: os outros testes desta
    suíte montam o estado direto no banco (_tenant_overdue) — não provam
    que o CAMINHO REAL (webhook do Asaas -> régua) de fato produz o
    estado que a régua espera. Este teste começa do zero e passa pelo
    handler de verdade: webhook PAYMENT_OVERDUE grava
    Subscription.status='overdue' + overdue_desde SEM tocar
    billing_status (permanece 'ativo' — a régua é quem decide o D+10, não
    o webhook); só então a régua, rodada com 'hoje' 10 dias à frente,
    transiciona pra 'leitura'."""
    import os
    os.environ.setdefault('ASAAS_WEBHOOK_TOKEN', 'token-de-teste-webhook-asaas')
    from core.tenancy.context import default_tenant_id
    from core.billing.models import Subscription as Sub

    client = app.test_client()
    with app.app_context():
        from extensions import db
        tenant = Tenant(slug='wh-ate-regua', nome='wh-ate-regua', subdominio='wh-ate-regua')
        db.session.add(tenant)
        db.session.flush()
        sub = Sub(tenant_id=tenant.id, plano='semente', asaas_customer_id='cus_wh_ate_regua_1',
                  status='active')
        db.session.add(sub)
        db.session.commit()
        tenant_id = tenant.id

    dia_vencimento = HOJE - timedelta(days=10)
    resp = client.post('/billing/webhook/asaas',
                        json={'event': 'PAYMENT_OVERDUE',
                              'payment': {'id': 'pay_wh_ate_regua_1', 'customer': 'cus_wh_ate_regua_1'}},
                        headers={'Asaas-Access-Token': os.environ['ASAAS_WEBHOOK_TOKEN']})
    assert resp.status_code == 200

    with app.app_context():
        from extensions import db
        # simula que o vencimento foi há 10 dias (o webhook grava a data
        # de HOJE de verdade — ajusta só pra exercitar o limiar sem
        # depender de rodar o teste 10 dias depois)
        sub_db = Sub.query.filter_by(asaas_customer_id='cus_wh_ate_regua_1').first()
        sub_db.overdue_desde = dia_vencimento
        db.session.commit()
        assert sub_db.status == 'overdue'
        assert Tenant.query.get(tenant_id).billing_status == 'ativo'   # webhook não adiantou

        executar_regua(hoje=HOJE)

        db.session.expire_all()
        assert Tenant.query.get(tenant_id).billing_status == 'leitura'


def test_isolamento_tenant_nao_relacionado_nao_e_afetado(app):
    with app.app_context():
        from extensions import db
        tenant_alvo, _ = _tenant_overdue(db, 'regua-isola-alvo', dias_overdue=10)
        tenant_ileso = Tenant(slug='regua-isola-ileso', nome='regua-isola-ileso',
                               subdominio='regua-isola-ileso', billing_status='ativo')
        db.session.add(tenant_ileso)
        db.session.flush()
        sub_ileso = Subscription(tenant_id=tenant_ileso.id, plano='semente', status='active')
        db.session.add(sub_ileso)
        db.session.commit()

        executar_regua(hoje=HOJE)

        db.session.expire_all()
        assert Tenant.query.get(tenant_alvo.id).billing_status == 'leitura'
        assert Tenant.query.get(tenant_ileso.id).billing_status == 'ativo'


def test_regua_e_middleware_fim_a_fim_via_tenant_padrao(app):
    """Cobre o middleware fim-a-fim usando o tenant PADRÃO dos testes de
    caracterização (nenhum TENANT_BASE_DOMAIN configurado neste app -> o
    middleware de billing resolve current_tenant() ou cai no tenant
    padrão, mesmo racional de current_tenant_id())."""
    from core.tenancy.context import default_tenant_id
    with app.app_context():
        from extensions import db
        tenant = Tenant.query.get(default_tenant_id())
        status_original = tenant.billing_status
        sub = Subscription.query.filter_by(tenant_id=tenant.id).first()
        criado_aqui = sub is None
        if sub is None:
            sub = Subscription(tenant_id=tenant.id, plano='semente', status='overdue',
                                overdue_desde=HOJE - timedelta(days=10))
            db.session.add(sub)
        else:
            sub.status = 'overdue'
            sub.overdue_desde = HOJE - timedelta(days=10)
        db.session.commit()

    client = app.test_client()
    try:
        with app.app_context():
            executar_regua(hoje=HOJE)

        with app.app_context():
            from extensions import db
            db.session.expire_all()
            assert Tenant.query.get(default_tenant_id()).billing_status == 'leitura'

        resp_get = client.get('/health')
        assert resp_get.status_code == 200   # exceção da lista, sempre livre

        resp_post = client.post('/api/auth/login', json={'email': 'x@x.com', 'password': 'x'})
        assert resp_post.status_code == 402

        # D+30: tudo bloqueado
        with app.app_context():
            from extensions import db
            sub_db = Subscription.query.filter_by(tenant_id=default_tenant_id()).first()
            sub_db.overdue_desde = HOJE - timedelta(days=30)
            db.session.commit()
        with app.app_context():
            executar_regua(hoje=HOJE)

        with app.app_context():
            from extensions import db
            db.session.expire_all()
            assert Tenant.query.get(default_tenant_id()).billing_status == 'suspenso'

        resp_get_bloqueado = client.get('/api/auth/user')
        assert resp_get_bloqueado.status_code == 402

        resp_theme_livre = client.get('/api/theme')
        assert resp_theme_livre.status_code != 402   # exceção da lista, mesmo suspenso

        resp_health_livre = client.get('/health')
        assert resp_health_livre.status_code != 402   # exceção da lista, mesmo suspenso

        resp_webhook_ainda_livre = client.post(
            '/billing/webhook/asaas', json={'event': 'PAYMENT_CONFIRMED'},
            headers={'Asaas-Access-Token': 'token-invalido'})
        # Chega ao handler (401 do token, não 402 do billing) — prova que a
        # exceção /billing/* passou pelo middleware de billing.
        assert resp_webhook_ainda_livre.status_code == 401
    finally:
        # Restaura estado para não vazar para outros testes da suíte
        # (fixture `app` é session-scoped).
        with app.app_context():
            from extensions import db
            tenant_db = Tenant.query.get(default_tenant_id())
            tenant_db.billing_status = status_original
            sub_db = Subscription.query.filter_by(tenant_id=default_tenant_id()).first()
            if criado_aqui:
                db.session.delete(sub_db)
            else:
                sub_db.status = 'active'
                sub_db.overdue_desde = None
            db.session.commit()
