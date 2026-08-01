"""Casos de isolamento do grupo 3 — conteúdo (Fase 3, fecha TEN-01).

Catálogo, cursos, aulas, trilhas, perguntas, notificações e avisos são POR
TENANT: conteúdo criado em A não existe em B — nem por listagem, nem por ID
direto (404, nunca 403 — não revelar existência).
"""
import pytest

from tests.isolation.conftest import TenantClient, HOST_A, HOST_B


@pytest.fixture()
def usuario_em(iso_app, vinculo_b):
    def _login(host, email, password='senha123'):
        c = TenantClient(iso_app.test_client(), host)
        r = c.post('/api/auth/login', json={'email': email, 'password': password})
        assert r.status_code == 200
        return c
    return _login


@pytest.fixture()
def curso_em_b(iso_app):
    """Curso publicado que pertence ao tenant B (demo)."""
    with iso_app.app_context():
        from extensions import db
        from core.tenancy import Tenant
        from models import Course
        b_id = Tenant.query.filter_by(slug='demo').first().id
        curso = Course.query.filter_by(tenant_id=b_id, name='Curso do Demo').first()
        if not curso:
            curso = Course(name='Curso do Demo', acesso='publico',
                           status='published', tenant_id=b_id)
            db.session.add(curso)
            db.session.commit()
        return curso.id


def test_catalogo_por_tenant(usuario_em, seeded, curso_em_b):
    """Listagem: o catálogo de A não contém cursos de B e vice-versa."""
    a = usuario_em(HOST_A, 'aluno@test.com')
    b = usuario_em(HOST_B, 'aluno@test.com')

    ids_a = {c['id'] for c in a.get('/api/courses').get_json()}
    ids_b = {c['id'] for c in b.get('/api/courses').get_json()}

    assert seeded['course_id'] in ids_a
    assert curso_em_b not in ids_a          # zero linhas de B no catálogo de A
    assert curso_em_b in ids_b
    assert seeded['course_id'] not in ids_b


def test_curso_de_outro_tenant_404_por_id_direto(usuario_em, seeded, curso_em_b):
    """ID direto: recurso de B responde 404 em A (nunca 403) — inclusive
    para admin, cujo poder é limitado ao próprio tenant."""
    a_aluno = usuario_em(HOST_A, 'aluno@test.com')
    a_admin = usuario_em(HOST_A, 'admin@test.com')

    assert a_aluno.get(f'/api/courses/{curso_em_b}').status_code == 404
    assert a_admin.get(f'/api/courses/{curso_em_b}').status_code == 404
    # escrita também: editar/apagar curso de B a partir de A → 404
    assert a_admin.put(f'/api/courses/{curso_em_b}',
                       json={'name': 'hackeado'}).status_code == 404
    assert a_admin.delete(f'/api/courses/{curso_em_b}').status_code == 404


def test_trilhas_por_tenant(usuario_em, seeded):
    b = usuario_em(HOST_B, 'aluno@test.com')
    ids_b = {t['id'] for t in b.get('/api/trails').get_json()}
    assert seeded['trail_id'] not in ids_b   # trilha do ibc invisível em B


def test_perguntas_por_tenant(usuario_em, iso_app, seeded):
    """Pergunta feita em A não aparece nas listagens de B."""
    a = usuario_em(HOST_A, 'aluno@test.com')
    b = usuario_em(HOST_B, 'aluno@test.com')

    q = a.post(f"/api/questions/{seeded['course_id']}",
               json={'texto': 'Pergunta isolada de conteúdo?'})
    assert q.status_code == 201

    minhas_b = b.get('/api/questions/me').get_json()
    assert all('isolada de conteúdo' not in x['texto'] for x in minhas_b)

    # por ID de curso: o curso de A nem existe em B
    assert b.get(f"/api/questions/{seeded['course_id']}").status_code == 404


def test_notificacoes_por_tenant(usuario_em, iso_app, seeded):
    """Notificação criada em A não aparece em B para o MESMO usuário."""
    with iso_app.app_context():
        from extensions import db
        from core.tenancy import Tenant
        from models import Notification
        a_id = Tenant.query.filter_by(slug='ibc').first().id
        db.session.add(Notification(user_id=seeded['users']['aluno'],
                                    title='Aviso isolado', message='só no ibc',
                                    tenant_id=a_id))
        db.session.commit()

    a = usuario_em(HOST_A, 'aluno@test.com')
    b = usuario_em(HOST_B, 'aluno@test.com')
    titulos_a = {n['title'] for n in a.get('/api/notifications').get_json()['notifications']}
    titulos_b = {n['title'] for n in b.get('/api/notifications').get_json()['notifications']}
    assert 'Aviso isolado' in titulos_a
    assert 'Aviso isolado' not in titulos_b


def test_avisos_ativos_por_tenant(usuario_em, iso_app, seeded):
    """Announcement de A não aparece nos avisos ativos de B."""
    with iso_app.app_context():
        from extensions import db
        from core.tenancy import Tenant
        from models import Announcement
        a_id = Tenant.query.filter_by(slug='ibc').first().id
        if not Announcement.query.filter_by(title='Anúncio do IBC', tenant_id=a_id).first():
            db.session.add(Announcement(title='Anúncio do IBC', message='olá ibc',
                                        created_by=seeded['users']['admin'],
                                        tenant_id=a_id))
            db.session.commit()

    b = usuario_em(HOST_B, 'aluno@test.com')
    ativos_b = b.get('/api/announcements/active').get_json()
    itens = ativos_b if isinstance(ativos_b, list) else ativos_b.get('announcements', [])
    assert all(x.get('title') != 'Anúncio do IBC' for x in itens)
