"""E2E da Etapa 2 (UX_ALUNO_SAAS.md §6): "abrir dashboard → continuar
lição" no navegador de verdade — os testes de API já provam que os dados
estão certos; isto prova que a estrutura de 5 grupos renderiza e a jornada
funciona ponta a ponta, como o critério de aceite pede.

Playwright NÃO é dependência do projeto (requirements.txt) — este módulo
inteiro pula (não falha) se ele não estiver instalado, para não impor uma
dependência nova a quem só quer rodar `pytest`. Roda de verdade neste
ambiente (Chromium pré-instalado) e em qualquer CI que optar por instalar
`playwright` + `playwright install chromium`.
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


@pytest.fixture(scope='module')
def servidor_vivo(app):
    """Sobe a app de teste (mesmo banco/fixtures da suíte) num thread real,
    porta livre do SO — Playwright precisa de um servidor HTTP de verdade,
    não do test client do Flask."""
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


def test_jornada_abrir_dashboard_e_continuar_licao(servidor_vivo, browser, seeded):
    """Critério de aceite da Etapa 2: um aluno com progresso em andamento
    abre o dashboard e vê a estrutura de 5 grupos com o card de 'continuar'
    correto — sem erro de console, sem tela branca."""
    page = browser.new_page(viewport={'width': 1280, 'height': 900})
    erros_console = []
    page.on('console', lambda m: erros_console.append(m.text) if m.type == 'error' else None)

    page.goto(servidor_vivo + '/')
    page.fill('#login-email', 'aluno@test.com')
    page.fill('#login-pass', 'senha123')
    page.press('#login-pass', 'Enter')
    page.wait_for_selector('#dash-saas-continuar', timeout=8000)

    # os 5 grupos existem no DOM
    for grupo_id in ('dash-saas-saudacao', 'dash-saas-continuar', 'dash-saas-pontuacao',
                     'dash-saas-metas', 'dash-saas-recomendacoes'):
        assert page.locator(f'#{grupo_id}').count() == 1, f'grupo {grupo_id} ausente'

    # nenhum grupo ficou preso no skeleton (loading infinito)
    for grupo_id in ('dash-saas-saudacao', 'dash-saas-continuar', 'dash-saas-pontuacao',
                     'dash-saas-metas', 'dash-saas-recomendacoes'):
        assert page.locator(f'#{grupo_id} .dash-saas-skeleton').count() == 0, \
            f'grupo {grupo_id} ficou preso no estado de loading'

    # a saudação leva o primeiro nome do usuário
    assert 'Aluno' in page.locator('#dash-saas-saudacao h1').inner_text()

    # 401 de rede/tunnel e o probe "já estou logado?" (GET /api/auth/user
    # ANTES do login, tratado com .catch pelo app) não são erros do
    # dashboard — são ruído do ambiente/fluxo de boot pré-existente.
    erros_relevantes = [e for e in erros_console
                        if 'ERR_TUNNEL' not in e and 'ERR_CONNECTION' not in e and '401' not in e]
    assert not erros_relevantes, f'erros de console inesperados: {erros_relevantes}'

    page.close()


def test_dashboard_responsivo_sem_scroll_horizontal_no_mobile(servidor_vivo, browser, seeded):
    """§3: grid mobile-first, coluna única <768px, sem scroll horizontal."""
    page = browser.new_page(viewport={'width': 375, 'height': 900})
    page.goto(servidor_vivo + '/')
    page.fill('#login-email', 'aluno@test.com')
    page.fill('#login-pass', 'senha123')
    page.press('#login-pass', 'Enter')
    page.wait_for_selector('#dash-saas-continuar', timeout=8000)

    largura_scroll = page.evaluate('document.documentElement.scrollWidth')
    largura_viewport = page.evaluate('document.documentElement.clientWidth')
    assert largura_scroll <= largura_viewport + 1   # +1 tolerância de subpixel

    page.close()


def test_carrossel_de_recomendacoes_nao_estoura_o_layout_no_mobile(app, servidor_vivo, browser, seeded):
    """Etapa 4 (§4.1): achado real do próprio processo de verificação — um
    carrossel horizontal com vários cards (flex/grid intrinsic sizing)
    empurrava a LARGURA DE main-content para fora do viewport no mobile,
    mesmo sem o <html> mostrar scroll horizontal (o overflow ficava preso
    num container interno). Semeia vários cursos pra garantir carrossel
    com conteúdo suficiente pra reproduzir o bug se ele voltar."""
    with app.app_context():
        from extensions import db
        from models import Course, Category
        from core.tenancy import default_tenant_id
        cat = Category.query.filter_by(tenant_id=default_tenant_id()).first()
        if cat is None:
            cat = Category(name='Categoria E2E', tenant_id=default_tenant_id())
            db.session.add(cat)
            db.session.flush()
        criados = []
        for i in range(6):
            c = Course(name=f'Curso Carrossel {i}', acesso='publico', status='published',
                      category_id=cat.id, icon='📚')
            db.session.add(c)
            criados.append(c)
        db.session.commit()
        ids_criados = [c.id for c in criados]

    try:
        page = browser.new_page(viewport={'width': 375, 'height': 900})
        page.goto(servidor_vivo + '/')
        page.fill('#login-email', 'aluno@test.com')
        page.fill('#login-pass', 'senha123')
        page.press('#login-pass', 'Enter')
        page.wait_for_selector('.dash-saas-carrossel .dash-saas-netflix-card', timeout=8000)

        largura_scroll = page.evaluate('document.documentElement.scrollWidth')
        largura_viewport = page.evaluate('document.documentElement.clientWidth')
        assert largura_scroll <= largura_viewport + 1

        main_content = page.evaluate("""
          () => { const el = document.getElementById('main-content');
                  return {scroll: el.scrollWidth, client: el.clientWidth}; }
        """)
        assert main_content['scroll'] <= main_content['client'] + 1, \
            f'main-content vazou horizontalmente: {main_content}'

        # o carrossel EM SI pode (e deve) rolar — só não pode vazar pro resto da página
        carrossel = page.evaluate("""
          () => { const el = document.querySelector('.dash-saas-carrossel');
                  return {scroll: el.scrollWidth, client: el.clientWidth}; }
        """)
        assert carrossel['scroll'] > carrossel['client'], \
            'carrossel com cards suficientes deveria precisar de scroll interno'

        page.close()
    finally:
        with app.app_context():
            from extensions import db
            from models import Course
            Course.query.filter(Course.id.in_(ids_criados)).delete(synchronize_session=False)
            db.session.commit()


def test_nome_de_curso_malicioso_nao_executa_no_dashboard(app, servidor_vivo, browser, seeded):
    """XSS armazenado (achado H1 da revisão Fable 5): _dashSaasRenderContinuar,
    _dashSaasRenderSaudacao, _dashSaasRenderMetas e _dashSaasRenderPontuacao
    injetavam nome de curso/badge/meta direto em innerHTML sem escape — um
    tutor/admin criando um curso com esse nome executava JS pra QUALQUER
    aluno do tenant que abrisse o dashboard (roubo de sessão, escalada
    tutor→aluno). Prova end-to-end: nenhum dialog dispara e o payload
    aparece como TEXTO na página, nunca como markup interpretado."""
    payload = '<img src=x onerror="window.__xss_fired=true">'
    with app.app_context():
        from extensions import db
        from models import Course, LessonProgress
        course = Course.query.get(seeded['course_id'])
        course.name = payload
        db.session.add(LessonProgress(user_id=seeded['users']['aluno'], course_id=seeded['course_id'],
                                       module_id=seeded['module1_id'], passed=True, score=2, total=2))
        db.session.commit()

    try:
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        disparou_dialog = []
        page.on('dialog', lambda d: (disparou_dialog.append(d.message), d.dismiss()))

        page.goto(servidor_vivo + '/')
        page.fill('#login-email', 'aluno@test.com')
        page.fill('#login-pass', 'senha123')
        page.press('#login-pass', 'Enter')
        page.wait_for_selector('#dash-saas-continuar', timeout=8000)

        # dá tempo pro onerror disparar se o markup tiver sido interpretado
        page.wait_for_timeout(500)

        assert not disparou_dialog, f'JS malicioso disparou dialog: {disparou_dialog}'
        assert page.evaluate('window.__xss_fired') is None, \
            'onerror do payload executou — innerHTML não estava escapado'

        # nenhum elemento <img src="x"> real foi criado no DOM
        assert page.locator('#dash-saas-continuar img[src="x"]').count() == 0

        page.close()
    finally:
        with app.app_context():
            from extensions import db
            from models import Course, LessonProgress
            Course.query.get(seeded['course_id']).name = 'Curso Caracterização'
            LessonProgress.query.filter_by(user_id=seeded['users']['aluno'],
                                           course_id=seeded['course_id']).delete()
            db.session.commit()
