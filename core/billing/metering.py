"""
Medição de consumo de IA — BIL-03 (doc 02-ARQUITETURA.md §4.8/§4.4 TUT-05),
PR 4 de 4 do módulo de billing.

STUB explícito: nenhuma função aqui chama um provedor de IA de verdade —
elas só REGISTRAM/LEEM a tabela `ai_usage` (PR 1). Quando `ai/` (próximo
módulo da Release 1.0, doc 02 §3) existir, `registrar_interacao_ia` é
chamada depois de cada chamada real via `ai/providers/` (CLAUDE.md regra 5
— este módulo não faz a chamada de IA em si, só contabiliza).

Tenant explícito (docs/DEBITOS.md #24/#26, mesma disciplina de PR 2/3):
TODA função aqui recebe `tenant_id` como parâmetro e NUNCA lê
`current_tenant_id()`/`g.tenant` implicitamente — `ai/` vai chamar isto de
QUALQUER contexto de request (tutor de aluno, endpoint de admin, etc.), e
eventualmente de um worker (RQ, quando existir — docs/DEBITOS.md #25), onde
não há `g.tenant` nenhum.

GUC/RLS (mesma classe de problema de docs/DEBITOS.md #26): diferente do
webhook do Asaas ou da régua, aqui o `tenant_id` normalmente CHEGA de dentro
de uma request onde `g.tenant` já deveria estar correto (TEN-02 já rodou
antes de qualquer rota de `ai/`). Mas "deveria" não é garantia — e a própria
docstring desta PR pede pra não assumir isso: um worker futuro, um teste, ou
uma chamada errada de `ai/` poderiam passar um `tenant_id` que NÃO bate com
`g.tenant` da request atual. `ai_usage`/`subscriptions` têm RLS (PR 1), e o
listener de `core/tenancy/rls.py` fixa o GUC a partir de `g.tenant` — não do
parâmetro. Se os dois divergissem, a escrita cairia silenciosamente no GUC
errado (RLS bloqueia sem avisar, ou pior, escreve pro tenant errado se o GUC
por acaso bater com outro tenant válido). Por isso: TODA função aqui busca o
Tenant por `tenant_id` (tabela sem RLS, seguro direto) e chama
`set_current_tenant()` + `db.session.rollback()` ANTES de qualquer leitura/
escrita ORM em tabela tenant-scoped — mesmo padrão de `regua.py`/
`routes.py::webhook_asaas` — em vez de confiar que `g.tenant` já está certo.
O custo (uma query a mais em `tenants`, sem RLS, e um rollback de transação
só-leitura) é desprezível comparado ao risco de escrever/ler no GUC errado.
"""
import logging
from datetime import date

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from extensions import db
from core.billing.models import AiUsage, Subscription
from core.billing.plans import get_plan
from core.tenancy.context import set_current_tenant
from core.tenancy.models import Tenant
from shared.events import publish_event

logger = logging.getLogger(__name__)

LIMIAR_ALERTA_80PCT = 0.8


def _periodo_atual(hoje=None):
    """'YYYY-MM' (mesmo formato de `AiUsage.periodo`, ver JUDGMENT CALL em
    core/billing/models.py). `hoje` é parâmetro explícito (nunca
    `date.today()` direto no corpo das funções públicas) para permitir
    testar a virada de mês com clock mockado — mesmo padrão de
    `regua.py::executar_regua(hoje=None)`."""
    if hoje is None:
        hoje = date.today()
    return hoje.strftime('%Y-%m')


def _ativar_tenant(tenant_id):
    """Busca o Tenant (tabela sem RLS, seguro direto) e fixa o GUC via
    `set_current_tenant` + `rollback` antes de qualquer ORM tenant-scoped —
    ver nota de RLS/GUC no topo do arquivo. Retorna o Tenant ou None se
    `tenant_id` não existir (chamador decide o que fazer).

    ATENÇÃO (achado Low da revisão Fable 5): o `rollback()` aqui descarta
    QUALQUER trabalho pendente na sessão ORM que já existisse antes desta
    chamada — ok pros pontos de entrada deste módulo (cada função pública
    chama isto primeiro, antes de qualquer escrita própria), mas não chame
    isto no MEIO de um fluxo maior de `ai/` que já tenha alterações
    pendentes na sessão sem commitar — o rollback apagaria elas junto."""
    tenant = Tenant.query.get(tenant_id)
    if tenant is None:
        return None
    set_current_tenant(tenant)
    db.session.rollback()
    return tenant


