# MELHORIAS-UI-ALUNO.md — Plano de refinamento do dashboard do aluno (GAM-05)

**Branch:** `feat/GAM-05-polish-dashboard` (a partir de `claude/zen-hopper-SeRac`, já com GAM-04 mergeado)
**Status:** aprovado — execução em 3 PRs, cada um com testes, screenshots (tenants `ibc` e `demo`) e revisão Fable 5 antes do commit final.

## Decisões tomadas

- **D1 — Tema claro é o padrão oficial do aluno.** `docs/UX_ALUNO_SAAS.md` §2 é atualizado para refletir isso (era escuro/navy por padrão).
- **D2 — Slot "Revisão do dia" fica oculto** até a feature (LRN-02) existir de verdade — sem placeholder, sem menção visível ao usuário.
- **D3 — Escopo desta rodada:** P0 completo + P1 completo. P2 fica na fila (registrado em `docs/DEBITOS.md` quando algo parecer mais urgente do que aparentava).
- **D4 — Deploy direto após revisão final do solicitante** (sem etapa de staging intermediária) — mas **nenhum merge em `claude/zen-hopper-SeRac` sem aprovação explícita**.

## PR 1 — Críticos de copy e token (P0.4 + P0.5)

1. Ocultar completamente o slot "Revisão do dia" (feature flag desligada → não renderiza nada).
2. Varredura de linguagem interna vazando pra UI (`Release`, `Sprint`, `MVP`, `flag`, etc.) em toda string visível ao usuário final.
3. Corrigir o gradiente do botão "Ver catálogo" para usar `--brand-gradient` derivado do tema do tenant (não hex hardcoded teal→roxo); investigar e corrigir o gap no lint de hex hardcoded que deixou passar.

## PR 2 — Layout e hierarquia do herói (P0.1 + P0.2 + P0.3)

1. Container com `max-width` ~1360px em viewports ≥1440px, grid 8/4 preservada, gutter mínimo 24px.
2. Card "Sua Pontuação" redesenhado: fundo `--brand-gradient`, texto `--brand-on-primary`, pontos como maior texto da tela, nível em chip próprio, contraste AA validado.
3. Streak consolidado dentro do card de pontuação (SVG com 3 estados, `prefers-reduced-motion` respeitado); saudação simplificada (frase de contexto dinâmica, sem duplicar streak/pontos-para-o-próximo-nível).

## PR 3 — Affordance e polimento (P1.1 a P1.6)

1. Estados vazios com ação explícita e tom de convite consistente.
2. Sidebar: tooltip/truncamento de nome de trilha, barra de progresso mais grossa, separação visual entre navegação e conteúdo.
3. Ícones do header com tooltip + `aria-label`.
4. Escala tipográfica explícita em tokens, espaçamento vertical padronizado entre grupos.
5. Micro-celebração ao concluir lição/curso/conquista (uma única execução por evento, desativada em `prefers-reduced-motion`, coberta por E2E).

## Pós-PRs

- Lighthouse re-medido nas mesmas 2 páginas do relatório anterior (login + dashboard autenticado) — reportado, não otimizado além do que os PRs já entregam.
- `docs/UX_ALUNO_SAAS.md` §2 atualizado para tema claro.
- Suíte completa + lint + audit + resumo consolidado antes de qualquer solicitação de merge.
