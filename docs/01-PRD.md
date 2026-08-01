# PRD — Product Requirements Document
**Produto:** XR Educação (evolução multi-tenant do IBC Ensino)
**Versão:** 1.0 | Julho/2026
**Documentos relacionados:** 00-VISAO.md · 02-ARQUITETURA.md · 03-ARQUITETURA-IA.md

---

## 1. Objetivo do documento

Especificar requisitos funcionais e não funcionais em nível suficiente para que o desenvolvimento seja executado por agentes de IA (Claude Code) e desenvolvedores humanos sem ambiguidade de intenção. Cada requisito tem ID estável (referenciável em commits, issues e prompts) e critérios de aceite verificáveis.

**Convenções de ID:** `TEN-xx` tenancy · `AUTH-xx` identidade · `CUR-xx` cursos/conteúdo · `TUT-xx` tutor de IA · `LRN-xx` learner model/adaptação · `GAM-xx` gamificação · `ANL-xx` analytics · `BIL-xx` billing · `ONB-xx` onboarding · `NFR-xx` não funcionais.

## 2. Personas

**P1 — Aluno (Ana, 34, membro de igreja).** Usa celular (>80% do acesso), estuda à noite, 20–40 min por sessão, pouca familiaridade com tecnologia. Precisa de: continuidade fácil ("continuar de onde parei"), respostas imediatas a dúvidas, sensação de progresso.

**P2 — Instrutor (Pr. Carlos, 48, líder de ensino).** Cria cursos a partir de materiais que já tem (PDFs, apostilas, vídeos no YouTube). Não é técnico. Precisa de: montar curso em horas e não semanas, saber quem está travado, intervir pontualmente.

**P3 — Administrador do tenant (Márcia, 41, secretária/coordenadora).** Gerencia matrículas, turmas, relatórios para liderança. Precisa de: cadastro em massa, relatórios exportáveis, controle de acesso.

**P4 — Operador da plataforma (Samir, fundador).** Gerencia tenants, planos, saúde do sistema e custos de IA. Precisa de: painel de operação, alertas, visibilidade de custo por tenant.

## 3. Escopo de MVP SaaS (Release 1.0)

**Dentro:** multi-tenancy com isolamento RLS; onboarding self-service de tenant; identidade e papéis; cursos/trilhas/lições (herdados do IBC Ensino); tutor de IA por lição com RAG; learner model v1 (domínio por conceito); revisão espaçada v1; gamificação existente (pontos, conquistas, streaks Opção B); dashboard do instrutor v1; billing com Asaas; painel do operador v1.

**Fora (Release 1.1+):** geração automática de curso a partir de upload (assistida no MVP, automática depois); white-label completo com domínio próprio; API pública; SSO; app nativo; avaliações proctoradas; marketplace de cursos entre tenants.

## 4. Requisitos funcionais

### 4.1 Tenancy e administração (TEN)

- **TEN-01** Todo dado de domínio pertence a exatamente um tenant. *Aceite:* nenhuma query de aplicação retorna registros de outro tenant; suíte automatizada de isolamento (doc 02 §5.4) passa em CI.
- **TEN-02** Resolução de tenant por subdomínio (`ibc.xreducacao.com.br`) com fallback por seleção no login. *Aceite:* acesso a subdomínio inexistente retorna página 404 institucional; usuário multi-tenant escolhe contexto após autenticar.
- **TEN-03** Personalização por tenant: logo, cor primária, nome exibido. *Aceite:* IBC opera com teal `#008ea8` e `Logo-IBC-Horizontal.png`; segundo tenant com identidade distinta sem deploy.
- **TEN-04** Painel do operador: criar/suspender tenant, definir plano, ver consumo de IA e alunos ativos. *Aceite:* suspensão bloqueia login de usuários do tenant em <60s, com página explicativa.
- **TEN-05** Exportação de dados do tenant (LGPD/portabilidade): cursos, matrículas, progresso em JSON/CSV. *Aceite:* export completo gerado assincronamente e disponibilizado por link expirável.

### 4.2 Identidade e acesso (AUTH)

- **AUTH-01** Papéis: `aluno`, `instrutor`, `admin_tenant`, `operador_plataforma`. Um usuário pode ter papéis diferentes em tenants diferentes.
- **AUTH-02** Cadastro de aluno por convite (link/QR da turma) ou importação CSV pelo admin. *Aceite:* importação de 500 alunos em <2 min com relatório de erros linha a linha.
- **AUTH-03** Autenticação por e-mail+senha e magic link; sessão JWT com claims de tenant e papel (doc 02 §6). Recuperação de senha por e-mail.
- **AUTH-04** Auditoria: ações administrativas (criação de curso, alteração de matrícula, exportação) registradas em log imutável por tenant.

### 4.3 Cursos e conteúdo (CUR)

