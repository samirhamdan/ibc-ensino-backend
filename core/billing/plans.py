"""
Catálogo de planos — BIL-01, doc 00-VISAO.md §6:

| Plano       | Alunos até | Preço/mês | Observação                              |
|-------------|-----------:|----------:|------------------------------------------|
| Semente     |         50 |    R$ 149 | Tutor com cota mensal de interações      |
| Crescimento |        250 |    R$ 349 | Tutor + revisão espaçada + analytics     |
| Comunidade  |      1.000 |    R$ 699 | Tudo + white-label completo + API        |
| Enterprise  |  ilimitado | sob consulta | SSO, SLA, instância dedicada          |

JUDGMENT CALL (cota de interações de IA por plano): o PRD (§4.4 TUT-05)
exige cota por plano mas não numera "básica/padrão/avançada" (§00 só
descreve o eixo de alunos/preço). Os números abaixo são uma primeira
estimativa arredondada — não modelagem de custo real — para destravar
TUT-05/BIL-03 nesta release; ajustar quando houver dados de uso reais
(ver NFR-07: custo de IA < 8% da receita do tenant em regime).
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Plano:
    nome: str
    limite_alunos: Optional[int]           # None = ilimitado (Enterprise)
    cota_interacoes_ia_mes: Optional[int]  # None = sob consulta (Enterprise)
    preco_mensal_brl: Optional[float]      # None = "sob consulta" (Enterprise)


PLANOS = {
    'semente': Plano(
        nome='Semente',
        limite_alunos=50,
        cota_interacoes_ia_mes=500,     # provisório: ~10 interações/aluno/mês
        preco_mensal_brl=149.0,
    ),
    'crescimento': Plano(
        nome='Crescimento',
        limite_alunos=250,
        cota_interacoes_ia_mes=3000,    # provisório: ~12 interações/aluno/mês
        preco_mensal_brl=349.0,
    ),
    'comunidade': Plano(
        nome='Comunidade',
        limite_alunos=1000,
        cota_interacoes_ia_mes=15000,   # provisório: ~15 interações/aluno/mês
        preco_mensal_brl=699.0,
    ),
    'enterprise': Plano(
        nome='Enterprise',
        limite_alunos=None,             # ilimitado
        cota_interacoes_ia_mes=None,    # sob consulta / contrato dedicado
        preco_mensal_brl=None,          # sob consulta
    ),
}


def get_plan(nome):
    """Retorna o `Plano` pelo nome (chave, case-insensitive). Levanta
    `KeyError` com mensagem clara para nome desconhecido — não retorna None
    silenciosamente, para não deixar código chamador com um plano fantasma."""
    chave = (nome or '').strip().lower()
    try:
        return PLANOS[chave]
    except KeyError:
        raise KeyError(
            f"Plano desconhecido: {nome!r}. Planos válidos: "
            f"{', '.join(sorted(PLANOS))}"
        )
