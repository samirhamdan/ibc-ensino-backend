#!/usr/bin/env python3
"""Etapa 3.4 do playbook — auditoria estática de queries órfãs.

Varre o código de aplicação procurando TODA query (SQLAlchemy ou SQL cru)
que toque tabela com tenant_id SEM passar por filtro de tenant. Gera o
relatório docs/AUDITORIA-QUERIES.md com arquivo:linha e correção proposta.

Uso: python scripts/audit_queries.py [--check]
  --check  sai com código 1 se houver achados (para uso futuro em CI)
"""
import glob
import re
import sys
import os

# Modelos tenant-scoped (Fase 3 completa — grupos 1, 2 e 3)
MODELOS_SCOPED = [
    'UserPoints', 'Badge', 'UserBadge', 'Achievement', 'UserAchievement',
    'Certificate', 'ActivityFeed',
    'LessonProgress', 'Progress', 'StudySession', 'UserTrail', 'OnboardingAnswer',
    'Category', 'Course', 'Module', 'Material', 'Quiz', 'Question',
    'Trail', 'TrailCourse', 'TutorCourse',
    'Announcement', 'Notification', 'AnnouncementDismissal',
    'Tenant', 'TenantUser',
]
# Tenant/TenantUser são as tabelas-mãe: consultas por slug/subdomínio são o
# mecanismo de RESOLUÇÃO de tenant, não vazamento — tratadas como exceção.
EXCECOES_MODELO = {'Tenant'}

TABELAS_SCOPED = [
    'user_points', 'badge', 'user_badge', 'achievements', 'user_achievements',
    'certificates', 'activity_feed', 'lesson_progress', 'progress',
    'study_sessions', 'user_trails', 'onboarding_answers', 'categories',
    'courses', 'modules', 'materials', 'quiz', 'questions', 'trails',
    'trail_courses', 'tutor_courses', 'announcements', 'notifications',
    'announcement_dismissals',
]

# Arquivos de aplicação (migrações ficam fora: SQL cru intencional de
# backfill; testes ficam fora: criam cenários cross-tenant de propósito)
ALVOS = sorted(glob.glob('routes/*.py')) + ['app.py', 'seed.py',
                                            'seed_production.py', 'make_admin.py']

M = '|'.join(m for m in MODELOS_SCOPED if m not in EXCECOES_MODELO)
RE_QUERY = re.compile(rf'\b({M})\.query\b')
RE_OK = re.compile(r'tenant_id\s*=|\.tenant_id\s*==|get_scoped')
# Exceções JUSTIFICADAS: lookup global de certificado por cert_code é design
# (verificação pública por código único não-adivinhável — o código precisa
# ser único globalmente, e a consulta retorna no máximo o certificado exato).
RE_JUSTIFICADA = re.compile(r'cert_code\s*=|tenant-scope: intencionalmente global')
RE_RAW = re.compile(r'(db\.session\.execute|sa\.text|text\()')


def _contexto(linhas, i, janela=3):
    """A query pode encadear o filtro nas linhas seguintes."""
    return ' '.join(linhas[i:i + janela])


def auditar():
    achados = []
    for path in ALVOS:
        if not os.path.exists(path):
            continue
        linhas = open(path).read().splitlines()
        for i, linha in enumerate(linhas):
            m = RE_QUERY.search(linha)
            if m and not RE_OK.search(_contexto(linhas, i)):
                if RE_JUSTIFICADA.search(linha):
                    continue   # exceção documentada (ver comentário acima)
                achados.append((path, i + 1, m.group(1), linha.strip()))
            if RE_RAW.search(linha) and any(t in linha for t in TABELAS_SCOPED):
                if 'tenant_id' not in _contexto(linhas, i):
                    achados.append((path, i + 1, 'SQL cru', linha.strip()))
    return achados


def main():
    achados = auditar()
    out = ['# AUDITORIA-QUERIES — Etapa 3.4 (queries órfãs de filtro de tenant)',
           '',
           'Gerado por `python scripts/audit_queries.py`. Toda query em tabela',
           'com `tenant_id` deve filtrar por tenant (ou usar `get_scoped*`).',
           '']
    if not achados:
        out.append('**Nenhuma query órfã encontrada.** Todas as consultas a tabelas')
        out.append('tenant-scoped passam por filtro de tenant ou helpers escopados.')
    else:
        out.append(f'**{len(achados)} achado(s):**')
        out.append('')
        out.append('| Arquivo:linha | Modelo/tipo | Trecho | Correção proposta |')
        out.append('|---|---|---|---|')
        for path, ln, modelo, trecho in achados:
            trecho = trecho.replace('|', '\\|')[:90]
            out.append(f'| `{path}:{ln}` | {modelo} | `{trecho}` | '
                       f'adicionar filtro `tenant_id=current_tenant_id()` ou usar get_scoped* |')
    os.makedirs('docs', exist_ok=True)
    open('docs/AUDITORIA-QUERIES.md', 'w').write('\n'.join(out) + '\n')
    print(f'{len(achados)} achado(s) — relatório em docs/AUDITORIA-QUERIES.md')
    for path, ln, modelo, trecho in achados:
        print(f'  {path}:{ln} [{modelo}] {trecho[:80]}')
    if '--check' in sys.argv and achados:
        sys.exit(1)


if __name__ == '__main__':
    main()
