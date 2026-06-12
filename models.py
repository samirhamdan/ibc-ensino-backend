"""
SQLAlchemy models for IBC Ensino
"""
from datetime import datetime, timedelta
from extensions import db
import bcrypt
import secrets


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
    onboarding_completed = db.Column(db.Boolean, default=False)
    active_trail_id = db.Column(db.Integer, db.ForeignKey('trails.id', use_alter=True, name='fk_user_active_trail'), nullable=True)

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
            'onboarding_completed': self.onboarding_completed,
            'active_trail_id': self.active_trail_id,
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
    video_url = db.Column(db.String(500), nullable=True)
    video_provider = db.Column(db.String(20), nullable=True)  # 'youtube' | 'vimeo'

    materials = db.relationship('Material', backref='module', lazy=True, cascade='all, delete-orphan')
    quiz = db.relationship('Quiz', backref='module', lazy=True, cascade='all, delete-orphan',
                           order_by='Quiz.position')

    def to_dict(self):
        return {
            'id': self.id, 'nome': self.nome, 'dur': self.dur, 'position': self.position,
            'video_url': self.video_url, 'video_provider': self.video_provider,
        }


class Material(db.Model):
    __tablename__ = 'materials'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey('modules.id'), nullable=True)
    name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.Text, nullable=False)
    tipo = db.Column(db.String(10), default='link')  # pdf | link
    size = db.Column(db.String(20), default='')
    original_name = db.Column(db.String(255), nullable=True)

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'url': self.url, 'tipo': self.tipo, 'size': self.size,
                'module_id': self.module_id, 'original_name': self.original_name}


class Quiz(db.Model):
    __tablename__ = 'quiz'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey('modules.id'), nullable=True)
    q = db.Column(db.Text, nullable=False)
    opts = db.Column(db.JSON, nullable=False)   # list of strings
    ans = db.Column(db.Integer, nullable=False)  # index of correct option
    exp = db.Column(db.Text, default='')
    position = db.Column(db.Integer, default=0)

    def to_dict(self, hide_answer=True):
        data = {'id': self.id, 'q': self.q, 'opts': self.opts, 'exp': self.exp, 'module_id': self.module_id}
        if not hide_answer:
            data['ans'] = self.ans
        return data


class LessonProgress(db.Model):
    __tablename__ = 'lesson_progress'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey('modules.id'), nullable=False)
    score = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=0)
    passed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    material_pages_viewed = db.Column(db.JSON, default=list)
    material_time_spent = db.Column(db.Integer, default=0)
    material_read_at = db.Column(db.DateTime, nullable=True)
    material_percentage = db.Column(db.Float, default=0.0)
    video_watched = db.Column(db.Boolean, default=False)

    user = db.relationship('User', backref='lesson_progresses', lazy=True)
    course = db.relationship('Course', backref='lesson_progresses', lazy=True)
    module = db.relationship('Module', backref='lesson_progresses', lazy=True)

    __table_args__ = (db.UniqueConstraint('user_id', 'module_id', name='uq_user_module'),)

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'course_id': self.course_id,
            'module_id': self.module_id,
            'material_pages_viewed': self.material_pages_viewed or [],
            'material_time_spent': self.material_time_spent or 0,
            'material_read_at': self.material_read_at.isoformat() if self.material_read_at else None,
            'material_percentage': self.material_percentage or 0.0,
            'video_watched': bool(self.video_watched),
            'score': self.score,
            'total': self.total,
            'passed': self.passed,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


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


class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])

    @staticmethod
    def generate(user_id):
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=1)
        return PasswordResetToken(user_id=user_id, token=token, expires_at=expires_at)

    def is_valid(self):
        return not self.used and datetime.utcnow() < self.expires_at


class Badge(db.Model):
    __tablename__ = 'badge'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(10), nullable=False)
    rarity = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'rarity': self.rarity,
        }


class UserBadge(db.Model):
    __tablename__ = 'user_badge'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey('badge.id'), nullable=False)
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow)

    badge = db.relationship('Badge')

    __table_args__ = (db.UniqueConstraint('user_id', 'badge_id', name='uq_user_badge'),)


class Trail(db.Model):
    __tablename__ = 'trails'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    icon = db.Column(db.String(10), default='🛤️')
    goal = db.Column(db.String(50), default='')  # evangelismo | discipulado | teologia | servico
    xp_bonus = db.Column(db.Integer, default=100)
    badge_code = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    trail_courses = db.relationship('TrailCourse', backref='trail', lazy=True,
                                    cascade='all, delete-orphan', order_by='TrailCourse.position')

    def to_dict(self, include_courses=False):
        data = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'goal': self.goal,
            'xp_bonus': self.xp_bonus,
            'badge_code': self.badge_code,
        }
        if include_courses:
            data['courses'] = [tc.to_dict() for tc in self.trail_courses]
        return data


class TrailCourse(db.Model):
    __tablename__ = 'trail_courses'

    id = db.Column(db.Integer, primary_key=True)
    trail_id = db.Column(db.Integer, db.ForeignKey('trails.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    position = db.Column(db.Integer, default=0)

    course = db.relationship('Course')

    def to_dict(self):
        return {
            'position': self.position,
            'course_id': self.course_id,
            'course_name': self.course.name if self.course else '',
            'course_icon': self.course.icon if self.course else '',
        }


class UserTrail(db.Model):
    __tablename__ = 'user_trails'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    trail_id = db.Column(db.Integer, db.ForeignKey('trails.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    trail = db.relationship('Trail')

    __table_args__ = (db.UniqueConstraint('user_id', 'trail_id', name='uq_user_trail'),)

    def to_dict(self):
        return {
            'trail_id': self.trail_id,
            'enrolled_at': self.enrolled_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class OnboardingAnswer(db.Model):
    __tablename__ = 'onboarding_answers'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    goal = db.Column(db.String(50), nullable=False)
    recommended_trail_id = db.Column(db.Integer, db.ForeignKey('trails.id'), nullable=True)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)

    recommended_trail = db.relationship('Trail')

    def to_dict(self):
        return {
            'goal': self.goal,
            'recommended_trail_id': self.recommended_trail_id,
        }


class UserPoints(db.Model):
    __tablename__ = 'user_points'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    total_points = db.Column(db.Integer, default=0)
    current_level = db.Column(db.Integer, default=1)
    points_in_level = db.Column(db.Integer, default=0)
    last_activity_date = db.Column(db.Date)

    def to_dict(self):
        return {
            'total_points': self.total_points,
            'current_level': self.current_level,
            'points_in_level': self.points_in_level,
        }


class Certificate(db.Model):
    __tablename__ = 'certificates'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=True)
    trail_id = db.Column(db.Integer, db.ForeignKey('trails.id'), nullable=True)
    cert_type = db.Column(db.String(10), nullable=False)  # 'course' | 'trail'
    cert_code = db.Column(db.String(20), unique=True, nullable=False)
    issued_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='certificates', lazy=True)
    course = db.relationship('Course', backref='certificates', lazy=True)
    trail = db.relationship('Trail', backref='certificates', lazy=True)

    def to_dict(self):
        title = ''
        if self.cert_type == 'course' and self.course:
            title = self.course.name
        elif self.cert_type == 'trail' and self.trail:
            title = self.trail.name
        return {
            'id': self.id,
            'cert_code': self.cert_code,
            'cert_type': self.cert_type,
            'title': title,
            'issued_at': self.issued_at.isoformat(),
            'student_name': self.user.name if self.user else '',
        }
