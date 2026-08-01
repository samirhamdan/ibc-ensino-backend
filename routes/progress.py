"""
Progress routes: get and save student progress per course
"""
from flask import Blueprint, request, jsonify, session
from extensions import db
from core.tenancy import current_tenant_id, get_scoped_or_404
from models import Progress, Course, Quiz, User

progress_bp = Blueprint('progress', __name__)


def _current_user():
    uid = session.get('user_id')
    if uid:
        return User.query.get(uid)
    return None


@progress_bp.route('/<int:course_id>', methods=['GET'])
def get_progress(course_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    get_scoped_or_404(Course, course_id)

    prog = Progress.query.filter_by(user_id=user.id, course_id=course_id, tenant_id=current_tenant_id()).first()
    if not prog:
        return jsonify({
            'user_id': user.id,
            'course_id': course_id,
            'material_done': False,
            'quiz_score': 0,
            'quiz_total': 0,
        }), 200

    return jsonify(prog.to_dict()), 200


@progress_bp.route('/<int:course_id>', methods=['POST'])
def save_progress(course_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    get_scoped_or_404(Course, course_id)

    data = request.get_json(silent=True) or {}

    prog = Progress.query.filter_by(user_id=user.id, course_id=course_id, tenant_id=current_tenant_id()).first()
    if not prog:
        prog = Progress(user_id=user.id, course_id=course_id)
        db.session.add(prog)

    if 'material_done' in data:
        prog.material_done = bool(data['material_done'])

    # quiz_score/quiz_total NÃO são mais aceitos do cliente: a nota é gravada
    # exclusivamente pela correção do servidor (POST /progress/quiz/<id>/submit).
    # Antes, um POST {"material_done":true,"quiz_score":10,"quiz_total":10}
    # marcava o curso como concluído (Progress.passed) sem fazer nada.

    db.session.commit()
    return jsonify(prog.to_dict()), 200


@progress_bp.route('/quiz/<int:course_id>/submit', methods=['POST'])
def submit_quiz(course_id):
    """Receive answer array, grade automatically, save and return result."""
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    get_scoped_or_404(Course, course_id)

    data = request.get_json(silent=True) or {}
    # answers: list of ints (selected option index per question)
    answers = data.get('answers') or []

    questions = Quiz.query.filter_by(tenant_id=current_tenant_id(), course_id=course_id).order_by(Quiz.position).all()
    if not questions:
        return jsonify({'error': 'Este curso não tem quiz'}), 404

    score = 0
    feedback = []
    for i, q in enumerate(questions):
        selected = answers[i] if i < len(answers) else None
        correct = selected == q.ans
        if correct:
            score += 1
        feedback.append({
            'question': q.q,
            'selected': selected,
            'correct_answer': q.ans,
            'is_correct': correct,
            'explanation': q.exp,
        })

    # Persist progress
    prog = Progress.query.filter_by(user_id=user.id, course_id=course_id, tenant_id=current_tenant_id()).first()
    if not prog:
        prog = Progress(user_id=user.id, course_id=course_id)
        db.session.add(prog)
    prog.quiz_score = score
    prog.quiz_total = len(questions)
    db.session.commit()

    return jsonify({
        'score': score,
        'total': len(questions),
        'percentage': round(score / len(questions) * 100) if questions else 0,
        'feedback': feedback,
    }), 200


@progress_bp.route('/quiz/<int:course_id>/resultado', methods=['GET'])
def quiz_result(course_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    prog = Progress.query.filter_by(user_id=user.id, course_id=course_id, tenant_id=current_tenant_id()).first()
    if not prog or prog.quiz_total == 0:
        return jsonify({'error': 'Nenhum quiz submetido para este curso'}), 404

    return jsonify({
        'score': prog.quiz_score,
        'total': prog.quiz_total,
        'percentage': round(prog.quiz_score / prog.quiz_total * 100),
    }), 200
