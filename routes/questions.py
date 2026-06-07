"""
Questions/Q&A routes: students ask questions, tutors answer
"""
from flask import Blueprint, request, jsonify, session
from extensions import db
from models import Question, Course, User, Progress

questions_bp = Blueprint('questions', __name__)


def _current_user():
    uid = session.get('user_id')
    if uid:
        return User.query.get(uid)
    return None


@questions_bp.route('/<int:course_id>', methods=['GET'])
def list_questions(course_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    Course.query.get_or_404(course_id)
    questions = Question.query.filter_by(course_id=course_id).order_by(Question.created_at.desc()).all()
    return jsonify([q.to_dict() for q in questions]), 200


@questions_bp.route('/<int:course_id>', methods=['POST'])
def ask_question(course_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    Course.query.get_or_404(course_id)

    data = request.get_json(silent=True) or {}
    texto = (data.get('texto') or '').strip()
    if not texto:
        return jsonify({'error': 'texto é obrigatório'}), 400

    q = Question(course_id=course_id, user_id=user.id, texto=texto)
    db.session.add(q)
    db.session.commit()
    return jsonify(q.to_dict()), 201


@questions_bp.route('/<int:question_id>/responder', methods=['POST'])
def answer_question(question_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    if user.role not in ('admin', 'tutor'):
        return jsonify({'error': 'Apenas tutores podem responder perguntas'}), 403

    question = Question.query.get_or_404(question_id)

    data = request.get_json(silent=True) or {}
    resposta = (data.get('resposta') or '').strip()
    if not resposta:
        return jsonify({'error': 'resposta é obrigatória'}), 400

    question.resposta = resposta
    question.respondido_por = user.name
    db.session.commit()
    return jsonify(question.to_dict()), 200


# ── Dashboard endpoints ──────────────────────────────────────────────────────

@questions_bp.route('/me', methods=['GET'])
def my_questions():
    """Student dashboard: list own questions (pending + answered)."""
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    questions = Question.query.filter_by(user_id=user.id).order_by(Question.created_at.desc()).all()
    result = []
    for q in questions:
        d = q.to_dict()
        d['course_name'] = q.course.name if q.course else ''
        d['course_icon'] = q.course.icon if q.course else ''
        result.append(d)
    return jsonify(result), 200


@questions_bp.route('/tutor/dashboard', methods=['GET'])
def tutor_dashboard():
    """Tutor/admin dashboard: list questions from managed courses."""
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401
    if user.role not in ('admin', 'tutor'):
        return jsonify({'error': 'Acesso negado'}), 403

    query = Question.query
    if user.role == 'tutor':
        course_ids = [c.id for c in Course.query.filter_by(tutor_id=user.id).all()]
        query = query.filter(Question.course_id.in_(course_ids))

    questions = query.order_by(Question.created_at.desc()).all()
    result = []
    for q in questions:
        d = q.to_dict()
        d['course_name'] = q.course.name if q.course else ''
        d['course_icon'] = q.course.icon if q.course else ''
        result.append(d)
    return jsonify(result), 200
