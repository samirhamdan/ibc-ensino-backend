# UX_TUTOR_SAAS.md — Experiência do Tutor de IA
**Produto:** XR Educação · **Versão:** 1.0
**Persona principal:** P1 (Ana — aluna, mobile-first, estuda à noite, 20–40 min/sessão)
**Requisitos:** TUT-01–05, LRN-01/02, doc 03 (arquitetura de IA) §1–2, §6
**Branch sugerida:** `feat/TUT-01-tutor-ux` (depende do módulo `ai/` — Release 1.0)

---

## 0. Princípio-mãe

O tutor não é um chatbot colado na plataforma; é **parte da lição**. Toda decisão de UX deriva disso: ele aparece onde a dúvida nasce, responde ancorado no material, e devolve o aluno ao estudo — nunca vira um destino em si. Métrica de design: o sucesso do tutor é o aluno **voltar para a lição**, não ficar no chat.

## 1. Estado atual

Não existe experiência de tutor — o slot foi reservado no dashboard (UX_ALUNO_SAAS §3, Grupo 2: "Tirar dúvida com o tutor" atrás de `tutor_enabled`). Este documento especifica o que esse slot abre. Backend correspondente: doc 03 §2 (orchestrator, modos, guardrails, RAG).

## 2. Onde o tutor vive (pontos de entrada)

| Entrada | Contexto carregado | Prioridade |
|---|---|---|
| Botão fixo dentro da lição ("Tirar dúvida") | Lição atual + posição do aluno nela | P0 — a entrada canônica |
| Seleção de texto na lição → "Perguntar sobre isso" | Trecho selecionado + lição | P1 — reduz o custo de formular a pergunta |
| Card hero do dashboard | Última lição em andamento | P0 (slot já existe) |
| Após errar questão de quiz | Questão + alternativa escolhida (modo socrático automático) | P1 — o momento de maior valor pedagógico |
| Revisão do dia | Item de revisão (modo revisor) | P1, junto com LRN-02 |

**Não há entrada "genérica" (chat global sem contexto)** no MVP — tutor sem contexto de lição incentiva conversa fora de escopo e piora o custo (doc 03 §8).

## 3. Anatomia da interface

### 3.1 Contêiner
- **Mobile (padrão de projeto):** bottom sheet que sobe cobrindo ~85% da tela, com a lição visível numa fresta no topo (âncora de contexto — o aluno "vê" que continua na lição). Arrastar para baixo fecha; estado da conversa persiste ao reabrir na mesma lição.
- **Desktop:** painel lateral direito (400px), lição permanece visível e rolável ao lado — pergunta e material lado a lado é o layout que sustenta "responder ancorado no material".
- Nunca modal bloqueante; nunca página separada.

### 3.2 Cabeçalho do painel
- Nome do tutor (configurável pelo tenant? **Não no MVP** — nome fixo "Tutor", identidade da plataforma; personalização de persona é decisão pedagógica delicada, adiada) + chip da lição atual ("Lição 3 · Hermenêutica").
- Ícone de informação → folha "Como o tutor funciona": responde com base no material do curso; o instrutor pode ver as conversas (transparência LGPD, doc 03 §6 — dito ANTES da primeira pergunta, não escondido em termos); pode errar — sempre confira com o material.

### 3.3 Mensagens
- Bolhas simples, alto contraste, tipografia da plataforma. Resposta do tutor em **streaming** (primeiro token <3s, NFR-03) com indicador de digitação até o primeiro token.
- **Fontes visíveis**: quando a resposta afirma conteúdo do curso, chips de fonte abaixo da bolha ("📄 Lição 2 · seção Contexto histórico" — sem emoji nativo, ícone Lucide) → clicar rola/abre o trecho na lição. É o elemento de UI que materializa a promessa "fundamentado no material" e o que diferencia de um ChatGPT embutido.
- Resposta sem fundamentação suficiente (doc 03 §2.1 passo 5): a própria bolha declara — "Isso vai além do material deste curso, mas em geral..." com estilo visual levemente distinto (borda tracejada). Honestidade epistêmica como elemento visual.
- Ao final de explicações, a **pergunta de verificação** chega como card destacado com campo de resposta próprio (não bolha comum) — sinaliza "isto é um micro-exercício" e alimenta o learner model com peso 0,5 (doc 03 §3.3). Responder é opcional; ignorar não pune.

### 3.4 Composer (entrada)
- Campo de texto + enviar. **Sugestões contextuais** acima do campo na abertura (3 chips): "Explica esta seção de outro jeito" · "Me dá um exemplo prático" · "Por que isso importa?" — resolve a tela em branco, que é onde alunos menos confiantes desistem.
- Sem upload de arquivo no MVP; sem áudio no MVP (roadmap: ditado por voz é natural para o público noturno/mobile — P2).

## 4. Os modos, traduzidos em experiência (doc 03 §2.2)

