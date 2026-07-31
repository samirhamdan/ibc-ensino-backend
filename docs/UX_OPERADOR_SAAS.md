# UX_OPERADOR_SAAS.md — Painel do Gestor da Plataforma (Operador)
**Produto:** XR Educação · **Versão:** 1.0
**Persona:** P4 — o fundador/operador da plataforma (hoje, Samir; amanhã, a equipe de operações da XR Solutions)
**Requisitos relacionados:** TEN-01/04/05, BIL-01/02/03, NFR-02/07/09, AUTH-04
**Papel de acesso:** `operador_plataforma` (nunca acessível a usuários de tenant)
**Branch sugerida:** `feat/OPS-01-painel-operador`

---

## 1. Levantamento do estado atual (diagnóstico honesto)

Hoje o "painel do operador" **não existe como produto** — a operação da plataforma é feita por:

| Tarefa | Como é feita hoje | Custo/risco |
|---|---|---|
| Criar/gerenciar tenant | SQL direto no console do Railway (`INSERT INTO tenants...` — foi assim que o tenant demo nasceu) | Erro humano em produção; sem auditoria; ninguém além do fundador consegue operar |
| Suspender tenant / mudar plano | Não há caminho — seria UPDATE manual | Idem |
| Ver saúde do sistema | Console do Railway (deployments, métricas cruas) + logs | Reativo; nenhuma visão de negócio |
| Custo de IA por tenant | Não existe (módulo `ai/` ainda na Release 1.0) | NFR-07 (<8% da receita) impossível de monitorar |
| Billing/inadimplência | Não existe (Asaas ainda não integrado) | BIL-02 bloqueado |
| Métricas de negócio (MRR, churn, ativação) | Não existem | Decisões no escuro; sem material para editais/investidores |

**Conclusão do levantamento:** o gargalo não é estético — é que a plataforma **não é operável por ninguém além do fundador com acesso root**. Isso é aceitável com 2 tenants; quebra no 5º; e é bloqueador absoluto para (a) férias do fundador, (b) primeiro contratado, (c) due diligence de edital/investidor. O painel do operador é o que transforma "projeto do Samir" em "empresa operável".

## 2. Jobs-to-be-done do operador (o que o painel precisa responder)

1. **"A plataforma está saudável agora?"** — em 5 segundos, sem abrir o Railway.
2. **"Como está o negócio este mês?"** — MRR, tenants ativos, churn, ativação, em 1 tela.
3. **"Este tenant está bem?"** — engajamento, consumo de IA, pagamento, num perfil único.
4. **"Preciso agir em algo?"** — inadimplência, cota de IA estourando, tenant inativo há 30 dias, erro recorrente.
5. **"Quanto custa me servir cada cliente?"** — custo de IA + infra por tenant vs. receita (margem real, NFR-07).
6. **"Provisionar/suspender/exportar um tenant"** — operações do ciclo de vida em cliques, com auditoria, sem SQL.

## 3. Arquitetura de informação

Aplicação separada logicamente (mesmo codebase, blueprint `platform/`), acessível apenas em rota dedicada (`ops.xreducacao.com.br` ou `/ops`) com papel `operador_plataforma` + 2FA obrigatório. Navegação lateral, 6 itens:

```
◉ Pulso           ← saúde técnica + negócio em uma tela
▣ Tenants         ← lista, perfil, ciclo de vida
▤ Receita         ← MRR, planos, inadimplência (Asaas)
▥ Custos de IA    ← consumo por tenant, margem, alertas (Release 1.0)
▦ Plataforma      ← deploys, erros, jobs, migrações, feature flags
▧ Auditoria       ← trilha de tudo que operadores fizeram
```

## 4. Especificação por tela

### 4.1 Pulso (home do operador)

Duas metades, lado a lado em desktop:

**Saúde técnica (esquerda):**
- Semáforo geral (verde/âmbar/vermelho) calculado de: uptime do healthcheck, taxa de erro 5xx (últimas 2h), latência p95, fila RQ (profundidade + jobs falhados), status do último deploy.
- Cada indicador clicável → detalhe na tela Plataforma.
- Incidente ativo (se houver) fixado no topo com timestamp e último evento.

