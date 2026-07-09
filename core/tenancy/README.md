# core/tenancy — Fundação de multi-tenancy (TEN-01/TEN-02)

Módulo criado na Fase 2 do playbook (docs/PLAYBOOK-MIGRACAO-0.9.md).
Referências: docs/02-ARQUITETURA.md §4–5 · docs/01-PRD.md TEN-01..05.

## O que existe (Etapa 2.1)

- **`Tenant`** — tabela `tenants` (UUIDv7, slug, subdomínio, plano, status,
  tema TEN-03). Gerenciada por Alembic (migração 0001).
- **`TenantUser`** — papéis por tenant (AUTH-01). `user_id` ainda SEM FK no
  banco (users é legado fora do Alembic até a Fase 3 — ver docstring).
- **`TenantScopedModel`** — mixin obrigatório para todo model de domínio a
  partir da 0.9: `tenant_id` (FK tenants) + índice composto `(tenant_id, id)`.
  RLS por tabela entra na Fase 4.
- **Contexto de request** — `set_current_tenant()` / `current_tenant()` /
  `require_tenant()` (404 sem tenant, 403 suspenso). Nenhuma rota legada usa
  ainda; o middleware de subdomínio (Etapa 2.2) é quem popula.
- **`uuid7()`** — UUIDv7 próprio (Python 3.12 não tem nativo); evita IDs
  sequenciais (vazamento indireto, doc 02 §5.5).

## Migrações

- `alembic upgrade head` / `alembic downgrade base` (URL vem de
  `DATABASE_URL`; sem ela, SQLite `instance/ibc_ensino.db`).
- Toda migração deste módulo é reversível — o job `migrations` do CI roda
  upgrade → downgrade → upgrade em Postgres.
- Em dev/teste o `db.create_all()` também cria as tabelas novas (create_all
  pula as existentes) — conveniência até o schema legado ser baselineado.

## Seeds

`seed.py::seed_tenants()` cria os tenants `ibc` e `demo` (idempotente).

## Middleware de resolução (Etapa 2.2 — TEN-02)

- `init_tenant_middleware(app)` registra o `before_request`: subdomínio sob
  `TENANT_BASE_DOMAIN` → `g.tenant` (um `TenantContext`, snapshot leve — não
  objeto ORM); inexistente → **404 institucional**; suspenso → **403
  explicativo** (TEN-04). Hosts fora do domínio-base (Railway/localhost)
  seguem SEM tenant — paridade total com a produção atual até a Fase 6.
- Cache em memória com TTL 60s (`clear_tenant_cache()` invalida; Redis entra
  na Fase 4). O TTL satisfaz o aceite "suspensão vale em <60s".
- Dev/teste: header `X-Tenant-Slug` como override (desligado em produção).
- `GET /api/tenant/current` devolve o tenant do contexto (404 fora dele) —
  é como o frontend aplicará o tema do tenant (TEN-03).

## Próximos passos no módulo

- Etapa 2.3: suíte `tests/isolation/` (doc 02 §5.4) — required no CI.
- Fase 4: RLS + claims de tenant no JWT; cache do middleware migra p/ Redis.
