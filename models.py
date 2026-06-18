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
    role = db.Column(db.String(20), nullable=False, default='aluno')
    # roles: admin | tutor | aluno
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    onboarding_completed = db.Column(db.Boolean, default=False)
    active_trail_id = db.Column(db.Integer, db.ForeignKey('trails.id', use_alter=True, name='fk_user_active_trail'), nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    progress = db.relationship('Progress', backref='user', lazy=True, cascade='all, delete-orphan')
    questions = db.relationship('Question', backref='author', lazy=True, cascade='all, delete-orphan', foreign_keys='Question.user_id')

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
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'is_active': self.is_active,
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
    color = db.Column(db.String(20), default='#008ea8')
    tag = db.Column(db.String(100), default='')
    description = db.Column(db.Text, default='')
    status = db.Column(db.String(20), default='published')
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
            'status': self.status or 'published',
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


class TutorCourse(db.Model):
    __tablename__ = 'tutor_courses'

    id = db.Column(db.Integer, primary_key=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    tutor = db.relationship('User', foreign_keys=[tutor_id])
    course = db.relationship('Course', foreign_keys=[course_id])

    __table_args__ = (db.UniqueConstraint('tutor_id', 'course_id', name='uq_tutor_course'),)


class Question(db.Model):
    __tablename__ = 'questions'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_tutor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    texto = db.Column(db.Text, nullable=False)
    resposta = db.Column(db.Text, default='')
    respondido_por = db.Column(db.String(150), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='open')  # open | answered | resolved
    resolved_at = db.Column(db.DateTime, nullable=True)

    assigned_tutor = db.relationship('User', foreign_keys=[assigned_tutor_id])

    def to_dict(self):
        return {
            'id': self.id,
            'course_id': self.course_id,
            'autor': self.author.name if self.author else '',
            'texto': self.texto,
            'resposta': self.resposta,
            'respondido_por': self.respondido_por,
            'assigned_tutor_id': self.assigned_tutor_id,
            'assigned_tutor_name': self.assigned_tutor.name if self.assigned_tutor else None,
            'created_at': self.created_at.isoformat(),
            'status': self.status or 'open',
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
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
    color = db.Column(db.String(20), default='#008ea8')
    certificate_name = db.Column(db.String(200), default='')
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


class Announcement(db.Model):
    __tablename__ = 'announcements'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), default='info')  # info | warning | success
    target_role = db.Column(db.String(20), default='all')  # aluno | tutor | all
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)

    creator = db.relationship('User', foreign_keys=[created_by])

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'severity': self.severity,
            'target_role': self.target_role,
            'is_active': self.is_active,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
        }


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), default='general')  # general | achievement | message | announcement
    is_read = db.Column(db.Boolean, default=False)
    link = db.Column(db.String(255), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])
    creator = db.relationship('User', foreign_keys=[created_by])

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'message': self.message,
            'type': self.type,
            'is_read': self.is_read,
            'link': self.link,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AnnouncementDismissal(db.Model):
    __tablename__ = 'announcement_dismissals'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    announcement_id = db.Column(db.Integer, db.ForeignKey('announcements.id'), nullable=False)
    dismissed_at = db.Column(db.DateTime, default=datetime.utcnow)


class PlatformConfig(db.Model):
    __tablename__ = 'platform_config'

    id = db.Column(db.Integer, primary_key=True)
    platform_name = db.Column(db.String(100), default='IBC Ensino')
    platform_short = db.Column(db.String(20), default='IBC')
    whatsapp = db.Column(db.String(30), default='(67) 99999-9999')
    support_email = db.Column(db.String(120), default='contato@ibc.com')
    support_hours = db.Column(db.String(60), default='Seg-Sex, 8h-17h')
    verse_text = db.Column(db.Text, default='Lâmpada para os meus pés é a tua palavra e luz para o meu caminho.')
    verse_reference = db.Column(db.String(60), default='Salmos 119:105')
    points_read_material = db.Column(db.Integer, default=10)
    points_complete_video = db.Column(db.Integer, default=10)
    points_correct_exercise = db.Column(db.Integer, default=20)
    points_complete_course = db.Column(db.Integer, default=50)
    points_complete_trail = db.Column(db.Integer, default=200)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'platform_name': self.platform_name,
            'platform_short': self.platform_short,
            'whatsapp': self.whatsapp,
            'support_email': self.support_email,
            'support_hours': self.support_hours,
            'verse_text': self.verse_text,
            'verse_reference': self.verse_reference,
            'points_read_material': self.points_read_material,
            'points_complete_video': self.points_complete_video,
            'points_correct_exercise': self.points_correct_exercise,
            'points_complete_course': self.points_complete_course,
            'points_complete_trail': self.points_complete_trail,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'updated_by': self.updated_by,
        }


class Level(db.Model):
    __tablename__ = 'levels'

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    min_points = db.Column(db.Integer, nullable=False)
    color = db.Column(db.String(7), default='#008ea8')

    def to_dict(self):
        return {
            'id': self.id,
            'number': self.number,
            'name': self.name,
            'min_points': self.min_points,
            'color': self.color,
        }


class Achievement(db.Model):
    """New 'Conquistas' system (Sprint 6.1) — distinct from the legacy
    Badge/UserBadge tables used in the hero/dashboard. See routes/gamification.py
    for the criteria checking logic."""
    __tablename__ = 'achievements'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, default='')
    icon = db.Column(db.String(10), default='🏆')
    criteria_type = db.Column(db.String(30), nullable=False)
    # criteria_type: lessons_completed | courses_completed | trails_completed |
    #                questions_created | certificates_earned | points_total
    criteria_value = db.Column(db.Integer, nullable=False, default=1)
    points_reward = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'criteria_type': self.criteria_type,
            'criteria_value': self.criteria_value,
            'points_reward': self.points_reward,
        }


class UserAchievement(db.Model):
    __tablename__ = 'user_achievements'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievements.id'), nullable=False)
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)

    achievement = db.relationship('Achievement')

    __table_args__ = (db.UniqueConstraint('user_id', 'achievement_id', name='uq_user_achievement'),)

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'achievement_id': self.achievement_id,
            'earned_at': self.earned_at.isoformat() if self.earned_at else None,
        }


class StudySession(db.Model):
    """Sprint 6.2: tracks time spent studying a given lesson (Modulo) via the
    frontend study timer."""
    __tablename__ = 'study_sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('modules.id'), nullable=True)
    duration_seconds = db.Column(db.Integer, default=0)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', foreign_keys=[user_id])
    lesson = db.relationship('Module', foreign_keys=[lesson_id])

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'lesson_id': self.lesson_id,
            'duration_seconds': self.duration_seconds,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
        }


class ActivityFeed(db.Model):
    """Sprint 6.2: 'Mural de Conclusões' — records when a student completes
    a course, to power the 'Comunidade em Ação' feed on the dashboard."""
    __tablename__ = 'activity_feed'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    action = db.Column(db.String(50), default='completed')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])
    course = db.relationship('Course', foreign_keys=[course_id])

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'course_id': self.course_id,
            'action': self.action,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
