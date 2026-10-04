"""Concede (ou revoga) o papel de operador da plataforma XR.

Uso:
    python make_operator.py email@exemplo.com            # concede
    python make_operator.py email@exemplo.com --revogar  # revoga
    python make_operator.py email@exemplo.com --reset-2fa

O operador configura o 2FA (TOTP) no primeiro acesso ao painel.
"""
import sys

from app import create_app, db
from models import User
from core.plataforma.models import OperadorPlataforma


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = {a for a in sys.argv[1:] if a.startswith('--')}
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)
    email = args[0].strip().lower()
    app = create_app('production')
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if not user:
            print(f"Erro: nenhum usuário com o e-mail '{email}'.")
            sys.exit(1)
        op = OperadorPlataforma.query.filter_by(user_id=user.id).first()
        if '--revogar' in flags:
            if op:
                op.ativo = False
                db.session.commit()
            print(f"Operador '{email}' revogado.")
            return
        if op is None:
            op = OperadorPlataforma(user_id=user.id)
            db.session.add(op)
        op.ativo = True
        if '--reset-2fa' in flags:
            op.totp_segredo, op.totp_ativo, op.totp_ultimo_contador = None, False, None
        db.session.commit()
        print(f"'{email}' é operador da plataforma. 2FA configurado: {'sim' if op.totp_ativo else 'não (configurar no primeiro acesso)'}")


if __name__ == '__main__':
    main()
