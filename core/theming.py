"""
Etapa 1 (GAM-04 / TEN-03, doc UX_ALUNO_SAAS.md §2): derivação de tema por
tenant. O tenant escolhe UMA cor primária (e opcionalmente logo); tudo o
mais é calculado aqui — hover, fundo sutil, gradiente, cor de texto sobre a
cor primária, e um ajuste automático de luminosidade se a cor escolhida não
alcançar contraste AA contra os tokens fixos da plataforma (§2.2.4).

Puro (sem Flask/DB) — usado por routes/theme.py e testável isoladamente.
"""
import colorsys
import re

# Tokens fixos da plataforma (§2.1) — o tenant nunca configura estes.
BG_BASE = '#0a0f1e'
TEXT_PRIMARY = '#f1f5f9'
CONTRASTE_MINIMO_TEXTO = 4.5   # WCAG AA, texto normal

_HEX_RE = re.compile(r'^#?([0-9a-fA-F]{6})$')


def _normaliza_hex(cor):
    m = _HEX_RE.match((cor or '').strip())
    if not m:
        raise ValueError(f'cor inválida: {cor!r} (esperado #RRGGBB)')
    return '#' + m.group(1).lower()


def hex_para_rgb(cor):
    cor = _normaliza_hex(cor)
    return tuple(int(cor[i:i + 2], 16) for i in (1, 3, 5))


def rgb_para_hex(rgb):
    r, g, b = (max(0, min(255, round(c))) for c in rgb)
    return f'#{r:02x}{g:02x}{b:02x}'


def _canal_linear(c):
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminancia_relativa(cor):
    """WCAG 2.1 §1.4.3."""
    r, g, b = hex_para_rgb(cor)
    r, g, b = _canal_linear(r), _canal_linear(g), _canal_linear(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def razao_de_contraste(cor_a, cor_b):
    la, lb = luminancia_relativa(cor_a), luminancia_relativa(cor_b)
    claro, escuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (escuro + 0.05)


def escurecer(cor, fracao):
    """Mistura com preto — usado para --brand-primary-hover (8%)."""
    r, g, b = hex_para_rgb(cor)
    f = 1 - fracao
    return rgb_para_hex((r * f, g * f, b * f))


def clarear(cor, fracao):
    r, g, b = hex_para_rgb(cor)
    return rgb_para_hex((r + (255 - r) * fracao, g + (255 - g) * fracao, b + (255 - b) * fracao))


def com_opacidade(cor, alpha):
    """rgba() para fundos sutis (--brand-primary-subtle, 10%)."""
    r, g, b = hex_para_rgb(cor)
    return f'rgba({r}, {g}, {b}, {alpha})'


def rotacionar_matiz(cor, graus):
    """Gira o matiz em HSL — usado no gradiente (primary → primary+20°)."""
    r, g, b = (c / 255 for c in hex_para_rgb(cor))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    h = (h + graus / 360.0) % 1.0
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return rgb_para_hex((r * 255, g * 255, b * 255))


def cor_sobre_primaria(cor_primaria):
    """Branco ou o texto escuro da plataforma, o que der mais contraste
    sobre a cor primária (texto de botão primário, --brand-on-primary)."""
    branco, escuro = '#ffffff', '#0a0f1e'
    if razao_de_contraste(cor_primaria, branco) >= razao_de_contraste(cor_primaria, escuro):
        return branco
    return escuro


def garantir_acessivel(cor_primaria, minimo=CONTRASTE_MINIMO_TEXTO):
    """Se a cor escolhida pelo tenant não alcança contraste AA contra
    --bg-base OU --text-primary (§2.2.4 — usada como texto/borda sobre o
    fundo escuro da plataforma, não só como fundo de botão), ajusta a
    luminosidade até passar. Devolve (cor_final, foi_ajustada)."""
    cor = _normaliza_hex(cor_primaria)
    if (razao_de_contraste(cor, BG_BASE) >= minimo):
        return cor, False

    r, g, b = (c / 255 for c in hex_para_rgb(cor))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    # A cor está escura demais para o fundo escuro da plataforma — clareia
    # em passos até bater o contraste mínimo (ou esgotar o intervalo).
    passo = 0.04
    candidata = cor
    while l < 1.0 and razao_de_contraste(candidata, BG_BASE) < minimo:
        l = min(1.0, l + passo)
        r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
        candidata = rgb_para_hex((r2 * 255, g2 * 255, b2 * 255))
    return candidata, candidata != cor


def construir_tokens(tema_json, nome_tenant):
    """Monta o dicionário de custom properties a partir de tenants.tema_json
    (`{"primary": "#RRGGBB", "logo": "...", "nome_exibido": "..."}` —
    aceita também a chave legada `cor_primaria`, do seed atual)."""
    tema_json = tema_json or {}
    bruta = tema_json.get('primary') or tema_json.get('cor_primaria') or '#008ea8'
    primaria, ajustada = garantir_acessivel(bruta)

    return {
        '--brand-primary': primaria,
        '--brand-primary-hover': escurecer(primaria, 0.08),
        '--brand-primary-subtle': com_opacidade(primaria, 0.10),
        '--brand-gradient': f'linear-gradient(120deg, {primaria} 0%, {rotacionar_matiz(primaria, 20)} 100%)',
        '--brand-on-primary': cor_sobre_primaria(primaria),
        '_meta': {
            'nome_exibido': tema_json.get('nome_exibido') or nome_tenant,
            'logo': tema_json.get('logo') or '',
            'cor_ajustada_por_contraste': ajustada,
        },
    }


def tokens_para_css(tokens):
    """Serializa os tokens (exceto `_meta`) como bloco :root para injeção
    em <style id="tenant-theme"> — só a IDENTIDADE e seus derivados; os
    tokens fixos da plataforma (§2.1) já estão em css/design-system.css."""
    linhas = [f'  {chave}: {valor};' for chave, valor in tokens.items() if chave != '_meta']
    return ':root {\n' + '\n'.join(linhas) + '\n}\n'
