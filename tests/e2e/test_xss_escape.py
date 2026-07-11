"""ROADMAP.md §2.1 — XSS armazenado: não existia nenhum escapeHtml() na
base, então nome de usuário/curso/pergunta/resposta controlado por
qualquer papel (aluno, tutor, admin) executava script na sessão de quem
visse aquele dado renderizado. index.html::escapeHtml() cobre os pontos
de maior risco (nome de curso/trilha/usuário, texto de pergunta/resposta,
feed de atividade, notificações/avisos).

Prova ponta a ponta com um payload real, não só que a função existe.
"""
import os
import threading
import time

import pytest

pytest.importorskip('playwright')
from playwright.sync_api import sync_playwright  # noqa: E402

_CHROMIUM_PATH = os.getenv('PLAYWRIGHT_CHROMIUM_PATH', '/opt/pw-browsers/chromium')
pytestmark = pytest.mark.skipif(
    not os.path.exists(_CHROMIUM_PATH),
    reason=f'Chromium não encontrado em {_CHROMIUM_PATH} (defina PLAYWRIGHT_CHROMIUM_PATH ou rode `playwright install chromium`)')

_PAYLOAD = '<script>window.__xss_executou = true</script>'


@pytest.fixture(scope='module')
def servidor_vivo(app):
    import socket
    from werkzeug.serving import make_server

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    porta = sock.getsockname()[1]
    sock.close()

    servidor = make_server('127.0.0.1', porta, app, threaded=True)
    t = threading.Thread(target=servidor.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    yield f'http://127.0.0.1:{porta}'
    servidor.shutdown()
    t.join(timeout=5)


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=_CHROMIUM_PATH)
        yield b
        b.close()


@pytest.fixture()
def curso_malicioso(app, seeded):
    """Curso com nome contendo um payload de script — reproduz o cenário
    real (tutor/admin cria o curso, aluno vê o catálogo)."""
    from extensions import db
    from models import Course, Category
    from core.tenancy import default_tenant_id
    with app.app_context():
        cat = Category.query.filter_by(tenant_id=default_tenant_id()).first()
        c = Course(name=_PAYLOAD, acesso='publico', status='published',
                  category_id=cat.id, icon='📚', tenant_id=default_tenant_id())
        db.session.add(c)
        db.session.commit()
        cid = c.id
    yield cid
    with app.app_context():
        from models import Course
        Course.query.filter_by(id=cid).delete()
        db.session.commit()


def test_nome_de_curso_malicioso_nao_executa_script_no_catalogo(
        app, servidor_vivo, browser, seeded, curso_malicioso):
    page = browser.new_page(viewport={'width': 1280, 'height': 900})
    dialogs = []
    page.on('dialog', lambda d: (dialogs.append(d.message), d.dismiss()))

    page.goto(servidor_vivo + '/')
    page.fill('#login-email', 'aluno@test.com')
    page.fill('#login-pass', 'senha123')
    page.press('#login-pass', 'Enter')
    page.wait_for_timeout(1500)
    page.evaluate("""
      try { closeOnboardingModal(); } catch(e) {}
      document.querySelectorAll('.modal,[id*=modal],.onboarding-modal').forEach(m=>m.remove());
    """)
    page.evaluate('showCatalog()')
    page.wait_for_selector('.course-card-v2-title', timeout=8000)

    executou = page.evaluate('window.__xss_executou === true')
    assert not executou, 'o payload de <script> executou — XSS ainda ativo'
    assert not dialogs, f'alert()/confirm() disparado pelo payload: {dialogs}'

    html = page.evaluate("document.getElementById('main-content').innerHTML")
    assert '<script>window.__xss_executou' not in html, \
        'a tag <script> apareceu LITERAL no DOM (não escapada)'
    assert '&lt;script&gt;' in html, \
        'o nome do curso deveria aparecer como texto escapado na página'

    page.close()


