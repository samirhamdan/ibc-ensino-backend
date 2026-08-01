"""
Fase 6 do playbook (docs/PLAYBOOK-MIGRACAO-0.9.md §Fase 6, passo 3/6):
"Modo manutenção ON (página estática)" ... "Modo manutenção OFF".

Um único `before_request`, registrado ANTES de qualquer outro middleware
(inclusive a resolução de tenant) — enquanto ativo, TUDO responde 503,
sem tocar em banco, sessão ou contexto de tenant. Isso é deliberado: o
propósito do modo manutenção é justamente proteger a janela em que o
schema pode estar a meio caminho de uma migração (passo 4, `alembic
upgrade head` roda DEPOIS do ON) — nenhuma rota deve arriscar consultar
um schema inconsistente nesse meio-tempo.

Controle: variável de ambiente MAINTENANCE_MODE (truthy: '1'/'true'/'yes',
case-insensitive) — lida a cada request (não cacheada no import), então o
operador só precisa setar/limpar a variável no Railway; se a plataforma
não reiniciar sozinha ao mudar env var, um `railway redeploy` (sem
rebuild) já aplica.

Exceções (sempre passam, mesmo em manutenção):
- GET /health — monitoração externa (uptime) não pode confundir a janela
  planejada de manutenção com o serviço fora do ar.
- Requests com o header X-Maintenance-Bypass batendo
  MAINTENANCE_BYPASS_TOKEN (se configurado) — permite rodar o smoke test
  de produção (playbook §6, passo 5: "smoke test de produção... somente
  leitura + um aluno de teste") ENQUANTO o modo manutenção ainda protege
  o público geral, antes do OFF.
"""
import os

from flask import request, jsonify, Response

_ROTAS_SEMPRE_LIVRES = {'/health'}

_PAGINA_MANUTENCAO = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Manutenção programada</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #0a0f1e; color: #f1f5f9;
         text-align: center; padding: 4rem 1.5rem; }}
  h1 {{ font-size: 1.6rem; margin-bottom: .5rem; }}
  p {{ color: #94a3b8; max-width: 32rem; margin: .5rem auto; }}
</style>
</head>
<body>
<h1>Manutenção programada</h1>
<p>Estamos aplicando uma atualização na plataforma. Voltamos em instantes —
não é necessário fazer nada, seu progresso está seguro.</p>
</body>
</html>"""


def _truthy(valor):
    return (valor or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _quer_json():
    return request.path.startswith('/api/')


def init_maintenance_middleware(app):
    @app.before_request
    def bloquear_em_manutencao():
        if not _truthy(os.getenv('MAINTENANCE_MODE')):
            return None
        if request.path in _ROTAS_SEMPRE_LIVRES:
            return None

        token = os.getenv('MAINTENANCE_BYPASS_TOKEN')
        if token and request.headers.get('X-Maintenance-Bypass') == token:
            return None

        if _quer_json():
            return jsonify({'error': 'Manutenção programada. Tente novamente em instantes.'}), 503
        return Response(_PAGINA_MANUTENCAO, status=503, mimetype='text/html')
