"""
Course routes: CRUD for courses, modules, materials
"""
from flask import Blueprint, request, jsonify, session
from extensions import db
from core.tenancy import current_tenant_id
from models import Course, Module, Material, Quiz, Category, User

courses_bp = Blueprint('courses', __name__)


def _current_user():
    uid = session.get('user_id')
    if uid:
        return User.query.get(uid)
    return None


def _require_auth():
    user = _current_user()
    if not user:
        return None, (jsonify({'error': 'Não autenticado'}), 401)
    return user, None


def _require_admin():
    user, err = _require_auth()
    if err:
        return None, err
    if user.role != 'admin':
        return None, (jsonify({'error': 'Acesso negado'}), 403)
    return user, None


def _can_edit_course(user, course):
    return user.role == 'admin' or (user.role == 'tutor' and course.tutor_id == user.id)


# ── Courses ────────────────────────────────────────────────────────────────────

@courses_bp.route('', methods=['GET'])
def list_courses():
    user = _current_user()
    query = Course.query
    if not user or user.role not in ('admin', 'tutor'):
        query = query.filter_by(status='published')

    category = request.args.get('category')
    if category:
        cat = Category.query.filter_by(name=category).first()
        if cat:
            query = query.filter_by(category_id=cat.id)

    courses = query.all()
    return jsonify([c.to_dict() for c in courses]), 200


@courses_bp.route('/<int:course_id>', methods=['GET'])
def get_course(course_id):
    user = _current_user()
    course = Course.query.get_or_404(course_id)

    is_staff = bool(user and user.role in ('admin', 'tutor'))
    if not is_staff:
        if course.status != 'published':
            return jsonify({'error': 'Curso não encontrado'}), 404
        if course.acesso == 'interno' and not user:
            return jsonify({'error': 'Não autenticado'}), 401

    return jsonify(course.to_dict(include_details=True)), 200


@courses_bp.route('', methods=['POST'])
def create_course():
    user, err = _require_admin()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name é obrigatório'}), 400

    # Resolve/create category
    category_id = None
    cat_name = (data.get('category') or '').strip()
    if cat_name:
        cat = Category.query.filter_by(name=cat_name).first()
        if not cat:
            cat = Category(name=cat_name)
            db.session.add(cat)
            db.session.flush()
        category_id = cat.id

    course = Course(
        name=name,
        icon=data.get('icon', '📖'),
        acesso=data.get('acesso', 'publico'),
        resumo=data.get('resumo', ''),
        duracao=data.get('duracao', ''),
        category_id=category_id,
        tutor_id=data.get('tutor_id'),
    )
    db.session.add(course)
    db.session.commit()
    return jsonify(course.to_dict(include_details=True)), 201


@courses_bp.route('/<int:course_id>', methods=['PUT'])
def update_course(course_id):
    user, err = _require_auth()
    if err:
        return err

    course = Course.query.get_or_404(course_id)

    if not _can_edit_course(user, course):
        return jsonify({'error': 'Acesso negado'}), 403

    data = request.get_json(silent=True) or {}

    for field in ('name', 'icon', 'acesso', 'resumo', 'duracao', 'tag', 'description', 'color'):
        if field in data:
            setattr(course, field, data[field])

    if 'category' in data:
        cat_name = (data['category'] or '').strip()
        if cat_name:
            cat = Category.query.filter_by(name=cat_name).first()
            if not cat:
                cat = Category(name=cat_name)
                db.session.add(cat)
                db.session.flush()
            course.category_id = cat.id
        else:
            course.category_id = None

    if 'tutor_id' in data and user.role == 'admin':
        course.tutor_id = data['tutor_id']

    db.session.commit()
    return jsonify(course.to_dict(include_details=True)), 200


@courses_bp.route('/<int:course_id>', methods=['DELETE'])
def delete_course(course_id):
    _, err = _require_admin()
    if err:
        return err

    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()
    return jsonify({'message': 'Curso removido'}), 200


# ── Modules ────────────────────────────────────────────────────────────────────

@courses_bp.route('/<int:course_id>/modulos', methods=['POST'])
def add_module(course_id):
    user, err = _require_auth()
    if err:
        return err

    course = Course.query.get_or_404(course_id)
    if not _can_edit_course(user, course):
        return jsonify({'error': 'Acesso negado'}), 403

    data = request.get_json(silent=True) or {}
    nome = (data.get('nome') or '').strip()
    if not nome:
        return jsonify({'error': 'nome é obrigatório'}), 400

    position = Module.query.filter_by(course_id=course_id).count()
    module = Module(course_id=course_id, nome=nome, dur=data.get('dur', ''), position=position)
    db.session.add(module)
    db.session.commit()
    return jsonify(module.to_dict()), 201


