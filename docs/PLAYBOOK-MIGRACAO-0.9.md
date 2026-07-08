# Playbook de Migração — Release 0.9 (Multi-tenancy via Claude Code)
**Objetivo:** transformar o IBC Ensino na plataforma multi-tenant **XR Educação**, com o IBC como tenant nº 1, sem downtime perceptível e sem regressão funcional.
**Executor:** Claude Code (agente) + Samir (revisão e decisões)
**Referências:** docs/02-ARQUITETURA.md §4–5 · docs/01-PRD.md (TEN-01 a TEN-05)
**Duração estimada:** 6 fases · 2–4 semanas em ritmo solo

---

## Regras do jogo (leia antes de qualquer prompt)

1. **Uma fase por vez, um PR por etapa.** Nunca peça ao Claude Code "faça a migração inteira". Cada etapa termina com testes verdes e revisão sua.
2. **Nada vai para `main` sem a suíte de isolamento passar** (a partir da Fase 2).
3. **Toda migração Alembic é reversível** (`downgrade` implementado e testado).
4. **Banco de produção só é tocado nas Fases 5–6**, sempre com backup verificado antes.
5. **Branch de trabalho:** `release/0.9-tenancy`, com branches de etapa (`feat/TEN-01-tenant-model` etc.) mergeadas nela.

## Pré-requisitos (Fase 0 — ~1 dia)

Checklist antes de abrir o Claude Code:

- [ ] Backup completo do PostgreSQL de produção (Railway) baixado e **restaurado localmente com sucesso** (backup não testado = não existe).
- [ ] Ambiente de staging no Railway: clone do serviço web + banco restaurado do backup. Toda validação de fase acontece aqui.
- [ ] Pacote de docs commitado em `docs/` (feito no passo anterior).
- [ ] Arquivo `CLAUDE.md` na raiz do repo (criado abaixo) — é o contrato permanente do agente.
- [ ] Cobertura de testes atual mapeada: rode `pytest --cov` e anote o baseline. Se áreas críticas (auth, matrículas, progresso) não têm testes, a Fase 1 começa por eles.

**Prompt inicial ao Claude Code para criar o CLAUDE.md:**

```
Leia docs/02-ARQUITETURA.md e docs/01-PRD.md. Crie um CLAUDE.md na raiz
com: (1) stack e comandos de dev/teste/migração deste repo; (2) as 5
regras para agentes do §3 da arquitetura; (3) convenção de branches e
commits com IDs de requisito (ex: feat(TEN-02): ...); (4) instrução de
que nenhum model de domínio pode ser criado sem tenant_id a partir da
Release 0.9. Não invente comandos: inspecione o repo para descobrir
como os testes e o servidor rodam hoje.
```

---

## Fase 1 — Rede de segurança (testes de caracterização)

**Por quê primeiro:** você vai mexer em TODAS as tabelas. Sem testes que capturem o comportamento atual, não há como saber se quebrou algo.

**Etapa 1.1 — Testes de caracterização das jornadas críticas.**
```
Crie testes de integração (pytest) que capturem o comportamento ATUAL
de: login, listagem de trilhas/cursos, abertura de lição, resposta de
quiz, progresso do aluno, pontos/conquistas, emissão de certificado.
Use o banco de teste real (Postgres em container), não mocks de ORM.
Objetivo: testes de caracterização — documentam o que o sistema faz
hoje, mesmo comportamentos estranhos. Não corrija nada que encontrar;
apenas registre em docs/DEBITOS.md.
```
**Gate de saída:** suíte roda em <5 min localmente; jornadas J1–J4 do PRD cobertas no estado atual.

**Etapa 1.2 — CI endurecido.**
```
Configure o pipeline de CI (GitHub Actions) com: lint, pytest com
Postgres de serviço, alembic upgrade head + downgrade base + upgrade
head (teste de reversibilidade), e job placeholder "isolation-suite"
que por enquanto passa vazio mas já é required check.
```

---

## Fase 2 — Fundação de tenancy (sem tocar nas tabelas existentes)

