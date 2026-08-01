# Arquitetura de Software — Plataforma Multi-tenant
**Produto:** XR Educação (evolução do IBC Ensino)
**Versão:** 1.0 | Julho/2026
**Documentos relacionados:** 00-VISAO.md · 01-PRD.md · 03-ARQUITETURA-IA.md

---

## 1. Princípios arquiteturais

1. **Evolução, não reescrita.** A base Flask 3.0.3 / SQLAlchemy 2.0.51 / PostgreSQL em produção no Railway é o ponto de partida. Cada mudança preserva o IBC Ensino funcionando.
2. **Monólito modular.** Um único deploy, módulos com fronteiras explícitas (pacotes Python com interfaces claras). Microsserviços só quando uma dor real de escala exigir — não antes. Exceção: workers assíncronos (fila) desde o MVP, porque IA e importação são inerentemente assíncronas.
3. **Defesa em profundidade no isolamento de tenant.** Isolamento garantido em três camadas independentes: middleware de aplicação, sessão de banco com RLS, e testes automatizados. Uma falha em uma camada não expõe dados.
4. **AI-ready development.** Estrutura de código, convenções e documentos escritos para que agentes de IA (Claude Code) implementem features com contexto mínimo: cada módulo tem README próprio, contratos tipados e testes como especificação executável.
5. **Custo proporcional à receita.** Infra simples no MVP (Railway), com caminho de migração definido (§8) em vez de sobre-engenharia antecipada.

## 2. Visão geral (C4 — nível contêiner)

```
┌────────────────────────────────────────────────────────────────┐
│  CLIENTES                                                      │
│  SPA aluno/instrutor (vanilla JS → migração p/ componentes)    │
│  Painel operador (mesma SPA, papel operador_plataforma)        │
└──────────────┬─────────────────────────────────────────────────┘
               │ HTTPS (subdomínio identifica tenant)
┌──────────────▼─────────────────────────────────────────────────┐
│  APLICAÇÃO FLASK (gunicorn, Railway)                           │
│                                                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │ core/    │ │ courses/ │ │ learning/│ │ ai/              │   │
│  │ tenancy  │ │ conteúdo │ │ learner  │ │ tutor, RAG,      │   │
│  │ auth     │ │ editor   │ │ model,   │ │ providers,       │   │
│  │ billing  │ │ quiz     │ │ spaced   │ │ guardrails       │   │
│  └──────────┘ └──────────┘ │ repetition│ └──────────────────┘   │
│  ┌──────────┐ ┌──────────┐ └──────────┘ ┌──────────────────┐   │
│  │ gamif./  │ │ analytics│              │ platform/        │   │
│  │ streaks  │ │ alertas  │              │ operador, planos │   │
│  └──────────┘ └──────────┘              └──────────────────┘   │
└───────┬───────────────┬───────────────────────┬────────────────┘
        │               │                       │
┌───────▼──────┐ ┌──────▼──────────┐  ┌─────────▼──────────────┐
│ PostgreSQL   │ │ Redis           │  │ Workers (RQ)           │
│ + RLS        │ │ cache, sessões, │  │ ingestão RAG,          │
│ + pgvector   │ │ fila RQ,        │  │ importação de curso,   │
│ (embeddings) │ │ rate limiting   │  │ exports, e-mails,      │
└──────────────┘ └─────────────────┘  │ recomputo learner model│
                                      └───────────┬────────────┘
                                       ┌──────────▼───────────┐
                                       │ EXTERNOS             │
                                       │ Claude API (tutor)   │
                                       │ Asaas (billing)      │
                                       │ Resend/SES (e-mail)  │
                                       │ S3/R2 (arquivos)     │
                                       └──────────────────────┘
```

**Decisões de stack (ADR resumido):**

| Área | Decisão | Racional / alternativa rejeitada |
|---|---|---|
| Backend | Manter Flask 3.0.3 + SQLAlchemy 2.0 | Base madura em produção; migrar p/ FastAPI não paga o custo agora (ADR-001) |
| Fila | Redis + RQ | Simplicidade > Celery p/ time de 1; Railway suporta Redis nativo (ADR-002) |
| Vetores | pgvector no mesmo PostgreSQL | Evita segundo banco; escala suficiente até ~1M chunks (ADR-003) |
| Frontend | Manter SPA vanilla; introduzir Web Components p/ novos módulos (tutor, mapa de domínio) | Reescrita em Next.js adiada; avaliar na Release 1.1 (ADR-004) |
| Arquivos | Cloudflare R2 (S3-compatible) | Egress gratuito, custo baixo p/ vídeos/PDFs (ADR-005) |
| Billing | Asaas | Pix + boleto nativos, público-alvo brasileiro (ADR-006, pendente confirmação PRD §8.2) |

## 3. Estrutura de código (contrato para desenvolvimento por IA)

