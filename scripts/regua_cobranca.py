#!/usr/bin/env python
"""CLI da régua de inadimplência (BIL-02, PR 3) — invocável por um
scheduler EXTERNO (cron do SO, Railway Cron Job, etc.): este repo não tem
nenhuma infra de scheduler/worker em processo (ver docs/DEBITOS.md #25
sobre a mesma lacuna pro RQ) — a única responsabilidade daqui é criar o
app context e chamar core.billing.regua.executar_regua().

Uso:
    python scripts/regua_cobranca.py
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')


def main():
    from app import create_app
    app = create_app('production' if '--production' in sys.argv else 'development')
    with app.app_context():
        from core.billing.regua import executar_regua
        resumo = executar_regua()
        logging.getLogger(__name__).info('regua_cobranca: %s', resumo)


if __name__ == '__main__':
    main()
