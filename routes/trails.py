"""
Trails + Onboarding endpoints
"""
from flask import Blueprint, jsonify, session, request
from extensions import db
from core.tenancy import current_tenant_id
from models import Trail, TrailCourse, UserTrail, OnboardingAnswer, User, UserPoints, Badge, UserBadge, Module, LessonProgress

trails_bp = Blueprint('trails', __name__)
onboarding_bp = Blueprint('onboarding', __name__)

GOAL_TO_TRAIL = {
    'evangelismo': 'evangelismo',
    'discipulado': 'discipulado',
    'teologia': 'teologia',
    'servico': 'servico',
}


def _current_user():
    uid = session.get('user_id')
    return User.query.get(uid) if uid else None


def _add_xp(user_id, points):
    up = UserPoints.query.filter_by(user_id=user_id, tenant_id=current_tenant_id()).first()
    if not up:
        up = UserPoints(user_id=user_id, total_points=0, current_level=1, points_in_level=0)
        db.session.add(up)
    up.total_points += points
    up.points_in_level += points
    level_threshold = up.current_level * 100
    if up.points_in_level >= level_threshold:
        up.points_in_level -= level_threshold
        up.current_level += 1


def _award_badge(user_id, code):
    badge = Badge.query.filter_by(code=code, tenant_id=current_tenant_id()).first()
    if not badge:
        return None
    existing = UserBadge.query.filter_by(user_id=user_id, badge_id=badge.id).first()
    if existing:
        return None
    db.session.add(UserBadge(user_id=user_id, badge_id=badge.id))
    return badge


# ── Trail endpoints ──────────────────────────────────────

@trails_bp.route('', methods=['GET'])
def list_trails():
    trails = Trail.query.all()
    return jsonify([t.to_dict(include_courses=True) for t in trails])


