"""
Admin-only routes: tutor management, user management, question assignment
"""
from flask import Blueprint, request, jsonify, session
from extensions import db
from models import (
    User, Course, Question, TutorCourse, UserTrail, UserPoints,
    Certificate, Progress, Trail
)
from sqlalchemy import func

admin_bp = Blueprint('admin', __name__)


def _admin_required():
    uid = session.get('user_id')
    user = User.query.get(uid) if uid else None
    if not user or user.role != 'admin':
        return None, (jsonify({'error': 'Acesso negado'}), 403)
    return user, None


# ── Tutors ───────────────────────────────────────────────────────────────────

@admin_bp.route('/tutors', methods=['GET'])
def list_tutors():
    _, err = _admin_required()
    if err:
        return err

    tutors = User.query.filter_by(role='tutor').order_by(User.name).all()
    result = []
    for t in tutors:
        assigned_courses = TutorCourse.query.filter_by(tutor_id=t.id).all()
        course_ids = [tc.course_id for tc in assigned_courses]

        pending = Question.query.filter(
            Question.assigned_tutor_id == t.id,
            Question.resposta == ''
        ).count()
        total_answered = Question.query.filter(
            Question.assigned_tutor_id == t.id,
            Question.resposta != ''
        ).count()

        courses_data = []
        for tc in assigned_courses:
            c = Course.query.get(tc.course_id)
            if c:
                courses_data.append({'id': c.id, 'name': c.name, 'icon': c.icon or ''})

        result.append({
            'id': t.id,
            'name': t.name,
            'email': t.email,
            'assigned_courses': courses_data,
            'pending_questions': pending,
            'total_answered': total_answered,
        })

    return jsonify(result), 200


@admin_bp.route('/tutors/<int:tutor_id>/assign-course', methods=['POST'])
def assign_course_to_tutor(tutor_id):
    _, err = _admin_required()
    if err:
        return err

    tutor = User.query.get_or_404(tutor_id)
    if tutor.role not in ('tutor', 'admin'):
        return jsonify({'error': 'Usuário não é tutor'}), 400

    data = request.get_json(silent=True) or {}
    course_id = data.get('course_id')
    if not course_id:
        return jsonify({'error': 'course_id obrigatório'}), 400

    Course.query.get_or_404(course_id)

    existing = TutorCourse.query.filter_by(tutor_id=tutor_id, course_id=course_id).first()
    if existing:
        return jsonify({'error': 'Curso já atribuído a este tutor'}), 409

    tc = TutorCourse(tutor_id=tutor_id, course_id=course_id)
    db.session.add(tc)
    db.session.commit()
    return jsonify({'ok': True}), 201


@admin_bp.route('/tutors/<int:tutor_id>/assign-course/<int:course_id>', methods=['DELETE'])
def unassign_course_from_tutor(tutor_id, course_id):
    _, err = _admin_required()
    if err:
        return err

    tc = TutorCourse.query.filter_by(tutor_id=tutor_id, course_id=course_id).first_or_404()
    db.session.delete(tc)
    db.session.commit()
    return jsonify({'ok': True}), 200


# ── Questions (admin) ─────────────────────────────────────────────────────────

@admin_bp.route('/questions/unassigned', methods=['GET'])
def list_unassigned_questions():
    _, err = _admin_required()
    if err:
        return err

    questions = Question.query.filter(
        Question.assigned_tutor_id.is_(None),
        Question.resposta == ''
    ).order_by(Question.created_at.asc()).all()

    result = []
    for q in questions:
        d = q.to_dict()
        d['course_name'] = q.course.name if q.course else ''
        d['student_name'] = q.author.name if q.author else ''
        result.append(d)
    return jsonify(result), 200


@admin_bp.route('/questions/<int:question_id>/assign', methods=['POST'])
def assign_question(question_id):
    _, err = _admin_required()
    if err:
        return err

    q = Question.query.get_or_404(question_id)
    data = request.get_json(silent=True) or {}
    tutor_id = data.get('tutor_id')

    if tutor_id:
        tutor = User.query.get_or_404(tutor_id)
        if tutor.role not in ('tutor', 'admin'):
            return jsonify({'error': 'Usuário não é tutor'}), 400
        q.assigned_tutor_id = tutor_id
    else:
        q.assigned_tutor_id = None

    db.session.commit()
    return jsonify(q.to_dict()), 200


@admin_bp.route('/courses/list-simple', methods=['GET'])
def list_courses_simple():
    _, err = _admin_required()
    if err:
        return err

    courses = Course.query.order_by(Course.name).all()
    return jsonify([{'id': c.id, 'name': c.name, 'icon': c.icon or ''} for c in courses]), 200


# ── Users ─────────────────────────────────────────────────────────────────────

@admin_bp.route('/users', methods=['GET'])
def list_users():
    _, err = _admin_required()
    if err:
        return err

    search = (request.args.get('search') or '').strip().lower()
    role_filter = request.args.get('role', '')
    trail_filter = request.args.get('trail', '')

    query = User.query

    if role_filter:
        query = query.filter_by(role=role_filter)

    if trail_filter:
        enrolled_ids = [
            ut.user_id for ut in UserTrail.query.filter_by(trail_id=int(trail_filter)).all()
        ]
        query = query.filter(User.id.in_(enrolled_ids))

    users = query.order_by(User.name).all()

    if search:
        users = [u for u in users if search in u.name.lower() or search in u.email.lower()]

    result = []
    for u in users:
        pts = UserPoints.query.filter_by(user_id=u.id).first()
        trail_count = UserTrail.query.filter_by(user_id=u.id).count()
        result.append({
            'id': u.id,
            'name': u.name,
            'email': u.email,
            'role': u.role,
            'created_at': u.created_at.isoformat() if u.created_at else None,
            'total_points': pts.total_points if pts else 0,
            'current_level': pts.current_level if pts else 1,
            'trail_count': trail_count,
            'active_trail_id': u.active_trail_id,
        })

    return jsonify(result), 200


