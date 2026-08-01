# MELHORIAS-UI-ALUNO.md — Plano de refinamento pós-deploy
**Base:** análise do dashboard REAL em produção (print de 13/07/2026) + melhores práticas de UI/UX
**Status:** AGUARDANDO APROVAÇÃO DO FUNDADOR antes de enviar ao Claude Code
**Branch sugerida:** `feat/GAM-05-polish-dashboard`

---

## Contexto: o que o print de produção revelou

O dashboard está funcional e a estrutura dos 5 grupos está de pé. Mas a versão real expôs lacunas entre a especificação e a execução — algumas de hierarquia visual, outras de consistência, e uma de vazamento de linguagem interna para o usuário final. Este plano organiza tudo em 3 níveis de prioridade para aprovação em bloco ou por item.

**Nota de alinhamento spec vs. realidade:** o produto em produção usa **tema claro**, enquanto o UX_ALUNO_SAAS especificava fundo escuro como identidade. Decisão necessária (item D1 abaixo) — recomendo **oficializar o tema claro** como padrão do aluno e atualizar a spec, em vez de reescrever a UI: o claro está funcionando, é mais seguro para o público-alvo (idade variada, uso diurno também) e evita retrabalho.

---

## P0 — Correções (as duas já identificadas + as críticas do print)

### P0.1 Largura do container em telas largas
- Sintoma: faixa morta à direita em desktop.
- Correção: `max-width` do conteúdo para ~1360px em viewports ≥1440px, mantendo grid 8/4; gutter lateral mínimo 24px. Nada de esticar cards individualmente.
- Aceite: em 1920px de largura, o conteúdo ocupa ≥70% do viewport sem quebrar a proporção dos grupos.

### P0.2 Card "Sua Pontuação" como protagonista visual
- Fundo com `--brand-gradient` (texto em `--brand-on-primary` calculado), sombra `--shadow-elevated`, e o número de pontos como o maior elemento tipográfico da tela (sugestão: 48-56px vs. os ~36px atuais).
- Nível com nome ("Estudioso") mantido — é excelente; dar-lhe um chip próprio.
- Aceite: teste de squint (apertar os olhos): o card de pontuação é o primeiro elemento percebido depois da saudação.

### P0.3 Streak duplicado → um streak forte
- Hoje "🔥 1 dia" aparece 2× (saudação + pontuação). Consolidar: a chama SVG animada (spec §4.2 — estados ativa/em risco/quebrada, `prefers-reduced-motion`) vive DENTRO do card de pontuação; na saudação fica apenas a frase de contexto dinâmica quando o streak está em risco ("Seu streak vence hoje — 5 min de revisão o mantém").
- Aceite: um único indicador de streak visível por vez; badge de texto genérico substituído pela chama SVG.

### P0.4 Vazamento de linguagem interna (CRÍTICO de copy)
- O card "Revisão do dia" mostra ao aluno: "Chega na Release 1.0 — vai te ajudar a fixar...". **"Release 1.0" é jargão interno** — o aluno não sabe nem deve saber o que é isso.
- Correção: copy voltada ao usuário: "**Em breve:** revisões diárias personalizadas para fixar o que você aprendeu." — ou simplesmente ocultar o slot até a feature existir (recomendado: ocultar; anunciar features futuras cria ansiedade de espera sem data).
- Varredura: grep por "Release", "sprint", "feature flag", "MVP" em qualquer string visível ao aluno.
- Aceite: zero terminologia interna em qualquer texto renderizado ao usuário final.

### P0.5 Gradiente fora da paleta no CTA
- O botão "Ver catálogo" usa gradiente teal→roxo. Roxo não pertence ao tema do IBC nem é derivado de `--brand-primary` — provavelmente um valor hardcoded que escapou do lint (verificar; se o lint não pegou, o lint tem um buraco).
- Correção: usar `--brand-gradient` (derivado por rotação de hue limitada, spec §2.1) e investigar por que o lint de hex não capturou.
- Aceite: nenhum gradiente/cor fora dos tokens; relatório do que deixou o lint passar isso.

## P1 — Melhorias de hierarquia e affordance

