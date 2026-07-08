# Documento de Visão — Plataforma SaaS de Aprendizagem com IA
**Produto:** XR Educação — unidade de negócio do grupo **XR Solutions** (CNPJ 45.310.753/0001-31)
**Origem:** Evolução do IBC Ensino (ibc-ensino.up.railway.app)
**Versão:** 1.0 | Julho/2026
**Status:** Aprovado para detalhamento em PRD e Arquitetura

---

## 1. Declaração de Visão

> Transformar o IBC Ensino na XR Educação: uma plataforma SaaS multi-tenant de aprendizagem, na qual cada aluno recebe um tutor de IA pessoal que adapta conteúdo, ritmo e método ao seu perfil cognitivo em tempo real. Nascida validada no nicho confessional (IBC como cliente-fundador em produção), a XR Educação entra cedo nos mercados de educação corporativa e cursos livres para se posicionar como edtech emergente brasileira de IA pedagógica.

A tese central: LMS tradicionais entregam **conteúdo**; nós entregamos **aprendizagem**. A diferença é a camada de IA pedagógica que observa cada interação do aluno e intervém como um bom professor humano interviria.

## 2. Problema

| Dor | Quem sente | Evidência (contexto IBC) |
|---|---|---|
| Evasão alta em cursos online (70–90% de abandono em EAD assíncrono) | Instituição | Alunos abandonam trilhas após 2–3 lições |
| Conteúdo "tamanho único" — o mesmo vídeo/texto para todos | Aluno | Alunos com bases muito diferentes na mesma turma |
| Professor/coordenador sem visibilidade de quem está travado e por quê | Instrutor | Feedback só aparece em prova ou desistência |
| Igrejas e instituições pequenas não têm equipe pedagógica nem TI | Instituição | IBC dependeu de um único desenvolvedor (fundador) |
| Plataformas de mercado (Moodle, Hotmart, etc.) são genéricas, caras ou complexas demais | Instituição | Nenhuma opção nacional acessível com IA pedagógica embarcada |

## 3. Solução (proposta de valor)

**Para o aluno:** um tutor de IA disponível 24/7 dentro de cada lição, que responde dúvidas com base no material do curso (não em conhecimento genérico da internet), faz perguntas socráticas, gera revisões espaçadas personalizadas e ajusta a dificuldade das atividades ao seu domínio real.

**Para o instrutor:** dashboards de domínio por aluno e por conceito ("60% da turma não dominou o conceito X"), alertas de risco de evasão e sugestões de intervenção geradas por IA.

**Para a instituição:** plataforma white-label com sua marca, seus cursos e seus dados isolados, com preço acessível ao mercado brasileiro (cobrança em BRL, Pix, sem custo por aluno proibitivo).

## 4. Diferenciais defensáveis

1. **IA pedagógica, não chatbot genérico.** O tutor opera sobre um modelo do aluno (learner model) com rastreamento de domínio por conceito, aplicando princípios de ciência cognitiva (prática de recuperação, repetição espaçada, intercalação, carga cognitiva) — detalhados no documento 03.
2. **Vertical-first.** Entrada pelo nicho de igrejas/educação confessional, onde há confiança relacional (IBC como cliente-fundador e caso de referência), baixa concorrência direta e comunidade que se indica mutuamente.
3. **Custo de IA controlado por arquitetura.** RAG sobre o conteúdo do próprio curso + cache + modelos dimensionados por tarefa mantêm custo marginal por aluno baixo (ver doc 03, §8).
4. **Simplicidade operacional.** Instituição sem TI consegue operar: onboarding assistido por IA, importação de conteúdo (PDF, vídeo, docs) com estruturação automática em lições.

## 5. Mercado e sequência de entrada (acelerada)

### 5.1 Contexto de mercado

O Brasil concentra um dos maiores ecossistemas de edtechs da América Latina (centenas de empresas mapeadas pelos censos Abstartups/CIEB), mas o mercado permanece fragmentado em três blocos que a XR Educação atravessa com um único produto:

