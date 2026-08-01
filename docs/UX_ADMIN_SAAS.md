# UX_ADMIN_SAAS.md — Painel do Administrador (tenant)
**Produto:** XR Educação · **Versão:** 1.0
**Persona principal:** P3 (Márcia — admin do tenant: matrículas, turmas, relatórios) e sobreposição com P2 (instrutor)
**Requisitos relacionados:** TEN-03/04/05, AUTH-02/04, ANL-01–04, ONB-01–03
**Branch sugerida:** `feat/ADM-01-painel-admin` (separada do dashboard do aluno)

---

## 0. Diagnóstico (por que o admin atual não é ponto forte)

O painel admin herdado do IBC Ensino foi construído para UM administrador técnico (o fundador). No SaaS, o admin típico é a Márcia: secretária/coordenadora, não técnica, no desktop, com 30 minutos por dia para a plataforma. A pesquisa de mercado converge em um ponto: o dashboard admin é a primeira tela que o gestor vê ao logar e é onde ele decide o que precisa de atenção hoje — quando isso falha, a plataforma é usada uma vez e silenciosamente abandonada, mesmo com assinatura renovada. O painel admin não é relatório; é **cockpit de decisão**.

Princípios extraídos da pesquisa e adotados aqui:
1. **Informação certa, hierarquia certa, ruído mínimo** — widgets decorativos que "não dizem nada útil" são o erro nº 1 dos LMS.
2. **Escopo por papel** — admin vê tudo do tenant; instrutor vê só suas turmas; ninguém vê dado que não precisa.
3. **Mínimo de cliques para completar ações administrativas** — navegação é o fator nº 1 de UX em LMS.
4. **Visão de desempenho por curso** (conclusão, nota média, ponto de abandono) — sem ela, o gestor "não faz ideia de qual curso as pessoas abandonam no módulo 2".
5. **Tempo real, não exportação** — cada pergunta que exige exportar CSV para responder é uma falha de design.

## 1. Arquitetura de informação (nova)

Navegação lateral fixa (desktop-first — admin usa desktop, ao contrário do aluno), máximo 7 itens:

```
▣ Hoje            ← home: fila de atenção + pulso do tenant
▤ Pessoas         ← alunos, instrutores, convites, importação
▥ Cursos          ← catálogo, desempenho por curso, editor
▦ Turmas          ← agrupamentos, matrículas em massa
▧ Relatórios      ← análises profundas + exportações
▨ Comunicação     ← avisos, convites pendentes, mensagens
⚙ Configurações   ← marca, tema, plano/billing, equipe admin
```

Regra de profundidade: **qualquer ação administrativa frequente em ≤ 2 cliques a partir de "Hoje"**. Ações raras (exportar LGPD, alterar plano) podem ficar a 3.

## 2. Tela "Hoje" — o cockpit (a maior mudança)

Substitui o dashboard atual de "cards de contagem" (total de alunos, total de cursos — métricas de vaidade que não pedem ação) por três zonas em ordem de prioridade visual (topo-esquerda primeiro, seguindo o padrão de leitura):

### Zona 1 — Fila de Atenção (o coração do painel)
Lista priorizada do que **precisa de decisão hoje**, cada item com ação inline:
- "5 alunos em risco de evasão" → [Ver alunos] → intervenção em 1 clique (mensagem-modelo)
- "Curso 'Finanças' tem 40% de abandono no Módulo 2" → [Ver ponto de abandono]
- "12 convites expiram em 3 dias" → [Reenviar todos]
- "3 atividades abertas aguardando correção há >5 dias" → [Corrigir agora]
- (Release 1.0+) "Dúvida recorrente detectada pelo tutor em 'Hermenêutica'" → [Ver resumo]

Estado vazio da fila = celebração explícita: "Tudo em dia. Nenhuma ação pendente." — o vazio comunica sucesso, não ausência de dados. Fila alimentada pelos eventos de domínio já arquitetados (`aluno.inativo_7d`, `tutor.interacao`, ANL-03).

### Zona 2 — Pulso da semana (4 números, não 12)
Alunos ativos (7d) · Conclusões da semana · Taxa de engajamento (% ativos/matriculados) · Minutos de aprendizagem — cada um com微 sparkline de 8 semanas e variação vs. semana anterior. Clicar em qualquer número abre o relatório correspondente já filtrado. Proibido: métricas acumuladas sem contexto ("total de pontos distribuídos: 45.231").

### Zona 3 — Atividade recente
Feed compacto (últimas 24h): matrículas, conclusões, certificados emitidos. Máximo 8 itens + "ver tudo".

## 3. Pessoas — onde a Márcia passa o tempo

