# SAAS_ROADMAP — IBC Ensino → Plataforma EAD Multi-Tenant (Laia Edu)

> Documento de planejamento estratégico e técnico. **Nenhuma alteração de código foi feita.**
> Base: branch `claude/zen-hopper-SeRac` — Flask 3 / SQLAlchemy 2 / PostgreSQL / SPA vanilla / Railway.
> Complementa (não substitui) o `ROADMAP.md` de auditoria técnica já existente. Data: 2026-07-02.

---

## SUMÁRIO EXECUTIVO — recomendação central

- **✅ Ir para SaaS multi-tenant, mas em duas velocidades.** O produto tem os blocos certos (trilhas, gamificação, certificados, tutoria, quiz) que são genéricos a qualquer formação contínua. A tese de virar produto-piloto da Laia Edu é sólida — o diferencial "Micro-SaaS com IA embarcada" é real e viável.
- **⚠️ Mas NÃO antes de fechar a dívida crítica do `ROADMAP.md`.** Os 3 buracos de segurança (signup vira admin, `SECRET_KEY` público, admin default) e a **ausência de migrações** são pré-requisitos absolutos: multi-tenant multiplica o raio de explosão de cada um. Hoje um bug vaza dados de uma igreja; num SaaS, vaza dados de todos os clientes de uma vez.
- **🏗️ Arquitetura recomendada: row-level com `tenant_id` (pool model)**, não schema-per-tenant nem banco-por-tenant. É o único caminho compatível com "dezenas a centenas de clientes pequenos" na infra atual do Railway sem custo operacional insustentável.
- **🎯 Verticais prioritárias: (1) Educação corporativa / treinamento de PMEs e franquias, (2) Coaches e infoprodutores.** A primeira reusa quase tudo (onboarding, trilhas, certificados) e paga bem; a segunda é volume alto e concorrência conhecida, mas cabe no diferencial de IA.
- **💰 Billing: começar com Asaas ou Mercado Pago** (PIX + boleto + cartão, essencial no Brasil PME), não Stripe puro. Modelo por faixas de alunos ativos + tier de features.
- **🔑 O IBC Ensino vira o "tenant #1"** — a migração é desenhada para que a igreja nunca perceba a mudança. Isso reduz drasticamente o risco: você valida a arquitetura multi-tenant com dados reais antes do primeiro cliente pago.
- **⏱️ Caminho mais rápido e seguro:** Fase A (fundação multi-tenant, ~4-6 semanas) → Fase B (1 piloto pago manual, sem self-service) → só então automatizar billing/onboarding (Fase C). **Não construa self-service antes de ter 1 cliente pago validando a vertical.**
- **🚨 Maior risco técnico:** vazamento cross-tenant por uma query que esqueceu o filtro `tenant_id`. Com ~14 blueprints e zero testes hoje, isso é quase certo de acontecer sem uma camada de isolamento automática (não manual) + testes de isolamento.

---

# BLOCO 1 — VALIDAÇÃO DE MERCADO

O que o sistema **já faz e é genérico** a qualquer vertical: catálogo de cursos → módulos/aulas → vídeo + material PDF + quiz → progresso → certificado verificável → gamificação (pontos/níveis/conquistas) → tutoria (perguntas e respostas) → trilhas sequenciais → avisos/notificações. O que é **específico de igreja** e precisa de white-label: nomenclatura ("Pontos" vs "XP"), versículo do dia (`PlatformConfig.verse_text`), tom pastoral, e o vocabulário do domínio.

## Verticais avaliadas

