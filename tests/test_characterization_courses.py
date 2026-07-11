"""J-catálogo: listagem de cursos/trilhas e visibilidade por papel."""


def test_aluno_ve_apenas_publicados(aluno, seeded):
    r = aluno.get('/api/courses')
    assert r.status_code == 200
    ids = [c['id'] for c in r.get_json()]
    assert seeded['course_id'] in ids
    assert seeded['draft_course_id'] not in ids


def test_staff_ve_rascunhos(admin, seeded):
    ids = [c['id'] for c in admin.get('/api/courses').get_json()]
    assert seeded['draft_course_id'] in ids


def test_anonimo_lista_publicados(client, seeded):
    """Comportamento atual: catálogo é público (sem autenticação)."""
    r = client.get('/api/courses')
    assert r.status_code == 200
    ids = [c['id'] for c in r.get_json()]
    assert seeded['course_id'] in ids


def test_detalhe_curso_com_modulos_e_quiz_sem_gabarito(aluno, seeded):
    r = aluno.get(f"/api/courses/{seeded['course_id']}")
    assert r.status_code == 200
    body = r.get_json()
    assert len(body['modules']) == 2
    assert len(body['quiz']) == 4
    # gabarito nunca vai ao cliente na listagem
    assert all('ans' not in q for q in body['quiz'])


def test_detalhe_curso_draft_404_para_aluno(aluno, seeded):
    assert aluno.get(f"/api/courses/{seeded['draft_course_id']}").status_code == 404


def test_trilhas_listadas_com_cursos(aluno, seeded):
    r = aluno.get('/api/trails')
    assert r.status_code == 200
    trilha = next(t for t in r.get_json() if t['id'] == seeded['trail_id'])
    assert trilha['name'] == 'Trilha Caracterização'


def test_categorias(aluno):
    r = aluno.get('/api/courses/categories')
    assert r.status_code == 200
    assert any(c['name'] == 'Teologia' for c in r.get_json())


def test_dashboard_aluno_carrega(aluno):
    r = aluno.get('/api/aluno/dashboard')
    assert r.status_code == 200


def test_spa_servida_na_raiz(client):
    r = client.get('/')
    assert r.status_code == 200
    assert b'<!DOCTYPE html>' in r.data or b'<html' in r.data
