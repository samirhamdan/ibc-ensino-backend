"""GAM-05 — lint de identidade do tenant no CSS (scripts/check_hardcoded_hex.py).

Cobre dois ângulos do mesmo bug (o botão "Ver catálogo" usando um gradiente
teal->violeta fixo em vez de --brand-gradient, ver docs/MELHORIAS-UI-ALUNO.md
PR 1):

1. `test_lint_passa_na_arvore_atual` / `test_lint_pega_gradiente_hex_reintroduzido`:
   o lint de hex hardcoded em si — passa hoje, e pega uma regressão óbvia
   (hex literal solto num seletor de CTA).
2. `test_botao_primario_referencia_brand_gradient`: a checagem que teria
   realmente pego o bug ORIGINAL, que não tinha hex nenhum — só um token
   errado (`--gradient-btn`, fixo) em vez do certo (`--brand-gradient`,
   por tenant). Um lint puramente hex-literal é cego para isso; ver
   docstring de scripts/check_hardcoded_hex.py.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

from check_hardcoded_hex import find_hardcoded_hex  # noqa: E402

BUTTONS_CSS = REPO_ROOT / 'css' / 'components' / 'buttons.css'


def test_lint_passa_na_arvore_atual():
    assert find_hardcoded_hex() == []


def test_lint_pega_gradiente_hex_reintroduzido(tmp_path, monkeypatch):
    """Reintroduz o gradiente teal->violeta hex hardcoded original em
    .btn-primary e confirma que o lint acusa a regressão."""
    import check_hardcoded_hex as lint_mod

    original = BUTTONS_CSS.read_text(encoding='utf-8')
    assert 'var(--brand-gradient' in original, (
        'pré-condição do teste: buttons.css deveria já estar usando '
        '--brand-gradient (fix desta PR) antes de simular a regressão'
    )
    regressao = original.replace(
        'background: var(--brand-gradient, var(--gradient-btn, var(--primary)));',
        'background: linear-gradient(90deg, #008ea8, #8b5cf6);',
    )
    assert regressao != original
    BUTTONS_CSS.write_text(regressao, encoding='utf-8')
    try:
        achados = lint_mod.find_hardcoded_hex()
    finally:
        BUTTONS_CSS.write_text(original, encoding='utf-8')

    assert achados, 'lint deveria ter acusado o hex hardcoded reintroduzido'
    assert any('8b5cf6' in hexcor.lower() or '8b5cf6' in trecho.lower()
               for _, _, trecho, hexcor in achados)


def test_botao_primario_referencia_brand_gradient():
    """A checagem que realmente teria pego o bug original: .btn-primary
    (usado pelo botão "Ver catálogo" do dashboard, index.html) precisa
    referenciar --brand-gradient (token por tenant, core/theming.py) — não
    só qualquer var(), o que deixaria passar --gradient-btn (fixo)."""
    css = BUTTONS_CSS.read_text(encoding='utf-8')
    m = re.search(r'\.btn-primary\s*\{([^}]*)\}', css)
    assert m, '.btn-primary não encontrado em css/components/buttons.css'
    bloco = m.group(1)
    assert 'background' in bloco
    assert '--brand-gradient' in bloco, (
        '.btn-primary não referencia --brand-gradient — o CTA primário '
        '(inclui "Ver catálogo") não segue a identidade do tenant'
    )