- **CUR-01** Hierarquia: Trilha → Curso → Módulo → Lição → Blocos (texto rico, vídeo embed, PDF, quiz, atividade aberta). Preserva o modelo atual do IBC Ensino.
- **CUR-02** Editor de curso do instrutor (evolução do editor do Sprint 6.3), com pré-visualização como aluno.
- **CUR-03** Cada lição declara os **conceitos** que ensina (tags do grafo de conceitos do curso — insumo do learner model, doc 03 §3). *Aceite:* instrutor consegue criar conceitos e associá-los; IA sugere conceitos a partir do texto da lição (assistido).
- **CUR-04** Quiz com correção automática (múltipla escolha, V/F, lacunas) e atividade aberta com correção assistida por IA + revisão do instrutor. Cada questão vincula-se a ≥1 conceito.
- **CUR-05** Importação assistida: upload de PDF/DOCX → IA propõe estrutura de módulos/lições/conceitos → instrutor revisa e publica. (MVP: assistido com revisão obrigatória.)
- **CUR-06** Versionamento leve de lição: publicar não afeta alunos em progresso até "republicar"; histórico das 10 últimas versões.

### 4.4 Tutor de IA (TUT) — resumo funcional (detalhe no doc 03)

- **TUT-01** Chat do tutor disponível dentro de cada lição, com contexto da lição atual e do progresso do aluno. *Aceite:* resposta inicial em <5s (streaming); respostas fundamentadas no material do curso com indicação da lição-fonte.
- **TUT-02** Modo socrático: quando o aluno pede a resposta de uma atividade avaliativa, o tutor conduz por perguntas em vez de entregar a resposta. Instrutor pode configurar rigidez por curso.
- **TUT-03** Fora de escopo: perguntas sem relação com o curso recebem redirecionamento cordial; temas sensíveis seguem a política de guardrails (doc 03 §6).
- **TUT-04** Escalonamento: aluno pode encaminhar a conversa ao instrutor; tutor sinaliza automaticamente dúvidas recorrentes da turma.
- **TUT-05** Cota de interações por plano com contador visível ao admin do tenant; degradação graciosa ao atingir a cota (respostas a partir de FAQ/cache, sem chamadas ao LLM).

### 4.5 Learner model e adaptação (LRN) — detalhe no doc 03

- **LRN-01** Domínio por conceito (escala 0–1) atualizado por evidências: quizzes, atividades, interações com tutor, revisões. Visível ao aluno como "mapa de domínio".
- **LRN-02** Revisão espaçada: fila diária de itens de revisão por aluno (algoritmo doc 03 §4.3), integrada aos streaks. *Aceite:* aluno com itens vencidos vê "Revisão do dia" no grupo PRÓXIMAS METAS do dashboard.
- **LRN-03** Recomendações adaptativas no grupo RECOMENDAÇÕES do dashboard: próxima lição, reforço de conceito fraco, desafio para conceito dominado.
- **LRN-04** Detecção de risco de evasão (heurística v1: inatividade + queda de desempenho + abandono de sessão) com alerta ao instrutor.

### 4.6 Gamificação (GAM) — herdada e estendida

