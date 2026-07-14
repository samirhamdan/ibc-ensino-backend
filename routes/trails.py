"""
Trails + Onboarding endpoints
"""
from flask import Blueprint, jsonify, session, request
from extensions import db
from core.tenancy import current_tenant_id, get_scoped, get_scoped_or_404, role_no_tenant
from models import Trail, TrailCourse, UserTrail, OnboardingAnswer, User, UserPoints, Badge, UserBadge, Module, LessonProgress

trails_bp = Blueprint('trails', __name__)
onboarding_bp = Blueprint('onboarding', __name__)

GOAL_TO_TRAIL = {
    'evangelismo': 'evangelismo',
    'discipulado': 'discipulado',
    'teologia': 'teologia',
    'servico': 'servico',
}


def _current_user():
    uid = session.get('user_id')
    return User.query.get(uid) if uid else None


def _add_xp(user_id, points):
    up = UserPoints.query.filter_by(user_id=user_id, tenant_id=current_tenant_id()).first()
    if not up:
        up = UserPoints(user_id=user_id, total_points=0, current_level=1, points_in_level=0)
        db.session.add(up)
    up.total_points += points
    up.points_in_level += points
    level_threshold = up.current_level * 100
    if up.points_in_level >= level_threshold:
        up.points_in_level -= level_threshold
        up.current_level += 1


def _award_badge(user_id, code):
    badge = Badge.query.filter_by(code=code, tenant_id=current_tenant_id()).first()
    if not badge:
        return None
    existing = UserBadge.query.filter_by(user_id=user_id, badge_id=badge.id, tenant_id=current_tenant_id()).first()
    if existing:
        return None
    db.session.add(UserBadge(user_id=user_id, badge_id=badge.id))
    return badge


def claim_trail_if_complete(user_id, trail, done_course_ids=None):
    """Concede XP/badge de conclusão de UMA trilha — atomicamente. Ponto
    ÚNICO de award para toda a trilha (chamado automaticamente ao concluir
    o último curso — routes/lessons.py — e como rede de segurança em
    my_trails(); POST /trails/active/claim também reusa isto).

    Correção H2 (revisão de release): o UPDATE abaixo, guardado por
    completed_at IS NULL, decide quem ganha o prêmio sob concorrência —
    não é "ler completed_at, decidir, depois escrever" (que tem uma janela
    entre leitura e escrita onde duas requisições simultâneas passam as
    duas pela checagem). UPDATE...WHERE é atômico por linha em qualquer
    banco relacional: só UMA execução consegue de fato mudar
    completed_at de NULL para um timestamp; a(s) outra(s) recebe(m)
    rowcount=0 e sabe(m) que chegou(aram) tarde, sem tocar XP/badge.
    Mesmo padrão sugerido no playbook de revisão — equivalente ao
    `with_for_update()` já usado em core/tenancy/auth.py::
    _get_or_create_points para o mesmo tipo de corrida (login concorrente).

    Retorna None se a trilha não está 100% concluída, se o usuário não
    está inscrito, ou se o prêmio já tinha sido reivindicado (por esta
    chamada ou por uma concorrente que venceu a corrida)."""
    if done_course_ids is None:
        done_course_ids = _completed_course_ids(user_id)
    trail_course_ids = [tc.course_id for tc in trail.trail_courses]
    if not trail_course_ids or not all(cid in done_course_ids for cid in trail_course_ids):
        return None

    from datetime import datetime
    from sqlalchemy import update
    resultado = db.session.execute(
        update(UserTrail)
        .where(UserTrail.user_id == user_id, UserTrail.trail_id == trail.id,
               UserTrail.tenant_id == current_tenant_id(), UserTrail.completed_at.is_(None))
        .values(completed_at=datetime.utcnow())
    )
    if resultado.rowcount == 0:
        # Não inscrito, ou já reivindicado (por esta chamada antes, ou por
        # uma requisição concorrente que ganhou a corrida agora mesmo).
        db.session.rollback()
        return None
    db.session.commit()   # o UPDATE já decidiu o vencedor — commit já trava isso

    _add_xp(user_id, trail.xp_bonus)
    awarded_badge = _award_badge(user_id, trail.badge_code) if trail.badge_code else None
    db.session.commit()

    resposta = {'trail_id': trail.id, 'trail_name': trail.name, 'xp_bonus': trail.xp_bonus}
    if awarded_badge:
        resposta['new_badge'] = awarded_badge.to_dict()
    return resposta


