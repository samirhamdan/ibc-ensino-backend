# OPS-STAGING.md — Ambiente de staging no Railway (Fase 5)

Procedimento operacional para o ensaio geral de migração
(`docs/PLAYBOOK-MIGRACAO-0.9.md` §Fase 5). Complementa `scripts/rehearsal.sh`
— aqui é o que acontece ANTES (recriar o staging) e DEPOIS (deletar) do
script, que é só a parte automatizável.

**Nunca versionar credencial de banco neste repositório.** As URLs internas
(`*.railway.internal`) ficam só em `scripts/run_rehearsal.sh`, local, fora do
git (`.gitignore` já cobre `scripts/run_rehearsal.sh` — confirme com
`git check-ignore -v scripts/run_rehearsal.sh` antes de qualquer commit).

## 1. Pré-requisitos

- Railway CLI instalado e autenticado: `railway login`.
- Projeto linkado neste diretório: `railway link` (escolha o projeto
  IBC Ensino / XR Educação).
- Dois **environments** Railway no mesmo projeto: `production` e `staging`
  (é o que os flags `--environment production` / `--environment staging`
  do `rehearsal.sh` selecionam).

## 2. Recriar o ambiente staging

O staging é **descartável por design** — cada ensaio começa de um banco
vazio, recém-provisionado, para garantir que o `alembic upgrade head`
cronometrado reflete uma migração real (não um banco já parcialmente
migrado de um ensaio anterior).

1. No painel do Railway, dentro do environment `staging`:
   - Se já existir um serviço Postgres de um ensaio anterior, delete-o
     (seção 3 abaixo) antes de recriar.
   - Adicione um novo serviço **PostgreSQL** (template do Railway).
   - Copie a **URL interna** (`postgres.railway.internal:5432/...` — só
     resolve de dentro da rede do Railway, por isso o script sempre chama
     os comandos via `railway run --environment staging`, nunca direto
     deste shell).
2. Atualize `scripts/run_rehearsal.sh` (local, não versionado) com a nova
   `DATABASE_URL_STAGING` — a senha muda a cada Postgres recriado.
3. Não é necessário criar tabelas manualmente: `scripts/rehearsal.sh`
   restaura o dump de produção e depois roda `alembic upgrade head` —
   o schema inteiro vem disso.

## 3. Rodar o ensaio

```bash
bash scripts/run_rehearsal.sh
```

O que acontece (ver o cabeçalho de `scripts/rehearsal.sh` para o detalhe
de cada passo): dump de produção → restaura em staging → `alembic upgrade
head` cronometrado → `pytest -m smoke` (as 5 jornadas críticas do aluno) →
ciclo `alembic downgrade`/`upgrade` (prova o rollback) → cria o tenant
`demo` em staging (idempotente, via `flask shell`) → relatório final.

Saídas geradas (nenhuma versionada — todas no `.gitignore`):
- `staging-rehearsal-report.txt` — relatório com o tempo de cada etapa.
- `rehearsal-backup-<timestamp>.sql` — dump de produção usado no ensaio.
  Contém dado real de usuários — trate como sensível mesmo estando fora
  do git; apague depois de revisar o relatório (`rm rehearsal-backup-*.sql`).

Se o script abortar no meio (qualquer etapa falhando), **não** tente
consertar o staging manualmente e continuar — ele já pode estar num estado
inconsistente (migração parcial). Siga a instrução impressa pelo próprio
script: delete o staging (seção 4) e recrie (seção 2) antes do próximo
ensaio.

**Gate de saída da Fase 5** (playbook): ensaio completo sem intervenção
manual, do início ao fim; tempo total de migração conhecido (linha "TOTAL
do ensaio" no relatório); rollback provado no próprio ensaio (passo 5),
não só no papel.

## 4. Deletar o staging após o ensaio (economizar créditos Hobby)

O plano Hobby do Railway cobra por uso — um Postgres de staging ocioso
consome crédito à toa entre ensaios. Depois de revisar o relatório:

1. No painel do Railway, environment `staging` → serviço Postgres →
   **Settings → Delete Service**. Confirme a exclusão.
2. Localmente, apague os artefatos sensíveis que sobraram:
   ```bash
   rm -f rehearsal-backup-*.sql staging-rehearsal-report.txt
   ```
3. **Não** delete o environment `staging` inteiro se ele tiver outros
   serviços além do Postgres (ex.: uma réplica do app para smoke via HTTP)
   — só o serviço de banco, que é o único recriado a cada ensaio.
4. Da próxima vez que for rodar o ensaio, volte à seção 2.

## 5. Segurança das credenciais

- As duas URLs (produção e staging) só existem em `scripts/run_rehearsal.sh`
  local. Se você suspeitar que uma credencial vazou (ex.: colada num chat,
  commitada por engano em outro branch), **rotacione a senha do Postgres
  no Railway imediatamente** (Settings → o serviço → regenerar credencial)
  — não basta remover do arquivo, a senha antiga continua válida até ser
  trocada no Railway.
- Antes de QUALQUER `git add`/`git commit` neste diretório, rode
  `git status --short` e confirme que `scripts/run_rehearsal.sh` não
  aparece na lista (ele deve estar ignorado). Se aparecer, PARE — algo
  mudou no `.gitignore` ou o arquivo foi forçado com `git add -f`.