**Etapa 2.1 — Models e contexto (TEN-01 parcial).**
```
Implemente conforme docs/02-ARQUITETURA.md §4-5:
1. Migração: tabelas tenants e tenant_users (UUIDv7 como PK).
2. Classe base TenantScopedModel (mixin SQLAlchemy com tenant_id,
   índice composto) em app/core/tenancy/.
3. Contexto de request: g.tenant + função require_tenant().
4. Seed de desenvolvimento: tenant "ibc" e tenant "demo".
Nenhuma tabela existente é alterada nesta etapa. Testes unitários
para o mixin e o contexto.
```

**Etapa 2.2 — Middleware de resolução (TEN-02).**
```
Implemente o middleware de resolução de tenant por subdomínio com
cache em memória (Redis entra na Fase 4; use dict com TTL por ora):
- subdomínio → tenant ativo → g.tenant
- subdomínio inexistente → 404 institucional
- em desenvolvimento, header X-Tenant-Slug como override
Inclua testes: subdomínio válido, inválido, tenant suspenso.
```

**Etapa 2.3 — Suíte de isolamento (a peça mais importante da release).**
```
Implemente tests/isolation/ conforme docs/02-ARQUITETURA.md §5.4:
framework parametrizado que para cada endpoint autenticado cria dados
em tenant A e B, autentica em A, e tenta acessar recursos de B por ID
direto, listagem, busca e filtros — exigindo 404/403 e zero linhas.
Comece cobrindo apenas as tabelas tenants/tenant_users. A suíte deve
descobrir endpoints por convenção e FALHAR se um endpoint novo não
tiver caso de isolamento registrado. Ative o job isolation-suite no CI
como required.
```
**Gate de saída da Fase 2:** isolamento verde no CI; app continua funcionando exatamente como antes para o IBC (testes de caracterização verdes).

---

## Fase 3 — Migração das tabelas de domínio (o coração)

Estratégia **expand → backfill → contract**, tabela a tabela, em grupos. Ordem: das folhas para o centro (menos dependências primeiro).

**Grupos sugeridos:** (1) gamificação: pontos, conquistas, certificados, streaks → (2) progresso: matrículas, progresso_licoes, tentativas_quiz → (3) conteúdo: trilhas, cursos, módulos, lições, blocos, questões.

**Prompt-modelo por grupo (repita 3×, ajustando o grupo):**
```
Migração multi-tenant do grupo [gamificação] conforme expand/contract:
EXPAND (migração 1):
- ADD COLUMN tenant_id UUID NULL em cada tabela do grupo
- Índices compostos (tenant_id, <fk_principal>) CONCURRENTLY
BACKFILL (migração 2, idempotente):
- UPDATE em lotes de 5.000 linhas: tenant_id = <id do tenant ibc>
- Registre progresso; deve ser seguro re-executar
CONTRACT (migração 3):
- SET NOT NULL + FK para tenants
- Models atualizados para herdar TenantScopedModel
- Repositórios/queries do módulo filtrando por g.tenant
Atualize os testes de caracterização do grupo para rodar com tenant e
adicione os casos na suíte de isolamento. Downgrade implementado nas 3
migrações.
```

**Sua revisão em cada grupo (não delegue):** ler o diff das queries alteradas procurando qualquer `Query` sem filtro de tenant; rodar a suíte completa; smoke manual no staging.

**Etapa 3.4 — Varredura de queries órfãs.**
```
Faça uma auditoria estática do repo: liste TODA query SQLAlchemy ou SQL
cru que toque tabelas com tenant_id sem passar pelos repositórios com
filtro de tenant. Gere relatório em docs/AUDITORIA-QUERIES.md com
arquivo:linha e correção proposta. Corrija após minha aprovação.
```

---

## Fase 4 — RLS + JWT com claims de tenant (defesa em profundidade)

**Etapa 4.1 — RLS.**
```
Conforme docs/02-ARQUITETURA.md §5.3:
1. Migração criando role de aplicação sem BYPASSRLS; ajuste a
   DATABASE_URL de app para essa role (documente no CLAUDE.md).
2. ENABLE + FORCE ROW LEVEL SECURITY + política tenant_isolation em
   todas as tabelas com tenant_id.
3. Sessão SQLAlchemy: SET LOCAL app.tenant_id na abertura de cada
   transação (event listener), a partir de g.tenant.
4. Teste que prova a defesa em profundidade: query deliberadamente SEM
   filtro de aplicação deve retornar zero linhas de outro tenant por
   causa do RLS.
Atenção: migrações Alembic e scripts de operador usam role separada
com BYPASSRLS — configure e documente.
```

