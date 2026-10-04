"""Menu lateral do aluno: /api/aluno/meus-cursos usa o progresso real das aulas."""


def test_meus_cursos_reflete_aula_concluida(app, seeded, aluno):
    from extensions import db
    from models import LessonProgress, Question
    assert aluno.get('/api/aluno/meus-cursos').get_json()['cursos'] == []
    with app.app_context():
        db.session.add(LessonProgress(user_id=seeded['users']['aluno'], course_id=seeded['course_id'],
                                      module_id=seeded['module1_id'], passed=True, score=2, total=2))
        db.session.add(Question(course_id=seeded['course_id'], user_id=seeded['users']['aluno'],
                                texto='?', resposta='!', status='answered'))
        db.session.commit()
    try:
        d = aluno.get('/api/aluno/meus-cursos').get_json()
        c = d['cursos'][0]
        assert c['id'] == seeded['course_id'] and c['percentage'] == 50
        assert c['aula_atual'] == 2 and c['total_aulas'] == 2 and c['status'] == 'em_andamento'
        assert d['respostas_novas'] == 1
    finally:
        with app.app_context():
            LessonProgress.query.filter_by(user_id=seeded['users']['aluno'], course_id=seeded['course_id']).delete()
            Question.query.filter_by(user_id=seeded['users']['aluno'], texto='?').delete()
            db.session.commit()


def test_meus_cursos_so_para_aluno(admin):
    assert admin.get('/api/aluno/meus-cursos').status_code == 403
