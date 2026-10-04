"""Painel do operador da plataforma — /api/ops (UX_OPERADOR_SAAS P0).

Acesso: usuário logado + registro em operadores_plataforma + 2FA (TOTP)
verificado nesta sessão, com expiração por 30 min de inatividade. Ações
destrutivas (suspender/reativar) exigem um código TOTP novo no corpo.
Qualquer usuário de tenant — inclusive admin — recebe 403.
"""
import time

from flask import Blueprint, jsonify, request, session

from extensions import db, limiter, chave_por_usuario
from core.plataforma import servico, totp
from core.plataforma.models import OperadorPlataforma
from core.tenancy.models import Tenant

ops_bp = Blueprint('ops', __name__)

SESSAO_MAX_INATIVA = 30 * 60


def _usuario():
    from models import User
    uid = session.get('user_id')
    return User.query.get(uid) if uid else None


def _operador(user):
    if user is None:
        return None
    return OperadorPlataforma.query.filter_by(user_id=user.id, ativo=True).first()


def _sessao_2fa_valida(user):
    if session.get('ops_uid') != user.id:
        return False
    ultimo = session.get('ops_ultimo') or 0
    if time.time() - ultimo > SESSAO_MAX_INATIVA:
        session.pop('ops_uid', None)
        return False
    session['ops_ultimo'] = time.time()
    return True


def _exigir_operador(exigir_2fa=True):
    user = _usuario()
    op = _operador(user)
    if op is None:
        return None, None, (jsonify({'error': 'Acesso restrito ao operador da plataforma'}), 403)
    if exigir_2fa and not (op.totp_ativo and _sessao_2fa_valida(user)):
        return None, None, (jsonify({'error': 'Verificação em duas etapas necessária', 'precisa_2fa': True}), 428)
    return user, op, None


def _consumir_codigo(op, codigo):
    contador = totp.verificar(op.totp_segredo, codigo, op.totp_ultimo_contador)
    if contador is None:
        return False
    op.totp_ultimo_contador = contador
    return True


def _tenant_ou_404(tenant_id):
    import uuid
    try:
        tid = uuid.UUID(str(tenant_id))
    except ValueError:
        return None
    return Tenant.query.get(tid)


# ── Sessão do operador / 2FA ────────────────────────────────────────────────

@ops_bp.route('/me', methods=['GET'])
def me():
    user, op, err = _exigir_operador(exigir_2fa=False)
    if err:
        return err
    return jsonify({'operador': True, 'email': user.email, 'nome': user.name,
                    '2fa_configurado': bool(op.totp_ativo),
                    '2fa_verificado': bool(op.totp_ativo and _sessao_2fa_valida(user))}), 200


@ops_bp.route('/2fa/configurar', methods=['POST'])
def configurar_2fa():
    user, op, err = _exigir_operador(exigir_2fa=False)
    if err:
        return err
    if op.totp_ativo:
        return jsonify({'error': '2FA já está configurado'}), 409
    op.totp_segredo = totp.gerar_segredo()
    db.session.commit()
    uri = totp.uri_otpauth(op.totp_segredo, user.email)
    import segno
    qr_svg = segno.make(uri, error='m').svg_data_uri(scale=5, border=2)
    return jsonify({'segredo': op.totp_segredo, 'uri': uri, 'qr_svg': qr_svg}), 200


@ops_bp.route('/2fa/verificar', methods=['POST'])
@limiter.limit('10 per minute')
@limiter.limit('5 per minute;20 per hour', key_func=chave_por_usuario)
def verificar_2fa():
    user, op, err = _exigir_operador(exigir_2fa=False)
    if err:
        return err
    codigo = (request.get_json(silent=True) or {}).get('codigo')
    if not op.totp_segredo or not _consumir_codigo(op, codigo):
        db.session.rollback()
        return jsonify({'error': 'Código inválido'}), 400
    op.totp_ativo = True
    db.session.commit()
    session['ops_uid'] = user.id
    session['ops_ultimo'] = time.time()
    return jsonify({'success': True}), 200


