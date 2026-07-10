"""
Auth routes: signup, login, logout, user info, password reset
"""
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Blueprint, request, jsonify, session
from extensions import db, limiter
from core.tenancy import current_tenant_id, role_no_tenant
from models import User, PasswordResetToken

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
    role = data.get('role', 'aluno')

    if not name or not email or not password:
        return jsonify({'error': 'name, email e password são obrigatórios'}), 400

    if len(password) < 6:
        return jsonify({'error': 'A senha deve ter ao menos 6 caracteres'}), 400

    # Só um admin autenticado pode escolher o role (uso: tela de cadastro de
    # usuários do admin). Qualquer outra requisição (anônima ou não-admin)
    # sempre cria um 'aluno', independentemente do que for enviado.
    requester = _current_user()
    valid_roles = {'aluno', 'tutor', 'admin'}
    if requester and role_no_tenant(requester) == 'admin' and role in valid_roles:
        pass
    else:
        role = 'aluno'

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email já cadastrado'}), 409

    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session['user_id'] = user.id
    from core.tenancy import current_tenant_id, vincular_usuario_ao_tenant
    session['tenant_id'] = str(current_tenant_id())
    vincular_usuario_ao_tenant(user)
    return jsonify(user.to_dict()), 201


@auth_bp.route('/login', methods=['POST'])
@limiter.limit('10 per minute')
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'email e password são obrigatórios'}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({'error': 'Email ou senha inválidos'}), 401

    if not user.is_active:
        return jsonify({'error': 'Conta desativada. Contate o administrador.'}), 403

    user.last_login = datetime.utcnow()
    db.session.commit()

    session['user_id'] = user.id
    # Etapa 4.2: sessão presa ao tenant onde foi criada (middleware barra uso
    # cruzado com 403) + vínculo de papel por tenant garantido no login.
    from core.tenancy import current_tenant_id, vincular_usuario_ao_tenant
    session['tenant_id'] = str(current_tenant_id())
    vincular_usuario_ao_tenant(user)

    # +5 XP de login diário, no máximo 1x por dia (guard: last_activity_date).
    # Concedido aqui no servidor — a ação 'daily_login' não é mais aceita via
    # /gamification/add-points, onde podia ser repetida à vontade.
    from routes.gamification import check_and_grant_achievements, award_points, _get_or_create_points
    up = _get_or_create_points(user.id)
    if up.last_activity_date != datetime.utcnow().date():
        award_points(user.id, 'daily_login')
    else:
        db.session.commit()

    new_achievements = check_and_grant_achievements(user.id)

    data_out = user.to_dict()
    data_out['new_achievements'] = new_achievements
    return jsonify(data_out), 200


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


@auth_bp.route('/profile', methods=['PUT'])
def update_profile():
    """Allows an authenticated user to update their own editable profile fields."""
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()

    if not name:
        return jsonify({'error': 'name é obrigatório'}), 400
    if len(name) < 3:
        return jsonify({'error': 'Nome deve ter pelo menos 3 caracteres'}), 400

    user.name = name
    db.session.commit()
    return jsonify(user.to_dict()), 200


@auth_bp.route('/password', methods=['PUT'])
def change_password():
    """New password-change flow for the 'Meu Perfil' UI (Sprint 6.1).
    Separate from the legacy POST /reset-password endpoint, left untouched."""
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password') or ''
    new_password = data.get('new_password') or ''
    confirm_password = data.get('confirm_password') or ''

    if not current_password or not new_password or not confirm_password:
        return jsonify({'error': 'current_password, new_password e confirm_password são obrigatórios'}), 400

    if not user.check_password(current_password):
        return jsonify({'error': 'Senha atual incorreta'}), 401

    if new_password != confirm_password:
        return jsonify({'error': 'As senhas não coincidem'}), 400

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
    if role_no_tenant(user) not in ('admin', 'tutor'):
        return jsonify({'error': 'Acesso negado'}), 403
    users = User.query.order_by(User.created_at).all()
    return jsonify([u.to_dict() for u in users]), 200


