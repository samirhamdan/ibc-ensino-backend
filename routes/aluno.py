"""
Aluno-facing endpoints (Sprint 6.1): stats/profile, achievements ("Conquistas"),
certificates list and "continue learning" info.
"""
from datetime import datetime
from flask import Blueprint, jsonify, session, request
from extensions import db
from models import (User, Course, Module, LessonProgress, UserPoints,
                     Achievement, UserAchievement, Certificate, Question,
                     StudySession)
from routes.gamification import (
    LEVEL_NAMES, _get_or_create_points,
    get_completed_lessons_count, get_completed_courses_count,
    get_completed_trails_count, get_questions_count, get_certificates_count,
)

aluno_bp = Blueprint('aluno', __name__)


def _current_user():
    uid = session.get('user_id')
    if uid:
        return User.query.get(uid)
    return None


def _require_aluno():
    user = _current_user()
    if not user:
        return None, (jsonify({'error': 'Não autenticado'}), 401)
    if user.role != 'aluno':
        return None, (jsonify({'error': 'Acesso negado'}), 403)
    return user, None


@aluno_bp.route('/stats', methods=['GET'])
def stats():
    user, err = _require_aluno()
    if err:
        return err

    up = _get_or_create_points(user.id)
    db.session.commit()

    return jsonify({
        'total_points': up.total_points,
        'current_level': up.current_level,
        'level_name': LEVEL_NAMES.get(up.current_level, ''),
        'points_in_level': up.points_in_level,
        'lessons_completed': get_completed_lessons_count(user.id),
        'courses_completed': get_completed_courses_count(user.id),
        'trails_completed': get_completed_trails_count(user.id),
        'questions_count': get_questions_count(user.id),
        'certificates_count': get_certificates_count(user.id),
    }), 200


@aluno_bp.route('/achievements', methods=['GET'])
def achievements():
    user, err = _require_aluno()
    if err:
        return err

    earned = {ua.achievement_id: ua for ua in UserAchievement.query.filter_by(user_id=user.id).all()}
    result = []
    for ach in Achievement.query.order_by(Achievement.criteria_type, Achievement.criteria_value).all():
        d = ach.to_dict()
        ua = earned.get(ach.id)
        d['earned'] = ua is not None
        d['earned_at'] = ua.earned_at.isoformat() if ua and ua.earned_at else None
        result.append(d)
    return jsonify(result), 200


@aluno_bp.route('/certificates', methods=['GET'])
def certificates():
    user, err = _require_aluno()
    if err:
        return err

    certs = Certificate.query.filter_by(user_id=user.id).order_by(Certificate.issued_at.desc()).all()
    result = []
    for c in certs:
        d = c.to_dict()
        d['id'] = c.id
        d['cert_code'] = c.cert_code
        result.append(d)
    return jsonify(result), 200


@aluno_bp.route('/continue', methods=['GET'])
def continue_learning():
    """Returns the last-accessed lesson/course the student has not yet
    completed, to drive the 'continue learning' card."""
    user, err = _require_aluno()
    if err:
        return err

    candidate = None
    for c in Course.query.all():
        modules = Module.query.filter_by(course_id=c.id).order_by(Module.position).all()
        if not modules:
            continue
        progresses = {p.module_id: p for p in
                      LessonProgress.query.filter_by(user_id=user.id, course_id=c.id).all()}
        if not progresses:
            continue
        passed_count = sum(1 for m in modules if progresses.get(m.id) and progresses[m.id].passed)
        if passed_count >= len(modules):
            continue  # course already fully completed

        last_progress = max(
            (p for p in progresses.values() if p.completed_at),
            key=lambda p: p.completed_at,
            default=None,
        )
        info = {
            'course_id': c.id,
            'course_name': c.name,
            'course_icon': c.icon,
            'aula_atual': min(passed_count + 1, len(modules)),
            'total_aulas': len(modules),
            'percentage': round(passed_count / len(modules) * 100),
            'last_accessed_at': last_progress.completed_at.isoformat() if last_progress and last_progress.completed_at else None,
        }
        if candidate is None or (
            info['last_accessed_at'] and (
                candidate['last_accessed_at'] is None or info['last_accessed_at'] > candidate['last_accessed_at']
            )
        ):
            candidate = info

    return jsonify(candidate), 200


# ── Minhas Perguntas (Sprint 6.2) ────────────────────────────────────────────

@aluno_bp.route('/questions', methods=['GET'])
def my_questions_with_status():
    """All of the current student's questions, with status/course info for the
    'Minhas Perguntas' screen."""
    user, err = _require_aluno()
    if err:
        return err

    questions = Question.query.filter_by(user_id=user.id).order_by(Question.created_at.desc()).all()
    result = []
    for q in questions:
        d = q.to_dict()
        d['course_name'] = q.course.name if q.course else ''
        d['course_icon'] = q.course.icon if q.course else ''
        result.append(d)
    return jsonify(result), 200


@aluno_bp.route('/questions/<int:question_id>/resolve', methods=['POST'])
def resolve_question(question_id):
    """Student marks an answered question as resolved."""
    user, err = _require_aluno()
    if err:
        return err

    question = Question.query.filter_by(id=question_id, user_id=user.id).first()
    if not question:
        return jsonify({'error': 'Pergunta não encontrada'}), 404

    if (question.status or 'open') != 'answered':
        return jsonify({'error': 'Apenas perguntas respondidas podem ser marcadas como resolvidas'}), 400

    question.status = 'resolved'
    question.resolved_at = datetime.utcnow()
    db.session.commit()
    return jsonify(question.to_dict()), 200


# ── Timer de Estudo (Sprint 6.2) ─────────────────────────────────────────────

@aluno_bp.route('/study-time', methods=['POST'])
def save_study_time():
    """Records a study session (time spent on a lesson)."""
    user, err = _require_aluno()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    lesson_id = data.get('lesson_id')
    seconds = data.get('seconds') or 0
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        seconds = 0
    # limita a 12h por sessão e ignora negativos (valor vem do timer do cliente)
    seconds = max(0, min(seconds, 12 * 3600))

    # lesson_id fantasma violava FK no commit → 500
    if lesson_id is not None and not Module.query.get(lesson_id):
        lesson_id = None

    session_row = StudySession(
        user_id=user.id,
        lesson_id=lesson_id,
        duration_seconds=seconds,
        ended_at=datetime.utcnow(),
    )
    db.session.add(session_row)
    db.session.commit()
    return jsonify({'success': True}), 200
