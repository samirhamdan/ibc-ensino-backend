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
