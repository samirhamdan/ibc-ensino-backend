"""
Gamification routes: points, levels and badges
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import Blueprint, request, jsonify, session
from sqlalchemy.exc import IntegrityError
from extensions import db
from core.tenancy import current_tenant_id
from models import (User, Badge, UserBadge, UserPoints, LessonProgress,
                    Question, Course, Module, Achievement, UserAchievement,
                    UserTrail, Certificate)

gamification_bp = Blueprint('gamification', __name__)

# Fuso fixo do público-alvo atual (IBC Ensino é 100% Brasil) — usado só
# para decidir o "dia" de streak/login diário. datetime.utcnow().date()
# vira o dia errado perto da virada BRT/UTC (ex.: 21h-24h local ainda é
# "amanhã" em UTC), quebrando streak de quem loga sempre à noite. Vira
# fuso por tenant/usuário na Release 1.0 (doc não pede multi-fuso agora);
# até lá, um fuso fixo correto para o público real é melhor que UTC puro.
_FUSO_STREAK = ZoneInfo('America/Sao_Paulo')


def hoje_streak():
    return datetime.now(_FUSO_STREAK).date()


def streak_efetivo(up):
    """Streak "de leitura" — current_streak só é zerado de verdade no
    próximo login (lazy reset, dentro de award_points). Sem isto, o
    dashboard mostrava "sequência de 10 dias, vence hoje" para quem sumiu
    há um mês (achado de revisão de segurança): current_streak fica > 0
    na linha até o usuário logar de novo, então precisa ser reinterpretado
    na LEITURA. Devolve (streak_exibido, em_risco):
      - sem linha/streak → (0, False)
      - renovou hoje      → (current_streak, False) — já garantido por hoje
      - renovou ontem     → (current_streak, True)  — ainda vale, mas some
                             se não renovar até o fim do dia
      - mais antigo que isso → (0, False) — já quebrou, só não foi
                             zerado no banco ainda (vai zerar no próximo login)
    """
    if not up or not up.current_streak or not up.last_activity_date:
        return 0, False
    hoje = hoje_streak()
    if up.last_activity_date == hoje:
        return up.current_streak, False
    if up.last_activity_date == hoje - timedelta(days=1):
        return up.current_streak, True
    return 0, False

LEVEL_NAMES = {
    1: 'Iniciante', 2: 'Aprendiz', 3: 'Estudioso', 4: 'Conhecedor',
    5: 'Mestre', 6: 'Especialista', 7: 'Guru',
}

POINTS_PER_ACTION = {
    'material_read': 10,
    'quiz_attempted': 20,
    'quiz_passed_first': 30,
    'quiz_passed_retry': 15,
    'question_asked': 15,
    'question_answered': 25,
    'course_completed': 100,
    'daily_login': 5,
}

# GAM-02 (Etapa 3): bônus de pontos ao bater um marco de streak — chave é
# o valor de current_streak que dispara o bônus.
STREAK_MARCOS = {7: 50, 30: 200, 100: 500}

# Todas as ações que award_points aceita (routes/lessons.py, routes/auth.py,
# routes/questions.py, routes/materials.py, routes/certificates.py) contam
# como "esteve ativo hoje" pro streak — nota que 'quiz_passed' não é chave
# de POINTS_PER_ACTION (o valor de pontos dela é calculado à parte, por
# tentativa), por isso não dá pra usar POINTS_PER_ACTION.keys() aqui.
_ACOES_QUE_CONTAM_STREAK = {
    'material_read', 'quiz_attempted', 'quiz_passed', 'question_asked',
    'question_answered', 'course_completed', 'daily_login',
}


def _current_user():
    uid = session.get('user_id')
    if uid:
        return User.query.get(uid)
    return None


def calculate_level(total_points):
    level = min(7, total_points // 100 + 1)
    points_in_level = total_points - (level - 1) * 100
    if level == 7:
        points_in_level = total_points - 600
    return level, points_in_level


def _get_or_create_points(user_id, lock=False):
    """lock=True (Postgres: SELECT ... FOR UPDATE; SQLite: sem efeito, o
    driver não suporta e a suíte de testes roda nele) serializa requests
    concorrentes na mesma linha — usado no guard de login diário, onde um
    double-click/retry sem lock lia o mesmo last_activity_date "antigo" em
    duas transações e dava streak +2 / bônus de marco em dobro no mesmo
    dia (achado de revisão de segurança)."""
    tid = current_tenant_id()
    q = UserPoints.query.filter_by(user_id=user_id, tenant_id=tid)
    if lock:
        q = q.with_for_update()
    up = q.first()
    if not up:
        try:
            with db.session.begin_nested():
                up = UserPoints(user_id=user_id, total_points=0, current_level=1, points_in_level=0)
                db.session.add(up)
                db.session.flush()
        except IntegrityError:
            # Corrida: outra requisição concorrente já criou o registro
            # (unique (tenant_id, user_id)). Recarrega o que foi criado.
            q = UserPoints.query.filter_by(user_id=user_id, tenant_id=tid)
            if lock:
                q = q.with_for_update()
            up = q.first()
    return up


def unlock_badge(user_id, badge_code):
    """Returns badge dict if newly unlocked, else None"""
    badge = Badge.query.filter_by(code=badge_code, tenant_id=current_tenant_id()).first()
    if not badge:
        return None
    existing = UserBadge.query.filter_by(user_id=user_id, badge_id=badge.id, tenant_id=current_tenant_id()).first()
    if existing:
        return None
    try:
        with db.session.begin_nested():
            ub = UserBadge(user_id=user_id, badge_id=badge.id)
            db.session.add(ub)
            db.session.flush()
    except IntegrityError:
        # Corrida: outra requisição concorrente já desbloqueou este badge
        # (uq_user_badge). Trata como "não desbloqueado agora".
        return None
    return badge.to_dict()


# ── Badge progress checks ────────────────────────────────────────────────

def _badge_progress(user_id, code):
    """Returns (current, target) progress for a badge"""
    if code == 'novo_discipulo':
        count = LessonProgress.query.filter_by(user_id=user_id, tenant_id=current_tenant_id()).distinct(LessonProgress.course_id).count()
        return min(count, 1), 1
    if code == 'estudioso_palavra':
        count = LessonProgress.query.filter(LessonProgress.user_id == user_id,
                                             LessonProgress.tenant_id == current_tenant_id(),
                                             LessonProgress.material_percentage >= 50).count()
        return min(count, 5), 5
    if code == 'guerreiro_palavra':
        count = LessonProgress.query.filter(LessonProgress.user_id == user_id,
                                             LessonProgress.tenant_id == current_tenant_id(),
                                             LessonProgress.passed == True,
                                             LessonProgress.score == LessonProgress.total).count()
        return min(count, 3), 3
    if code == 'buscador_verdade':
        count = Question.query.filter_by(tenant_id=current_tenant_id(), user_id=user_id).count()
        return min(count, 5), 5
    if code == 'iluminado_graca':
        count = Question.query.filter(Question.tenant_id == current_tenant_id(), Question.user_id == user_id, Question.resposta != '').count()
        return min(count, 1), 1
    if code == 'edificador':
        course_count = _completed_courses_count(user_id)
        return min(course_count, 3), 3
    if code == 'corredor_incansavel':
        return 0, 1
    if code == 'servo_fiel':
        up = UserPoints.query.filter_by(user_id=user_id, tenant_id=current_tenant_id()).first()
        return (1, 1) if (up and _consecutive_days(up) >= 7) else (_consecutive_days(up) if up else 0, 7)
    return 0, 1


def _completed_courses_count(user_id):
    """Count courses where user passed all modules"""
    count = 0
    for course in Course.query.filter_by(tenant_id=current_tenant_id()).all():
        modules = Module.query.filter_by(tenant_id=current_tenant_id(), course_id=course.id).all()
        if not modules:
            continue
        progresses = {p.module_id: p for p in
                      LessonProgress.query.filter_by(user_id=user_id, course_id=course.id, tenant_id=current_tenant_id()).all()}
        if all(progresses.get(m.id) and progresses[m.id].passed for m in modules):
            count += 1
    return count


def _consecutive_days(user_points):
    # GAM-02 (Etapa 3): antes sempre retornava 0 (docs/DEBITOS.md #6 — o
    # badge 'servo_fiel', streak de 7 dias, era inalcançável por design).
    # Agora que current_streak existe de verdade, usa a mesma
    # reinterpretação de leitura que o dashboard usa (streak_efetivo) —
    # não o campo bruto, que só é zerado no próximo login (lazy reset).
    return streak_efetivo(user_points)[0]


# ── Badge check orchestration ────────────────────────────────────────────

def check_all_badges(user_id):
    unlocked = []
    for badge in Badge.query.filter_by(tenant_id=current_tenant_id()).all():
        if UserBadge.query.filter_by(user_id=user_id, badge_id=badge.id, tenant_id=current_tenant_id()).first():
            continue
        current, target = _badge_progress(user_id, badge.code)
        if current >= target:
            result = unlock_badge(user_id, badge.code)
            if result:
                unlocked.append(result)
    return unlocked


def award_points(user_id, action, metadata=None):
    """Awards points for an action, updates level, returns dict of results"""
    metadata = metadata or {}
    points = 0
    if action == 'material_read':
        points = POINTS_PER_ACTION['material_read']
    elif action == 'quiz_attempted':
        points = POINTS_PER_ACTION['quiz_attempted']
    elif action == 'quiz_passed':
        points = (POINTS_PER_ACTION['quiz_passed_first'] if metadata.get('attempts', 1) <= 1
                  else POINTS_PER_ACTION['quiz_passed_retry'])
    elif action == 'question_asked':
        points = POINTS_PER_ACTION['question_asked']
    elif action == 'question_answered':
        points = POINTS_PER_ACTION['question_answered']
    elif action == 'course_completed':
        points = POINTS_PER_ACTION['course_completed']
    elif action == 'daily_login':
        points = POINTS_PER_ACTION['daily_login']

    up = _get_or_create_points(user_id)
    old_level = up.current_level

    # GAM-02 (Etapa 3, UX_ALUNO_SAAS.md §3 Grupo 3 / §4 Grupo 4): streak de
    # dias consecutivos de ATIVIDADE — corrigido na auditoria de release
    # (achado H2/Etapa 3): a versão anterior só contava 'daily_login', mas
    # a UI e a própria doc prometem "estude hoje para manter seu streak" /
    # "completar a revisão mantém o streak" — um aluno que estuda todo dia
    # sem reenviar o form de login (sessão continua viva) perdia o streak
    # silenciosamente, e o CTA "em risco" não era acionável pela ação que
    # ele recomendava. Agora QUALQUER ação real de award_points conta como
    # "esteve ativo hoje" — todas as chamadas a award_points já são
    # engajamento real do usuário (quiz, material, curso, pergunta, login),
    # nunca eventos passivos/automáticos, então generalizar de 'daily_login'
    # para "qualquer ação" é seguro.
    #
    # UPDATE...WHERE guardado (não SELECT...FOR UPDATE): generalizar pra
    # "qualquer ação" multiplica os pontos de entrada que podem disparar o
    # streak concorrentemente (duas abas, dois quizzes seguidos), e
    # with_for_update() não serializa em SQLite (documentado em
    # _get_or_create_points — a suíte roda nele). Mesmo padrão já usado em
    # routes/trails.py::claim_trail_if_complete (correção H2 da revisão de
    # release de trilhas): o UPDATE só afeta a linha se last_activity_date
    # ainda for o valor que acabamos de ler — se outra ação concorrente já
    # tiver vencido a corrida e comitado "hoje" primeiro, rowcount vem 0 e
    # esta chamada não mexe em streak nem paga bônus, só relê o estado
    # atual. Chamada duplicada no mesmo dia (last_activity_date == hoje)
    # nem tenta o UPDATE — não conta streak de novo.
    streak_bonus = 0
    marco_atingido = None
    if action in _ACOES_QUE_CONTAM_STREAK:
        hoje = hoje_streak()
        ontem = hoje - timedelta(days=1)
        last_activity_antigo = up.last_activity_date
        if last_activity_antigo != hoje:
            if last_activity_antigo == ontem:
                novo_streak = (up.current_streak or 0) + 1
            else:
                novo_streak = 1   # primeira atividade ou dia perdido — reinicia
            novo_longest = max(up.longest_streak or 0, novo_streak)

            from sqlalchemy import update
            filtro_last_activity = (UserPoints.last_activity_date == last_activity_antigo
                                    if last_activity_antigo is not None
                                    else UserPoints.last_activity_date.is_(None))
            resultado = db.session.execute(
                update(UserPoints)
                .where(UserPoints.id == up.id, filtro_last_activity)
                .values(current_streak=novo_streak, longest_streak=novo_longest, last_activity_date=hoje)
            )
            if resultado.rowcount == 1:
                up.current_streak = novo_streak
                up.longest_streak = novo_longest
                up.last_activity_date = hoje
                if novo_streak in STREAK_MARCOS:
                    streak_bonus = STREAK_MARCOS[novo_streak]
                    marco_atingido = novo_streak
            else:
                # Perdeu a corrida — outra ação concorrente já contou hoje
                # (ou já reiniciou o streak) entre a leitura e este UPDATE.
                # Não paga bônus, não mexe no streak; só relê o estado real.
                db.session.refresh(up)

    up.total_points = (up.total_points or 0) + points + streak_bonus
    up.current_level, up.points_in_level = calculate_level(up.total_points)
    db.session.flush()

    level_up = up.current_level > old_level
    badges_unlocked = check_all_badges(user_id)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()

    return {
        'points_awarded': points + streak_bonus,
        'total_points': up.total_points,
        'level_up': level_up,
        'new_level': up.current_level if level_up else None,
        'badge_unlocked': badges_unlocked[0] if badges_unlocked else None,
        'current_streak': up.current_streak or 0,
        'streak_marco_atingido': marco_atingido,
        'streak_bonus': streak_bonus,
    }


# ── Endpoints ────────────────────────────────────────────────────────────

@gamification_bp.route('/user-stats', methods=['GET'])
def user_stats():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    up = _get_or_create_points(user.id)
    db.session.commit()

    tid = current_tenant_id()
    unlocked_ids = {ub.badge_id for ub in UserBadge.query.filter_by(user_id=user.id, tenant_id=tid).all()}
    user_badges = {ub.badge_id: ub for ub in UserBadge.query.filter_by(user_id=user.id, tenant_id=tid).all()}

    badges_unlocked = []
    badges_locked = []
    for badge in Badge.query.filter_by(tenant_id=tid).all():
        if badge.id in unlocked_ids:
            ub = user_badges[badge.id]
            badges_unlocked.append({
                'id': badge.id, 'code': badge.code, 'name': badge.name,
                'icon': badge.icon, 'unlocked_at': ub.unlocked_at.isoformat(),
            })
        else:
            current, target = _badge_progress(user.id, badge.code)
            badges_locked.append({
                'id': badge.id, 'code': badge.code, 'name': badge.name,
                'icon': badge.icon, 'progress': f'{current}/{target}',
            })

    return jsonify({
        'total_points': up.total_points,
        'current_level': up.current_level,
        'points_in_level': up.points_in_level,
        'badges_count': len(badges_unlocked),
        'badges_unlocked': badges_unlocked,
        'badges_locked': badges_locked,
    }), 200


@gamification_bp.route('/badges', methods=['GET'])
def list_badges():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    tid = current_tenant_id()
    unlocked = {ub.badge_id: ub for ub in UserBadge.query.filter_by(user_id=user.id, tenant_id=tid).all()}
    result = []
    for badge in Badge.query.filter_by(tenant_id=tid).all():
        d = badge.to_dict()
        if badge.id in unlocked:
            d['unlocked'] = True
            d['unlocked_at'] = unlocked[badge.id].unlocked_at.isoformat()
            d['progress'] = None
        else:
            current, target = _badge_progress(user.id, badge.code)
            d['unlocked'] = False
            d['unlocked_at'] = None
            d['progress'] = f'{current}/{target}'
        result.append(d)
    return jsonify(result), 200


@gamification_bp.route('/add-points', methods=['POST'])
def add_points():
    """DESATIVADO como vetor de pontos: aceitava qualquer ação repetidamente,
    sem verificação de evento real (XP/nível/badge ilimitados via POST em loop).
    Todos os pontos agora são concedidos no servidor, no evento verificado:
    - material_read      → routes/materials.py (cruzar 50% de leitura, 1x/aula)
    - quiz_attempted/... → routes/lessons.py   (1ª tentativa / 1ª aprovação)
    - question_asked     → routes/questions.py (pergunta criada)
    - question_answered  → routes/questions.py (1ª resposta do tutor)
    - course_completed   → lessons/certificates (emissão do certificado)
    - daily_login        → routes/auth.py      (login, 1x por dia)
    A rota permanece para clientes antigos, que tratam !res.ok como no-op."""
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401
    return jsonify({'error': 'Pontos são concedidos automaticamente pelas ações reais'}), 400


# ── Achievements ("Conquistas") — Sprint 6.1 ────────────────────────────
# NOTE: this is a NEW, separate system from the legacy Badge/UserBadge tables
# above (already surfaced as "Conquistas" in the hero/dashboard UI). Both
# exist concurrently for now — see final report for the flagged duplication.

def get_completed_lessons_count(user_id):
    return LessonProgress.query.filter_by(user_id=user_id, passed=True, tenant_id=current_tenant_id()).count()


def get_completed_courses_count(user_id):
    """Count courses where the user has passed all modules. Reuses the same
    logic as the legacy _completed_courses_count() helper above."""
    return _completed_courses_count(user_id)


def get_completed_trails_count(user_id):
    return UserTrail.query.filter(UserTrail.user_id == user_id,
                                   UserTrail.tenant_id == current_tenant_id(),
                                   UserTrail.completed_at.isnot(None)).count()


def get_questions_count(user_id):
    return Question.query.filter_by(tenant_id=current_tenant_id(), user_id=user_id).count()


def get_certificates_count(user_id):
    return Certificate.query.filter_by(user_id=user_id, tenant_id=current_tenant_id()).count()


def _achievement_progress_value(user_id, criteria_type):
    if criteria_type == 'lessons_completed':
        return get_completed_lessons_count(user_id)
    if criteria_type == 'courses_completed':
        return get_completed_courses_count(user_id)
    if criteria_type == 'trails_completed':
        return get_completed_trails_count(user_id)
    if criteria_type == 'questions_created':
        return get_questions_count(user_id)
    if criteria_type == 'certificates_earned':
        return get_certificates_count(user_id)
    if criteria_type == 'points_total':
        up = UserPoints.query.filter_by(user_id=user_id, tenant_id=current_tenant_id()).first()
        return up.total_points if up else 0
    return 0


def check_and_grant_achievements(user_id):
    """Checks all Achievement rows not yet earned by the user; grants any
    whose criteria is now met (creating UserAchievement + awarding points).
    Returns a list of newly granted Achievement dicts (for popup display)."""
    tid = current_tenant_id()
    earned_ids = {ua.achievement_id for ua in UserAchievement.query.filter_by(user_id=user_id, tenant_id=tid).all()}
    newly_granted = []

    for ach in Achievement.query.filter_by(tenant_id=tid).all():
        if ach.id in earned_ids:
            continue
        current = _achievement_progress_value(user_id, ach.criteria_type)
        if current >= ach.criteria_value:
            try:
                with db.session.begin_nested():
                    ua = UserAchievement(user_id=user_id, achievement_id=ach.id)
                    db.session.add(ua)
                    if ach.points_reward:
                        up = _get_or_create_points(user_id)
                        up.total_points = (up.total_points or 0) + ach.points_reward
                        up.current_level, up.points_in_level = calculate_level(up.total_points)
                    db.session.flush()
            except IntegrityError:
                # Corrida: outra requisição concorrente já concedeu esta
                # conquista (uq_user_achievement). Não conta como nova.
                continue
            newly_granted.append(ach.to_dict())

    if newly_granted:
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    return newly_granted


@gamification_bp.route('/check-badge-progress', methods=['POST'])
def check_badge_progress():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    unlocked = check_all_badges(user.id)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    msg = ''
    if unlocked:
        names = ', '.join(b['name'] for b in unlocked)
        msg = f'Você desbloqueou: {names}!'
    return jsonify({'badges_unlocked': unlocked, 'message': msg}), 200
