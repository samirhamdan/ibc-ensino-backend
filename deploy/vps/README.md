# Deploy na VPS (23.95.96.132)

A stack roda em Docker Compose: app (gunicorn), Postgres 16 e Redis. Ela fica atrás do Caddy que já existe no projeto sdr-agent. O app escuta em `172.18.0.1:5003`, o mesmo padrão do Morumbi Festas (porta 5001), então não fica exposto na internet.

## 1. Conferir a VPS
```sh
ssh root@23.95.96.132
uname -a; nproc; free -h; df -h /
docker network inspect bridge -f '{{(index .IPAM.Config 0).Gateway}}'   # deve ser 172.18.0.1
ss -ltnp | grep -E ':500[0-9]'                                        # porta 5003 livre?
```
Se o gateway não for `172.18.0.1`, use o mesmo IP do bloco `morumbifestas` no Caddyfile.

### Convivência com os 3 sistemas que já rodam
```sh
docker ps --format 'table {{.Names}}\t{{.Ports}}'   # portas e nomes já em uso
docker stats --no-stream                            # consumo de RAM atual
```
- Projeto Compose separado (`xr-educacao`): containers, volumes e rede próprios. Não usa o Postgres nem o Redis dos outros sistemas.
- Nenhuma porta pública. Só `172.18.0.1:5003` para o Caddy. Se a 5003 estiver ocupada, troque em `docker-compose.yml` e no Caddyfile.
- O Caddyfile é compartilhado. **Faça backup antes de editar** (`cp Caddyfile Caddyfile.bak`) e valide com `docker exec lite_default-caddy-1 caddy validate --config /etc/caddy/Caddyfile` antes de reiniciar. Um erro de sintaxe derruba o HTTPS dos 3 sistemas.
- A stack usa cerca de 400–600 MB de RAM. Se a VPS tiver ≤2 GB livres, troque `--workers 2` por `--workers 1` no Dockerfile.

## 2. Código e configuração
```sh
git clone -b claude/zen-hopper-SeRac https://github.com/samirhamdan/ibc-ensino-backend /opt/xr-educacao
cd /opt/xr-educacao/deploy/vps
cp .env.example .env && nano .env      # SECRET_KEY: python3 -c "import secrets;print(secrets.token_hex(32))"
mkdir -p backups && chmod +x backup.sh
```

## 3. DNS
Crie um subdomínio no DuckDNS (ex.: `xreducacao`) apontando para `23.95.96.132`.

## 4. Migrar o banco do Railway (antes do primeiro start)
```sh
docker compose up -d db
pg_dump "<DATABASE_URL do Railway>" -Fc -f backups/railway.dump   # rodar de qualquer máquina com pg_dump 16
docker compose exec -T db pg_restore -U xr -d xr --no-owner --no-acl < backups/railway.dump
```
Os PDFs antigos do Railway ficavam em `/tmp/uploads`, que é apagado a cada deploy, então provavelmente já se perderam. Os materiais com upload precisam ser reenviados. Links externos não são afetados.

## 5. Subir
```sh
docker compose up -d --build
docker compose logs -f app       # espera "Booting worker"
curl -s http://172.18.0.1:5003/health
```

## 6. Caddy
Adicione em `/opt/sdr-agent/infra/lite/Caddyfile`:
```
xreducacao.duckdns.org {
    reverse_proxy 172.18.0.1:5003
}
```
Depois rode `docker restart lite_default-caddy-1`. Confira o nome com `docker ps | grep caddy`.

## 7. Backup diário
```sh
crontab -e
0 3 * * * /opt/xr-educacao/deploy/vps/backup.sh
```

## Atualizar
```sh
cd /opt/xr-educacao && git pull && cd deploy/vps && docker compose up -d --build
```
As migrações e o seed rodam sozinhos no start do container.

## Limitação: subdomínio por tenant
O DuckDNS não permite certificado wildcard sem o plugin de DNS do Caddy. Enquanto isso não estiver configurado, a plataforma roda num único domínio, com o tenant padrão. Quando houver um domínio próprio, use Cloudflare com `*.dominio` e `TENANT_BASE_DOMAIN`.
