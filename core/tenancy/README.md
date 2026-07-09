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

## Suíte de isolamento (Etapa 2.3 — NFR-01)

- `tests/isolation/` — casos de isolamento (A não alcança dados de B por
  contexto, ID, listagem) + **gate de cobertura**: todo endpoint da aplicação
  precisa estar classificado em `tests/isolation/registry.py`
  (TENANT_SCOPED com teste · LEGACY_PRE_TENANCY · PUBLIC_INFRA); endpoint
  novo sem classificação DERRUBA o pipeline. Job `isolation-suite` do CI
  roda a suíte em Postgres — configurar como required check.
- Na Fase 3, cada grupo de tabelas migradas move seus endpoints de
  LEGACY_PRE_TENANCY para TENANT_SCOPED com casos novos.

## Fase 3 — migração das tabelas de domínio (em andamento)

- **Grupo 1 (gamificação) MIGRADO:** user_points, badge, user_badge,
  achievements, user_achievements, certificates, activity_feed com tenant_id
  NOT NULL + FK (migrações 0003–0005, expand → backfill → contract, todas
  reversíveis). Uniques convertidos para por-tenant: (tenant_id, user_id) em
  user_points e (tenant_id, code) em badge/achievements.
- Escritas escopam automaticamente via default do mixin
  (`current_tenant_id()`); leituras filtram explicitamente em cada query.
- **Modo mono-tenant:** sem tenant resolvido, `current_tenant_id()` usa o
  tenant padrão (`DEFAULT_TENANT_SLUG`, default `ibc`) — produção atual segue
  idêntica até o DNS da Fase 6.
- Baseline do legado: migração 0002 (checkfirst; downgrade só em ambiente
  descartável — runbook: produção nunca desce abaixo de 0002).
- `railway.json`: preDeployCommand roda `alembic upgrade head` antes do seed.
- **Grupo 2 (progresso) MIGRADO:** lesson_progress, progress,
  study_sessions, user_trails, onboarding_answers (migrações 0006–0008;
  onboarding_answers.user_id vira unique por tenant). 18 endpoints movidos
  para TENANT_SCOPED no registry.
- **Grupo 3 (conteúdo) MIGRADO — TEN-01 completo:** categories, courses,
  modules, materials, quiz, questions, trails, trail_courses, tutor_courses,
  announcements, notifications, announcement_dismissals (migrações
  0009–0011; categories.name vira unique por tenant). Helpers
  `get_scoped()`/`get_scoped_or_404()` substituem os gets por PK (recurso de
  outro tenant → 404, nunca 403). ~160 queries escopadas no total.
- Fora do escopo de tenant (com justificativa no registry): users (global
  por design — papéis por tenant na Fase 4), PlatformConfig/Level (config
  global legada, DEBITOS #1).

## RLS — defesa em profundidade (Etapa 4.1)

- Migração 0012: ENABLE + FORCE ROW LEVEL SECURITY + política
  `tenant_isolation` em TODAS as 25 tabelas com tenant_id (PostgreSQL;
  no-op com aviso em SQLite). Fail-closed: sem `app.tenant_id`, zero linhas.
- `core/tenancy/rls.py`: SET LOCAL `app.tenant_id` por transação (listener
  de Session; `set_config(..., true)` parametrizado — nunca SET de sessão).
- Migrações usam `ALEMBIC_DATABASE_URL` (role privilegiada) — com FORCE
  RLS, migração como role de app atualizaria 0 linhas.
- **Ativação em produção é operacional**: docs/RUNBOOK-RLS.md (criar role
  `ibc_app` sem BYPASSRLS e trocar a DATABASE_URL do serviço). Até lá o
  RLS é inócuo (superuser bypassa).
- Prova em CI: tests/test_rls.py — query SEM filtro de aplicação não lê
  nem escreve outro tenant; sem GUC → zero linhas; superuser bypassa (por
  isso a role importa).

## Próximos passos no módulo

- Etapa 4.2: JWT com claims de tenant; papéis migram para tenant_users.
- Etapa 4.3: Redis (cache de tenant, rate limiting, base para RQ).
