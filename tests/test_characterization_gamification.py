"""J4 (estado atual): pontos, níveis, badges e conquistas."""


def test_user_stats_formato(fresh_aluno):
    r = fresh_aluno.get('/api/gamification/user-stats')
    assert r.status_code == 200
    body = r.get_json()
    for campo in ('total_points', 'current_level', 'points_in_level',
                  'badges_count', 'badges_unlocked', 'badges_locked'):
        assert campo in body
    # aluno novo: 5 pts do login diário, nível 1
    assert body['total_points'] == 5
    assert body['current_level'] == 1


def test_badges_listados_com_progresso(fresh_aluno):
    r = fresh_aluno.get('/api/gamification/badges')
    assert r.status_code == 200
    badges = r.get_json()
    assert len(badges) >= 8  # seed cria 12
    bloqueado = next(b for b in badges if not b['unlocked'])
    assert '/' in bloqueado['progress']  # formato "atual/alvo"


def test_add_points_desativado(fresh_aluno):
    """Rota legada não concede mais pontos (movidos para eventos do servidor)."""
    r = fresh_aluno.post('/api/gamification/add-points', json={'action': 'material_read'})
    assert r.status_code == 400


def test_nivel_sobe_a_cada_100_pontos(app, seeded):
    """CARACTERIZAÇÃO: calculate_level é linear (100 pts/nível, teto 7) e
    IGNORA a tabela Level do admin e os pontos configuráveis do
    PlatformConfig — três sistemas de nível concorrentes (docs/DEBITOS.md)."""
    from routes.gamification import calculate_level
    assert calculate_level(0) == (1, 0)
    assert calculate_level(99) == (1, 99)
    assert calculate_level(100) == (2, 0)
    assert calculate_level(650) == (7, 50)
    assert calculate_level(2000) == (7, 1400)  # points_in_level cresce sem teto


def test_pergunta_concede_pontos_e_conta_para_badge(fresh_aluno, seeded):
    r = fresh_aluno.post(f"/api/questions/{seeded['course_id']}",
                         json={'texto': 'Qual o sentido da vida?'})
    assert r.status_code == 201
    body = r.get_json()
    assert body['points']['points_awarded'] == 15

    badges = fresh_aluno.get('/api/gamification/badges').get_json()
    buscador = next(b for b in badges if b['code'] == 'buscador_verdade')
    assert buscador['progress'] == '1/5'


def test_config_gamificacao_exige_login(app, seeded, aluno):
    """CARACTERIZAÇÃO: /api/config/gamification exige autenticação (401 anônimo)."""
    anonimo = app.test_client()
    assert anonimo.get('/api/config/gamification').status_code == 401
    assert aluno.get('/api/config/gamification').status_code == 200