| Modo | Como o aluno percebe (sem jargão de "modo") |
|---|---|
| Explicador | Comportamento padrão: passos curtos, um conceito por mensagem, exemplo, pergunta de verificação no fim |
| Socrático | Ao pedir resposta de atividade avaliativa: "Vou te ajudar a chegar lá 😉→(sem emoji; texto direto: 'Vou te ajudar a chegar na resposta — primeiro me diz...')" + **dicas graduais** com UI própria: botão "Quero uma dica" (nível 1→2→3), cada nível revelado sob demanda. O aluno sente progressão, não bloqueio |
| Revisor | Na Revisão do dia: fluxo guiado item a item, barra de progresso (3/7), feedback imediato certo/errado com explicação curta, streak confirmado ao final |
| Acolhedor | Sinais de frustração: tom muda, meta reduz ("que tal só terminar esta seção hoje?"), sem exposição do mecanismo. Se recorrente, aviso discreto ao instrutor (ANL-03) |

**Regra de transparência dos limites:** quando o guardrail recusa (fora de escopo, tema sensível), a mensagem é fixa, gentil e com saída: fora de escopo → "Consigo ajudar melhor com o conteúdo deste curso. Sobre [tema da lição], o que você quer entender?"; tema sensível → mensagem acolhedora fixa + botão [Falar com o instrutor] (encaminhamento TUT-04 em 1 toque). Nunca um "não posso responder isso" seco.

## 5. Cota e degradação (TUT-05) — UX do limite

- O aluno **não vê contador** de interações (ansiedade desnecessária); o admin do tenant vê.
- Ao atingir a cota do tenant: o tutor não some — degrada com dignidade: busca no cache semântico/FAQ do curso e responde "Encontrei isto de uma dúvida parecida:" com a resposta cacheada + "Seu grupo atingiu o limite de perguntas novas deste mês; perguntas voltam em [data]". Botão [Avisar meu administrador].
- Nunca: paywall na cara do aluno (a relação comercial é com o tenant, não com ele).

## 6. Estados obrigatórios

- **Primeira abertura (onboarding de 1 tela):** o que ele faz, o que não faz, transparência instrutor — botão "Entendi, vamos lá". Nunca mais aparece.
- **Carregando resposta:** indicador + streaming (nunca spinner mudo >3s).
- **Erro de rede/provider:** "Não consegui responder agora. Sua pergunta ficou salva — tentar de novo?" (a pergunta não se perde; retry reaproveita).
- **Lição sem conteúdo indexado** (RAG vazio): tutor abre avisando que este material ainda não tem suporte completo e oferece encaminhar ao instrutor — melhor que alucinar.
- **Offline:** composer desabilitado com explicação curta.

## 7. Feedback e melhoria contínua (doc 03 §9)

- Por resposta: 👍/👎 discretos (ícones Lucide) no hover/toque longo; 👎 abre um "o que faltou?" opcional de 1 toque (Não entendi · Não era isso · Resposta errada). Alimenta a avaliação online.
- Encaminhar ao instrutor (TUT-04): disponível no menu da conversa; leva a conversa junto — o aluno não repete a dúvida.

## 8. Acessibilidade e performance (gates)

- Chat completo por teclado; `aria-live="polite"` nas respostas em streaming; foco gerenciado ao abrir/fechar o sheet; touch targets ≥44px; contraste AA nas bolhas em qualquer tema de tenant (as bolhas usam superfícies fixas da plataforma, não a cor do tenant — só acentos usam `--brand-primary`).
- Primeiro token <3s (p95); abertura do painel <300ms; conversa persiste por lição (recarregar a página não apaga).
- `prefers-reduced-motion`: sem animação de digitação, streaming vira blocos.

## 9. O que fica explicitamente fora do MVP

Nome/avatar de tutor por tenant · voz (entrada ou saída) · upload de imagem/arquivo pelo aluno · chat entre alunos · tutor fora do contexto de lição · histórico global pesquisável de conversas (P2; por lição basta no MVP).

## 10. Faseamento

| Fase | Entrega |
|---|---|
| P0 | Painel (sheet/lateral) + entrada na lição e no dashboard + explicador com streaming + fontes clicáveis + onboarding de 1 tela + estados de erro/cota |
| P1 | Socrático com dicas graduais + pós-erro de quiz + seleção de texto → pergunta + feedback 👍/👎 + encaminhar ao instrutor |
| P1 | Modo revisor integrado à Revisão do dia (junto com LRN-02) |
| P2 | Acolhedor + ditado por voz + histórico pesquisável |

## 11. Métricas de sucesso da experiência

- % de alunos ativos que usam o tutor na semana (adoção) e **taxa de retorno à lição** após conversa (o norte do §0 — alvo >80% das sessões de tutor terminam com navegação de volta ao conteúdo).
- "Resolveu minha dúvida" (👍) > 70%; taxa de acionamento de guardrail fora-de-escopo < 15% (acima disso, o problema é expectativa/onboarding, não os alunos).
- Ganho médio de domínio pós-interação (doc 03 §9) — a métrica pedagógica que importa.