1. **Educação corporativa (T&D):** empresas brasileiras investem bilhões de reais por ano em treinamento e desenvolvimento, com dor crônica: baixa conclusão, zero personalização e nenhuma medição de retenção de conhecimento. LMS corporativos dominantes (ex.: plataformas internacionais licenciadas por usuário em dólar) são caros para PMEs. É exatamente onde o tutor de IA + learner model se diferencia: a empresa não compra "hospedagem de vídeo", compra **evidência de que a equipe aprendeu** (mapa de domínio por colaborador e por competência).
2. **Cursos livres / criadores de conteúdo educacional:** mercado massivo no Brasil (plataformas de infoprodutos movimentam bilhões/ano), mas as plataformas dominantes (Hotmart, Kiwify, Eduzz) são máquinas de **venda**, não de **aprendizagem** — a evasão pós-compra é o problema não resolvido. Produtores premium buscam diferenciação por resultado do aluno; o tutor de IA é essa diferenciação.
3. **Educação confessional:** nicho de entrada já validado (IBC em produção), com ~580 mil igrejas evangélicas no Brasil, milhares de seminários e institutos, baixa concorrência direta e forte efeito de indicação comunitária.

**Leitura estratégica:** o bloco 3 valida o produto com custo de aquisição próximo de zero (rede relacional); os blocos 1 e 2 são onde está o volume e o ticket — e a janela competitiva de IA pedagógica no Brasil ainda está aberta em 2026. Esperar 2027–2028 para entrar (plano anterior) desperdiçaria a vantagem de timing. Por isso a sequência foi antecipada.

### 5.2 Sequência de entrada revisada

**Fase 1 — Validação confessional (EM ANDAMENTO, 2026).** IBC Ensino em produção é a Fase 1 executada: produto real, alunos reais, métricas reais. Entregas restantes da fase: migração multi-tenant (Release 0.9), tutor de IA v1 e um segundo tenant do nicho para provar isolamento e repetibilidade. O nicho confessional continua sendo cultivado como base de receita recorrente e caso social — mas deixa de ser pré-requisito para as próximas fases.

**Fase 2 — Educação corporativa SMB + cursos livres (INÍCIO IMEDIATO PÓS-1.0, 2026–2027).** Antecipada de 2027–2028 para o ciclo atual. Dois movimentos paralelos com o mesmo produto:
- **Corporativo SMB:** onboarding/treinamento de equipes com trilhas + tutor + relatório de domínio por colaborador. Go-to-market inicial pela base quente existente: clientes e rede da Alessio (segurança eletrônica exige treinamento técnico e comercial recorrente — a própria Alessio é o tenant corporativo piloto), demais unidades do grupo XR Solutions e ecossistema local de Campo Grande/MS (Sebrae, associações comerciais). Ticket-alvo: R$ 349–1.500/mês.
- **Cursos livres:** produtores de conteúdo premium que querem vender "curso com tutor de IA" como diferencial. Go-to-market: parcerias com 3–5 produtores-âncora com revenue share no primeiro ano, depois self-service.
- Requisitos de produto adicionais (Release 1.1): templates corporativos (onboarding, compliance, produto/vendas), relatório de competências para RH, checkout/venda avulsa de curso para o caso cursos livres.

**Fase 3 — Escala como edtech (2027–2028).** Escolas confessionais e educação formal (compliance educacional), API pública, marketplace, clientes Enterprise. A marca XR Educação posiciona-se publicamente como edtech de IA pedagógica — participação em programas de aceleração, editais de fomento (§9-A) e comunidade edtech (ex.: eventos Abstartups) desde a Fase 2, não na Fase 3.

### 5.3 Posicionamento

"A plataforma onde o aluno realmente aprende": enquanto concorrentes vendem distribuição de conteúdo, a XR Educação vende ganho de domínio mensurável — com o tutor de IA como recurso visível e o learner model como ativo defensável. Mensagem por segmento: igrejas ("discipulado que acompanha cada membro"), empresas ("prova de que sua equipe aprendeu"), produtores ("seu curso com um tutor pessoal para cada aluno").

## 6. Modelo de negócio

Assinatura mensal por instituição (tenant), com degraus por número de alunos ativos:

| Plano | Alunos ativos | Preço-alvo | Recursos de IA |
|---|---|---|---|
| Semente | até 50 | R$ 149/mês | Tutor com cota mensal de interações |
| Crescimento | até 250 | R$ 349/mês | Tutor + revisão espaçada + analytics |
| Comunidade | até 1.000 | R$ 699/mês | Tudo + white-label completo + API |
| Enterprise | ilimitado | sob consulta | SSO, SLA, instância dedicada |

Cobrança nacional (Pix/boleto/cartão via Asaas ou Stripe BR). IA embutida no plano com cota justa (fair use) e add-on de créditos de IA para uso intensivo — isso protege a margem (ver doc 03, §8).

