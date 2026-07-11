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
