"""Resposta em lote do tutor: só dúvidas do próprio tenant e dos próprios cursos."""
from tests.isolation.conftest import TenantClient, HOST_A
from tests.isolation.test_credenciais_globais import usuario_admin_em_ab  # noqa: F401


def _pergunta(db, Question, tenant_id, course_id, user_id, texto):
    q = Question(course_id=course_id, user_id=user_id, texto=texto, tenant_id=tenant_id)
    db.session.add(q); db.session.flush(); return q.id


def test_lote_responde_varias_e_recusa_pergunta_de_outro_tenant(iso_app, seeded, usuario_admin_em_ab):  # noqa: F811
    from extensions import db
    from models import Question, Course, Notification
    from core.tenancy import Tenant
    with iso_app.app_context():
        a = Tenant.query.filter_by(slug='ibc').first(); b = Tenant.query.filter_by(slug='demo').first()
        curso_b = Course(name='Curso B', tenant_id=b.id); db.session.add(curso_b); db.session.flush()
        aluno = seeded['users']['aluno']
        q1 = _pergunta(db, Question, a.id, seeded['course_id'], aluno, 'Dúvida A1')
        q2 = _pergunta(db, Question, a.id, seeded['course_id'], aluno, 'Dúvida A2')
        qb = _pergunta(db, Question, b.id, curso_b.id, aluno, 'Dúvida B')
        db.session.commit()

    c = TenantClient(iso_app.test_client(), HOST_A)
    c.post('/api/auth/login', json={'email': 'admin@test.com', 'password': 'senha123'})
    # pergunta do tenant B no lote: nada é respondido
    r = c.post('/api/questions/responder-lote', json={'ids': [q1, qb], 'resposta': 'Veja a aula 2.'})
    assert r.status_code == 404
    with iso_app.app_context():
        assert Question.query.get(q1).resposta == ''
        assert Question.query.get(qb).resposta == ''

    r = c.post('/api/questions/responder-lote', json={'ids': [q1, q2], 'resposta': 'Veja a aula 2.'})
    assert r.status_code == 200 and r.get_json()['respondidas'] == 2
    with iso_app.app_context():
        assert Question.query.get(q1).status == 'answered' and Question.query.get(q2).resposta == 'Veja a aula 2.'
        assert Notification.query.filter_by(user_id=aluno, title='Sua pergunta foi respondida').count() >= 2
        Question.query.filter(Question.id.in_([q1, q2, qb])).delete(synchronize_session=False)
        Course.query.filter_by(name='Curso B').delete()
        db.session.commit()


def test_aluno_nao_responde_em_lote(client, aluno):
    assert aluno.post('/api/questions/responder-lote', json={'ids': [1], 'resposta': 'x'}).status_code == 403


def test_lote_valida_entrada(admin):
    assert admin.post('/api/questions/responder-lote', json={'ids': [], 'resposta': 'x'}).status_code == 400
    assert admin.post('/api/questions/responder-lote', json={'ids': [1], 'resposta': ''}).status_code == 400
    assert admin.post('/api/questions/responder-lote', json={'ids': list(range(21)), 'resposta': 'x'}).status_code == 400


def test_aula_de_outro_tenant_nao_pode_ser_origem_da_duvida(iso_app, seeded):
    from extensions import db
    from models import Course, Module
    from core.tenancy import Tenant
    from tests.isolation.conftest import HOST_A
    with iso_app.app_context():
        b = Tenant.query.filter_by(slug='demo').first()
        cb = Course(name='Curso B aula', tenant_id=b.id); db.session.add(cb); db.session.flush()
        mb = Module(course_id=cb.id, nome='Aula B', tenant_id=b.id); db.session.add(mb); db.session.commit()
        mid, cid_b = mb.id, cb.id
    try:
        c = TenantClient(iso_app.test_client(), HOST_A)
        c.post('/api/auth/login', json={'email': 'aluno@test.com', 'password': 'senha123'})
        r = c.post(f"/api/questions/{seeded['course_id']}", json={'texto': 'x', 'module_id': mid})
        assert r.status_code == 400
    finally:
        with iso_app.app_context():
            Module.query.filter_by(id=mid).delete(); Course.query.filter_by(id=cid_b).delete(); db.session.commit()
