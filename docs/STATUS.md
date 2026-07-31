# STATUS DE IMPLEMENTACAO — Auditoria completa (31 jul 2026)

Levantamento automatizado cruzando docs de UX/roadmap com codigo e commits.
Nenhuma implementacao foi feita neste documento — apenas registro.

---

## UX_ALUNO_SAAS.md

| Modulo | Item | Status | Commit | Falta |
|--------|------|--------|--------|-------|
| Dashboard | Grupo 1 — Saudacao + streak chip + frase contexto | DONE | `67a9f7b` | — |
| Dashboard | Grupo 2 — Continue seus estudos (hero + cards) | DONE | `67a9f7b` | — |
| Dashboard | Grupo 3 — Sua Pontuacao (XP, nivel, badges) | DONE | `67a9f7b` | — |
| Dashboard | Grupo 4 — Proximas Metas | DONE | `67a9f7b` | — |
| Dashboard | Grupo 5 — Recomendacoes (carrossel Netflix) | DONE | `67a9f7b` | — |
| Dashboard | 4 estados por grupo (skeleton, vazio, erro, conteudo) | DONE | `8bc391c` | — |
| Dashboard | Polish P0.1-P0.5 (hero hierarchy, score card, copy, gradient) | DONE | `8bc391c`, `353a220` | — |
| Dashboard | Polish P1.1-P1.5 (affordance) | DONE | `dff50b0` | — |
| Dashboard | Slot TUT-01 (botao tutor no grupo 2) | OPEN | — | Adiado p/ Release 1.0 (§7) |
| Dashboard | Slot LRN-02 (revisao do dia com dados reais no grupo 4) | OPEN | — | Adiado p/ Release 1.0 (§7) |

## ROADMAP.md §2.8 — Blocos A e C

| Modulo | Item | Status | Commit | Falta |
|--------|------|--------|--------|-------|
| Player (A) | A1 — Modo foco com rail de progresso | DONE | `92ce794` | — |
| Player (A) | A2 — "Proximo" persistente, aposentar overlay | DONE | `4f78cce` | — |
| Player (A) | A3 — Progresso real de video via player API | DONE | `ac05a52` | — |
| Player (A) | A4 — Legendas e velocidade nativos | DONE | `af95059` | — |
| Curso (C) | C1 — Hero + CTA unico de retomada | DONE | `331473a` | — |
| Curso (C) | C2 — Accordion de aulas (substitui tabs) | DONE | `2a3db1b` | — |
| Curso (C) | C3 — Rail lateral (certificado, metadados, skills) | DONE | `a841d4e` | — |
| Curso (C) | C4 — Emojis → icones vetoriais | DONE | `331473a` | — |

## UX_ADMIN_SAAS (spec nao existe como doc — avaliado contra codigo)

| Modulo | Item | Status | Commit | Falta |
|--------|------|--------|--------|-------|
| Admin | Tela "Hoje" (3 zonas: fila de atencao, pulso, atividade) | PARCIAL | — | Dados existem em `/api/dashboards/admin/dashboard` mas sem tela dedicada |
| Admin | Navegacao lateral (7 itens redesenhados) | PARCIAL | — | Sidebar legado existe; redesign nao implementado |
| Admin | Busca global de pessoas + perfil slide-over | PARCIAL | — | Search param no endpoint de users existe; sem slide-over UI |
| Admin | Desempenho por curso (funil de abandono) | PARCIAL | — | Dropout % calculado em alertas; sem tela de funil |
| Admin | Importacao CSV com preview | NAO INICIADO | — | Nenhum codigo encontrado |

## UX_OPERADOR_SAAS (spec nao existe como doc)

| Modulo | Item | Status | Commit | Falta |
|--------|------|--------|--------|-------|
| Operador | Painel Pulso v1 | NAO INICIADO | — | Sem dashboard de operador |
| Operador | Tela Tenants (lista + perfil + criar/suspender) | NAO INICIADO | — | Sem CRUD de tenants para operador |
| Operador | Tela Receita (Asaas + regua de inadimplencia) | NAO INICIADO | — | Sem tela de receita |
| Operador | Auditoria de acoes do operador | NAO INICIADO | — | Sem audit trail |

## SAAS_ROADMAP.md — Bloco 2 (Multi-Tenant)

| Modulo | Item | Status | Commit | Falta |
|--------|------|--------|--------|-------|
| Tenancy | tenant_id em todas as tabelas de dominio (26 models) | DONE | migrations 0001-0016 | — |
| Tenancy | White-label (cores/logo por tenant via tema_json) | DONE | `31ac49d` | — |
| Tenancy | Subdominio por cliente (resolucao + cache) | DONE | middleware.py | — |
| Tenancy | Middleware de isolamento (contexto + sessao + RLS) | DONE | isolation test suite | — |

## Billing (branch `feat/BIL-01-asaas` — NAO MERGEADO)

| Modulo | Item | Status | Commit | Falta |
|--------|------|--------|--------|-------|
| Billing | BIL-01: Planos + modelo de dados (Subscription, WebhookEvent) | DONE (unmerged) | `3844bd4` | Merge/rebase na main |
| Billing | BIL-02: Cliente Asaas + webhook + idempotencia | DONE (unmerged) | `f8cfabf` | Merge/rebase na main |
| Billing | BIL-02: Regua de cobranca D+10/D+30 + middleware 402 | DONE (unmerged) | `2f03650` | Merge/rebase na main |
| Billing | BIL-03: Metering de consumo IA | PARCIAL (stub, unmerged) | `04d42b3` | Implementacao completa + merge |

## Outros itens rastreados

| Modulo | Item | Status | Commit | Falta |
|--------|------|--------|--------|-------|
| Performance | N+1 dashboards (batch_completion) | DONE | `52ebcd7` | — |
| Performance | N+1 gamification (_completed_courses_count) | DONE | `52ebcd7` | — |
| Performance | N+1 em list_tutors, list_users, admin_list_trails | DESEJAVEL | — | Nao critico no volume atual |
| Seguranca | Rate limiting (login 10/min, forgot-password 5/hr) | DONE | Flask-Limiter | — |
| Seguranca | Revisao de seguranca (enumeracao, XSS, IDOR) | DONE | commits jul/2026 | — |
| Progresso | Unificacao Progress/LessonProgress | ADIADO | — | Fase 3; teste de convergencia ativo (`test_progress_convergence.py`) |
| Error handling | api() interceptor (401/5xx/network) + toasts | DONE | `a841d4e` | — |
| Error handling | Zero alert() em codigo vivo | DONE | `a841d4e` | — |
| Debitos | DEBITOS.md atualizado (16 itens) | DONE | — | Itens 6, 8 resolvidos; restantes rastreados |

---

**Legenda:** DONE = implementado e mergeado · PARCIAL = dados/logica existem mas sem UI/tela dedicada · NAO INICIADO = sem codigo · ADIADO = decisao consciente de postergar · DESEJAVEL = melhoria nao critica
