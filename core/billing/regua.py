"""
Régua de inadimplência — BIL-02 (doc 02-ARQUITETURA.md §4.8, PRD §4.8),
PR 3 de 4 do módulo de billing.

Semântica (exata, do task spec da Release 1.0):
  - D+10 desde que a Subscription entrou em 'overdue' (e ainda está overdue,
    ainda não voltou a pagar): Tenant.billing_status -> 'leitura'.
  - D+30: Tenant.billing_status -> 'suspenso'.
  - Idempotente: rodar a régua duas vezes no mesmo dia para um tenant já em
    'leitura'/'suspenso' não reenvia e-mail nem duplica auditoria — só age
    em cima de uma TRANSIÇÃO real de billing_status.

Não é um scheduler em processo: `workers/`/APScheduler/cron não existem
neste repo (mesma constatação de docs/DEBITOS.md #25 pro RQ) — esta é uma
função pura, invocável por um scheduler EXTERNO (cron do SO, Railway Cron
Job, etc.) via `scripts/regua_cobranca.py`. `hoje` é parâmetro explícito
(nunca `date.today()` direto no corpo do laço) exatamente para permitir
testar os limiares D+9/D+10/D+29/D+30 com clock mockado sem monkeypatch de
módulo.

Cross-tenant + RLS/GUC (mesma classe de problema documentada em
docs/DEBITOS.md #26, resolvida no webhook do Asaas na PR 2): este job
itera Subscriptions de TODOS os tenants — não há g.tenant nenhum (não é
uma request). Mesmo fix: a consulta que decide QUAIS tenants avaliar usa
uma conexão RAW (db.engine.connect(), fora do listener de
core/tenancy/rls.py, que está registrado em Session, não em
Engine/Connection) — nunca `Subscription.query.filter_by(...)` puro, que
cairia no modo mono-tenant (tenant padrão) do listener e nunca veria
subscriptions de nenhum outro tenant. Depois de identificar os candidatos
por linha crua, cada transição individual usa `set_current_tenant()` +
`db.session.rollback()` (mesmo padrão do webhook) para abrir a próxima
transação da Session já com o GUC do tenant CERTO antes de qualquer
escrita ORM daquele tenant.

JUDGMENT CALL (evento de domínio): a régua publica `billing.leitura` /
`billing.suspenso` — tipos PRÓPRIOS, não reaproveita `pagamento.falhou`
(doc 02 §7). Razão: `pagamento.falhou` já está semanticamente amarrado a
UM evento de pagamento (webhook Asaas, payload com `payment`); a régua não
tem um pagamento novo para anexar ao evento — é uma decisão derivada de
TEMPO decorrido, payload diferente (`dias_overdue`, `subscription_id`), e
consumidores futuros (ex.: um worker que dispara comunicação de cobrança)
plausivelmente querem reagir SÓ a essas transições sem filtrar dentro de
`pagamento.falhou`. Mantém a convenção `dominio.evento` do doc 02 §7.
"""
import html
import logging
import smtplib
import os
import uuid as uuid_mod
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import text

from extensions import db
from core.billing.models import Subscription
from core.tenancy.models import Tenant, TenantUser
from core.tenancy.context import set_current_tenant
from shared.audit import registrar_auditoria
from shared.events import publish_event

logger = logging.getLogger(__name__)

D_LEITURA = 10
D_SUSPENSO = 30


def _candidatos_overdue():
    """Linhas cruas (sem RLS/GUC — não há g.tenant no job) de subscriptions
    overdue com `overdue_desde` conhecido. Ver nota de RLS/GUC no topo do
    arquivo: NUNCA `Subscription.query.filter_by(...)` aqui.

    Exclui tenants com `regua_pausada=True` (PR 4, BIL-03): override manual
    do operador pra negociação em andamento — ver docs/OPS-BILLING.md
    "Pausar a régua para negociação". `:pausada` é passado como parâmetro
    (não interpolado) pra funcionar nos dois dialetos (Postgres booleano
    nativo, SQLite 0/1) sem SQL condicional por dialect."""
    with db.engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, tenant_id, overdue_desde FROM subscriptions "
                 "WHERE status = 'overdue' AND overdue_desde IS NOT NULL "
                 "AND (regua_pausada IS NULL OR regua_pausada = :pausada)"),
            {'pausada': False},
        ).fetchall()
    return list(rows)


