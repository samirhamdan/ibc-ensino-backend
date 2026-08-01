# O que vai acontecer com a XR Educação — Mapa de Transformação

**Escrito para:** você entender o caminho real, o timeline, os pontos de risco e o que muda na sua vida de fundador.

---

## Estado atual (julho/2026 — hoje)

**Onde você está:**
- **IBC Ensino em produção:** uma plataforma de aprendizagem (Rails → Flask/React, agora vanilla JS) rodando no Railway, com ~150–200 alunos na IBC, features de gamificação (pontos, conquistas, certificados), editor de cursos e quiz. É uma aplicação monolítica, single-tenant (dados da IBC só da IBC, mas porque não tem multi-tenant), sem tutor de IA, sem medição de aprendizado real.
- **Operação:** você (solo) mantém, evolui e suporta. Sprints 6.1–6.3 entregues; streaks e cards Netflix "congelados" à espera de roadmap multi-tenant.
- **Faturamento:** zero (IBC é cliente interno/gratuito, validação de produto).
- **Visibilidade:** regional (rede IBC, conhecidos em Campo Grande), nenhuma presença no mercado edtech nacional.

---

## Fases de transformação (timeline realista)

### **FASE 0.9 — Multi-tenancy (agosto–outubro 2026, ~6 semanas)**

**O que vai mudar:**

A plataforma deixa de ser "IBC Ensino" e vira a **infraestrutura técnica de XR Educação**. IBC continua funcionando idêntico, mas agora é o **Tenant nº 1** de um sistema que consegue hospedar N clientes com dados isolados e seguros.

**Entregas concretas:**
- Migração de banco de dados com expand/contract/backfill (zero downtime perceptível).
- Row-Level Security (RLS) ativado no PostgreSQL — garantia técnica de isolamento.
- Suíte automatizada de testes de isolamento que roda em CI — qualquer novo código que vaze dados entre tenants é bloqueado antes de ir para produção.
- Autenticação por subdomínio (ibc.xreducacao.com.br, demo.xreducacao.com.br, etc.).
- Painel de operação: você consegue criar, suspender e gerenciar tenants.
- Release **0.9 sai de produção** com **2 tenants funcionando** (IBC + demo/piloto).

**Por que isso importa:**
- Você sai de "produto customizado para uma igreja" e entra em "plataforma SaaS".
- Risco técnico eliminado: se o isolamento falha aqui, os próximos passos são impossíveis.
- Você finalmente consegue dizer "temos multi-tenant" em conversas com potenciais clientes/investidores.

**Seu tempo:** 100% engajado com Claude Code (Phases 1–6 do playbook). Sem novas features. Suporte mínimo ao IBC. Estimativa solo: 6 semanas se rigoroso no planejamento; 8–10 se tiver regredir.

**Risco real:** quebrar algo do IBC durante a migração. Prevenção: testes de caracterização (Fase 1 do playbook) capturam tudo o que o sistema faz hoje; downgrade de BD é testado antes de produção.

---

### **RELEASE 1.0 — Tutor de IA + Learner Model (outubro–dezembro 2026, ~8 semanas pós-0.9)**

**O que vai mudar:**

A plataforma ganha seu **diferencial defensável**: o tutor de IA dentro de cada lição que:
- Responde dúvidas do aluno fundamentadas no material do curso (RAG).
- Detecta quando o aluno pediu a resposta de um quiz e força modo socrático (ensina a pensar, não entrega).
- Aprende o nível de cada aluno por conceito (learner model) e calibra a dificuldade das perguntas para cada um.
- Alimenta uma fila diária de revisão espaçada (o aluno revisa 5–10 conceitos/dia, mantém streak, consolida aprendizado).

