"""GAM-02 (Etapa 3, UX_ALUNO_SAAS.md §3 Grupo 3/§6): streak de dias
consecutivos, calculado em routes/gamification.py::award_points no
gatilho 'daily_login' — mesmo hook que já limitava o bônus de login a
1x/dia. Testes diretos da função (não via HTTP): controlar
last_activity_date em transições de dia exigiria "viajar no tempo" pelo
login real; chamar award_points direto com o estado montado é mais
simples e testa exatamente a lógica nova.
"""
from datetime import timedelta

import pytest

from routes.gamification import award_points, STREAK_MARCOS, streak_efetivo, hoje_streak

# hoje_streak() (America/Sao_Paulo), não date.today() (relógio local da
# máquina, que pode ser UTC no CI) — testar com uma fonte de "hoje"
# diferente da que routes/gamification.py usa é o tipo exato de bug que
# passa/falha por acaso dependendo do fuso do runner (achado de revisão).


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
    ontem = hoje_streak() - timedelta(days=1)
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
    hoje = hoje_streak()
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
    tres_dias_atras = hoje_streak() - timedelta(days=3)
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
    ontem = hoje_streak() - timedelta(days=1)
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
    ontem = hoje_streak() - timedelta(days=1)
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
    ontem = hoje_streak() - timedelta(days=1)
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
    ontem = hoje_streak() - timedelta(days=1)
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


def test_outra_acao_nao_toca_last_activity_date(app, uid):
    """Correção de revisão (H1): a versão anterior atualizava
    last_activity_date em TODA ação — um material_read num dia sem login
    "consertava" um streak que devia estar quebrado. Agora só daily_login
    lê/escreve esse campo."""
    ontem = hoje_streak() - timedelta(days=1)
    tres_dias_atras = hoje_streak() - timedelta(days=3)
    _set_last_activity(app, uid, tres_dias_atras)
    with app.app_context():
        from extensions import db
        from models import UserPoints
        from core.tenancy import default_tenant_id
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        up.current_streak = 10
        db.session.commit()

        award_points(uid, 'material_read')   # dia de estudo, SEM login

        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        assert up.last_activity_date == tres_dias_atras   # não mudou
        assert up.current_streak == 10   # streak "morto" continua intacto na linha

        # login no dia seguinte àquele activity (não ao material_read de
        # hoje) reinicia — o material_read de hoje não "salvou" o streak
        r = award_points(uid, 'daily_login')
        assert r['current_streak'] == 1


def test_retry_no_mesmo_dia_nao_paga_marco_duas_vezes(app, uid):
    """Correção de revisão (M2): antes, a checagem de marco ficava FORA
    dos ramos de transição — uma segunda chamada de daily_login no mesmo
    dia (retry, corrida) com current_streak já em cima de um marco pagava
    o bônus de novo. Agora só o ramo que incrementa concede bônus."""
    ontem = hoje_streak() - timedelta(days=1)
    _set_last_activity(app, uid, ontem)
    with app.app_context():
        from extensions import db
        from models import UserPoints
        from core.tenancy import default_tenant_id
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        up.current_streak = 6   # vira 7 (marco) nesta chamada
        db.session.commit()

        r1 = award_points(uid, 'daily_login')
        assert r1['streak_bonus'] == STREAK_MARCOS[7]

        r2 = award_points(uid, 'daily_login')   # retry, mesmo dia
        assert r2['streak_bonus'] == 0
        assert r2['streak_marco_atingido'] is None
        assert r2['current_streak'] == 7   # não incrementou de novo


class TestStreakEfetivo:
    """Correção de revisão (H2): current_streak só é zerado de verdade no
    PRÓXIMO login (lazy reset) — o dashboard não pode mostrar um streak
    morto há semanas como "vencendo hoje". streak_efetivo() reinterpreta
    o valor na leitura, sem tocar o banco."""

    def test_sem_streak(self):
        assert streak_efetivo(None) == (0, False)

    def test_renovado_hoje_nao_esta_em_risco(self, app):
        with app.app_context():
            from models import UserPoints
            up = UserPoints(current_streak=5, last_activity_date=hoje_streak())
            assert streak_efetivo(up) == (5, False)

    def test_renovado_ontem_esta_em_risco(self, app):
        with app.app_context():
            from models import UserPoints
            up = UserPoints(current_streak=5, last_activity_date=hoje_streak() - timedelta(days=1))
            assert streak_efetivo(up) == (5, True)

    def test_quebrado_ha_semanas_aparece_como_zero_nao_em_risco(self, app):
        """O achado exato da revisão: current_streak=10 na linha, mas
        last_activity_date de um mês atrás — não pode aparecer como
        "sequência de 10 dias, vence hoje"."""
        with app.app_context():
            from models import UserPoints
            up = UserPoints(current_streak=10, last_activity_date=hoje_streak() - timedelta(days=30))
            assert streak_efetivo(up) == (0, False)