| Vertical | Esforço de adaptação | Diferencial possível | Concorrência |
|---|---|---|---|
| **Educação corporativa / treinamento PME e franquias** | **Baixo.** Reusa trilhas (onboarding de funcionário), certificados (compliance/NR), quiz (avaliação), tutoria. Muda: relatórios para RH, matrícula por equipe/departamento, SSO opcional. | Simplicidade e preço vs. LMS corporativo caro; IA que gera trilha de onboarding a partir de um manual. | Alta mas cara: TalentLMS, 360Learning, Twygo (BR), Eadbox/Sambatech (BR). Espaço no "bom e barato para PME/franquia". |
| **Coaches / infoprodutores** | **Baixo-médio.** Reusa tudo; muda: área de membros, upsell, foco em vídeo, comunidade. | IA que estrutura o infoproduto e gera quizzes; preço abaixo de plataformas premium. | **Muito alta:** Hotmart, Kiwify, Eduzz, Memberkit, Circle. Diferenciação difícil — competir por nicho/IA, não por feature. |
| **Escolas de idiomas / cursos livres** | **Médio.** Reusa trilhas e quiz; precisa de aula ao vivo (não existe), correção de fala, spaced repetition. | Gamificação já pronta (forte em idiomas); IA de conversação. | Alta: Duolingo (não-SaaS), plataformas próprias. Nicho de escola pequena que quer plataforma própria é viável. |
| **ONGs / associações / formação de voluntários** | **Baixo.** Praticamente idêntico ao caso igreja (formação contínua de pessoas, baixo orçamento). | Preço social; reuso quase total do que já existe. | Baixa concorrência dedicada — mercado fragmentado e mal atendido. Ticket baixo, porém. |
| **Escolas técnicas / cursos profissionalizantes** | **Médio-alto.** Precisa de notas formais, diário de classe, carga horária, emissão de certificado com validade legal. | Certificado verificável já existe (base boa). | Média: Moodle (gratuito mas complexo), plataformas próprias. Barreira: exigências regulatórias. |
| **Academias / personal trainers com conteúdo** | **Médio.** Reusa trilhas e vídeo; muda: agendamento, planos de treino, acompanhamento físico (fora do escopo atual). | Nicho, mas exige features de fitness que não existem. | Média: apps de fitness dedicados. Fit fraco com o produto atual. |

## Recomendação: 2 verticais para atacar primeiro