**Entregas concretas:**
- Módulo `ai/` completo: tutor em Python/Claude API, guardrails de segurança (não responde fora do escopo, não entraja a resposta de avaliativas), cache de dúvidas repetidas.
- Módulo `learning/`: learner model (domínio por conceito), revisão espaçada (SM-2), risco de evasão.
- Dashboard do instrutor: "Domínio médio da turma é 62% no conceito X" + alertas de risco.
- Billing: integração Asaas para cobrança mensal (Pix, boleto, cartão).
- Onboarding: admin novo consegue criar um curso em <1 hora a partir de template ou import de PDF.
- Release **1.0 sai de produção** com IBC + 1 novo tenant piloto funcionando.

**Entregas de design/UX:**
- Dashboard do aluno conforme `UX_ALUNO.md`: 5 grupos verticais (saudação, continue, sua pontuação, próximas metas, recomendações), zero emojis nativos, design system teal #008ea8 para IBC (configurável por tenant).
- Streaks migrados de localStorage para servidor (agora funcionam em qualquer dispositivo).
- Cards Netflix-style + micro-interações nas trilhas.

**Por que isso importa:**
- Você saiu de "LMS que distribui conteúdo" para "plataforma que **garante aprendizagem**".
- O tutor é visível, os alunos percebem que "estudar aqui é diferente".
- Dados de conclusão e retenção ficam muito melhores (prova de conceito).
- Você pode começar a falar com clientes corporativos de verdade (eles compram resultado, não video-player).

**Seu tempo:** 60–70% com dev/Claude Code (tutor, learner model, integração Asaas), 20% com testes pedagógicos (garantir que o tutor não alucina, que guardrails funcionam), 10% com IBC (novos tenants piloto).

**Custo de IA (real):** ~R$ 60–80/aluno intenso/mês com o tutor. Cotas por plano mantêm isso controlado; com cache semântico, cai para ~R$ 30–40. Monitorar desde o dia 1.

**Risco real:** tutor gera respostas fora do escopo ou muito genéricas (não usa RAG bem). Prevenção: suíte de testes com 60+ casos adversariais roda em CI; feedback dos alunos do IBC (mês 1) valida qualidade antes de oferecer para outros tenants.

---

### **RELEASE 1.1 — Fase 2 (Corporativo + Cursos Livres) – início 2027, ~10 semanas**

**O que vai mudar:**

A plataforma deixa de ser exclusiva de nicho confessional e entra no mercado principal: educação corporativa (treinamento de equipes) e cursos livres (produtores de conteúdo premium).

**Entregas concretas:**
- **Templates corporativos:** onboarding, compliance, treinamento técnico, desenvolvimento de liderança (4–5 templates pré-estruturados).
- **Importação automática de curso:** você sobe um PDF → IA propõe estrutura + conceitos → publica em 30 min (vs. 1 hora manual hoje). Instrutor só revisa.
- **Relatório de competências p/ RH:** "João dominou 80% de X competência; Maria ainda está em risco em Y; turma tem gap em Z". Exportável para HRIS (SuccessFactors, BambooHR, etc.).
- **Checkout e venda avulsa:** produtor de curso publica na XR Educação; aluno compra Pix/cartão; produtor recebe em 24h (como Hotmart, mas com tutor de IA incluído).
- **White-label por domínio próprio:** cliente grande quer xr-educacao.seudominio.com.br com sua marca — feito com SSL automático.

**Clientes-alvo do lançamento:**
- **Alessio Climatização (seu próprio cliente interno):** treinamento de vendedores + técnicos de instalação. Estimado R$ 699/mês.
- **3–5 produtores de cursos premium:** ex.: curso de "JavaScript Avançado" com tutor de IA. Revenue share 70/30 (produtor/XR) no ano 1. Estimado R$ 500–2k/mês cada.
- **SMB local em MS:** associações comerciais, Sebrae, consultório/clínica de treinamento. Estimado R$ 349–699/mês cada.

**Por que isso importa:**
- Ticket-alvo sobe de R$ 149–499 (igrejas) para R$ 349–5k (corporativo).
- Volume potencial é 100× maior (mercado de T&D corporativo brasileiro é de bilhões/ano).
- Você deixa de ser "edtech religiosa" e vira "edtech com tutor de IA para qualquer mercado".
- Prova de tração em dois segmentos = interessante para investidores / editais.

