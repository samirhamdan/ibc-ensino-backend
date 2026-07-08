"""
Lesson (aula) routes: linear lesson flow — material + inline quiz per module
"""
import re
from flask import Blueprint, request, jsonify, session
from extensions import db
from models import Course, Module, LessonProgress, User, UserPoints, Badge, UserBadge, Certificate, ActivityFeed
from routes.gamification import award_points, check_and_grant_achievements

lessons_bp = Blueprint('lessons', __name__)

PASS_THRESHOLD = 60  # percent

ALLOWED_VIDEO_HOSTS = ('youtube.com', 'youtu.be', 'vimeo.com', 'www.youtube.com', 'www.vimeo.com')


def _current_user():
    uid = session.get('user_id')
    if uid:
        return User.query.get(uid)
    return None


def _ordered_modules(course_id):
    return Module.query.filter_by(course_id=course_id).order_by(Module.position).all()


def _merge_points(a, b):
    """Combine two award_points() results into one payload for the frontend."""
    if not a:
        return b
    if not b:
        return a
    return {
        'points_awarded': (a.get('points_awarded') or 0) + (b.get('points_awarded') or 0),
        'total_points': b.get('total_points'),
        'level_up': a.get('level_up') or b.get('level_up'),
        'new_level': b.get('new_level') or a.get('new_level'),
        'badge_unlocked': a.get('badge_unlocked') or b.get('badge_unlocked'),
    }


def get_embed_url(video_url):
    """Return embeddable iframe URL from a YouTube or Vimeo URL, or None."""
    if not video_url:
        return None, None
    # YouTube: watch?v=ID or youtu.be/ID or youtube.com/embed/ID
    yt = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([A-Za-z0-9_-]{11})', video_url)
    if yt:
        return f'https://www.youtube.com/embed/{yt.group(1)}', 'youtube'
    # Vimeo: vimeo.com/ID or player.vimeo.com/video/ID
    vm = re.search(r'(?:vimeo\.com/|player\.vimeo\.com/video/)(\d+)', video_url)
    if vm:
        return f'https://player.vimeo.com/video/{vm.group(1)}', 'vimeo'
    return None, None


def validate_video_url(url):
    """Return True if URL is from allowed video hosts."""
    if not url:
        return True
    from urllib.parse import urlparse
    host = urlparse(url).netloc.lstrip('www.')
    return host in ('youtube.com', 'youtu.be', 'vimeo.com')


def _lesson_dict(module, progress_map, unlocked):
    quiz_total = len(module.quiz)
    prog = progress_map.get(module.id)
    embed_url, provider = get_embed_url(module.video_url)
    return {
        'id': module.id,
        'nome': module.nome,
        'dur': module.dur,
        'position': module.position,
        'materiais': [m.to_dict() for m in module.materials],
        'quiz_total': quiz_total,
        'progress': prog.to_dict() if prog else None,
        'unlocked': unlocked,
        'video_url': module.video_url,
        'video_provider': provider or module.video_provider,
        'video_embed_url': embed_url,
    }


@lessons_bp.route('/<int:course_id>/aulas', methods=['GET'])
def list_aulas(course_id):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    Course.query.get_or_404(course_id)
    modules = _ordered_modules(course_id)

    progresses = LessonProgress.query.filter_by(user_id=user.id, course_id=course_id).all()
    progress_map = {p.module_id: p for p in progresses}

    result = []
    unlocked = True
    for m in modules:
        result.append(_lesson_dict(m, progress_map, unlocked))
        prog = progress_map.get(m.id)
        unlocked = bool(prog and prog.passed)

    return jsonify(result), 200


@lessons_bp.route('/<int:course_id>/aulas/<int:aula_num>', methods=['GET'])
def get_aula(course_id, aula_num):
    """aula_num is 1-based position index"""
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    Course.query.get_or_404(course_id)
    modules = _ordered_modules(course_id)
    if aula_num < 1 or aula_num > len(modules):
        return jsonify({'error': 'Aula não encontrada'}), 404

    progresses = LessonProgress.query.filter_by(user_id=user.id, course_id=course_id).all()
    progress_map = {p.module_id: p for p in progresses}

    # Check unlock: all previous lessons must be passed
    unlocked = True
    for i in range(aula_num - 1):
        prog = progress_map.get(modules[i].id)
        if not (prog and prog.passed):
            unlocked = False
            break

    if not unlocked and user.role not in ('admin', 'tutor'):
        return jsonify({'error': 'Esta aula está bloqueada. Conclua a aula anterior primeiro.'}), 403

    module = modules[aula_num - 1]
    data = _lesson_dict(module, progress_map, True)
    data['quiz'] = [q.to_dict(hide_answer=True) for q in module.quiz]
    data['total_aulas'] = len(modules)
    data['aula_num'] = aula_num
    data['course'] = {'id': module.course_id, 'name': module.course.name, 'icon': module.course.icon}
    return jsonify(data), 200


