"""
Lesson (aula) routes: linear lesson flow — material + inline quiz per module
"""
from flask import Blueprint, request, jsonify, session
from extensions import db
from models import Course, Module, LessonProgress, User

lessons_bp = Blueprint('lessons', __name__)

PASS_THRESHOLD = 60  # percent


def _current_user():
    uid = session.get('user_id')
    if uid:
        return User.query.get(uid)
    return None


def _ordered_modules(course_id):
    return Module.query.filter_by(course_id=course_id).order_by(Module.position).all()


def _lesson_dict(module, progress_map, unlocked):
    quiz_total = len(module.quiz)
    prog = progress_map.get(module.id)
    return {
        'id': module.id,
        'nome': module.nome,
        'dur': module.dur,
        'position': module.position,
        'materiais': [m.to_dict() for m in module.materials],
        'quiz_total': quiz_total,
        'progress': prog.to_dict() if prog else None,
        'unlocked': unlocked,
    }


@lessons_bp.route('/<int:course_id>/aulas', methods=['GET'])
def list_aulas(course_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    Course.query.get_or_404(course_id)
    modules = _ordered_modules(course_id)

    progresses = LessonProgress.query.filter_by(user_id=user.id, course_id=course_id).all()
    progress_map = {p.module_id: p for p in progresses}

    result = []
    unlocked = True
    for m in modules:
        result.append(_lesson_dict(m, progress_map, unlocked))
        prog = progress_map.get(m.id)
        unlocked = bool(prog and prog.passed)

    return jsonify(result), 200


@lessons_bp.route('/<int:course_id>/aulas/<int:aula_num>', methods=['GET'])
def get_aula(course_id, aula_num):
    """aula_num is 1-based position index"""
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    Course.query.get_or_404(course_id)
    modules = _ordered_modules(course_id)
    if aula_num < 1 or aula_num > len(modules):
        return jsonify({'error': 'Aula não encontrada'}), 404

    progresses = LessonProgress.query.filter_by(user_id=user.id, course_id=course_id).all()
    progress_map = {p.module_id: p for p in progresses}

    # Check unlock: all previous lessons must be passed
    unlocked = True
    for i in range(aula_num - 1):
        prog = progress_map.get(modules[i].id)
        if not (prog and prog.passed):
            unlocked = False
            break

    if not unlocked and user.role not in ('admin', 'tutor'):
        return jsonify({'error': 'Esta aula está bloqueada. Conclua a aula anterior primeiro.'}), 403

    module = modules[aula_num - 1]
    data = _lesson_dict(module, progress_map, True)
    data['quiz'] = [q.to_dict(hide_answer=True) for q in module.quiz]
    data['total_aulas'] = len(modules)
    data['aula_num'] = aula_num
    data['course'] = {'id': module.course_id, 'name': module.course.name, 'icon': module.course.icon}
    return jsonify(data), 200


@lessons_bp.route('/<int:course_id>/aulas/<int:aula_num>/submit-quiz', methods=['POST'])
def submit_aula_quiz(course_id, aula_num):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    Course.query.get_or_404(course_id)
    modules = _ordered_modules(course_id)
    if aula_num < 1 or aula_num > len(modules):
        return jsonify({'error': 'Aula não encontrada'}), 404

    module = modules[aula_num - 1]
    quiz = module.quiz
    if not quiz:
        return jsonify({'error': 'Esta aula não tem exercício'}), 404

    data = request.get_json(silent=True) or {}
    answers = data.get('answers') or []

    score = 0
    feedback = []
    for i, q in enumerate(quiz):
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

    total = len(quiz)
    percentage = round(score / total * 100) if total else 0
    passed = percentage >= PASS_THRESHOLD

    prog = LessonProgress.query.filter_by(user_id=user.id, module_id=module.id).first()
    is_first_attempt = prog is None
    already_passed = bool(prog and prog.passed)
    if not prog:
        prog = LessonProgress(user_id=user.id, course_id=course_id, module_id=module.id)
        db.session.add(prog)
    # Keep best attempt
    if score > (prog.score or 0) or not prog.total:
        prog.score = score
        prog.total = total
    prog.passed = prog.passed or passed
    db.session.commit()

    next_unlocked = passed
    is_last = aula_num == len(modules)

    return jsonify({
        'score': score,
        'total': total,
        'percentage': percentage,
        'passed': passed,
        'pass_threshold': PASS_THRESHOLD,
        'feedback': feedback,
        'next_unlocked': next_unlocked,
        'is_last_lesson': is_last,
    }), 200
