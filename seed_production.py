"""
Seed seguro para produção (Vercel + PostgreSQL/Neon).

Requer a variável de ambiente DATABASE_URL apontando para o banco de produção.
Cria as tabelas (se necessário), os dados de configuração/níveis/conquistas
padrão e um único usuário admin a partir de ADMIN_EMAIL / ADMIN_PASSWORD.

Uso:
    DATABASE_URL=postgresql://... python seed_production.py
"""
import os

from app import create_app, db
from models import User, Category
from seed import seed_config, seed_levels, seed_achievements, seed_badges, seed_tenants

DEFAULT_CATEGORIES = ['Teologia', 'Crescimento', 'Bíblia']


def seed_admin():
    admin_email = os.getenv('ADMIN_EMAIL')
    admin_password = os.getenv('ADMIN_PASSWORD')

    if not admin_email or not admin_password:
        print("ADMIN_EMAIL/ADMIN_PASSWORD não definidos — criação de admin padrão pulada "
              "(defina ambos no ambiente se precisar criar um admin inicial).")
        return

    if User.query.filter_by(email=admin_email).first():
        print(f"Usuário admin '{admin_email}' já existe — pulando.")
        return

    admin = User(name='Administrador', email=admin_email, role='admin')
    admin.set_password(admin_password)
    db.session.add(admin)
    db.session.commit()
    print(f"Usuário admin '{admin_email}' criado.")


def seed_categories():
    from core.tenancy import current_tenant_id
    for name in DEFAULT_CATEGORIES:
        if Category.query.filter_by(name=name, tenant_id=current_tenant_id()).first():
            continue
        db.session.add(Category(name=name))
    db.session.commit()
    print("Categorias padrão verificadas/criadas.")


def main():
    app = create_app('production')
    with app.app_context():
        db.create_all()

        seed_tenants()   # PRIMEIRO: badges/achievements são por tenant
        seed_config()
        seed_levels()
        seed_badges()
        seed_achievements()
        seed_categories()
        seed_admin()

        print("Seed de produção concluído.")


if __name__ == '__main__':
    main()
