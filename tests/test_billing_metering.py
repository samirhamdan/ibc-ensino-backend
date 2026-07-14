"""BIL-03 (PR 4 de 4): medição de consumo de IA (core/billing/metering.py).

Stub — não chama nenhum provedor de IA de verdade, só registra/lê
`ai_usage`. `hoje` é sempre passado explicitamente (clock mockado), mesmo
padrão de `regua.py::executar_regua(hoje=None)`.
"""
import os
import subprocess
import sys
import tempfile
from datetime import date

from core.billing.metering import (
    checar_cota,
    consumo_do_tenant,
    registrar_interacao_ia,
)
from core.billing.models import AiUsage, Subscription
from core.billing.regua import pausar_regua, _candidatos_overdue
from core.tenancy import Tenant
from shared.events import DomainEvent

HOJE = date(2026, 7, 14)
PERIODO = '2026-07'
OUTRO_PERIODO_HOJE = date(2026, 8, 1)


def test_migracao_0018_colunas_reversivel():
    """upgrade -> downgrade -> upgrade em banco limpo, mesmo padrão de
    test_billing.py::test_migracao_0015_billing_reversivel."""
    fd, path = tempfile.mkstemp(suffix='.db', prefix='alembic_test_billing_metering_')
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
        cols_ai_usage = {row[1] for row in con.execute("PRAGMA table_info(ai_usage)")}
        cols_subs = {row[1] for row in con.execute("PRAGMA table_info(subscriptions)")}
        con.close()
        assert 'alerta_80pct_enviado' in cols_ai_usage
        assert 'regua_pausada' in cols_subs

        r = subprocess.run([sys.executable, '-m', 'alembic', 'downgrade', '-1'],
                           capture_output=True, text=True, env=env, cwd=repo_root)
        assert r.returncode == 0, r.stderr
        con = sqlite3.connect(path)
        cols_ai_usage_after = {row[1] for row in con.execute("PRAGMA table_info(ai_usage)")}
        cols_subs_after = {row[1] for row in con.execute("PRAGMA table_info(subscriptions)")}
        con.close()
        assert 'alerta_80pct_enviado' not in cols_ai_usage_after
        assert 'regua_pausada' not in cols_subs_after
    finally:
        os.unlink(path)


def _tenant(db, slug, plano='semente'):
    tenant = Tenant(slug=slug, nome=slug, subdominio=slug)
    db.session.add(tenant)
    db.session.flush()
    sub = Subscription(tenant_id=tenant.id, plano=plano, status='active')
    db.session.add(sub)
    db.session.commit()
    return tenant, sub


# ---------------------------------------------------------------------------
# registrar_interacao_ia
# ---------------------------------------------------------------------------

def test_registrar_cria_linha_nova(app):
    with app.app_context():
        from extensions import db
        tenant, _ = _tenant(db, 'met-cria')

        uso = registrar_interacao_ia(tenant.id, tokens_in=10, tokens_out=20,
                                      custo_estimado=0.05, hoje=HOJE)

        assert uso.periodo == PERIODO
        assert uso.interacoes == 1
        assert uso.tokens_entrada == 10
        assert uso.tokens_saida == 20
        assert float(uso.custo_estimado) == 0.05


def test_registrar_acumula_no_mesmo_periodo(app):
    with app.app_context():
        from extensions import db
        tenant, _ = _tenant(db, 'met-acumula')

        registrar_interacao_ia(tenant.id, tokens_in=10, tokens_out=5, custo_estimado=0.01, hoje=HOJE)
        registrar_interacao_ia(tenant.id, tokens_in=7, tokens_out=3, custo_estimado=0.02, hoje=HOJE)

        uso = AiUsage.query.filter_by(tenant_id=tenant.id, periodo=PERIODO).first()
        assert uso.interacoes == 2
        assert uso.tokens_entrada == 17
        assert uso.tokens_saida == 8
        assert round(float(uso.custo_estimado), 2) == 0.03


def test_registrar_periodo_diferente_cria_linha_separada(app):
    with app.app_context():
        from extensions import db
        tenant, _ = _tenant(db, 'met-periodo')

        registrar_interacao_ia(tenant.id, hoje=HOJE)
        registrar_interacao_ia(tenant.id, hoje=OUTRO_PERIODO_HOJE)

        linhas = AiUsage.query.filter_by(tenant_id=tenant.id).all()
        periodos = {linha.periodo for linha in linhas}
        assert periodos == {'2026-07', '2026-08'}
        for linha in linhas:
            assert linha.interacoes == 1


