"""
Fixtures da suíte de caracterização (Fase 1 do playbook 0.9).

Estes testes documentam o comportamento ATUAL do sistema — inclusive
comportamentos estranhos (registrados em docs/DEBITOS.md, nunca "corrigidos"
por aqui). Banco real via SQLAlchemy (sem mock de ORM): SQLite local por
padrão; o CI aponta TEST_DATABASE_URL para um Postgres de serviço.
"""
import os
import tempfile

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret-key')


@pytest.fixture(scope='session')
def app():
    # Banco isolado por sessão de teste
    test_db_url = os.getenv('TEST_DATABASE_URL')
    if not test_db_url:
        fd, path = tempfile.mkstemp(suffix='.db', prefix='ibc_test_')
        os.close(fd)
        test_db_url = f'sqlite:///{path}'
    os.environ['DATABASE_URL'] = test_db_url

    from app import create_app
    application = create_app('development')
    application.config['TESTING'] = True
    # Sem isso, o limite de 10 logins/min (Flask-Limiter) derruba a suíte,
    # que autentica dezenas de vezes — 429 mascarando o comportamento real.
    # (Direto na extensão: o config RATELIMIT_ENABLED só é lido no init_app.)
    from extensions import limiter
    limiter.enabled = False

    with application.app_context():
        from extensions import db
        from seed import seed_config, seed_levels, seed_badges, seed_achievements, seed_tenants
        db.create_all()
        seed_tenants()   # PRIMEIRO: badges/achievements são por tenant
        seed_config()
        seed_levels()
        seed_badges()
        seed_achievements()
        db.session.commit()

    yield application


@pytest.fixture(scope='session')
def seeded(app):
    """Dados mínimos das jornadas: usuários, curso com 2 aulas + quiz, trilha."""
    with app.app_context():
        from extensions import db
        from models import User, Course, Module, Quiz, Trail, TrailCourse, Category

        cat = Category(name='Teologia')
        db.session.add(cat)
        db.session.flush()

        from core.tenancy import Tenant, TenantUser, default_tenant_id
        tenant_padrao = Tenant.query.get(default_tenant_id())

        users = {}
        for name, email, role in [('Admin', 'admin@test.com', 'admin'),
                                  ('Tutor', 'tutor@test.com', 'tutor'),
                                  ('Aluno', 'aluno@test.com', 'aluno')]:
            u = User(name=name, email=email, role=role)
            u.set_password('senha123')
            db.session.add(u)
            db.session.flush()
            users[role] = u.id
            # Espelha a migração 0013: todo usuário pré-existente ganha
            # vínculo no tenant padrão com o papel global — sem isto, os
            # helpers escopados (usuarios_do_tenant_query/
            # get_user_scoped_or_404) não enxergam usuários criados
            # diretamente no banco (só quem loga pelo menos uma vez).
            db.session.add(TenantUser(tenant_id=tenant_padrao.id, user_id=u.id, papel=role))

        course = Course(name='Curso Caracterização', acesso='publico',
                        resumo='Curso usado pelos testes', category_id=cat.id,
                        tutor_id=users['tutor'], status='published')
        db.session.add(course)
        db.session.flush()

        m1 = Module(course_id=course.id, nome='Aula 1', position=0)
        m2 = Module(course_id=course.id, nome='Aula 2', position=1)
        db.session.add_all([m1, m2])
        db.session.flush()
        # Quiz de 2 questões por aula; resposta correta é sempre o índice 1
        for m in (m1, m2):
            for i in range(2):
                db.session.add(Quiz(course_id=course.id, module_id=m.id, position=i,
                                    q=f'Pergunta {i+1} da {m.nome}?',
                                    opts=['errada', 'certa', 'errada'], ans=1,
                                    exp='Explicação de teste'))

        trail = Trail(name='Trilha Caracterização', goal='teologia', xp_bonus=100)
        db.session.add(trail)
        db.session.flush()
        db.session.add(TrailCourse(trail_id=trail.id, course_id=course.id, position=0))

        draft = Course(name='Curso Rascunho', acesso='publico', status='draft')
        db.session.add(draft)
        db.session.commit()

        return {
            'course_id': course.id,
            'draft_course_id': draft.id,
            'trail_id': trail.id,
            'module1_id': m1.id,
            'module2_id': m2.id,
            'users': users,
        }


@pytest.fixture()
def client(app, seeded):
    return app.test_client()


def login(client, email, password='senha123'):
    return client.post('/api/auth/login', json={'email': email, 'password': password})


@pytest.fixture()
def aluno(client):
    login(client, 'aluno@test.com')
    return client


@pytest.fixture()
def admin(client):
    login(client, 'admin@test.com')
    return client


@pytest.fixture()
def tutor(client):
    login(client, 'tutor@test.com')
    return client


_counter = {'n': 0}


@pytest.fixture()
def fresh_aluno(app, seeded):
    """Cliente autenticado como um aluno NOVO (progresso zerado) por teste —
    jornadas que acumulam pontos/progresso não podem compartilhar usuário."""
    _counter['n'] += 1
    email = f'fresh{_counter["n"]}@test.com'
    c = app.test_client()
    r = c.post('/api/auth/register', json={
        'name': 'Aluno Fresco', 'email': email,
        'password': 'senha123', 'confirm_password': 'senha123',
    })
    assert r.status_code == 201, r.get_json()
    login(c, email)
    return c
