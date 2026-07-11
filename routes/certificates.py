"""
Certificate endpoints: issue, download PDF, verify (public), list
"""
import random
import string
from io import BytesIO
from datetime import datetime
from flask import Blueprint, jsonify, session, send_file, request, current_app
from extensions import db, limiter
from core.tenancy import current_tenant_id, get_scoped
from models import Certificate, User, Course, Trail, UserTrail, ActivityFeed

certificates_bp = Blueprint('certificates', __name__)

_CERT_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no 0/O/1/I


def generate_cert_code():
    """Generate unique IBC-XXXX-XXXX code."""
    while True:
        part1 = ''.join(random.choices(_CERT_CHARS, k=4))
        part2 = ''.join(random.choices(_CERT_CHARS, k=4))
        code = f'IBC-{part1}-{part2}'
        if not Certificate.query.filter_by(cert_code=code).first():
            return code


def _current_user():
    uid = session.get('user_id')
    return User.query.get(uid) if uid else None


# ── Issue certificate ──────────────────────────────────────────────────────

@certificates_bp.route('/issue', methods=['POST'])
def issue_certificate():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    data = request.get_json(silent=True) or {}
    cert_type = data.get('cert_type')  # 'course' | 'trail'
    entity_id = data.get('entity_id')

    if cert_type not in ('course', 'trail') or not entity_id:
        return jsonify({'error': 'Parâmetros inválidos'}), 400
    try:
        entity_id = int(entity_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'Parâmetros inválidos'}), 400

    # Valida conclusão real (Module + LessonProgress) antes de emitir —
    # antes qualquer autenticado emitia certificado de qualquer course_id/
    # trail_id, concluído ou não. Reusa o mesmo critério já usado para
    # marcar cursos como concluídos dentro de uma trilha (routes/trails.py).
    from routes.trails import _completed_course_ids
    done_course_ids = _completed_course_ids(user.id)

    if cert_type == 'course':
        if not get_scoped(Course, entity_id):
            return jsonify({'error': 'Curso não encontrado'}), 404
        if entity_id not in done_course_ids:
            return jsonify({'error': 'Curso ainda não foi concluído'}), 403
        existing = Certificate.query.filter_by(user_id=user.id, course_id=entity_id, cert_type='course', tenant_id=current_tenant_id()).first()
    else:
        trail = get_scoped(Trail, entity_id)
        if not trail:
            return jsonify({'error': 'Trilha não encontrada'}), 404
        trail_course_ids = [tc.course_id for tc in trail.trail_courses]
        if not trail_course_ids or not all(cid in done_course_ids for cid in trail_course_ids):
            return jsonify({'error': 'Trilha ainda não foi concluída'}), 403
        existing = Certificate.query.filter_by(user_id=user.id, trail_id=entity_id, cert_type='trail', tenant_id=current_tenant_id()).first()

    if existing:
        return jsonify({'certificate_issued': False, 'cert': existing.to_dict()}), 200

    code = generate_cert_code()
    if cert_type == 'course':
        cert = Certificate(user_id=user.id, course_id=entity_id, cert_type='course', cert_code=code)
    else:
        cert = Certificate(user_id=user.id, trail_id=entity_id, cert_type='trail', cert_code=code)
    db.session.add(cert)
    db.session.commit()

    # Sprint 6.2: "Mural de Conclusões" — register course completions for the
    # community activity feed (trail completions are not posted here).
    if cert_type == 'course':
        db.session.add(ActivityFeed(user_id=user.id, course_id=entity_id, action='completed'))
        db.session.commit()

    # 100 pts de curso concluído junto com a emissão (1x por curso — se o
    # certificado já existia, retornamos antes de chegar aqui).
    points = None
    if cert_type == 'course':
        from routes.gamification import award_points
        points = award_points(user.id, 'course_completed')

    from routes.gamification import check_and_grant_achievements
    new_achievements = check_and_grant_achievements(user.id)

    return jsonify({'certificate_issued': True, 'cert': cert.to_dict(),
                    'new_achievements': new_achievements, 'points': points}), 201


# ── List my certificates ───────────────────────────────────────────────────

@certificates_bp.route('/my', methods=['GET'])
def my_certificates():
    user = _current_user()
    if not user:
        return jsonify({'error': 'Não autenticado'}), 401

    certs = Certificate.query.filter_by(user_id=user.id, tenant_id=current_tenant_id()).order_by(Certificate.issued_at.desc()).all()
    return jsonify([c.to_dict() for c in certs]), 200


# ── Verify (public, no login) ──────────────────────────────────────────────
#
# ROADMAP.md §1.1 apontou "arquivo servido sem autenticação" para /download
# no mesmo grupo de materials.py/uploads (que exigem sessão agora). Decisão
# consciente de NÃO exigir login aqui: verificação e download de certificado
# são, por design, um credencial PÚBLICO verificável (o mesmo modelo de
# LinkedIn/Credly) — quem tem o link verifica sem precisar de conta (ex.:
# empregador). cert_code tem ~41 bits de entropia (33^8 combinações,
# alfabeto sem caracteres confusos) — não é enumerável por listagem (só
# lookup exato) nem por força bruta prática. Rate limit abaixo é defesa em
# profundidade contra scanning automatizado, não a mitigação principal.