def claim_completed_trails_for_course(user_id, course_id):
    """Chamado automaticamente quando um curso vira 100% concluído
    (routes/lessons.py::submit_aula_quiz) — reivindica TODAS as trilhas
    (não só a "ativa") em que esse curso é o último pendente. Um curso
    pode pertencer a mais de uma trilha; a trilha "ativa" é só a que o
    aluno está focando na UI, não limita quais trilhas podem completar."""
    trail_ids = [tc.trail_id for tc in
                TrailCourse.query.filter_by(tenant_id=current_tenant_id(), course_id=course_id).all()]
    if not trail_ids:
        return []
    inscritas = {ut.trail_id for ut in
                UserTrail.query.filter_by(user_id=user_id, tenant_id=current_tenant_id())
                .filter(UserTrail.trail_id.in_(trail_ids), UserTrail.completed_at.is_(None)).all()}
    if not inscritas:
        return []
    done_course_ids = _completed_course_ids(user_id)
    premios = []
    for tid in inscritas:
        trail = get_scoped(Trail, tid)
        if not trail:
            continue
        premio = claim_trail_if_complete(user_id, trail, done_course_ids)
        if premio:
            premios.append(premio)
    return premios


# ── Trail endpoints ──────────────────────────────────────

def _trail_dict_scoped(trail, user, is_staff):
    """Mesma política de acesso a curso já aplicada em
    routes/courses.py::list_courses (correção M1, revisão de release):
    staff vê tudo; qualquer outro (autenticado ou não) só vê curso
    publicado; anônimo, adicionalmente, nunca vê curso acesso='interno'.
    Sem isto, o título de curso interno/rascunho vazava pra qualquer
    visitante através de QUALQUER trilha que o contivesse — mesma classe
    de vazamento do catálogo, só que por um caminho diferente.

    Aplicado em TODO lugar que serializa trail.courses pra fora (list_trails,
    active_trail, my_trails, enroll_trail, submit_onboarding) — não só nos
    dois primeiros; o vazamento também acontecia em enroll/onboarding."""
    data = trail.to_dict(include_courses=False)
    courses = []
    for tc in trail.trail_courses:
        c = tc.course
        if not is_staff:
            if not c or c.status != 'published':
                continue
            if not user and c.acesso == 'interno':
                continue
        courses.append(tc.to_dict())
    data['courses'] = courses
    return data


def _trail_fully_done(trail, done_course_ids):
    """Conclusão real da trilha (TODOS os cursos, inclusive rascunho/interno
    que um não-staff não enxerga na listagem) — não pode ser calculada sobre
    a lista já filtrada por _trail_dict_scoped, senão diverge do critério
    usado por claim_trail_if_complete (que exige 100% dos trail_courses) e a
    UI mostra completed=true sem nunca conseguir reivindicar o prêmio."""
    trail_course_ids = [tc.course_id for tc in trail.trail_courses]
    return bool(trail_course_ids) and all(cid in done_course_ids for cid in trail_course_ids)


@trails_bp.route('', methods=['GET'])
def list_trails():
    user = _current_user()
    is_staff = bool(user and role_no_tenant(user) in ('admin', 'tutor'))
    trails = Trail.query.filter_by(tenant_id=current_tenant_id()).all()
    return jsonify([_trail_dict_scoped(t, user, is_staff) for t in trails])


