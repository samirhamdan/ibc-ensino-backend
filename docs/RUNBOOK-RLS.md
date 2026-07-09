# RUNBOOK — Ativação do RLS em produção (Etapa 4.1)

**Pré-requisito:** migração `0012_rls` aplicada (o preDeploy faz sozinho).
Até executar este runbook, o RLS está criado mas **inócuo**: a app conecta
como superuser/owner do Postgres, que **ignora RLS silenciosamente** — a
armadilha nº 1 do playbook. A defesa só vale após a troca de role.

## Passo a passo (Railway)

1. **Backup verificado** do Postgres (regra 4 do playbook).

2. **Criar a role de aplicação** (no plugin Postgres → aba *Data*/psql, com
   a conexão privilegiada atual):

   ```sql
   CREATE ROLE ibc_app LOGIN PASSWORD '<senha-forte-gerada>' NOBYPASSRLS;
   GRANT USAGE ON SCHEMA public TO ibc_app;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ibc_app;
   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ibc_app;
   -- tabelas/sequências futuras criadas pela role privilegiada:
   ALTER DEFAULT PRIVILEGES IN SCHEMA public
     GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ibc_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public
     GRANT USAGE, SELECT ON SEQUENCES TO ibc_app;
   ```

3. **Variáveis do serviço web** (Railway → serviço `ibc-ensino-backend` →
   Variables):
   - `ALEMBIC_DATABASE_URL` = a URL ATUAL privilegiada (a mesma
     `DATABASE_URL` de hoje). As migrações do preDeploy continuam rodando
     com bypass — com FORCE RLS, migração rodando como `ibc_app`
     atualizaria 0 linhas silenciosamente.
   - `DATABASE_URL` = mesma URL trocando usuário/senha para
     `ibc_app:<senha>`.

4. **Redeploy.** O preDeploy roda `alembic upgrade head` (via
   `ALEMBIC_DATABASE_URL`) e a app sobe conectada como `ibc_app`.

5. **Verificação (5 min):**
   - login + dashboard + abrir uma aula como aluno real → tudo 200;
   - logs sem `permission denied` (falta de GRANT) e sem listas vazias
     inesperadas (GUC não setada → fail-closed);
   - no psql privilegiado: `SELECT rolname, rolbypassrls FROM pg_roles
     WHERE rolname = 'ibc_app';` → `f`.

6. **Rollback imediato** (qualquer sintoma): devolver `DATABASE_URL` para a
   URL privilegiada e redeploy — o RLS volta a ser inócuo, app volta ao
   comportamento anterior. As políticas podem ficar.

## O que o código já garante

- `SET LOCAL app.tenant_id` por transação (listener em `core/tenancy/rls.py`;
  `SET LOCAL`, nunca `SET` de sessão — sem vazamento entre requests no pool).
- Fail-closed: transação sem GUC → política compara com NULL → zero linhas.
- Prova em CI: `tests/test_rls.py` cria role sem BYPASSRLS num Postgres real
  e demonstra que query SEM filtro de aplicação não vê/escreve outro tenant.
