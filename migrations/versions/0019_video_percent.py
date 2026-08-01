"""feat(GAM-01): video_percent em lesson_progress (§2.8 A3)

Revision ID: 0015_video_pct
Revises: 0018_billing_metering_columns
Create Date: 2026-07-31

Armazena o percentual real de vídeo assistido (0.0–100.0) reportado pela
YouTube IFrame API / Vimeo Player SDK. Complementa o booleano video_watched
que continua existindo como flag de conclusão.
"""
from alembic import op
import sqlalchemy as sa

revision = '0015_video_pct'
down_revision = '0018_billing_metering_columns'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existentes = {c['name'] for c in insp.get_columns('lesson_progress')}
    if 'video_percent' not in existentes:
        with op.batch_alter_table('lesson_progress') as batch:
            batch.add_column(sa.Column('video_percent', sa.Float(), nullable=False, server_default='0'))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existentes = {c['name'] for c in insp.get_columns('lesson_progress')}
    if 'video_percent' in existentes:
        with op.batch_alter_table('lesson_progress') as batch:
            batch.drop_column('video_percent')