@trails_bp.route('/<int:trail_id>/enroll', methods=['POST'])
def enroll_trail(trail_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    trail = get_scoped_or_404(Trail, trail_id)

    existing = UserTrail.query.filter_by(user_id=user.id, trail_id=trail_id, tenant_id=current_tenant_id()).first()
    already = bool(existing)
    if not existing:
        db.session.add(UserTrail(user_id=user.id, trail_id=trail_id))

    # enrolling makes this the focused trail
    user.active_trail_id = trail_id
    db.session.commit()

    is_staff = role_no_tenant(user) in ('admin', 'tutor')
    return jsonify({'ok': True, 'already_enrolled': already,
                    'trail': _trail_dict_scoped(trail, user, is_staff)})


@trails_bp.route('/<int:trail_id>/focus', methods=['POST'])
def focus_trail(trail_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    enrolled = UserTrail.query.filter_by(user_id=user.id, trail_id=trail_id, tenant_id=current_tenant_id()).first()
    if not enrolled:
        return jsonify({'error': 'Você não está inscrito nesta trilha'}), 400

    user.active_trail_id = trail_id
    db.session.commit()
    return jsonify({'ok': True, 'focused_trail_id': trail_id})


def _completed_course_ids(user_id):
    """Ids de curso 100% concluídos pelo usuário (todos os módulos com
    LessonProgress.passed=True). Substitui o antigo cálculo baseado no modelo
    legado `Progress` — routes/progress.py não é mais usado pelo frontend, então
    `Progress` fica sempre vazio e a conclusão de trilha nunca disparava
    (bug crítico do ROADMAP.md, seção 1.2)."""
    modules_by_course = {}
    for m in Module.query.filter_by(tenant_id=current_tenant_id()).all():
        modules_by_course.setdefault(m.course_id, []).append(m.id)

    passed_module_ids = {
        lp.module_id for lp in LessonProgress.query.filter_by(user_id=user_id, passed=True, tenant_id=current_tenant_id()).all()
    }

    done_ids = set()
    for cid, module_ids in modules_by_course.items():
        if module_ids and all(mid in passed_module_ids for mid in module_ids):
            done_ids.add(cid)
    return done_ids


def _annotate_trail_progress(trail, user, is_staff, done_course_ids=None):
    """Return trail dict with per-course done/current/locked states."""
    if done_course_ids is None:
        done_course_ids = _completed_course_ids(user.id)

    trail_dict = _trail_dict_scoped(trail, user, is_staff)
    first_undone = None
    for tc in trail_dict['courses']:
        done = tc['course_id'] in done_course_ids
        tc['done'] = done
        if not done and first_undone is None:
            first_undone = tc['course_id']
    for tc in trail_dict['courses']:
        if tc['done']:
            tc['state'] = 'done'
        elif tc['course_id'] == first_undone:
            tc['state'] = 'current'
        else:
            tc['state'] = 'locked'

    trail_dict['current_course_id'] = first_undone
    done_count = sum(1 for tc in trail_dict['courses'] if tc['done'])
    total = len(trail_dict['courses'])
    trail_dict['done_count'] = done_count
    trail_dict['total_courses'] = total
    trail_dict['percentage'] = round(done_count / total * 100) if total else 0
    # Completude REAL (todos os trail_courses, não só os visíveis pro papel
    # do usuário) — precisa bater com claim_trail_if_complete, senão a UI
    # mostra completed=true pra uma trilha que nunca vai conseguir premiar
    # (ex.: trilha com um curso rascunho que só staff enxerga).
    trail_dict['completed'] = _trail_fully_done(trail, done_course_ids)
    return trail_dict


@trails_bp.route('/my', methods=['GET'])
def my_trails():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    enrollments = UserTrail.query.filter_by(user_id=user.id, tenant_id=current_tenant_id()).all()
    done_course_ids = _completed_course_ids(user.id)
    is_staff = role_no_tenant(user) in ('admin', 'tutor')

    in_progress, completed = [], []
    for ut in enrollments:
        if not ut.trail:
            continue
        td = _annotate_trail_progress(ut.trail, user, is_staff, done_course_ids)
        td['enrolled_at'] = ut.enrolled_at.isoformat()
        if not ut.completed_at and td['completed']:
            # Rede de segurança (correção H1): o gatilho principal é
            # automático em submit_aula_quiz, mas se por qualquer motivo
            # o aluno completou o último curso sem passar por lá (ex.:
            # sessão anterior, corrida, etc.), a página "Minhas Trilhas"
            # reivindica na hora em que é aberta — nunca fica presa
            # "computada como completa" sem o prêmio de verdade.
            claim_trail_if_complete(user.id, ut.trail, done_course_ids)
        if ut.completed_at or td['completed']:
            td['completed_at'] = ut.completed_at.isoformat() if ut.completed_at else None
            completed.append(td)
        else:
            in_progress.append(td)

    return jsonify({
        'in_progress': in_progress,
        'completed': completed,
        'focused_trail_id': user.active_trail_id,
    })


@trails_bp.route('/active', methods=['GET'])
def active_trail():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    if not user.active_trail_id:
        return jsonify(None)

    trail = get_scoped(Trail, user.active_trail_id)
    if not trail:
        return jsonify(None)

    is_staff = role_no_tenant(user) in ('admin', 'tutor')
    trail_dict = _trail_dict_scoped(trail, user, is_staff)

    # annotate each course with state: done | current | locked
    done_course_ids = _completed_course_ids(user.id)

    first_undone = None
    for tc in trail_dict['courses']:
        cid = tc['course_id']
        done = cid in done_course_ids
        tc['done'] = done
        if not done and first_undone is None:
            first_undone = cid

    for tc in trail_dict['courses']:
        cid = tc['course_id']
        if tc['done']:
            tc['state'] = 'done'
        elif cid == first_undone:
            tc['state'] = 'current'
        else:
            tc['state'] = 'locked'

    trail_dict['current_course_id'] = first_undone

    # Só computa/expõe se está completa — o AWARD (XP, badge, completed_at)
    # não acontece mais aqui. GET não pode ter efeito colateral de escrita:
    # sob SameSite=Lax, um GET ainda é acionável cross-site (ex.: <img
    # src="/api/trails/active">, prefetch de link) — achado do ROADMAP.md
    # §1.1. O cliente chama POST /trails/active/claim depois de ver
    # completed=true (idempotente, ver abaixo).
    #
    # Usa _trail_fully_done (todos os trail_courses reais), não
    # `all(tc['done'] for tc in trail_dict['courses'])` — essa lista já foi
    # filtrada por _trail_dict_scoped, então pra um não-staff ela nunca
    # inclui um curso rascunho/interno da trilha; calcular "completed" só
    # sobre os cursos visíveis fazia a UI achar a trilha 100% concluída sem
    # que claim_trail_if_complete (que exige TODOS os cursos) jamais
    # conseguisse premiar.
    trail_dict['completed'] = _trail_fully_done(trail, done_course_ids)

    return jsonify(trail_dict)


@trails_bp.route('/active/claim', methods=['POST'])
def claim_active_trail_completion():
    """Concede XP/badge de conclusão da trilha ativa — idempotente e
    seguro sob concorrência (claim_trail_if_complete, correção H2).

    Gatilho PRINCIPAL: automático, em routes/lessons.py::submit_aula_quiz,
    no instante em que o último curso pendente da trilha é concluído (e
    em my_trails(), como rede de segurança pra quem completou por outro
    caminho). Este endpoint continua existindo pra disparo explícito do
    cliente/testes — mas a UI não depende mais só dele (correção H1: o
    call site antigo, loadTrailsSection, não era mais alcançável)."""
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    if not user.active_trail_id:
        return jsonify({'completed_now': False}), 200

    trail = get_scoped(Trail, user.active_trail_id)
    if not trail:
        return jsonify({'completed_now': False}), 200

    premio = claim_trail_if_complete(user.id, trail)
    if not premio:
        return jsonify({'completed_now': False}), 200

    premio['completed_now'] = True
    return jsonify(premio), 200


# ── Onboarding endpoints ─────────────────────────────────

@onboarding_bp.route('/status', methods=['GET'])
def onboarding_status():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401
    return jsonify({'completed': user.onboarding_completed})


@onboarding_bp.route('', methods=['POST'])
def submit_onboarding():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    data = request.get_json(silent=True) or {}
    goal = data.get('goal', '')

    trail = Trail.query.filter_by(tenant_id=current_tenant_id(), goal=goal).first()

    existing = OnboardingAnswer.query.filter_by(user_id=user.id, tenant_id=current_tenant_id()).first()
    if existing:
        existing.goal = goal
        existing.recommended_trail_id = trail.id if trail else None
    else:
        db.session.add(OnboardingAnswer(
            user_id=user.id,
            goal=goal,
            recommended_trail_id=trail.id if trail else None,
        ))

    user.onboarding_completed = True
    db.session.commit()

    is_staff = role_no_tenant(user) in ('admin', 'tutor')
    return jsonify({
        'ok': True,
        'recommended_trail': _trail_dict_scoped(trail, user, is_staff) if trail else None,
    })


# ═══════════════════════════════════════════════════════════════
# ADMIN: Trails management (Sprint 4)
# ═══════════════════════════════════════════════════════════════

def _admin_required():
    uid = session.get('user_id')
    user = User.query.get(uid) if uid else None
    if not user or role_no_tenant(user) != 'admin':
        return None, (jsonify({'error': 'Acesso negado'}), 403)
    return user, None

@trails_bp.route('/admin/trails', methods=['GET'])
def admin_list_trails():
    user, err = _admin_required()
    if err: return err
    from models import Course
    trails = Trail.query.filter_by(tenant_id=current_tenant_id()).all()
    result = []
    for t in trails:
        trail_courses = TrailCourse.query.filter_by(tenant_id=current_tenant_id(), trail_id=t.id).order_by(TrailCourse.position).all()
        enrolled = UserTrail.query.filter_by(trail_id=t.id, tenant_id=current_tenant_id()).count()
        completed = UserTrail.query.filter_by(trail_id=t.id, tenant_id=current_tenant_id()).filter(UserTrail.completed_at.isnot(None)).count()
        courses_data = []
        for tc in trail_courses:
            c = get_scoped(Course, tc.course_id)
            if c:
                courses_data.append({'id': c.id, 'name': c.name, 'position': tc.position})
        result.append({
            'id': t.id, 'name': t.name, 'icon': t.icon or 'trails',
            'color': t.color or '#008ea8', 'description': t.description or '',
            'xp_bonus': t.xp_bonus or 0, 'certificate_name': t.certificate_name or '',
            'total_courses': len(trail_courses), 'enrolled_users': enrolled,
            'completed_users': completed, 'courses': courses_data
        })
    return jsonify({'trails': result})

@trails_bp.route('/admin/trails/<int:trail_id>', methods=['PUT'])
def admin_update_trail(trail_id):
    user, err = _admin_required()
    if err: return err
    t = get_scoped_or_404(Trail, trail_id)
    data = request.get_json() or {}
    if 'name' in data: t.name = data['name']
    if 'description' in data: t.description = data['description']
    if 'icon' in data: t.icon = data['icon']
    if 'color' in data: t.color = data['color']
    if 'xp_bonus' in data:
        try:
            t.xp_bonus = int(data['xp_bonus'])
        except (TypeError, ValueError):
            return jsonify({'error': 'xp_bonus deve ser um número'}), 400
    if 'certificate_name' in data: t.certificate_name = data['certificate_name']
    db.session.commit()
    return jsonify({'success': True})

@trails_bp.route('/admin/trails/<int:trail_id>/courses/reorder', methods=['PUT'])
def admin_reorder_trail_courses(trail_id):
    user, err = _admin_required()
    if err: return err
    data = request.get_json() or {}
    course_ids = data.get('course_ids', [])
    for idx, cid in enumerate(course_ids, 1):
        tc = TrailCourse.query.filter_by(tenant_id=current_tenant_id(), trail_id=trail_id, course_id=cid).first()
        if tc:
            tc.position = idx
    db.session.commit()
    return jsonify({'success': True})

@trails_bp.route('/admin/trails/<int:trail_id>/courses', methods=['POST'])
def admin_add_course_to_trail(trail_id):
    user, err = _admin_required()
    if err: return err
    data = request.get_json() or {}
    course_id = data.get('course_id')
    if not course_id:
        return jsonify({'error': 'course_id required'}), 400
    existing = TrailCourse.query.filter_by(tenant_id=current_tenant_id(), trail_id=trail_id, course_id=course_id).first()
    if existing:
        return jsonify({'error': 'Curso já na trilha'}), 409
    max_pos = db.session.query(db.func.max(TrailCourse.position)).filter_by(trail_id=trail_id).scalar() or 0
    tc = TrailCourse(trail_id=trail_id, course_id=course_id, position=max_pos + 1)
    db.session.add(tc)
    db.session.commit()
    return jsonify({'success': True})

@trails_bp.route('/admin/trails/<int:trail_id>/courses/<int:course_id>', methods=['DELETE'])
def admin_remove_course_from_trail(trail_id, course_id):
    user, err = _admin_required()
    if err: return err
    tc = TrailCourse.query.filter_by(tenant_id=current_tenant_id(), trail_id=trail_id, course_id=course_id).first()
    if tc:
        db.session.delete(tc)
        db.session.commit()
    return jsonify({'success': True})

@trails_bp.route('/admin/courses/available-for-trail/<int:trail_id>', methods=['GET'])
def admin_available_courses_for_trail(trail_id):
    user, err = _admin_required()
    if err: return err
    from models import Course
    trail_course_ids = {tc.course_id for tc in TrailCourse.query.filter_by(tenant_id=current_tenant_id(), trail_id=trail_id).all()}
    all_courses = Course.query.filter_by(tenant_id=current_tenant_id()).all()
    available = [{'id': c.id, 'name': c.name} for c in all_courses if c.id not in trail_course_ids]
    return jsonify({'courses': available})



@trails_bp.route('', methods=['POST'])
def create_trail():
    uid = session.get('user_id')
    user = User.query.get(uid) if uid else None
    if not user or role_no_tenant(user) != 'admin':
        return jsonify({'error': 'Acesso negado'}), 403
    
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name é obrigatório'}), 400
    
    try:
        xp_bonus = int(data.get('xp_bonus', 100))
    except (TypeError, ValueError):
        return jsonify({'error': 'xp_bonus deve ser um número'}), 400

    t = Trail(
        name=name,
        description=data.get('description', ''),
        xp_bonus=xp_bonus,
        color=data.get('color', '#008ea8')
    )
    db.session.add(t)
    db.session.commit()
    return jsonify({'id': t.id, 'name': t.name}), 201
