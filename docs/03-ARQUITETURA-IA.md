# Arquitetura de IA — Tutor, Learner Model e Ciência Cognitiva
**Produto:** XR Educação
**Versão:** 1.0 | Julho/2026
**Documentos relacionados:** 00-VISAO.md · 01-PRD.md · 02-ARQUITETURA.md

---

## 1. Fundamentos pedagógicos (por que o tutor funciona)

O tutor não é um chatbot com acesso ao curso. É um agente pedagógico cujo comportamento implementa seis princípios com forte evidência em ciência cognitiva. Cada princípio mapeia para um mecanismo concreto do sistema:

| Princípio | Evidência | Mecanismo no produto |
|---|---|---|
| **Prática de recuperação** (testing effect) | Recuperar da memória consolida mais que reler | Tutor encerra interações com pergunta de verificação; quizzes geram evidência de domínio |
| **Repetição espaçada** | Intervalos crescentes combatem a curva do esquecimento | Fila diária de revisão (§4.3) integrada aos streaks |
| **Intercalação** | Misturar conceitos supera prática em bloco | Fila de revisão mistura conceitos de lições diferentes |
| **Carga cognitiva** (Sweller) | Memória de trabalho é limitada; reduzir carga extrínseca | Tutor responde em passos curtos; uma ideia por mensagem; scaffolding progressivo |
| **Zona de desenvolvimento proximal** (Vygotsky) | Aprender no limite do que se consegue com ajuda | Dificuldade de perguntas calibrada pelo domínio atual do conceito (§3) |
| **Metacognição e feedback** | Feedback imediato e específico acelera aprendizagem | Correção explicativa em quizzes; mapa de domínio visível ao aluno |

**Anti-objetivo explícito:** o tutor não deve maximizar "satisfação da resposta" (entregar a resposta agrada, mas prejudica a aprendizagem em contexto avaliativo). A métrica do tutor é ganho de domínio, não estrelas de avaliação.

## 2. Arquitetura do módulo `ai/`

```
app/ai/
├── providers/          # abstração de LLM (Claude API primário)
│   ├── base.py         # interface: complete(), stream(), embed()
│   ├── anthropic.py    # claude-sonnet-4-6 (tutor), haiku (tarefas leves)
│   └── router.py       # roteia tarefa → modelo por custo/qualidade
├── rag/
│   ├── ingestion.py    # chunking de lições → embeddings → pgvector
│   ├── retrieval.py    # busca híbrida (vetorial + keyword), filtro tenant
│   └── chunking.py     # ~500 tokens, overlap 80, respeita blocos
├── tutor/
│   ├── orchestrator.py # monta contexto, chama LLM, streaming SSE
│   ├── prompts/        # templates versionados (system, socrático, revisão)
│   ├── modes.py        # explicador | socrático | revisor | acolhedor
│   └── memory.py       # janela da sessão + resumo persistente por curso
├── guardrails/
│   ├── input.py        # classificação da pergunta (escopo, sensível, injection)
│   ├── output.py       # verificação de fundamentação e política
│   └── policies.py     # política por tenant (rigidez socrática, temas)
├── grading/            # correção assistida de atividades abertas (CUR-04)
├── importer/           # estruturação de curso a partir de PDF/DOCX (CUR-05)
└── metering.py         # tokens, custo, cotas por tenant (BIL-03)
```

### 2.1 Fluxo de uma interação do tutor (TUT-01)

1. **Entrada:** mensagem do aluno + `licao_id` + sessão.
2. **Guardrail de entrada (haiku, ~200ms):** classifica em `no_escopo | fora_de_escopo | pedido_de_resposta_avaliativa | sensivel | prompt_injection`. Caminhos fora do escopo nem chegam ao modelo principal (economia + segurança).
3. **Montagem de contexto:** system prompt do modo ativo + perfil resumido do aluno (domínio dos conceitos da lição, últimas dificuldades) + chunks recuperados (retrieval híbrido top-6, filtrado por tenant e curso) + janela da conversa (últimas N mensagens + resumo).
4. **Geração (sonnet, streaming SSE):** resposta fundamentada; instrução de citar a lição-fonte quando afirmar conteúdo do curso.
5. **Pós-processamento:** extração de "fontes" para a UI; se a resposta afirma conteúdo sem chunk de suporte, marcador de baixa confiança + reformulação ("isso vai além do material do curso...").
6. **Efeitos:** evento `tutor.interacao` → evidência no learner model (§3.3), medição de custo, analytics.

### 2.2 Modos do tutor

