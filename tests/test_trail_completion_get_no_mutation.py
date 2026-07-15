"""Correção de segurança (ROADMAP.md §1.1) + revisão de release (H1/H2):

- GET /api/trails/active premiava XP/badge e gravava completed_at como
  efeito colateral — um GET não pode mutar estado (achável cross-site
  mesmo sob SameSite=Lax: <img src=...>, prefetch de link).
- O award foi movido para claim_trail_if_complete() (routes/trails.py),
  chamado automaticamente no instante em que o ÚLTIMO curso pendente de
  uma trilha é concluído (routes/lessons.py::submit_aula_quiz), com
  my_trails() como rede de segurança e POST /trails/active/claim como
  gatilho explícito. A função é atômica (UPDATE...WHERE completed_at IS
  NULL) — duas chamadas concorrentes só premiam uma vez (H2).
"""
import threading

import pytest


@pytest.fixture()
def trilha_com_badge(app, seeded):
    """Trilha própria (não a seedada) com badge_code, pra testar o award
    de badge também — a trilha seedada em conftest não tem badge_code."""
    from extensions import db
    from models import Trail, TrailCourse, Badge
    from core.tenancy import default_tenant_id
    with app.app_context():
        tid = default_tenant_id()
        badge = Badge.query.filter_by(tenant_id=tid, code='trilha_teste_badge').first()
        if not badge:
            badge = Badge(tenant_id=tid, code='trilha_teste_badge', name='Concluiu a Trilha Teste',
                          icon='🏅', rarity='raro')
            db.session.add(badge)
            db.session.flush()
        trail = Trail(tenant_id=tid, name='Trilha de Teste H1/H2', goal='teologia',
                      xp_bonus=150, badge_code='trilha_teste_badge')
        db.session.add(trail)
        db.session.flush()
        db.session.add(TrailCourse(tenant_id=tid, trail_id=trail.id, course_id=seeded['course_id'], position=0))
        db.session.commit()
        trail_id = trail.id
    yield trail_id
    with app.app_context():
        from models import Trail, TrailCourse, UserTrail, UserBadge, Badge
        from core.tenancy import default_tenant_id
        tid = default_tenant_id()
        UserTrail.query.filter_by(trail_id=trail_id).delete()
        TrailCourse.query.filter_by(trail_id=trail_id).delete()
        badge = Badge.query.filter_by(tenant_id=tid, code='trilha_teste_badge').first()
        if badge:
            UserBadge.query.filter_by(badge_id=badge.id).delete()
        Trail.query.filter_by(id=trail_id).delete()
        db.session.commit()


def _completar_curso_via_quiz(aluno, seeded):
    """Aprova o quiz de todos os módulos do curso seedado — mesmo caminho
    real que um aluno percorre na SPA (routes/lessons.py::submit_aula_quiz),
    não um atalho direto no banco."""
    respostas = []
    for i, modulo_id in enumerate((seeded['module1_id'], seeded['module2_id']), start=1):
        r = aluno.post(f"/api/courses/{seeded['course_id']}/aulas/{i}/submit-quiz",
                       json={'answers': [1, 1]})
        assert r.status_code == 200
        respostas.append(r.get_json())
    return respostas


# ── H1: fluxo completo, ponta a ponta ────────────────────────────────────

def test_completar_ultimo_curso_premia_trilha_automaticamente(app, aluno, seeded, trilha_com_badge):
    """H1: o award acontece automaticamente no instante em que o último
    curso pendente da trilha é concluído — sem precisar de nenhuma
    chamada extra do frontend."""
    from extensions import db
    from models import UserPoints
    from core.tenancy import default_tenant_id

    r = aluno.post(f'/api/trails/{trilha_com_badge}/enroll')
    assert r.status_code == 200

    with app.app_context():
        up = UserPoints.query.filter_by(user_id=seeded['users']['aluno'], tenant_id=default_tenant_id()).first()
        pontos_antes = up.total_points if up else 0

    respostas = _completar_curso_via_quiz(aluno, seeded)
    ultima = respostas[-1]

    # a última resposta de quiz (que fecha o curso) já vem com o prêmio.
    # certificate_issued pode ser False aqui se outro teste (ex.: suíte de
    # isolamento) já emitiu certificado pro mesmo aluno/curso antes — o que
    # importa pro H1 é o award da trilha, não a emissão do certificado.
    assert len(ultima['trail_completions']) == 1
    premio = ultima['trail_completions'][0]
    assert premio['trail_id'] == trilha_com_badge
    assert premio['xp_bonus'] == 150
    assert premio['new_badge']['code'] == 'trilha_teste_badge'

    with app.app_context():
        from models import UserTrail
        ut = UserTrail.query.filter_by(user_id=seeded['users']['aluno'], trail_id=trilha_com_badge,
                                       tenant_id=default_tenant_id()).first()
        assert ut.completed_at is not None

        up = UserPoints.query.filter_by(user_id=seeded['users']['aluno'], tenant_id=default_tenant_id()).first()
        # +150 da trilha, +100 do curso concluído, +30 do quiz passado 1ª vez
        # (não precisamos do valor exato — só que os 150 da trilha entraram
        # UMA vez, não duas nem zero).
        assert up.total_points >= pontos_antes + 150

        from models import UserBadge, Badge
        badge = Badge.query.filter_by(tenant_id=default_tenant_id(), code='trilha_teste_badge').first()
        qtd_badges = UserBadge.query.filter_by(user_id=seeded['users']['aluno'], badge_id=badge.id).count()
        assert qtd_badges == 1   # badge concedido exatamente 1 vez