def registrar_interacao_ia(tenant_id, tokens_in=0, tokens_out=0, custo_estimado=0, hoje=None):
    """Upsert do agregado mensal de uso de IA do tenant (BIL-03, stub — não
    chama provedor nenhum, só contabiliza). Incrementa `interacoes` em 1 e
    acumula tokens/custo. Cria a linha do período se ainda não existir
    (`AiUsage.tenant_id+periodo` é UNIQUE — PR 1).

    Achado Medium da revisão Fable 5: a versão anterior fazia
    leitura-modificação-escrita em Python (`uso.interacoes = uso.interacoes
    + 1`) — duas chamadas concorrentes do MESMO tenant/período (plausível
    de verdade: gunicorn com múltiplas threads, dois tutores de IA
    respondendo quase ao mesmo tempo) perdem incremento (undercounta uma
    métrica de billing) e a corrida "criar a linha do mês" podia estourar
    IntegrityError sem tratamento. Trocado por UPDATE...WHERE atômico com
    incremento em SQL (soma no próprio banco, não em Python) — se a linha
    ainda não existe (rowcount 0), tenta INSERT; se OUTRA requisição venceu
    a corrida de criação entre o UPDATE falho e o INSERT, IntegrityError é
    tratado como "a linha já existe agora" e o UPDATE é refeito (dessa vez
    com sucesso). Mesma classe de padrão já usada em
    routes/trails.py::claim_trail_if_complete e
    routes/gamification.py::award_points (streak) — nunca
    SELECT...FOR UPDATE, que não serializa em SQLite (onde a suíte roda)."""
    tenant = _ativar_tenant(tenant_id)
    if tenant is None:
        raise ValueError(f'registrar_interacao_ia: tenant {tenant_id!r} não existe')

    periodo = _periodo_atual(hoje)
    tin, tout, custo = int(tokens_in or 0), int(tokens_out or 0), float(custo_estimado or 0)

    resultado = db.session.execute(
        update(AiUsage)
        .where(AiUsage.tenant_id == tenant_id, AiUsage.periodo == periodo)
        .values(interacoes=AiUsage.interacoes + 1,
                tokens_entrada=AiUsage.tokens_entrada + tin,
                tokens_saida=AiUsage.tokens_saida + tout,
                custo_estimado=AiUsage.custo_estimado + custo)
    )
    if resultado.rowcount == 0:
        try:
            with db.session.begin_nested():
                db.session.add(AiUsage(tenant_id=tenant_id, periodo=periodo, interacoes=1,
                                       tokens_entrada=tin, tokens_saida=tout, custo_estimado=custo))
        except IntegrityError:
            # Corrida: outra requisição criou a linha entre o UPDATE (que
            # não achou nada) e este INSERT — a linha já existe agora,
            # refaz o UPDATE atômico, que desta vez encontra e incrementa.
            db.session.execute(
                update(AiUsage)
                .where(AiUsage.tenant_id == tenant_id, AiUsage.periodo == periodo)
                .values(interacoes=AiUsage.interacoes + 1,
                        tokens_entrada=AiUsage.tokens_entrada + tin,
                        tokens_saida=AiUsage.tokens_saida + tout,
                        custo_estimado=AiUsage.custo_estimado + custo)
            )
    db.session.commit()
    return AiUsage.query.filter_by(tenant_id=tenant_id, periodo=periodo).first()


