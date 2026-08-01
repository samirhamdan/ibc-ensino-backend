"""J1/J4 (estado atual): fluxo linear de aulas — abertura, bloqueio, quiz,
pontos e certificado ao concluir o curso."""

RESPOSTAS_CERTAS = [1, 1]   # conftest: ans=1 em todas as questões
RESPOSTAS_ERRADAS = [0, 0]


def _submit(client, course_id, aula_num, answers):
    return client.post(f'/api/courses/{course_id}/aulas/{aula_num}/submit-quiz',
                       json={'answers': answers})


def test_lista_aulas_primeira_desbloqueada(fresh_aluno, seeded):
    r = fresh_aluno.get(f"/api/courses/{seeded['course_id']}/aulas")
    assert r.status_code == 200
    aulas = r.get_json()
    assert len(aulas) == 2
    assert aulas[0]['unlocked'] is True
    assert aulas[1]['unlocked'] is False


def test_abrir_aula_bloqueada_403(fresh_aluno, seeded):
    r = fresh_aluno.get(f"/api/courses/{seeded['course_id']}/aulas/2")
    assert r.status_code == 403


def test_submit_em_aula_bloqueada_403(fresh_aluno, seeded):
    r = _submit(fresh_aluno, seeded['course_id'], 2, RESPOSTAS_CERTAS)
    assert r.status_code == 403


def test_aula_inexistente_404(fresh_aluno, seeded):
    assert fresh_aluno.get(f"/api/courses/{seeded['course_id']}/aulas/99").status_code == 404


def test_aulas_de_curso_draft_404_para_aluno(fresh_aluno, seeded):
    assert fresh_aluno.get(f"/api/courses/{seeded['draft_course_id']}/aulas").status_code == 404


def test_abrir_aula_1_traz_quiz_sem_gabarito(fresh_aluno, seeded):
    r = fresh_aluno.get(f"/api/courses/{seeded['course_id']}/aulas/1")
    assert r.status_code == 200
    body = r.get_json()
    assert body['aula_num'] == 1
    assert body['total_aulas'] == 2
    assert len(body['quiz']) == 2
    assert all('ans' not in q for q in body['quiz'])


def test_reprovar_oculta_gabarito_e_nao_desbloqueia(fresh_aluno, seeded):
    r = _submit(fresh_aluno, seeded['course_id'], 1, RESPOSTAS_ERRADAS)
    assert r.status_code == 200
    body = r.get_json()
    assert body['passed'] is False
    assert body['next_unlocked'] is False
    # gabarito das erradas não é revelado ao reprovar
    erradas = [f for f in body['feedback'] if not f['is_correct']]
    assert erradas and all(f['correct_answer'] is None for f in erradas)
    # 1ª tentativa concede pontos de quiz_attempted (20)
    assert body['points']['points_awarded'] == 20


def test_jornada_completa_ate_certificado(fresh_aluno, seeded):
    cid = seeded['course_id']

    # aula 1: reprova (20 pts de tentativa), depois passa (15 pts repescagem)
    assert _submit(fresh_aluno, cid, 1, RESPOSTAS_ERRADAS).get_json()['passed'] is False
    r1 = _submit(fresh_aluno, cid, 1, RESPOSTAS_CERTAS).get_json()
    assert r1['passed'] is True
    assert r1['next_unlocked'] is True
    assert r1['points']['points_awarded'] == 15
    # ao passar, o gabarito completo é visível
    assert all(f['correct_answer'] is not None for f in r1['feedback'])

    # re-submeter aula já passada não re-pontua
    assert _submit(fresh_aluno, cid, 1, RESPOSTAS_CERTAS).get_json()['points'] is None

    # aula 2 agora abre
    assert fresh_aluno.get(f'/api/courses/{cid}/aulas/2').status_code == 200

    # next-lesson aponta para a aula 2
    nl = fresh_aluno.get(f'/api/courses/{cid}/next-lesson').get_json()
    assert nl['has_next'] is True
    assert nl['lesson_count'] == {'current': 2, 'total': 2}

    # aula 2 passa de primeira: 20 (tentativa) + 30 (1ª aprovação) + 100
    # (curso concluído) e certificado emitido
    r2 = _submit(fresh_aluno, cid, 2, RESPOSTAS_CERTAS).get_json()
    assert r2['passed'] is True
    assert r2['is_last_lesson'] is True
    assert r2['certificate_issued'] is True
    assert r2['cert_code']
    assert r2['points']['points_awarded'] == 20 + 30 + 100

    # certificado aparece em /certificates/my e valida publicamente
    my = fresh_aluno.get('/api/certificates/my').get_json()
    codes = [c['cert_code'] for c in my]
    assert r2['cert_code'] in codes
    v = fresh_aluno.get(f"/api/certificates/verify/{r2['cert_code']}")
    assert v.status_code == 200

    # concluir de novo não emite segundo certificado
    r3 = _submit(fresh_aluno, cid, 2, RESPOSTAS_CERTAS).get_json()
    assert r3['certificate_issued'] is False


def test_issue_manual_exige_conclusao(fresh_aluno, seeded):
    r = fresh_aluno.post('/api/certificates/issue',
                         json={'cert_type': 'course', 'entity_id': seeded['course_id']})
    assert r.status_code == 403  # curso não concluído por este aluno