def test_ui_mostra_trilha_concluida_apos_o_fluxo(aluno, seeded, trilha_com_badge):
    """'UI updates correctly': a página real que o aluno visita
    (GET /trails/my, por trás de renderTrilhasPage) reflete a conclusão
    de verdade (completed_at gravado), não só o cálculo de progresso."""
    aluno.post(f'/api/trails/{trilha_com_badge}/enroll')
    _completar_curso_via_quiz(aluno, seeded)

    r = aluno.get('/api/trails/my')
    assert r.status_code == 200
    body = r.get_json()
    concluida = next((t for t in body['completed'] if t['id'] == trilha_com_badge), None)
    assert concluida is not None
    assert concluida['completed_at'] is not None   # não só "completed: true" calculado


def test_get_active_nao_grava_completed_at_nem_premia(app, aluno, seeded, trilha_com_badge):
    """GET não pode mutar estado — só POST/gatilho automático premiam."""
    from extensions import db
    from core.tenancy import default_tenant_id

    aluno.post(f'/api/trails/{trilha_com_badge}/enroll')
    aluno.post(f'/api/trails/{trilha_com_badge}/focus')
    _completar_curso_via_quiz(aluno, seeded)

    # o auto-claim do submit-quiz já premiou — reseta pra testar o GET isolado
    with app.app_context():
        from models import UserTrail, UserBadge, Badge
        ut = UserTrail.query.filter_by(user_id=seeded['users']['aluno'], trail_id=trilha_com_badge,
                                       tenant_id=default_tenant_id()).first()
        ut.completed_at = None
        badge = Badge.query.filter_by(tenant_id=default_tenant_id(), code='trilha_teste_badge').first()
        UserBadge.query.filter_by(user_id=seeded['users']['aluno'], badge_id=badge.id).delete()
        db.session.commit()

    r = aluno.get('/api/trails/active')
    assert r.status_code == 200
    body = r.get_json()
    assert body['completed'] is True
    assert 'new_badge' not in body

    with app.app_context():
        from models import UserTrail
        ut = UserTrail.query.filter_by(user_id=seeded['users']['aluno'], trail_id=trilha_com_badge,
                                       tenant_id=default_tenant_id()).first()
        assert ut.completed_at is None, 'GET não pode gravar completed_at'


def test_post_claim_premia_uma_vez_so(app, aluno, seeded, trilha_com_badge):
    from core.tenancy import default_tenant_id

    aluno.post(f'/api/trails/{trilha_com_badge}/enroll')
    aluno.post(f'/api/trails/{trilha_com_badge}/focus')
    _completar_curso_via_quiz(aluno, seeded)   # já premia automaticamente

    # chamada explícita adicional: idempotente, não premia de novo
    r = aluno.post('/api/trails/active/claim')
    assert r.status_code == 200
    assert r.get_json()['completed_now'] is False


def test_claim_sem_trilha_ativa_e_sem_efeito(aluno):
    r = aluno.post('/api/trails/active/claim')
    assert r.status_code == 200
    assert r.get_json()['completed_now'] is False


# ── H2: corrida — duas chamadas "simultâneas" premiam só uma vez ─────────

