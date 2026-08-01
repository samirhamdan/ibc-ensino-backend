"""feat(GAM-02) Etapa 3 — streak: current_streak/longest_streak em user_points

Revision ID: 0014_streak
Revises: 0013_tenant_users
Create Date: 2026-07-11

UX_ALUNO_SAAS.md §3 Grupo 3 / §6 Etapa 3: streaks migram de localStorage
para o servidor. Reaproveita user_points (mesma linha que já rastreia
last_activity_date por tenant+usuário) em vez de criar uma tabela nova —
current_streak/longest_streak são só mais dois contadores por linha
existente, sem chave nova nem FK.

Guardas por introspecção (idempotente/re-executável, mesmo padrão do
resto do grupo 1). NOT NULL direto com server_default: dado existente
(current_streak/longest_streak inexistentes) vira 0, não NULL — sem
precisar de um passo de backfill separado.
"""
from alembic import op
import sqlalchemy as sa

revision = '0014_streak'
down_revision = '0013_tenant_users'
branch_labels = None
depends_on = None

_COLUNAS = ('current_streak', 'longest_streak')


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existentes = {c['name'] for c in insp.get_columns('user_points')}
    faltando = [c for c in _COLUNAS if c not in existentes]
    if not faltando:
        return
    with op.batch_alter_table('user_points') as batch:
        for coluna in faltando:
            batch.add_column(sa.Column(coluna, sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existentes = {c['name'] for c in insp.get_columns('user_points')}
    with op.batch_alter_table('user_points') as batch:
        for coluna in _COLUNAS:
            if coluna in existentes:
                batch.drop_column(coluna)
