"""Dashboard do aluno v2: campos novos da API e regressão do dashboard externo."""


def test_dashboard_aluno_traz_proxima_aula_e_meta_do_dia(app, seeded, aluno):
    from extensions import db
    from models import LessonProgress
    with app.app_context():
        db.session.add(LessonProgress(user_id=seeded['users']['aluno'], course_id=seeded['course_id'],
                                      module_id=seeded['module1_id'], passed=True, score=2, total=2))
        db.session.commit()
    try:
        d = aluno.get('/api/aluno/dashboard').get_json()
        ip = d['in_progress_course']
        assert ip['proxima_aula']['nome'] == 'Aula 2'
        assert ip['aulas_restantes'] == 1
        assert d['user_stats']['estudou_hoje'] is True
        assert 'conquistas_novas' in d['user_stats']
    finally:
        with app.app_context():
            LessonProgress.query.filter_by(user_id=seeded['users']['aluno'], course_id=seeded['course_id']).delete()
            db.session.commit()


def test_dashboard_externo_logado_nao_quebra(aluno):
    r = aluno.get('/api/aluno-externo/dashboard')
    assert r.status_code == 200