def pausar_regua(tenant_id, pausar=True):
    """Override do operador (docs/OPS-BILLING.md): pausa/retoma a régua de
    inadimplência para UM tenant específico, tipicamente durante negociação
    de pagamento. Não altera billing_status/status — só faz
    `_candidatos_overdue` ignorar este tenant enquanto `pausar=True`. Uso
    esperado: `flask shell` / script de operador (nenhuma rota HTTP nesta
    PR — a única superfície é este helper, mesmo nível de acesso que os
    outros scripts operacionais deste módulo, ver scripts/regua_cobranca.py).
    Retorna a Subscription atualizada ou None se o tenant não tiver uma.

    Mesmo cuidado de GUC/RLS do resto deste arquivo: quem chama isto (shell
    de operador, script) não necessariamente tem `g.tenant` setado pro
    tenant certo (pode não haver request nenhum) — `set_current_tenant` +
    `rollback` antes da consulta ORM garante que a transação abre com o GUC
    do tenant CERTO, não o padrão/mono-tenant."""
    tenant = Tenant.query.get(tenant_id)   # tenants não tem RLS — seguro direto
    if tenant is None:
        return None
    set_current_tenant(tenant)
    db.session.rollback()

    sub = Subscription.query.filter_by(tenant_id=tenant_id).first()
    if sub is None:
        return None
    sub.regua_pausada = bool(pausar)
    db.session.commit()
    return sub


def _admin_email(tenant_id):
    """E-mail do admin do tenant (tenant_users.papel='admin_tenant', o
    primeiro por id — não há hoje um conceito de "admin principal" separado
    de "qualquer admin"). `users` não é tenant-scoped (legado, fora do
    Alembic) — consulta direta é segura independente do GUC/RLS."""
    from models import User
    vinculo = (TenantUser.query
               .filter_by(tenant_id=tenant_id, papel='admin_tenant')
               .order_by(TenantUser.user_id.asc())
               .first())
    if vinculo is None:
        return None
    user = User.query.get(vinculo.user_id)
    if user is None:
        return None
    return user.email, user.name


def _enviar_email_billing(to_email, to_name, assunto, titulo, corpo_html):
    """Mesmo mecanismo de routes/auth.py::_send_reset_email (SMTP síncrono,
    mesmas variáveis de ambiente) — reutilizado aqui em vez de duplicar um
    segundo cliente de e-mail. Falha de envio NUNCA propaga: é logada e a
    régua segue para o próximo tenant (uma falha de SMTP de um tenant não
    pode travar o lote inteiro)."""
    smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', 587))
    smtp_user = os.getenv('SMTP_USER', '')
    smtp_pass = os.getenv('SMTP_PASS', '')
    from_name = os.getenv('EMAIL_FROM_NAME', 'IBC Ensino')

    if not smtp_user or not smtp_pass:
        logger.warning('regua: SMTP não configurado, e-mail "%s" não enviado para %s',
                        assunto, to_email)
        return False

    # html.escape no nome do admin: achado Low da revisão Fable 5 — só
    # afeta a própria caixa do admin (sem vazamento cross-tenant), mas um
    # nome com HTML/tag quebraria o layout do e-mail sem isto.
    corpo_email = f"""
    <div style="font-family:sans-serif;max-width:500px;margin:auto;padding:2rem">
      <h2 style="color:#1a2e52">{html.escape(titulo)}</h2>
      <p>Olá, <strong>{html.escape(to_name)}</strong>!</p>
      {corpo_html}
      <hr style="border:none;border-top:1px solid #eee;margin:1.5rem 0">
      <p style="color:#999;font-size:.75rem;text-align:center">IBC Ensino — Igreja Batista Central</p>
    </div>
    """
    msg = MIMEMultipart('alternative')
    msg['Subject'] = assunto
    msg['From'] = f'{from_name} <{smtp_user}>'   # header, não HTML — sem html.escape aqui
    msg['To'] = to_email
    msg.attach(MIMEText(corpo_email, 'html'))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        return True
    except Exception:
        logger.exception('regua: falha ao enviar e-mail "%s" para %s', assunto, to_email)
        return False


