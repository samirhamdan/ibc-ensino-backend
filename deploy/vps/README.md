# Deploy na VPS (23.95.96.132 — racknerd)

A VPS tem ~2 GB de RAM compartilhada com outros sistemas (alessio, morumbi3d, morumbi-festas, iago). Para caber nela:

- Só o app roda em container: `xr_educacao_app`, 1 worker, limite de 300 MB.
- Banco `xr` com usuário `xr` próprio, dentro do `alessio_postgres` que já existe.
- O `alessio_caddy` fala com o app pela rede Docker `lite_default`. Nenhuma porta é aberta no host.

## 1. Criar banco e usuário (isolados do n8n)
```sh
SENHA=$(openssl rand -hex 16); echo "Guarde: $SENHA"
docker exec alessio_postgres psql -U alessio -d n8n -c "CREATE USER xr WITH PASSWORD '$SENHA';"
docker exec alessio_postgres psql -U alessio -d n8n -c "CREATE DATABASE xr OWNER xr;"
# Mesmo comportamento do Railway: RLS ainda não é ativado (ver docs/RUNBOOK-RLS.md)
docker exec alessio_postgres psql -U alessio -d n8n -c "ALTER USER xr BYPASSRLS;"
```
Use só letras e números na senha (`openssl rand -hex 16` já gera assim).

## 2. Código e .env
```sh
git clone -b claude/zen-hopper-SeRac https://github.com/samirhamdan/ibc-ensino-backend /opt/xr-educacao
cd /opt/xr-educacao/deploy/vps
cp .env.example .env
nano .env    # XR_DB_PASSWORD=<senha do passo 1>; SECRET_KEY=<openssl rand -hex 32>; ADMIN_*; SMTP_*
chmod +x backup.sh
```

## 3. (Opcional) Trazer os dados do Railway
```sh
pg_dump "<DATABASE_URL do Railway>" -Fc -f /tmp/railway.dump
docker exec -i alessio_postgres pg_restore -U alessio -d xr --no-owner --role=xr < /tmp/railway.dump
```
Sem esse passo, o app sobe com banco novo: as migrações e o seed criam o admin a partir de `ADMIN_EMAIL`/`ADMIN_PASSWORD`.

## 4. Subir
```sh
docker compose up -d --build
docker compose logs -f app              # Ctrl+C ao ver "Booting worker"
docker exec alessio_caddy wget -qO- http://xr_educacao_app:8000/health
```

## 5. Domínio e Caddy
1. Na conta do DuckDNS, crie o subdomínio `xreducacao` apontando para `23.95.96.132`.
2. Adicione o bloco no Caddyfile do `alessio_caddy`. **Faça backup antes**: esse arquivo serve todos os sistemas.
```
xreducacao.duckdns.org {
    encode gzip
    reverse_proxy xr_educacao_app:8000
}
```
3. Valide e recarregue. O reload não derruba os outros sites se a validação passar:
```sh
docker exec alessio_caddy caddy validate --config /etc/caddy/Caddyfile
docker exec alessio_caddy caddy reload --config /etc/caddy/Caddyfile
```

## 6. Backup diário (3h, guarda 14 dias)
```sh
(crontab -l; echo "0 3 * * * /opt/xr-educacao/deploy/vps/backup.sh") | crontab -
```

## Operador da plataforma
Para conceder acesso ao painel do operador (gestão de todos os clientes) a um usuário que já existe:
```sh
docker exec xr_educacao_app python make_operator.py seu@email.com
```
No primeiro acesso a "Operador da plataforma", configure o app autenticador lendo o QR code.

Se perder o celular:
```sh
docker exec xr_educacao_app python make_operator.py seu@email.com --reset-2fa
```

## Atualizar
```sh
cd /opt/xr-educacao && git pull && cd deploy/vps && docker compose up -d --build
```

## Remover tudo (se precisar)
```sh
cd /opt/xr-educacao/deploy/vps && docker compose down
docker exec alessio_postgres psql -U alessio -d n8n -c "DROP DATABASE xr;" -c "DROP USER xr;"
```
Remova também o bloco `xreducacao` do Caddyfile.

## Limitação
O DuckDNS não emite certificado wildcard sem plugin. Por enquanto a plataforma roda num único domínio, com o tenant padrão. Subdomínio por cliente fica para quando houver domínio próprio.
