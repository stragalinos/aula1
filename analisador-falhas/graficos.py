"""Gráficos do analisador, feitos com Altair (já vem instalado com o Streamlit)."""

import altair as alt
import pandas as pd

from indicadores import numero_br

# Cores testadas para quem tem daltonismo, com uma versão para cada tema.
# Cada tipo de manutenção tem sempre a mesma cor, mesmo se outro sumir no filtro.
TIPOS = ["Corretiva", "Preventiva", "Preditiva", "Outros"]
CORES = {
    "light": {"fundo": "#ffffff", "destaque": "#2a78d6", "neutro": "#898781", "tipos": ["#2a78d6", "#eb6834", "#1baf7a", "#898781"]},
    "dark": {"fundo": "#0e1117", "destaque": "#3987e5", "neutro": "#898781", "tipos": ["#3987e5", "#d95926", "#199e70", "#898781"]},
}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def grafico_pareto(tabela: pd.DataFrame, rotulo_valor: str, tema: str = "light") -> alt.Chart:
    """Barras horizontais do maior para o menor; a classe A fica em destaque."""
    cores = CORES.get(tema, CORES["light"])
    grupos = ["Classe A (até 80% do total)", "Demais"]
    dados = tabela.assign(
        grupo=tabela["classe_a"].map({True: grupos[0], False: grupos[1]}),
        valor_txt=tabela["valor"].map(numero_br),
        percentual_txt=tabela["percentual"].map(lambda v: numero_br(v) + "%"),
        acumulado_txt=tabela["acumulado"].map(lambda v: numero_br(v) + "%"),
    )
    return (
        alt.Chart(dados)
        .mark_bar(size=16, cornerRadiusEnd=4)
        .encode(
            x=alt.X("valor:Q", title=rotulo_valor),
            y=alt.Y("equipamento:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
            color=alt.Color(
                "grupo:N",
                scale=alt.Scale(domain=grupos, range=[cores["destaque"], cores["neutro"]]),
                legend=alt.Legend(title=None, orient="top"),
            ),
            tooltip=[
                alt.Tooltip("equipamento:N", title="Equipamento"),
                alt.Tooltip("valor_txt:N", title=rotulo_valor),
                alt.Tooltip("percentual_txt:N", title="% do total"),
                alt.Tooltip("acumulado_txt:N", title="% acumulado"),
            ],
        )
        .properties(height=alt.Step(28))
    )


def grafico_mensal(tabela: pd.DataFrame, tema: str = "light") -> alt.LayerChart:
    """Uma linha por tipo de manutenção, mostrando quantas OS houve em cada mês."""
    cores = CORES.get(tema, CORES["light"])
    dados = tabela.assign(
        tipo=tabela["tipo_manutencao"].where(tabela["tipo_manutencao"].isin(TIPOS[:3]), "Outros"),
        mes_txt=tabela["mes"].map(lambda m: f"{MESES[int(m[5:7]) - 1]}/{m[2:4]}"),
    )
    dados = dados.groupby(["mes", "mes_txt", "tipo"], as_index=False)["quantidade"].sum()

    presentes = [t for t in TIPOS if t in set(dados["tipo"])]
    ordem_meses = list(dict.fromkeys(dados.sort_values("mes")["mes_txt"]))
    base = alt.Chart(dados).encode(
        x=alt.X("mes_txt:O", sort=ordem_meses, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("quantidade:Q", title="Ordens de serviço"),
        color=alt.Color(
            "tipo:N",
            scale=alt.Scale(domain=presentes, range=[cores["tipos"][TIPOS.index(t)] for t in presentes]),
            legend=alt.Legend(title=None, orient="top"),
        ),
        tooltip=[
            alt.Tooltip("mes_txt:O", title="Mês"),
            alt.Tooltip("tipo:N", title="Tipo"),
            alt.Tooltip("quantidade:Q", title="OS"),
        ],
    )
    linhas = base.mark_line(strokeWidth=2, strokeCap="round", strokeJoin="round")
    # O contorno na cor do fundo separa os pontos quando duas linhas se cruzam
    pontos = base.mark_point(filled=True, size=64, opacity=1, stroke=cores["fundo"], strokeWidth=2)
    return (linhas + pontos).properties(height=320)
