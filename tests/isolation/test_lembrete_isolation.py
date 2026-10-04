"""Lembrete aos alunos inativos (dashboard admin v2): só atinge alunos do
próprio tenant e não repete em 24h."""
from tests.isolation.conftest import TenantClient, HOST_A
from tests.isolation.test_credenciais_globais import usuario_admin_em_ab  # noqa: F401


def test_lembrete_so_notifica_alunos_do_proprio_tenant(iso_app, usuario_admin_em_ab):  # noqa: F811
    from extensions import db
    from models import User, Notification
    from core.tenancy import Tenant, TenantUser
    with iso_app.app_context():
        b = Tenant.query.filter_by(slug='demo').first()
        so_b = User.query.filter_by(email='so-b@test.com').first()
        if not so_b:
            so_b = User(name='Aluno Só B', email='so-b@test.com', role='aluno'); so_b.set_password('senha123')
            db.session.add(so_b); db.session.flush()
            db.session.add(TenantUser(tenant_id=b.id, user_id=so_b.id, papel='aluno'))
            db.session.commit()
        so_b_id = so_b.id
        aluno_a = User.query.filter_by(email='aluno@test.com').first().id
        Notification.query.filter_by(type='lembrete').delete(); db.session.commit()

    a = TenantClient(iso_app.test_client(), HOST_A)
    assert a.post('/api/auth/login', json={'email': 'admin@test.com', 'password': 'senha123'}).status_code == 200
    r = a.post('/api/admin/lembrete-inativos')
    assert r.status_code == 200 and r.get_json()['enviados'] >= 1

    with iso_app.app_context():
        assert Notification.query.filter_by(type='lembrete', user_id=aluno_a).count() == 1
        assert Notification.query.filter_by(type='lembrete', user_id=so_b_id).count() == 0

    # 2ª chamada no mesmo dia não duplica
    assert a.post('/api/admin/lembrete-inativos').get_json()['enviados'] == 0
    with iso_app.app_context():
        assert Notification.query.filter_by(type='lembrete', user_id=aluno_a).count() == 1


def test_fila_traz_titulo_descricao_e_acoes(iso_app, usuario_admin_em_ab):  # noqa: F811
    a = TenantClient(iso_app.test_client(), HOST_A)
    a.post('/api/auth/login', json={'email': 'admin@test.com', 'password': 'senha123'})
    alerts = a.get('/api/admin/dashboard').get_json()['alerts']
    inat = next(x for x in alerts if x['type'] == 'inactivity')
    assert inat['titulo'] and inat['descricao']
    assert inat['acoes'][0]['acao'] == 'lembrete_inativos'


def test_aluno_nao_dispara_lembrete(client, aluno):
    assert aluno.post('/api/admin/lembrete-inativos').status_code == 403