## 7. Princípios de produto (invioláveis)

1. **O tutor nunca substitui o professor; ele o multiplica.** Toda IA voltada ao aluno é auditável pelo instrutor.
2. **Dados do tenant pertencem ao tenant.** Isolamento estrito, exportação livre, conformidade LGPD.
3. **A IA responde a partir do material do curso.** Alucinação fora do escopo do conteúdo é falha de produto, não "limitação de LLM".
4. **Simplicidade antes de recurso.** Uma igreja de 80 membros precisa conseguir usar sem treinamento.
5. **Progressão honesta.** Gamificação (streaks, pontos, badges — já validados no IBC Ensino) serve à aprendizagem, nunca a métricas de vaidade.

## 8. Relação com o IBC Ensino (estratégia de evolução)

O IBC Ensino **não será reescrito do zero**. Ele se torna o **tenant nº 1** da plataforma. A evolução é incremental:

1. Extração da lógica de tenant (tenant_id em todas as entidades + middleware de resolução) sobre a base Flask/PostgreSQL existente.
2. Camada de IA (tutor + learner model) construída como módulo novo, plugável.
3. Painel de administração de tenants, billing e onboarding self-service.
4. IBC migra para o modelo multi-tenant em produção; segundo tenant piloto valida o isolamento.

Isso preserva os Sprints 6.x já entregues (perfis, conquistas, certificados, focus mode, feed) e os itens travados de roadmap (streaks Opção B; cards estilo Netflix F+A), que passam a ser recursos da plataforma, não do IBC.

## 9. Riscos principais e mitigação

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Custo de IA por aluno corroer margem | Média | Alto | Cotas por plano, cache agressivo, roteamento de modelos (doc 03 §8) |
| Fundador solo como gargalo | Alta | Alto | Documentação AI-ready (este pacote), desenvolvimento assistido por IA, escopo de MVP disciplinado |
| Isolamento de dados falhar (vazamento entre tenants) | Baixa | Crítico | RLS no PostgreSQL + testes automatizados de isolamento em CI (doc 02 §5) |
| Nicho igrejas ter baixa disposição a pagar | Média | Médio | Preço de entrada baixo, plano Semente, caso IBC como prova de ROI |
| Dependência de um único provedor de LLM | Média | Médio | Camada de abstração de provider (doc 03 §7) |
| Entrada antecipada dispersar foco (3 segmentos, 1 fundador) | Alta | Alto | Mesmo produto para todos os segmentos; só templates e mensagem mudam; Fase 2 inicia apenas após Release 1.0 estável |

## 9-A. Fomento e editais (captação não diluitiva)

A XR Educação é candidata forte a fomento público: base tecnológica com IA, impacto social mensurável (educação), produto já em produção (raro entre proponentes) e sede em MS — estado com ecossistema de fomento ativo e menos concorrido que o eixo SP/Sul. Estratégia: **subvenção não reembolsável primeiro** (não dilui, não endivida), aceleração equity-free em paralelo, crédito subsidiado só com receita recorrente estabelecida.

### 9-A.1 Situação e calendário (atualizado em jul/2026)

| Programa | Status | Valor | Ação |
|---|---|---|---|
| **Centelha 3 MS (Fundect)** | Inscrições **encerradas em 25/05/2026** (janela perdida neste ciclo) | Até R$ 89,6 mil subvenção + até R$ 50 mil bolsas CNPq, 47 propostas | Acompanhar resultado e eventuais vagas remanescentes/repescagem; preparar proposta-modelo desde já para o Centelha 4 (ciclos ~anuais); participar dos eventos Fundect para networking com o ecossistema local |
| **FINEP Startup** | Ciclos recorrentes | Até ~R$ 1,5 mi (investimento) | Exige faturamento mínimo (~R$ 360 mil/12m) e LTDA/SA ≥ 6 meses — alvo para 2027, após tração da Fase 2 |
| **Sebrae Startups / Capital Empreendedor** | Fluxos e ciclos ao longo do ano | Aceleração + conexão com investimento | Inscrever assim que o CNPJ da XR Educação existir; Sebrae MS é parceiro do ecossistema local (mesmo circuito do Centelha) |
| **InovAtiva Brasil** | 2 ciclos/ano, equity-free e gratuito | Aceleração + selo/vitrine | Inscrever no próximo ciclo — baixo custo de participação, alto valor de sinal para editais futuros |
| **Tecnova / FINEP-FAPs (via Fundect)** | Editais estaduais por cronograma | Subvenção para MPEs inovadoras | Monitorar página da Fundect trimestralmente; é a evolução natural pós-Centelha |
| **BNDES Garagem (impacto)** | Ciclos até 2028 | Aceleração + prêmios | Enquadramento por impacto educacional/social — candidatura na Fase 2 |
| **Programa Mais Inovação (FINEP/BNDES)** | Chamadas contínuas até 2026+ | Crédito subsidiado + subvenção (R$ 60 bi mobilizados) | Radar para 2027+, quando crédito fizer sentido |