@pytest.fixture()
def certificado_malicioso(app, seeded):
    """Certificado emitido para um usuário com nome contendo um payload —
    reproduz o achado CRÍTICO da revisão (Fable 5): a página PÚBLICA de
    verificação (sem login) renderizava student_name sem escape."""
    from extensions import db
    from models import User, Certificate
    from core.tenancy import default_tenant_id, TenantUser
    with app.app_context():
        tid = default_tenant_id()
        u = User(name=_PAYLOAD, email='cert-xss@test.com', role='aluno')
        u.set_password('senha123')
        db.session.add(u)
        db.session.flush()
        db.session.add(TenantUser(tenant_id=tid, user_id=u.id, papel='aluno'))
        cert = Certificate(user_id=u.id, course_id=seeded['course_id'], cert_type='course',
                           cert_code='XSSPROOF001', tenant_id=tid)
        db.session.add(cert)
        db.session.commit()
        uid = u.id
    yield 'XSSPROOF001'
    with app.app_context():
        from models import User, Certificate
        from core.tenancy import TenantUser
        Certificate.query.filter_by(cert_code='XSSPROOF001').delete()
        TenantUser.query.filter_by(user_id=uid).delete()
        User.query.filter_by(id=uid).delete()
        db.session.commit()


def test_nome_malicioso_na_verificacao_publica_de_certificado(
        app, servidor_vivo, browser, seeded, certificado_malicioso):
    """Rota pública (#verificar/<code>), sem login — o pior caso: qualquer
    visitante não-autenticado que abra o link de verificação é quem
    executaria o payload."""
    page = browser.new_page(viewport={'width': 1280, 'height': 900})
    dialogs = []
    page.on('dialog', lambda d: (dialogs.append(d.message), d.dismiss()))

    page.goto(f'{servidor_vivo}/#verificar/{certificado_malicioso}')
    page.wait_for_timeout(1500)

    executou = page.evaluate('window.__xss_executou === true')
    assert not executou, 'o payload de <script> executou na página PÚBLICA de verificação'
    assert not dialogs, f'alert()/confirm() disparado: {dialogs}'

    html = page.evaluate("document.body.innerHTML")
    assert '<script>window.__xss_executou' not in html
    assert '&lt;script&gt;' in html

    page.close()


def test_nome_com_aspas_simples_nao_escapa_do_onclick_no_painel_admin(
        app, servidor_vivo, browser, seeded):
    """Achado CRÍTICO da revisão: escapeHtml() sozinho dentro de
    onclick="fn('${...}')" NÃO impede quebra de string JS — o navegador
    decodifica entidades HTML (&#39; → ') antes do JS rodar. jsAttr()
    (JSON.stringify + escapeHtml, aspas simples no atributo) fecha isso.
    Um nome como `x'); window.__onclick_xss_executou=true; //` prova que
    o clique não executa nada além da função esperada."""
    from extensions import db
    from models import User
    from core.tenancy import default_tenant_id, TenantUser

    nome_malicioso = "x'); window.__onclick_xss_executou=true; //"
    with app.app_context():
        tid = default_tenant_id()
        u = User(name=nome_malicioso, email='onclick-xss@test.com', role='aluno')
        u.set_password('senha123')
        db.session.add(u)
        db.session.flush()
        db.session.add(TenantUser(tenant_id=tid, user_id=u.id, papel='aluno'))
        db.session.commit()
        uid = u.id

    try:
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        dialogs = []
        page.on('dialog', lambda d: (dialogs.append(d.message), d.dismiss()))

        page.goto(servidor_vivo + '/')
        page.fill('#login-email', 'admin@test.com')
        page.fill('#login-pass', 'senha123')
        page.press('#login-pass', 'Enter')
        page.wait_for_timeout(1500)
        page.evaluate("""
          try { closeOnboardingModal(); } catch(e) {}
          document.querySelectorAll('.modal,[id*=modal],.onboarding-modal').forEach(m=>m.remove());
        """)
        page.evaluate("showAdminPanel('users')")
        page.wait_for_timeout(800)
        page.evaluate(f'openUserProfile({uid})')
        page.wait_for_selector('.profile-actions', timeout=8000)

        executou = page.evaluate('window.__onclick_xss_executou === true')
        assert not executou, 'o payload quebrou pra fora da string JS do onclick — breakout ainda ativo'
        assert not dialogs, f'alert()/confirm() disparado: {dialogs}'

        page.close()
    finally:
        with app.app_context():
            from models import User
            from core.tenancy import TenantUser
            TenantUser.query.filter_by(user_id=uid).delete()
            User.query.filter_by(id=uid).delete()
            db.session.commit()
