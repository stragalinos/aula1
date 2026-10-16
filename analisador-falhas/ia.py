"""Análise do histórico de falhas com o Claude (API da Anthropic).

O Claude recebe apenas os indicadores já calculados e algumas descrições das
falhas repetitivas, não a planilha inteira. Isso economiza tokens (custo) e
expõe menos dados da empresa.
"""

import anthropic
import pandas as pd

from indicadores import numero_br

MODELO = "claude-opus-5-5"

INSTRUCOES = """Você é um engenheiro de manutenção experiente, especialista em PCM \
(Planejamento e Controle da Manutenção) de frigoríficos: refrigeração industrial \
por amônia, túneis de congelamento, câmaras frias, linhas de abate e desossa, \
embalagem e utilidades.

Você recebe indicadores calculados a partir do histórico de ordens de serviço de \
uma planta e escreve uma análise para a equipe de planejamento da manutenção.

Como trabalhar:
- Use somente os números fornecidos; não invente dados. Quando apontar uma causa \
provável, deixe claro que é hipótese a ser confirmada em campo.
- Seja específico: cite equipamento, componente e números.
- Priorize pelo impacto: horas paradas e falhas que se repetem pesam mais do que \
uma contagem isolada.
- Sugira ações práticas de PCM: ajustar ou criar itens no plano preventivo, \
inspeção preditiva (vibração, termografia), análise de causa raiz, peças críticas \
em estoque, padronização de procedimento, treinamento.
- Quando a ação envolver amônia, vasos de pressão ou caldeiras (NR-13), segurança \
de máquinas (NR-12), saúde e segurança em frigoríficos (NR-36) ou Boas Práticas \
de Fabricação, lembre que a mudança deve ser avaliada por profissional habilitado.

Responda em português do Brasil, em Markdown, com no máximo 600 palavras e estas seções:
## Resumo
## Principais problemas
## Ações recomendadas
(tabela com as colunas: Ação | Equipamento | Prioridade | Por quê)
## Pontos de atenção"""


def _tabela(df: pd.DataFrame) -> str:
    """Tabela em texto (CSV com ';' e vírgula decimal), fácil para o modelo ler."""
    return df.to_csv(index=False, sep=";", decimal=",", float_format="%.1f")


def montar_contexto(
    dados: pd.DataFrame,
    periodo: str,
    horas_por_dia: float,
    resumo: dict,
    equipamentos: pd.DataFrame,
    repetitivas: pd.DataFrame,
    por_mes: pd.DataFrame,
) -> str:
    """Junta os indicadores em um texto que será enviado ao Claude."""
    partes = [
        f"Período analisado: {periodo}",
        f"Horas de operação consideradas por dia: {numero_br(horas_por_dia, 0)}",
        "As horas vêm das horas apontadas nas OS; nas corretivas, são tratadas como tempo de equipamento parado.",
        "",
        "## Resumo geral",
        f"- Ordens de serviço: {resumo['total_os']}",
        f"- Falhas (OS corretivas): {resumo['falhas']} ({numero_br(resumo['percentual_corretiva'])}% do total)",
        f"- Horas paradas por falha: {numero_br(resumo['horas_paradas'])}",
        f"- MTTR geral: {numero_br(resumo['mttr'])} h",
        "",
        "## Indicadores por equipamento (horas; disponibilidade em %)",
        _tabela(equipamentos[["equipamento", "area", "falhas", "horas_paradas", "mttr", "mtbf", "disponibilidade"]]),
        "## OS por mês e tipo de manutenção",
        _tabela(por_mes.pivot_table(index="mes", columns="tipo_manutencao", values="quantidade", aggfunc="sum", fill_value=0).reset_index()),
    ]

    if repetitivas.empty:
        partes.append("## Falhas repetitivas\nNenhuma no período.")
    else:
        partes.append("## Falhas repetitivas (mesmo componente do mesmo equipamento)")
        corretivas = dados[dados["tipo_manutencao"] == "Corretiva"]
        for _, linha in repetitivas.head(10).iterrows():
            mesmas = corretivas[
                (corretivas["equipamento"] == linha["equipamento"])
                & (corretivas["componente"] == linha["componente"])
            ]
            descricoes = mesmas.sort_values("data", ascending=False)["descricao"].head(3)
            partes.append(
                f"- {linha['equipamento']} / {linha['componente']}: {linha['ocorrencias']} ocorrências, "
                f"{numero_br(linha['horas_paradas'])} h paradas, uma falha a cada "
                f"{numero_br(linha['dias_entre_falhas'], 0)} dias em média. "
                f"Descrições recentes: {' | '.join(descricoes)}"
            )

    partes.append("\nFaça a análise seguindo as instruções.")
    return "\n".join(partes)


def analisar(contexto: str, api_key: str | None = None):
    """Pede a análise ao Claude e devolve o texto aos pedaços (streaming).

    Assim a resposta vai aparecendo na tela enquanto é escrita. Sem api_key, o
    SDK usa a variável de ambiente ANTHROPIC_API_KEY.
    """
    cliente = anthropic.Anthropic(api_key=api_key)
    with cliente.beta.messages.stream(
        model=MODELO,
        max_tokens=16000,
        system=INSTRUCOES,
        messages=[{"role": "user", "content": contexto}],
        # "medium" equilibra qualidade e custo; use "high" para análises mais profundas
        output_config={"effort": "medium"},
        # Se o modelo recusar o pedido, a própria API tenta de novo com outro modelo
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        yield from stream.text_stream
        resposta = stream.get_final_message()

    if resposta.stop_reason == "refusal":
        yield "\n\n*O modelo não concluiu esta análise. Tente gerar de novo.*"
    elif resposta.stop_reason == "max_tokens":
        yield "\n\n*A análise foi interrompida por ficar longa demais.*"