@auth_bp.route('/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401
    if role_no_tenant(user) != 'admin':
        return jsonify({'error': 'Acesso negado'}), 403
    if user.id == user_id:
        return jsonify({'error': 'Não é possível remover a si mesmo'}), 400
    target = User.query.get_or_404(user_id)

    # Referências que apontam para o usuário mas não são "posse" dele: precisam
    # ser anuladas/removidas antes do delete, senão o Postgres viola FK → 500.
    from models import Course, Question, Notification, TutorCourse
    Course.query.filter_by(tenant_id=current_tenant_id(), tutor_id=user_id).update({'tutor_id': None})
    Question.query.filter_by(tenant_id=current_tenant_id(), assigned_tutor_id=user_id).update({'assigned_tutor_id': None})
    Notification.query.filter_by(tenant_id=current_tenant_id(), created_by=user_id).update({'created_by': None})
    TutorCourse.query.filter_by(tenant_id=current_tenant_id(), tutor_id=user_id).delete()

    db.session.delete(target)
    db.session.commit()
    return jsonify({'message': 'Usuário removido'}), 200


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    if not name or len(name) < 3:
        return jsonify({'error': 'Nome deve ter pelo menos 3 caracteres'}), 400
    if not email or '@' not in email:
        return jsonify({'error': 'E-mail inválido'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'E-mail já cadastrado'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Senha deve ter pelo menos 6 caracteres'}), 400
    if password != confirm_password:
        return jsonify({'error': 'As senhas não coincidem'}), 400

    user = User(name=name, email=email, role='aluno')
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Conta criada com sucesso! Faça login para continuar.'}), 201


def _send_reset_email(to_email, to_name, reset_url):
    """Send password reset email via SMTP (Gmail)."""
    smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', 587))
    smtp_user = os.getenv('SMTP_USER', '')
    smtp_pass = os.getenv('SMTP_PASS', '')
    from_name = os.getenv('EMAIL_FROM_NAME', 'IBC Ensino')

    if not smtp_user or not smtp_pass:
        return False, 'Email não configurado no servidor'

    html = f"""
    <div style="font-family:sans-serif;max-width:500px;margin:auto;padding:2rem">
      <h2 style="color:#1a2e52">🔑 Redefinição de Senha</h2>
      <p>Olá, <strong>{to_name}</strong>!</p>
      <p>Recebemos uma solicitação para redefinir sua senha na plataforma <strong>IBC Ensino</strong>.</p>
      <div style="text-align:center;margin:2rem 0">
        <a href="{reset_url}" style="background:#c9a84c;color:#fff;padding:.9rem 2rem;border-radius:8px;text-decoration:none;font-weight:bold;font-size:1rem">
          Redefinir minha senha
        </a>
      </div>
      <p style="color:#666;font-size:.85rem">Este link expira em <strong>1 hora</strong>. Se você não solicitou, ignore este email.</p>
      <hr style="border:none;border-top:1px solid #eee;margin:1.5rem 0">
      <p style="color:#999;font-size:.75rem;text-align:center">IBC Ensino — Igreja Batista Central</p>
    </div>
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Redefinição de senha — IBC Ensino'
    msg['From'] = f'{from_name} <{smtp_user}>'
    msg['To'] = to_email
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        return True, 'OK'
    except Exception as e:
        return False, str(e)


@auth_bp.route('/forgot-password', methods=['POST'])
@limiter.limit('5 per hour')
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({'error': 'Email é obrigatório'}), 400

    user = User.query.filter_by(email=email).first()
    # Always return success to avoid email enumeration
    if not user:
        return jsonify({'message': 'Se o email existir, você receberá as instruções.'}), 200

    # Invalidate old tokens
    PasswordResetToken.query.filter_by(user_id=user.id, used=False).update({'used': True})

    token_obj = PasswordResetToken.generate(user.id)
    db.session.add(token_obj)
    db.session.commit()

    base_url = os.getenv('APP_URL', 'http://localhost:5000')
    reset_url = f"{base_url}/?reset_token={token_obj.token}"

    ok, msg = _send_reset_email(user.email, user.name, reset_url)
    if not ok:
        return jsonify({'error': f'Erro ao enviar email: {msg}'}), 500

    return jsonify({'message': 'Se o email existir, você receberá as instruções.'}), 200


@auth_bp.route('/reset-password-token', methods=['POST'])
def reset_password_token():
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    new_password = data.get('new_password') or ''

    if not token or not new_password:
        return jsonify({'error': 'token e new_password são obrigatórios'}), 400

    if len(new_password) < 6:
        return jsonify({'error': 'A senha deve ter ao menos 6 caracteres'}), 400

    token_obj = PasswordResetToken.query.filter_by(token=token).first()
    if not token_obj or not token_obj.is_valid():
        return jsonify({'error': 'Token inválido ou expirado'}), 400

    token_obj.user.set_password(new_password)
    token_obj.used = True
    db.session.commit()

    return jsonify({'message': 'Senha redefinida com sucesso!'}), 200
