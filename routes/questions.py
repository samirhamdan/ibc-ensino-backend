"""
Questions/Q&A routes: students ask questions, tutors answer
"""
from flask import Blueprint, request, jsonify, session
from extensions import db
from core.tenancy import current_tenant_id, get_scoped_or_404, role_no_tenant
from models import Question, Course, User, Progress, Notification, TutorCourse

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

    get_scoped_or_404(Course, course_id)
    questions = Question.query.filter_by(tenant_id=current_tenant_id(), course_id=course_id).order_by(Question.created_at.desc()).all()
    return jsonify([q.to_dict() for q in questions]), 200


@questions_bp.route('/<int:course_id>', methods=['POST'])
def ask_question(course_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    get_scoped_or_404(Course, course_id)

    data = request.get_json(silent=True) or {}
    texto = (data.get('texto') or '').strip()
    if not texto:
        return jsonify({'error': 'texto é obrigatório'}), 400

    q = Question(course_id=course_id, user_id=user.id, texto=texto)
    db.session.add(q)
    db.session.commit()

    # Pontos concedidos aqui (evento real: pergunta criada) — antes vinham de
    # /gamification/add-points, chamável repetidamente sem criar pergunta.
    from routes.gamification import award_points, check_and_grant_achievements
    points = award_points(user.id, 'question_asked')
    new_achievements = check_and_grant_achievements(user.id)

    result = q.to_dict()
    result['new_achievements'] = new_achievements
    result['points'] = points
    return jsonify(result), 201


@questions_bp.route('/<int:question_id>/responder', methods=['POST'])
def answer_question(question_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    if role_no_tenant(user) not in ('admin', 'tutor'):
        return jsonify({'error': 'Apenas tutores podem responder perguntas'}), 403

    question = get_scoped_or_404(Question, question_id)

    # Tutor pode responder se: é o tutor principal do curso, OU foi vinculado
    # ao curso via TutorCourse (admin /tutors/<id>/assign-course), OU a pergunta
    # foi atribuída a ele (admin /questions/<id>/assign). Antes só o tutor_id
    # do curso passava — o fluxo de atribuição do admin ficava inoperante (403).
    if role_no_tenant(user) == 'tutor':
        is_course_tutor = bool(question.course and question.course.tutor_id == user.id)
        is_linked_tutor = bool(question.course and TutorCourse.query.filter_by(tenant_id=current_tenant_id(), 
            tutor_id=user.id, course_id=question.course_id).first())
        is_assigned = question.assigned_tutor_id == user.id
        if not (is_course_tutor or is_linked_tutor or is_assigned):
            return jsonify({'error': 'Você só pode responder perguntas dos seus cursos'}), 403

    data = request.get_json(silent=True) or {}
    resposta = (data.get('resposta') or '').strip()
    if not resposta:
        return jsonify({'error': 'resposta é obrigatória'}), 400

    is_first_answer = question.status != 'answered'

    question.resposta = resposta
    question.respondido_por = user.name
    question.status = 'answered'
    db.session.commit()

    # Pontos para quem perguntou, concedidos aqui (servidor, evento real) e só
    # na primeira resposta — não mais via /gamification/add-points, que
    # aceitava question_id arbitrário vindo do cliente sem checagem alguma.
    if is_first_answer:
        from routes.gamification import award_points
        award_points(question.user_id, 'question_answered')

    notification = Notification(
        user_id=question.user_id,
        title='Sua pergunta foi respondida',
        message=f'{user.name} respondeu sua pergunta em "{question.course.name if question.course else "um curso"}".',
        type='message',
        link='minhas-perguntas',
        created_by=user.id,
    )
    db.session.add(notification)
    db.session.commit()

    return jsonify(question.to_dict()), 200


# ── Dashboard endpoints ──────────────────────────────────────────────────────

@questions_bp.route('/me', methods=['GET'])
def my_questions():
    """Student dashboard: list own questions (pending + answered)."""
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    questions = Question.query.filter_by(tenant_id=current_tenant_id(), user_id=user.id).order_by(Question.created_at.desc()).all()
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
    if role_no_tenant(user) not in ('admin', 'tutor'):
        return jsonify({'error': 'Acesso negado'}), 403

    query = Question.query.filter_by(tenant_id=current_tenant_id())
    if role_no_tenant(user) == 'tutor':
        # mesmos critérios de answer_question: cursos onde é tutor principal,
        # cursos vinculados via TutorCourse e perguntas atribuídas diretamente
        course_ids = {c.id for c in Course.query.filter_by(tenant_id=current_tenant_id(), tutor_id=user.id).all()}
        course_ids.update(tc.course_id for tc in TutorCourse.query.filter_by(tenant_id=current_tenant_id(), tutor_id=user.id).all())
        query = query.filter(db.or_(Question.course_id.in_(course_ids),
                                    Question.assigned_tutor_id == user.id))

    questions = query.order_by(Question.created_at.desc()).all()
    result = []
    for q in questions:
        d = q.to_dict()
        d['course_name'] = q.course.name if q.course else ''
        d['course_icon'] = q.course.icon if q.course else ''
        result.append(d)
    return jsonify(result), 200
