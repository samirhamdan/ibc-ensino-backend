"""Operações da plataforma sobre tenants (ciclo de vida + métricas).

Leituras aqui são CROSS-TENANT por definição (o operador enxerga todos os
tenants) — tenant-scope: intencionalmente global. Toda escrita grava a linha
de auditoria na MESMA transação da mudança (UX_OPERADOR_SAAS §4.6).

Hoje a app conecta com role BYPASSRLS (docs/RUNBOOK-RLS.md); quando o RLS for
ativado, estas consultas precisam de uma conexão de operador (DEBITOS #26).
"""
import re
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta

from flask import g
from sqlalchemy import func

from extensions import db
from core.billing.plans import PLANOS
from core.tenancy.middleware import _to_context, clear_tenant_cache
from core.tenancy.models import Tenant, TenantUser
from shared.audit import AuditLog, registrar_auditoria

SUBDOMINIOS_RESERVADOS = {'www', 'ops', 'api', 'admin', 'app', 'xr', 'mail', 'static', 'billing'}
RE_SLUG = re.compile(r'^[a-z0-9](?:[a-z0-9-]{1,28}[a-z0-9])$')
STATUS_VALIDOS = {'active', 'read_only', 'suspended'}


class ErroOperacao(ValueError):
    pass


@contextmanager
def no_contexto_do_tenant(tenant):
    """Executa código que usa current_tenant_id() (seeds) como se o request
    fosse do tenant alvo, restaurando o contexto do operador depois."""
    anterior = getattr(g, 'tenant', None)
    g.tenant = _to_context(tenant)
    g.pop('_papel_cache', None)
    try:
        yield
    finally:
        g.tenant = anterior
        g.pop('_papel_cache', None)


def mrr_do_tenant(tenant):
    plano = PLANOS.get(tenant.plano)
    if not plano or plano.preco_mensal_brl is None:
        return 0.0
    if tenant.status != 'active' or (tenant.billing_status or 'ativo') == 'suspenso':
        return 0.0
    return plano.preco_mensal_brl


def _metricas_por_tenant():
    from models import Course, User
    sete_dias = datetime.utcnow() - timedelta(days=7)
    usuarios = dict(db.session.query(TenantUser.tenant_id, func.count(TenantUser.user_id))
                    .group_by(TenantUser.tenant_id).all())
    alunos = dict(db.session.query(TenantUser.tenant_id, func.count(TenantUser.user_id))
                  .filter(TenantUser.papel == 'aluno').group_by(TenantUser.tenant_id).all())
    ativos = dict(db.session.query(TenantUser.tenant_id, func.count(TenantUser.user_id))
                  .join(User, User.id == TenantUser.user_id)
                  .filter(User.last_login >= sete_dias).group_by(TenantUser.tenant_id).all())
    ultimo = dict(db.session.query(TenantUser.tenant_id, func.max(User.last_login))
                  .join(User, User.id == TenantUser.user_id).group_by(TenantUser.tenant_id).all())
    cursos = dict(db.session.query(Course.tenant_id, func.count(Course.id))
                  .group_by(Course.tenant_id).all())
    return usuarios, alunos, ativos, ultimo, cursos


def resumo_tenant(tenant, metricas):
    usuarios, alunos, ativos, ultimo, cursos = metricas
    ultimo_acesso = ultimo.get(tenant.id)
    plano = PLANOS.get(tenant.plano)
    return {
        **tenant.to_dict(),
        'plano_nome': plano.nome if plano else tenant.plano,
        'criado_em': tenant.criado_em.isoformat() if tenant.criado_em else None,
        'usuarios': usuarios.get(tenant.id, 0),
        'alunos': alunos.get(tenant.id, 0),
        'ativos_7d': ativos.get(tenant.id, 0),
        'cursos': cursos.get(tenant.id, 0),
        'ultimo_acesso': ultimo_acesso.isoformat() if ultimo_acesso else None,
        'mrr': mrr_do_tenant(tenant),
    }