@courses_bp.route('/<int:course_id>/modulos/<int:module_id>', methods=['DELETE'])
def delete_module(course_id, module_id):
    user, err = _require_auth()
    if err:
        return err

    course = Course.query.get_or_404(course_id)
    if not _can_edit_course(user, course):
        return jsonify({'error': 'Acesso negado'}), 403

    module = Module.query.filter_by(id=module_id, course_id=course_id).first_or_404()
    db.session.delete(module)
    db.session.commit()
    return jsonify({'message': 'Módulo removido'}), 200


# ── Materials ──────────────────────────────────────────────────────────────────

@courses_bp.route('/<int:course_id>/materiais', methods=['POST'])
def add_material(course_id):
    user, err = _require_auth()
    if err:
        return err

    course = Course.query.get_or_404(course_id)
    if not _can_edit_course(user, course):
        return jsonify({'error': 'Acesso negado'}), 403

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    url = (data.get('url') or '').strip()
    if not name or not url:
        return jsonify({'error': 'name e url são obrigatórios'}), 400

    mat = Material(
        course_id=course_id,
        name=name,
        url=url,
        tipo=data.get('tipo', 'link'),
        size=data.get('size', ''),
    )
    db.session.add(mat)
    db.session.commit()
    return jsonify(mat.to_dict()), 201


@courses_bp.route('/<int:course_id>/materiais/<int:mat_id>', methods=['DELETE'])
def delete_material(course_id, mat_id):
    user, err = _require_auth()
    if err:
        return err

    course = Course.query.get_or_404(course_id)
    if not _can_edit_course(user, course):
        return jsonify({'error': 'Acesso negado'}), 403

    mat = Material.query.filter_by(id=mat_id, course_id=course_id).first_or_404()
    db.session.delete(mat)
    db.session.commit()
    return jsonify({'message': 'Material removido'}), 200


# ── Categories ─────────────────────────────────────────────────────────────────

@courses_bp.route('/categories', methods=['GET'])
def list_categories():
    cats = Category.query.all()
    return jsonify([c.to_dict() for c in cats]), 200


# ═══════════════════════════════════════════════════════════════
# ADMIN: Courses + Lessons management (Sprint 4)
# ═══════════════════════════════════════════════════════════════

def _course_admin_required():
    uid = session.get('user_id')
    user = User.query.get(uid) if uid else None
    if not user or user.role not in ('admin', 'tutor'):
        return None, (jsonify({'error': 'Acesso negado'}), 403)
    return user, None

@courses_bp.route('/admin/courses', methods=['GET'])
def admin_list_courses():
    user, err = _course_admin_required()
    if err: return err
    from models import TrailCourse, Trail, Progress
    courses = Course.query.all()
    result = []
    for c in courses:
        modules = c.modules
        all_mats = []
        for m in modules:
            all_mats.extend(m.materials)
        has_video = any(m.video_url for m in modules)
        has_pdf = any(mat.tipo == 'pdf' for mat in all_mats)
        enrolled_ids = {p.user_id for p in Progress.query.filter_by(course_id=c.id, tenant_id=current_tenant_id()).all()}
        total_lessons = len(modules)
        avg_progress = 0
        if enrolled_ids and total_lessons > 0:
            user_pcts = []
            for uid2 in enrolled_ids:
                passed = Progress.query.filter_by(course_id=c.id, user_id=uid2, passed=True, tenant_id=current_tenant_id()).count()
                user_pcts.append(round(passed / total_lessons * 100))
            avg_progress = round(sum(user_pcts) / len(user_pcts)) if user_pcts else 0
        tc = TrailCourse.query.filter_by(course_id=c.id).first()
        trail_name = None
        if tc:
            t = Trail.query.get(tc.trail_id)
            trail_name = t.name if t else None
        result.append({
            'id': c.id, 'name': c.name,
            'category': c.tag or (c.resumo[:30] if c.resumo else 'Geral'),
            'color': c.color or '#008ea8',
            'total_lessons': total_lessons,
            'enrolled_users': len(enrolled_ids),
            'avg_progress': avg_progress,
            'has_video': has_video,
            'has_pdf': has_pdf,
            'trail_name': trail_name,
            'status': c.status or 'published',
        })
    return jsonify({'courses': result})

