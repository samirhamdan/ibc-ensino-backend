"""
Profile-specific dashboard routes: admin, tutor, aluno, aluno-externo
"""
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, session, request
from extensions import db
from core.tenancy import current_tenant_id, role_no_tenant
from core.tenancy.models import TenantUser
from models import (User, Course, Module, Question, LessonProgress,
                    Badge, UserBadge, UserPoints, ActivityFeed)

dashboards_bp = Blueprint('dashboards', __name__)


def time_ago_pt(dt):
    """Human-readable Portuguese relative time, e.g. 'há 3 horas'."""
    if not dt:
        return ''
    now = datetime.utcnow()
    delta = now - dt
    seconds = delta.total_seconds()
    if seconds < 60:
        return 'agora mesmo'
    minutes = int(seconds // 60)
    if minutes < 60:
        return f'há {minutes} minuto{"s" if minutes != 1 else ""}'
    hours = int(seconds // 3600)
    if hours < 24:
        return f'há {hours} hora{"s" if hours != 1 else ""}'
    days = int(seconds // 86400)
    if days < 30:
        return f'há {days} dia{"s" if days != 1 else ""}'
    months = int(days // 30)
    if months < 12:
        return f'há {months} mês' if months == 1 else f'há {months} meses'
    years = int(days // 365)
    return f'há {years} ano{"s" if years != 1 else ""}'

LEVEL_NAMES = {
    1: 'Iniciante', 2: 'Aprendiz', 3: 'Estudioso', 4: 'Conhecedor',
    5: 'Mestre', 6: 'Especialista', 7: 'Guru',
}

TESTIMONIALS = [
    {'author': 'Maria', 'location': 'SP', 'text': 'Transformou minha vida!'},
    {'author': 'João', 'location': 'RJ', 'text': 'Muito bem estruturado'},
    {'author': 'Pedro', 'location': 'MG', 'text': 'Recomendo!'},
]


def _current_user():
    uid = session.get('user_id')
    if uid:
        return User.query.get(uid)
    return None


def _completed_pct(course, user_id):
    modules = Module.query.filter_by(tenant_id=current_tenant_id(), course_id=course.id).all()
    if not modules:
        return 0
    progresses = {p.module_id: p for p in
                  LessonProgress.query.filter_by(user_id=user_id, course_id=course.id, tenant_id=current_tenant_id()).all()}
    passed = sum(1 for m in modules if progresses.get(m.id) and progresses[m.id].passed)
    return round(passed / len(modules) * 100)


# ── Admin ────────────────────────────────────────────────────────────────

@dashboards_bp.route('/admin/dashboard', methods=['GET'])
def admin_dashboard():
    user = _current_user()
    if not user or role_no_tenant(user) != 'admin':
        return jsonify({'error': 'Acesso negado'}), 403

    # Contagem por papel EFETIVO no tenant (tenant_users.papel), não por
    # User.role global — antes contava usuários de TODOS os tenants juntos.
    contagem_papeis = dict(
        db.session.query(TenantUser.papel, db.func.count(TenantUser.user_id))
        .filter_by(tenant_id=current_tenant_id())
        .group_by(TenantUser.papel).all()
    )
    alunos = contagem_papeis.get('aluno', 0)
    tutores = contagem_papeis.get('tutor', 0)
    admins = contagem_papeis.get('admin', 0)
    total_users = alunos + tutores + admins

    total_courses = Course.query.filter_by(tenant_id=current_tenant_id()).count()

    all_progress = LessonProgress.query.filter_by(tenant_id=current_tenant_id()).all()
    completion_rate = round(sum(1 for p in all_progress if p.passed) / len(all_progress) * 100, 1) if all_progress else 0.0

    week_ago = datetime.utcnow() - timedelta(days=7)
    # Novos vínculos neste tenant nos últimos 7 dias (não novas contas
    # globais — um usuário pode ser antigo em outro tenant e novo aqui).
    new_users_7d = TenantUser.query.filter(
        TenantUser.tenant_id == current_tenant_id(),
        TenantUser.criado_em >= week_ago).count()

    weekly_stats = []
    for i in range(6, -1, -1):
        day = (datetime.utcnow() - timedelta(days=i)).date()
        signups = TenantUser.query.filter(
            TenantUser.tenant_id == current_tenant_id(),
            db.func.date(TenantUser.criado_em) == day).count()
        weekly_stats.append({'day': day.strftime('%d/%m'), 'logins': signups, 'signups': signups})

    user_distribution = {
        'alunos': round(alunos / total_users * 100) if total_users else 0,
        'tutores': round(tutores / total_users * 100) if total_users else 0,
        'admins': round(admins / total_users * 100) if total_users else 0,
    }

    alerts = []
    for course in Course.query.filter_by(tenant_id=current_tenant_id()).all():
        modules = Module.query.filter_by(tenant_id=current_tenant_id(), course_id=course.id).all()
        if not modules:
            continue
        students = db.session.query(LessonProgress.user_id).filter_by(course_id=course.id).distinct().count()
        completed = sum(1 for uid, in db.session.query(LessonProgress.user_id).filter_by(course_id=course.id).distinct()
                        if _completed_pct(course, uid) == 100)
        if students >= 3:
            dropout = round((students - completed) / students * 100)
            if dropout >= 35:
                alerts.append({'type': 'dropout', 'message': f'Curso "{course.name}" com {dropout}% abandono (ALTO!)', 'severity': 'high'})
    if new_users_7d:
        alerts.append({'type': 'signup', 'message': f'{new_users_7d} novos alunos inscritos nos últimos 7 dias', 'severity': 'info'})
    if not alerts:
        alerts.append({'type': 'ok', 'message': 'Nenhum alerta no momento. Tudo funcionando bem! ✅', 'severity': 'info'})

    recent_activities = []
    for q in Question.query.filter_by(tenant_id=current_tenant_id()).order_by(Question.created_at.desc()).limit(3).all():
        recent_activities.append({'user': q.author.name if q.author else '—', 'action': f'fez uma pergunta em "{q.course.name if q.course else ""}"', 'timestamp': q.created_at.isoformat()})
    for p in LessonProgress.query.filter_by(passed=True, tenant_id=current_tenant_id()).order_by(LessonProgress.completed_at.desc()).limit(3).all():
        recent_activities.append({'user': p.user.name if p.user else '—', 'action': f'concluiu uma aula em "{p.course.name if p.course else ""}"', 'timestamp': p.completed_at.isoformat() if p.completed_at else ''})
    recent_activities.sort(key=lambda a: a['timestamp'], reverse=True)
    recent_activities = recent_activities[:6]

    return jsonify({
        'total_users': {'alunos': alunos, 'tutores': tutores, 'admins': admins, 'total': total_users},
        'total_courses': total_courses,
        'completion_rate': completion_rate,
        'new_users_7d': new_users_7d,
        'weekly_stats': weekly_stats,
        'user_distribution': user_distribution,
        'alerts': alerts,
        'recent_activities': recent_activities,
    }), 200


# ── Tutor ────────────────────────────────────────────────────────────────

@dashboards_bp.route('/tutor/dashboard', methods=['GET'])
def tutor_dashboard():
    user = _current_user()
    if not user or role_no_tenant(user) not in ('tutor', 'admin'):
        return jsonify({'error': 'Acesso negado'}), 403

    my_courses_q = Course.query if role_no_tenant(user) == 'admin' else Course.query.filter_by(tenant_id=current_tenant_id(), tutor_id=user.id)
    my_courses_list = my_courses_q.all()
    course_ids = [c.id for c in my_courses_list]

    pending = Question.query.filter(Question.tenant_id == current_tenant_id(), Question.course_id.in_(course_ids), Question.resposta == '') \
        .order_by(Question.created_at.asc()).limit(10).all()
    pending_questions = [{
        'id': q.id, 'author': q.author.name if q.author else '—', 'text': q.texto,
        'course': q.course.name if q.course else '', 'timestamp': q.created_at.isoformat(),
    } for q in pending]

    my_courses = []
    for c in my_courses_list:
        modules = Module.query.filter_by(tenant_id=current_tenant_id(), course_id=c.id).all()
        student_ids = [uid for uid, in db.session.query(LessonProgress.user_id).filter_by(course_id=c.id).distinct()]
        completed = sum(1 for uid in student_ids if modules and _completed_pct(c, uid) == 100)
        rate = round(completed / len(student_ids) * 100) if student_ids else 0
        my_courses.append({
            'id': c.id, 'name': c.name, 'icon': c.icon,
            'students': len(student_ids), 'completed': completed, 'completion_rate': rate,
            'alerts': [] if rate >= 50 or not student_ids else [f'Atenção: taxa de conclusão baixa ({rate}%)'],
        })

    week_ago = datetime.utcnow() - timedelta(days=7)
    new_questions = Question.query.filter(Question.tenant_id == current_tenant_id(), Question.course_id.in_(course_ids), Question.created_at >= week_ago).count()
    answered = Question.query.filter(Question.tenant_id == current_tenant_id(), Question.course_id.in_(course_ids), Question.created_at >= week_ago, Question.resposta != '').count()
    # Novos vínculos de aluno NESTE tenant — não contas globais criadas em
    # qualquer tenant (antes vazava a contagem de todos os tenants juntos).
    new_students = TenantUser.query.filter(
        TenantUser.tenant_id == current_tenant_id(),
        TenantUser.papel == 'aluno',
        TenantUser.criado_em >= week_ago).count()

    return jsonify({
        'pending_questions': pending_questions,
        'my_courses': my_courses,
        'weekly_activity': {'new_questions': new_questions, 'answered': answered, 'new_students': new_students},
        'upcoming_tasks': [],
    }), 200


# ── Aluno (interno) ──────────────────────────────────────────────────────

@dashboards_bp.route('/aluno/dashboard', methods=['GET'])
def aluno_dashboard():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    from routes.gamification import streak_efetivo

    up = UserPoints.query.filter_by(user_id=user.id, tenant_id=current_tenant_id()).first()
    # streak_efetivo reinterpreta current_streak na LEITURA: a linha só é
    # zerada de verdade no próximo login (lazy reset) — sem isto, um
    # streak morto há semanas ainda aparecia "vencendo hoje".
    streak_exibido, streak_em_risco = streak_efetivo(up)
    user_stats = {
        'level': up.current_level if up else 1,
        'level_name': LEVEL_NAMES.get(up.current_level if up else 1, ''),
        'total_points': up.total_points if up else 0,
        'points_in_level': up.points_in_level if up else 0,
        'current_streak': streak_exibido,
        'longest_streak': up.longest_streak if up else 0,
        'streak_em_risco': streak_em_risco,
    }

    user_badges = UserBadge.query.filter_by(user_id=user.id, tenant_id=current_tenant_id()).order_by(UserBadge.unlocked_at.desc()).all()
    trofeus_unlocked = [{'icon': ub.badge.icon, 'name': ub.badge.name,
                         'date': ub.unlocked_at.isoformat() + 'Z'} for ub in user_badges]

    enrolled_courses = []
    for c in Course.query.filter_by(tenant_id=current_tenant_id()).all():
        modules = Module.query.filter_by(tenant_id=current_tenant_id(), course_id=c.id).order_by(Module.position).all()
        progresses = {p.module_id: p for p in LessonProgress.query.filter_by(user_id=user.id, course_id=c.id, tenant_id=current_tenant_id()).all()}
        if not progresses or not modules:
            continue
        passed_count = sum(1 for m in modules if progresses.get(m.id) and progresses[m.id].passed)
        pct = round(passed_count / len(modules) * 100) if modules else 0
        aula_atual = min(passed_count + 1, len(modules))
        enrolled_courses.append({
            'id': c.id, 'name': c.name, 'icon': c.icon,
            'aula_atual': aula_atual, 'total_aulas': len(modules), 'percentage': pct,
            'status': 'concluido' if pct == 100 else 'em_andamento',
        })

    in_progress_course = next((c for c in enrolled_courses if c['status'] == 'em_andamento'), None)
    other_courses = [c for c in enrolled_courses if c is not in_progress_course]
    not_enrolled = [c for c in Course.query.filter_by(tenant_id=current_tenant_id()).all() if c.id not in {ec['id'] for ec in enrolled_courses}]
    for c in not_enrolled[:4]:
        other_courses.append({'id': c.id, 'name': c.name, 'icon': c.icon, 'status': 'nao_iniciado'})

    next_metas = []
    if in_progress_course:
        next_metas.append({'description': f"Continue \"{in_progress_course['name']}\" — Aula {in_progress_course['aula_atual']}/{in_progress_course['total_aulas']}", 'type': 'curso'})
    if up and up.current_level < 7:
        falta = 100 - up.points_in_level
        next_metas.append({'description': f'+{falta} pontos para o próximo nível', 'type': 'xp'})
    locked_badges = Badge.query.filter(Badge.tenant_id == current_tenant_id(),
                                       ~Badge.id.in_([ub.badge_id for ub in user_badges])).limit(2).all()
    for b in locked_badges:
        next_metas.append({'description': f'Conquistar "{b.name}"', 'type': 'trofeu'})
    pending_q = Question.query.filter_by(tenant_id=current_tenant_id(), user_id=user.id, resposta='').count()
    if pending_q:
        next_metas.append({'description': f'Você tem {pending_q} pergunta(s) aguardando resposta', 'type': 'duvida'})

    return jsonify({
        'user_stats': user_stats,
        'trofeus_count': len(trofeus_unlocked),
        'trofeus_unlocked': trofeus_unlocked[:8],
        'in_progress_course': in_progress_course,
        'next_metas': next_metas[:5],
        'recent_trofeus': trofeus_unlocked[:3],
        'other_courses': other_courses[:6],
    }), 200


# ── Aluno dashboard ────────────────────────────────────────────

@dashboards_bp.route('/aluno-externo/dashboard', methods=['GET'])
def aluno_externo_dashboard():
    user = _current_user()

    user_stats = None
    in_progress = None
    trofeus_unlocked = []
    if user:
        up = UserPoints.query.filter_by(user_id=user.id, tenant_id=current_tenant_id()).first()
        user_stats = {
            'level': up.current_level if up else 1,
            'level_name': LEVEL_NAMES.get(up.current_level if up else 1, ''),
            'total_points': up.total_points if up else 0,
            'points_in_level': up.points_in_level if up else 0,
        }
        user_badges = UserBadge.query.filter_by(user_id=user.id, tenant_id=current_tenant_id()).order_by(UserBadge.unlocked_at.desc()).all()
        trofeus_unlocked = [{'icon': ub.badge.icon, 'name': ub.badge.name, 'description': ub.badge.description, 'date': ub.unlocked_at.isoformat()} for ub in user_badges]

        for c in Course.query.filter_by(tenant_id=current_tenant_id(), acesso='publico').all():
            modules = Module.query.filter_by(tenant_id=current_tenant_id(), course_id=c.id).order_by(Module.position).all()
            progresses = {p.module_id: p for p in LessonProgress.query.filter_by(user_id=user.id, course_id=c.id, tenant_id=current_tenant_id()).all()}
            if not progresses or not modules:
                continue
            passed_count = sum(1 for m in modules if progresses.get(m.id) and progresses[m.id].passed)
            pct = round(passed_count / len(modules) * 100)
            if pct < 100:
                in_progress = {'id': c.id, 'name': c.name, 'icon': c.icon,
                               'aula': min(passed_count + 1, len(modules)), 'total': len(modules), 'percentage': pct}
                break

    featured_courses = []
    for c in Course.query.filter_by(tenant_id=current_tenant_id(), acesso='publico').limit(4).all():
        n_modules = Module.query.filter_by(tenant_id=current_tenant_id(), course_id=c.id).count()
        featured_courses.append({
            'id': c.id, 'name': c.name, 'icon': c.icon, 'category': c.category_rel.name if c.category_rel else '',
            'rating': 4.8, 'review_count': 50 + c.id * 37, 'lessons': n_modules,
        })

    # "Comunidade" é a comunidade DESTE tenant — contagem global vazava o
    # tamanho da base de outros tenants para qualquer aluno autenticado.
    total_users = TenantUser.query.filter_by(tenant_id=current_tenant_id()).count()
    total_courses = Course.query.filter_by(tenant_id=current_tenant_id()).count()
    all_progress = LessonProgress.query.filter_by(tenant_id=current_tenant_id()).all()
    completion_rate = round(sum(1 for p in all_progress if p.passed) / len(all_progress) * 100) if all_progress else 0

    return jsonify({
        'user_stats': user_stats,
        'trofeus_count': len(trofeus_unlocked),
        'trofeus_unlocked': trofeus_unlocked[:5],
        'in_progress': in_progress,
        'featured_courses': featured_courses,
        'community_stats': {
            'total_users': total_users, 'total_courses': total_courses,
            'completion_rate': completion_rate, 'avg_rating': 4.8,
        },
        'testimonials': TESTIMONIALS,
    }), 200


# ── Activity Feed ("Mural de Conclusões" — Sprint 6.2) ──────────────────────

@dashboards_bp.route('/activity-feed', methods=['GET'])
def activity_feed():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    try:
        limit = int(request.args.get('limit', 10))
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(limit, 50))

    items = (ActivityFeed.query
             .filter_by(tenant_id=current_tenant_id())
             .order_by(ActivityFeed.created_at.desc())
             .limit(limit)
             .all())

    result = []
    for item in items:
        u = item.user
        c = item.course
        name = u.name if u else ''
        result.append({
            'id': item.id,
            'user_name': name,
            'user_initial': name[:1].upper() if name else '?',
            'course_name': c.name if c else '',
            'action': item.action,
            'created_at': item.created_at.isoformat() if item.created_at else None,
            'time_ago': time_ago_pt(item.created_at),
        })

    return jsonify(result), 200
