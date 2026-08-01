"""Smoke das jornadas do aluno real do IBC — Fase 5 do playbook 0.9.

`pytest -m smoke` roda SÓ este arquivo, e é o que scripts/rehearsal.sh
executa contra o staging depois do `alembic upgrade head` cronometrado
(playbook §5.3). Cada teste é uma jornada ponta a ponta pela API, não uma
regra isolada — a suíte de caracterização/isolamento já cobre as regras;
aqui o objetivo é "a plataforma inteira, do jeito que o aluno usa, não
quebrou depois da migração".
"""
import pytest

pytestmark = pytest.mark.smoke


def test_jornada_login(fresh_aluno):
    """1) Login: sessão criada, /api/auth/user devolve o perfil."""
    r = fresh_aluno.get('/api/auth/user')
    assert r.status_code == 200
    assert r.get_json()['email'].startswith('fresh')


def test_jornada_catalogo_e_curso(fresh_aluno, seeded):
    """2) Catálogo: lista cursos publicados e abre o detalhe de um deles."""
    cid = seeded['course_id']
    r = fresh_aluno.get('/api/courses')
    assert r.status_code == 200
    assert any(c['id'] == cid for c in r.get_json())

    r = fresh_aluno.get(f'/api/courses/{cid}')
    assert r.status_code == 200
    assert r.get_json()['id'] == cid


def test_jornada_aula_e_quiz(fresh_aluno, seeded):
    """3) Aula: abre a aula 1, responde o quiz da aula e evolui o progresso."""
    cid = seeded['course_id']
    r = fresh_aluno.get(f'/api/courses/{cid}/aulas')
    assert r.status_code == 200
    aulas = r.get_json()
    assert len(aulas) >= 1

    r = fresh_aluno.get(f'/api/courses/{cid}/aulas/1')
    assert r.status_code == 200

    r = fresh_aluno.post(f'/api/courses/{cid}/aulas/1/submit-quiz',
                         json={'answers': [1, 1]})
    assert r.status_code == 200
    assert r.get_json()['score'] >= 0


def test_jornada_gamificacao(fresh_aluno):
    """4) Hábito: pontos e badges respondem sem erro (mantém o engajamento)."""
    r = fresh_aluno.get('/api/gamification/user-stats')
    assert r.status_code == 200
    assert 'total_points' in r.get_json()

    r = fresh_aluno.get('/api/gamification/badges')
    assert r.status_code == 200


def test_jornada_dashboard_do_aluno(fresh_aluno):
    """5) Painel: o aluno enxerga o próprio progresso consolidado."""
    r = fresh_aluno.get('/api/aluno/dashboard')
    assert r.status_code == 200
