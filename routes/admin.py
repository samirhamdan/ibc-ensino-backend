"""
Admin-only routes: tutor management, user management, question assignment
"""
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from extensions import db
from core.tenancy import current_tenant_id, get_scoped, get_scoped_or_404, role_no_tenant
from models import (
    User, Course, Question, TutorCourse, UserTrail, UserPoints,
    Certificate, Progress, Trail, Notification, Announcement, AnnouncementDismissal,
    PlatformConfig, Level, Module, Material, Quiz, LessonProgress
)
from sqlalchemy import func

admin_bp = Blueprint('admin', __name__)


def _admin_required():
    uid = session.get('user_id')
    user = User.query.get(uid) if uid else None
    if not user or role_no_tenant(user) != 'admin':
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
        assigned_courses = TutorCourse.query.filter_by(tenant_id=current_tenant_id(), tutor_id=t.id).all()
        course_ids = [tc.course_id for tc in assigned_courses]

        pending = Question.query.filter(Question.tenant_id == current_tenant_id(), 
            Question.assigned_tutor_id == t.id,
            Question.resposta == ''
        ).count()
        total_answered = Question.query.filter(Question.tenant_id == current_tenant_id(), 
            Question.assigned_tutor_id == t.id,
            Question.resposta != ''
        ).count()

        courses_data = []
        for tc in assigned_courses:
            c = get_scoped(Course, tc.course_id)
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

    get_scoped_or_404(Course, course_id)

    existing = TutorCourse.query.filter_by(tenant_id=current_tenant_id(), tutor_id=tutor_id, course_id=course_id).first()
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

    tc = TutorCourse.query.filter_by(tenant_id=current_tenant_id(), tutor_id=tutor_id, course_id=course_id).first_or_404()
    db.session.delete(tc)
    db.session.commit()
    return jsonify({'ok': True}), 200


# ── Questions (admin) ─────────────────────────────────────────────────────────

