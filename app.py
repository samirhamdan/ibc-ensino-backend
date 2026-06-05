"""
IBC Ensino Backend — Flask App
Autenticação real com SQLite, permissões por perfil, API REST
"""
import os
from flask import Flask, jsonify, session, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import timedelta

# ──────────────────────────────────────────────────────
# Configuração
# ──────────────────────────────────────────────────────

db = SQLAlchemy()

def create_app(config_name='development'):
    """Factory para criar instância Flask"""
    app = Flask(__name__)
    
    # Config
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URL', 'sqlite:///instance/ibc_ensino.db'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-prod')
    app.config['SESSION_PERMANENT'] = True
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
    app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only em produção
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
        
        app.register_blueprint(auth_bp, url_prefix='/api/auth')
        app.register_blueprint(courses_bp, url_prefix='/api/courses')
        app.register_blueprint(progress_bp, url_prefix='/api/progress')
        app.register_blueprint(questions_bp, url_prefix='/api/questions')
        
        # Health check
        @app.route('/health', methods=['GET'])
        def health():
            return jsonify({'status': 'ok', 'db': 'connected'}), 200
        
        # Home
        @app.route('/', methods=['GET'])
        def home():
            return jsonify({
                'app': 'IBC Ensino Backend',
                'version': '2.0-beta',
                'endpoints': [
                    'GET  /health',
                    'POST /api/auth/signup',
                    'POST /api/auth/login',
                    'POST /api/auth/logout',
                    'GET  /api/user',
                    'GET  /api/courses',
                    'POST /api/courses',
                    'GET  /api/progress/<courseId>',
                    'POST /api/progress/<courseId>',
                    'GET  /api/questions/<courseId>',
                    'POST /api/questions/<courseId>',
                ]
            }), 200
    
    return app

# ──────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────

if __name__ == '__main__':
    app = create_app()
    # Replit usa 0.0.0.0:5000 por padrão
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
