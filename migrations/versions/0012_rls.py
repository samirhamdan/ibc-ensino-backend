"""feat(NFR-01): Row Level Security em todas as tabelas de domínio

Revision ID: 0012_rls
Revises: 0011_conteudo_contract
Create Date: 2026-07-09

Fase 4, Etapa 4.1 (doc 02 §5.3): ENABLE + FORCE ROW LEVEL SECURITY e política
tenant_isolation em TODAS as tabelas com tenant_id. A aplicação define
app.tenant_id por transação (SET LOCAL via listener — core/tenancy/rls.py).

Semântica fail-closed: sem app.tenant_id definido, a política compara com
NULL e NENHUMA linha é visível (NULLIF de string vazia cobre reset da GUC).

IMPORTANTE (runbook docs/RUNBOOK-RLS.md):
- RLS só tem efeito quando a APP conecta com role SEM BYPASSRLS (superuser
  ignora RLS silenciosamente — a armadilha nº 1 do playbook). Até a troca de
  role no Railway, esta migração é inócua (modo permissive de fato).
- MIGRAÇÕES continuam rodando com role privilegiada: configure
  ALEMBIC_DATABASE_URL (migrations/env.py a prefere sobre DATABASE_URL) —
  com FORCE RLS, backfills rodando como role de app atualizariam 0 linhas.
- SQLite (dev) não tem RLS: no-op com aviso.
"""
from alembic import op

revision = '0012_rls'
down_revision = '0011_conteudo_contract'
branch_labels = None
depends_on = None

# Todas as tabelas com tenant_id (grupos 1–3 + tenant_users)
TABELAS = [
    'user_points', 'badge', 'user_badge', 'achievements', 'user_achievements',
    'certificates', 'activity_feed',
    'lesson_progress', 'progress', 'study_sessions', 'user_trails',
    'onboarding_answers',
    'categories', 'courses', 'modules', 'materials', 'quiz', 'questions',
    'trails', 'trail_courses', 'tutor_courses',
    'announcements', 'notifications', 'announcement_dismissals',
    'tenant_users',
]


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        print('  aviso: RLS é PostgreSQL-only — no-op neste banco '
              f'({bind.dialect.name}); a defesa em dev é o filtro de aplicação.')
        return
    for t in TABELAS:
        op.execute(f'ALTER TABLE {t} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {t} FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON {t}')
        op.execute(
            f"CREATE POLICY tenant_isolation ON {t} "
            f"USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    for t in reversed(TABELAS):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON {t}')
        op.execute(f'ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {t} DISABLE ROW LEVEL SECURITY')