**Saúde do negócio (direita):**
- MRR atual + variação mensal · Tenants ativos/pagantes · Alunos ativos totais (7d) · Ativação de tenants novos (% que completou ONB-03 em 7d).
- Fila de ação do operador (espelho da "Fila de Atenção" do admin, mas nível plataforma): "Tenant X inadimplente há 12 dias (modo leitura em 3 dias)" → [Ver] · "Tenant Y a 85% da cota de IA" → [Ver consumo] · "Tenant Z sem login de nenhum usuário há 21 dias (risco de churn)" → [Ver perfil].

Estado vazio da fila = "Nenhuma ação pendente." — mesma filosofia do painel admin.

### 4.2 Tenants

- **Lista** com colunas: nome, plano, status (ativo/leitura/suspenso), alunos ativos, MRR, consumo de IA %, último acesso, saúde (semáforo composto). Ordenável, filtrável por status/plano, busca por nome/slug.
- **Perfil do tenant** (página, não slide-over — aqui a densidade justifica): identidade (logo/cor/subdomínio), métricas de engajamento (mini-versão do que o admin do tenant vê), assinatura e histórico de pagamentos, consumo de IA (série 90d), usuários admin do tenant (com [Reenviar acesso]), log de eventos do tenant.
- **Ações de ciclo de vida** (todas auditadas, todas com confirmação descritiva no padrão §6 do UX_ADMIN):
  - Criar tenant (form que substitui o SQL manual: slug, nome, subdomínio com validação de disponibilidade, plano, cor/logo opcionais) — o fluxo que faltou na criação do `demo`.
  - Suspender / reativar (TEN-04: bloqueio de login <60s, página explicativa) — o motivo é obrigatório e vai para a auditoria.
  - Mudar plano (com pró-rata explicado na tela).
  - Exportar dados (TEN-05: dispara job assíncrono, link expirável) e Excluir (fluxo LGPD com dupla confirmação + prazo de arrependimento de 7 dias).
  - Impersonar admin do tenant (ver o que ele vê, banner vermelho fixo "VOCÊ ESTÁ IMPERSONANDO", tudo auditado, sem acesso a senhas) — a ferramenta nº 1 de suporte.

### 4.3 Receita

- MRR por mês (12m), quebra por plano, movimentos do mês (novos, upgrades, downgrades, churn) — o clássico "MRR bridge".
- Inadimplência: lista de cobranças falhadas (webhook Asaas), dias em atraso, régua automática visível (D+10 leitura, D+30 suspensão — BIL-02) com opção de pausar a régua por tenant (caso pastoral/negociação).
- Exportação CSV de tudo (material de edital/investidor).

### 4.4 Custos de IA (Release 1.0, projetar slots desde já)

- Custo total do mês vs. orçamento; custo por tenant (tabela: interações, tokens, custo, % da cota, % da receita do tenant — a métrica NFR-07 viva).
- Alertas configuráveis (default: 80% da cota → notifica operador e admin do tenant).
- Cache hit rate do cache semântico e economia estimada (valida a arquitetura de custos do doc 03 §8).
- Até a Release 1.0: tela existe com estado vazio explicativo ("Disponível quando o módulo de IA estiver ativo") — mesmo padrão de slot do dashboard do aluno.

### 4.5 Plataforma

- Deploys recentes (via API do Railway se viável; senão, registro manual no pipeline de CI), migração atual do Alembic, feature flags por tenant (tabela editável — é aqui que se liga `tutor_enabled` no futuro), jobs RQ (fila, falhas com retry manual), erros agrupados (integração Sentry: top 5 por frequência, link direto).

### 4.6 Auditoria

- Trilha imutável de toda ação de operador: quem, o quê, em qual tenant, quando, IP (AUTH-04 estendido ao nível plataforma). Filtros por operador/tenant/ação/período. Exportável. **Nenhuma ação de ciclo de vida existe sem linha aqui** — regra de implementação, não de UI.

## 5. UI e design