### P1.1 Estados vazios com ação, não beco
- "Suas conquistas aparecem aqui." é passivo. Padrão da casa (spec §4.4: vazio é convite): "Complete sua primeira lição para ganhar a conquista **Primeiro Passo**" + mini-ícone da conquista bloqueada (silhueta). Dá alvo concreto.
- Mesmo tratamento para "Nenhum curso iniciado" na sidebar (hoje tem link "Explorar catálogo →" — bom, manter e padronizar o tom nos demais vazios).

### P1.2 Redundância de metas
- "+90 pontos para o próximo nível" aparece na saudação E em Próximas Metas. Uma informação, um lugar: fica em Próximas Metas (é meta); a saudação usa a frase de contexto dinâmica da spec (prioridade: streak em risco > revisão pendente > progresso de curso).

### P1.3 Sidebar: hierarquia e truncamento
- "Fundamentos da..." truncado sem tooltip — adicionar `title`/tooltip e permitir 2 linhas para nomes de trilha.
- Barra de progresso da trilha (0%) é quase invisível — engrossar para 6px e usar `--brand-primary`; mostrar % à direita já existe, manter.
- Agrupar visualmente: itens de navegação (Meu Painel...Catálogo) vs. conteúdo do aluno (Minhas Trilhas, Meus Cursos) com espaçamento e label de seção mais distintos (as labels existem — reforçar o ritmo com mais respiro, 8pt grid).

### P1.4 Ícones do header sem rótulo
- Relógio, olho e sino no topo não comunicam função. Adicionar tooltip em hover/focus e `aria-label`; em mobile, garantir que a função é descoberta (se "olho" = focus mode do Sprint 6.2, considerar rótulo curto ao lado em desktop).

### P1.5 Tipografia e ritmo
- Estabelecer escala explícita (ex: 14/16/20/28/40/56) e aplicar: títulos de grupo hoje competem com conteúdo. Espaçamento vertical entre grupos consistente (32px) — no print, o respiro entre "Continue" e o fim do card hero varia.

### P1.6 Momento de celebração (micro-interação de maior ROI emocional)
- Ao concluir lição/curso/conquista: animação breve de celebração no card correspondente (escala + partículas discretas em `--brand-primary`, 800ms, 1×, desativada em `prefers-reduced-motion`). É o par emocional do sistema de pontos — pontos sem momento de celebração são contabilidade.
- Aceite: disparo apenas em evento real de conclusão; nunca em loop; testável via E2E.

## P2 — Polimento (fila após P0+P1)

- **P2.1** Skeletons por grupo na carga (a spec pede; confirmar se o deploy atual mostra tela branca por instantes).
- **P2.2** Transição suave entre estados vazio→conteúdo (fade 200ms).
- **P2.3** Sidebar colapsável em desktop (ícones-só) para dar ainda mais área útil — resolve parte do P0.1 em telas médias.
- **P2.4** Avatar com iniciais coloridas derivadas do nome (hash → hue dentro da paleta) em vez de círculo genérico.
- **P2.5** Revisitar débito de Lighthouse performance (~62-64) — as correções P0/P1 tocam CSS/JS; medir de novo após; se continuar <85, abrir trabalho dedicado (lazy-load de imagens dos cards, fontes com `font-display: swap`, JS não crítico deferido).

## Decisões que preciso do fundador (aprovar/ajustar)

| ID | Decisão | Recomendação |
|---|---|---|
| D1 | Tema claro vs. escuro como padrão do aluno | Oficializar CLARO; atualizar UX_ALUNO_SAAS §2 |
| D2 | Slot "Revisão do dia": ocultar até a Release 1.0 ou manter com copy "Em breve" | OCULTAR |
| D3 | Escopo desta rodada | P0 completo + P1 completo; P2 fica na fila |
| D4 | Deploy: direto após revisão ou represar com próxima leva | Direto (mudanças visuais de baixo risco, sem migração) |

## Ordem de execução proposta (1 PR por bloco)

1. P0.4 + P0.5 (copy interna + cor fora de token — rápidos e críticos)
2. P0.1 + P0.2 + P0.3 (layout e hierarquia do herói)
3. P1.1 → P1.6
4. Medição Lighthouse pós-mudanças (informa P2.5)

Cada PR: testes atualizados, screenshots dos 2 tenants (ibc + demo), Sonnet-escreve/Fable-revisa, sem merge sem aprovação.