@certificates_bp.route('/verify/<cert_code>', methods=['GET'])
@limiter.limit('30 per minute')
def verify_certificate(cert_code):
    # Lookup global INTENCIONAL: verificação pública por código único
    # (empregadores etc.) — não vaza listagem, só o certificado exato.
    cert = Certificate.query.filter_by(cert_code=cert_code).first()
    if not cert:
        return jsonify({'valid': False}), 200

    title = ''
    if cert.cert_type == 'course' and cert.course:
        title = cert.course.name
    elif cert.cert_type == 'trail' and cert.trail:
        title = cert.trail.name

    return jsonify({
        'valid': True,
        'student_name': cert.user.name if cert.user else '',
        'title': title,
        'cert_type': cert.cert_type,
        'issued_at': cert.issued_at.isoformat(),
        'cert_code': cert.cert_code,
    }), 200


# ── Download PDF ───────────────────────────────────────────────────────────

@certificates_bp.route('/<cert_code>/download', methods=['GET'])
@limiter.limit('30 per minute')
def download_certificate(cert_code):
    cert = Certificate.query.filter_by(cert_code=cert_code).first()
    if not cert:
        return jsonify({'error': 'Certificado não encontrado'}), 404

    pdf = _generate_pdf(cert)
    return send_file(
        pdf,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'certificado-{cert_code}.pdf',
    )


def _generate_pdf(cert):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader
    import os

    buf = BytesIO()
    w, h = landscape(A4)
    c = rl_canvas.Canvas(buf, pagesize=(w, h))

    primary = colors.HexColor('#008ea8')
    dark = colors.HexColor('#003d4d')
    gold = colors.HexColor('#e9c46a')
    gray = colors.HexColor('#555555')
    light_gray = colors.HexColor('#aaaaaa')

    # Outer border
    c.setStrokeColor(primary)
    c.setLineWidth(4)
    c.rect(12 * mm, 12 * mm, w - 24 * mm, h - 24 * mm)
    # Inner border
    c.setLineWidth(1.5)
    c.rect(16 * mm, 16 * mm, w - 32 * mm, h - 32 * mm)

    # Logo (if exists)
    logo_path = os.path.join(os.path.dirname(__file__), '..', 'Logo-IBC-Horizontal.png')
    logo_y = h - 38 * mm
    if os.path.exists(logo_path):
        try:
            c.drawImage(ImageReader(logo_path), w / 2 - 40 * mm, logo_y, width=80 * mm, height=18 * mm,
                        preserveAspectRatio=True, mask='auto')
            logo_y -= 6 * mm
        except Exception:
            pass
    else:
        # Fallback text header
        c.setFont('Helvetica-Bold', 20)
        c.setFillColor(primary)
        c.drawCentredString(w / 2, h - 30 * mm, 'IBC ENSINO')
        c.setFont('Helvetica', 11)
        c.setFillColor(gray)
        c.drawCentredString(w / 2, h - 38 * mm, 'Igreja Batista Central de Campo Grande')
        logo_y = h - 44 * mm

    # Decorative line
    c.setStrokeColor(gold)
    c.setLineWidth(2)
    c.line(40 * mm, logo_y - 4 * mm, w - 40 * mm, logo_y - 4 * mm)

    # CERTIFICADO title
    c.setFont('Helvetica-Bold', 32)
    c.setFillColor(dark)
    c.drawCentredString(w / 2, logo_y - 22 * mm, 'CERTIFICADO')

    # Body
    c.setFont('Helvetica', 14)
    c.setFillColor(gray)
    c.drawCentredString(w / 2, logo_y - 32 * mm, 'Certificamos que')

    # Student name
    student_name = cert.user.name if cert.user else ''
    c.setFont('Helvetica-Bold', 28)
    c.setFillColor(dark)
    c.drawCentredString(w / 2, logo_y - 48 * mm, student_name)

    # Name underline
    name_w = c.stringWidth(student_name, 'Helvetica-Bold', 28)
    c.setStrokeColor(primary)
    c.setLineWidth(1)
    c.line(w / 2 - name_w / 2, logo_y - 50 * mm, w / 2 + name_w / 2, logo_y - 50 * mm)

    # Course/trail label
    c.setFont('Helvetica', 14)
    c.setFillColor(gray)
    cert_label = 'concluiu com êxito o curso' if cert.cert_type == 'course' else 'concluiu com êxito a trilha'
    c.drawCentredString(w / 2, logo_y - 60 * mm, cert_label)

    # Title
    title = ''
    if cert.cert_type == 'course' and cert.course:
        title = cert.course.name
    elif cert.cert_type == 'trail' and cert.trail:
        title = cert.trail.name
    c.setFont('Helvetica-Bold', 20)
    c.setFillColor(primary)
    c.drawCentredString(w / 2, logo_y - 72 * mm, title)

    # Decorative line bottom
    c.setStrokeColor(gold)
    c.setLineWidth(2)
    c.line(40 * mm, logo_y - 80 * mm, w - 40 * mm, logo_y - 80 * mm)

    # Footer
    issued_str = cert.issued_at.strftime('%d/%m/%Y') if cert.issued_at else ''
    app_url = current_app.config.get('APP_URL', 'http://localhost:5000')

    c.setFont('Helvetica', 9)
    c.setFillColor(light_gray)
    c.drawString(24 * mm, 22 * mm, f'Emitido em: {issued_str}')
    c.drawCentredString(w / 2, 22 * mm, f'Verifique em: {app_url}/#verificar/{cert.cert_code}')
    c.drawRightString(w - 24 * mm, 22 * mm, f'Código de verificação: {cert.cert_code}')

    c.save()
    buf.seek(0)
    return buf
