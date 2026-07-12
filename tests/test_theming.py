"""Testes unitários da derivação de tema (Etapa 1, UX_ALUNO_SAAS.md §2)."""
import pytest

from core.theming import (
    construir_tokens, tokens_para_css, razao_de_contraste, escurecer,
    cor_sobre_primaria, garantir_acessivel, BG_BASE,
)


def test_ibc_default_nao_precisa_de_ajuste():
    """A cor default do seed (#008ea8) já é a usada em produção hoje —
    o pipeline não pode alterá-la (aceite da Etapa 1: 'IBC renderiza
    idêntico ao atual via tokens')."""
    cor, ajustada = garantir_acessivel('#008ea8')
    assert cor == '#008ea8'
    assert ajustada is False


def test_cor_escura_demais_e_clareada_ate_passar_no_contraste():
    cor, ajustada = garantir_acessivel('#050505')
    assert ajustada is True
    assert razao_de_contraste(cor, BG_BASE) >= 4.5


def test_escurecer_produz_cor_mais_escura():
    base = '#008ea8'
    escura = escurecer(base, 0.08)
    assert escura != base
    # mistura com preto: cada canal <= original
    from core.theming import hex_para_rgb
    r1, g1, b1 = hex_para_rgb(base)
    r2, g2, b2 = hex_para_rgb(escura)
    assert r2 <= r1 and g2 <= g1 and b2 <= b1


def test_cor_sobre_primaria_escolhe_o_maior_contraste():
    # primária muito clara → texto escuro tem mais contraste que branco
    assert cor_sobre_primaria('#fefefe') == '#0a0f1e'
    # primária escura → texto branco tem mais contraste
    assert cor_sobre_primaria('#111111') == '#ffffff'


def test_construir_tokens_aceita_chave_legada_cor_primaria():
    """seed.py ainda usa `cor_primaria` (não `primary`) — o pipeline tem
    que continuar funcionando sem exigir migração do seed nesta etapa."""
    tokens = construir_tokens({'cor_primaria': '#008ea8'}, 'IBC Ensino')
    assert tokens['--brand-primary'] == '#008ea8'
    assert tokens['_meta']['nome_exibido'] == 'IBC Ensino'


def test_construir_tokens_usa_nome_exibido_do_tema_quando_presente():
    tokens = construir_tokens({'primary': '#7c3aed', 'nome_exibido': 'Demo XR'}, 'Tenant Demo')
    assert tokens['_meta']['nome_exibido'] == 'Demo XR'


def test_construir_tokens_sem_tema_cai_no_default():
    tokens = construir_tokens(None, 'Tenant Sem Tema')
    assert tokens['--brand-primary'] == '#008ea8'


def test_construir_tokens_rejeita_cor_invalida():
    with pytest.raises(ValueError):
        construir_tokens({'primary': 'não-é-cor'}, 'X')


def test_tokens_para_css_nao_vaza_meta():
    tokens = construir_tokens({'primary': '#008ea8'}, 'IBC')
    css = tokens_para_css(tokens)
    assert ':root {' in css
    assert '--brand-primary: #008ea8;' in css
    assert '_meta' not in css
    assert 'nome_exibido' not in css


def test_endpoint_theme_nao_quebra_com_cor_malformada_no_banco(app, seeded):
    """Correção da 1ª revisão Fable 5 (H2): tema_json malformado (edição
    manual, bug futuro no editor de admin) não pode derrubar /api/theme
    com 500 — cai no default da plataforma e responde 200."""
    with app.app_context():
        from extensions import db
        from core.tenancy import Tenant, default_tenant_id
        from core.tenancy.cache import cache_clear
        tenant = Tenant.query.get(default_tenant_id())
        original = tenant.tema_json
        tenant.tema_json = {'primary': 'não-é-cor'}
        db.session.commit()
    cache_clear()

    try:
        c = app.test_client()
        r = c.get('/api/theme')
        assert r.status_code == 200
        assert '--brand-primary' in r.get_data(as_text=True)

        r2 = c.get('/api/theme.json')
        assert r2.status_code == 200
        assert r2.get_json()['--brand-primary'] == '#008ea8'
    finally:
        with app.app_context():
            from extensions import db
            from core.tenancy import Tenant, default_tenant_id
            from core.tenancy.cache import cache_clear as _clear
            tenant = Tenant.query.get(default_tenant_id())
            tenant.tema_json = original
            db.session.commit()
        cache_clear()
