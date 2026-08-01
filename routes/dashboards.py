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


def _batch_completion(tenant_id, course_ids=None, user_ids=None):
    """Batch completion stats: {(course_id, user_id): pct}.

    2 queries total regardless of course/user count:
    one for module counts per course, one for passed counts per (course, user).
    """
    mod_q = db.session.query(Module.course_id, db.func.count(Module.id)) \
        .filter_by(tenant_id=tenant_id)
    if course_ids:
        mod_q = mod_q.filter(Module.course_id.in_(course_ids))
    mod_counts = dict(mod_q.group_by(Module.course_id).all())

    prog_q = db.session.query(
        LessonProgress.course_id, LessonProgress.user_id,
        db.func.count(LessonProgress.id)
    ).filter(
        LessonProgress.tenant_id == tenant_id,
        LessonProgress.passed.is_(True),
    )
    if course_ids:
        prog_q = prog_q.filter(LessonProgress.course_id.in_(course_ids))
    if user_ids:
        prog_q = prog_q.filter(LessonProgress.user_id.in_(user_ids))
    passed_counts = {(cid, uid): cnt for cid, uid, cnt in
                     prog_q.group_by(LessonProgress.course_id, LessonProgress.user_id).all()}

    result = {}
    for (cid, uid), passed in passed_counts.items():
        total = mod_counts.get(cid, 0)
        result[(cid, uid)] = round(passed / total * 100) if total else 0
    return result, mod_counts


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

    total_lp = LessonProgress.query.filter_by(tenant_id=current_tenant_id()).count()
    passed_lp = LessonProgress.query.filter_by(tenant_id=current_tenant_id(), passed=True).count()
    completion_rate = round(passed_lp / total_lp * 100, 1) if total_lp else 0.0

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

    # ── Pulso: sparklines de 8 semanas ──
    tid = current_tenant_id()
    pulso_weeks = []
    now = datetime.utcnow()
    for w in range(7, -1, -1):
        week_end = now - timedelta(weeks=w)
        week_start = week_end - timedelta(days=7)
        active = db.session.query(db.func.count(db.func.distinct(LessonProgress.user_id))).filter(
            LessonProgress.tenant_id == tid,
            LessonProgress.completed_at >= week_start,
            LessonProgress.completed_at < week_end).scalar() or 0
        completions = LessonProgress.query.filter(
            LessonProgress.tenant_id == tid,
            LessonProgress.passed == True,
            LessonProgress.completed_at >= week_start,
            LessonProgress.completed_at < week_end).count()
        signups_w = TenantUser.query.filter(
            TenantUser.tenant_id == tid,
            TenantUser.criado_em >= week_start,
            TenantUser.criado_em < week_end).count()
        pulso_weeks.append({
            'label': week_end.strftime('%d/%m'),
            'active': active,
            'completions': completions,
            'signups': signups_w,
        })

    this_week = pulso_weeks[-1] if pulso_weeks else {}
    prev_week = pulso_weeks[-2] if len(pulso_weeks) >= 2 else {}
    enrolled_total = alunos
    engagement_rate = round(this_week.get('active', 0) / enrolled_total * 100) if enrolled_total else 0

    pulso = {
        'alunos_ativos_7d': this_week.get('active', 0),
        'alunos_ativos_prev': prev_week.get('active', 0),
        'conclusoes_semana': this_week.get('completions', 0),
        'conclusoes_prev': prev_week.get('completions', 0),
        'engajamento_pct': engagement_rate,
        'engajamento_prev': round(prev_week.get('active', 0) / enrolled_total * 100) if enrolled_total else 0,
        'novos_semana': this_week.get('signups', 0),
        'novos_prev': prev_week.get('signups', 0),
        'sparklines': {
            'active': [w['active'] for w in pulso_weeks],
            'completions': [w['completions'] for w in pulso_weeks],
            'signups': [w['signups'] for w in pulso_weeks],
        },
        'labels': [w['label'] for w in pulso_weeks],
    }

    # ── Fila de Atencao (alerts priorizados com acao) ──
    alerts = []
    all_courses = Course.query.filter_by(tenant_id=tid).all()
    course_map = {c.id: c for c in all_courses}
    course_ids = list(course_map.keys())
    completion, mod_counts = _batch_completion(tid, course_ids=course_ids)
    student_counts = dict(
        db.session.query(LessonProgress.course_id, db.func.count(db.func.distinct(LessonProgress.user_id)))
        .filter(LessonProgress.course_id.in_(course_ids), LessonProgress.tenant_id == tid)
        .group_by(LessonProgress.course_id).all()
    ) if course_ids else {}
    for cid, students in student_counts.items():
        if students < 3:
            continue
        completed = sum(1 for (c2, u2), pct in completion.items() if c2 == cid and pct == 100)
        dropout = round((students - completed) / students * 100)
        if dropout >= 35:
            c = course_map.get(cid)
            alerts.append({
                'type': 'dropout',
                'message': f'Curso "{c.name if c else cid}" com {dropout}% de abandono',
                'severity': 'high',
                'action_label': 'Ver ponto de abandono',
                'action_target': f'courses:{cid}',
            })

    inactive_7d = db.session.query(db.func.count(db.func.distinct(TenantUser.user_id))).filter(
        TenantUser.tenant_id == tid,
        TenantUser.papel == 'aluno',
        ~TenantUser.user_id.in_(
            db.session.query(db.func.distinct(LessonProgress.user_id)).filter(
                LessonProgress.tenant_id == tid,
                LessonProgress.completed_at >= now - timedelta(days=7))
        )
    ).scalar() or 0
    if inactive_7d > 0:
        alerts.append({
            'type': 'inactivity',
            'message': f'{inactive_7d} alunos sem atividade nos ultimos 7 dias',
            'severity': 'warn',
            'action_label': 'Ver alunos',
            'action_target': 'users',
        })

    pending_questions = Question.query.filter(
        Question.tenant_id == tid,
        Question.resposta == '',
        Question.created_at <= now - timedelta(days=5)
    ).count()
    if pending_questions > 0:
        alerts.append({
            'type': 'pending_questions',
            'message': f'{pending_questions} perguntas aguardando resposta ha mais de 5 dias',
            'severity': 'warn',
            'action_label': 'Responder agora',
            'action_target': 'users',
        })

    if new_users_7d:
        alerts.append({
            'type': 'signup',
            'message': f'{new_users_7d} novos alunos inscritos nos ultimos 7 dias',
            'severity': 'info',
            'action_label': 'Ver alunos',
            'action_target': 'users',
        })

    # ── Atividade recente (24h, max 8) ──
    recent_activities = []
    day_ago = now - timedelta(hours=24)
    for q in Question.query.filter(
            Question.tenant_id == tid,
            Question.created_at >= day_ago
    ).order_by(Question.created_at.desc()).limit(4).all():
        recent_activities.append({
            'user': q.author.name if q.author else '',
            'action': f'perguntou em "{q.course.name if q.course else ""}"',
            'type': 'question',
            'timestamp': q.created_at.isoformat(),
        })
    for p in LessonProgress.query.filter(
            LessonProgress.tenant_id == tid,
            LessonProgress.passed == True,
            LessonProgress.completed_at >= day_ago
    ).order_by(LessonProgress.completed_at.desc()).limit(4).all():
        recent_activities.append({
            'user': p.user.name if p.user else '',
            'action': f'concluiu aula em "{p.course.name if p.course else ""}"',
            'type': 'completion',
            'timestamp': p.completed_at.isoformat() if p.completed_at else '',
        })
    recent_activities.sort(key=lambda a: a['timestamp'], reverse=True)
    recent_activities = recent_activities[:8]

    return jsonify({
        'total_users': {'alunos': alunos, 'tutores': tutores, 'admins': admins, 'total': total_users},
        'total_courses': total_courses,
        'completion_rate': completion_rate,
        'new_users_7d': new_users_7d,
        'weekly_stats': weekly_stats,
        'user_distribution': user_distribution,
        'alerts': alerts,
        'recent_activities': recent_activities,
        'pulso': pulso,
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
    tid = current_tenant_id()
    completion_tutor, mod_counts_tutor = _batch_completion(tid, course_ids=course_ids)
    student_counts_tutor = dict(
        db.session.query(LessonProgress.course_id, db.func.count(db.func.distinct(LessonProgress.user_id)))
        .filter(LessonProgress.course_id.in_(course_ids), LessonProgress.tenant_id == tid)
        .group_by(LessonProgress.course_id).all()
    ) if course_ids else {}
    for c in my_courses_list:
        students = student_counts_tutor.get(c.id, 0)
        completed = sum(1 for (c2, u2), pct in completion_tutor.items() if c2 == c.id and pct == 100)
        rate = round(completed / students * 100) if students else 0
        my_courses.append({
            'id': c.id, 'name': c.name, 'icon': c.icon,
            'students': students, 'completed': completed, 'completion_rate': rate,
            'alerts': [] if rate >= 50 or not students else [f'Atenção: taxa de conclusão baixa ({rate}%)'],
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
    tid = current_tenant_id()
    all_courses_aluno = Course.query.filter_by(tenant_id=tid).all()
    course_map_aluno = {c.id: c for c in all_courses_aluno}
    cids_aluno = list(course_map_aluno.keys())
    completion_aluno, mod_counts_aluno = _batch_completion(tid, course_ids=cids_aluno, user_ids=[user.id])
    for cid, c in course_map_aluno.items():
        pct = completion_aluno.get((cid, user.id), 0)
        total = mod_counts_aluno.get(cid, 0)
        if not total or (cid, user.id) not in completion_aluno:
            continue
        passed_count = round(pct * total / 100) if total else 0
        aula_atual = min(passed_count + 1, total)
        enrolled_courses.append({
            'id': c.id, 'name': c.name, 'icon': c.icon,
            'aula_atual': aula_atual, 'total_aulas': total, 'percentage': pct,
            'status': 'concluido' if pct == 100 else 'em_andamento',
        })

    in_progress_course = next((c for c in enrolled_courses if c['status'] == 'em_andamento'), None)
    other_courses = [c for c in enrolled_courses if c is not in_progress_course]
    # status='published': mesmo filtro que list_courses() já aplica pra
    # quem não é admin/tutor — sem isto, um curso em rascunho aparecia no
    # carrossel de recomendações de todo aluno (a fatia cresceu de 4 pra
    # 8 nesta etapa, achado de revisão de segurança).
    not_enrolled = [c for c in Course.query.filter_by(tenant_id=current_tenant_id(), status='published').all()
                    if c.id not in {ec['id'] for ec in enrolled_courses}]
    # Etapa 4 (UX_ALUNO_SAAS.md §3 Grupo 5): ordena por popularidade no
    # tenant — quantos alunos distintos têm QUALQUER progresso no curso.
    # Slot pronto pra LRN-03 (recomendação por learner model, Release
    # 1.0); até lá, popularidade real é melhor que a ordem do id.
    popularidade = dict(
        db.session.query(LessonProgress.course_id, db.func.count(db.func.distinct(LessonProgress.user_id)))
        .filter_by(tenant_id=current_tenant_id())
        .group_by(LessonProgress.course_id).all()
    )
    not_enrolled.sort(key=lambda c: popularidade.get(c.id, 0), reverse=True)
    for c in not_enrolled[:8]:
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

        tid_ext = current_tenant_id()
        pub_courses = Course.query.filter_by(tenant_id=tid_ext, acesso='publico').all()
        pub_cids = [c.id for c in pub_courses]
        comp_ext, mod_ext = _batch_completion(tid_ext, course_ids=pub_cids, user_ids=[user.id])
        for c in pub_courses:
            pct = comp_ext.get((c.id, user.id), 0)
            total = mod_ext.get(c.id, 0)
            if not total or (c.id, user.id) not in comp_ext:
                continue
            if pct < 100:
                passed_n = round(pct * total / 100) if total else 0
                in_progress = {'id': c.id, 'name': c.name, 'icon': c.icon,
                               'aula': min(passed_n + 1, total), 'total': total, 'percentage': pct}
                break

    featured_courses = []
    feat_list = Course.query.filter_by(tenant_id=current_tenant_id(), acesso='publico').limit(4).all()
    feat_cids = [c.id for c in feat_list]
    feat_mod_counts = dict(
        db.session.query(Module.course_id, db.func.count(Module.id))
        .filter(Module.course_id.in_(feat_cids), Module.tenant_id == current_tenant_id())
        .group_by(Module.course_id).all()
    ) if feat_cids else {}
    for c in feat_list:
        featured_courses.append({
            'id': c.id, 'name': c.name, 'icon': c.icon, 'category': c.category_rel.name if c.category_rel else '',
            'rating': 4.8, 'review_count': 50 + c.id * 37, 'lessons': feat_mod_counts.get(c.id, 0),
        })

    # "Comunidade" é a comunidade DESTE tenant — contagem global vazava o
    # tamanho da base de outros tenants para qualquer aluno autenticado.
    total_users = TenantUser.query.filter_by(tenant_id=current_tenant_id()).count()
    total_courses = Course.query.filter_by(tenant_id=current_tenant_id()).count()
    total_lp_ext = LessonProgress.query.filter_by(tenant_id=current_tenant_id()).count()
    passed_lp_ext = LessonProgress.query.filter_by(tenant_id=current_tenant_id(), passed=True).count()
    completion_rate = round(passed_lp_ext / total_lp_ext * 100) if total_lp_ext else 0

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