def _transicionar(tenant, novo_billing_status, dias_overdue, sub_id, evento_dominio,
                   assunto, titulo, corpo_html):
    """Aplica UMA transição de billing_status já confirmada como necessária
    pelo chamador (idempotência é responsabilidade do chamador — checa
    tenant.billing_status ANTES de chamar). GUC/RLS já deve estar setado
    para este tenant (set_current_tenant + rollback feito pelo chamador)."""
    tenant.billing_status = novo_billing_status
    registrar_auditoria(
        tenant.id, user_id=None, acao=f'billing.{novo_billing_status}',
        alvo=f'subscription:{sub_id}',
        payload={'dias_overdue': dias_overdue, 'subscription_id': sub_id},
    )
    publish_event(tenant.id, evento_dominio, {
        'dias_overdue': dias_overdue,
        'subscription_id': sub_id,
        'billing_status': novo_billing_status,
    })
    db.session.commit()

    admin = _admin_email(tenant.id)
    if admin is not None:
        to_email, to_name = admin
        _enviar_email_billing(to_email, to_name, assunto, titulo, corpo_html)
    else:
        logger.warning('regua: tenant %s sem admin_tenant vinculado, e-mail não enviado', tenant.id)


def executar_regua(hoje=None):
    """Roda a régua de inadimplência para TODOS os tenants overdue.
    `hoje` é explícito (default `date.today()`) para permitir teste com
    clock mockado — ver docstring do módulo.

    Retorna um resumo (dict) com contagens, útil pro CLI/logs do job."""
    if hoje is None:
        hoje = date.today()

    resumo = {'avaliados': 0, 'leitura': 0, 'suspenso': 0, 'sem_transicao': 0}

    for row in _candidatos_overdue():
        sub_id, tenant_id, overdue_desde = row[0], row[1], row[2]
        # Mesma normalização do webhook (core/billing/routes.py): a conexão
        # raw devolve tenant_id como veio do driver (string no SQLite).
        tenant_id = tenant_id if isinstance(tenant_id, uuid_mod.UUID) else uuid_mod.UUID(str(tenant_id))
        resumo['avaliados'] += 1

        if isinstance(overdue_desde, str):
            overdue_desde = date.fromisoformat(overdue_desde)
        dias = (hoje - overdue_desde).days

        # tenants NÃO tem RLS (só tabelas de domínio, mesmo racional do
        # webhook em routes.py) — seguro buscar direto antes do GUC setado.
        tenant = Tenant.query.get(tenant_id)
        if tenant is None:
            logger.error('regua: tenant %s (subscription %s) não existe mais, pulando', tenant_id, sub_id)
            continue

        # Mesmo fix do webhook (docs/DEBITOS.md #26): a consulta acima já
        # abriu uma transação na Session ANTES do GUC deste tenant existir.
        # set_current_tenant + rollback garante que a PRÓXIMA transação
        # (as escritas de verdade abaixo) abre com o GUC correto.
        set_current_tenant(tenant)
        db.session.rollback()

        if dias >= D_SUSPENSO and tenant.billing_status != 'suspenso':
            _transicionar(
                tenant, 'suspenso', dias, sub_id, 'billing.suspenso',
                assunto='Sua conta foi suspensa por inadimplência — IBC Ensino',
                titulo='⚠️ Conta suspensa',
                corpo_html=(
                    '<p>Sua assinatura está em atraso há mais de 30 dias e o acesso '
                    'da sua organização à plataforma foi <strong>suspenso</strong>.</p>'
                    '<p>Regularize o pagamento para restabelecer o acesso.</p>'
                ),
            )
            resumo['suspenso'] += 1
        elif dias >= D_LEITURA and tenant.billing_status == 'ativo':
            _transicionar(
                tenant, 'leitura', dias, sub_id, 'billing.leitura',
                assunto='Pagamento em atraso — acesso em modo leitura — IBC Ensino',
                titulo='⚠️ Pagamento em atraso',
                corpo_html=(
                    '<p>Identificamos um atraso no pagamento da sua assinatura há mais '
                    'de 10 dias. O acesso da sua organização entrou em '
                    '<strong>modo leitura</strong> (sem novas ações) até a regularização.</p>'
                ),
            )
            resumo['leitura'] += 1
        else:
            resumo['sem_transicao'] += 1

    return resumo
