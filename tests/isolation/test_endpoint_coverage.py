"""Gate de cobertura (doc 02 §5.4): endpoint novo sem classificação de
isolamento DERRUBA o pipeline. É este teste que transforma a regra do
CLAUDE.md ("nenhum endpoint novo sem caso de isolamento") em verificação
executável."""
from tests.isolation.registry import TENANT_SCOPED, LEGACY_PRE_TENANCY, PUBLIC_INFRA


def _endpoints(app):
    return {r.endpoint for r in app.url_map.iter_rules() if r.endpoint != 'static'}


def test_todo_endpoint_esta_classificado(iso_app):
    atuais = _endpoints(iso_app)
    classificados = set(TENANT_SCOPED) | LEGACY_PRE_TENANCY | PUBLIC_INFRA

    sem_classificacao = atuais - classificados
    assert not sem_classificacao, (
        'Endpoint(s) novo(s) sem classificação de isolamento: '
        f'{sorted(sem_classificacao)}.\n'
        'Registre em tests/isolation/registry.py:\n'
        ' - TENANT_SCOPED (com caso de isolamento em tests/isolation/) se o\n'
        '   endpoint toca dado com tenant_id — regra dura da Release 0.9;\n'
        ' - LEGACY_PRE_TENANCY apenas se a tabela ainda não migrou (Fase 3);\n'
        ' - PUBLIC_INFRA para infra sem dado de domínio.'
    )


def test_registro_sem_entradas_orfas(iso_app):
    """Entrada no registro apontando p/ endpoint inexistente = lixo acumulado."""
    atuais = _endpoints(iso_app)
    classificados = set(TENANT_SCOPED) | LEGACY_PRE_TENANCY | PUBLIC_INFRA
    orfaos = classificados - atuais
    assert not orfaos, f'Entradas órfãs no registry (endpoint não existe): {sorted(orfaos)}'


def test_classificacoes_nao_se_sobrepoem():
    a = set(TENANT_SCOPED) & LEGACY_PRE_TENANCY
    b = set(TENANT_SCOPED) & PUBLIC_INFRA
    c = LEGACY_PRE_TENANCY & PUBLIC_INFRA
    assert not (a | b | c), f'Endpoint em mais de uma classificação: {a | b | c}'


def test_tenant_scoped_indica_teste_existente():
    """Cada entrada TENANT_SCOPED aponta o teste que prova o isolamento."""
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    for endpoint, ref in TENANT_SCOPED.items():
        assert '::' in ref, f'{endpoint}: referência de teste inválida ({ref})'
        arquivo, teste = ref.split('::', 1)
        path = os.path.join(here, arquivo)
        assert os.path.exists(path), f'{endpoint}: arquivo {arquivo} não existe'
        conteudo = open(path).read()
        assert f'def {teste.split("[")[0]}' in conteudo, (
            f'{endpoint}: teste {teste} não encontrado em {arquivo}')
