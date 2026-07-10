import os

from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()

# Rate limiting (Etapa 4.3): com REDIS_URL o storage é compartilhado entre
# workers/réplicas — sem ela, memória por processo (correto para o único
# worker atual; com réplicas, cada worker teria contador próprio e o limite
# efetivo seria multiplicado — docs/DEBITOS.md #10, resolvido quando o Redis
# for provisionado).
#
# in_memory_fallback_enabled=True: se o Redis configurado ficar inacessível
# em runtime, o limiter cai para memória em vez de propagar a exceção do
# storage — sem isso, Redis fora do ar derrubava /login e /forgot-password
# com 500 para TODOS os tenants (achado de revisão de segurança).
_redis_url = os.getenv('REDIS_URL')
limiter = Limiter(key_func=get_remote_address,
                  storage_uri=_redis_url or 'memory://',
                  in_memory_fallback_enabled=True)