@courses_bp.route('/admin/courses/<int:course_id>/lessons', methods=['GET'])
def admin_get_lessons(course_id):
    user, err = _course_admin_required()
    if err: return err
    modules = Module.query.filter_by(course_id=course_id).order_by(Module.position).all()
    result = []
    for m in modules:
        quiz = Quiz.query.filter_by(module_id=m.id).first()
        exercise = None
        if quiz:
            exercise = {'id': quiz.id, 'question': quiz.q, 'options': quiz.opts or [], 'correct_index': quiz.ans or 0}
        result.append({
            'id': m.id, 'nome': m.nome, 'position': m.position or 0,
            'dur': m.dur or '',
            'video_url': m.video_url or '',
            'materials': [{'id': mat.id, 'name': mat.name, 'url': mat.url, 'tipo': mat.tipo} for mat in m.materials],
            'exercise': exercise
        })
    return jsonify({'lessons': result})

@courses_bp.route('/admin/courses/<int:course_id>/lessons/reorder', methods=['PUT'])
def admin_reorder_lessons(course_id):
    user, err = _course_admin_required()
    if err: return err
    data = request.get_json() or {}
    lesson_ids = data.get('lesson_ids', [])
    for idx, lid in enumerate(lesson_ids, 1):
        m = Module.query.get(lid)
        if m and m.course_id == course_id:
            m.position = idx
    db.session.commit()
    return jsonify({'success': True})

@courses_bp.route('/admin/lessons/<int:lesson_id>', methods=['PUT'])
def admin_update_lesson(lesson_id):
    user, err = _course_admin_required()
    if err: return err
    m = Module.query.get_or_404(lesson_id)
    data = request.get_json() or {}
    if 'nome' in data: m.nome = data['nome']
    if 'dur' in data: m.dur = data['dur']
    if 'video_url' in data:
        url = (data['video_url'] or '').strip()
        if url:
            allowed = ('youtube.com', 'youtu.be', 'vimeo.com')
            if not any(d in url for d in allowed):
                return jsonify({'error': 'URL de vídeo inválida. Use YouTube ou Vimeo.'}), 400
        m.video_url = url or None
    db.session.commit()
    return jsonify({'success': True})

@courses_bp.route('/admin/lessons/<int:lesson_id>/materials', methods=['POST'])
def admin_add_material(lesson_id):
    user, err = _course_admin_required()
    if err: return err
    m = Module.query.get_or_404(lesson_id)
    data = request.get_json() or {}
    mat = Material(course_id=m.course_id, module_id=m.id,
                   name=data.get('name', 'Material'),
                   url=data.get('url', ''),
                   tipo=data.get('tipo', 'link'))
    db.session.add(mat)
    db.session.commit()
    return jsonify({'success': True, 'id': mat.id, 'name': mat.name, 'url': mat.url, 'tipo': mat.tipo})

@courses_bp.route('/admin/materials/<int:material_id>', methods=['DELETE'])
def admin_delete_material(material_id):
    user, err = _course_admin_required()
    if err: return err
    mat = Material.query.get_or_404(material_id)
    db.session.delete(mat)
    db.session.commit()
    return jsonify({'success': True})

@courses_bp.route('/admin/lessons/<int:lesson_id>/exercise', methods=['PUT'])
def admin_update_exercise(lesson_id):
    user, err = _course_admin_required()
    if err: return err
    m = Module.query.get_or_404(lesson_id)
    data = request.get_json() or {}
    quiz = Quiz.query.filter_by(module_id=m.id).first()
    if not quiz:
        quiz = Quiz(course_id=m.course_id, module_id=m.id,
                    q=data.get('question', ''), opts=data.get('options', []), ans=data.get('correct_index', 0))
        db.session.add(quiz)
    else:
        quiz.q = data.get('question', quiz.q)
        quiz.opts = data.get('options', quiz.opts)
        quiz.ans = data.get('correct_index', quiz.ans)
    db.session.commit()
    return jsonify({'success': True})

@courses_bp.route('/admin/lessons/<int:lesson_id>', methods=['DELETE'])
def admin_delete_lesson(lesson_id):
    user, err = _course_admin_required()
    if err: return err
    m = Module.query.get_or_404(lesson_id)
    db.session.delete(m)  # cascade deletes materials, quiz, progress
    db.session.commit()
    return jsonify({'success': True})