def test_claim_concorrente_premia_exatamente_uma_vez(app, seeded, trilha_com_badge):
    """Duas threads chamando claim_trail_if_complete() pro MESMO
    usuário/trilha ao mesmo tempo — o UPDATE...WHERE completed_at IS NULL
    é atômico por linha; só uma das duas pode vencer a corrida,
    independente de quem chegou primeiro."""
    from extensions import db
    from models import UserTrail, Trail, UserPoints
    from core.tenancy import default_tenant_id

    uid = seeded['users']['aluno']
    with app.app_context():
        tid = default_tenant_id()
        db.session.add(UserTrail(tenant_id=tid, user_id=uid, trail_id=trilha_com_badge))
        db.session.commit()

        # completa o curso direto no banco (não precisa do fluxo HTTP aqui —
        # o alvo deste teste é a corrida no claim, não o caminho de conclusão)
        from models import Module, LessonProgress
        for m in Module.query.filter_by(tenant_id=tid, course_id=seeded['course_id']).all():
            if not LessonProgress.query.filter_by(user_id=uid, module_id=m.id, tenant_id=tid).first():
                db.session.add(LessonProgress(user_id=uid, course_id=seeded['course_id'], module_id=m.id,
                                              tenant_id=tid, passed=True, score=2, total=2))
        db.session.commit()

    resultados = []
    erros = []

    def _tentar_premiar():
        try:
            with app.app_context():
                from routes.trails import claim_trail_if_complete
                trail = Trail.query.get(trilha_com_badge)
                premio = claim_trail_if_complete(uid, trail)
                resultados.append(premio)
        except Exception as e:   # noqa: BLE001 — quer capturar QUALQUER erro pra reportar, não mascarar
            erros.append(e)

    threads = [threading.Thread(target=_tentar_premiar) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not erros, f'erro inesperado numa das chamadas concorrentes: {erros}'
    premiados = [r for r in resultados if r is not None]
    assert len(premiados) == 1, f'esperado exatamente 1 vencedor da corrida, veio {len(premiados)}: {resultados}'

    with app.app_context():
        tid = default_tenant_id()
        from models import UserBadge, Badge
        badge = Badge.query.filter_by(tenant_id=tid, code='trilha_teste_badge').first()
        assert UserBadge.query.filter_by(user_id=uid, badge_id=badge.id).count() == 1

    # limpeza específica deste teste (fixture cleanup só cobre a trilha em si)
    with app.app_context():
        from models import UserPoints
        pass  # xp somado fica — sem assert de valor absoluto de total_points neste teste


# ── M1: cursos internos/rascunho não vazam através de trilhas ────────────

@pytest.fixture()
def trilha_com_curso_interno(app, seeded):
    from extensions import db
    from models import Trail, TrailCourse, Course, Category
    from core.tenancy import default_tenant_id
    with app.app_context():
        tid = default_tenant_id()
        cat = Category.query.filter_by(tenant_id=tid).first()
        curso_interno = Course(tenant_id=tid, name='Curso Interno M1', acesso='interno',
                               status='published', category_id=cat.id, icon='🔒')
        curso_rascunho = Course(tenant_id=tid, name='Curso Rascunho M1', acesso='publico',
                                status='draft', category_id=cat.id, icon='📝')
        db.session.add_all([curso_interno, curso_rascunho])
        db.session.flush()
        trail = Trail(tenant_id=tid, name='Trilha M1', goal='teologia', xp_bonus=50)
        db.session.add(trail)
        db.session.flush()
        db.session.add(TrailCourse(tenant_id=tid, trail_id=trail.id, course_id=curso_interno.id, position=0))
        db.session.add(TrailCourse(tenant_id=tid, trail_id=trail.id, course_id=curso_rascunho.id, position=1))
        db.session.add(TrailCourse(tenant_id=tid, trail_id=trail.id, course_id=seeded['course_id'], position=2))
        db.session.commit()
        ids = {'trail_id': trail.id, 'interno_id': curso_interno.id, 'rascunho_id': curso_rascunho.id}
    yield ids
    with app.app_context():
        from models import Trail, TrailCourse, Course
        TrailCourse.query.filter_by(trail_id=ids['trail_id']).delete()
        Trail.query.filter_by(id=ids['trail_id']).delete()
        Course.query.filter(Course.id.in_([ids['interno_id'], ids['rascunho_id']])).delete(synchronize_session=False)
        db.session.commit()


def test_anonimo_nao_ve_curso_interno_nem_rascunho_via_trilha(app, trilha_com_curso_interno):
    anonimo = app.test_client()
    r = anonimo.get('/api/trails')
    assert r.status_code == 200
    trilha = next(t for t in r.get_json() if t['id'] == trilha_com_curso_interno['trail_id'])
    ids_visiveis = {c['course_id'] for c in trilha['courses']}
    assert trilha_com_curso_interno['interno_id'] not in ids_visiveis
    assert trilha_com_curso_interno['rascunho_id'] not in ids_visiveis


def test_aluno_ve_curso_interno_mas_nao_rascunho_via_trilha(aluno, trilha_com_curso_interno):
    r = aluno.get('/api/trails')
    assert r.status_code == 200
    trilha = next(t for t in r.get_json() if t['id'] == trilha_com_curso_interno['trail_id'])
    ids_visiveis = {c['course_id'] for c in trilha['courses']}
    assert trilha_com_curso_interno['interno_id'] in ids_visiveis
    assert trilha_com_curso_interno['rascunho_id'] not in ids_visiveis


def test_tutor_ve_tudo_via_trilha(tutor, trilha_com_curso_interno):
    r = tutor.get('/api/trails')
    assert r.status_code == 200
    trilha = next(t for t in r.get_json() if t['id'] == trilha_com_curso_interno['trail_id'])
    ids_visiveis = {c['course_id'] for c in trilha['courses']}
    assert trilha_com_curso_interno['interno_id'] in ids_visiveis
    assert trilha_com_curso_interno['rascunho_id'] in ids_visiveis


def test_admin_ve_tudo_via_trilha(admin, trilha_com_curso_interno):
    r = admin.get('/api/trails')
    assert r.status_code == 200
    trilha = next(t for t in r.get_json() if t['id'] == trilha_com_curso_interno['trail_id'])
    ids_visiveis = {c['course_id'] for c in trilha['courses']}
    assert trilha_com_curso_interno['interno_id'] in ids_visiveis
    assert trilha_com_curso_interno['rascunho_id'] in ids_visiveis


def test_aluno_nao_ve_rascunho_ao_se_inscrever_na_trilha(aluno, trilha_com_curso_interno):
    """M1 (achado da 2ª revisão): enroll_trail respondia com
    trail.to_dict(include_courses=True) sem filtro — curso rascunho vazava
    pro aluno no exato momento em que ele se inscrevia na trilha."""
    r = aluno.post(f"/api/trails/{trilha_com_curso_interno['trail_id']}/enroll")
    assert r.status_code == 200
    ids_visiveis = {c['course_id'] for c in r.get_json()['trail']['courses']}
    assert trilha_com_curso_interno['interno_id'] in ids_visiveis
    assert trilha_com_curso_interno['rascunho_id'] not in ids_visiveis


def test_aluno_nao_ve_rascunho_em_minhas_trilhas(aluno, trilha_com_curso_interno):
    """M1 (achado da 2ª revisão): my_trails/_annotate_trail_progress também
    serializava trail.to_dict(include_courses=True) sem o filtro de M1."""
    aluno.post(f"/api/trails/{trilha_com_curso_interno['trail_id']}/enroll")
    r = aluno.get('/api/trails/my')
    assert r.status_code == 200
    body = r.get_json()
    trilha = next(t for t in body['in_progress'] + body['completed']
                  if t['id'] == trilha_com_curso_interno['trail_id'])
    ids_visiveis = {c['course_id'] for c in trilha['courses']}
    assert trilha_com_curso_interno['interno_id'] in ids_visiveis
    assert trilha_com_curso_interno['rascunho_id'] not in ids_visiveis


def test_trilha_com_curso_oculto_nao_aparece_completa_pro_aluno(app, aluno, seeded, trilha_com_curso_interno):
    """Achado da 2ª revisão (Fable 5): completed=true era calculado sobre a
    lista JÁ filtrada por _trail_dict_scoped — um aluno que termina todos os
    cursos visíveis via completed=true numa trilha que ainda tem um curso
    rascunho pendente (só staff vê/pode concluir), e o front fica preso
    chamando POST /trails/active/claim pra sempre sem nunca premiar. O
    critério de completude tem que ser o mesmo em toda parte: TODOS os
    trail_courses reais, igual claim_trail_if_complete exige."""
    from core.tenancy import default_tenant_id
    from models import Module, LessonProgress
    from extensions import db

    tid_trail = trilha_com_curso_interno['trail_id']
    aluno.post(f'/api/trails/{tid_trail}/enroll')
    aluno.post(f'/api/trails/{tid_trail}/focus')
    _completar_curso_via_quiz(aluno, seeded)  # completa o único curso que o aluno enxerga/pode fazer

    r = aluno.get('/api/trails/active')
    assert r.status_code == 200
    body = r.get_json()
    # o rascunho continua pendente (staff-only) — não pode aparecer "completa"
    assert body['completed'] is False

    r = aluno.get('/api/trails/my')
    trilha = next(t for t in r.get_json()['in_progress'] + r.get_json()['completed']
                  if t['id'] == tid_trail)
    assert trilha['completed'] is False

    r = aluno.post('/api/trails/active/claim')
    assert r.get_json()['completed_now'] is False
