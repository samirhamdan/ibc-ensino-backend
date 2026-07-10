# UX_ALUNO_SAAS.md — Dashboard do Aluno preparado para Multi-tenant
**Produto:** XR Educação · **Versão:** 2.0 (substitui UX_ALUNO.md single-tenant)
**Escopo:** dashboard do aluno + componentes compartilhados + sistema de theming por tenant
**Requisitos cobertos:** GAM-02, GAM-03, GAM-04, LRN-02, LRN-03, TUT-01 (slot), TEN-03
**Branch:** `feat/GAM-04-dashboard-saas` (separada da release/0.9-tenancy)

---

## 1. Princípio central: um dashboard, N identidades

O layout, a hierarquia e o comportamento são **fixos da plataforma** (é o que garante qualidade UX para todo tenant, incluindo o que não tem designer). A **identidade visual é do tenant** (cor, logo, nome). A fronteira exata entre os dois é a decisão mais importante deste documento:

| Camada | Dono | Exemplos |
|---|---|---|
| Estrutura e hierarquia | Plataforma (fixo) | 5 grupos verticais, ordem, grid, espaçamentos |
| Comportamento | Plataforma (fixo) | Micro-interações, estados, navegação, acessibilidade |
| Tipografia | Plataforma (fixo) | Escala tipográfica única (evita tenant quebrar legibilidade) |
| Identidade | Tenant (configurável) | Cor primária, logo, nome exibido, saudação personalizada |
| Derivados de cor | Plataforma (calculado) | Hover, gradientes, estados — derivados da cor primária via algoritmo |

**Regra de ouro:** o tenant escolhe UMA cor primária e um logo. Todo o resto é derivado ou fixo. Isso impede o "efeito MySpace" (tenants criando telas ilegíveis) e mantém o custo de suporte próximo de zero.

## 2. Design tokens (arquitetura de theming)

### 2.1 Tokens em CSS Custom Properties

Toda cor no CSS do dashboard referencia tokens — **nenhum hex hardcoded em componente**:

```css
:root {
  /* IDENTIDADE (injetados por tenant via tema_json) */
  --brand-primary: #008ea8;        /* IBC default */
  --brand-logo-url: url(...);
  
  /* DERIVADOS (calculados no build do tema, não pelo tenant) */
  --brand-primary-hover: ...;      /* primary escurecido 8% */
  --brand-primary-subtle: ...;     /* primary a 10% opacidade (fundos) */
  --brand-gradient: ...;           /* primary → primary rotacionado 20° no hue */
  --brand-on-primary: ...;         /* branco ou preto por contraste calculado */
  
  /* FIXOS DA PLATAFORMA (iguais para todos os tenants) */
  --bg-base: #0a0f1e;              /* navy escuro — base da plataforma */
  --bg-surface: #111827;
  --bg-elevated: #1a2332;
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --success: #10b981;  --warning: #f59e0b;  --danger: #ef4444;
  --streak-flame: #f97316;         /* streak é identidade da PLATAFORMA */
  --radius-card: 12px;  --radius-button: 8px;
  --shadow-card: 0 4px 12px rgb(0 0 0 / 0.3);
  --shadow-elevated: 0 8px 24px rgb(0 0 0 / 0.4);
}
```

### 2.2 Pipeline do tema

1. `tenants.tema_json` guarda apenas: `{ "primary": "#008ea8", "logo": "...", "nome_exibido": "IBC Ensino" }`.
2. Endpoint `GET /api/theme` (cacheado por tenant, TTL 5 min) calcula os derivados no servidor (Python: escurecer, opacidade, contraste WCAG) e retorna o bloco de custom properties.
3. SPA injeta em `<style id="tenant-theme">` no boot, antes do primeiro paint (evita flash de tema errado).
4. **Validação no painel admin:** ao escolher a cor, o sistema calcula contraste contra `--bg-base` e `--text-primary`; cores reprovadas (contraste < 4.5:1 em texto) recebem ajuste automático de luminosidade com aviso ao admin. O tenant nunca consegue publicar um tema ilegível.

### 2.3 O que o tenant NUNCA configura

Fundo escuro (identidade da plataforma), tipografia, espaçamentos, ícones (Lucide, `stroke-width: 1.75` em toda a plataforma), cor do streak (laranja-fogo é assinatura XR Educação, igual em todo tenant — vira reconhecível), emojis nativos (proibidos em toda a plataforma, sem exceção).

