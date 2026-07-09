"""
IBC Ensino Backend — Flask App
Autenticação real com SQLite, permissões por perfil, API REST
"""
import os
import uuid
from flask import Flask, jsonify, session, request, send_from_directory
from flask_cors import CORS
from datetime import timedelta
from dotenv import load_dotenv
from extensions import db, limiter

# Carrega .env ANTES de qualquer leitura de os.getenv — python-dotenv estava
# em requirements.txt mas load_dotenv() nunca era chamado: um .env local com
# SECRET_KEY/DATABASE_URL/ADMIN_* era silenciosamente ignorado.
load_dotenv()

ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_MB = 20

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ──────────────────────────────────────────────────────
# Configuração
# ──────────────────────────────────────────────────────

def create_app(config_name='development'):
    """Factory para criar instância Flask"""
    app = Flask(__name__)

    # Detecta produção via parâmetro explícito, FLASK_ENV ou execução na Vercel
    is_production = (
        config_name == 'production'
        or os.getenv('FLASK_ENV') == 'production'
        or os.getenv('VERCEL') == '1'
    )

    # Config
    basedir = os.path.abspath(os.path.dirname(__file__))
    instance_dir = os.path.join(basedir, 'instance')
    if is_production:
        # Vercel só permite escrita em /tmp (efêmero entre invocações)
        uploads_dir = '/tmp/uploads'
    else:
        uploads_dir = os.path.join(basedir, 'uploads')
    os.makedirs(instance_dir, exist_ok=True)
    os.makedirs(uploads_dir, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = uploads_dir
    app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_MB * 1024 * 1024

    # DATABASE_URL: Postgres (Neon) em produção, SQLite local em dev
    default_db = f"sqlite:///{os.path.join(instance_dir, 'ibc_ensino.db')}"
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        if database_url.startswith('postgresql://'):
            database_url = database_url.replace('postgresql://', 'postgresql+psycopg2://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = default_db
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    secret_key = os.getenv('SECRET_KEY')
    if not secret_key:
        if is_production:
            raise RuntimeError(
                'SECRET_KEY não definida. Configure a variável de ambiente SECRET_KEY '
                'antes de rodar em produção (gere com: python -c "import secrets; print(secrets.token_hex(32))").'
            )
        secret_key = 'dev-secret-key-change-in-prod'
    app.config['SECRET_KEY'] = secret_key
    app.config['SESSION_PERMANENT'] = True
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
    app.config['SESSION_COOKIE_SECURE'] = is_production
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # Database
    db.init_app(app)

    # Rate limiting (login/forgot-password — ver decorators em routes/auth.py)
    limiter.init_app(app)

    # CORS (permitir requisições do frontend)
    # Nota: nada de curingas tipo 'https://*.vercel.app' aqui — o Flask-CORS trata
    # a string como regex, onde esse padrão não casa com subdomínios reais mas
    # aceita qualquer domínio registrável parecido (ex.: https://xvercelyapp.com),
    # o que com supports_credentials=True é uma falha de segurança. Usar sempre
    # origens exatas.
    cors_origins = ['http://localhost:3000', 'http://localhost:5000']
    app_url = os.getenv('APP_URL')
    if app_url:
        cors_origins.append(app_url)
    railway_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN')
    if railway_domain:
        cors_origins.append(f'https://{railway_domain}')
    CORS(app, supports_credentials=True,
         origins=cors_origins,
         allow_headers=['Content-Type', 'Authorization'])
    
    # Context
    with app.app_context():
        # Importar modelos
        from models import User, Course, Material, Module, Quiz, Progress, Question, Category, Trail, TrailCourse, UserTrail, OnboardingAnswer, Certificate, Announcement, Notification, AnnouncementDismissal, PlatformConfig, Level, Achievement, UserAchievement, StudySession, ActivityFeed
        # Tenancy (Release 0.9): tabelas gerenciadas por Alembic; registrar os
        # models aqui faz o create_all de dev/teste criá-las também (pula as
        # existentes) até o schema legado ser baselineado na Fase 3.
        from core.tenancy import Tenant, TenantUser
        
        # Criar tabelas
        db.create_all()
        
        # Registrar blueprints (rotas)
        from routes.auth import auth_bp
        from routes.courses import courses_bp
        from routes.progress import progress_bp
        from routes.questions import questions_bp
        from routes.lessons import lessons_bp
        from routes.materials import materials_bp
        from routes.gamification import gamification_bp
        from routes.dashboards import dashboards_bp
        from routes.trails import trails_bp, onboarding_bp
        from routes.certificates import certificates_bp
        from routes.admin import admin_bp
        from routes.notifications import notifications_bp
        from routes.aluno import aluno_bp

        app.register_blueprint(auth_bp, url_prefix='/api/auth')
        app.register_blueprint(courses_bp, url_prefix='/api/courses')
        app.register_blueprint(progress_bp, url_prefix='/api/progress')
        app.register_blueprint(questions_bp, url_prefix='/api/questions')
        app.register_blueprint(lessons_bp, url_prefix='/api/courses')
        app.register_blueprint(materials_bp, url_prefix='/api/materiais')
        app.register_blueprint(gamification_bp, url_prefix='/api/gamification')
        app.register_blueprint(dashboards_bp, url_prefix='/api')
        app.register_blueprint(trails_bp, url_prefix='/api/trails')
        app.register_blueprint(onboarding_bp, url_prefix='/api/onboarding')
        app.register_blueprint(certificates_bp, url_prefix='/api/certificates')
        app.register_blueprint(admin_bp, url_prefix='/api/admin')
        app.register_blueprint(notifications_bp, url_prefix='/api')
        app.register_blueprint(aluno_bp, url_prefix='/api/aluno')

        # Convenience alias so GET /api/user works alongside /api/auth/user
        @app.route('/api/user', methods=['GET'])
        def api_user():
            from routes.auth import get_user
            return get_user()
        
        # Upload PDF
        # Nota: em produção (Vercel) os arquivos são salvos em /tmp, que é efêmero
        # entre invocações serverless — usar links externos para materiais em produção.
        @app.route('/api/upload', methods=['POST'])
        def upload_file():
            uid = session.get('user_id')
            if not uid:
                return jsonify({'error': 'Não autenticado'}), 401
            if 'file' not in request.files:
                return jsonify({'error': 'Nenhum arquivo enviado'}), 400
            f = request.files['file']
            if not f or f.filename == '':
                return jsonify({'error': 'Arquivo inválido'}), 400
            if not allowed_file(f.filename):
                return jsonify({'error': 'Apenas arquivos PDF são permitidos'}), 400
            ext = f.filename.rsplit('.', 1)[1].lower()
            safe_name = f"{uuid.uuid4().hex}.{ext}"
            f.save(os.path.join(uploads_dir, safe_name))
            size_mb = round(os.path.getsize(os.path.join(uploads_dir, safe_name)) / 1024 / 1024, 2)
            return jsonify({
                'url': f'/uploads/{safe_name}',
                'original_name': f.filename,
                'size': f'{size_mb} MB',
            }), 201

        # Serve uploaded files (including materials/ subdir)
        @app.route('/uploads/<path:filename>', methods=['GET'])
        def serve_upload(filename):
            # Prevent path traversal
            import posixpath
            safe = posixpath.normpath(filename)
            if safe.startswith('..'):
                return jsonify({'error': 'Acesso negado'}), 403

            uid = session.get('user_id')
            user = User.query.get(uid) if uid else None
            if not user:
                return jsonify({'error': 'Não autenticado'}), 401

            # Se o arquivo é um material de curso registrado, aplica a mesma
            # regra de acesso usada em routes/materials.py (get_material).
            material = Material.query.filter_by(url=f'/uploads/{safe}').first()
            if material:
                from routes.materials import _can_access_material
                if not _can_access_material(user, material):
                    return jsonify({'error': 'Acesso negado'}), 403

            return send_from_directory(uploads_dir, safe)

        # Serve SVG icon sprite
        @app.route('/css/icons/sprite.svg', methods=['GET'])
        def serve_icon_sprite():
            icons_dir = os.path.join(basedir, 'css', 'icons')
            resp = send_from_directory(icons_dir, 'sprite.svg')
            resp.headers['Content-Type'] = 'image/svg+xml'
            resp.headers['Cache-Control'] = 'public, max-age=86400'
            return resp

        # Serve image assets (logo etc.)
        @app.route('/images/<path:filename>', methods=['GET'])
        def serve_images(filename):
            import posixpath
            safe = posixpath.normpath(filename)
            if safe.startswith('..'):
                return jsonify({'error': 'Acesso negado'}), 403
            return send_from_directory(os.path.join(basedir, 'images'), safe)

        # Favicon
        @app.route('/favicon.svg', methods=['GET'])
        def favicon():
            return send_from_directory(basedir, 'favicon.svg')

        # Serve CSS design system files
        @app.route('/css/<path:filename>', methods=['GET'])
        def serve_css(filename):
            css_dir = os.path.join(basedir, 'css')
            return send_from_directory(css_dir, filename)

        # Health check
        @app.route('/health', methods=['GET'])
        def health():
            return jsonify({'status': 'ok', 'db': 'connected'}), 200
        
        # Serve frontend
        @app.route('/index.html', methods=['GET'])
        @app.route('/app', methods=['GET'])
        def frontend():
            return send_from_directory(basedir, 'index.html')

        # Home
        @app.route('/', methods=['GET'])
        def home():
            return send_from_directory(basedir, 'index.html')
    
    return app

# ──────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────

if __name__ == '__main__':
    app = create_app()
    # Replit usa 0.0.0.0:5000 por padrão
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
