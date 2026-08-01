"""
Promove um usuário existente para role='admin'.

Uso:
    python make_admin.py email@exemplo.com
"""
import sys

from app import create_app, db
from models import User


def main():
    if len(sys.argv) != 2:
        print("Uso: python make_admin.py email@exemplo.com")
        sys.exit(1)

    email = sys.argv[1].strip().lower()

    app = create_app('production')
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if not user:
            print(f"Erro: nenhum usuário encontrado com o email '{email}'.")
            sys.exit(1)

        if user.role == 'admin':
            print(f"Usuário '{email}' já é admin — nada a fazer.")
            return

        anterior = user.role
        user.role = 'admin'
        db.session.commit()
        print(f"Usuário '{email}' promovido de '{anterior}' para 'admin' com sucesso.")


if __name__ == '__main__':
    main()
