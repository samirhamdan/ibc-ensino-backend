"""GAM-02 (Etapa 3, UX_ALUNO_SAAS.md §3 Grupo 3/§6): streak de dias
consecutivos, calculado em routes/gamification.py::award_points no
gatilho 'daily_login' — mesmo hook que já limitava o bônus de login a
1x/dia. Testes diretos da função (não via HTTP): controlar
last_activity_date em transições de dia exigiria "viajar no tempo" pelo
login real; chamar award_points direto com o estado montado é mais
simples e testa exatamente a lógica nova.
"""
from datetime import date, timedelta

import pytest

from routes.gamification import award_points, STREAK_MARCOS


@pytest.fixture()
def uid(app, seeded):
    """`aluno` é compartilhado (session-scoped) por toda a suíte — restaura
    total_points/streak ao final, mesmo padrão de tests/isolation/*.py
    (nenhum outro teste hoje depende do valor absoluto, mas não é motivo
    para deixar o estado sujo pra próxima pessoa que escrever um)."""
    from extensions import db
    from models import UserPoints
    from core.tenancy import default_tenant_id
    aluno_id = seeded['users']['aluno']
    with app.app_context():
        up = UserPoints.query.filter_by(user_id=aluno_id, tenant_id=default_tenant_id()).first()
        original = (up.total_points, up.current_level, up.points_in_level,
                   up.last_activity_date, up.current_streak, up.longest_streak) if up else None
    yield aluno_id
    with app.app_context():
        up = UserPoints.query.filter_by(user_id=aluno_id, tenant_id=default_tenant_id()).first()
        if up and original:
            (up.total_points, up.current_level, up.points_in_level,
             up.last_activity_date, up.current_streak, up.longest_streak) = original
            db.session.commit()


def _set_last_activity(app, uid, dia):
    from extensions import db
    from models import UserPoints
    from core.tenancy import default_tenant_id
    with app.app_context():
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        if up is None:
            up = UserPoints(user_id=uid, tenant_id=default_tenant_id(), total_points=0,
                            current_level=1, points_in_level=0, current_streak=0, longest_streak=0)
            db.session.add(up)
        up.last_activity_date = dia
        up.current_streak = 0
        up.longest_streak = 0
        db.session.commit()


def test_primeiro_login_inicia_streak_em_1(app, uid):
    _set_last_activity(app, uid, None)
    with app.app_context():
        r = award_points(uid, 'daily_login')
        assert r['current_streak'] == 1


def test_login_no_dia_seguinte_incrementa(app, uid):
    ontem = date.today() - timedelta(days=1)
    _set_last_activity(app, uid, ontem)
    with app.app_context():
        from extensions import db
        from models import UserPoints
        from core.tenancy import default_tenant_id
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        up.current_streak = 5
        db.session.commit()

        r = award_points(uid, 'daily_login')
        assert r['current_streak'] == 6


def test_login_no_mesmo_dia_nao_conta_duas_vezes(app, uid):
    hoje = date.today()
    _set_last_activity(app, uid, hoje)
    with app.app_context():
        from extensions import db
        from models import UserPoints
        from core.tenancy import default_tenant_id
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        up.current_streak = 3
        db.session.commit()

        r = award_points(uid, 'daily_login')
        assert r['current_streak'] == 3   # não incrementou de novo


def test_dia_perdido_reinicia_streak(app, uid):
    tres_dias_atras = date.today() - timedelta(days=3)
    _set_last_activity(app, uid, tres_dias_atras)
    with app.app_context():
        from extensions import db
        from models import UserPoints
        from core.tenancy import default_tenant_id
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        up.current_streak = 10
        db.session.commit()

        r = award_points(uid, 'daily_login')
        assert r['current_streak'] == 1   # quebrou, reinicia


def test_longest_streak_nunca_diminui(app, uid):
    ontem = date.today() - timedelta(days=1)
    _set_last_activity(app, uid, ontem)
    with app.app_context():
        from extensions import db
        from models import UserPoints
        from core.tenancy import default_tenant_id
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        up.current_streak = 5
        up.longest_streak = 20   # recorde de uma sequência anterior, já quebrada
        db.session.commit()

        award_points(uid, 'daily_login')

        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        assert up.current_streak == 6
        assert up.longest_streak == 20   # não regrediu


@pytest.mark.parametrize('marco', sorted(STREAK_MARCOS))
def test_marco_de_streak_dispara_bonus(app, uid, marco):
    ontem = date.today() - timedelta(days=1)
    _set_last_activity(app, uid, ontem)
    with app.app_context():
        from extensions import db
        from models import UserPoints
        from core.tenancy import default_tenant_id
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        up.current_streak = marco - 1
        pontos_antes = up.total_points
        db.session.commit()

        r = award_points(uid, 'daily_login')
        assert r['current_streak'] == marco
        assert r['streak_marco_atingido'] == marco
        assert r['streak_bonus'] == STREAK_MARCOS[marco]

        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        esperado = pontos_antes + 5 + STREAK_MARCOS[marco]   # 5 = POINTS_PER_ACTION['daily_login']
        assert up.total_points == esperado


def test_dia_normal_sem_marco_nao_da_bonus(app, uid):
    ontem = date.today() - timedelta(days=1)
    _set_last_activity(app, uid, ontem)
    with app.app_context():
        from extensions import db
        from models import UserPoints
        from core.tenancy import default_tenant_id
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        up.current_streak = 2   # vira 3, não é marco
        db.session.commit()

        r = award_points(uid, 'daily_login')
        assert r['current_streak'] == 3
        assert r['streak_marco_atingido'] is None
        assert r['streak_bonus'] == 0


def test_outras_acoes_nao_mexem_no_streak(app, uid):
    ontem = date.today() - timedelta(days=1)
    _set_last_activity(app, uid, ontem)
    with app.app_context():
        from extensions import db
        from models import UserPoints
        from core.tenancy import default_tenant_id
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        up.current_streak = 5
        db.session.commit()

        award_points(uid, 'material_read')

        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        assert up.current_streak == 5   # inalterado — só daily_login mexe
