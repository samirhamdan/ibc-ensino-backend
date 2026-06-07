"""
IBC Ensino Backend — Flask App
Autenticação real com SQLite, permissões por perfil, API REST
"""
import os
import uuid
from flask import Flask, jsonify, session, request, send_from_directory
from flask_cors import CORS
from datetime import timedelta
from extensions import db

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
    
    # Config
    basedir = os.path.abspath(os.path.dirname(__file__))
    instance_dir = os.path.join(basedir, 'instance')
    uploads_dir = os.path.join(basedir, 'uploads')
    os.makedirs(instance_dir, exist_ok=True)
    os.makedirs(uploads_dir, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = uploads_dir
    app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_MB * 1024 * 1024
    default_db = f"sqlite:///{os.path.join(instance_dir, 'ibc_ensino.db')}"
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', default_db)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-prod')
    app.config['SESSION_PERMANENT'] = True
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
    app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    
    # Database
    db.init_app(app)
    
    # CORS (permitir requisições do frontend)
    CORS(app, supports_credentials=True, 
         origins=['http://localhost:3000', 'http://localhost:5000', 'https://*.replit.dev'],
         allow_headers=['Content-Type', 'Authorization'])
    
    # Context
    with app.app_context():
        # Importar modelos
        from models import User, Course, Material, Module, Quiz, Progress, Question, Category
        
        # Criar tabelas
        db.create_all()
        
        # Registrar blueprints (rotas)
        from routes.auth import auth_bp
        from routes.courses import courses_bp
        from routes.progress import progress_bp
        from routes.questions import questions_bp
        from routes.lessons import lessons_bp

        app.register_blueprint(auth_bp, url_prefix='/api/auth')
        app.register_blueprint(courses_bp, url_prefix='/api/courses')
        app.register_blueprint(progress_bp, url_prefix='/api/progress')
        app.register_blueprint(questions_bp, url_prefix='/api/questions')
        app.register_blueprint(lessons_bp, url_prefix='/api/courses')

        # Convenience alias so GET /api/user works alongside /api/auth/user
        @app.route('/api/user', methods=['GET'])
        def api_user():
            from routes.auth import get_user
            return get_user()
        
        # Upload PDF
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

        # Serve uploaded files
        @app.route('/uploads/<path:filename>', methods=['GET'])
        def serve_upload(filename):
            return send_from_directory(uploads_dir, filename)

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
