"""
Material routes: PDF viewer metadata + read-progress tracking + upload
"""
import os
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, session, current_app, send_from_directory
from werkzeug.utils import secure_filename
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
    return user.role == 'aluno'


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
    crossed_50 = False
    if total_pages:
        before = prog.material_percentage or 0.0
        prog.material_percentage = round(len(existing) / total_pages * 100, 1)
        crossed_50 = before < 50 and prog.material_percentage >= 50

    db.session.commit()
    return jsonify({'saved': True, 'crossed_50': crossed_50}), 200


@materials_bp.route('/upload', methods=['POST'])
def upload_material():
    user = _current_user()
    if not user or user.role not in ('admin', 'tutor'):
        return jsonify({'error': 'Acesso negado'}), 403

    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400

    f = request.files['file']
    if not f or f.filename == '':
        return jsonify({'error': 'Arquivo inválido'}), 400

    fname = f.filename.lower()
    if not fname.endswith('.pdf'):
        return jsonify({'error': 'Apenas arquivos PDF são permitidos'}), 400

    # Read into memory to check size (10 MB limit)
    data = f.read()
    if len(data) > 10 * 1024 * 1024:
        return jsonify({'error': 'Arquivo muito grande. Limite: 10 MB'}), 413

    # Check PDF magic bytes
    if not data.startswith(b'%PDF'):
        return jsonify({'error': 'Arquivo não é um PDF válido'}), 400

    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'materials')
    os.makedirs(upload_dir, exist_ok=True)

    safe = secure_filename(f.filename)
    filename = f'{uuid.uuid4().hex}_{safe}'
    path = os.path.join(upload_dir, filename)
    with open(path, 'wb') as fp:
        fp.write(data)

    size_mb = round(len(data) / 1024 / 1024, 2)
    return jsonify({
        'url': f'/uploads/materials/{filename}',
        'original_name': f.filename,
        'size': f'{size_mb} MB',
    }), 201


@materials_bp.route('/files/materials/<path:filename>', methods=['GET'])
def serve_material_file(filename):
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'materials')
    return send_from_directory(upload_dir, filename)
