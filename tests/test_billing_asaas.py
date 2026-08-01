"""BIL-01/02 (PR 2 de 4): cliente HTTP do Asaas (core/billing/asaas.py).

Sem rede real: `requests` é mockado. Foco: timeout/retry configurados
corretamente e a API key nunca aparece em mensagem de exceção.
"""
import os
from unittest.mock import patch, MagicMock

import pytest

from core.billing import asaas


SECRET_KEY_VALUE = 'segredo-super-sensivel-nao-pode-vazar-em-log-nem-excecao'


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv('ASAAS_API_KEY', SECRET_KEY_VALUE)
    monkeypatch.delenv('ASAAS_SANDBOX', raising=False)


def test_base_url_sandbox_vs_producao(monkeypatch):
    monkeypatch.setenv('ASAAS_SANDBOX', 'true')
    assert asaas._base_url() == 'https://api-sandbox.asaas.com/v3'

    monkeypatch.setenv('ASAAS_SANDBOX', 'false')
    assert asaas._base_url() == 'https://api.asaas.com/v3'

    monkeypatch.delenv('ASAAS_SANDBOX', raising=False)
    assert asaas._base_url() == 'https://api.asaas.com/v3'


def test_api_key_lida_apenas_do_ambiente():
    assert asaas._api_key() == SECRET_KEY_VALUE
    assert asaas._headers()['access_token'] == SECRET_KEY_VALUE


def test_api_key_ausente_levanta_erro_sem_hardcode(monkeypatch):
    monkeypatch.delenv('ASAAS_API_KEY', raising=False)
    with pytest.raises(asaas.AsaasError) as exc_info:
        asaas._api_key()
    assert 'ASAAS_API_KEY' in str(exc_info.value)


def test_sessao_configura_timeout_e_retry():
    """_request usa session.request(..., timeout=10) e a Retry do adapter
    está configurada para 3 tentativas com backoff exponencial."""
    with patch('core.billing.asaas.requests.Session.request') as mock_request:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"id": "cus_123"}'
        mock_resp.json.return_value = {'id': 'cus_123'}
        mock_request.return_value = mock_resp

        resultado = asaas._request('GET', '/customers/cus_123')

        assert resultado == {'id': 'cus_123'}
        _, kwargs = mock_request.call_args
        assert kwargs['timeout'] == asaas._TIMEOUT_SECONDS == 10

    # Retry/backoff: inspeciona o adapter montado pela sessão real.
    session = asaas._session()
    adapter = session.get_adapter('https://api.asaas.com/v3/customers')
    assert adapter.max_retries.total == 3
    assert adapter.max_retries.backoff_factor == asaas._BACKOFF_FACTOR
    assert 500 in adapter.max_retries.status_forcelist
    assert 429 in adapter.max_retries.status_forcelist


def test_api_key_nunca_aparece_em_excecao_de_erro_http():
    """Simula um 401 do Asaas (chave inválida) — a mensagem da exceção não
    pode conter a API key em nenhuma hipótese, mesmo que o corpo de erro do
    Asaas mencione algo sobre autenticação."""
    with patch('core.billing.asaas.requests.Session.request') as mock_request:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = 'Unauthorized: invalid access_token header'
        mock_request.return_value = mock_resp

        with pytest.raises(asaas.AsaasError) as exc_info:
            asaas._request('POST', '/customers', {'name': 'Tenant X'})

        assert SECRET_KEY_VALUE not in str(exc_info.value)


def test_api_key_nunca_aparece_em_excecao_de_erro_de_rede():
    import requests as real_requests

    with patch('core.billing.asaas.requests.Session.request') as mock_request:
        mock_request.side_effect = real_requests.exceptions.ConnectionError(
            f'boom while sending access_token={SECRET_KEY_VALUE}'
        )
        with pytest.raises(asaas.AsaasError) as exc_info:
            asaas._request('POST', '/customers', {'name': 'Tenant X'})

        assert SECRET_KEY_VALUE not in str(exc_info.value)


def test_criar_customer_retorna_id():
    tenant = MagicMock(nome='Igreja Teste', id='11111111-1111-1111-1111-111111111111')
    with patch('core.billing.asaas._request', return_value={'id': 'cus_000001'}) as mock_req:
        customer_id = asaas.criar_customer(tenant)
    assert customer_id == 'cus_000001'
    mock_req.assert_called_once()
    metodo, path = mock_req.call_args.args[0], mock_req.call_args.args[1]
    assert metodo == 'POST'
    assert path == '/customers'