@lessons_bp.route('/<int:course_id>/aulas/<int:aula_num>/submit-quiz', methods=['POST'])
def submit_aula_quiz(course_id, aula_num):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    Course.query.get_or_404(course_id)
    modules = _ordered_modules(course_id)
    if aula_num < 1 or aula_num > len(modules):
        return jsonify({'error': 'Aula não encontrada'}), 404

    # Mesmo bloqueio sequencial de get_aula: sem isso, bastava POSTar direto
    # nesta rota para completar aulas bloqueadas fora de ordem.
    if user.role not in ('admin', 'tutor'):
        progress_check = {p.module_id: p for p in
                          LessonProgress.query.filter_by(user_id=user.id, course_id=course_id).all()}
        for i in range(aula_num - 1):
            prev = progress_check.get(modules[i].id)
            if not (prev and prev.passed):
                return jsonify({'error': 'Esta aula está bloqueada. Conclua a aula anterior primeiro.'}), 403

    module = modules[aula_num - 1]
    quiz = module.quiz
    if not quiz:
        return jsonify({'error': 'Esta aula não tem exercício'}), 404

    data = request.get_json(silent=True) or {}
    answers = data.get('answers') or []

    score = 0
    feedback = []
    for i, q in enumerate(quiz):
        selected = answers[i] if i < len(answers) else None
        correct = selected == q.ans
        if correct:
            score += 1
        feedback.append({
            'question': q.q,
            'selected': selected,
            'correct_answer': q.ans,
            'is_correct': correct,
            'explanation': q.exp,
        })

    total = len(quiz)
    percentage = round(score / total * 100) if total else 0
    passed = percentage >= PASS_THRESHOLD

    # Reprovou: não devolver o gabarito das questões erradas — senão basta
    # errar de propósito, copiar as respostas e re-submeter com 100%.
    if not passed:
        for f in feedback:
            if not f['is_correct']:
                f['correct_answer'] = None
                f['explanation'] = None

    prog = LessonProgress.query.filter_by(user_id=user.id, module_id=module.id).first()
    is_first_attempt = prog is None or not prog.total
    already_passed = bool(prog and prog.passed)
    if not prog:
        prog = LessonProgress(user_id=user.id, course_id=course_id, module_id=module.id)
        db.session.add(prog)
    # Keep best attempt
    if score > (prog.score or 0) or not prog.total:
        prog.score = score
        prog.total = total
    prog.passed = prog.passed or passed
    db.session.commit()

    # Pontos concedidos aqui (evento real, com dedupe) — antes o frontend
    # chamava /gamification/add-points, que aceitava POSTs repetidos sem
    # nenhuma verificação (XP ilimitado).
    points = None
    if is_first_attempt:
        points = award_points(user.id, 'quiz_attempted')
    if passed and not already_passed:
        passed_result = award_points(user.id, 'quiz_passed',
                                     {'attempts': 1 if is_first_attempt else 2})
        points = _merge_points(points, passed_result)

    next_unlocked = passed
    is_last = aula_num == len(modules)

    # Check if course is now fully complete → issue certificate
    certificate_issued = False
    cert_code = None
    if passed and is_last:
        all_modules = modules
        all_progs = {p.module_id: p for p in LessonProgress.query.filter_by(user_id=user.id, course_id=course_id).all()}
        all_done = all(all_progs.get(m.id) and all_progs[m.id].passed for m in all_modules)
        if all_done:
            existing_cert = Certificate.query.filter_by(user_id=user.id, course_id=course_id, cert_type='course').first()
            if not existing_cert:
                from routes.certificates import generate_cert_code
                code = generate_cert_code()
                cert = Certificate(user_id=user.id, course_id=course_id, cert_type='course', cert_code=code)
                db.session.add(cert)
                db.session.add(ActivityFeed(user_id=user.id, course_id=course_id, action='completed'))
                db.session.commit()
                certificate_issued = True
                cert_code = code
                # 100 pts de curso concluído: concedidos junto com o certificado
                # (1x por curso, por construção — só entra aqui se não existia).
                points = _merge_points(points, award_points(user.id, 'course_completed'))

    new_achievements = check_and_grant_achievements(user.id) if passed else []

    # Sprint 6.2: surface the next lesson so the frontend can offer a
    # "Continuar para próxima aula" panel after this one is completed.
    next_lesson = None
    if passed and not is_last:
        next_module = modules[aula_num]  # aula_num is 1-based, so this is index `aula_num`
        next_lesson = {
            'id': next_module.id,
            'title': next_module.nome,
            'course_id': course_id,
        }

    return jsonify({
        'score': score,
        'total': total,
        'percentage': percentage,
        'passed': passed,
        'pass_threshold': PASS_THRESHOLD,
        'feedback': feedback,
        'next_unlocked': next_unlocked,
        'is_last_lesson': is_last,
        'certificate_issued': certificate_issued,
        'cert_code': cert_code,
        'new_achievements': new_achievements,
        'next_lesson': next_lesson,
        'points': points,
    }), 200