```
ibc-ensino-backend/            # renomear repo → xr-educacao na Release 1.0
├── app/
│   ├── core/                  # tenancy, auth, billing, config
│   │   ├── tenancy/           # middleware, contexto, RLS session
│   │   ├── auth/              # JWT, papéis, convites
│   │   └── billing/           # planos, Asaas, medição
│   ├── courses/               # trilhas, cursos, lições, blocos, quiz, editor
│   ├── learning/              # learner model, conceitos, spaced repetition, risco
│   ├── ai/                    # tutor, RAG, providers, prompts, guardrails, custo
│   ├── gamification/          # pontos, conquistas, streaks, certificados
│   ├── analytics/             # dashboards instrutor, alertas, exports
│   ├── platform/              # painel operador, gestão de tenants
│   └── shared/                # eventos de domínio, utils, tipos
├── migrations/                # Alembic
├── workers/                   # jobs RQ
├── tests/
│   ├── isolation/             # suíte de isolamento de tenant (obrigatória em CI)
│   └── ...
└── docs/                      # este pacote + ADRs + READMEs de módulo
```

**Regras para agentes de IA (aplicáveis a todo PR):**
1. Todo model SQLAlchemy de domínio herda de `TenantScopedModel` (inclui `tenant_id`, índice composto, política RLS na migração).
2. Nenhum acesso a banco fora de repositórios do módulo; controllers não importam models de outros módulos — comunicação entre módulos via serviços ou eventos de domínio (`shared/events.py`).
3. Toda feature nova inclui: migração Alembic reversível, testes (incl. caso de isolamento se tocar dados), atualização do README do módulo.
4. Segredos apenas via variáveis de ambiente; nunca em código ou migração.
5. Chamadas a LLM apenas através de `ai/providers/` (nunca chamar SDK diretamente de outro módulo).

## 4. Modelo de dados (núcleo)

Entidades novas em relação ao IBC Ensino atual estão marcadas com ●.

```
● tenants(id, slug, nome, subdominio, plano, status, tema_json, criado_em)
● tenant_users(tenant_id, user_id, papel)          -- papéis por tenant
users(id, email, senha_hash, nome, ...)            -- global, sem tenant_id
trilhas / cursos / modulos / licoes / blocos       -- existentes + tenant_id
● conceitos(id, tenant_id, curso_id, nome, descricao)
● licao_conceitos(licao_id, conceito_id)
questoes(id, tenant_id, licao_id, tipo, ...) ● + questao_conceitos
matriculas, progresso_licoes, tentativas_quiz      -- existentes + tenant_id
pontos, conquistas, certificados                   -- existentes + tenant_id
● streaks(user_id, tenant_id, atual, recorde, ultimo_dia, congelamentos)
● learner_concept_state(user_id, tenant_id, conceito_id,
      dominio float, evidencias int, atualizado_em)       -- doc 03 §3
● review_items(user_id, tenant_id, conceito_id, due_date,
      intervalo, facilidade, historico_json)              -- doc 03 §4.3
● tutor_sessions(id, tenant_id, user_id, licao_id, iniciado_em)
● tutor_messages(session_id, papel, conteudo, fontes_json,
      tokens_in, tokens_out, custo_estimado, criado_em)
● content_chunks(id, tenant_id, licao_id, ordem, texto,
      embedding vector(1024), metadata_json)              -- RAG
● ai_usage(tenant_id, periodo, interacoes, tokens, custo)  -- medição BIL-03
● subscriptions(tenant_id, plano, asaas_id, status, ciclo)
● audit_log(tenant_id, user_id, acao, alvo, payload_json, criado_em)
● domain_events(id, tenant_id, tipo, payload_json, criado_em, processado)
```

**Migração do IBC Ensino (Release 0.9):** script idempotente cria tenant `ibc`, adiciona `tenant_id` NOT NULL com default para o tenant IBC em todas as tabelas de domínio, cria índices `(tenant_id, ...)` e ativa RLS tabela a tabela com janela de verificação (modo `permissive` → `enforced`).

## 5. Multi-tenancy — projeto detalhado

### 5.1 Modelo escolhido
**Banco único, schema único, RLS por linha** (pool compartilhado). Racional: menor custo operacional para dezenas–centenas de tenants pequenos; isolamento forte via RLS; caminho de saída para cliente Enterprise = replicar stack em instância dedicada (o modelo de dados não muda).

### 5.2 Resolução de tenant (request lifecycle)
1. Middleware extrai subdomínio → busca tenant (cache Redis, TTL 60s) → valida status (ativo/leitura/suspenso).
2. Autenticação valida JWT; claims incluem `tenant_id` e `papel`. **Regra:** `tenant do token == tenant do subdomínio`, senão 403.
3. Contexto de request (`g.tenant`) definido; sessão SQLAlchemy executa `SET LOCAL app.tenant_id = :id` na abertura da transação.

### 5.3 RLS (PostgreSQL)
Política padrão por tabela de domínio:
```sql
ALTER TABLE licoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE licoes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON licoes
  USING (tenant_id = current_setting('app.tenant_id')::uuid);
```
A aplicação conecta com role **sem** `BYPASSRLS`. Migrações e painel do operador usam role separada com auditoria reforçada.

