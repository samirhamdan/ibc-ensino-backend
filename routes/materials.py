"""
Material routes: PDF viewer metadata + read-progress tracking
"""
import os
from datetime import datetime
from flask import Blueprint, request, jsonify, session, current_app
from extensions import db
from models import Material, User, LessonProgress, Course

materials_bp = Blueprint('materials', __name__)


def _current_user():
    uid = session.get('user_id')
    if uid:
        return User.query.get(uid)
    return None


def _can_access_material(user, material):
    if user.role in ('admin', 'tutor'):
        return True
    course = Course.query.get(material.course_id)
    if not course:
        return False
    if course.acesso == 'publico':
        return True
    return user.role == 'aluno_interno'


@materials_bp.route('/<int:material_id>', methods=['GET'])
def get_material(material_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    material = Material.query.get_or_404(material_id)
    if not _can_access_material(user, material):
        return jsonify({'error': 'Acesso negado'}), 403

    file_size = None
    uploaded_at = None
    if material.url.startswith('/uploads/'):
        path = os.path.join(current_app.config['UPLOAD_FOLDER'], os.path.basename(material.url))
        if os.path.exists(path):
            file_size = os.path.getsize(path)
            uploaded_at = datetime.utcfromtimestamp(os.path.getmtime(path)).isoformat()

    return jsonify({
        'id': material.id,
        'name': material.name,
        'file_url': material.url,
        'file_size': file_size,
        'pages': None,
        'uploaded_at': uploaded_at,
    }), 200


@materials_bp.route('/<int:material_id>/read-progress', methods=['POST'])
def save_read_progress(material_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    material = Material.query.get_or_404(material_id)
    if not material.module_id:
        return jsonify({'error': 'Material não vinculado a uma aula'}), 400

    data = request.get_json(silent=True) or {}
    pages_viewed = data.get('pages_viewed') or []
    time_spent = int(data.get('time_spent') or 0)
    current_page = data.get('current_page')
    total_pages = data.get('total_pages')

    prog = LessonProgress.query.filter_by(user_id=user.id, module_id=material.module_id).first()
    if not prog:
        prog = LessonProgress(user_id=user.id, course_id=material.course_id, module_id=material.module_id)
        db.session.add(prog)

    existing = set(prog.material_pages_viewed or [])
    existing.update(pages_viewed)
    prog.material_pages_viewed = sorted(existing)
    prog.material_time_spent = (prog.material_time_spent or 0) + time_spent
    prog.material_read_at = datetime.utcnow()
    if total_pages:
        prog.material_percentage = round(len(existing) / total_pages * 100, 1)

    db.session.commit()
    return jsonify({'saved': True}), 200