def _plano_do_tenant(tenant):
    """Plano ATUAL do tenant para fins de cota de IA.

    JUDGMENT CALL (fonte de verdade divergente, docs/DEBITOS.md #27):
    `Subscription.plano` (PR 1) é o plano de COBRANÇA — o que o Asaas de
    fato fatura, atualizado pelo fluxo de assinatura/checkout. `Tenant.plano`
    (pré-existente, TEN-01) é uma coluna solta, default 'semente', usada
    hoje só como metadado exposto em `Tenant.to_dict()`/cache de contexto
    (`core/tenancy/middleware.py`) — nada neste repo escreve nela depois da
    criação do tenant. As duas podem divergir (ex.: tenant faz upgrade via
    Asaas, `Subscription.plano` muda, `Tenant.plano` fica parado no valor de
    criação) — não há sincronização entre elas nesta PR. Para cota de IA
    (dinheiro real sendo gasto), a fonte de verdade tem que ser a que
    reflete o que o tenant PAGA: `Subscription.plano`. Se não houver
    `Subscription` (tenant nunca assinou/checkout pendente), cai pro
    `Tenant.plano` (mesmo default 'semente' de sempre) — mais seguro do que
    levantar exceção/tratar como sem-cota."""
    sub = Subscription.query.filter_by(tenant_id=tenant.id).first()
    nome_plano = sub.plano if sub is not None else tenant.plano
    return get_plan(nome_plano)


def consumo_do_tenant(tenant_id, hoje=None):
    """Fração 0.0-1.0 do consumo de IA do tenant no período atual contra a
    cota do plano. Enterprise (`cota_interacoes_ia_mes=None`, "sob
    consulta") retorna 0.0 — nunca "acima da cota" nem ZeroDivisionError:
    sem número de cota, não há como estar "acima" dele."""
    tenant = _ativar_tenant(tenant_id)
    if tenant is None:
        raise ValueError(f'consumo_do_tenant: tenant {tenant_id!r} não existe')

    plano = _plano_do_tenant(tenant)
    if not plano.cota_interacoes_ia_mes:
        return 0.0

    periodo = _periodo_atual(hoje)
    uso = AiUsage.query.filter_by(tenant_id=tenant_id, periodo=periodo).first()
    interacoes = uso.interacoes if uso is not None else 0
    return interacoes / plano.cota_interacoes_ia_mes


def checar_cota(tenant_id, hoje=None):
    """True se dentro da cota (consumo <= 1.0), False se acima.

    Publica `ai.cota_80pct` (doc 02 §7) na PRIMEIRA vez que o consumo do
    período cruza 80% — não a cada chamada subsequente enquanto o tenant
    segue entre 80% e 100%. Rastreado por `AiUsage.alerta_80pct_enviado`
    (PR 4, coluna nova): por linha (1 por tenant+período), reseta sozinho a
    cada mês novo (linha nova nasce com o default False) — não é uma flag
    "pra sempre" no tenant, é por período, que é o que o spec pede (crossing
    80% de novo num período NOVO dispara evento de novo)."""
    tenant = _ativar_tenant(tenant_id)
    if tenant is None:
        raise ValueError(f'checar_cota: tenant {tenant_id!r} não existe')

    consumo = consumo_do_tenant(tenant_id, hoje=hoje)

    periodo = _periodo_atual(hoje)
    if consumo >= LIMIAR_ALERTA_80PCT:
        # Achado Medium da revisão Fable 5: check-then-set em Python
        # (ler alerta_80pct_enviado, decidir, só depois marcar True) tem a
        # mesma corrida clássica que o webhook/streak já corrigiram noutro
        # lugar deste módulo — duas chamadas concorrentes cruzando 80% ao
        # mesmo tempo podiam publicar o evento duas vezes. UPDATE guardado
        # por `alerta_80pct_enviado = false`: só a chamada que MUDA a linha
        # de fato (rowcount 1) publica o evento; a perdedora da corrida
        # recebe rowcount 0 e não publica nada.
        resultado = db.session.execute(
            update(AiUsage)
            .where(AiUsage.tenant_id == tenant_id, AiUsage.periodo == periodo,
                   AiUsage.alerta_80pct_enviado.is_(False))
            .values(alerta_80pct_enviado=True)
        )
        if resultado.rowcount == 1:
            uso = AiUsage.query.filter_by(tenant_id=tenant_id, periodo=periodo).first()
            publish_event(tenant_id, 'ai.cota_80pct', {
                'periodo': periodo,
                'consumo': consumo,
                'interacoes': uso.interacoes if uso else None,
            })
            db.session.commit()
            logger.info('metering.checar_cota: tenant %s cruzou 80%% de cota em %s (%.1f%%)',
                        tenant_id, periodo, consumo * 100)
        else:
            db.session.rollback()

    return consumo <= 1.0