## 3. Estrutura do dashboard — 5 grupos verticais (preservados + slots SaaS)

A estrutura validada no IBC é mantida; cada grupo ganha os slots que a Release 1.0 vai preencher. Layout mobile-first: coluna única em <768px, grid 2 colunas (8/4) em desktop com grupos 1–2 à esquerda e 3–4 empilhados à direita, grupo 5 full-width abaixo.

### Grupo 1 — SAUDAÇÃO
- Logo do tenant (esquerda) + avatar/menu (direita).
- "Boa noite, Ana" (saudação por horário) + frase de contexto dinâmica: prioridade (a) streak em risco ("Seu streak de 12 dias vence hoje"), (b) revisões pendentes ("5 revisões esperando por você"), (c) progresso ("Você está a 2 lições de concluir o Módulo 3").
- **Slot SaaS:** contador de streak compacto (chama + número) sempre visível aqui, clicável → modal de detalhe do streak (GAM-02).

### Grupo 2 — CONTINUE SEUS ESTUDOS
- Card hero da lição em andamento: thumbnail/gradiente, título, curso, barra de progresso, botão "Continuar" (primário, `--brand-primary`).
- Cards secundários (até 2) de outros cursos em andamento — formato Netflix compacto.
- **Slot SaaS (Release 1.0):** botão "Tirar dúvida com o tutor" no card hero — abre o tutor já no contexto da lição em andamento (TUT-01). Até a 1.0, o slot renderiza nulo (feature flag `tutor_enabled` por tenant).

### Grupo 3 — SUA PONTUAÇÃO
- Linha 1: pontos totais + posição/nível.
- Linha 2: streak expandido — chama animada (CSS, respeita `prefers-reduced-motion`), dias atuais, recorde, marcos (7/30/100 dias) com bônus (GAM-02, dados agora server-side).
- Linha 3: últimas 3 conquistas (badges) com estado "nova" (bounce sutil, 1×, GAM-03).

### Grupo 4 — PRÓXIMAS METAS
- **"Revisão do dia" é o item nº 1 do grupo** (LRN-02): card com contagem de itens (ex.: "7 conceitos · ~5 min"), CTA "Revisar agora". Completar a revisão mantém o streak — a conexão revisão↔streak é o motor de hábito do produto e deve ser visível ("Revise hoje e mantenha seus 12 dias").
- Metas de curso: próxima lição, quiz pendente, certificado a 1 módulo de distância.
- Estado vazio: "Nenhuma meta pendente — explore as recomendações abaixo" (nunca grupo em branco).

### Grupo 5 — RECOMENDAÇÕES
- Carrossel horizontal de cards Netflix (GAM-03): thumbnail ou gradiente derivado (`--brand-gradient` com variação por hash do título — cursos sem imagem nunca ficam cinza).
- **Slot SaaS (Release 1.0):** recomendações passam a vir do learner model (LRN-03) com rótulo do motivo: "Reforce: Hermenêutica" / "Desafio: você domina este tema" / "Novo no catálogo". Até lá, ordenação por popularidade no tenant.

### Novo elemento transversal — Mapa de Domínio (Release 1.0, atrás de flag)
Entrada no menu do avatar + card compacto opcional no Grupo 3: radar/lista de conceitos com barra de domínio 0–100%. No dashboard aparece só o resumo (3 conceitos mais fortes / 3 a reforçar); página própria para o detalhe. Não entra como 6º grupo — a estrutura de 5 é fixa.

## 4. Componentes (especificação para implementação)

### 4.1 Card Netflix (GAM-03 — Opções F+A travadas)
- Proporção 16:9, `--radius-card`, thumbnail com overlay gradiente inferior para legibilidade do título.
- Hover (desktop): `transform: scale(1.02)` + `--shadow-elevated`, transição 180ms ease-out. Touch: sem hover, feedback por `:active` (scale 0.98).
- Conteúdo: título (máx. 2 linhas, ellipsis), curso/categoria (eyebrow em `--text-muted`), barra de progresso fina (2px) na base quando em andamento.
- Badge "Novo" (`--brand-primary`) com bounce de entrada 1× (400ms), nunca em loop.

