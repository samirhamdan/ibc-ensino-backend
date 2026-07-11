"""Correção de segurança (ROADMAP.md §1.1): GET /api/trails/active premiava
XP/badge e gravava completed_at como efeito colateral — um GET não pode
mutar estado (achável cross-site mesmo sob SameSite=Lax: <img src=...>,
prefetch de link). O award agora só acontece em POST /trails/active/claim,
idempotente.
"""
from datetime import datetime

import pytest


@pytest.fixture()
def aluno_com_trilha_completa(app, aluno, seeded):
    """Matricula o aluno na trilha seedada e completa o único curso dela
    (aprova o quiz de todos os módulos)."""
    from extensions import db
    from models import UserPoints, UserTrail

    r = aluno.post(f"/api/trails/{seeded['trail_id']}/enroll")
    assert r.status_code == 200

    for modulo_id in (seeded['module1_id'], seeded['module2_id']):
        r = aluno.post(f"/api/courses/{seeded['course_id']}/aulas/"
                       f"{1 if modulo_id == seeded['module1_id'] else 2}/submit-quiz",
                       json={'answers': [1, 1]})
        assert r.status_code == 200

    yield

    with app.app_context():
        from core.tenancy import default_tenant_id
        UserTrail.query.filter_by(trail_id=seeded['trail_id']).delete()
        up = UserPoints.query.filter_by(user_id=seeded['users']['aluno'], tenant_id=default_tenant_id()).first()
        if up:
            up.total_points = max(0, (up.total_points or 0))
        db.session.commit()


def test_get_active_nao_grava_completed_at_nem_premia(app, aluno, seeded, aluno_com_trilha_completa):
    with app.app_context():
        from models import UserTrail
        from core.tenancy import default_tenant_id
        ut = UserTrail.query.filter_by(user_id=seeded['users']['aluno'], trail_id=seeded['trail_id'],
                                       tenant_id=default_tenant_id()).first()
        assert ut.completed_at is None

    r = aluno.get('/api/trails/active')
    assert r.status_code == 200
    body = r.get_json()
    assert body['completed'] is True
    assert 'new_badge' not in body   # award só acontece via POST /claim

    with app.app_context():
        from models import UserTrail
        from core.tenancy import default_tenant_id
        ut = UserTrail.query.filter_by(user_id=seeded['users']['aluno'], trail_id=seeded['trail_id'],
                                       tenant_id=default_tenant_id()).first()
        assert ut.completed_at is None, 'GET não pode gravar completed_at'


def test_post_claim_premia_uma_vez_so(app, aluno, seeded, aluno_com_trilha_completa):
    r1 = aluno.post('/api/trails/active/claim')
    assert r1.status_code == 200
    body1 = r1.get_json()
    assert body1['completed_now'] is True
    assert 'xp_bonus' in body1

    with app.app_context():
        from models import UserTrail
        from core.tenancy import default_tenant_id
        ut = UserTrail.query.filter_by(user_id=seeded['users']['aluno'], trail_id=seeded['trail_id'],
                                       tenant_id=default_tenant_id()).first()
        assert ut.completed_at is not None

    r2 = aluno.post('/api/trails/active/claim')
    assert r2.status_code == 200
    assert r2.get_json()['completed_now'] is False


def test_claim_sem_trilha_ativa_e_sem_efeito(aluno):
    r = aluno.post('/api/trails/active/claim')
    assert r.status_code == 200
    assert r.get_json()['completed_now'] is False