**Seu tempo:** 50% dev (templates, importação, checkout), 30% go-to-market (conversas com Alessio, produtores, SMBs), 20% suporte/operação.

**Faturamento realista em Release 1.1:**
- IBC: R$ 0/mês (ainda interno).
- Alessio: R$ 699/mês (certeza alta).
- 2–3 produtores de cursos: R$ 1.200–3k/mês.
- 5–10 clientes SMB: R$ 2k–5k/mês.
- **Total: R$ 4k–9k/mês** (não é Amazon, mas é real, recorrente e prova de mercado).

**Risco real:** você quer correr atrás de 10 segmentos ao mesmo tempo, perde foco, o produto fica meia-boca para todos. Prevenção: Release 1.1 prioriza apenas corporativo SMB + produtores de cursos (2 segmentos). Escolas vão para Release 1.2.

---

### **RELEASE 1.2 — Escala + Enterprise (2027–2028, 3–6 meses)**

**O que vai mudar:**

Você sai de "startup em tração" e entra em "empresa pequena com mercado claro".

**Entregas concretas:**
- **API pública versionada:** partners e integradores conseguem buildar sobre XR Educação.
- **SSO (OIDC):** cliente Enterprise conecta seu Azure AD / Google Workspace e faz onboarding de 100 alunos em 5 min.
- **Relatórios avançados:** compliance (LMS para educação formal exige auditoria), análise de aprendizagem por coorte, previsão de evasão com IA.
- **Conformidade educacional:** se entrar em escolas confessionais formais, compliance BNCC/CNE.
- **Instâncias dedicadas:** cliente Enterprise quer seu banco de dados isolado / infrastructure própria — ofertar sob demanda (margem gorda).

**Clientes esperados na fase:**
- Primeira escola confessional de porte (50–200 alunos).
- Primeira empresa média de T&D (500–2k alunos).
- Eventual cliente Enterprise (5k+ alunos) com SLA.

**Faturamento esperado:**
- Portfólio Release 1.1 recorrente: ~R$ 4k–9k/mês.
- 10–20 clientes SMB novos acumulados: +R$ 5k–10k/mês.
- 1–2 clientes de porte: +R$ 2k–5k/mês.
- **Total: R$ 11k–24k/mês** (em regime, acumulado).

---

## Seu status pessoal — mudanças reais

| Hoje (jul/2026) | Após Release 0.9 (out/2026) | Após Release 1.0 (dez/2026) | Após Release 1.1 (mar/2027) |
|---|---|---|---|
| Solo dev em monolito single-tenant | Solo dev em SaaS multi-tenant | Dev + suporte a 2–3 tenants | Dev (30%) + CEO (70%): conversas com clientes, vendas, decisões |
| Zero receita | R$ 0, mas infra pronta | R$ 500–2k tração inicial | R$ 4k–9k mensal recorrente |
| Nenhuma validação externa | Isolamento validado, produto estável | Tutor validado como diferencial | Dois segmentos validados; produto claro |
| Perfil: engenheiro | Perfil: ainda engenheiro (90%) + empresário (10%) | Transição: engenheiro (70%) + empresário (30%) | Empresário de tech (60%) + dev advisor (40%) |
| Código + infra é 100% da responsabilidade | Idem, + gerenciar tenants, RTOs, backups | Idem, + decidir sobre features x bugs x debt técnico | Idem, + recrutamento, precisa de 1–2 devs para não ficar insano |

---

## Cenários realistas — o que pode acontecer

### Cenário 1 — Execução limpa (70% de probabilidade)

- Release 0.9 sai a tempo, isolamento é robusto.
- Release 1.0 o tutor de IA funciona bem, IBC e tenants piloto validam qualidade.
- Release 1.1 você convence 3–5 clientes pagantes em paralelo.
- **Resultado:** fim de 2027 você tem receita de R$ 4k–9k/mês, pull real de market fit, consegue atrair investimento anjo ou edital de fomento (Centelha 4, FINEP, Sebrae). Decisão clara: contratar 1º dev e focar em vendas ou manter solo e crescer lento.