@trails_bp.route('/<int:trail_id>/enroll', methods=['POST'])
def enroll_trail(trail_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    trail = Trail.query.get_or_404(trail_id)

    existing = UserTrail.query.filter_by(user_id=user.id, trail_id=trail_id).first()
    already = bool(existing)
    if not existing:
        db.session.add(UserTrail(user_id=user.id, trail_id=trail_id))

    # enrolling makes this the focused trail
    user.active_trail_id = trail_id
    db.session.commit()

    return jsonify({'ok': True, 'already_enrolled': already,
                    'trail': trail.to_dict(include_courses=True)})


@trails_bp.route('/<int:trail_id>/focus', methods=['POST'])
def focus_trail(trail_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    enrolled = UserTrail.query.filter_by(user_id=user.id, trail_id=trail_id).first()
    if not enrolled:
        return jsonify({'error': 'Você não está inscrito nesta trilha'}), 400

    user.active_trail_id = trail_id
    db.session.commit()
    return jsonify({'ok': True, 'focused_trail_id': trail_id})


def _completed_course_ids(user_id):
    """Ids de curso 100% concluídos pelo usuário (todos os módulos com
    LessonProgress.passed=True). Substitui o antigo cálculo baseado no modelo
    legado `Progress` — routes/progress.py não é mais usado pelo frontend, então
    `Progress` fica sempre vazio e a conclusão de trilha nunca disparava
    (bug crítico do ROADMAP.md, seção 1.2)."""
    modules_by_course = {}
    for m in Module.query.all():
        modules_by_course.setdefault(m.course_id, []).append(m.id)

    passed_module_ids = {
        lp.module_id for lp in LessonProgress.query.filter_by(user_id=user_id, passed=True).all()
    }

    done_ids = set()
    for cid, module_ids in modules_by_course.items():
        if module_ids and all(mid in passed_module_ids for mid in module_ids):
            done_ids.add(cid)
    return done_ids


def _annotate_trail_progress(trail, user_id, done_course_ids=None):
    """Return trail dict with per-course done/current/locked states."""
    if done_course_ids is None:
        done_course_ids = _completed_course_ids(user_id)

    trail_dict = trail.to_dict(include_courses=True)
    first_undone = None
    for tc in trail_dict['courses']:
        done = tc['course_id'] in done_course_ids
        tc['done'] = done
        if not done and first_undone is None:
            first_undone = tc['course_id']
    for tc in trail_dict['courses']:
        if tc['done']:
            tc['state'] = 'done'
        elif tc['course_id'] == first_undone:
            tc['state'] = 'current'
        else:
            tc['state'] = 'locked'

    trail_dict['current_course_id'] = first_undone
    done_count = sum(1 for tc in trail_dict['courses'] if tc['done'])
    total = len(trail_dict['courses'])
    trail_dict['done_count'] = done_count
    trail_dict['total_courses'] = total
    trail_dict['percentage'] = round(done_count / total * 100) if total else 0
    trail_dict['completed'] = total > 0 and done_count == total
    return trail_dict


@trails_bp.route('/my', methods=['GET'])
def my_trails():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    enrollments = UserTrail.query.filter_by(user_id=user.id).all()
    done_course_ids = _completed_course_ids(user.id)

    in_progress, completed = [], []
    for ut in enrollments:
        if not ut.trail:
            continue
        td = _annotate_trail_progress(ut.trail, user.id, done_course_ids)
        td['enrolled_at'] = ut.enrolled_at.isoformat()
        if ut.completed_at or td['completed']:
            td['completed_at'] = ut.completed_at.isoformat() if ut.completed_at else None
            completed.append(td)
        else:
            in_progress.append(td)

    return jsonify({
        'in_progress': in_progress,
        'completed': completed,
        'focused_trail_id': user.active_trail_id,
    })


@trails_bp.route('/active', methods=['GET'])
def active_trail():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    if not user.active_trail_id:
        return jsonify(None)

    trail = Trail.query.get(user.active_trail_id)
    if not trail:
        return jsonify(None)

    trail_dict = trail.to_dict(include_courses=True)

    # annotate each course with state: done | current | locked
    done_course_ids = _completed_course_ids(user.id)

    first_undone = None
    for tc in trail_dict['courses']:
        cid = tc['course_id']
        done = cid in done_course_ids
        tc['done'] = done
        if not done and first_undone is None:
            first_undone = cid

    for tc in trail_dict['courses']:
        cid = tc['course_id']
        if tc['done']:
            tc['state'] = 'done'
        elif cid == first_undone:
            tc['state'] = 'current'
        else:
            tc['state'] = 'locked'

    trail_dict['current_course_id'] = first_undone

    # check trail completion
    all_done = all(tc['done'] for tc in trail_dict['courses'])
    trail_dict['completed'] = all_done
    if all_done:
        ut = UserTrail.query.filter_by(user_id=user.id, trail_id=trail.id).first()
        if ut and not ut.completed_at:
            from datetime import datetime
            ut.completed_at = datetime.utcnow()
            _add_xp(user.id, trail.xp_bonus)
            awarded_badge = None
            if trail.badge_code:
                awarded_badge = _award_badge(user.id, trail.badge_code)
            db.session.commit()
            if awarded_badge:
                trail_dict['new_badge'] = awarded_badge.to_dict()
                trail_dict['xp_bonus'] = trail.xp_bonus

    return jsonify(trail_dict)


# ── Onboarding endpoints ─────────────────────────────────

@onboarding_bp.route('/status', methods=['GET'])
def onboarding_status():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401
    return jsonify({'completed': user.onboarding_completed})


@onboarding_bp.route('', methods=['POST'])
def submit_onboarding():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    data = request.get_json(silent=True) or {}
    goal = data.get('goal', '')

    trail = Trail.query.filter_by(goal=goal).first()

    existing = OnboardingAnswer.query.filter_by(user_id=user.id).first()
    if existing:
        existing.goal = goal
        existing.recommended_trail_id = trail.id if trail else None
    else:
        db.session.add(OnboardingAnswer(
            user_id=user.id,
            goal=goal,
            recommended_trail_id=trail.id if trail else None,
        ))

    user.onboarding_completed = True
    db.session.commit()

    return jsonify({
        'ok': True,
        'recommended_trail': trail.to_dict(include_courses=True) if trail else None,
    })


# ═══════════════════════════════════════════════════════════════
# ADMIN: Trails management (Sprint 4)
# ═══════════════════════════════════════════════════════════════

def _admin_required():
    uid = session.get('user_id')
    user = User.query.get(uid) if uid else None
    if not user or user.role != 'admin':
        return None, (jsonify({'error': 'Acesso negado'}), 403)
    return user, None

@trails_bp.route('/admin/trails', methods=['GET'])
def admin_list_trails():
    user, err = _admin_required()
    if err: return err
    from models import Course
    trails = Trail.query.all()
    result = []
    for t in trails:
        trail_courses = TrailCourse.query.filter_by(trail_id=t.id).order_by(TrailCourse.position).all()
        enrolled = UserTrail.query.filter_by(trail_id=t.id).count()
        completed = UserTrail.query.filter_by(trail_id=t.id).filter(UserTrail.completed_at.isnot(None)).count()
        courses_data = []
        for tc in trail_courses:
            c = Course.query.get(tc.course_id)
            if c:
                courses_data.append({'id': c.id, 'name': c.name, 'position': tc.position})
        result.append({
            'id': t.id, 'name': t.name, 'icon': t.icon or 'trails',
            'color': t.color or '#008ea8', 'description': t.description or '',
            'xp_bonus': t.xp_bonus or 0, 'certificate_name': t.certificate_name or '',
            'total_courses': len(trail_courses), 'enrolled_users': enrolled,
            'completed_users': completed, 'courses': courses_data
        })
    return jsonify({'trails': result})

@trails_bp.route('/admin/trails/<int:trail_id>', methods=['PUT'])
def admin_update_trail(trail_id):
    user, err = _admin_required()
    if err: return err
    t = Trail.query.get_or_404(trail_id)
    data = request.get_json() or {}
    if 'name' in data: t.name = data['name']
    if 'description' in data: t.description = data['description']
    if 'icon' in data: t.icon = data['icon']
    if 'color' in data: t.color = data['color']
    if 'xp_bonus' in data:
        try:
            t.xp_bonus = int(data['xp_bonus'])
        except (TypeError, ValueError):
            return jsonify({'error': 'xp_bonus deve ser um número'}), 400
    if 'certificate_name' in data: t.certificate_name = data['certificate_name']
    db.session.commit()
    return jsonify({'success': True})

@trails_bp.route('/admin/trails/<int:trail_id>/courses/reorder', methods=['PUT'])
def admin_reorder_trail_courses(trail_id):
    user, err = _admin_required()
    if err: return err
    data = request.get_json() or {}
    course_ids = data.get('course_ids', [])
    for idx, cid in enumerate(course_ids, 1):
        tc = TrailCourse.query.filter_by(trail_id=trail_id, course_id=cid).first()
        if tc:
            tc.position = idx
    db.session.commit()
    return jsonify({'success': True})

@trails_bp.route('/admin/trails/<int:trail_id>/courses', methods=['POST'])
def admin_add_course_to_trail(trail_id):
    user, err = _admin_required()
    if err: return err
    data = request.get_json() or {}
    course_id = data.get('course_id')
    if not course_id:
        return jsonify({'error': 'course_id required'}), 400
    existing = TrailCourse.query.filter_by(trail_id=trail_id, course_id=course_id).first()
    if existing:
        return jsonify({'error': 'Curso já na trilha'}), 409
    max_pos = db.session.query(db.func.max(TrailCourse.position)).filter_by(trail_id=trail_id).scalar() or 0
    tc = TrailCourse(trail_id=trail_id, course_id=course_id, position=max_pos + 1)
    db.session.add(tc)
    db.session.commit()
    return jsonify({'success': True})

@trails_bp.route('/admin/trails/<int:trail_id>/courses/<int:course_id>', methods=['DELETE'])
def admin_remove_course_from_trail(trail_id, course_id):
    user, err = _admin_required()
    if err: return err
    tc = TrailCourse.query.filter_by(trail_id=trail_id, course_id=course_id).first()
    if tc:
        db.session.delete(tc)
        db.session.commit()
    return jsonify({'success': True})

@trails_bp.route('/admin/courses/available-for-trail/<int:trail_id>', methods=['GET'])
def admin_available_courses_for_trail(trail_id):
    user, err = _admin_required()
    if err: return err
    from models import Course
    trail_course_ids = {tc.course_id for tc in TrailCourse.query.filter_by(trail_id=trail_id).all()}
    all_courses = Course.query.all()
    available = [{'id': c.id, 'name': c.name} for c in all_courses if c.id not in trail_course_ids]
    return jsonify({'courses': available})



@trails_bp.route('', methods=['POST'])
def create_trail():
    uid = session.get('user_id')
    user = User.query.get(uid) if uid else None
    if not user or user.role != 'admin':
        return jsonify({'error': 'Acesso negado'}), 403
    
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name é obrigatório'}), 400
    
    try:
        xp_bonus = int(data.get('xp_bonus', 100))
    except (TypeError, ValueError):
        return jsonify({'error': 'xp_bonus deve ser um número'}), 400

    t = Trail(
        name=name,
        description=data.get('description', ''),
        xp_bonus=xp_bonus,
        color=data.get('color', '#008ea8')
    )
    db.session.add(t)
    db.session.commit()
    return jsonify({'id': t.id, 'name': t.name}), 201