@ops_bp.route('/sair', methods=['POST'])
def sair():
    _, _, err = _exigir_operador(exigir_2fa=False)
    if err:
        return err
    session.pop('ops_uid', None)
    session.pop('ops_ultimo', None)
    return jsonify({'success': True}), 200


# ── Pulso / Tenants / Auditoria ─────────────────────────────────────────────

@ops_bp.route('/pulso', methods=['GET'])
def get_pulso():
    _, _, err = _exigir_operador()
    if err:
        return err
    return jsonify(servico.pulso()), 200


@ops_bp.route('/planos', methods=['GET'])
def get_planos():
    _, _, err = _exigir_operador()
    if err:
        return err
    from core.billing.plans import PLANOS
    return jsonify([{'id': k, 'nome': p.nome, 'preco': p.preco_mensal_brl, 'limite_alunos': p.limite_alunos}
                    for k, p in PLANOS.items()]), 200


@ops_bp.route('/tenants', methods=['GET'])
def get_tenants():
    _, _, err = _exigir_operador()
    if err:
        return err
    pagina = max(request.args.get('pagina', 1, type=int), 1)
    return jsonify(servico.listar_tenants(request.args.get('busca', '').strip(),
                                          request.args.get('status', ''), pagina)), 200


@ops_bp.route('/tenants/disponibilidade', methods=['GET'])
def get_disponibilidade():
    _, _, err = _exigir_operador()
    if err:
        return err
    return jsonify(servico.disponibilidade(request.args.get('slug', ''))), 200


@ops_bp.route('/tenants', methods=['POST'])
def post_tenant():
    user, _, err = _exigir_operador()
    if err:
        return err
    try:
        tenant, admin, senha = servico.criar_tenant(user, request.get_json(silent=True) or {})
    except servico.ErroOperacao as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    return jsonify({'tenant': tenant.to_dict(), 'admin_email': admin.email,
                    'senha_temporaria': senha}), 201


@ops_bp.route('/tenants/<tenant_id>', methods=['GET'])
def get_tenant(tenant_id):
    _, _, err = _exigir_operador()
    if err:
        return err
    tenant = _tenant_ou_404(tenant_id)
    if not tenant:
        return jsonify({'error': 'Tenant não encontrado'}), 404
    return jsonify(servico.perfil_tenant(tenant.id)), 200


@ops_bp.route('/tenants/<tenant_id>', methods=['PATCH'])
def patch_tenant(tenant_id):
    user, _, err = _exigir_operador()
    if err:
        return err
    tenant = _tenant_ou_404(tenant_id)
    if not tenant:
        return jsonify({'error': 'Tenant não encontrado'}), 404
    try:
        servico.atualizar_tenant(user, tenant, request.get_json(silent=True) or {})
    except servico.ErroOperacao as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    return jsonify({'tenant': tenant.to_dict()}), 200


@ops_bp.route('/tenants/<tenant_id>/status', methods=['POST'])
@limiter.limit('20 per minute')
def post_status(tenant_id):
    user, op, err = _exigir_operador()
    if err:
        return err
    tenant = _tenant_ou_404(tenant_id)
    if not tenant:
        return jsonify({'error': 'Tenant não encontrado'}), 404
    dados = request.get_json(silent=True) or {}
    if not _consumir_codigo(op, dados.get('codigo')):
        db.session.rollback()
        return jsonify({'error': 'Confirme com um código novo do autenticador'}), 400
    try:
        servico.mudar_status(user, tenant, dados.get('status'), dados.get('motivo'))
    except servico.ErroOperacao as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    return jsonify({'tenant': tenant.to_dict()}), 200


@ops_bp.route('/auditoria', methods=['GET'])
def get_auditoria():
    _, _, err = _exigir_operador()
    if err:
        return err
    tenant = _tenant_ou_404(request.args.get('tenant')) if request.args.get('tenant') else None
    pagina = max(request.args.get('pagina', 1, type=int), 1)
    return jsonify(servico.auditoria(tenant.id if tenant else None, pagina)), 200