@admin_bp.route('/users/<int:user_id>/profile', methods=['GET'])
def get_user_profile(user_id):
    _, err = _admin_required()
    if err:
        return err

    u = User.query.get_or_404(user_id)
    pts = UserPoints.query.filter_by(user_id=u.id).first()

    trails = []
    for ut in UserTrail.query.filter_by(user_id=u.id).all():
        t = Trail.query.get(ut.trail_id)
        if not t:
            continue
        course_ids = [tc.course_id for tc in t.trail_courses]
        completed_courses = Progress.query.filter(
            Progress.user_id == u.id,
            Progress.course_id.in_(course_ids),
            Progress.passed == True
        ).with_entities(Progress.course_id).distinct().count() if course_ids else 0
        trails.append({
            'id': t.id,
            'name': t.name,
            'icon': t.icon or '',
            'color': t.color or '#008ea8',
            'enrolled_at': ut.enrolled_at.isoformat(),
            'completed_at': ut.completed_at.isoformat() if ut.completed_at else None,
            'total_courses': len(course_ids),
            'completed_courses': completed_courses,
        })

    certs = []
    for cert in Certificate.query.filter_by(user_id=u.id).all():
        c = Course.query.get(cert.course_id)
        certs.append({
            'id': cert.id,
            'course_name': c.name if c else '',
            'issued_at': cert.issued_at.isoformat() if cert.issued_at else None,
        })

    course_progress = []
    done_ids = set()
    for prog in Progress.query.filter_by(user_id=u.id).all():
        if prog.course_id in done_ids:
            continue
        done_ids.add(prog.course_id)
        c = Course.query.get(prog.course_id)
        if c:
            course_progress.append({
                'course_id': prog.course_id,
                'course_name': c.name,
                'passed': prog.passed,
            })

    return jsonify({
        'id': u.id,
        'name': u.name,
        'email': u.email,
        'role': u.role,
        'created_at': u.created_at.isoformat() if u.created_at else None,
        'active_trail_id': u.active_trail_id,
        'onboarding_completed': u.onboarding_completed,
        'gamification': pts.to_dict() if pts else {'total_points': 0, 'current_level': 1, 'points_in_level': 0},
        'trails': trails,
        'certificates': certs,
        'course_progress': course_progress,
    }), 200


@admin_bp.route('/users/<int:user_id>/reset-progress', methods=['POST'])
def reset_user_progress(user_id):
    _, err = _admin_required()
    if err:
        return err

    u = User.query.get_or_404(user_id)

    Progress.query.filter_by(user_id=u.id).delete()
    UserTrail.query.filter_by(user_id=u.id).delete()

    pts = UserPoints.query.filter_by(user_id=u.id).first()
    if pts:
        pts.total_points = 0
        pts.current_level = 1
        pts.points_in_level = 0

    u.active_trail_id = None
    u.onboarding_completed = False

    db.session.commit()
    return jsonify({'ok': True}), 200


@admin_bp.route('/users/<int:user_id>/trail', methods=['PUT'])
def change_user_active_trail(user_id):
    _, err = _admin_required()
    if err:
        return err

    u = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    trail_id = data.get('trail_id')

    if trail_id:
        Trail.query.get_or_404(trail_id)
        ut = UserTrail.query.filter_by(user_id=u.id, trail_id=trail_id).first()
        if not ut:
            ut = UserTrail(user_id=u.id, trail_id=trail_id)
            db.session.add(ut)
        u.active_trail_id = trail_id
    else:
        u.active_trail_id = None

    db.session.commit()
    return jsonify({'ok': True}), 200


@admin_bp.route('/users/bulk-action', methods=['POST'])
def bulk_action_users():
    _, err = _admin_required()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    action = data.get('action')
    user_ids = data.get('user_ids', [])
    trail_id = data.get('trail_id')

    if not user_ids:
        return jsonify({'error': 'Nenhum usuário selecionado'}), 400

    if action == 'enroll_trail':
        if not trail_id:
            return jsonify({'error': 'trail_id obrigatório'}), 400
        Trail.query.get_or_404(trail_id)
        for uid in user_ids:
            existing = UserTrail.query.filter_by(user_id=uid, trail_id=trail_id).first()
            if not existing:
                db.session.add(UserTrail(user_id=uid, trail_id=trail_id))
        db.session.commit()
        return jsonify({'ok': True, 'enrolled': len(user_ids)}), 200

    elif action == 'remove_trail':
        if not trail_id:
            return jsonify({'error': 'trail_id obrigatório'}), 400
        for uid in user_ids:
            UserTrail.query.filter_by(user_id=uid, trail_id=trail_id).delete()
        db.session.commit()
        return jsonify({'ok': True}), 200

    return jsonify({'error': 'Ação desconhecida'}), 400