def test_isolamento_entre_tenants(app):
    with app.app_context():
        from extensions import db
        tenant_a, _ = _tenant(db, 'met-iso-a')
        tenant_b, _ = _tenant(db, 'met-iso-b')

        registrar_interacao_ia(tenant_a.id, tokens_in=100, hoje=HOJE)

        uso_a = AiUsage.query.filter_by(tenant_id=tenant_a.id, periodo=PERIODO).first()
        uso_b = AiUsage.query.filter_by(tenant_id=tenant_b.id, periodo=PERIODO).first()
        assert uso_a.interacoes == 1
        assert uso_b is None


# ---------------------------------------------------------------------------
# consumo_do_tenant
# ---------------------------------------------------------------------------

def test_consumo_zero_sem_uso(app):
    with app.app_context():
        from extensions import db
        tenant, _ = _tenant(db, 'met-cons-zero')
        assert consumo_do_tenant(tenant.id, hoje=HOJE) == 0.0


def test_consumo_fracao_parcial(app):
    with app.app_context():
        from extensions import db
        tenant, _ = _tenant(db, 'met-cons-frac', plano='semente')  # cota=500
        for _ in range(50):
            registrar_interacao_ia(tenant.id, hoje=HOJE)

        assert abs(consumo_do_tenant(tenant.id, hoje=HOJE) - 0.1) < 1e-9


def test_consumo_enterprise_sempre_zero(app):
    with app.app_context():
        from extensions import db
        tenant, _ = _tenant(db, 'met-cons-ent', plano='enterprise')
        for _ in range(1000):
            registrar_interacao_ia(tenant.id, hoje=HOJE)

        assert consumo_do_tenant(tenant.id, hoje=HOJE) == 0.0


def test_consumo_usa_plano_da_subscription_nao_do_tenant(app):
    """Subscription.plano é autoritativo (docs/DEBITOS.md #27) — mesmo se
    Tenant.plano divergir (default 'semente' nunca atualizado)."""
    with app.app_context():
        from extensions import db
        tenant = Tenant(slug='met-cons-div', nome='met-cons-div', subdominio='met-cons-div',
                         plano='semente')  # Tenant.plano != Subscription.plano
        db.session.add(tenant)
        db.session.flush()
        sub = Subscription(tenant_id=tenant.id, plano='crescimento', status='active')  # cota=3000
        db.session.add(sub)
        db.session.commit()

        for _ in range(300):
            registrar_interacao_ia(tenant.id, hoje=HOJE)

        # Se caísse em Tenant.plano ('semente', cota=500) daria 0.6, não 0.1
        assert abs(consumo_do_tenant(tenant.id, hoje=HOJE) - 0.1) < 1e-9


# ---------------------------------------------------------------------------
# checar_cota
# ---------------------------------------------------------------------------

def test_checar_cota_dentro_da_cota(app):
    with app.app_context():
        from extensions import db
        tenant, _ = _tenant(db, 'met-cota-ok', plano='semente')
        for _ in range(10):
            registrar_interacao_ia(tenant.id, hoje=HOJE)

        assert checar_cota(tenant.id, hoje=HOJE) is True
        assert DomainEvent.query.filter_by(tenant_id=tenant.id, tipo='ai.cota_80pct').count() == 0


def test_checar_cota_acima_da_cota(app):
    with app.app_context():
        from extensions import db
        tenant, _ = _tenant(db, 'met-cota-over', plano='semente')  # cota=500
        for _ in range(600):
            registrar_interacao_ia(tenant.id, hoje=HOJE)

        assert checar_cota(tenant.id, hoje=HOJE) is False


def test_checar_cota_publica_evento_uma_unica_vez_ao_cruzar_80pct(app):
    with app.app_context():
        from extensions import db
        tenant, _ = _tenant(db, 'met-cota-80', plano='semente')  # cota=500

        # 79% - ainda não cruzou
        for _ in range(395):
            registrar_interacao_ia(tenant.id, hoje=HOJE)
        checar_cota(tenant.id, hoje=HOJE)
        assert DomainEvent.query.filter_by(tenant_id=tenant.id, tipo='ai.cota_80pct').count() == 0

        # cruza 80% (401/500 = 80.2%)
        for _ in range(6):
            registrar_interacao_ia(tenant.id, hoje=HOJE)
        checar_cota(tenant.id, hoje=HOJE)
        assert DomainEvent.query.filter_by(tenant_id=tenant.id, tipo='ai.cota_80pct').count() == 1

        # chamadas subsequentes ainda entre 80-100% não republicam
        for _ in range(50):
            registrar_interacao_ia(tenant.id, hoje=HOJE)
            checar_cota(tenant.id, hoje=HOJE)
        assert DomainEvent.query.filter_by(tenant_id=tenant.id, tipo='ai.cota_80pct').count() == 1

        uso = AiUsage.query.filter_by(tenant_id=tenant.id, periodo=PERIODO).first()
        assert uso.alerta_80pct_enviado is True