- **Mesma base de tokens** (`tokens.css`), tema fixo da plataforma XR Educação (o operador não tem tenant — usa a identidade XR: pode ser o primeiro lugar onde a marca própria da XR Educação aparece pura, sem tenant). Modo claro por padrão, denso.
- **Diferenciação visual deliberada do painel de tenant**: barra superior em cor distinta (ex.: grafite com selo "OPERADOR") para que nunca haja confusão sobre "em qual poder estou agindo" — princípio de segurança por design, reforçado no modo impersonação (banner vermelho).
- Tabelas com paginação server-side, filtros persistentes, densidade compacta por padrão (operador é power user — o oposto da Márcia).
- Gráficos: sparklines e barras simples, sem decoração; paleta neutra + semáforos semânticos (`--success/--warning/--danger` já existentes).
- Zero emojis nativos; Lucide; skeleton por zona; WCAG AA (mesmo sendo interno — vira hábito e a equipe cresce).

## 6. Segurança (requisitos duros desta superfície)

1. Papel `operador_plataforma` em tabela própria, nunca atribuível via painel de tenant; concessão só por outro operador + auditoria.
2. 2FA obrigatório (TOTP) para qualquer conta de operador.
3. Sessão curta (30 min de inatividade) e re-autenticação para ações destrutivas (suspender, excluir, impersonar).
4. O painel usa a role de banco com visão cross-tenant **somente leitura** onde possível; escritas passam por serviços auditados — nunca SQL cru exposto.
5. Rate limiting próprio e IP allowlist opcional (config por env var).

## 7. Priorização e faseamento

| Fase | Entrega | Desbloqueia |
|---|---|---|
| **P0 (junto com Release 1.0)** | Tenants: lista + perfil + criar/suspender/plano + auditoria dessas ações | Onboarding do 2º tenant sem SQL; TEN-04 |
| **P0** | Pulso v1 (saúde técnica básica + 4 números de negócio) | Operação diária sem abrir Railway |
| **P1** | Receita (Asaas) + régua de inadimplência visível | BIL-01/02 operáveis |
| **P1** | Impersonação auditada | Suporte real ao primeiro cliente pagante |
| **P1 (com módulo ai/)** | Custos de IA completo | NFR-07 monitorável desde o 1º dia do tutor |
| **P2** | Plataforma (flags, jobs, Sentry) + exportação/exclusão LGPD | Escala de operação; compliance |

## 8. Métricas de sucesso

- Zero operações de tenant via SQL direto após P0 (medível pela auditoria: toda mudança tem trilha).
- Tempo para provisionar tenant novo: de ~30 min manuais para <3 min.
- Tempo para diagnosticar "a plataforma está com problema?": <1 min sem abrir o Railway.
- Pré-requisito de contratação: o primeiro funcionário de suporte/ops consegue operar sem acesso ao banco.

## 9. Prompt de implementação (P0)

```
Leia docs/UX_OPERADOR_SAAS.md por completo e docs/02-ARQUITETURA.md §3.
Implemente a fase P0 na branch feat/OPS-01-painel-operador:

1. Papel operador_plataforma (tabela própria, seed do fundador,
   2FA TOTP obrigatório, sessão 30min, re-auth para ações destrutivas).
2. Blueprint platform/ com rota /ops isolada (403 para qualquer
   usuário de tenant, mesmo admin).
3. Tela Tenants: lista (paginação server-side) + perfil + ações
   criar/suspender/reativar/mudar plano — cada ação com registro
   em audit_log ANTES do commit da mudança (mesma transação).
4. Tela Pulso v1: semáforo técnico (healthcheck, 5xx 2h, p95,
   fila RQ) + 4 métricas de negócio + fila de ação.
5. UI: tokens existentes, tema XR fixo, modo claro denso, barra
   superior "OPERADOR" distinta, zero hex hardcoded (lint ativo).
6. Testes: unitários das ações de ciclo de vida, isolamento
   (usuário de tenant recebe 403 em TODAS as rotas /ops — adicionar
   à suíte de isolamento), auditoria (toda ação gera linha).
Critérios de aceite viram testes. Rota pelo padrão
Sonnet-escreve/Fable-revisa. Não fazer merge sem minha aprovação.
```
