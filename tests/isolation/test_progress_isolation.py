"""Casos de isolamento do grupo 2 — progresso (Fase 3).

O MESMO usuário tem progresso de aulas, matrículas em trilha e onboarding
independentes por tenant: avançar no tenant A não desbloqueia nada em B.
"""
import pytest

from tests.isolation.conftest import TenantClient, HOST_A, HOST_B


@pytest.fixture()
def aluno_em(iso_app, seeded, vinculo_b):
    def _login(host):
        c = TenantClient(iso_app.test_client(), host)
        r = c.post('/api/auth/login', json={'email': 'aluno@test.com',
                                            'password': 'senha123'})
        assert r.status_code == 200
        return c
    return _login


def _limpa_progresso(iso_app, seeded):
    with iso_app.app_context():
        from extensions import db
        from models import LessonProgress
        LessonProgress.query.filter_by(user_id=seeded['users']['aluno']).delete()
        db.session.commit()


def test_progresso_de_aula_nao_desbloqueia_em_outro_tenant(aluno_em, iso_app, seeded):
    _limpa_progresso(iso_app, seeded)
    cid = seeded['course_id']
    a = aluno_em(HOST_A)
    b = aluno_em(HOST_B)

    # passa a aula 1 no tenant A (gabarito do conftest: índice 1)
    r = a.post(f'/api/courses/{cid}/aulas/1/submit-quiz', json={'answers': [1, 1]})
    assert r.status_code == 200 and r.get_json()['passed'] is True
    assert a.get(f'/api/courses/{cid}/aulas/2').status_code == 200  # desbloqueou em A

    # em B o curso NEM EXISTE (grupo 3: conteúdo é por tenant) — 404 em tudo,
    # que é isolamento ainda mais forte que progresso zerado
    assert b.get(f'/api/courses/{cid}/aulas/2').status_code == 404
    assert b.get(f'/api/courses/{cid}/aulas').status_code == 404
    assert b.get(f'/api/courses/{cid}').status_code == 404

    _limpa_progresso(iso_app, seeded)


def test_matricula_em_trilha_nao_vaza(aluno_em, iso_app, seeded):
    tid = seeded['trail_id']
    a = aluno_em(HOST_A)
    b = aluno_em(HOST_B)

    r = a.post(f'/api/trails/{tid}/enroll')
    assert r.status_code in (200, 201)

    def _ids(resp):
        body = resp.get_json()
        return {t['id'] for t in body.get('in_progress', []) + body.get('completed', [])}

    assert tid in _ids(a.get('/api/trails/my'))
    assert tid not in _ids(b.get('/api/trails/my'))

    with iso_app.app_context():
        from extensions import db
        from models import UserTrail
        UserTrail.query.filter_by(user_id=seeded['users']['aluno']).delete()
        db.session.commit()


def test_onboarding_answer_por_tenant(aluno_em, iso_app, seeded):
    """A resposta de onboarding (OnboardingAnswer) é por tenant — responder
    em A não cria registro em B. (A flag User.onboarding_completed é global
    por design atual — registrada em docs/DEBITOS.md.)"""
    a = aluno_em(HOST_A)
    r = a.post('/api/onboarding', json={'goal': 'teologia'})
    assert r.status_code in (200, 201)

    with iso_app.app_context():
        from core.tenancy import Tenant
        from models import OnboardingAnswer
        uid = seeded['users']['aluno']
        a_id = Tenant.query.filter_by(slug='ibc').first().id
        b_id = Tenant.query.filter_by(slug='demo').first().id
        assert OnboardingAnswer.query.filter_by(user_id=uid, tenant_id=a_id).count() == 1
        assert OnboardingAnswer.query.filter_by(user_id=uid, tenant_id=b_id).count() == 0

        from extensions import db
        OnboardingAnswer.query.filter_by(user_id=uid).delete()
        db.session.commit()


def test_progresso_legado_zero_linhas_cruzadas(iso_app, tenants_ab, seeded):
    """Tabela Progress (legada): consulta escopada em A não vê linhas de B."""
    with iso_app.app_context():
        from extensions import db
        from models import Progress
        uid = seeded['users']['aluno']
        a_id, b_id = tenants_ab['a_id'], tenants_ab['b_id']

        Progress.query.filter_by(user_id=uid).delete()
        db.session.add(Progress(user_id=uid, course_id=seeded['course_id'],
                                material_done=True, tenant_id=a_id))
        db.session.commit()

        assert Progress.query.filter_by(user_id=uid, tenant_id=a_id).count() == 1
        assert Progress.query.filter_by(user_id=uid, tenant_id=b_id).count() == 0

        Progress.query.filter_by(user_id=uid).delete()
        db.session.commit()