- **Busca instantânea global** (nome/e-mail, resultado <300ms) no topo fixo — a ação nº 1 de qualquer admin é "achar o aluno X".
- **Perfil do aluno em painel lateral** (slide-over), não página nova: progresso, streak, últimos acessos, domínio por conceito (Release 1.0), botões [Mensagem] [Resetar senha] [Trocar turma] sem sair da lista.
- **Importação CSV com preview e correção inline** (AUTH-02): mostra as 5 primeiras linhas mapeadas ANTES de importar; erros aparecem por linha com correção na própria tela, não em relatório para baixar.
- **Convites com estado visível**: pendente / aceito / expirado, reenvio em massa, link/QR da turma sempre à mão.
- **Ações em massa seguras**: seleção múltipla → barra de ações contextual; ações destrutivas exigem digitar a palavra "confirmar" (padrão já usado no fix de `bulk_action_users`).

## 4. Cursos — desempenho, não só catálogo

Cada curso ganha uma aba **Desempenho** (a lacuna mais citada na pesquisa):
- Funil de progresso por módulo (onde os alunos param) — barra horizontal por módulo com % que chegou e % que concluiu; o "ponto de abandono" fica visualmente óbvio.
- Taxa de conclusão, nota média por quiz, tempo médio por lição.
- (Release 1.0) Heatmap de domínio por conceito da turma (ANL-01) e dúvidas mais frequentes no tutor.
- CTA de melhoria: "O Módulo 2 concentra 40% do abandono — revisar conteúdo?" com link direto ao editor naquele módulo.

## 5. Sistema visual do admin (UI)

- **Mesmos tokens do design system** (`--brand-*` etc.), mas **modo claro por padrão** no admin: trabalho administrativo diurno de leitura densa de dados favorece fundo claro; o dark fica como preferência do usuário. O aluno mantém o dark (identidade da experiência de estudo). Isso exige adicionar os tokens de superfície clara ao `tokens.css` (`--bg-base-light` etc.) — única extensão de tokens necessária.
- **Densidade adaptável**: tabelas com toggle confortável/compacto (admins com 500 alunos precisam de densidade; admins com 40 preferem respiro).
- **Tabelas de verdade**: ordenação por coluna, filtros persistentes por sessão, colunas configuráveis, paginação server-side desde o início (a lição do `bulk_action` já mostrou o custo de listas ingênuas).
- **Zero emojis nativos** (regra da plataforma), ícones Lucide, gráficos com a paleta derivada do tema do tenant — o admin também "sente" a marca dele.
- **Skeleton + progressive render** por zona (mesma regra do dashboard do aluno §4.4).

## 6. Microcopy e redução de medo

Admin não técnico tem medo de "quebrar algo". Três regras:
1. Toda ação destrutiva diz **o que acontece e o que NÃO acontece**: "Remover a matrícula apaga o progresso desta aluna neste curso. A conta dela e os certificados já emitidos permanecem."
2. **Undo em vez de confirmação** onde for seguro (desfazer em 10s no toast) — confirmações em excesso treinam o clique automático.
3. Linguagem do domínio da pessoa, não do sistema: "Turma", "Matrícula", "Convite" — nunca "registro", "entidade", "sincronizar".

## 7. Onboarding do admin (primeira sessão)

Checklist de ativação persistente (ONB-03) no topo da tela "Hoje" até completar: (1) personalize sua marca → (2) crie ou importe o primeiro curso → (3) convide 10 alunos → (4) publique. Cada item leva direto à tela da ação com tour de 1 balão (não tour de 12 passos que todo mundo pula). Meta ONB-01 mantida: primeiro curso publicado em <1h.

## 8. Priorização de implementação

| Prioridade | Entrega | Justificativa |
|---|---|---|
| P0 | Tela "Hoje" (3 zonas) + navegação nova | É o que o cliente novo (Alessio, produtor) vê na demo; maior impacto por esforço |
| P0 | Busca global de pessoas + perfil slide-over | Ação mais frequente do admin real |
| P1 | Desempenho por curso (funil de abandono) | Diferencial vs. LMS genérico; conversa direto com a tese "vendemos aprendizagem" |
| P1 | Importação CSV com preview | Remove a maior fricção do onboarding de igreja/empresa |
| P2 | Densidade adaptável, undo pattern, modo claro/escuro | Polimento que consolida |
| Release 1.0 | Fila de atenção com sinais de IA (risco de evasão, dúvidas recorrentes) | Depende do módulo `learning/` |

## 9. Métricas de sucesso do redesign

- Tempo até completar as 3 tarefas mais comuns (achar aluno, matricular turma, ver desempenho de curso) — medir antes/depois, alvo −50%.
- % de sessões admin que interagem com a Fila de Atenção (alvo >60%).
- Ativação de tenant novo (ONB-03 completo) em <7 dias (alvo >70%).
- NPS do admin por tenant (pergunta única trimestral dentro do painel).