- **GAM-01** Pontos, conquistas e certificados (Sprints 6.1–6.2) preservados, agora por tenant.
- **GAM-02** Streaks (Opção B do documento "INOVAÇÕES PARA ENGAJAMENTO"): dias consecutivos, visual de fogo, bônus por marcos — persistência migra de localStorage para servidor (requisito de multi-dispositivo).
- **GAM-03** Cards estilo Netflix + micro-interações (Opções F+A) aplicados ao catálogo, respeitando o design system do tenant.
- **GAM-04** Dashboard do aluno segue a especificação UX_ALUNO.md: cinco grupos verticais — SAUDAÇÃO, CONTINUE SEUS ESTUDOS, SUA PONTUAÇÃO, PRÓXIMAS METAS, RECOMENDAÇÕES — zero emojis nativos, design system do tenant (IBC: teal #008ea8).

### 4.7 Analytics do instrutor (ANL)

- **ANL-01** Visão de turma: progresso, domínio médio por conceito, mapa de calor de dificuldades.
- **ANL-02** Visão de aluno: linha do tempo de atividade, domínio por conceito, conversas com tutor (transparência pedagógica — aluno é informado no onboarding).
- **ANL-03** Alertas: risco de evasão (LRN-04), conceito com domínio médio <50% na turma, dúvida recorrente detectada pelo tutor (TUT-04).
- **ANL-04** Exportação CSV de qualquer visão.

### 4.8 Billing (BIL)

- **BIL-01** Planos Semente/Crescimento/Comunidade/Enterprise (doc 00 §6) com contagem de alunos ativos (login nos últimos 30 dias).
- **BIL-02** Integração Asaas: assinatura recorrente com Pix, boleto e cartão; webhooks de pagamento atualizam status do tenant. *Aceite:* inadimplência >10 dias move tenant para modo leitura; >30 dias, suspensão com aviso.
- **BIL-03** Medição de consumo de IA por tenant (tokens/interações) com relatório mensal e add-on de créditos.

### 4.9 Onboarding (ONB)

- **ONB-01** Fluxo self-service: cadastro → criação do tenant → escolha de subdomínio → identidade visual → primeiro curso (template ou importação CUR-05) → convite de alunos. Meta: primeiro curso publicado em <1h.
- **ONB-02** Templates verticais de curso: "Escola Bíblica", "Curso de Membresia", "Vida em Prática" (aproveitando o programa de 10 semanas já estruturado), "Treinamento de Liderança".
- **ONB-03** Checklist de ativação com progresso visível ao admin (definição de tenant ativado: ≥1 curso publicado + ≥10 alunos + ≥1 semana de uso).

## 5. Requisitos não funcionais (NFR)

| ID | Requisito | Alvo |
|---|---|---|
| NFR-01 | Isolamento de dados | RLS ativo em 100% das tabelas de domínio; teste de isolamento em CI obrigatório |
| NFR-02 | Disponibilidade | 99,5% mensal no MVP (Railway); plano de evolução no doc 02 §8 |
| NFR-03 | Performance | p95 < 500ms em endpoints de navegação; tutor: primeiro token < 3s |
| NFR-04 | Mobile-first | Todas as telas do aluno utilizáveis em viewport 360px; Core Web Vitals verdes |
| NFR-05 | LGPD | Base legal documentada por tratamento; consentimento para uso pedagógico de dados de IA; exportação (TEN-05) e exclusão sob demanda |
| NFR-06 | Segurança | OWASP ASVS nível 1; senhas argon2; rate limiting; segredos fora do código |
| NFR-07 | Custo de IA | < 8% da receita do tenant em regime; alerta ao operador a 80% da cota |
| NFR-08 | Acessibilidade | WCAG 2.1 AA nas telas do aluno |
| NFR-09 | Observabilidade | Logs estruturados com tenant_id; métricas de negócio e técnica; tracing das chamadas de IA |
| NFR-10 | i18n | PT-BR no MVP; strings externalizadas para futura tradução |

## 6. Jornadas críticas (user stories priorizadas)

**J1 — Aluno estuda com tutor (núcleo do produto).**
Como aluna, ao abrir uma lição quero tirar dúvidas com o tutor sem sair da página, para não travar meu estudo.
Fluxo: abre lição → lê/assiste → abre tutor → pergunta → resposta fundamentada com referência → tutor propõe pergunta de verificação → evidência registrada no learner model.
Aceite: TUT-01, TUT-02, LRN-01.

**J2 — Instrutor cria curso a partir de material existente.**
Como instrutor, quero transformar minha apostila PDF em curso estruturado em menos de uma hora.
Fluxo: upload → IA propõe estrutura e conceitos → revisão/edição → publica → convida turma.
Aceite: CUR-05, CUR-03, ONB-01.

**J3 — Admin ativa a igreja na plataforma.**
Como administradora, quero cadastrar nossa igreja, colocar nossa marca e matricular 200 alunos em uma tarde.
Aceite: ONB-01, TEN-03, AUTH-02.

**J4 — Aluno mantém o hábito.**
Como aluno, quero minha revisão diária curta (5–10 min) que mantém meu streak e consolida o que aprendi.
Aceite: LRN-02, GAM-02, GAM-04.

**J5 — Instrutor intervém a tempo.**
Como instrutor, quero ser alertado quando um aluno está em risco de abandonar, para agir antes da evasão.
Aceite: LRN-04, ANL-03.

## 7. Faseamento de releases

| Release | Conteúdo | Critério de saída |
|---|---|---|
| 0.9 (interna) | Tenancy + RLS + IBC migrado como tenant 1 | Suíte de isolamento verde; paridade funcional com produção atual |
| 1.0 (MVP SaaS) | Tutor v1, learner model v1, billing, onboarding, 2º tenant piloto | 2 tenants ativos; NFR-01/03/07 atendidos |
| 1.1 | Importação automática de curso, white-label domínio próprio, revisão espaçada v2, **templates corporativos + relatório de competências (RH) + checkout de curso avulso (Fase 2 da visão §5.2)** | 10 tenants pagantes, ≥1 tenant corporativo e ≥1 produtor de cursos livres |
| 1.2 | API pública, relatórios avançados, SSO | Primeiro cliente Enterprise |

## 8. Questões em aberto (decisões pendentes do fundador)

1. ~~Nome comercial~~ **RESOLVIDO: XR Educação** (registrar domínio e marca INPI — pendente apenas execução).
2. Gateway: Asaas (recomendado p/ Pix+boleto nacional) vs. Stripe (melhor DX). Decisão até Release 0.9.
3. Política de conteúdo entre tenants de denominações distintas (neutralidade doutrinária da plataforma — recomendação: plataforma é agnóstica; conteúdo é 100% do tenant).
4. Vida em Prática como template ONB-02 ou como curso demonstrativo público.
