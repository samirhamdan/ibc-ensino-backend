# Pacote de Documentação — XR Educação (SaaS)
**Evolução multi-tenant do IBC Ensino com tutor de IA · Grupo XR Solutions (CNPJ 45.310.753/0001-31)**
Versão 1.0 · Julho/2026

## Documentos

| Arquivo | Conteúdo | Leia primeiro se você é... |
|---|---|---|
| `00-VISAO.md` | Estratégia, mercado, modelo de negócio, princípios | Fundador, parceiro, investidor |
| `01-PRD.md` | Requisitos funcionais (IDs estáveis), personas, jornadas, releases | Product/dev definindo o que construir |
| `02-ARQUITETURA.md` | Multi-tenancy (RLS), estrutura de código, dados, segurança, infra | Dev implementando qualquer feature |
| `03-ARQUITETURA-IA.md` | Tutor, learner model, revisão espaçada, RAG, guardrails, custos | Dev implementando o módulo `ai/` ou `learning/` |

## Como usar com desenvolvimento assistido por IA (Claude Code)

1. **Commite este pacote em `docs/`** no repositório (`ibc-ensino-backend`), ao lado de ROADMAP.md, SAAS_ROADMAP.md e IA_ROADMAP.md. Estes documentos **substituem** o SAAS_ROADMAP.md e o IA_ROADMAP.md como fonte de verdade (arquive os antigos em `docs/archive/` ou reconcilie divergências antes).
2. **Referencie IDs de requisito** em prompts, branches e commits: `feat(TEN-02): resolução de tenant por subdomínio`. Isso dá rastreabilidade requisito → código → teste.
3. **Prompt-padrão para agentes:** "Leia docs/02-ARQUITETURA.md §3 (regras para agentes) e o README do módulo antes de implementar. Implemente [ID do requisito] conforme docs/01-PRD.md, com critérios de aceite como testes."
4. **Ordem de implementação:** siga o roteiro da Release 0.9 (doc 02 §10) — tenancy antes de qualquer feature nova. A suíte de isolamento (doc 02 §5.4) é o primeiro entregável de teste.
5. **Mudanças de escopo** passam por atualização do documento correspondente no mesmo PR (docs e código evoluem juntos).

## Decisões pendentes (bloqueiam releases)

| Decisão | Bloqueia | Referência |
|---|---|---|
| ~~Nome comercial~~ RESOLVIDO: XR Educação | — (executar registro de domínio/marca) | PRD §8.1 |
| **Regularizar situação INAPTA da XR Solutions (bloqueia faturamento e fomento)** | Tudo que envolve receita/editais | Visão §9-A.2 |
| Veículo p/ editais estaduais: sede PR vs. MS + empresa >12m não é 'nascente' | Fomento §9-A da Visão | Visão §9-A.2 |
| Asaas vs. Stripe | Release 0.9 → 1.0 (billing) | PRD §8.2 / ADR-006 |
| Política de neutralidade doutrinária | Guardrails por tenant | PRD §8.3 / doc 03 §6 |
| Vida em Prática: template ou demo | Onboarding ONB-02 | PRD §8.4 |

## Estado de origem (para contexto de quem chega agora)

O IBC Ensino está em produção (Railway, ibc-ensino.up.railway.app): Python 3.12, Flask 3.0.3, SQLAlchemy 2.0.51, PostgreSQL, gunicorn, SPA vanilla. Sprints 6.1–6.3 entregues (perfis, conquistas, certificados, focus mode, timer, histórico, feed, editor). Design system teal `#008ea8`, zero emojis nativos, dashboard especificado em UX_ALUNO.md (cinco grupos verticais). Itens de roadmap travados: streaks Opção B e cards Netflix F+A — ambos incorporados ao PRD (GAM-02, GAM-03).
