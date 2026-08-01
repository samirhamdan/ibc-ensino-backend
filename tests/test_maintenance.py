"""Modo manutenção (Fase 6, docs/PLAYBOOK-MIGRACAO-0.9.md §Produção)."""
import os

import pytest


@pytest.fixture()
def sem_manutencao():
    """Garante estado limpo entre testes — MAINTENANCE_MODE é lido do
    ambiente a cada request, não há cache para resetar."""
    antes_modo = os.environ.pop('MAINTENANCE_MODE', None)
    antes_token = os.environ.pop('MAINTENANCE_BYPASS_TOKEN', None)
    yield
    if antes_modo is not None:
        os.environ['MAINTENANCE_MODE'] = antes_modo
    else:
        os.environ.pop('MAINTENANCE_MODE', None)
    if antes_token is not None:
        os.environ['MAINTENANCE_BYPASS_TOKEN'] = antes_token
    else:
        os.environ.pop('MAINTENANCE_BYPASS_TOKEN', None)


def test_sem_maintenance_mode_nada_muda(client, sem_manutencao):
    assert client.get('/health').status_code == 200
    assert client.get('/api/courses').status_code in (200, 401)


def test_maintenance_mode_bloqueia_api_com_json_503(client, sem_manutencao):
    os.environ['MAINTENANCE_MODE'] = 'true'
    r = client.get('/api/courses')
    assert r.status_code == 503
    assert 'Manutenção' in r.get_json()['error']


def test_maintenance_mode_bloqueia_html_com_pagina_503(client, sem_manutencao):
    os.environ['MAINTENANCE_MODE'] = 'true'
    r = client.get('/')
    assert r.status_code == 503
    assert 'Manutenção programada' in r.get_data(as_text=True)


def test_health_sempre_passa_mesmo_em_manutencao(client, sem_manutencao):
    """Monitoração externa (uptime) não pode confundir manutenção
    planejada com o serviço fora do ar."""
    os.environ['MAINTENANCE_MODE'] = 'true'
    assert client.get('/health').status_code == 200


def test_bypass_token_libera_smoke_de_producao(client, sem_manutencao):
    """Playbook §6 passo 5: smoke test de produção roda ENQUANTO a
    manutenção ainda protege o público geral, antes do OFF."""
    os.environ['MAINTENANCE_MODE'] = 'true'
    os.environ['MAINTENANCE_BYPASS_TOKEN'] = 'segredo-do-ensaio'

    sem_bypass = client.get('/api/courses')
    assert sem_bypass.status_code == 503

    com_bypass = client.get('/api/courses', headers={'X-Maintenance-Bypass': 'segredo-do-ensaio'})
    assert com_bypass.status_code != 503

    com_token_errado = client.get('/api/courses', headers={'X-Maintenance-Bypass': 'chute'})
    assert com_token_errado.status_code == 503


def test_maintenance_mode_valores_falsy_nao_ativam(client, sem_manutencao):
    for valor in ('', '0', 'false', 'off', 'nada'):
        os.environ['MAINTENANCE_MODE'] = valor
        assert client.get('/health').status_code == 200
        assert client.get('/api/courses').status_code != 503
