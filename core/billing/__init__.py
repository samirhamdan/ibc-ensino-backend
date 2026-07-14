"""
`core/billing/` — planos, Asaas, medição (doc 02-ARQUITETURA.md §3, BIL-01/02/03).

Vive em `core/billing/` (e não `app/core/billing/`) pelo mesmo motivo
documentado em `core/__init__.py`: o módulo legado `app.py` ainda existe na
raiz do repo, e um pacote `app/` sombrearia o import `app:create_app` usado
pelo gunicorn/railway.json. Move para `app/core/billing/` na reestruturação
completa da Release 1.0 (quando `app.py` for renomeado/absorvido).

PR 1 de 4 (esta PR): modelo de dados (`Subscription`, `AiUsage`) e o catálogo
de planos. Integração com Asaas (webhooks, cobrança) e o worker de medição
de IA entram nas próximas PRs do módulo.
"""
from core.billing.models import Subscription, AiUsage, WebhookEvent
from core.billing.plans import PLANOS, Plano, get_plan

__all__ = ['Subscription', 'AiUsage', 'WebhookEvent', 'PLANOS', 'Plano', 'get_plan']