### 5.4 Suíte de isolamento (obrigatória em CI — NFR-01)
Testes parametrizados que, para cada endpoint autenticado: (a) criam dados em tenant A e B; (b) autenticam como usuário de A; (c) tentam acessar recursos de B por ID direto, listagem, busca e filtros; (d) exigem 404/403 e zero linhas. Novo endpoint sem cobertura de isolamento falha o pipeline (verificação por convenção de nomenclatura de testes).

### 5.5 Vazamentos indiretos (checklist de revisão)
IDs sequenciais (usar UUIDv7), contadores globais, busca full-text, embeddings (content_chunks TEM tenant_id e o retrieval filtra antes da similaridade), caches (chave sempre prefixada por tenant), logs (nunca conteúdo de outro tenant em stack traces), e-mails (remetente/branding do tenant correto).

## 6. Identidade e segurança

- **Sessões:** JWT curto (15 min) + refresh token httpOnly rotativo; revogação por lista em Redis. Claims: `sub`, `tenant_id`, `papel`, `jti`.
- **Senhas:** argon2id; política mínima 8 chars + verificação contra listas vazadas (offline, k-anonymity opcional pós-MVP).
- **Rate limiting:** por IP e por usuário (Redis), com limites específicos para endpoints de IA e auth.
- **LGPD (NFR-05):** registro de bases legais; dados de menores (comum em igrejas) exigem consentimento do responsável no convite; conversas com tutor são dados pessoais — retenção configurável por tenant (default 12 meses) e anonimização em métricas agregadas.
- **Uploads:** validação de tipo/tamanho, antivírus (ClamAV no worker), URLs assinadas do R2, nunca execução de conteúdo enviado.
- **Cabeçalhos:** CSP estrita por subdomínio, HSTS, X-Frame-Options.

## 7. Módulos assíncronos e eventos

Eventos de domínio (outbox em `domain_events`, consumidos por workers RQ):

| Evento | Produtor | Consumidores |
|---|---|---|
| `licao.publicada` | courses | ai (reindexar chunks RAG), analytics |
| `quiz.respondido` | courses | learning (atualizar domínio), gamification (pontos) |
| `tutor.interacao` | ai | learning (evidência), billing (medição), analytics |
| `aluno.inativo_7d` | scheduler | learning (risco), notificações |
| `pagamento.confirmado/falhou` | billing (webhook Asaas) | platform (status do tenant) |
| `curso.importado` | workers | courses (rascunho pronto), notificações |

Jobs agendados: fila de revisão diária (00:30 por fuso do tenant), recomputo de risco de evasão, fechamento de medição de IA, verificação de streaks.

## 8. Infraestrutura e operação

**MVP (Railway):** serviço web (gunicorn, 2× replicas), serviço worker (RQ), PostgreSQL com pgvector, Redis. Deploy por push na `main` após CI verde (lint, testes, suíte de isolamento, migração dry-run).

**Observabilidade (NFR-09):** logs JSON estruturados com `tenant_id`/`request_id` (Railway → Better Stack ou Axiom); métricas de negócio (alunos ativos, interações de tutor, custo IA/tenant) em tabela própria + painel do operador; Sentry para erros; tracing simplificado das chamadas de IA (latência, tokens, custo por request).

**Backups:** snapshot diário do PostgreSQL + PITR; teste de restauração mensal documentado.

**Gatilhos de evolução de infra (não antes):**
| Sinal | Ação |
|---|---|
| p95 > 500ms sustentado | Réplicas de leitura / otimização de queries antes de mudar infra |
| >50 tenants ou >10k alunos ativos | Avaliar migração p/ Fly.io ou AWS (RDS + ECS) |
| Retrieval vetorial >200ms p95 | Índice HNSW tunado; só depois considerar banco vetorial dedicado |
| Cliente Enterprise | Stack dedicada por IaC (Terraform), mesmo codebase |

## 9. Estratégia de testes

Pirâmide: unitários (regras de domínio, learner model determinístico), integração (repositórios + RLS real via Postgres em container no CI), isolamento (§5.4), contrato de IA (respostas do provider mockadas + testes de guardrail com fixtures adversariais, doc 03 §6), E2E smoke das 5 jornadas do PRD §6 (Playwright). Cobertura mínima de 80% em `core/`, `learning/` e `ai/`.

## 10. Roteiro técnico (alinhado ao PRD §7)

| Fase | Entregas técnicas |
|---|---|
| 0.9 | TenantScopedModel + migração IBC; middleware+RLS; suíte de isolamento; CI/CD endurecido; Redis+RQ; outbox de eventos |
| 1.0 | Módulo `ai/` completo (doc 03); `learning/` v1; billing Asaas; onboarding; painel operador; streaks server-side; dashboard UX_ALUNO.md |
| 1.1 | Importação automática de curso; white-label domínio próprio (SSL automático); revisão espaçada v2; Web Components no front |
| 1.2 | API pública versionada (OpenAPI), SSO (OIDC), relatórios avançados |