def test_criar_customer_sem_id_na_resposta_levanta_erro():
    tenant = MagicMock(nome='Igreja Teste', id='x')
    with patch('core.billing.asaas._request', return_value={}):
        with pytest.raises(asaas.AsaasError):
            asaas.criar_customer(tenant)


def test_criar_subscription_exige_customer_id_previo():
    tenant = MagicMock(nome='Igreja Teste', id='x')
    subscription = MagicMock(asaas_customer_id=None)
    with pytest.raises(asaas.AsaasError, match='asaas_customer_id'):
        asaas.criar_subscription(tenant, 'semente', subscription)


def test_criar_subscription_plano_enterprise_recusa():
    tenant = MagicMock(nome='Igreja Teste', id='x')
    subscription = MagicMock(asaas_customer_id='cus_1')
    with pytest.raises(asaas.AsaasError, match='sob consulta'):
        asaas.criar_subscription(tenant, 'enterprise', subscription)


def test_criar_subscription_ok():
    tenant = MagicMock(nome='Igreja Teste', id='x')
    subscription = MagicMock(asaas_customer_id='cus_1')
    with patch('core.billing.asaas._request', return_value={'id': 'sub_000001'}) as mock_req:
        sub_id = asaas.criar_subscription(tenant, 'semente', subscription)
    assert sub_id == 'sub_000001'
    metodo, path = mock_req.call_args.args[0], mock_req.call_args.args[1]
    assert metodo == 'POST'
    assert path == '/subscriptions'


def test_cancelar_subscription_faz_delete():
    with patch('core.billing.asaas._request', return_value={}) as mock_req:
        asaas.cancelar_subscription('sub_000001')
    mock_req.assert_called_once_with('DELETE', '/subscriptions/sub_000001')


def test_cancelar_subscription_sem_id_levanta_erro():
    with pytest.raises(asaas.AsaasError):
        asaas.cancelar_subscription('')


# ---------------------------------------------------------------------------
# Critério de aceite final (task spec BIL-01/02/03): "em modo sandbox
# (ASAAS_SANDBOX=true), a integração roda end-to-end sem credencial real"
# ---------------------------------------------------------------------------

def test_importar_modulo_sem_nenhuma_credencial_nao_quebra(monkeypatch):
    """Reimportar core.billing.asaas com ASAAS_SANDBOX=true e SEM
    ASAAS_API_KEY setada não levanta nada no import — nenhuma leitura de
    variável de ambiente acontece em nível de módulo (só dentro das
    funções, preguiçosamente, quando uma chamada de verdade acontece)."""
    monkeypatch.setenv('ASAAS_SANDBOX', 'true')
    monkeypatch.delenv('ASAAS_API_KEY', raising=False)
    import importlib
    from core.billing import asaas as asaas_module
    importlib.reload(asaas_module)  # não deve levantar
    assert asaas_module._base_url() == 'https://api-sandbox.asaas.com/v3'


def test_sandbox_sem_api_key_falha_previsivel_nao_crash(monkeypatch):
    """Com ASAAS_SANDBOX=true e SEM ASAAS_API_KEY: uma chamada de verdade
    (criar_customer) falha de forma PREVISÍVEL (AsaasError, com mensagem
    clara pedindo a variável de ambiente) — não um crash genérico
    (KeyError/AttributeError/TypeError) nem um request de rede real sem
    credencial nenhuma. Isto é o que a task spec chama de "roda end-to-end
    sem credencial real": o fluxo não quebra de forma inesperada, ele
    recusa a chamada de forma limpa e identificável antes de qualquer
    request HTTP sair."""
    monkeypatch.setenv('ASAAS_SANDBOX', 'true')
    monkeypatch.delenv('ASAAS_API_KEY', raising=False)

    with patch('core.billing.asaas.requests.Session.request') as mock_request:
        tenant = MagicMock(nome='Igreja Teste', id='x')
        with pytest.raises(asaas.AsaasError) as exc_info:
            asaas.criar_customer(tenant)
        assert 'ASAAS_API_KEY' in str(exc_info.value)
        # nenhuma request de rede sai — falha ANTES de montar a chamada HTTP
        mock_request.assert_not_called()
