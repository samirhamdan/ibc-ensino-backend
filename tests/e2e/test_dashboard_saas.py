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


def test_tenant_com_cor_diferente_aplica_de_verdade_no_browser(app, servidor_vivo, browser):
    """Etapa 1 (§6): achado da auditoria de release — GET /api/theme
    calculava a cor certa e o <style id="tenant-theme"> era injetado com o
    valor certo, mas design-system.css (carregado DEPOIS na versão antiga)
    declarava --brand-primary de novo em :root com o fallback fixo do IBC —
    mesma especificidade, ordem no documento decidia, e o fallback sempre
    vencia. Provado aqui via getComputedStyle no navegador de verdade (não
    só inspecionando o texto do <style> injetado, que "passava" mesmo com o
    bug): tenant demo com cor diferente do IBC precisa aplicar a cor DELE."""
    from extensions import db
    from core.tenancy import Tenant

    with app.app_context():
        demo = Tenant.query.filter_by(slug='demo').first()
        assert demo is not None
        demo.tema_json = {**(demo.tema_json or {}), 'cor_primaria': '#7c3aed'}
        db.session.commit()

    ctx_ibc = browser.new_context(extra_http_headers={'X-Tenant-Slug': 'ibc'})
    ctx_demo = browser.new_context(extra_http_headers={'X-Tenant-Slug': 'demo'})
    try:
        page_ibc = ctx_ibc.new_page()
        page_ibc.goto(servidor_vivo + '/')
        page_ibc.wait_for_selector('#tenant-theme', state='attached', timeout=5000)
        cor_ibc = page_ibc.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--brand-primary').trim()")

        page_demo = ctx_demo.new_page()
        page_demo.goto(servidor_vivo + '/')
        page_demo.wait_for_selector('#tenant-theme', state='attached', timeout=5000)
        cor_demo = page_demo.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--brand-primary').trim()")

        assert cor_ibc.lower() == '#008ea8', f'IBC deveria manter a cor de sempre, veio {cor_ibc}'
        assert cor_demo.lower() != cor_ibc.lower(), (
            f'demo aplicou a MESMA cor do IBC ({cor_demo}) — a cor do tenant não está '
            'realmente sendo aplicada no navegador, só calculada no servidor')

        page_ibc.close()
        page_demo.close()
    finally:
        ctx_ibc.close()
        ctx_demo.close()
        with app.app_context():
            demo = Tenant.query.filter_by(slug='demo').first()
            demo.tema_json = {k: v for k, v in (demo.tema_json or {}).items() if k != 'cor_primaria'}
            db.session.commit()