1. **Educação corporativa / treinamento de PMEs e franquias (prioridade #1).** É o melhor casamento entre "reuso alto do que já existe" e "disposição a pagar". Onboarding de funcionário, treinamento de rede de franquias e compliance são dores caras e recorrentes; o produto atual entrega 80% disso hoje. O ciclo de venda é B2B (previsível, contrato anual) e o churn é baixo quando vira ferramenta de RH. A adaptação principal é relatório para gestor e matrícula por equipe — ambos já parcialmente esboçados no `ROADMAP.md` (coortes, relatórios).

2. **Coaches / infoprodutores (prioridade #2, para volume).** Mercado enorme e com dinheiro, mas concorrência feroz e comoditizada. A entrada só faz sentido apoiada no **diferencial de IA da Laia** (gerar curso/quiz a partir de um PDF ou transcrição) e mirando o coach pequeno que acha Hotmart/Kiwify caro ou genérico demais. É a vertical de "muitos clientes de ticket baixo" que valida o motor de self-service da Fase C.

> **Por que não igrejas/ONGs como #1 comercial:** é o nicho de origem (você já domina), mas é o de menor ticket e maior sensibilidade a preço. Vale manter como base de validação e como vertical de menor esforço, não como motor de receita.

---

# BLOCO 2 — ARQUITETURA MULTI-TENANT (o bloco crítico)

## 2.1 Estratégia de isolamento: recomendação **row-level (`tenant_id`) — pool model**

| Estratégia | Prós | Contras | Veredito p/ este caso |
|---|---|---|---|
| **Banco-por-tenant** | Isolamento máximo; backup/restore/LGPD por cliente triviais | Inviável no Railway p/ dezenas+ de clientes (custo e ops por banco); migração N vezes; conexões explodem | ❌ Não |
| **Schema-per-tenant** (mesmo banco, schemas separados) | Bom isolamento; migração ainda gerenciável | SQLAlchemy + Flask-Migrate com N schemas é complexo; `search_path` por request é frágil; ainda pesa a centenas de schemas | ⚠️ Só se exigência de isolamento forte (dados sensíveis) — não é o caso |
| **Row-level (`tenant_id` em cada tabela)** | 1 schema, 1 migração; escala a centenas de tenants pequenos; simples no Railway | **Risco de vazamento se uma query esquecer o filtro**; queries um pouco maiores | ✅ **Recomendado** |

**Justificativa:** o perfil é "muitos clientes pequenos/médios" — exatamente o cenário onde o pool model (row-level) ganha. O contra (vazamento por filtro esquecido) é mitigável por engenharia e é **o item nº 1 de risco** (ver Bloco 4 e 5). A mitigação central: **não confiar em filtro manual** — usar um `tenant_id` resolvido no início do request (do subdomínio/sessão) + um default query filter / mixin que injeta o filtro automaticamente, reforçado por testes de isolamento.

## 2.2 Mapa de tenancy dos 28 models atuais

O jeito mais seguro é dar `tenant_id` **direto** às entidades-raiz e às tabelas muito consultadas (evita JOIN só para filtrar), e deixar as tabelas-filhas herdarem por FK — mas, para segurança de row-level, **recomenda-se `tenant_id` denormalizado em praticamente todas**, porque o custo é baixo e fecha a porta de vazamento.

**Entidade nova fundacional: `Tenant`** (id, slug/subdomínio, nome, domínio custom, status, plano, trial_ends_at, created_at). A tabela **`platform_config` já é praticamente isso** — hoje é singleton com `platform_name`, `platform_short`, `support_email`, versículo e valores de pontuação. Ela vira **1:1 com Tenant** (ou é absorvida por ele), o que torna o white-label quase de graça (ver 2.3).

Tenant-scoped (recebem `tenant_id`):

- **Raiz de conteúdo:** `categories`, `courses`, `trails`, `badge`, `levels`, `achievements`, `announcements` — `tenant_id` direto (essenciais).
- **Identidade:** `users` — `tenant_id` direto **+ mudança crítica de constraint** (ver 2.6): `email` deixa de ser globalmente único e passa a ser único **por tenant** (`UNIQUE(tenant_id, email)`).
- **Config/white-label:** `platform_config` → 1:1 com tenant (ou vira o próprio Tenant).
- **Conteúdo filho** (herdam via FK, mas denormalizar `tenant_id` por segurança/performance): `modules`, `materials`, `quiz`, `trail_courses`, `tutor_courses`.
- **Dados de aluno** (denormalizar `tenant_id`): `lesson_progress`, `progress`, `user_trails`, `user_points`, `user_badge`, `user_achievements`, `certificates`, `study_sessions`, `activity_feed`, `onboarding_answers`, `questions`, `notifications`, `announcement_dismissals`, `password_reset_tokens`.

Global (SEM `tenant_id`): apenas o novo `Tenant` e, futuramente, uma tabela de **super-admin/plataforma** (usuários donos do SaaS) e de **billing/assinaturas** — que são cross-tenant por natureza.

> **Total:** dos 28 models, ~26 recebem `tenant_id`; `platform_config` funde-se ao Tenant; e criam-se ~3-4 tabelas globais novas (Tenant, Subscription, SuperAdmin, AuditLog).

## 2.3 White-label

O trabalho pesado **já está feito pela metade**: `PlatformConfig` (`models.py:539`) já externaliza `platform_name`, `platform_short`, `support_email`, `whatsapp`, versículo e pontuação. O que falta:

- **Cores e logo:** hoje o teal `#008ea8` e o navy estão hardcoded em CSS (e, pior, há dois `:root` conflitantes — ver `ROADMAP.md §2.2`). Adicionar ao Tenant: `primary_color`, `secondary_color`, `logo_url`, `favicon_url`. O frontend passa a injetar essas cores como CSS custom properties no `<head>` a partir de um endpoint `GET /api/tenant/theme` (resolvido pelo subdomínio) — as ~40 cores hardcoded viram `var(--primary)`. **Pré-requisito:** unificar os tokens CSS (já é item do `ROADMAP.md §2.2`), então isso se paga duas vezes.
- **Nomenclatura configurável:** "Pontos/Nível/Conquistas" já são termos de negócio; para verticais fora de igreja, expor rótulos configuráveis por tenant (ex.: "XP", "Badges") ou manter os atuais como default. O versículo do dia vira um "banner/frase configurável" genérico (vazio por default fora de igreja).
- **Domínio de e-mail/remetente:** e-mails transacionais (forgot-password, lembretes) precisam sair com o nome do tenant, não "IBC".

## 2.4 Autenticação e domínios

- **Subdomínio por cliente (`cliente.laiaedu.com.br`)** — **recomendado como padrão.** Viável no Railway com um domínio wildcard (`*.laiaedu.com.br`) apontando para o serviço; o app resolve o tenant pelo `Host`/subdomínio no início do request. É a abordagem mais simples e a que casa com row-level (subdomínio → `tenant_id`).
- **Domínio próprio via CNAME (`ead.clientexyz.com.br`)** — oferecer como feature de tier alto. Exige o cliente apontar CNAME para a plataforma e o Railway/edge emitir certificado TLS para o domínio custom. O Railway suporta domínios custom, mas **automatizar emissão de TLS para N domínios de clientes** é trabalho não-trivial — deixar para depois do self-service (Fase C+).
- **Sessão:** o cookie de sessão precisa considerar o tenant. Com subdomínios distintos, cookies são naturalmente isolados por origem (bom). A resolução de tenant deve acontecer **antes** da autenticação (um `before_request` que lê o Host, carrega o Tenant e o injeta no contexto), e o login passa a validar credenciais **dentro** daquele tenant.

## 2.5 White-label do frontend: nota de esforço

O `index.html` é um monólito de 5.630 linhas com `IBC` e cores espalhados. A migração para white-label real depende de: (a) unificar tokens CSS (já planejado), (b) trocar strings hardcoded "IBC/IBC Ensino" por valores vindos do theme endpoint, (c) tratar o logo como variável. É **médio** de esforço e deve ser feito junto da resolução dos dois `:root` conflitantes para não pagar a dívida duas vezes.

## 2.6 Impacto no deploy atual — migrar sem quebrar o IBC

Estratégia de "expand-and-contract", com o IBC virando **tenant #1**:

1. **Pré-requisito:** adotar Flask-Migrate (já é item crítico do `ROADMAP.md §1.5`). Multi-tenant é impossível de aplicar com segurança sob `db.create_all()`.
2. Criar a tabela `Tenant` e inserir 1 linha: o IBC (absorvendo o `platform_config` atual).
3. Adicionar `tenant_id` como **nullable** em todas as tabelas (migração aditiva, não quebra nada).
4. **Backfill:** `UPDATE ... SET tenant_id = <id_do_IBC>` em todas as linhas existentes.
5. Tornar `tenant_id` **NOT NULL** + criar índices `(tenant_id, ...)`.
6. **Constraint de e-mail:** trocar `UNIQUE(email)` por `UNIQUE(tenant_id, email)` — **ponto de atenção**, é a mudança que mais pode quebrar login se feita errado.
7. Introduzir a resolução de tenant por subdomínio, mantendo o domínio atual do IBC apontando para o tenant #1 (a igreja não percebe nada).
8. Só então habilitar criação de novos tenants.

Cada passo é um deploy reversível. O IBC continua no ar o tempo todo.

---

# BLOCO 3 — MODELO DE NEGÓCIO E BILLING

## 3.1 Modelos de precificação (mercado BR, PMEs/pequenas organizações)

- **Modelo A — Por alunos ativos/mês (recomendado p/ corporativo):** faixas por MAU (monthly active users). Ex.: até 50 alunos R$ 97/mês · até 200 R$ 247/mês · até 500 R$ 497/mês · 500+ sob consulta. Previsível, escala com o valor entregue, fácil de comunicar.
- **Modelo B — Por tier de features (flat):** Starter R$ 97 · Pro R$ 297 · Enterprise sob consulta, com limites de alunos/cursos por tier. Mais simples de vender a quem tem medo de "conta variável".
- **Modelo C — Flat + overage:** mensalidade base com cota de alunos incluída + valor por aluno excedente. Bom para reter clientes que crescem, mas mais complexo de faturar.

**Recomendação:** começar com **Modelo B (tier flat)** por simplicidade de venda e de implementação, e migrar para **A (por MAU)** quando houver dados de uso. Ancorar preços em R$ — PME brasileira compara com "uma assinatura de ferramenta", não com LMS gringo em dólar.

## 3.2 O que construir tecnicamente para billing

- **Gateway:** **Asaas ou Mercado Pago** (não Stripe puro). Motivo: PIX e boleto são inegociáveis para PME brasileira, e a experiência de cobrança recorrente nacional é melhor. Asaas é forte em cobrança recorrente + inadimplência; Mercado Pago tem alcance e confiança. Pagar.me é alternativa robusta. Stripe só se mirar clientes internacionais.
- **Modelos novos:** `Subscription` (tenant_id, plano, status, ciclo, current_period_end), `Invoice`/`Payment` (histórico), `PlanLimits` (cota de alunos/cursos por tier).
- **Trial:** `Tenant.trial_ends_at` + middleware que checa status no `before_request` (banner de trial, bloqueio ao expirar).
- **Upgrade/downgrade:** endpoint que muda o plano e ajusta limites; proração fica a cargo do gateway.
- **Bloqueio por inadimplência:** webhook do gateway → muda `Subscription.status` → middleware bloqueia acesso (tela de "pagamento pendente") preservando os dados. **Nunca deletar dados por inadimplência** — suspender.
- **Webhooks:** endpoint para eventos do gateway (pago, falhou, estornado) — precisa de idempotência e verificação de assinatura.

## 3.3 Features por tier (com base no que já existe hoje)

| Feature | Trial (14d) | Starter | Pro | Enterprise |
|---|---|---|---|---|
| Cursos/módulos/quiz | ✅ limitado | ✅ | ✅ | ✅ |
| Gamificação (pontos/níveis/conquistas) | ✅ | ✅ | ✅ | ✅ |
| Certificados verificáveis | ✅ marca d'água | ✅ | ✅ | ✅ sem marca |
| Trilhas | ✅ | limite baixo | ✅ | ✅ |
| Tutoria (perguntas/respostas) | ✅ | ✅ | ✅ | ✅ |
| Coortes/turmas com prazos (planejado) | — | — | ✅ | ✅ |
| Relatórios avançados / exportação | — | básico | ✅ | ✅ |
| White-label cores+logo | — | — | ✅ | ✅ |
| Domínio próprio (CNAME) | — | — | — | ✅ |
| IA (geração de curso/quiz) — diferencial Laia | trial | add-on | ✅ | ✅ |
| Nº de alunos | 20 | 100 | 500 | ilimitado/negociado |

O tier gratuito permanente é desaconselhado no início (suporte custa); preferir **trial de 14 dias** que exige cartão/PIX só na conversão.

---

# BLOCO 4 — GAPS TÉCNICOS PARA OPERAR COMO SAAS

Além do multi-tenant (Bloco 2):

1. **Onboarding self-service** — hoje a criação de tenant/admin é manual (via `seed`/console). Precisa de: fluxo de signup de **organização** (cria Tenant + admin + config inicial), escolha de subdomínio, wizard de setup (logo, cor, primeiro curso). **Não construir na Fase B** — validar com onboarding manual primeiro.
2. **Painel de super-admin** — não existe. Precisa de um app/rota separada, fora do escopo de qualquer tenant, para: listar tenants, ver MAU e status de assinatura, impersonar (suporte), suspender/reativar, métricas agregadas. É também onde vivem os usuários "donos da plataforma" (tabela global nova).
3. **Observabilidade** — hoje há 44 `print()` e zero logging estruturado (`ROADMAP.md §1.5`). Precisa de: **Sentry** (erros), logging estruturado com `tenant_id` em cada linha, e métricas de uso por tenant. Num SaaS, "de qual cliente é esse erro?" precisa ser respondível em segundos.
4. **Escalabilidade — o que quebra primeiro com 50 tenants:** (a) **o 1 worker gunicorn** (`ROADMAP.md §1.5`) — serializa tudo, é o primeiro gargalo; (b) os **N+1 nos dashboards** (`ROADMAP.md §1.3`) — com dados de 50 clientes, dashboards que hoje são lentos ficam inviáveis; (c) **pool de conexões do Postgres** do Railway — precisa dimensionar; (d) **uploads em `/tmp`** — quebra já com 1 tenant, obrigatório resolver com storage externo (S3/R2) antes de escalar. Ordem de correção: uploads → workers → N+1 → conexões.
5. **Backups e DR por tenant** — com row-level, backup nativo do Railway cobre tudo junto, mas **restaurar um único tenant** exige `pg_dump` filtrado por `tenant_id` ou export lógico. Construir um export por tenant (também serve à LGPD).
6. **LGPD** — row-level facilita: (a) **exportação** de dados de um usuário/tenant = SELECT filtrado por `tenant_id`/`user_id` → JSON/CSV; (b) **exclusão** = DELETE em cascata (depende de resolver o `delete_user` sem cascade do `ROADMAP.md §1.2`); (c) termo de consentimento no signup; (d) DPA (contrato de tratamento de dados) com cada tenant. O maior risco LGPD é justamente o vazamento cross-tenant (Bloco 5).

---

# BLOCO 5 — ROADMAP DE EXECUÇÃO

> Regra de ouro: **cada fase só avança quando a anterior está validada em produção.** Não paralelizar Fase C (self-service) antes de ter receita da Fase B.

## Fase 0 (pré-requisito, ~1-2 semanas) — Fechar a dívida crítica

Não é opcional. Antes de qualquer trabalho multi-tenant:
- Corrigir os 3 críticos de segurança + XSS (`ROADMAP.md §1.1, §2.1`).
- Adotar Flask-Migrate (`ROADMAP.md §1.5`).
- Resolver uploads em filesystem efêmero (storage externo).
- Suíte de testes mínima + CI (é o alicerce dos testes de isolamento da Fase A).

**Pronto para avançar quando:** produção segura, migrações funcionando, CI verde.

## Fase A — Fundação multi-tenant sem quebrar o IBC (~4-6 semanas)

- **Pré-requisitos técnicos:** Fase 0 completa; modelo de progresso unificado (`ROADMAP.md §1.2`, senão o bug se multiplica por tenant).
- **Entregas:** tabela `Tenant`; `tenant_id` em todas as tabelas via expand-and-contract (2.6); IBC vira tenant #1; resolução por subdomínio; **camada automática de filtro por tenant** (não manual); **testes de isolamento** (aluno do tenant A nunca vê dado do tenant B); white-label básico (cor/logo do theme endpoint).
- **Marco de validação de negócio:** criar um **segundo tenant de teste** (interno) e provar isolamento total. O IBC segue idêntico para a igreja.
- **Riscos principais:** ⚠️ **vazamento cross-tenant por filtro esquecido** (o maior de todos); quebra do login pela mudança de constraint de e-mail (2.6); regressão no IBC durante o backfill.

## Fase B — Primeiro cliente piloto pago fora de igreja (~3-4 semanas + venda)

- **Pré-requisitos técnicos:** Fase A validada; onboarding **manual** (você cria o tenant); relatórios básicos para gestor (se corporativo).
- **Entregas:** 1 tenant real pago na vertical #1 (corporativo). Billing pode ser **manual/fora do sistema** nesta fase (contrato + cobrança avulsa) — o objetivo é validar valor, não automação.
- **Marco de validação de negócio:** cliente usando de verdade, pagando, com feedback de retenção. **É o gate mais importante do roadmap** — se não fechar 1 cliente pago aqui, não construa a Fase C.
- **Riscos principais:** descobrir que a vertical exige feature ausente (ex.: SSO, aula ao vivo); suporte manual consumindo tempo; churn precoce por bug de isolamento não pego na Fase A.

## Fase C — Self-service + billing automatizado (~5-8 semanas)

- **Pré-requisitos técnicos:** ≥1 cliente pago satisfeito; painel de super-admin; Sentry + observabilidade por tenant; gateway (Asaas/Mercado Pago) integrado.
- **Entregas:** signup de organização self-service; wizard de setup; trial 14d; upgrade/downgrade; bloqueio por inadimplência; webhooks idempotentes.
- **Marco de validação de negócio:** um cliente entra, configura e paga **sem você tocar em nada**. Primeira conversão 100% automática.
- **Riscos principais:** fraude/abuso no signup aberto; complexidade de billing (proração, estornos, inadimplência); custo de suporte de clientes self-service de ticket baixo.

## Fase D — Expansão para a 2ª vertical (~4-6 semanas + go-to-market)

- **Pré-requisitos técnicos:** self-service estável; **diferencial de IA** pronto (geração de curso/quiz), que é o que torna a vertical de coaches/infoprodutores defensável.
- **Entregas:** ajustes de white-label/nomenclatura para a vertical #2; features específicas mínimas (área de membros, comunidade); landing/go-to-market dedicado.
- **Marco de validação de negócio:** primeiros clientes pagos na vertical #2 via self-service.
- **Riscos principais:** dispersão de foco entre duas verticais; concorrência esmagadora em infoprodutos exigindo o diferencial de IA realmente maduro; suporte a dois públicos com necessidades distintas.

---

## Síntese de dependências

```
Fase 0 (segurança + migrações + uploads + testes)
   └─> Fase A (tenant_id + isolamento automático + testes de isolamento + white-label)
          └─> Fase B (1 piloto pago manual, vertical corporativa)   ← GATE DE NEGÓCIO
                 └─> Fase C (self-service + billing Asaas/MP + super-admin + Sentry)
                        └─> Fase D (IA madura + 2ª vertical: coaches/infoprodutores)
```

O caminho crítico não é técnico no fim — é o **gate da Fase B**: um cliente pago fora de igreja valida a tese inteira antes de investir em automação.
