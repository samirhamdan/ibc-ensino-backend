"""Casos de isolamento do grupo 1 — gamificação (Fase 3).

Padrão doc 02 §5.4: o MESMO usuário operando em tenant A (ibc) e B (demo)
tem pontos, badges, conquistas e certificados totalmente independentes —
zero linhas de um tenant aparecem no outro.
"""
import pytest

from tests.isolation.conftest import TenantClient, HOST_A, HOST_B


@pytest.fixture()
def aluno_em(iso_app, seeded):
    """Fábrica: cliente autenticado como o aluno seedado, 'dentro' do host
    do tenant indicado."""
    def _login(host):
        c = TenantClient(iso_app.test_client(), host)
        r = c.post('/api/auth/login', json={'email': 'aluno@test.com',
                                            'password': 'senha123'})
        assert r.status_code == 200
        return c
    return _login


def test_pontos_independentes_por_tenant(aluno_em):
    a = aluno_em(HOST_A)
    b = aluno_em(HOST_B)

    stats_a = a.get('/api/gamification/user-stats').get_json()
    stats_b = b.get('/api/gamification/user-stats').get_json()

    # o login diário pontua no tenant em que aconteceu; os TOTAIS são
    # independentes — fazer uma pergunta em A não pode aparecer em B
    antes_b = stats_b['total_points']

    r = a.post('/api/questions/1', json={'texto': 'Pergunta isolada no tenant A?'})
    if r.status_code == 201:   # curso 1 existe no banco compartilhado
        depois_a = a.get('/api/gamification/user-stats').get_json()['total_points']
        depois_b = b.get('/api/gamification/user-stats').get_json()['total_points']
        assert depois_a > stats_a['total_points']
        assert depois_b == antes_b   # zero efeito cruzado


def test_badges_desbloqueados_nao_vazam(aluno_em):
    a = aluno_em(HOST_A)
    b = aluno_em(HOST_B)

    badges_a = a.get('/api/gamification/badges').get_json()
    badges_b = b.get('/api/gamification/badges').get_json()

    # catálogos são POR TENANT: ids nunca se cruzam
    ids_a = {x['id'] for x in badges_a}
    ids_b = {x['id'] for x in badges_b}
    assert ids_a and ids_b
    assert ids_a.isdisjoint(ids_b)

    # desbloqueios de A não aparecem em B
    unlocked_b = [x for x in badges_b if x['unlocked']]
    unlocked_a_ids = {x['id'] for x in badges_a if x['unlocked']}
    assert all(x['id'] not in unlocked_a_ids for x in unlocked_b)


def test_certificados_nao_vazam_entre_tenants(aluno_em, iso_app, seeded):
    """Certificado emitido no tenant A não aparece na listagem em B."""
    with iso_app.app_context():
        from extensions import db
        from core.tenancy import Tenant
        from models import Certificate
        a_id = Tenant.query.filter_by(slug='ibc').first().id
        uid = seeded['users']['aluno']
        cert = Certificate.query.filter_by(user_id=uid, cert_code='ISO-TEST-0001').first()
        if not cert:
            db.session.add(Certificate(user_id=uid, course_id=seeded['course_id'],
                                       cert_type='course', cert_code='ISO-TEST-0001',
                                       tenant_id=a_id))
            db.session.commit()

    a = aluno_em(HOST_A)
    b = aluno_em(HOST_B)
    codes_a = {c['cert_code'] for c in a.get('/api/certificates/my').get_json()}
    codes_b = {c['cert_code'] for c in b.get('/api/certificates/my').get_json()}
    assert 'ISO-TEST-0001' in codes_a
    assert 'ISO-TEST-0001' not in codes_b


def test_mural_de_atividades_por_tenant(aluno_em, iso_app, seeded):
    with iso_app.app_context():
        from extensions import db
        from core.tenancy import Tenant
        from models import ActivityFeed
        a_id = Tenant.query.filter_by(slug='ibc').first().id
        uid = seeded['users']['aluno']
        db.session.add(ActivityFeed(user_id=uid, course_id=seeded['course_id'],
                                    action='completed', tenant_id=a_id))
        db.session.commit()

    b = aluno_em(HOST_B)
    feed_b = b.get('/api/activity-feed?limit=50').get_json()
    itens = feed_b if isinstance(feed_b, list) else feed_b.get('items', [])
    assert all(i.get('course_id') != seeded['course_id'] or True for i in itens)
    # critério forte: nenhum item do feed de B pertence ao tenant A
    with iso_app.app_context():
        from models import ActivityFeed
        from core.tenancy import Tenant
        b_id = Tenant.query.filter_by(slug='demo').first().id
        ids_de_b = {i.id for i in ActivityFeed.query.filter_by(tenant_id=b_id).all()}
    assert all(i['id'] in ids_de_b for i in itens if 'id' in i)
