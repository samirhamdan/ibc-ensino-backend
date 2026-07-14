"""
Cliente HTTP do Asaas — BIL-01/02 (doc 02-ARQUITETURA.md §7), PR 2 de 4.

DECISÃO DOCUMENTADA (síncrono, não RQ): o playbook (§4.8) diz "rodar via
worker RQ quando possível", mas este repo ainda não tem infraestrutura de
worker/fila (nenhum `workers/`, nenhum RQ configurado — confirmado na
pesquisa da PR 1). Construir a fila inteira é escopo maior que "modelo de
dados + cliente HTTP + webhook" desta PR. As chamadas ficam síncronas por
ora, mas isoladas neste módulo (nenhum outro código chama a API do Asaas
diretamente — regra 5 do CLAUDE.md, adaptada de "LLM" pra "provider externo"
pelo mesmo espírito) para que uma PR futura troque a implementação por
`enqueue(criar_customer, ...)` sem tocar em quem chama. Ver docs/DEBITOS.md.

AVISO: os paths de endpoint abaixo (`/customers`, `/subscriptions`,
`/subscriptions/{id}`) seguem a convenção típica de REST v3 documentada
publicamente pelo Asaas, mas não foram verificados contra a documentação
oficial nem contra uma chave real neste ambiente — são uma estrutura
razoável para destravar o resto do módulo (modelo de dados, webhook,
idempotência) e devem ser conferidos contra https://docs.asaas.com antes de
usar com uma chave de produção real.

Segredo: a API key SÓ é lida de `os.environ['ASAAS_API_KEY']`, nunca
hardcoded, nunca logada, nunca incluída em mensagem de exceção (testado em
tests/test_billing_asaas.py — a asserção é direta, não só documentada).
"""
import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_TIMEOUT_SECONDS = 10
_MAX_RETRIES = 3
_BACKOFF_FACTOR = 1  # urllib3: espera backoff_factor * (2 ** (tentativa - 1))


class AsaasError(Exception):
    """Erro de chamada à API do Asaas. A mensagem NUNCA inclui a API key —
    só código HTTP e um trecho do corpo de resposta (que é do Asaas, não
    nosso segredo)."""


def _base_url():
    sandbox = os.environ.get('ASAAS_SANDBOX', '').strip().lower() in ('1', 'true', 'yes', 'on')
    return 'https://api-sandbox.asaas.com/v3' if sandbox else 'https://api.asaas.com/v3'


def _api_key():
    key = os.environ.get('ASAAS_API_KEY')
    if not key:
        # Mensagem propositalmente sem interpolar `key` (é None/vazio aqui,
        # mas o padrão vale mesmo se um dia isso mudar): nunca montar essa
        # string a partir do valor do segredo.
        raise AsaasError(
            'ASAAS_API_KEY não configurada — defina a variável de ambiente '
            '(nunca em código/migração, CLAUDE.md regra 4).'
        )
    return key


def _session():
    """Sessão `requests` com timeout curto e retry com backoff exponencial
    (3 tentativas) em erros de rede e em respostas 5xx/429 — os únicos casos
    em que repetir a MESMA chamada é seguro (POST de criação idealmente
    seria idempotente via chave do Asaas; como este cliente ainda não usa
    idempotency key do lado do Asaas, ver nota abaixo)."""
    retry = Retry(
        total=_MAX_RETRIES,
        backoff_factor=_BACKOFF_FACTOR,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(('GET', 'POST', 'DELETE', 'PUT')),
        raise_on_status=False,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


def _headers():
    # header 'access_token' é a convenção do Asaas v3 (não Bearer/Authorization)
    return {
        'access_token': _api_key(),
        'Content-Type': 'application/json',
        'User-Agent': 'ibc-ensino-billing/1.0',
    }


def _request(method, path, json_body=None):
    url = f'{_base_url()}{path}'
    try:
        resp = _session().request(
            method, url, json=json_body, headers=_headers(), timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        # str(exc) de uma exceção de rede do `requests` não inclui headers
        # nem a API key (só URL e a causa) — mesmo assim, não repassamos o
        # exc original bruto: construímos uma mensagem própria, curta, sem
        # nada do request (defesa em profundidade).
        raise AsaasError(f'Falha de rede ao chamar Asaas ({method} {path}): {type(exc).__name__}') from None

    if resp.status_code >= 400:
        # resp.text é a resposta do Asaas (nunca contém nossa API key —
        # é o corpo que ELES devolvem); ainda assim, cortamos o tamanho.
        corpo = (resp.text or '')[:300]
        raise AsaasError(f'Asaas respondeu {resp.status_code} em {method} {path}: {corpo}')

    if not resp.content:
        return {}
    return resp.json()


def criar_customer(tenant):
    """Cria um customer no Asaas para o tenant e retorna o `asaas_customer_id`.
    Não persiste no banco — quem chama decide onde/quando salvar em
    `Subscription.asaas_customer_id` (mesma convenção de publish_event: esta
    função não faz commit nem grava model)."""
    payload = {
        'name': tenant.nome,
        'externalReference': str(tenant.id),
    }
    data = _request('POST', '/customers', payload)
    customer_id = data.get('id')
    if not customer_id:
        raise AsaasError('Resposta do Asaas sem "id" ao criar customer')
    return customer_id


def criar_subscription(tenant, plano, subscription, ciclo='MONTHLY'):
    """Cria uma assinatura recorrente no Asaas (Pix/boleto/cartão — BIL-02).
    `subscription` é a linha `core.billing.models.Subscription` do tenant —
    já precisa ter `asaas_customer_id` preenchido (chamar criar_customer()
    antes). Retorna o `asaas_subscription_id`; não persiste — quem chama
    decide onde/quando salvar (mesma convenção de criar_customer)."""
    from core.billing.plans import get_plan
    plano_obj = get_plan(plano)
    if plano_obj.preco_mensal_brl is None:
        raise AsaasError(f'Plano {plano_obj.nome} é sob consulta — não tem cobrança recorrente automática')

    customer_id = getattr(subscription, 'asaas_customer_id', None)
    if not customer_id:
        raise AsaasError('Subscription sem asaas_customer_id — chame criar_customer() primeiro')

    payload = {
        'customer': customer_id,
        'billingType': 'UNDEFINED',  # Asaas decide Pix/boleto/cartão na tela de pagamento
        'value': plano_obj.preco_mensal_brl,
        'cycle': ciclo,
        'description': f'Assinatura {plano_obj.nome} — {tenant.nome}',
        'externalReference': str(tenant.id),
    }
    data = _request('POST', '/subscriptions', payload)
    subscription_id = data.get('id')
    if not subscription_id:
        raise AsaasError('Resposta do Asaas sem "id" ao criar subscription')
    return subscription_id


def cancelar_subscription(subscription_id):
    """Cancela (DELETE) uma assinatura no Asaas pelo `asaas_subscription_id`."""
    if not subscription_id:
        raise AsaasError('subscription_id vazio')
    return _request('DELETE', f'/subscriptions/{subscription_id}')
