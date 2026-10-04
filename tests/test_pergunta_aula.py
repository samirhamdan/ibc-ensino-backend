"""Dúvida guarda a aula de origem (questions.module_id)."""


def test_pergunta_com_aula_e_tutor_ve_numero_da_aula(app, seeded, aluno):
    from extensions import db
    from models import Question
    cid, m2 = seeded['course_id'], seeded['module2_id']
    r = aluno.post(f'/api/questions/{cid}', json={'texto': 'Dúvida da aula 2', 'module_id': m2})
    assert r.status_code == 201
    q = r.get_json()
    assert q['module_id'] == m2 and q['module_nome'] == 'Aula 2'
    try:
        tutor = app.test_client()
        tutor.post('/api/auth/login', json={'email': 'tutor@test.com', 'password': 'senha123'})
        lista = tutor.get('/api/questions/tutor/dashboard').get_json()
        item = next(x for x in lista if x['id'] == q['id'])
        assert item['aula_num'] == 2
    finally:
        with app.app_context():
            Question.query.filter_by(id=q['id']).delete(); db.session.commit()


def test_pergunta_sem_aula_continua_valida(app, seeded, aluno):
    from extensions import db
    from models import Question
    r = aluno.post(f"/api/questions/{seeded['course_id']}", json={'texto': 'Geral'})
    assert r.status_code == 201 and r.get_json()['module_id'] is None
    with app.app_context():
        Question.query.filter_by(id=r.get_json()['id']).delete(); db.session.commit()


def test_aula_de_outro_curso_e_recusada(app, seeded, aluno):
    from extensions import db
    from models import Course, Module
    with app.app_context():
        outro = Course(name='Outro curso', status='published'); db.session.add(outro); db.session.flush()
        m = Module(course_id=outro.id, nome='Aula alheia'); db.session.add(m); db.session.commit()
        mid, oid = m.id, outro.id
    try:
        r = aluno.post(f"/api/questions/{seeded['course_id']}", json={'texto': 'x', 'module_id': mid})
        assert r.status_code == 400
        assert aluno.post(f"/api/questions/{seeded['course_id']}", json={'texto': 'x', 'module_id': 'abc'}).status_code == 400
    finally:
        with app.app_context():
            Module.query.filter_by(id=mid).delete(); Course.query.filter_by(id=oid).delete(); db.session.commit()