### Cenário 2 — Atrito técnico (20% de probabilidade)

- Release 0.9 demora mais do que esperado (Claude Code esbarra em edge case, quebra algo do IBC).
- Release 1.0 atrasa 4–6 semanas porque tutor de IA precisa calibragem real com dados da IBC.
- **Resultado:** calendário aperta, você trabalha muito em jan–fev/2027, Release 1.1 sai em junho/2027 em vez de março. Receita sai 3 meses depois. Não é fracasso, é desvio realista em startups de tech. Risco: você queima, quer parar ou perde foco.

### Cenário 3 — Go-to-market falha (10% de probabilidade)

- Você constrói tudo perfeito tecnicamente.
- Ninguém compra (falta de distribuição, preço errado, mensagem não cola, concorrência aparece).
- **Resultado:** Release 1.1 sai, mas IBC continua sendo o único tenant pagante. Você está com receita R$ 0/mês ainda. Decisão necessária: pivotar (mudar segmento), ficar em nicho confessional e crescer lento, ou parar. O risco aqui não é técnico, é de produto-market fit — a lição: começar vendas em Release 1.0, não em 1.1.

---

## O que você precisa decidir agora (antes de começar)

1. **Comprometimento:** Releases 0.9 + 1.0 = 4 meses de foco extremo. Você consegue? (Alessio, clientes existentes, vida pessoal — tudo vai pro segundo plano.) Se não, estenda para 6 meses com ritmo mais leve.
2. **Editais como fundo:** a regularização da XR Solutions (situação INAPTA) é pré-requisito. Resolver com contador AGORA, não em 3 meses.
3. **Mentoria / suporte:** você solo vai ter picos de burnout. Encontre alguém (co-founder, mentor, grupo de founders) que você liga toda semana pra bater um papo real.
4. **Go-to-market cedo:** não espere Release 1.1 pra falar com clientes. Em Release 1.0, já comece conversas de propósito com 5–10 potenciais clientes corporativos / produtores de curso. Validação paralela muda tudo.

---

## Síntese — para você explicar para outros

**Hoje:** você tem um LMS educacional (IBC Ensino) em produção, single-tenant, sem IA, baseado em gamificação simples. Funciona, mas é um produto customizado para uma igreja.

**Após executar este planejamento:**

- **Release 0.9 (ago–out/2026):** plataforma vira multi-tenant com isolamento garantido. Infra de SaaS pronta. Você consegue colocar N clientes sem compartilhar dados. Tecnicamente robusto.
- **Release 1.0 (out–dez/2026):** tutor de IA que aprende cada aluno e personaliza conteúdo em tempo real. É o diferencial defensável. Igrejas/educação confessional vira feito; agora é uma plataforma real com IA pedagógica.
- **Release 1.1 (jan–mar/2027):** entra no mercado corporativo (T&D) + cursos livres. Primeiros clientes pagantes (Alessio, produtores, SMBs). Faturamento sai do zero para alguns milhares/mês. Prova de mercado em 2 segmentos.

**Resultado:** de engenheiro solo mantendo um LMS para uma igreja, você vira founder com SaaS com tutor de IA, validação de mercado em múltiplos segmentos e receita recorrente. Posição competitiva clara vs. Moodle/Hotmart/plataformas genéricas. Pronto para levantar capital ou crescer bootstrapped.

**Tempo total:** 4–6 meses de trabalho intenso. Você sai exausto, mas com produto real, clientes reais e visibilidade.

**Risco financeiro:** R$ 0 até Release 1.1 (continue com Alessio/Laia se precisar de cashflow). Release 1.1 em diante, receita começa de verdade.

---

**Próximo passo concreto:** escolha uma data de início (sugestão: segunda semana de agosto/2026) e abra a Release 0.9 com Claude Code.