**Etapa 4.2 — JWT com tenant (AUTH-03 parcial).**
```
Adicione claims tenant_id e papel ao JWT. Regra dura no middleware:
tenant do token deve ser igual ao tenant do subdomínio, senão 403.
Migre a tabela de usuários: papéis saem do usuário global e passam a
viver em tenant_users. Testes: token de tenant A em subdomínio B → 403.
```

**Etapa 4.3 — Redis real.** Cache de tenant, rate limiting básico e base para RQ (necessário na Release 1.0, barato de fazer agora).

**Gate de saída:** teste de defesa em profundidade verde; suíte de isolamento cobrindo 100% das tabelas de domínio.

---

## Fase 5 — Ensaio geral em staging

1. Restaure backup **fresco** de produção no staging.
2. `alembic upgrade head` completo, cronometrado (você precisa saber quanto tempo o backfill leva com dados reais).
3. Rode a suíte completa + smoke manual das 5 jornadas como aluno real do IBC.
4. Teste o downgrade até o ponto pré-0.9 e o upgrade de novo.
5. Crie o tenant `demo` no staging e repita o smoke nele (validação do isolamento a olho nu).

**Prompt útil:**
```
Escreva scripts/rehearsal.sh que executa o ensaio de migração contra o
staging: backup lógico prévio, upgrade cronometrado por migração,
smoke tests via pytest -m smoke, e relatório final. Aborta no primeiro
erro com instrução de rollback.
```

**Gate de saída (go/no-go para produção):** ensaio completo sem intervenção manual; tempo total de migração conhecido; plano de rollback impresso (literalmente).

---

## Fase 6 — Produção

**Janela:** horário de menor uso (madrugada de sábado costuma ser o vale para plataforma de igreja — confirme nos seus analytics).

1. Avisar usuários (banner 48h antes: "manutenção programada, até X min").
2. Backup + verificação de restauração (de novo — o de ontem não vale).
3. Modo manutenção ON (página estática).
4. `alembic upgrade head` (tempo já conhecido da Fase 5).
5. Deploy da versão 0.9; smoke test de produção (script da Fase 5 apontado para prod, somente leitura + um aluno de teste).
6. Modo manutenção OFF; monitorar Sentry e logs por 48h com atenção a qualquer 403/404 anômalo.
7. **Rollback se necessário:** manutenção ON → `alembic downgrade <rev pré-0.9>` → deploy da tag anterior → manutenção OFF. Critério objetivo de rollback: qualquer suspeita de vazamento entre tenants (crítico) ou >5% de erro nas jornadas por >15 min.

**Pós-migração (mesma semana):**
- Subdomínio `ibc.` configurado e DNS propagado; domínio antigo redireciona.
- Tenant `demo` criado em produção → é o seu ambiente de demonstração comercial e o segundo tenant que valida o isolamento real (critério da Release 0.9 no PRD §7).
- Retrospectiva em docs/RETRO-0.9.md: o que o Claude Code fez bem/mal, prompts que funcionaram — vira insumo para a Release 1.0 (módulo de IA).

---

## Armadilhas conhecidas (aprenda com a dor dos outros)

| Armadilha | Prevenção neste playbook |
|---|---|
| `CREATE INDEX` travando tabela em produção | `CONCURRENTLY` na fase expand (fora de transação Alembic — usar `op.execute` com autocommit) |
| Backfill estourando timeout/locks | Lotes de 5.000 + idempotência |
| RLS ligado com app conectando como superuser (RLS silenciosamente ignorado) | Role sem BYPASSRLS + teste de defesa em profundidade (4.1.4) |
| `SET app.tenant_id` vazando entre requests no pool | `SET LOCAL` (escopo de transação), nunca `SET` de sessão |
| Query nova sem filtro passando despercebida | Suíte de isolamento required no CI + auditoria 3.4 |
| Claude Code "corrigindo" comportamento legado durante a migração | Instrução explícita de caracterização (1.1) + DEBITOS.md |
| Streaks em localStorage perdidos na virada | Fora do escopo 0.9 — migração de streaks para servidor é GAM-02 na Release 1.0; comunicar no banner |