@lessons_bp.route('/<int:course_id>/next-lesson', methods=['GET'])
def next_lesson(course_id):
    """Returns the next unwatched/unpassed lesson for the current student."""
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    Course.query.get_or_404(course_id)
    modules = _ordered_modules(course_id)
    total = len(modules)

    if not total:
        return jsonify({'has_next': False, 'lesson': None, 'lesson_count': {'current': 0, 'total': 0}}), 200

    progress_map = {p.module_id: p for p in
                     LessonProgress.query.filter_by(user_id=user.id, course_id=course_id).all()}

    next_idx = None
    for i, m in enumerate(modules):
        prog = progress_map.get(m.id)
        if not (prog and prog.passed):
            next_idx = i
            break

    if next_idx is None:
        return jsonify({'has_next': False, 'lesson': None, 'lesson_count': {'current': total, 'total': total}}), 200

    next_module = modules[next_idx]
    return jsonify({
        'has_next': True,
        'lesson': {
            'id': next_module.id,
            'title': next_module.nome,
            'order': next_module.position,
        },
        'lesson_count': {'current': next_idx + 1, 'total': total},
    }), 200


@lessons_bp.route('/<int:course_id>/aulas/<int:aula_num>/video-watched', methods=['POST'])
def mark_video_watched(course_id, aula_num):
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    Course.query.get_or_404(course_id)
    modules = _ordered_modules(course_id)
    if aula_num < 1 or aula_num > len(modules):
        return jsonify({'error': 'Aula não encontrada'}), 404

    module = modules[aula_num - 1]
    if not module.video_url:
        return jsonify({'error': 'Esta aula não tem vídeo'}), 400

    prog = LessonProgress.query.filter_by(user_id=user.id, module_id=module.id).first()
    already_watched = bool(prog and prog.video_watched)
    if not prog:
        prog = LessonProgress(user_id=user.id, course_id=course_id, module_id=module.id)
        db.session.add(prog)

    prog.video_watched = True
    db.session.commit()

    points_result = None
    if not already_watched:
        points_result = award_points(user.id, 'material_read')

    # Determine if quiz is now unlocked
    mat = (module.materials or [None])[0] if module.materials else None
    mat_read = bool(prog.material_read_at) or bool(prog.material_percentage and prog.material_percentage >= 50)
    has_material = bool(mat and mat.tipo == 'pdf')
    quiz_unlocked = prog.video_watched and (not has_material or mat_read)

    return jsonify({
        'ok': True,
        'already_watched': already_watched,
        'points': points_result,
        'quiz_unlocked': quiz_unlocked,
    }), 200


@lessons_bp.route('/<int:course_id>/modulos/<int:module_id>/video', methods=['PATCH'])
def update_module_video(course_id, module_id):
    """Admin/tutor: set or clear video URL on a module."""
    user = _current_user()
    if not user or user.role not in ('admin', 'tutor'):
        return jsonify({'error': 'Acesso negado'}), 403

    module = Module.query.filter_by(id=module_id, course_id=course_id).first_or_404()
    data = request.get_json(silent=True) or {}
    video_url = data.get('video_url', '').strip() or None

    if video_url and not validate_video_url(video_url):
        return jsonify({'error': 'URL inválida. Use YouTube ou Vimeo.'}), 400

    embed_url, provider = get_embed_url(video_url)
    module.video_url = video_url
    module.video_provider = provider
    db.session.commit()
    return jsonify({'ok': True, 'video_url': video_url, 'video_embed_url': embed_url}), 200
