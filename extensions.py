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
_redis_url = os.getenv('REDIS_URL')
limiter = Limiter(key_func=get_remote_address,
                  storage_uri=_redis_url or 'memory://')