| Modo | Gatilho | Comportamento |
|---|---|---|
| Explicador | Dúvida conceitual | Explica em passos curtos, exemplo contextualizado, encerra com pergunta de verificação |
| Socrático | Pergunta sobre atividade avaliativa (TUT-02) | Nunca entrega resposta; decompõe em subperguntas; dá dicas graduais (3 níveis); rigidez configurável por curso |
| Revisor | Sessão de revisão diária | Conduz recuperação ativa dos itens vencidos; feedback imediato; atualiza review_items |
| Acolhedor | Sinais de frustração/desânimo | Valida o esforço, reduz a meta da sessão, sugere pausa ou lição mais leve; aciona alerta ao instrutor se recorrente |

## 3. Learner Model (LRN-01)

### 3.1 Representação
Estado por `(aluno, conceito)`: `dominio ∈ [0,1]`, contagem de evidências, timestamp. Conceitos são declarados pelo instrutor por lição/questão (CUR-03) — o grafo de pré-requisitos entre conceitos é opcional no MVP (v2).

### 3.2 Atualização (v1 — média exponencial ponderada por evidência)
Escolha deliberada: modelo **simples, determinístico e explicável** antes de knowledge tracing bayesiano (BKT) ou deep knowledge tracing. Fórmula:

```
dominio_novo = dominio_atual + α(e) × (resultado − dominio_atual)
```
onde `resultado ∈ [0,1]` é o desempenho da evidência e `α(e)` decresce com o nº de evidências (0,4 → 0,15), estabilizando o estado. Pesos por tipo de evidência: quiz 1,0 · revisão 0,8 · pergunta de verificação do tutor 0,5 · atividade aberta corrigida 1,0. Decaimento temporal leve (esquecimento): −0,02/semana sem evidência, piso 0,3.

### 3.3 Evidências vindas do tutor
A pergunta de verificação ao final de interações (modo explicador) é avaliada pelo próprio LLM em rubrica 0–1 com justificativa registrada; evidência de peso reduzido (0,5) por ser avaliação automática.

### 3.4 Uso do estado
Calibra dificuldade das perguntas do tutor (ZPD), alimenta a fila de revisão, gera o mapa de domínio do aluno, compõe o heatmap da turma (ANL-01) e o score de risco de evasão (LRN-04: inatividade × queda de domínio × abandono de sessão, pesos versionados).

## 4. Revisão espaçada (LRN-02)

### 4.1 Unidade de revisão
Item = conceito com domínio ≥ 0,4 (já aprendido minimamente). Perguntas de revisão: banco do instrutor primeiro; geração por IA com aprovação do instrutor como fallback (nunca pergunta gerada sem revisão em contexto avaliativo).

### 4.2 Experiência
"Revisão do dia": 5–10 itens, ~5 min, no grupo PRÓXIMAS METAS do dashboard (UX_ALUNO.md). Completa a revisão → mantém streak (GAM-02). Intercalação garantida (itens de ≥2 cursos/lições quando disponível).

### 4.3 Algoritmo (v1 — SM-2 modificado)
SM-2 clássico com ajustes: intervalo inicial 1d → 3d → 7d; fator de facilidade acoplado ao domínio do conceito (domínio alto alonga intervalos); teto de 60 dias no MVP. v2 (Release 1.1): FSRS, que ajusta parâmetros por aluno com melhor retenção por revisão.

## 5. RAG — ingestão e recuperação

**Ingestão (worker, evento `licao.publicada`):** blocos de texto da lição → limpeza → chunking (~500 tokens, overlap 80, nunca cruza fronteira de bloco) → embedding (voyage-3 ou equivalente via provider) → `content_chunks` com `tenant_id`, `licao_id`, metadados. Vídeos: transcrição (v1: instrutor cola transcrição; v2: transcrição automática) entra no mesmo pipeline.

**Recuperação:** filtro duro por `tenant_id` + curso **antes** da similaridade (nunca busca vetorial global); híbrido: top-20 vetorial (HNSW) + BM25 keyword → fusão RRF → top-6 ao contexto. Latência-alvo p95 < 200ms.

**Qualidade:** conjunto dourado de 30–50 perguntas/curso com chunks esperados (montado com o instrutor no onboarding do IBC); recall@6 ≥ 0,85 como gate de regressão quando mudar chunking/embedding.

## 6. Guardrails e segurança de IA

**Entrada (classificador haiku + regras):**
- `fora_de_escopo`: redirecionamento cordial ao tema do curso; sem chamada ao modelo principal.
- `sensivel` (sofrimento emocional, temas de risco): resposta acolhedora fixa (não gerada), orientação a procurar o instrutor/liderança e canais de apoio; sinalização ao instrutor conforme política do tenant. O tutor nunca faz aconselhamento pastoral ou de saúde mental.
- `prompt_injection` (instruções para ignorar regras, exfiltrar prompt, mudar persona): recusa padrão; conteúdo de lições e mensagens é tratado como dado, nunca como instrução (delimitação estrita no template).
- `pedido_de_resposta_avaliativa`: força modo socrático (TUT-02).

