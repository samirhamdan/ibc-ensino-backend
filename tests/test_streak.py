"""GAM-02 (Etapa 3, UX_ALUNO_SAAS.md §3 Grupo 3/§4 Grupo 4/§6): streak de
dias consecutivos, calculado em routes/gamification.py::award_points —
QUALQUER ação real de estudo conta como "esteve ativo hoje" (correção da
auditoria de release, achado H2: a versão anterior só contava
'daily_login', contradizendo a UI/doc, que prometem que estudar mantém o
streak). Testes diretos da função (não via HTTP): controlar
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


def test_resposta_do_tutor_nao_mantem_streak_do_aluno_que_perguntou(app, uid):
    """Achado da 2ª revisão Fable 5 (mesma classe do bloqueador H2): quem
    AGE em 'question_answered' é o TUTOR que responde — award_points(uid,
    'question_answered') credita pontos pro aluno que perguntou, mas isso
    não é o aluno "estando ativo hoje". Um tutor respondendo uma pergunta
    antiga não pode manter/estender o streak de alguém que não fez nada."""
    ontem = hoje_streak() - timedelta(days=1)
    _set_last_activity(app, uid, ontem)
    with app.app_context():
        from extensions import db
        from models import UserPoints
        from core.tenancy import default_tenant_id
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        up.current_streak = 5
        db.session.commit()

        from routes.gamification import POINTS_PER_ACTION
        r = award_points(uid, 'question_answered')   # ação do TUTOR, não do aluno

        assert r['streak_bonus'] == 0
        assert r['streak_marco_atingido'] is None
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        assert up.current_streak == 5   # não mexeu — nem incrementou nem reiniciou
        assert up.last_activity_date == ontem   # não atualizou last_activity_date
        assert r['points_awarded'] == POINTS_PER_ACTION['question_answered']   # os pontos, sim, continuam sendo dados


def test_estudar_sem_logar_de_novo_mantem_o_streak(app, uid):
    """Correção da auditoria de release (achado H2/Etapa 3): a versão
    anterior só contava 'daily_login' — um aluno que estuda todo dia sem
    reenviar o form de login (sessão continua viva) perdia o streak
    silenciosamente, contradizendo a UI ("estude hoje para não perdê-la")
    e a doc (UX_ALUNO_SAAS.md §3 Grupo 4: "completar a revisão mantém o
    streak"). Agora qualquer ação real de estudo conta como "esteve ativo
    hoje" — não só o login."""
    ontem = hoje_streak() - timedelta(days=1)
    _set_last_activity(app, uid, ontem)
    with app.app_context():
        from extensions import db
        from models import UserPoints
        from core.tenancy import default_tenant_id
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        up.current_streak = 5
        db.session.commit()

        award_points(uid, 'material_read')   # dia de estudo, SEM login

        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        assert up.current_streak == 6   # estendeu, igual um login teria feito
        assert up.last_activity_date == hoje_streak()


def test_duas_acoes_no_mesmo_dia_nao_incrementam_streak_duas_vezes(app, uid):
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
        award_points(uid, 'quiz_attempted')
        r = award_points(uid, 'daily_login')

        assert r['current_streak'] == 6   # só incrementou uma vez, na primeira ação do dia


def test_streak_morto_nao_se_salva_por_acao_de_dia_muito_antigo(app, uid):
    """Uma ação de estudo só ESTENDE um streak que ainda vale (ontem) ou
    reinicia um streak morto (mais de 1 dia sem atividade) — nunca finge
    que os dias perdidos no meio não aconteceram."""
    tres_dias_atras = hoje_streak() - timedelta(days=3)
    _set_last_activity(app, uid, tres_dias_atras)
    with app.app_context():
        from extensions import db
        from models import UserPoints
        from core.tenancy import default_tenant_id
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        up.current_streak = 10
        db.session.commit()

        r = award_points(uid, 'material_read')

        assert r['current_streak'] == 1   # reiniciou, não "consertou" os 10 antigos


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


def test_duas_acoes_de_estudo_concorrentes_nao_dobram_o_marco(app, uid):
    """Achado da auditoria de release: generalizar o streak de
    'daily_login' pra "qualquer ação" reabre a corrida que o lock do login
    já existia pra evitar — se duas ações reais (não só login) rodarem "ao
    mesmo tempo" (duas abas, dois quizzes seguidos rápido demais),
    _get_or_create_points(lock=True) tem que serializar as duas, senão dá
    streak +2 / bônus de marco em dobro no mesmo dia."""
    import threading

    ontem = hoje_streak() - timedelta(days=1)
    _set_last_activity(app, uid, ontem)
    with app.app_context():
        from extensions import db
        from models import UserPoints
        from core.tenancy import default_tenant_id
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        up.current_streak = 6   # vira 7 (marco) na próxima ação
        db.session.commit()

    resultados = []
    erros = []

    def _agir(acao):
        try:
            with app.app_context():
                resultados.append(award_points(uid, acao))
        except Exception as e:   # noqa: BLE001 — quer capturar QUALQUER erro pra reportar
            erros.append(e)

    threads = [threading.Thread(target=_agir, args=(acao,))
               for acao in ('material_read', 'quiz_attempted')]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not erros, f'erro inesperado numa das chamadas concorrentes: {erros}'
    with app.app_context():
        from models import UserPoints
        from core.tenancy import default_tenant_id
        up = UserPoints.query.filter_by(user_id=uid, tenant_id=default_tenant_id()).first()
        assert up.current_streak == 7, f'esperado incrementar 1x só (6→7), veio {up.current_streak}'

    bonus_pagos = [r['streak_bonus'] for r in resultados if r['streak_bonus']]
    assert len(bonus_pagos) == 1, f'bônus de marco pago mais de uma vez: {resultados}'


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
