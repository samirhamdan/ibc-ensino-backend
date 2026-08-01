# core/billing — Billing, Asaas e medição de consumo (BIL-01/02/03)

Módulo construído em 4 PRs sob a Release 1.0 (docs/02-ARQUITETURA.md §3/§4.8,
docs/01-PRD.md BIL-01/02/03). Vive em `core/billing/` (não
`app/core/billing/`) pelo mesmo motivo documentado em `core/tenancy/`: um
pacote `app/` no nível raiz sombrearia `app.py`/`app:create_app`
(gunicorn/railway.json) — move na reestruturação completa da Release 1.0.

Operação/runbook (Asaas manual, reembolso, pausar régua): `docs/OPS-BILLING.md`.
Decisões/riscos conhecidos: `docs/DEBITOS.md` #24-#27.

## O que existe

- **`plans.py`** — catálogo `PLANOS` (Semente/Crescimento/Comunidade/
  Enterprise): `limite_alunos`, `cota_interacoes_ia_mes`, `preco_mensal_brl`
  (Enterprise = `None`/"sob consulta" nos 3 campos que fazem sentido).
  Números de cota são estimativa de primeira passada (ver docstring do
  módulo), não modelagem de custo real.
- **`models.py`**:
  - `Subscription` (1 por tenant, `tenant_id` UNIQUE) — plano, status
    (`pending|active|overdue|suspended|canceled`), ids do Asaas,
    `overdue_desde` (régua), `regua_pausada` (override do operador, PR 4).
  - `WebhookEvent` — idempotência de webhooks Asaas (`event_id` único
    globalmente, chave `evento:payment_id`).
  - `AiUsage` (1 por tenant+período `'YYYY-MM'`) — agregado mensal de
    interações/tokens/custo de IA + `alerta_80pct_enviado` (PR 4).
- **`asaas.py`** — cliente HTTP síncrono (`criar_customer`,
  `criar_subscription`, `cancelar_subscription`); retry/timeout via
  `requests` + `HTTPAdapter`; `ASAAS_API_KEY` só de `os.environ`, nunca
  logada. Endpoints REST v3 não verificados contra credencial real
  (aviso no topo do módulo) — ver docs/OPS-BILLING.md.
- **`routes.py`** — `POST /billing/webhook/asaas`: token via header
  `Asaas-Access-Token` (`hmac.compare_digest`), idempotência real via
  `WebhookEvent`, resolução de tenant a partir do payload (NUNCA fallback
  pro tenant padrão — docs/DEBITOS.md #24/#26).
- **`regua.py`** — `executar_regua(hoje=None)`: D+10 overdue →
  `billing_status='leitura'`, D+30 → `'suspenso'`; idempotente por
  construção (olha o `billing_status` atual antes de agir); e-mail ao admin
  via o mesmo SMTP de `routes/auth.py`. `pausar_regua(tenant_id, pausar)`
  (PR 4) — override do operador, ver docs/OPS-BILLING.md.
- **`middleware.py`** — `init_billing_middleware`: `'leitura'` bloqueia
  mutações (402), `'suspenso'` bloqueia tudo, exceções `/billing/*`,
  `/health`, `/api/theme`.
- **`metering.py`** (PR 4, BIL-03) — STUB de medição de consumo de IA, sem
  chamar nenhum provedor: `registrar_interacao_ia`, `consumo_do_tenant`,
  `checar_cota` (publica `ai.cota_80pct` uma vez por período ao cruzar
  80%). Ver docstring do módulo para o raciocínio de tenant explícito/GUC —
  toda função recebe `tenant_id` como parâmetro e nunca lê
  `current_tenant_id()`/`g.tenant` implicitamente, porque será chamada de
  contextos variados (rotas de `ai/`, futuro worker).

## Migrações

`0015_billing_tables` (Subscription/WebhookEvent/AiUsage/DomainEvent/
AuditLog/billing_status, RLS) → `0016_billing_webhook_events` →
`0017_subscription_overdue_desde` → `0018_billing_metering_columns`
(`ai_usage.alerta_80pct_enviado`, `subscriptions.regua_pausada`). Todas
reversíveis, testadas via `alembic upgrade head` → `downgrade base` →
`upgrade head` (SQLite + subprocess, mesmo padrão dos outros módulos).

## RLS / GUC — padrão recorrente neste módulo

Toda tabela de domínio deste módulo tem RLS (regra 1 do CLAUDE.md), e o
listener de `core/tenancy/rls.py` só fixa o GUC `app.tenant_id` a partir de
`g.tenant`. Três lugares neste módulo processam dados de um tenant SEM
`g.tenant` já resolvido (webhook global, régua cross-tenant, medição
chamada por parâmetro explícito) — todos usam o mesmo padrão: resolver o
`Tenant` via consulta que não depende de RLS (raw connection ou a tabela
`tenants`, que não tem RLS), depois `set_current_tenant()` +
`db.session.rollback()` antes de qualquer leitura/escrita ORM
tenant-scoped. Ver docs/DEBITOS.md #26 e a docstring de cada arquivo.

## Testes

`tests/test_billing.py` (modelos/migração 0015) ·
`tests/test_billing_asaas.py` (cliente HTTP, incluindo sandbox sem
credencial) · `tests/test_billing_webhook.py` (idempotência, isolamento,
fim-a-fim webhook→régua) · `tests/test_billing_regua.py` (limiares D+10/D+30
com clock mockado) · `tests/test_billing_middleware.py` · `tests/
test_billing_metering.py` (medição, cota, evento 80%, pausar régua).
