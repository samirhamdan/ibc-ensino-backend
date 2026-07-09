"""Ambiente Alembic — URL vem de DATABASE_URL (mesma convenção do app).

Sem autogenerate por enquanto: o schema legado ainda nasce de db.create_all()
(será baselineado na Fase 3); as migrações desta fase são escritas à mão e
tocam apenas tabelas novas de tenancy.
"""
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from dotenv import load_dotenv
load_dotenv()

config = context.config

basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
default_url = f"sqlite:///{os.path.join(basedir, 'instance', 'ibc_ensino.db')}"
url = os.getenv('DATABASE_URL', default_url)
if url.startswith('postgres://'):
    url = url.replace('postgres://', 'postgresql://', 1)
config.set_main_option('sqlalchemy.url', url)

target_metadata = None


def run_migrations_offline():
    context.configure(url=url, target_metadata=target_metadata,
                      literal_binds=True,
                      dialect_opts={'paramstyle': 'named'})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
