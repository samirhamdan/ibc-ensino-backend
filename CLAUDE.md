# CLAUDE.md — Contrato do agente (IBC Ensino → XR Educação)

Este repositório é o IBC Ensino em produção, em evolução para a plataforma
multi-tenant **XR Educação**. Fonte de verdade: `docs/` (visão, PRD com IDs de
requisito, arquitetura, arquitetura de IA e playbook da Release 0.9). Leia
`docs/02-ARQUITETURA.md` §3 e o README do módulo antes de implementar qualquer
feature.

## Stack e comandos (estado atual do repo — verificado, não inventado)

- **Stack:** Python 3.12 · Flask 3.0.3 · SQLAlchemy 2.0.51 · PostgreSQL em
  produção (Railway) / SQLite em dev · gunicorn · SPA vanilla JS em
  `index.html` (servida pelo Flask) · CSS em `css/`.
- **Rodar em dev:**
  `python app.py` (porta 5000; usa `.env` via python-dotenv — `.env.example`
  documenta as variáveis; sem `DATABASE_URL` cai em SQLite `instance/`).
- **Rodar como produção (mesmo comando do railway.json):**
  `gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --worker-class gthread "app:create_app('production')"`
  (exige `SECRET_KEY`; `create_app('production')` recusa boot sem ela).
- **Seed de dev:** `python seed.py` (usuários demo, cursos, badges, níveis).
- **Seed de produção:** `python seed_production.py` (idempotente; roda como
  `preDeployCommand` no Railway; admin vem de `ADMIN_EMAIL`/`ADMIN_PASSWORD`).
- **Testes:** `python -m pytest` (suíte de caracterização da Fase 1 em
  `tests/`; SQLite por padrão, `TEST_DATABASE_URL` aponta para Postgres no
  CI). Comportamentos estranhos encontrados vão para `docs/DEBITOS.md`, nunca
  são "corrigidos" dentro de teste de caracterização. A suíte de isolamento
  (`tests/isolation/`, doc 02 §5.4) está ATIVA: todo endpoint precisa estar
  classificado em `tests/isolation/registry.py` — endpoint novo sem caso de
  isolamento (ou classificação legada justificada) derruba o CI.
- **Migrações:** Alembic ativo desde TEN-01 (`alembic upgrade head` /
  `downgrade base`; URL via `DATABASE_URL`). Toda migração é reversível
  (`downgrade` implementado e testado — o job `migrations` do CI roda o ciclo
  completo em Postgres). O schema LEGADO ainda nasce de `db.create_all()` em
  `app.py` e será baselineado no Alembic na Fase 3 do playbook.

## Regras para agentes (doc 02 §3 — aplicáveis a todo PR)

1. Todo model SQLAlchemy de domínio herda de `TenantScopedModel` (inclui
   `tenant_id`, índice composto, política RLS na migração).
2. Nenhum acesso a banco fora de repositórios do módulo; controllers não
   importam models de outros módulos — comunicação entre módulos via serviços
   ou eventos de domínio (`shared/events.py`).
3. Toda feature nova inclui: migração Alembic reversível, testes (incluindo
   caso de isolamento se tocar dados) e atualização do README do módulo.
4. Segredos apenas via variáveis de ambiente; nunca em código ou migração.
5. Chamadas a LLM apenas através de `ai/providers/` (nunca chamar SDK
   diretamente de outro módulo).

*(As regras 1–3 pressupõem a estrutura `app/` da Release 0.9 — doc 02 §3. Até
a migração de estrutura, aplique o espírito delas ao layout atual:
`models.py` + `routes/`.)*

## Convenção de branches e commits

- Branch da release: `release/0.9-tenancy`; branches de etapa por requisito:
  `feat/TEN-01-tenant-model`, `feat/TEN-02-middleware-subdominio`, etc.
- Commits referenciam o ID do requisito do PRD:
  `feat(TEN-02): resolução de tenant por subdomínio`.
  IDs válidos em `docs/01-PRD.md` (TEN/AUTH/CUR/TUT/LRN/GAM/ANL/BIL/ONB/NFR).
- Uma fase do playbook por vez, um PR por etapa; nada vai para `main` sem a
  suíte de isolamento verde (a partir da Fase 2 do playbook).

## Regra dura a partir da Release 0.9

**Nenhum model de domínio pode ser criado sem `tenant_id`.** Todo dado de
domínio pertence a exatamente um tenant (PRD TEN-01); a suíte de isolamento em
CI falha se um endpoint novo não tiver caso de isolamento registrado.

## Débitos e comportamento legado

Durante testes de caracterização (Fase 1), NÃO corrigir comportamento estranho
encontrado — registrar em `docs/DEBITOS.md`. Bugs só são corrigidos fora do
fluxo de caracterização, em commits próprios.