def test_checar_cota_novo_periodo_dispara_evento_de_novo(app):
    with app.app_context():
        from extensions import db
        tenant, _ = _tenant(db, 'met-cota-novo-periodo', plano='semente')  # cota=500

        for _ in range(450):
            registrar_interacao_ia(tenant.id, hoje=HOJE)
        checar_cota(tenant.id, hoje=HOJE)
        assert DomainEvent.query.filter_by(tenant_id=tenant.id, tipo='ai.cota_80pct').count() == 1

        for _ in range(450):
            registrar_interacao_ia(tenant.id, hoje=OUTRO_PERIODO_HOJE)
        checar_cota(tenant.id, hoje=OUTRO_PERIODO_HOJE)
        assert DomainEvent.query.filter_by(tenant_id=tenant.id, tipo='ai.cota_80pct').count() == 2


# ---------------------------------------------------------------------------
# regua_pausada (override do operador, ver docs/OPS-BILLING.md)
# ---------------------------------------------------------------------------

def test_pausar_regua_exclui_tenant_dos_candidatos(app):
    with app.app_context():
        from extensions import db
        from datetime import timedelta
        tenant = Tenant(slug='met-pausa', nome='met-pausa', subdominio='met-pausa',
                         billing_status='ativo')
        db.session.add(tenant)
        db.session.flush()
        sub = Subscription(tenant_id=tenant.id, plano='semente', status='overdue',
                            overdue_desde=HOJE - timedelta(days=15))
        db.session.add(sub)
        db.session.commit()

        alvo = str(tenant.id).replace('-', '')

        candidatos_antes = {str(row[1]).replace('-', '') for row in _candidatos_overdue()}
        assert alvo in candidatos_antes

        pausar_regua(tenant.id, pausar=True)
        candidatos_pausado = {str(row[1]).replace('-', '') for row in _candidatos_overdue()}
        assert alvo not in candidatos_pausado

        pausar_regua(tenant.id, pausar=False)
        candidatos_retomado = {str(row[1]).replace('-', '') for row in _candidatos_overdue()}
        assert alvo in candidatos_retomado

        # Deixa pausado de novo ao final: o `app` é session-scoped (mesmo
        # banco entre arquivos de teste) — sem isto, este tenant overdue
        # ficaria "vazando" como candidato real pra executar_regua() nos
        # testes de tests/test_billing_regua.py, inflando as contagens de
        # resumo['leitura']/['suspenso'] deles.
        pausar_regua(tenant.id, pausar=True)


def test_registrar_concorrente_nao_perde_incremento(app):
    """Achado Medium da revisão Fable 5: a versão anterior fazia
    leitura-modificação-escrita em Python — duas chamadas concorrentes do
    MESMO tenant/período podiam perder incremento (undercounta billing).
    Prova real com threads: N chamadas concorrentes têm que resultar em
    exatamente N interações contadas, nunca menos."""
    import threading

    with app.app_context():
        from extensions import db
        tenant = Tenant(slug='met-concorrente', nome='met-concorrente',
                        subdominio='met-concorrente')
        db.session.add(tenant)
        db.session.commit()
        tenant_id = tenant.id

    N = 8
    erros = []

    def _registrar():
        try:
            with app.app_context():
                registrar_interacao_ia(tenant_id, tokens_in=1, tokens_out=1,
                                       custo_estimado=0.01, hoje=HOJE)
        except Exception as e:   # noqa: BLE001 — quer capturar qualquer erro pra reportar
            erros.append(e)

    threads = [threading.Thread(target=_registrar) for _ in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not erros, f'erro inesperado numa das chamadas concorrentes: {erros}'
    with app.app_context():
        uso = AiUsage.query.filter_by(tenant_id=tenant_id, periodo=PERIODO).first()
        assert uso.interacoes == N, f'esperado {N} interações, veio {uso.interacoes} — incremento perdido'
        assert uso.tokens_entrada == N
        assert uso.tokens_saida == N
