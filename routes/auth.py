"""
Auth routes: signup, login, logout, user info, password reset
"""
from flask import Blueprint, request, jsonify, session
from extensions import db
from models import User

auth_bp = Blueprint('auth', __name__)


def _current_user():
    uid = session.get('user_id')
    if uid:
        return User.query.get(uid)
    return None


@auth_bp.route('/signup', methods=['POST'])
def signup():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    role = data.get('role', 'aluno_externo')

    if not name or not email or not password:
        return jsonify({'error': 'name, email e password são obrigatórios'}), 400

    if len(password) < 6:
        return jsonify({'error': 'A senha deve ter ao menos 6 caracteres'}), 400

    valid_roles = {'aluno_externo', 'aluno_interno', 'tutor', 'admin'}
    if role not in valid_roles:
        role = 'aluno_externo'

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email já cadastrado'}), 409

    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session['user_id'] = user.id
    return jsonify(user.to_dict()), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'email e password são obrigatórios'}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({'error': 'Email ou senha inválidos'}), 401

    session['user_id'] = user.id
    return jsonify(user.to_dict()), 200


@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logout realizado com sucesso'}), 200


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """Allows an authenticated user to change their own password."""
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    data = request.get_json(silent=True) or {}
    old_password = data.get('old_password') or ''
    new_password = data.get('new_password') or ''

    if not old_password or not new_password:
        return jsonify({'error': 'old_password e new_password são obrigatórios'}), 400

    if not user.check_password(old_password):
        return jsonify({'error': 'Senha atual incorreta'}), 401

    if len(new_password) < 6:
        return jsonify({'error': 'A nova senha deve ter ao menos 6 caracteres'}), 400

    user.set_password(new_password)
    db.session.commit()
    return jsonify({'message': 'Senha alterada com sucesso'}), 200


@auth_bp.route('/user', methods=['GET'])
def get_user():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401
    return jsonify(user.to_dict()), 200


@auth_bp.route('/users', methods=['GET'])
def list_users():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401
    if user.role not in ('admin', 'tutor'):
        return jsonify({'error': 'Acesso negado'}), 403
    users = User.query.order_by(User.created_at).all()
    return jsonify([u.to_dict() for u in users]), 200


@auth_bp.route('/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401
    if user.role != 'admin':
        return jsonify({'error': 'Acesso negado'}), 403
    if user.id == user_id:
        return jsonify({'error': 'Não é possível remover a si mesmo'}), 400
    target = User.query.get_or_404(user_id)
    db.session.delete(target)
    db.session.commit()
    return jsonify({'message': 'Usuário removido'}), 200
