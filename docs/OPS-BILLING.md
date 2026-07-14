# OPS-BILLING — operação do módulo de billing (BIL-01/02/03)

Guia operacional pro módulo `core/billing/` (doc 02-ARQUITETURA.md §4.8,
§7). **Aviso honesto**: os passos contra a API do Asaas abaixo não foram
verificados contra uma conta/credencial real neste ambiente (ver aviso em
`core/billing/asaas.py`) — são a melhor orientação possível a partir do
código deste repo e da documentação pública do Asaas
(https://docs.asaas.com), não um runbook testado ponta a ponta em produção.
Antes de rodar contra produção pela primeira vez, valide cada passo em
sandbox (`ASAAS_SANDBOX=true`) e confira contra a documentação oficial mais
recente do Asaas.

## Variáveis de ambiente exigidas

Já documentadas em `.env.example` (seção "Billing — Asaas"), confirmadas
atuais nesta PR:

| Variável | Obrigatória | Descrição |
|---|---|---|
| `ASAAS_API_KEY` | sim (fora de teste) | Chave de API do Asaas. Nunca em código/migração (CLAUDE.md regra 4). Lida só em `os.environ` (`core/billing/asaas.py::_api_key`), nunca logada. |
| `ASAAS_WEBHOOK_TOKEN` | sim (fora de teste) | Token esperado no header `Asaas-Access-Token` do webhook (`POST /billing/webhook/asaas`). Sem ela configurada, **nenhum** webhook é aceito (fail-closed, `core/billing/routes.py::_token_valido`). Gerar com `openssl rand -hex 32` e cadastrar o mesmo valor no painel do Asaas → Integrações → Webhooks. |
| `ASAAS_SANDBOX` | não (default produção) | Truthy (`1`/`true`/`yes`/`on`) usa `api-sandbox.asaas.com`; vazio/ausente usa `api.asaas.com`. |

`SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASS`/`EMAIL_FROM_NAME` já
existiam em `.env.example` (usadas por `routes/auth.py::forgot_password`
desde antes deste módulo) — a régua de inadimplência (`core/billing/
regua.py::_enviar_email_billing`) reaproveita o MESMO mecanismo/variáveis,
não precisa de nada novo. Confirmado nesta PR: segue igual, nenhuma
variável nova de e-mail necessária.

## Critério de aceite: sandbox sem credencial real

A task spec original exige que "em modo sandbox (`ASAAS_SANDBOX=true`), a
integração roda end-to-end sem credencial real". Verificado concretamente
nesta PR (`tests/test_billing_asaas.py::test_importar_modulo_sem_nenhuma_credencial_nao_quebra`
e `::test_sandbox_sem_api_key_falha_previsivel_nao_crash`):

- Importar `core/billing/asaas.py` com `ASAAS_SANDBOX=true` e **sem**
  `ASAAS_API_KEY` não levanta nada — nenhuma variável de ambiente é lida em
  nível de módulo, só dentro de cada função, no momento da chamada.
- Uma chamada de verdade (`criar_customer`, `criar_subscription`,
  `cancelar_subscription`) sem `ASAAS_API_KEY` falha com `AsaasError`
  (mensagem clara, pedindo a variável) **antes** de qualquer request HTTP
  sair (nenhuma tentativa de rede sem credencial) — não um crash genérico
  nem uma chamada real sem autenticação.
- "Roda end-to-end" aqui significa: o restante do fluxo (webhook, régua,
  medição) não depende de rede/Asaas nenhuma para funcionar em
  desenvolvimento/CI — só as 3 funções de `core/billing/asaas.py` (que
  fazem chamada de rede de verdade) exigem a chave.

## Criar uma assinatura manualmente para o primeiro tenant

Sem painel de checkout self-service ainda (fora do escopo desta release) —
o fluxo abaixo é manual, via shell Python (`flask shell` ou
`python -c`) dentro do app context.

1. Confirmar que o tenant e a `Subscription` (pendente) já existem — a
   `Subscription` nasce com `status='pending'` no momento em que o tenant é
   provisionado (fora do escopo desta PR — quem cria a linha inicial é o
   fluxo de onboarding/ONB, não `core/billing/`).

2. Criar o customer no Asaas e persistir o id:

   ```python
   from core.billing.asaas import criar_customer
   from core.billing.models import Subscription
   from core.tenancy.models import Tenant
   from extensions import db

   tenant = Tenant.query.filter_by(slug='SLUG-DO-TENANT').first()
   sub = Subscription.query.filter_by(tenant_id=tenant.id).first()

   sub.asaas_customer_id = criar_customer(tenant)
   db.session.commit()
   ```

3. Criar a assinatura recorrente e persistir o id:

   ```python
   from core.billing.asaas import criar_subscription

   sub.asaas_subscription_id = criar_subscription(tenant, sub.plano, sub, ciclo='MONTHLY')
   db.session.commit()
   ```

4. Cadastrar (ou confirmar já cadastrada) a URL do webhook no painel do
   Asaas: `https://SEU-DOMINIO/billing/webhook/asaas`, com o header
   `Asaas-Access-Token` = mesmo valor de `ASAAS_WEBHOOK_TOKEN`.

5. A partir daqui, `sub.status` e `tenant.billing_status` são atualizados
   automaticamente pelos eventos que o Asaas envia ao webhook (pagamento
   confirmado/atrasado — `core/billing/routes.py::webhook_asaas`) — não há
   passo manual recorrente.

**Alternativa via dashboard do Asaas**: os mesmos 2 recursos (customer +
subscription) podem ser criados direto na UI do Asaas (Clientes → Novo
Cliente; Cobranças → Nova Assinatura) — nesse caso, o passo manual
adicional é copiar o `customer_id`/`subscription_id` gerado pela UI de
volta para `Subscription.asaas_customer_id`/`asaas_subscription_id` no
banco (senão o webhook nunca resolve o tenant — `docs/DEBITOS.md` #24/#26).

## Processar um reembolso

O que o Asaas oferece (via painel ou API `POST /payments/{id}/refund`):
estorno total ou parcial de um pagamento já confirmado (Pix/cartão —
boleto pago não é estornável pela API do Asaas, é tratado manualmente pelo
suporte deles).

**O que este código NÃO automatiza** (nenhuma função em
`core/billing/asaas.py` chama `/payments/{id}/refund` — fora do escopo das
4 PRs desta release, que cobriram customer/subscription/cancelamento, não
reembolso avulso de pagamento): reembolso hoje é 100% manual, feito
diretamente no painel do Asaas (Cobranças → localizar o pagamento →
Estornar). Depois de estornar no painel, se o reembolso também deveria
mudar o estado da assinatura no XR Educação (ex.: voltar `billing_status`
pra algo diferente de `'ativo'`, ou cancelar a `Subscription`), isso
também é manual — nenhum webhook de reembolso é tratado por
`core/billing/routes.py::webhook_asaas` (só os 4 eventos em
`_EVENTO_ASAAS_PARA_STATUS`: `PAYMENT_CONFIRMED`, `PAYMENT_RECEIVED`,
`PAYMENT_OVERDUE`, `PAYMENT_DELETED`).

## Pausar a régua para negociação (override do operador)

A régua de inadimplência (`core/billing/regua.py::executar_regua`) sobe
qualquer tenant `overdue` para `'leitura'` em D+10 e `'suspenso'` em D+30,
sem exceção — até esta PR, não havia como um operador pausar essa
progressão automática para um tenant específico em negociação (ex.: cliente
grande combinando um parcelamento, prazo extra acordado por telefone).

**Mecanismo (adicionado nesta PR)**: `Subscription.regua_pausada`
(booleano, default `False`, migração `0018`). Enquanto `True`, a consulta
de candidatos da régua (`core/billing/regua.py::_candidatos_overdue`)
ignora esse tenant inteiramente — ele continua com `status='overdue'` na
`Subscription` (o Asaas não muda isso), mas a régua não transiciona
`billing_status` nem envia e-mail de cobrança enquanto o flag estiver
ligado.

Ativar/desativar via shell (não há rota HTTP nesta PR — mesma superfície de
acesso operacional que `scripts/regua_cobranca.py`, que também roda fora de
uma request):

```python
from core.billing.regua import pausar_regua
from core.tenancy.models import Tenant

tenant = Tenant.query.filter_by(slug='SLUG-DO-TENANT').first()

# Pausar (início da negociação):
pausar_regua(tenant.id, pausar=True)

# Retomar (negociação concluída/cancelada — a régua volta a avaliar D+10/D+30
# a partir do overdue_desde ATUAL na próxima execução, não retroage):
pausar_regua(tenant.id, pausar=False)
```

Importante: pausar a régua **não** move o tenant de volta para
`billing_status='ativo'` nem impede o `billing_status` que ela JÁ tinha
setado antes da pausa — só congela transições FUTURAS enquanto o flag
estiver ligado. Se o tenant já está `'leitura'`/`'suspenso'` quando a
negociação começa e o operador quer liberar acesso durante a negociação,
isso é uma ação SEPARADA (mudar `tenant.billing_status` manualmente) — a
régua pausada não desfaz o que já foi feito.

## Referências

- `core/billing/README.md` — visão do módulo, o que cada PR das 4 entregou.
- `docs/DEBITOS.md` #24-#27 — decisões/riscos conhecidos do módulo
  (resolução de tenant no webhook, chamadas síncronas ao Asaas, RLS via
  conexão raw, divergência `Tenant.plano`/`Subscription.plano`).
- `docs/RUNBOOK-RLS.md` — contexto da troca de role RLS que afeta as
  consultas cross-tenant deste módulo (webhook, régua).