**Saída:** verificação de fundamentação (afirmações de conteúdo devem ter chunk de suporte; senão, reformular com transparência); filtro de política do tenant (ex.: neutralidade em temas doutrinários controversos — configurável, ver PRD §8.3); nunca revelar dados de outros alunos.

**Testes:** fixture adversarial versionada (≥60 casos: injections, fora de escopo, sensíveis, pedidos de cola) rodando em CI contra os guardrails; adição de caso novo a cada incidente real (processo de post-mortem).

**Transparência (LGPD/ética):** aluno informado no onboarding de que conversas são visíveis ao instrutor e usadas para personalizar o ensino; retenção configurável (doc 02 §6).

## 7. Abstração de provider e roteamento de modelos

Interface única (`providers/base.py`) com implementação Anthropic como primária. Roteamento por tarefa:

| Tarefa | Modelo | Racional |
|---|---|---|
| Tutor (diálogo) | claude-sonnet-4-6 | Qualidade pedagógica, custo/latência equilibrados |
| Classificação de entrada, títulos, resumos de sessão | claude-haiku-4-5 | ~10× mais barato, latência baixa |
| Importação de curso, correção de atividade aberta | claude-sonnet-4-6 (batch quando possível) | Qualidade em tarefa assíncrona; batch reduz custo |
| Embeddings | provider dedicado (voyage) | Especializado, barato |

Prompts versionados em arquivos (`prompts/*.md` com front-matter: versão, modelo, data, changelog) — mudança de prompt é PR revisável, com avaliação no conjunto dourado antes de merge.

## 8. Economia de IA (NFR-07 — margem protegida por arquitetura)

**Estimativa por interação de tutor (sonnet):** contexto ~3,5k tokens de entrada (system + perfil + 6 chunks + janela) + ~350 de saída ≈ US$ 0,015–0,02. Aluno engajado: ~40 interações/mês ≈ US$ 0,6–0,8 ≈ R$ 3,5–4,5/aluno intenso.

**Mecanismos de controle:**
1. **Cotas por plano (TUT-05):** Semente ~150 interações/aluno/mês (folga sobre o uso típico), com degradação graciosa (cache/FAQ) ao teto.
2. **Cache de respostas frequentes:** perguntas semanticamente similares dentro do mesmo curso (similaridade > 0,95) servem resposta cacheada com revalidação — dúvidas de turma são altamente repetitivas (30–50% de acerto de cache esperado).
3. **Prompt caching (Anthropic):** system prompt + chunks estáveis da lição marcados como cache — reduz custo de entrada de interações subsequentes na mesma lição em até ~90%.
4. **Roteamento (§7)** e guardrail de entrada barato evitando chamadas caras.
5. **Medição em tempo real (`metering.py`):** custo por tenant/dia; alerta ao operador a 80% da cota; relatório mensal (BIL-03).

**Meta consolidada:** custo de IA < 8% da receita do tenant em regime. Plano Semente (R$149, 50 alunos): pior caso realista ~R$ 60–80 de IA/mês sem cache → ~R$ 25–35 com cache e cotas → dentro da meta com folga apertada; monitorar desde o piloto.

## 9. Avaliação contínua da qualidade pedagógica

1. **Offline:** conjunto dourado de perguntas/curso (recall de RAG §5 + rubrica de qualidade de resposta avaliada por LLM juiz com amostragem humana mensal).
2. **Online:** taxa de "resolveu minha dúvida" (feedback binário no chat), ganho médio de domínio pós-interação, taxa de escalonamento ao instrutor, taxa de acionamento de guardrails.
3. **Pedagógico (o que importa):** conclusão de trilhas e retenção de conteúdo (desempenho em revisões 30d depois) de alunos que usam o tutor vs. não usam — análise trimestral, com honestidade metodológica (viés de seleção reconhecido).

## 10. Roteiro do módulo de IA

| Release | Entregas |
|---|---|
| 1.0 | Tutor (explicador + socrático), RAG v1, learner model v1, revisão SM-2, guardrails v1, metering, cache semântico |
| 1.1 | Importação automática de curso, transcrição de vídeo, FSRS, modo revisor completo, correção assistida de atividades abertas |
| 1.2 | Grafo de pré-requisitos entre conceitos, recomendação adaptativa v2, relatórios pedagógicos por IA para o instrutor ("resumo semanal da turma") |