### 9-A.2 Pré-requisitos para submissão (fazer agora)

1. **Regularizar e enquadrar o veículo societário.** A XR Educação opera sob a XR Solutions (razão social Camila C. Hamdan LTDA - ME, CNPJ 45.310.753/0001-31, constituída em 16/02/2022, sede em Curitiba/PR, CNAE de desenvolvimento e licenciamento de software — aderente ao SaaS). Três restrições mapeadas em jul/2026:
   - **Situação cadastral INAPTA (bloqueio nº 1):** empresa inapta não emite NF regularmente, não contrata com o poder público e não recebe fomento. Regularização com contador é pré-requisito para QUALQUER caminho — inclusive para faturar a XR Educação. Prioridade imediata.
   - **Constituída há >12 meses:** não se enquadra como "empresa nascente" em programas tipo Centelha. Nesses, submeter como **pessoa física** (permitido) ou constituir LTDA nova específica quando houver edital-alvo com data.
   - **Sede em Curitiba/PR, operação em Campo Grande/MS:** editais estaduais (Centelha MS, Fundect, Tecnova-MS) exigem CNPJ sediado em MS — o Centelha MS, por exemplo, exige constituição da empresa em MS pelos selecionados. Decidir com o contador: transferir a sede da XR Solutions para MS, abrir filial, ou reservar a LTDA nova (item anterior) já sediada em MS. Alternativa: mirar também editais do PR/nacionais (FINEP, Sebrae, InovAtiva), onde a sede atual não é impedimento.
   - Para FINEP Startup (exige empresa ≥6 meses com faturamento R$360 mil+/12m), a XR Solutions regularizada é o veículo natural quando houver tração.
2. **Kit de submissão permanente**, derivado deste pacote de docs: pitch deck (10 slides), vídeo de 3 min, one-pager, planilha de projeções 3 anos, prova de tração (métricas IBC Ensino: alunos, conclusão, engajamento). Manter atualizado trimestralmente — a maior vantagem competitiva em edital é ter material pronto quando a janela abre.
3. **Métricas que editais pontuam:** inovação (tutor + learner model — enquadrar como "IA aplicada à educação", tema prioritário em chamadas atuais), impacto social (educação acessível, interior do Brasil), potencial de mercado (§5.1), equipe (histórico de execução: plataforma em produção). Bancas valorizam ESG/impacto — o caso IBC (educação comunitária gratuita/acessível) é ativo real aqui, não cosmético.
4. **Responsável e cadência:** revisar oportunidades na primeira semana de cada trimestre (fontes: fundect.ms.gov.br, finep.gov.br, sebraestartups.com.br, programacentelha.com.br). Registrar cada submissão e feedback em docs/FOMENTO.md.

## 10. Métricas norte (North Star + guardrails)

- **North Star:** minutos semanais de aprendizagem ativa por aluno (interação com conteúdo + tutor + revisões, não tempo de tela passivo).
- Retenção de tenant (churn mensal < 3%), conclusão de trilhas (> 40% vs. ~10% típico de EAD), NPS de instrutor, custo de IA por aluno ativo (< 8% do ticket).

## 11. Mapa dos documentos

| Doc | Conteúdo | Público |
|---|---|---|
| 00-VISAO.md (este) | Estratégia, mercado, modelo de negócio | Fundador, investidores, parceiros |
| 01-PRD.md | Requisitos de produto, personas, histórias, escopo de MVP | Produto + desenvolvimento |
| 02-ARQUITETURA.md | Arquitetura de software, multi-tenancy, dados, segurança, infra | Desenvolvimento (IA e humanos) |
| 03-ARQUITETURA-IA.md | Tutor de IA, learner model, ciência cognitiva, prompts, custos | Desenvolvimento + pedagogia |
