"""
SQLAlchemy models for IBC Ensino
"""
from datetime import datetime
from extensions import db
import bcrypt


class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    courses = db.relationship('Course', backref='category_rel', lazy=True)

    def to_dict(self):
        return {'id': self.id, 'name': self.name}


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='aluno_externo')
    # roles: admin | tutor | aluno_interno | aluno_externo
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    progress = db.relationship('Progress', backref='user', lazy=True, cascade='all, delete-orphan')
    questions = db.relationship('Question', backref='author', lazy=True, cascade='all, delete-orphan')

    def set_password(self, plain: str):
        self.password_hash = bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

    def check_password(self, plain: str) -> bool:
        return bcrypt.checkpw(plain.encode(), self.password_hash.encode())

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'role': self.role,
            'created_at': self.created_at.isoformat(),
        }


class Course(db.Model):
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    icon = db.Column(db.String(10), default='📖')
    acesso = db.Column(db.String(20), nullable=False, default='publico')
    # acesso: interno | publico
    resumo = db.Column(db.Text, default='')
    duracao = db.Column(db.String(50), default='')
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tutor = db.relationship('User', foreign_keys=[tutor_id])
    modules = db.relationship('Module', backref='course', lazy=True, cascade='all, delete-orphan',
                               order_by='Module.position')
    materials = db.relationship('Material', backref='course', lazy=True, cascade='all, delete-orphan')
    quiz = db.relationship('Quiz', backref='course', lazy=True, cascade='all, delete-orphan',
                           order_by='Quiz.position')
    questions = db.relationship('Question', backref='course', lazy=True, cascade='all, delete-orphan')
    progress = db.relationship('Progress', backref='course', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, include_details=False):
        data = {
            'id': self.id,
            'name': self.name,
            'icon': self.icon,
            'acesso': self.acesso,
            'resumo': self.resumo,
            'duracao': self.duracao,
            'category': self.category_rel.name if self.category_rel else None,
            'category_id': self.category_id,
            'tutor_id': self.tutor_id,
        }
        if include_details:
            data['modules'] = [m.to_dict() for m in self.modules]
            data['materiais'] = [m.to_dict() for m in self.materials]
            data['quiz'] = [q.to_dict() for q in self.quiz]
        return data


class Module(db.Model):
    __tablename__ = 'modules'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    nome = db.Column(db.String(200), nullable=False)
    dur = db.Column(db.String(50), default='')
    position = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {'id': self.id, 'nome': self.nome, 'dur': self.dur, 'position': self.position}


class Material(db.Model):
    __tablename__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.Text, nullable=False)
    tipo = db.Column(db.String(10), default='link')  # pdf | link
    size = db.Column(db.String(20), default='')

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'url': self.url, 'tipo': self.tipo, 'size': self.size}


class Quiz(db.Model):
    __tablename__ = 'quiz'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    q = db.Column(db.Text, nullable=False)
    opts = db.Column(db.JSON, nullable=False)   # list of strings
    ans = db.Column(db.Integer, nullable=False)  # index of correct option
    exp = db.Column(db.Text, default='')
    position = db.Column(db.Integer, default=0)

    def to_dict(self, hide_answer=True):
        data = {'id': self.id, 'q': self.q, 'opts': self.opts, 'exp': self.exp}
        if not hide_answer:
            data['ans'] = self.ans
        return data


class Progress(db.Model):
    __tablename__ = 'progress'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    material_done = db.Column(db.Boolean, default=False)
    quiz_score = db.Column(db.Integer, default=0)
    quiz_total = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'course_id', name='uq_user_course'),)

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'course_id': self.course_id,
            'material_done': self.material_done,
            'quiz_score': self.quiz_score,
            'quiz_total': self.quiz_total,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Question(db.Model):
    __tablename__ = 'questions'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    texto = db.Column(db.Text, nullable=False)
    resposta = db.Column(db.Text, default='')
    respondido_por = db.Column(db.String(150), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'course_id': self.course_id,
            'autor': self.author.name if self.author else '',
            'texto': self.texto,
            'resposta': self.resposta,
            'respondido_por': self.respondido_por,
            'created_at': self.created_at.isoformat(),
        }
