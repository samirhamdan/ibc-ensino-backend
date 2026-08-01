"""feat(CUR-03): level, updated_at, skills em courses (§2.8 C3)

Revision ID: 0016_course_meta
Revises: 0015_video_pct
Create Date: 2026-07-31
"""
from alembic import op
import sqlalchemy as sa

revision = '0016_course_meta'
down_revision = '0015_video_pct'
branch_labels = None
depends_on = None

_COLUNAS = {
    'level': (sa.String(50), "'Iniciante'"),
    'updated_at': (sa.DateTime(), 'NULL'),
    'skills': (sa.JSON(), 'NULL'),
}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existentes = {c['name'] for c in insp.get_columns('courses')}
    faltando = {k: v for k, v in _COLUNAS.items() if k not in existentes}
    if not faltando:
        return
    with op.batch_alter_table('courses') as batch:
        for col_name, (col_type, default) in faltando.items():
            nullable = default == 'NULL'
            kw = {'nullable': nullable}
            if not nullable:
                kw['server_default'] = default
            batch.add_column(sa.Column(col_name, col_type, **kw))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existentes = {c['name'] for c in insp.get_columns('courses')}
    with op.batch_alter_table('courses') as batch:
        for col_name in _COLUNAS:
            if col_name in existentes:
                batch.drop_column(col_name)
