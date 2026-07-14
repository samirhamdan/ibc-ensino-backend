"""
`shared/` — infraestrutura compartilhada entre módulos da Release 1.0
(doc 02-ARQUITETURA.md §3 e §7): eventos de domínio (outbox) e auditoria.

Vive em `shared/` na raiz (e não `app/shared/`) pelo mesmo motivo documentado
em `core/__init__.py`: `app.py` ainda existe como módulo legado na raiz do
repo, e um pacote `app/` sombrearia o import `app:create_app` usado pelo
gunicorn/railway.json (`import app` resolveria para o pacote, não para
`app.py`). Move para `app/shared/` na reestruturação completa da Release 1.0.

Regra 2 do doc 02 §3: módulos não acessam banco uns dos outros diretamente;
comunicação via `shared.events.publish_event` (outbox consumido por workers,
fora de escopo desta PR).
"""
from shared.events import DomainEvent, publish_event
from shared.audit import AuditLog, registrar_auditoria

__all__ = ['DomainEvent', 'publish_event', 'AuditLog', 'registrar_auditoria']