def test_jornada_abrir_dashboard_e_continuar_licao(servidor_vivo, browser, seeded):
    """Critério de aceite da Etapa 2: um aluno com progresso em andamento
    abre o dashboard (v2: saudação, continuar, resumo) e vê a estrutura com o card de 'continuar'
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
                     'dash-saas-recomendacoes'):
        assert page.locator(f'#{grupo_id}').count() == 1, f'grupo {grupo_id} ausente'

    # nenhum grupo ficou preso no skeleton (loading infinito)
    for grupo_id in ('dash-saas-saudacao', 'dash-saas-continuar', 'dash-saas-pontuacao'):
        assert page.locator(f'#{grupo_id} .dash-saas-skeleton').count() == 0, \
            f'grupo {grupo_id} ficou preso no estado de loading'

    # a saudação leva o primeiro nome do usuário
    assert 'Aluno' in page.locator('#dash-saas-saudacao h1').inner_text()

    # 401 de rede/tunnel e o probe "já estou logado?" (GET /api/auth/user
    # ANTES do login, tratado com .catch pelo app) não são erros do
    # dashboard — são ruído do ambiente/fluxo de boot pré-existente.
    erros_relevantes = [e for e in erros_console
                        if 'ERR_TUNNEL' not in e and 'ERR_CONNECTION' not in e and 'ERR_CERT' not in e and '401' not in e]
    assert not erros_relevantes, f'erros de console inesperados: {erros_relevantes}'

    page.close()


def test_contadores_de_streak_e_pontos_tem_aria_live(servidor_vivo, browser, seeded):
    """UX_ALUNO_SAAS.md §5 (gate de aceite): contadores (streak, pontos) com
    aria-live='polite'. No v2 o streak vive na meta do dia (saudação) e os
    pontos no resumo de uma linha."""
    page = browser.new_page()
    page.goto(servidor_vivo + '/')
    page.fill('#login-email', 'aluno@test.com')
    page.fill('#login-pass', 'senha123')
    page.press('#login-pass', 'Enter')
    page.wait_for_selector('.aluno-v2-resumo', timeout=8000)
    page.wait_for_selector('.aluno-v2-meta', timeout=8000)
    assert page.locator('.aluno-v2-resumo').get_attribute('aria-live') == 'polite'
    assert page.locator('.aluno-v2-meta').get_attribute('aria-live') == 'polite'
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


def test_carrossel_navega_por_setas_do_teclado(app, servidor_vivo, browser, seeded):
    """UX_ALUNO_SAAS.md §5 (gate de aceite): "carrossel operável por
    setas" — achado da auditoria de release, faltava inteiramente (só
    Tab/click funcionava). Prova real: foca o carrossel, aperta
    ArrowRight, confirma que o scrollLeft realmente mudou."""
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
        for i in range(8):
            c = Course(name=f'Curso Teclado {i}', acesso='publico', status='published',
                      category_id=cat.id, icon='📚')
            db.session.add(c)
            criados.append(c)
        db.session.commit()
        ids_criados = [c.id for c in criados]

    try:
        page = browser.new_page(viewport={'width': 1200, 'height': 800})
        page.goto(servidor_vivo + '/')
        page.fill('#login-email', 'aluno@test.com')
        page.fill('#login-pass', 'senha123')
        page.press('#login-pass', 'Enter')
        page.wait_for_selector('.dash-saas-carrossel .dash-saas-netflix-card', timeout=8000)

        carrossel = page.locator('.dash-saas-carrossel')
        carrossel.focus()
        assert page.evaluate("document.activeElement.classList.contains('dash-saas-carrossel')")

        scroll_antes = page.evaluate("document.querySelector('.dash-saas-carrossel').scrollLeft")
        page.keyboard.press('ArrowRight')
        page.wait_for_timeout(400)   # scrollBy(behavior:'smooth')
        scroll_depois = page.evaluate("document.querySelector('.dash-saas-carrossel').scrollLeft")
        assert scroll_depois > scroll_antes, 'ArrowRight não rolou o carrossel'

        page.keyboard.press('ArrowLeft')
        page.wait_for_timeout(400)
        scroll_final = page.evaluate("document.querySelector('.dash-saas-carrossel').scrollLeft")
        assert scroll_final < scroll_depois, 'ArrowLeft não rolou o carrossel de volta'

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


def test_container_do_dashboard_tem_max_width_em_viewport_largo(servidor_vivo, browser, seeded):
    """Em telas muito largas o conteúdo não estica até a borda (linhas de
    leitura absurdas) nem vira uma coluna minúscula — v2 limita a ~1120px."""
    page = browser.new_page(viewport={'width': 1920, 'height': 1080})
    page.goto(servidor_vivo + '/')
    page.fill('#login-email', 'aluno@test.com')
    page.fill('#login-pass', 'senha123')
    page.press('#login-pass', 'Enter')
    page.wait_for_selector('#dash-saas-continuar', timeout=8000)

    largura = page.evaluate("document.querySelector('.aluno-v2').getBoundingClientRect().width")
    assert 700 <= largura <= 1200, f'largura do dashboard fora do esperado: {largura}px'
    page.close()


def test_meta_do_dia_mostra_a_chama_de_streak_na_saudacao(servidor_vivo, browser, seeded):
    """Dashboard v2: o streak (motor de hábito) sobe para a meta do dia, ao
    lado da saudação — uma chama só na tela, sem duplicar no resumo."""
    page = browser.new_page()
    page.goto(servidor_vivo + '/')
    page.fill('#login-email', 'aluno@test.com')
    page.fill('#login-pass', 'senha123')
    page.press('#login-pass', 'Enter')
    page.wait_for_selector('#dash-saas-saudacao .aluno-v2-meta', timeout=8000)
    assert page.locator('#dash-saas-saudacao .dash-saas-flame').count() == 1
    assert page.locator('#dash-saas-pontuacao .dash-saas-flame').count() == 0
    assert 'Meta de hoje' in page.locator('#dash-saas-saudacao').inner_text()
    page.close()


def test_flame_relocado_respeita_prefers_reduced_motion(servidor_vivo, browser, seeded, app):
    """GAM-02 (§4.2): a chama de streak tem animação (flicker/pulso) que
    precisa desligar com prefers-reduced-motion — comportamento pré-
    existente que a relocação pro card de pontuação (P0.3, GAM-05 PR 2)
    não pode quebrar. Seeda um streak ativo pra garantir que a chama saia
    do estado 'quebrada' (que já não anima) e realmente exercite a
    animação sob teste."""
    with app.app_context():
        from extensions import db
        from models import UserPoints
        from core.tenancy import default_tenant_id
        from routes.gamification import hoje_streak
        up = UserPoints.query.filter_by(user_id=seeded['users']['aluno'], tenant_id=default_tenant_id()).first()
        if up is None:
            up = UserPoints(user_id=seeded['users']['aluno'], tenant_id=default_tenant_id())
            db.session.add(up)
        up.current_streak = 3
        up.last_activity_date = hoje_streak()
        db.session.commit()

    try:
        page = browser.new_page()
        page.emulate_media(reduced_motion='reduce')
        page.goto(servidor_vivo + '/')
        page.fill('#login-email', 'aluno@test.com')
        page.fill('#login-pass', 'senha123')
        page.press('#login-pass', 'Enter')
        page.wait_for_selector('#dash-saas-saudacao .dash-saas-flame', timeout=8000)

        flame = page.locator('#dash-saas-saudacao .dash-saas-flame')
        assert flame.count() == 1
        animacao = flame.evaluate("el => getComputedStyle(el).animationName")
        assert animacao in ('none', ''), \
            f'chama ainda anima com prefers-reduced-motion ativo: animationName={animacao!r}'

        page.close()
    finally:
        with app.app_context():
            from extensions import db
            from models import UserPoints
            from core.tenancy import default_tenant_id
            up = UserPoints.query.filter_by(user_id=seeded['users']['aluno'], tenant_id=default_tenant_id()).first()
            if up:
                up.current_streak = 0
                db.session.commit()


def test_revisao_do_dia_nao_renderiza_nada(servidor_vivo, browser, seeded):
    """Com DASH_SAAS_FLAGS.revisao_ia_enabled desligado (LRN-02 ainda não
    existe), nada de "Revisão do dia" nem placeholder de feature futura."""
    page = browser.new_page()
    page.goto(servidor_vivo + '/')
    page.fill('#login-email', 'aluno@test.com')
    page.fill('#login-pass', 'senha123')
    page.press('#login-pass', 'Enter')
    page.wait_for_selector('#dash-saas-continuar', timeout=8000)
    page.wait_for_timeout(300)
    html = page.locator('#main-content').inner_html()
    assert 'dash-saas-meta-revisao' not in html
    assert 'Revisão do dia' not in html
    assert 'Release' not in html
    page.close()


def test_botao_ver_catalogo_usa_gradiente_do_tenant(servidor_vivo, browser, seeded):
    """GAM-05 (docs/MELHORIAS-UI-ALUNO.md PR 1, item 3): o botão "Ver
    catálogo" (.btn-primary, grupo 'Continue seus estudos') deve pintar
    com --brand-gradient (identidade do tenant, core/theming.py) — não com
    um gradiente teal→violeta fixo (--gradient-btn, que nunca muda por
    tenant)."""
    page = browser.new_page()
    page.goto(servidor_vivo + '/')
    page.fill('#login-email', 'aluno@test.com')
    page.fill('#login-pass', 'senha123')
    page.press('#login-pass', 'Enter')
    page.wait_for_selector('#dash-saas-continuar', timeout=8000)

    botao = page.get_by_role('button', name='Ver catálogo')
    assert botao.count() == 1
    background = botao.evaluate("el => getComputedStyle(el).backgroundImage")
    assert background != 'none'

    # Comparar background (computado) direto com o texto CRU de
    # --brand-gradient (custom property, nunca passa pela normalização do
    # navegador — vira "rgb(...)" no computed style) sempre diverge em
    # formato e faz o assert degradar pra "é algum linear-gradient", o que
    # o bug original (--gradient-btn fixo) também satisfaz (achado da
    # revisão Fable 5). Em vez disso, renderiza DOIS elementos ocultos —
    # um com var(--brand-gradient), outro com var(--gradient-btn) — e
    # compara o backgroundImage COMPUTADO de cada um contra o do botão:
    # mesma normalização dos dois lados, comparação sem ambiguidade.
    referencia_tenant, referencia_fixa = page.evaluate("""
        () => {
          const mk = (expr) => {
            const el = document.createElement('div');
            el.style.background = expr;
            document.body.appendChild(el);
            const v = getComputedStyle(el).backgroundImage;
            el.remove();
            return v;
          };
          return [mk('var(--brand-gradient)'), mk('var(--gradient-btn)')];
        }
    """)
    assert background == referencia_tenant, (
        f'botão não herda --brand-gradient do tenant: {background!r} != {referencia_tenant!r}')
    assert background != referencia_fixa, (
        'botão ainda usa o gradiente fixo da plataforma (--gradient-btn), não o do tenant')

    page.close()


def test_celebracao_dispara_uma_vez_por_conclusao_real_e_nao_reaparece_no_reload(
        app, servidor_vivo, browser, seeded):
    """GAM-05 PR 3 (P1.5): a micro-interação de celebração (scale + 2
    partículas em --brand-primary) precisa disparar num evento REAL de
    conclusão — não em qualquer re-render do dashboard — e não pode
    reaparecer sozinha num reload/re-render sem uma conclusão nova.

    Prova end-to-end: usa um aluno com progresso zerado (`fresh` via
    registro direto, não o `aluno` compartilhado — outros testes desta
    suíte já usam esse usuário e podem deixar a aula 1 concluída),
    responde e envia o quiz de verdade (POST real pra
    /api/courses/<id>/aulas/<n>/submit-quiz) através da própria função
    submitAulaQuiz() do app — não injeta o painel nem a classe via DOM.
    Confirma que a classe de celebração aparece no card certo, então
    recarrega a página e confirma que ela NÃO existe em lugar nenhum sem
    um novo evento de conclusão."""
    from extensions import db
    from models import User
    from core.tenancy import TenantUser

    email = 'celebra@test.com'
    with app.app_context():
        existente = User.query.filter_by(email=email).first()
        if existente:
            TenantUser.query.filter_by(user_id=existente.id).delete()
            db.session.delete(existente)
            db.session.commit()

    page = browser.new_page(viewport={'width': 1280, 'height': 900})
    page.goto(servidor_vivo + '/')

    # Registro direto via API (evita depender do formulário de cadastro
    # do SPA, que não é o objeto deste teste) — mas o login em seguida
    # É feito pelo navegador de verdade, como qualquer usuário faria.
    page.evaluate(f"""
        () => fetch('/api/auth/register', {{
            method: 'POST', headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{name: 'Aluno Celebra', email: '{email}',
                                   password: 'senha123', confirm_password: 'senha123'}})
        }})
    """)

    page.goto(servidor_vivo + '/')
    # Segundo goto na mesma page reintroduz a UI de login do zero (a tela
    # some enquanto o app aguarda GET /api/auth/user pra decidir se mostra
    # login ou dashboard) — espera ficar visível antes de preencher, senão
    # o fill corre uma race real contra esse fetch inicial.
    page.wait_for_selector('#login-email', state='visible', timeout=15000)
    page.fill('#login-email', email)
    page.fill('#login-pass', 'senha123')
    page.press('#login-pass', 'Enter')
    page.wait_for_selector('#dash-saas-continuar', timeout=8000)

    course_id = seeded['course_id']
    # Abre a Aula 1 do curso semeado (2 questões, resposta correta = índice 1)
    # através da própria função do app (loadAula), como o clique em
    # "Continuar lição"/carrossel faria.
    # Usuário recém-registrado dispara o modal de onboarding, que fica
    # sobreposto ao dashboard/quiz e intercepta cliques (achado real deste
    # teste, não do fluxo de conclusão) — fecha como o usuário faria.
    page.evaluate("""
      try { closeOnboardingModal(); } catch(e) {}
      document.querySelectorAll('.modal,[id*=modal],.onboarding-modal').forEach(m=>m.remove());
    """)

    page.evaluate(f"loadAula({course_id}, 1)")
    page.wait_for_selector('#aqcard-0 .option', timeout=8000)

    # Responde as 2 questões com a opção correta (índice 1, ver conftest.seeded)
    for qi in range(2):
        page.click(f'#aqcard-{qi} .option >> nth=1')

    page.click('button:has-text("Enviar respostas")')

    # submitAulaQuiz() dispara showLessonCompletedPanel() com um
    # setTimeout(1300ms) quando a aula é aprovada pela primeira vez.
    page.wait_for_selector('.lesson-completed-check--celebrate', timeout=5000)
    assert page.locator('.lesson-completed-check--celebrate').count() == 1, \
        'classe de celebração não apareceu no card de "Aula concluída" após conclusão real'

    # Fecha o painel (fluxo normal do usuário) e recarrega a página sem
    # gerar NENHUM evento de conclusão novo — a celebração não pode
    # reaparecer sozinha num re-render/reload.
    page.evaluate('closeLessonCompletedPanel()')
    page.reload()
    # A sessão (cookie) segue válida depois do reload — o app vai direto
    # pro dashboard, sem tela de login. Preencher #login-email/#login-pass
    # aqui é bug do teste: esses campos nunca aparecem pra um usuário já
    # autenticado, e o fill trava até estourar o timeout esperando um
    # formulário que corretamente não é mostrado.
    page.wait_for_selector('#dash-saas-continuar', timeout=8000)
    page.wait_for_timeout(500)

    assert page.locator('.lesson-completed-check--celebrate').count() == 0, \
        'classe de celebração reapareceu num reload sem conclusão nova — deveria só existir ' \
        'no card criado por um evento real de conclusão'

    page.close()
    with app.app_context():
        from models import User
        from core.tenancy import TenantUser
        u = User.query.filter_by(email=email).first()
        if u:
            # TenantUser não tem cascade de FK — apagar só o User deixa a
            # linha órfã em tenant_users. Sem isto, o próximo teste que
            # criar um usuário reaproveitando o mesmo id (SQLite reusa
            # rowid livre) esbarra num UNIQUE constraint (tenant_id,
            # user_id) alheio, quebrando um teste que não tem nada a ver
            # com celebração (achado real ao rodar a suíte inteira).
            TenantUser.query.filter_by(user_id=u.id).delete()
            db.session.delete(u)
            db.session.commit()
