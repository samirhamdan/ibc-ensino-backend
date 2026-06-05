"""
Course routes: CRUD for courses, modules, materials
"""
from flask import Blueprint, request, jsonify, session
from extensions import db
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

    # Alunos externos e usuários não autenticados only see public courses
    if not user or user.role == 'aluno_externo':
        query = query.filter_by(acesso='publico')

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

    if course.acesso == 'interno' and (not user or user.role == 'aluno_externo'):
        return jsonify({'error': 'Acesso negado'}), 403

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

    for field in ('name', 'icon', 'acesso', 'resumo', 'duracao'):
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