def listar_tenants(busca='', status='', pagina=1, por_pagina=25):
    q = Tenant.query
    if busca:
        termo = f'%{busca.lower()}%'
        q = q.filter(db.or_(func.lower(Tenant.nome).like(termo), Tenant.slug.like(termo)))
    if status in STATUS_VALIDOS:
        q = q.filter(Tenant.status == status)
    total = q.count()
    tenants = q.order_by(Tenant.criado_em.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    metricas = _metricas_por_tenant()
    return {'tenants': [resumo_tenant(t, metricas) for t in tenants],
            'total': total, 'pagina': pagina, 'por_pagina': por_pagina}


def pulso():
    import time
    from models import User
    inicio = time.perf_counter()
    db.session.execute(db.text('SELECT 1'))
    latencia_db = round((time.perf_counter() - inicio) * 1000, 1)
    try:
        migracao = db.session.execute(db.text('SELECT version_num FROM alembic_version')).scalar()
    except Exception:
        db.session.rollback()
        migracao = None

    tenants = Tenant.query.all()
    metricas = _metricas_por_tenant()
    resumos = [resumo_tenant(t, metricas) for t in tenants]
    agora = datetime.utcnow()

    fila = []
    for r in resumos:
        if r['billing_status'] == 'suspenso':
            fila.append({'nivel': 'high', 'tenant_id': r['id'], 'msg': f"{r['nome']}: suspenso por inadimplência"})
        elif r['billing_status'] == 'leitura':
            fila.append({'nivel': 'warn', 'tenant_id': r['id'], 'msg': f"{r['nome']}: em modo leitura por inadimplência"})
        if r['status'] == 'suspended':
            fila.append({'nivel': 'info', 'tenant_id': r['id'], 'msg': f"{r['nome']}: suspenso pelo operador"})
        if r['status'] == 'active':
            if r['usuarios'] == 0:
                fila.append({'nivel': 'warn', 'tenant_id': r['id'], 'msg': f"{r['nome']}: nenhum usuário cadastrado"})
            elif not r['ultimo_acesso'] or datetime.fromisoformat(r['ultimo_acesso']) < agora - timedelta(days=21):
                fila.append({'nivel': 'warn', 'tenant_id': r['id'], 'msg': f"{r['nome']}: nenhum acesso há mais de 21 dias (risco de churn)"})

    sete_dias = agora - timedelta(days=7)
    return {
        'tecnico': {
            'db_ok': True,
            'db_latencia_ms': latencia_db,
            'migracao': migracao,
            'semaforo': 'verde' if latencia_db < 200 else 'amarelo',
        },
        'negocio': {
            'mrr': round(sum(r['mrr'] for r in resumos), 2),
            'tenants_total': len(resumos),
            'tenants_ativos': sum(1 for r in resumos if r['status'] == 'active'),
            'tenants_pagantes': sum(1 for r in resumos if r['mrr'] > 0),
            'usuarios_ativos_7d': User.query.filter(User.last_login >= sete_dias).count(),
            'novos_tenants_30d': sum(1 for t in tenants if t.criado_em and t.criado_em >= agora - timedelta(days=30)),
        },
        'fila': fila,
    }


def perfil_tenant(tenant_id):
    from models import User
    tenant = Tenant.query.get(tenant_id)
    if not tenant:
        return None
    resumo = resumo_tenant(tenant, _metricas_por_tenant())
    admins = (db.session.query(User).join(TenantUser, TenantUser.user_id == User.id)
              .filter(TenantUser.tenant_id == tenant.id, TenantUser.papel == 'admin').all())
    resumo['admins'] = [{'id': u.id, 'nome': u.name, 'email': u.email,
                         'ultimo_acesso': u.last_login.isoformat() if u.last_login else None} for u in admins]
    eventos = (AuditLog.query.filter_by(tenant_id=tenant.id)
               .order_by(AuditLog.id.desc()).limit(30).all())
    resumo['eventos'] = [e.to_dict() for e in eventos]
    return resumo


def _validar_identificador(valor, campo):
    valor = (valor or '').strip().lower()
    if not RE_SLUG.match(valor):
        raise ErroOperacao(f'{campo}: use 3 a 30 letras minúsculas, números ou hífen')
    if valor in SUBDOMINIOS_RESERVADOS:
        raise ErroOperacao(f'{campo}: "{valor}" é reservado')
    return valor


def disponibilidade(slug):
    try:
        slug = _validar_identificador(slug, 'Subdomínio')
    except ErroOperacao as e:
        return {'disponivel': False, 'motivo': str(e)}
    existe = Tenant.query.filter(db.or_(Tenant.slug == slug, Tenant.subdominio == slug)).first()
    return {'disponivel': existe is None, 'motivo': 'Já está em uso' if existe else ''}


def criar_tenant(operador_user, dados):
    from models import User
    from core.tenancy.auth import invalidar_cache_papel

    nome = (dados.get('nome') or '').strip()
    if not nome or len(nome) > 200:
        raise ErroOperacao('Nome é obrigatório (até 200 caracteres)')
    slug = _validar_identificador(dados.get('slug') or dados.get('subdominio'), 'Subdomínio')
    if not disponibilidade(slug)['disponivel']:
        raise ErroOperacao('Subdomínio já está em uso')
    plano = dados.get('plano') or 'semente'
    if plano not in PLANOS:
        raise ErroOperacao('Plano inválido')

    admin_email = (dados.get('admin_email') or '').strip().lower()
    admin_nome = (dados.get('admin_nome') or '').strip()
    if not admin_email or '@' not in admin_email:
        raise ErroOperacao('E-mail do administrador é obrigatório')

    tenant = Tenant(slug=slug, nome=nome, subdominio=slug, plano=plano, status='active',
                    tema_json={'nome_exibido': nome})
    db.session.add(tenant)
    db.session.flush()

    senha_temporaria = None
    admin = User.query.filter_by(email=admin_email).first()
    if admin is None:
        senha_temporaria = 'XR' + secrets.token_urlsafe(9)
        admin = User(name=admin_nome or admin_email.split('@')[0], email=admin_email,
                     role='aluno', is_active=True, onboarding_completed=True)
        admin.set_password(senha_temporaria)
        db.session.add(admin)
        db.session.flush()
    db.session.add(TenantUser(tenant_id=tenant.id, user_id=admin.id, papel='admin'))
    invalidar_cache_papel(admin.id)

    registrar_auditoria(tenant.id, operador_user.id, 'operador.tenant_criado', alvo=slug,
                        payload={'nome': nome, 'plano': plano, 'admin_email': admin_email,
                                 'admin_novo': senha_temporaria is not None})
    db.session.commit()

    with no_contexto_do_tenant(tenant):
        import seed
        from models import PlatformConfig
        seed.seed_config()
        seed.seed_levels()
        seed.seed_badges()
        seed.seed_achievements()
        import seed_production
        seed_production.seed_categories()
        cfg = PlatformConfig.query.filter_by(tenant_id=tenant.id).first()
        if cfg:
            cfg.platform_name = nome
            db.session.commit()
    clear_tenant_cache()
    return tenant, admin, senha_temporaria


def atualizar_tenant(operador_user, tenant, dados):
    mudancas = {}
    if 'nome' in dados:
        nome = (dados.get('nome') or '').strip()
        if not nome:
            raise ErroOperacao('Nome é obrigatório')
        if nome != tenant.nome:
            mudancas['nome'] = [tenant.nome, nome]
            tenant.nome = nome
    if 'plano' in dados:
        plano = dados.get('plano')
        if plano not in PLANOS:
            raise ErroOperacao('Plano inválido')
        if plano != tenant.plano:
            mudancas['plano'] = [tenant.plano, plano]
            tenant.plano = plano
    if not mudancas:
        return tenant
    registrar_auditoria(tenant.id, operador_user.id, 'operador.tenant_atualizado',
                        alvo=tenant.slug, payload=mudancas)
    db.session.commit()
    clear_tenant_cache()
    return tenant


def mudar_status(operador_user, tenant, novo_status, motivo):
    if novo_status not in STATUS_VALIDOS:
        raise ErroOperacao('Status inválido')
    motivo = (motivo or '').strip()
    if novo_status != 'active' and len(motivo) < 5:
        raise ErroOperacao('Informe o motivo (mínimo 5 caracteres)')
    if tenant.status == novo_status:
        raise ErroOperacao('O tenant já está neste status')
    from core.tenancy.context import default_tenant_id
    if novo_status == 'suspended' and tenant.id == default_tenant_id():
        raise ErroOperacao('O tenant padrão da plataforma não pode ser suspenso')
    anterior = tenant.status
    tenant.status = novo_status
    registrar_auditoria(tenant.id, operador_user.id, f'operador.tenant_{novo_status}',
                        alvo=tenant.slug, payload={'de': anterior, 'para': novo_status, 'motivo': motivo})
    db.session.commit()
    clear_tenant_cache()
    return tenant


def auditoria(tenant_id=None, pagina=1, por_pagina=50):
    q = AuditLog.query.filter(AuditLog.acao.like('operador.%'))
    if tenant_id:
        q = q.filter(AuditLog.tenant_id == tenant_id)
    total = q.count()
    linhas = q.order_by(AuditLog.id.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    from models import User
    nomes = {u.id: u.email for u in User.query.filter(User.id.in_({l.user_id for l in linhas if l.user_id})).all()}
    slugs = {t.id: t.nome for t in Tenant.query.all()}
    return {'total': total, 'pagina': pagina, 'eventos': [
        {**l.to_dict(), 'operador': nomes.get(l.user_id), 'tenant_nome': slugs.get(l.tenant_id)} for l in linhas]}
