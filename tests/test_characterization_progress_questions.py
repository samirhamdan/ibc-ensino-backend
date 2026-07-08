"""Progresso legado (tabela Progress) e fluxo de perguntas/respostas."""
from tests.conftest import login


def test_progresso_default_zerado(fresh_aluno, seeded):
    r = fresh_aluno.get(f"/api/progress/{seeded['course_id']}")
    assert r.status_code == 200
    body = r.get_json()
    assert body['material_done'] is False
    assert body['quiz_score'] == 0


def test_progresso_aceita_apenas_material_done(fresh_aluno, seeded):
    """CARACTERIZAÇÃO: quiz_score/quiz_total do cliente são ignorados —
    nota só entra pela correção do servidor."""
    r = fresh_aluno.post(f"/api/progress/{seeded['course_id']}",
                         json={'material_done': True, 'quiz_score': 10, 'quiz_total': 10})
    assert r.status_code == 200
    body = r.get_json()
    assert body['material_done'] is True
    assert body['quiz_score'] == 0
    assert body['quiz_total'] == 0


def test_quiz_legado_do_curso_corrigido_no_servidor(fresh_aluno, seeded):
    """POST /progress/quiz/<id>/submit corrige e persiste na tabela Progress.
    CARACTERIZAÇÃO: este fluxo REVELA o gabarito mesmo errando (diferente do
    quiz de aula) — registrado em docs/DEBITOS.md."""
    r = fresh_aluno.post(f"/api/progress/quiz/{seeded['course_id']}/submit",
                         json={'answers': [1, 1, 1, 1]})
    assert r.status_code == 200
    body = r.get_json()
    assert body['score'] == 4 and body['total'] == 4

    res = fresh_aluno.get(f"/api/progress/quiz/{seeded['course_id']}/resultado").get_json()
    assert res['percentage'] == 100


def test_fluxo_pergunta_resposta(fresh_aluno, app, seeded):
    cid = seeded['course_id']
    q = fresh_aluno.post(f'/api/questions/{cid}', json={'texto': 'Dúvida da aula 1?'}).get_json()

    # texto vazio é rejeitado
    assert fresh_aluno.post(f'/api/questions/{cid}', json={'texto': '  '}).status_code == 400

    # aluno NÃO pode responder
    r = fresh_aluno.post(f"/api/questions/{q['id']}/responder", json={'resposta': 'eu mesmo'})
    assert r.status_code == 403

    # tutor do curso responde; autor ganha 25 pts (question_answered) e notificação
    tutor_c = app.test_client()
    login(tutor_c, 'tutor@test.com')
    r = tutor_c.post(f"/api/questions/{q['id']}/responder", json={'resposta': 'Boa pergunta!'})
    assert r.status_code == 200
    assert r.get_json()['status'] == 'answered'

    minhas = fresh_aluno.get('/api/questions/me').get_json()
    respondida = next(x for x in minhas if x['id'] == q['id'])
    assert respondida['resposta'] == 'Boa pergunta!'

    notifs = fresh_aluno.get('/api/notifications').get_json()
    assert any('respondida' in n['title'].lower() for n in notifs['notifications'])
    assert notifs['unread_count'] >= 1

    # responder de novo não re-pontua o autor (só a 1ª resposta pontua)
    antes = fresh_aluno.get('/api/gamification/user-stats').get_json()['total_points']
    tutor_c.post(f"/api/questions/{q['id']}/responder", json={'resposta': 'Editando'})
    depois = fresh_aluno.get('/api/gamification/user-stats').get_json()['total_points']
    assert antes == depois


def test_dashboard_tutor_lista_perguntas(tutor):
    r = tutor.get('/api/questions/tutor/dashboard')
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_admin_dashboard(admin):
    assert admin.get('/api/admin/dashboard').status_code == 200


def test_admin_endpoints_negados_para_aluno(aluno):
    assert aluno.get('/api/admin/dashboard').status_code == 403
    assert aluno.get('/api/admin/users').status_code == 403
