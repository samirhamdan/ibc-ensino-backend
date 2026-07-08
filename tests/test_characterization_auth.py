"""J-auth: login, sessão, logout, registro — comportamento atual."""
from tests.conftest import login


def test_login_ok_retorna_usuario(client):
    r = login(client, 'aluno@test.com')
    assert r.status_code == 200
    body = r.get_json()
    assert body['email'] == 'aluno@test.com'
    assert body['role'] == 'aluno'
    # login devolve conquistas novas (pode ser lista vazia)
    assert 'new_achievements' in body


def test_login_senha_errada_401(client):
    r = client.post('/api/auth/login', json={'email': 'aluno@test.com', 'password': 'errada'})
    assert r.status_code == 401


def test_login_email_inexistente_401(client):
    r = client.post('/api/auth/login', json={'email': 'nao@existe.com', 'password': 'x'})
    assert r.status_code == 401


def test_login_sem_campos_400(client):
    assert client.post('/api/auth/login', json={}).status_code == 400


def test_sessao_e_logout(aluno):
    r = aluno.get('/api/auth/user')
    assert r.status_code == 200
    assert r.get_json()['email'] == 'aluno@test.com'

    assert aluno.post('/api/auth/logout').status_code == 200
    assert aluno.get('/api/auth/user').status_code == 401


def test_alias_api_user(aluno):
    """/api/user é alias de /api/auth/user."""
    assert aluno.get('/api/user').status_code == 200


def test_registro_validacoes(client):
    base = {'name': 'Nome Válido', 'email': 'novo@test.com',
            'password': 'senha123', 'confirm_password': 'senha123'}
    assert client.post('/api/auth/register', json={**base, 'name': 'ab'}).status_code == 400
    assert client.post('/api/auth/register', json={**base, 'email': 'seminvalido'}).status_code == 400
    assert client.post('/api/auth/register', json={**base, 'password': '123', 'confirm_password': '123'}).status_code == 400
    assert client.post('/api/auth/register', json={**base, 'confirm_password': 'outra'}).status_code == 400
    # e-mail duplicado
    assert client.post('/api/auth/register', json={**base, 'email': 'aluno@test.com'}).status_code == 400


def test_login_diario_concede_5_pontos_uma_vez(fresh_aluno):
    """daily_login: +5 XP no primeiro login do dia; re-login não duplica."""
    r = fresh_aluno.get('/api/gamification/user-stats')
    pontos = r.get_json()['total_points']
    assert pontos == 5

    login(fresh_aluno, fresh_aluno.get('/api/auth/user').get_json()['email'])
    assert fresh_aluno.get('/api/gamification/user-stats').get_json()['total_points'] == 5
