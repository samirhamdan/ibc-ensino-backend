#!/usr/bin/env python3
"""Lint: nenhuma cor hex hardcoded nos componentes do dashboard SaaS (GAM-05).

## Contexto / achado da investigação (GAM-05, PR 1)

docs/UX_ALUNO_SAAS.md §6 já prometia esta checagem ("lint customizado que
falha se encontrar cor fora de tokens.css") como critério de aceite da
Etapa 1 do GAM-04 — mas ela NUNCA foi implementada, commitada nem ligada ao
CI (não há vestígio em `scripts/`, `.github/workflows/ci.yml`, nem em
`tests/`; era só uma prática manual/aspiracional). Não havia, portanto,
nenhum lint a "não pegar" o bug — a causa raiz do gap é ausência total da
ferramenta, não um regex malformado.

Mas escrever a versão óbvia do lint (grep por `#[0-9a-f]{3,6}` em todo
`css/**/*.css`) TAMBÉM não pegaria o bug real: o botão "Ver catálogo" usa
`.btn-primary` (css/components/buttons.css), cujo `background` é
`var(--gradient-btn, var(--primary))` — zero caracteres hex literais nessa
linha. O hardcode não é um valor de cor cru; é uma referência ao token
ERRADO: `--gradient-btn` (css/design-system.css) é composto de
`--primary-400/--primary-600/--violet-600`, que são a ESCALA FIXA da
plataforma (nunca sobrescrita por tenant) — só `--brand-primary` e seus
derivados (`--brand-gradient` etc.) são injetados por tenant via
`<style id="tenant-theme">` (core/theming.py). Um lint puramente
hex-literal está estruturalmente cego para "token certo vs. token errado".

Por isso este script faz DUAS coisas:
  1. Varre hex literal (pega o caso óbvio — cor solta em vez de token).
  2. `tests/test_lint_hardcoded_hex.py::test_botao_primario_usa_brand_gradient`
     faz a checagem que realmente importa aqui: asserta que os seletores de
     CTA primário referenciam `--brand-gradient` (ou `--brand-primary`)
     explicitamente, não só qualquer `var(--algo)`.

## Escopo do hex-lint

Rodar isto contra TODO `css/**/*.css` hoje dá 200+ achados pré-existentes
(badges.css, notifications.css, admin-ux.css, login.css...) — débito real,
mas de outras eras/features, fora do escopo do GAM-05 e não algo para este
PR corrigir de uma vez (viraria um PR gigante não relacionado). Ligar isso
ao CI sem faseamento quebraria o pipeline por débito alheio.

Este lint, portanto, tem escopo EXPLÍCITO (allowlist, não a árvore
inteira): a superfície do dashboard do aluno (GAM-04/GAM-05) —
`css/design-system.css` (definição de token, hex é o lugar certo) e os
arquivos de `SCANNED_FILES` abaixo. `css/components/buttons.css` está
DELIBERADAMENTE na lista mesmo sendo pré-GAM-04 (ver `git log --follow`):
é o arquivo COMPARTILHADO que o botão "Ver catálogo" usa via `.btn-primary`
— excluí-lo por ser "legado" é exatamente o tipo de lacuna de escopo que
deixou o bug original passar (hipótese (b) do PR: arquivo tratado como
fora do escopo do check quando na verdade alimenta um componente novo).
Outros arquivos legados de fora dessa lista (app.css, badges.css, etc.)
ficam como débito rastreado em docs/DEBITOS.md, não neste gate.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSS_DIR = REPO_ROOT / 'css'

# Único arquivo onde hex literal é a própria definição do token (fallback
# documentado em design-system.css:15-27).
TOKEN_DEFINITION_FILES = {
    CSS_DIR / 'design-system.css',
}

# Allowlist explícita: superfície do dashboard do aluno (GAM-04/GAM-05).
# Ver nota de escopo acima sobre por que buttons.css entra aqui mesmo
# sendo um arquivo pré-existente.
SCANNED_FILES = {
    CSS_DIR / 'components' / 'dashboard-saas.css',
    CSS_DIR / 'components' / 'buttons.css',
}

# Dentro de buttons.css nem toda regra é "identidade do tenant" — .btn-gold,
# .btn-outline etc. usam paleta fixa da plataforma de propósito (dourado de
# conquista, por ex., não é cor de marca). Só as regras de CTA PRIMÁRIO
# (as que o botão "Ver catálogo" — .btn-primary — realmente usa) precisam
# ser 100% livres de hex solto; o resto é escopo de outro débito
# (docs/DEBITOS.md), não desta checagem de identidade de tenant.
BRAND_SCOPED_SELECTOR_PREFIXES = ('.btn-primary', '.dash-saas-')

HEX_RE = re.compile(r'#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b')
# hex usado como fallback de var(--token, #hex) é uma referência a token
# válida (mesmo padrão de css/design-system.css: var(--brand-gradient,
# var(--gradient-btn, var(--primary)))) — não é o hardcode que procuramos.
# Removemos o conteúdo de qualquer var(...) antes de buscar hex "solto".
VAR_CALL_RE = re.compile(r'var\([^)]*\)')


def _selector_e_brand_scoped(selector_atual):
    return any(sel.strip().startswith(BRAND_SCOPED_SELECTOR_PREFIXES) for sel in selector_atual.split(','))


def find_hardcoded_hex():
    """Retorna lista de (arquivo_relativo, num_linha, trecho, hex) para
    toda ocorrência de hex "solto" (fora de var(...)) dentro de regras de
    CTA com identidade de tenant (BRAND_SCOPED_SELECTOR_PREFIXES) nos
    arquivos escaneados (SCANNED_FILES)."""
    achados = []
    for css_file in sorted(SCANNED_FILES):
        if not css_file.exists() or css_file in TOKEN_DEFINITION_FILES:
            continue
        selector_atual = ''
        dentro_de_regra_brand = False
        for lineno, line in enumerate(css_file.read_text(encoding='utf-8').splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith('/*') or stripped.startswith('*'):
                continue
            if '{' in line:
                selector_atual = line.split('{', 1)[0]
                dentro_de_regra_brand = _selector_e_brand_scoped(selector_atual)
            if dentro_de_regra_brand:
                sem_var = VAR_CALL_RE.sub('', line)
                for m in HEX_RE.finditer(sem_var):
                    achados.append((str(css_file.relative_to(REPO_ROOT)), lineno, line.strip(), m.group(0)))
            if '}' in line:
                dentro_de_regra_brand = False
    return achados


def main():
    achados = find_hardcoded_hex()
    if achados:
        print('Cor hex hardcoded na superfície do dashboard do aluno (SCANNED_FILES):')
        for arquivo, lineno, trecho, hexcor in achados:
            print(f'  {arquivo}:{lineno}: {hexcor}  |  {trecho}')
        print(f'\n{len(achados)} ocorrência(s). Use var(--token) (css/design-system.css) em vez de hex literal.')
        return 1
    print('OK: nenhuma cor hex hardcoded na superfície do dashboard do aluno.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