### 4.2 Chama de streak (GAM-02)
- SVG próprio (não emoji), cor fixa `--streak-flame`, 3 estados: ativa (flicker sutil CSS 3s loop), em risco hoje (pulso de opacidade + tooltip), quebrada (cinza `--text-muted`, sem animação).
- `prefers-reduced-motion: reduce` → todas as animações viram estados estáticos.

### 4.3 Botões e CTAs
- Primário: fundo `--brand-primary`, texto `--brand-on-primary` (calculado). Um único CTA primário visível por grupo — hierarquia clara.
- Rótulos por ação, não por sistema: "Continuar lição", "Revisar agora", "Tirar dúvida" (nunca "Submeter", "Acessar módulo").

### 4.4 Estados obrigatórios de cada grupo
Todo grupo implementa 4 estados: **loading** (skeleton na estrutura final, sem spinner global), **vazio** (mensagem + ação — vazio é convite, não beco), **erro** (o que houve + "Tentar de novo", sem tom de desculpa), **conteúdo**. O dashboard renderiza progressivamente por grupo (endpoint por grupo ou payload único seccionado — decisão de implementação, mas o usuário nunca vê tela branca).

## 5. Acessibilidade e qualidade (gate de aceite)

- Contraste AA (4.5:1 texto, 3:1 UI) garantido pelo pipeline de tema (§2.2.4) — testado com as cores reais dos tenants piloto.
- Navegação completa por teclado; foco visível (outline 2px `--brand-primary`); carrossel operável por setas.
- Touch targets ≥ 44px; viewport mínimo 360px sem scroll horizontal.
- `aria-label` em ícones de ação; contadores (streak, pontos) com `aria-live="polite"` quando atualizam.
- Lighthouse: performance ≥ 85 mobile, acessibilidade ≥ 95.

## 6. Plano de implementação (Claude Code — 4 etapas, 1 PR cada)

**Etapa 1 — Fundação de tema (TEN-03).** Tokens CSS, endpoint `/api/theme` com derivação e validação de contraste, injeção no boot, migração de todo hex hardcoded existente para tokens. *Aceite: IBC renderiza idêntico ao atual via tokens; tenant demo com outra cor primária renderiza correto sem deploy.*

**Etapa 2 — Estrutura dos 5 grupos.** Grid responsivo, os 5 grupos com estados (loading/vazio/erro/conteúdo), dados dos grupos 1, 2 e 4 (metas de curso) ligados às APIs existentes. *Aceite: jornada "abrir dashboard → continuar lição" funcional nos 2 tenants de staging.*

**Etapa 3 — Gamificação server-side.** Streaks migrados de localStorage para API (GAM-02: modelo já existe da Fase 3 — ligar UI), chama SVG com 3 estados, conquistas com badge "nova", pontos no Grupo 3. *Aceite: streak sobrevive a troca de dispositivo; marcos disparam bônus.*

**Etapa 4 — Cards Netflix + recomendações v0.** Carrossel do Grupo 5, cards F+A com hover/touch, gradientes derivados para cursos sem thumbnail, ordenação por popularidade (slot pronto para LRN-03). *Aceite: Lighthouse dentro do gate; `prefers-reduced-motion` respeitado.*

**Prompt-modelo por etapa:**
```
Leia docs/UX_ALUNO_SAAS.md (§2 e §6, Etapa N) e docs/02-ARQUITETURA.md §3.
Implemente a Etapa N na branch feat/GAM-04-dashboard-saas.
Critérios de aceite da etapa viram testes (unitários p/ derivação de tema;
E2E Playwright p/ jornadas). Nenhum hex hardcoded em componente novo —
lint customizado que falha se encontrar cor fora de tokens.css.
Screenshots dos 2 tenants de staging no PR.
```

## 7. O que fica explicitamente para a Release 1.0 (slots prontos, features desligadas)

Tutor no card hero (TUT-01), "Revisão do dia" com dados reais (LRN-02 — na 0.9 o card mostra estado vazio elegante), recomendações por learner model (LRN-03), mapa de domínio. Tudo atrás de feature flags por tenant — o dashboard novo entra em produção na 0.9 sem esperar a IA, e a 1.0 "liga" os slots sem retrabalho de layout.