@admin_bp.route('/questions/unassigned', methods=['GET'])
def list_unassigned_questions():
    _, err = _admin_required()
    if err:
        return err

    questions = Question.query.filter(Question.tenant_id == current_tenant_id(), 
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

    q = get_scoped_or_404(Question, question_id)
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

    courses = Course.query.filter_by(tenant_id=current_tenant_id()).order_by(Course.name).all()
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
        try:
            trail_filter_id = int(trail_filter)
        except (TypeError, ValueError):
            return jsonify({'error': 'Filtro de trilha inválido'}), 400
        enrolled_ids = [
            ut.user_id for ut in UserTrail.query.filter_by(trail_id=trail_filter_id, tenant_id=current_tenant_id()).all()
        ]
        query = query.filter(User.id.in_(enrolled_ids))

    users = query.order_by(User.name).all()

    if search:
        users = [u for u in users if search in u.name.lower() or search in u.email.lower()]

    result = []
    for u in users:
        pts = UserPoints.query.filter_by(user_id=u.id, tenant_id=current_tenant_id()).first()
        trail_count = UserTrail.query.filter_by(user_id=u.id, tenant_id=current_tenant_id()).count()
        result.append({
            'id': u.id,
            'name': u.name,
            'email': u.email,
            'role': role_no_tenant(u),
            'created_at': u.created_at.isoformat() if u.created_at else None,
            'total_points': pts.total_points if pts else 0,
            'current_level': pts.current_level if pts else 1,
            'trail_count': trail_count,
            'active_trail_id': u.active_trail_id,
            'is_active': u.is_active,
        })

    return jsonify(result), 200


@admin_bp.route('/users/<int:user_id>/profile', methods=['GET'])
def get_user_profile(user_id):
    _, err = _admin_required()
    if err:
        return err

    u = User.query.get_or_404(user_id)
    pts = UserPoints.query.filter_by(user_id=u.id, tenant_id=current_tenant_id()).first()

    trails = []
    for ut in UserTrail.query.filter_by(user_id=u.id, tenant_id=current_tenant_id()).all():
        t = get_scoped(Trail, ut.trail_id)
        if not t:
            continue
        course_ids = [tc.course_id for tc in t.trail_courses]
        completed_courses = Progress.query.filter(
            Progress.tenant_id == current_tenant_id(),
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
    for cert in Certificate.query.filter_by(user_id=u.id, tenant_id=current_tenant_id()).all():
        c = get_scoped(Course, cert.course_id)
        certs.append({
            'id': cert.id,
            'course_name': c.name if c else '',
            'issued_at': cert.issued_at.isoformat() if cert.issued_at else None,
        })

    course_progress = []
    done_ids = set()
    for prog in Progress.query.filter_by(user_id=u.id, tenant_id=current_tenant_id()).all():
        if prog.course_id in done_ids:
            continue
        done_ids.add(prog.course_id)
        c = get_scoped(Course, prog.course_id)
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
        'role': role_no_tenant(u),
        'created_at': u.created_at.isoformat() if u.created_at else None,
        'active_trail_id': u.active_trail_id,
        'onboarding_completed': u.onboarding_completed,
        'last_login': u.last_login.isoformat() if u.last_login else None,
        'is_active': u.is_active,
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

    Progress.query.filter_by(user_id=u.id, tenant_id=current_tenant_id()).delete()
    LessonProgress.query.filter_by(user_id=u.id, tenant_id=current_tenant_id()).delete()
    UserTrail.query.filter_by(user_id=u.id, tenant_id=current_tenant_id()).delete()

    pts = UserPoints.query.filter_by(user_id=u.id, tenant_id=current_tenant_id()).first()
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
        get_scoped_or_404(Trail, trail_id)
        ut = UserTrail.query.filter_by(user_id=u.id, trail_id=trail_id, tenant_id=current_tenant_id()).first()
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
        get_scoped_or_404(Trail, trail_id)
        # só ids que existem: um id fantasma na lista violava FK e derrubava
        # a operação inteira com 500
        valid_ids = {u.id for u in User.query.filter(User.id.in_(user_ids)).all()}
        for uid in valid_ids:
            existing = UserTrail.query.filter_by(user_id=uid, trail_id=trail_id, tenant_id=current_tenant_id()).first()
            if not existing:
                db.session.add(UserTrail(user_id=uid, trail_id=trail_id))
        db.session.commit()
        return jsonify({'ok': True, 'enrolled': len(valid_ids)}), 200

    elif action == 'remove_trail':
        if not trail_id:
            return jsonify({'error': 'trail_id obrigatório'}), 400
        for uid in user_ids:
            UserTrail.query.filter_by(user_id=uid, trail_id=trail_id, tenant_id=current_tenant_id()).delete()
        db.session.commit()
        return jsonify({'ok': True}), 200

    return jsonify({'error': 'Ação desconhecida'}), 400


@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    admin_user, err = _admin_required()
    if err:
        return err

    u = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    role = data.get('role')

    if not name or not email or not role:
        return jsonify({'error': 'name, email e role são obrigatórios'}), 400

    valid_roles = {'admin', 'tutor', 'aluno'}
    if role not in valid_roles:
        return jsonify({'error': 'role inválido'}), 400

    existing = User.query.filter(User.email == email, User.id != user_id).first()
    if existing:
        return jsonify({'error': 'Email já em uso por outro usuário'}), 409

    if user_id == admin_user.id and role != 'admin':
        return jsonify({'error': 'Não é possível alterar o próprio papel de administrador'}), 400

    u.name = name
    u.email = email
    u.role = role
    db.session.commit()
    return jsonify(u.to_dict()), 200


@admin_bp.route('/users/<int:user_id>/toggle-active', methods=['POST'])
def toggle_user_active(user_id):
    _, err = _admin_required()
    if err:
        return err

    u = User.query.get_or_404(user_id)
    u.is_active = not u.is_active
    db.session.commit()
    return jsonify(u.to_dict()), 200


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
def admin_reset_user_password(user_id):
    _, err = _admin_required()
    if err:
        return err

    u = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    new_password = data.get('new_password') or ''

    if len(new_password) < 6:
        return jsonify({'error': 'A nova senha deve ter ao menos 6 caracteres'}), 400

    u.set_password(new_password)
    db.session.commit()
    return jsonify({'ok': True}), 200


@admin_bp.route('/users/invite', methods=['POST'])
def invite_user():
    admin_user, err = _admin_required()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    role = data.get('role')
    password = data.get('password') or ''

    if not name or not email or not role or not password:
        return jsonify({'error': 'name, email, role e password são obrigatórios'}), 400

    valid_roles = {'admin', 'tutor', 'aluno'}
    if role not in valid_roles:
        return jsonify({'error': 'role inválido'}), 400

    if len(password) < 6:
        return jsonify({'error': 'A senha deve ter ao menos 6 caracteres'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email já cadastrado'}), 409

    u = User(
        name=name,
        email=email,
        role=role,
        is_active=True,
        onboarding_completed=True,
        created_at=datetime.utcnow(),
    )
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return jsonify(u.to_dict()), 201


@admin_bp.route('/users/<int:user_id>/message', methods=['POST'])
def send_user_message(user_id):
    admin_user, err = _admin_required()
    if err:
        return err

    target = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    message = (data.get('message') or '').strip()

    if not title or not message:
        return jsonify({'error': 'title e message são obrigatórios'}), 400

    notif = Notification(
        user_id=target.id,
        title=title,
        message=message,
        type='message',
        created_by=admin_user.id,
    )
    db.session.add(notif)
    db.session.commit()
    return jsonify(notif.to_dict()), 201


# ── Announcements (admin) ──────────────────────────────────────────────────

@admin_bp.route('/announcements', methods=['POST'])
def create_announcement():
    admin_user, err = _admin_required()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    message = (data.get('message') or '').strip()
    severity = data.get('severity') or 'info'
    target_role = data.get('target_role') or 'all'
    expires_at_raw = data.get('expires_at')

    if not title or not message:
        return jsonify({'error': 'title e message são obrigatórios'}), 400

    if severity not in ('info', 'warning', 'success'):
        return jsonify({'error': 'severity inválido'}), 400
    if target_role not in ('aluno', 'tutor', 'all'):
        return jsonify({'error': 'target_role inválido'}), 400

    expires_at = None
    if expires_at_raw:
        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except ValueError:
            return jsonify({'error': 'expires_at inválido'}), 400

    ann = Announcement(
        title=title,
        message=message,
        severity=severity,
        target_role=target_role,
        created_by=admin_user.id,
        expires_at=expires_at,
    )
    db.session.add(ann)
    db.session.commit()
    return jsonify(ann.to_dict()), 201


@admin_bp.route('/announcements', methods=['GET'])
def list_announcements():
    _, err = _admin_required()
    if err:
        return err

    anns = Announcement.query.filter_by(tenant_id=current_tenant_id()).order_by(Announcement.created_at.desc()).all()
    result = []
    for a in anns:
        d = a.to_dict()
        d['dismissed_count'] = AnnouncementDismissal.query.filter_by(tenant_id=current_tenant_id(), announcement_id=a.id).count()
        result.append(d)
    return jsonify(result), 200


@admin_bp.route('/announcements/<int:announcement_id>', methods=['DELETE'])
def delete_announcement(announcement_id):
    _, err = _admin_required()
    if err:
        return err

    ann = get_scoped_or_404(Announcement, announcement_id)
    ann.is_active = False
    db.session.commit()
    return jsonify({'ok': True}), 200


# ── Platform Configuration ────────────────────────────────────────────────────

def _get_or_create_config():
    config = PlatformConfig.query.first()
    if not config:
        config = PlatformConfig()
        db.session.add(config)
        db.session.commit()
    return config


@admin_bp.route('/config', methods=['GET'])
def get_admin_config():
    _, err = _admin_required()
    if err:
        return err

    config = _get_or_create_config()
    data = config.to_dict()
    data['levels'] = [lv.to_dict() for lv in Level.query.order_by(Level.number).all()]
    return jsonify(data), 200


@admin_bp.route('/config', methods=['PUT'])
def update_admin_config():
    admin_user, err = _admin_required()
    if err:
        return err

    config = _get_or_create_config()
    data = request.get_json(silent=True) or {}
    fields = (
        'platform_name', 'platform_short', 'whatsapp', 'support_email', 'support_hours',
        'verse_text', 'verse_reference', 'points_read_material', 'points_complete_video',
        'points_correct_exercise', 'points_complete_course', 'points_complete_trail',
    )
    for field in fields:
        if field in data:
            setattr(config, field, data[field])
    config.updated_by = admin_user.id
    db.session.commit()
    return jsonify({'success': True, 'config': config.to_dict()}), 200


@admin_bp.route('/levels', methods=['GET'])
def list_levels():
    _, err = _admin_required()
    if err:
        return err

    levels = Level.query.order_by(Level.number).all()
    return jsonify([lv.to_dict() for lv in levels]), 200


@admin_bp.route('/levels', methods=['PUT'])
def replace_levels():
    _, err = _admin_required()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    levels_data = data.get('levels', [])
    if not levels_data:
        return jsonify({'error': 'É necessário pelo menos um nível'}), 400

    numbers = [lv.get('number') for lv in levels_data]
    if len(numbers) != len(set(numbers)):
        return jsonify({'error': 'Números de nível devem ser únicos'}), 400

    sorted_levels = sorted(levels_data, key=lambda lv: lv.get('number', 0))
    prev_points = None
    for lv in sorted_levels:
        points = lv.get('min_points', 0)
        if prev_points is not None and points <= prev_points:
            return jsonify({'error': 'Pontos mínimos devem aumentar a cada nível'}), 400
        prev_points = points

    Level.query.delete()
    for lv in levels_data:
        db.session.add(Level(
            number=lv.get('number'),
            name=lv.get('name', ''),
            min_points=lv.get('min_points', 0),
            color=lv.get('color', '#008ea8'),
        ))
    db.session.commit()
    return jsonify({'success': True, 'levels': [lv.to_dict() for lv in Level.query.order_by(Level.number).all()]}), 200


# ── Course status management ──────────────────────────────────────────────────

@admin_bp.route('/courses/<int:course_id>/toggle-status', methods=['POST'])
def toggle_course_status(course_id):
    _, err = _admin_required()
    if err:
        return err

    course = get_scoped_or_404(Course, course_id)
    data = request.get_json(silent=True) or {}
    status = data.get('status')
    if status not in ('published', 'draft', 'archived'):
        return jsonify({'error': 'status inválido'}), 400

    course.status = status
    db.session.commit()
    return jsonify({'success': True, 'status': course.status}), 200


@admin_bp.route('/courses/<int:course_id>/duplicate', methods=['POST'])
def duplicate_course(course_id):
    _, err = _admin_required()
    if err:
        return err

    course = get_scoped_or_404(Course, course_id)
    new_course = Course(
        name=f'Cópia de {course.name}',
        icon=course.icon,
        acesso=course.acesso,
        resumo=course.resumo,
        duracao=course.duracao,
        category_id=course.category_id,
        tutor_id=course.tutor_id,
        color=course.color,
        tag=course.tag,
        description=course.description,
        status='draft',
    )
    db.session.add(new_course)
    db.session.flush()

    for m in Module.query.filter_by(tenant_id=current_tenant_id(), course_id=course.id).order_by(Module.position).all():
        new_module = Module(
            course_id=new_course.id, nome=m.nome, dur=m.dur, position=m.position,
            video_url=m.video_url, video_provider=m.video_provider,
        )
        db.session.add(new_module)
        db.session.flush()

        for mat in Material.query.filter_by(tenant_id=current_tenant_id(), module_id=m.id).all():
            db.session.add(Material(
                course_id=new_course.id, module_id=new_module.id,
                name=mat.name, url=mat.url, tipo=mat.tipo, size=mat.size,
            ))

        for q in Quiz.query.filter_by(tenant_id=current_tenant_id(), module_id=m.id).order_by(Quiz.position).all():
            db.session.add(Quiz(
                course_id=new_course.id, module_id=new_module.id,
                q=q.q, opts=q.opts, ans=q.ans, exp=q.exp, position=q.position,
            ))

    db.session.commit()
    return jsonify({'success': True, 'course_id': new_course.id, 'name': new_course.name}), 200
