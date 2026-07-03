from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()

# Nota: storage padrão é em memória (por processo) — correto para o único
# worker gunicorn usado hoje (railway.json). Se o número de workers for
# aumentado no futuro, cada worker passa a ter seu próprio contador
# independente, multiplicando o limite efetivo pelo número de workers —
# nesse caso, migrar para um storage compartilhado (ex.: Redis).
limiter = Limiter(key_func=get_remote_address)
