"""
Trails + Onboarding endpoints
"""
from flask import Blueprint, jsonify, session, request
from extensions import db
from models import Trail, TrailCourse, UserTrail, OnboardingAnswer, User, UserPoints, Badge, UserBadge, Progress

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
    up = UserPoints.query.filter_by(user_id=user_id).first()
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
    badge = Badge.query.filter_by(code=code).first()
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


def _annotate_trail_progress(trail, user_id, progress_map=None):
    """Return trail dict with per-course done/current/locked states."""
    if progress_map is None:
        progress_map = {p.course_id: p for p in Progress.query.filter_by(user_id=user_id).all()}

    trail_dict = trail.to_dict(include_courses=True)
    first_undone = None
    for tc in trail_dict['courses']:
        prog = progress_map.get(tc['course_id'])
        done = bool(prog and prog.material_done and prog.quiz_total > 0
                    and prog.quiz_score >= prog.quiz_total * 0.6)
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
    progress_map = {p.course_id: p for p in Progress.query.filter_by(user_id=user.id).all()}

    in_progress, completed = [], []
    for ut in enrollments:
        if not ut.trail:
            continue
        td = _annotate_trail_progress(ut.trail, user.id, progress_map)
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
    progress_map = {
        p.course_id: p for p in Progress.query.filter_by(user_id=user.id).all()
    }

    first_undone = None
    for tc in trail_dict['courses']:
        cid = tc['course_id']
        prog = progress_map.get(cid)
        done = bool(prog and prog.material_done and prog.quiz_total > 0 and prog.quiz_score >= prog.quiz_total * 0.6)
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
