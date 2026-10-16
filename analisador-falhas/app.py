"""Analisador de histórico de falhas - a tela do projeto (Streamlit).

Para abrir:  streamlit run app.py
"""

import os
from pathlib import Path

import anthropic
import pandas as pd
import streamlit as st

import graficos
import ia
from indicadores import (
    COLUNAS,
    COLUNAS_OBRIGATORIAS,
    falhas_repetitivas,
    indicadores_por_equipamento,
    normalizar_nome,
    numero_br,
    os_por_mes,
    pareto,
    preparar_dados,
    resumo_geral,
)

ARQUIVO_EXEMPLO = Path(__file__).parent / "dados" / "os_exemplo.csv"
NAO_TENHO = "(não tenho)"

st.set_page_config(page_title="Analisador de falhas", page_icon="🔧", layout="wide")


# ---------------------------------------------------------------------------
# Leitura da planilha
# ---------------------------------------------------------------------------

def ler_planilha(arquivo) -> pd.DataFrame:
    """Lê CSV (separado por ';' ou ',') ou Excel (.xlsx)."""
    nome = getattr(arquivo, "name", str(arquivo)).lower()
    if nome.endswith(".xlsx"):
        return pd.read_excel(arquivo)
    try:
        return pd.read_csv(arquivo, sep=None, engine="python", encoding="utf-8-sig")
    except UnicodeDecodeError:
        # Planilhas salvas pelo Excel em português costumam vir em latin-1
        if hasattr(arquivo, "seek"):
            arquivo.seek(0)
        return pd.read_csv(arquivo, sep=None, engine="python", encoding="latin-1")


def escolher_colunas(bruto: pd.DataFrame) -> pd.DataFrame:
    """Pergunta qual coluna da planilha corresponde a cada informação."""
    opcoes = [NAO_TENHO] + list(bruto.columns)
    por_nome = {normalizar_nome(c): c for c in bruto.columns}
    sugestoes = {chave: por_nome.get(chave, NAO_TENHO) for chave in COLUNAS}
    achou_todas = all(sugestoes[c] != NAO_TENHO for c in COLUNAS_OBRIGATORIAS)

    escolhas = {}
    with st.sidebar.expander("Colunas da planilha", expanded=not achou_todas):
        st.caption("Diga qual coluna da sua planilha tem cada informação. * = obrigatória")
        for chave, rotulo in COLUNAS.items():
            obrigatoria = " *" if chave in COLUNAS_OBRIGATORIAS else ""
            escolhas[chave] = st.selectbox(
                rotulo + obrigatoria, opcoes, index=opcoes.index(sugestoes[chave]), key=f"coluna_{chave}"
            )

    faltando = [COLUNAS[c] for c in COLUNAS_OBRIGATORIAS if escolhas[c] == NAO_TENHO]
    if faltando:
        st.warning(f"Escolha na barra lateral as colunas obrigatórias: {', '.join(faltando)}.")
        st.stop()

    renomear = {origem: destino for destino, origem in escolhas.items() if origem != NAO_TENHO}
    return bruto[list(renomear)].rename(columns=renomear)


# ---------------------------------------------------------------------------
# Barra lateral: dados e parâmetros
# ---------------------------------------------------------------------------

st.sidebar.header("Dados")
fonte = st.sidebar.radio("De onde vêm as ordens de serviço?", ["Dados de exemplo (fictícios)", "Minha planilha"])

if fonte == "Minha planilha":
    arquivo = st.sidebar.file_uploader("Planilha de OS (CSV ou Excel)", type=["csv", "xlsx"])
    if arquivo is None:
        st.title("🔧 Analisador de histórico de falhas")
        st.info(
            "Envie na barra lateral uma planilha de ordens de serviço (exportada do SAP, de outro sistema "
            "ou do Excel). Cada linha deve ser uma OS. Colunas obrigatórias: **equipamento**, **tipo de "
            "manutenção** (corretiva, preventiva...), **início** e **fim** da intervenção. Opcionais: número "
            "da OS, área, componente e descrição."
        )
        st.stop()
    bruto = escolher_colunas(ler_planilha(arquivo))
else:
    bruto = ler_planilha(ARQUIVO_EXEMPLO)

st.sidebar.header("Parâmetros")
horas_por_dia = st.sidebar.slider(
    "Horas de operação por dia", 1, 24, 24,
    help="Quanto tempo por dia os equipamentos deveriam estar disponíveis. Usado no MTBF e na disponibilidade.",
)
minimo_repeticoes = st.sidebar.slider(
    "Falha repetitiva a partir de", 2, 10, 3,
    help="Quantas falhas do mesmo componente, no mesmo equipamento, contam como falha repetitiva.",
)

api_key = None
if not os.environ.get("ANTHROPIC_API_KEY"):
    st.sidebar.header("Inteligência artificial")
    api_key = st.sidebar.text_input(
        "Chave da API da Anthropic", type="password",
        help="Só é necessária para a aba 'Análise com IA'. Crie a sua em console.anthropic.com.",
    ) or None

try:
    dados, descartadas = preparar_dados(bruto)
except ValueError as erro:
    st.error(str(erro))
    st.stop()

if descartadas:
    st.sidebar.warning(f"{descartadas} linha(s) ignorada(s) por data vazia, inválida ou com fim antes do início.")
if dados.empty:
    st.error("Nenhuma ordem de serviço com datas válidas foi encontrada na planilha.")
    st.stop()


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------

st.title("🔧 Analisador de histórico de falhas")
st.caption("Indicadores de manutenção (MTBF, MTTR, disponibilidade, Pareto) e análise com IA a partir das ordens de serviço.")

primeiro_dia = dados["inicio"].min().date()
ultimo_dia = dados["inicio"].max().date()
coluna_area, coluna_periodo = st.columns([2, 1])
areas = coluna_area.multiselect("Áreas", sorted(dados["area"].unique()), placeholder="Todas as áreas")
periodo = coluna_periodo.date_input(
    "Período", (primeiro_dia, ultimo_dia), min_value=primeiro_dia, max_value=ultimo_dia, format="DD/MM/YYYY"
)
if len(periodo) != 2:
    st.info("Escolha a data final do período.")
    st.stop()

data_inicial, data_final = periodo
filtro = (dados["inicio"].dt.date >= data_inicial) & (dados["inicio"].dt.date <= data_final)
if areas:
    filtro &= dados["area"].isin(areas)
filtrado = dados[filtro]

if filtrado.empty:
    st.warning("Nenhuma ordem de serviço com esses filtros.")
    st.stop()

dias = (data_final - data_inicial).days + 1
horas_planejadas = dias * horas_por_dia
texto_periodo = f"{data_inicial:%d/%m/%Y} a {data_final:%d/%m/%Y} ({dias} dias)"

resumo = resumo_geral(filtrado)
equipamentos = indicadores_por_equipamento(filtrado, horas_planejadas)
repetitivas = falhas_repetitivas(filtrado, minimo_repeticoes)
por_mes = os_por_mes(filtrado)
tema = st.context.theme.type or "light"


# ---------------------------------------------------------------------------
# Números principais
# ---------------------------------------------------------------------------

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Ordens de serviço", resumo["total_os"])
c2.metric("Falhas (corretivas)", resumo["falhas"])
c3.metric(
    "Corretivas no total", f"{numero_br(resumo['percentual_corretiva'], 0)}%",
    help="Quanto menor, mais a manutenção está sendo planejada em vez de apagar incêndio.",
)
c4.metric("Horas paradas por falha", f"{numero_br(resumo['horas_paradas'], 0)} h")
c5.metric("MTTR geral", f"{numero_br(resumo['mttr'])} h", help="Tempo médio para reparar uma falha.")

aba_equip, aba_pareto, aba_repet, aba_mes, aba_ia, aba_dados = st.tabs(
    ["Equipamentos", "Pareto", "Falhas repetitivas", "Evolução mensal", "Análise com IA", "Ordens de serviço"]
)


# ---------------------------------------------------------------------------
# Abas
# ---------------------------------------------------------------------------

with aba_equip:
    st.dataframe(
        equipamentos.round(1),
        hide_index=True,
        width="stretch",
        column_config={
            "equipamento": "Equipamento",
            "area": "Área",
            "falhas": st.column_config.NumberColumn("Falhas"),
            "horas_paradas": st.column_config.NumberColumn("Horas paradas", format="localized"),
            "mttr": st.column_config.NumberColumn("MTTR (h)", format="localized"),
            "mtbf": st.column_config.NumberColumn("MTBF (h)", format="localized"),
            "disponibilidade": st.column_config.NumberColumn("Disponibilidade (%)", format="localized"),
        },
    )
    st.caption(
        f"Base de cálculo: {numero_br(horas_planejadas, 0)} horas planejadas por equipamento "
        f"({dias} dias × {horas_por_dia} h). **MTTR** = horas paradas ÷ falhas. "
        "**MTBF** = (horas planejadas − horas paradas) ÷ falhas. "
        "**Disponibilidade** = (horas planejadas − horas paradas) ÷ horas planejadas. "
        "Só OS corretivas contam como falha."
    )

with aba_pareto:
    medida = st.radio("Medir por", ["Número de falhas", "Horas paradas"], horizontal=True)
    chave = "falhas" if medida == "Número de falhas" else "horas"
    tabela_pareto = pareto(filtrado, "equipamento", chave)
    if tabela_pareto.empty:
        st.success("Nenhuma falha no período. 🎉")
    else:
        classe_a = tabela_pareto[tabela_pareto["classe_a"]]
        st.markdown(
            f"**{len(classe_a)} de {len(tabela_pareto)} equipamentos** concentram "
            f"**{numero_br(classe_a['acumulado'].iloc[-1], 0)}%** {'das falhas' if chave == 'falhas' else 'das horas paradas'}. "
            "Comece por eles."
        )
        st.altair_chart(graficos.grafico_pareto(tabela_pareto, medida, tema), width="stretch")
        with st.expander("Ver tabela"):
            st.dataframe(
                tabela_pareto.drop(columns="classe_a").round(1),
                hide_index=True,
                width="stretch",
                column_config={
                    "equipamento": "Equipamento",
                    "valor": st.column_config.NumberColumn(medida, format="localized"),
                    "percentual": st.column_config.NumberColumn("% do total", format="%.1f%%"),
                    "acumulado": st.column_config.NumberColumn("% acumulado", format="%.1f%%"),
                },
            )

with aba_repet:
    st.markdown(
        f"Mesmo componente do mesmo equipamento falhando **{minimo_repeticoes} vezes ou mais**. "
        "Normalmente a peça é trocada, mas a causa da quebra continua lá: são candidatas a análise de causa raiz."
    )
    if repetitivas.empty:
        st.success("Nenhuma falha repetitiva no período.")
    else:
        st.dataframe(
            repetitivas.round({"horas_paradas": 1, "dias_entre_falhas": 1}),
            hide_index=True,
            width="stretch",
            column_config={
                "equipamento": "Equipamento",
                "componente": "Componente",
                "ocorrencias": "Ocorrências",
                "horas_paradas": st.column_config.NumberColumn("Horas paradas", format="localized"),
                "primeira": st.column_config.DatetimeColumn("Primeira", format="DD/MM/YYYY"),
                "ultima": st.column_config.DatetimeColumn("Última", format="DD/MM/YYYY"),
                "dias_entre_falhas": st.column_config.NumberColumn("Dias entre falhas (média)", format="%.0f"),
            },
        )

with aba_mes:
    st.altair_chart(graficos.grafico_mensal(por_mes, tema), width="stretch")
    st.caption("Se as corretivas sobem enquanto as preventivas ficam iguais, o plano preventivo pode não estar pegando as falhas.")
    with st.expander("Ver tabela"):
        st.dataframe(
            por_mes.pivot_table(index="mes", columns="tipo_manutencao", values="quantidade", aggfunc="sum", fill_value=0),
            width="stretch",
        )

with aba_ia:
    st.markdown(
        "O Claude lê os indicadores acima e escreve um resumo com os principais problemas e ações recomendadas. "
        "São enviados **apenas os números calculados** e as descrições das falhas repetitivas, não a planilha inteira."
    )
    st.caption("A IA sugere; a decisão é da equipe técnica. Confira sempre antes de aplicar.")

    contexto = ia.montar_contexto(filtrado, texto_periodo, horas_por_dia, resumo, equipamentos, repetitivas, por_mes)
    with st.expander("Ver exatamente o que será enviado"):
        st.code(contexto, language=None)

    sem_chave = api_key is None and not os.environ.get("ANTHROPIC_API_KEY")
    if sem_chave:
        st.info("Para usar esta aba, coloque sua chave da API da Anthropic na barra lateral.")

    if st.button("Gerar análise", type="primary", disabled=sem_chave):
        try:
            with st.spinner("O Claude está analisando os dados..."):
                texto = st.write_stream(ia.analisar(contexto, api_key))
            st.session_state["analise"] = {"contexto": contexto, "texto": texto}
        except anthropic.AuthenticationError:
            st.error("Chave da API inválida. Confira a chave na barra lateral.")
        except anthropic.RateLimitError:
            st.error("Limite de uso da API atingido. Espere um pouco e tente de novo.")
        except anthropic.APIConnectionError:
            st.error("Não foi possível conectar à API. Verifique a internet.")
        except anthropic.APIStatusError as erro:
            st.error(f"A API respondeu com erro {erro.status_code}: {erro.message}")
    else:
        # Mostra a última análise, se ela foi feita com estes mesmos filtros
        anterior = st.session_state.get("analise")
        if anterior and anterior["contexto"] == contexto:
            st.markdown(anterior["texto"])

    analise = st.session_state.get("analise")
    if analise and analise["contexto"] == contexto:
        st.download_button(
            "Baixar análise (.md)", analise["texto"], file_name="analise_falhas.md", mime="text/markdown"
        )

with aba_dados:
    st.dataframe(
        filtrado.drop(columns="horas").assign(horas=filtrado["horas"].round(2)),
        hide_index=True,
        width="stretch",
        column_config={
            "numero_os": "OS",
            "equipamento": "Equipamento",
            "area": "Área",
            "tipo_manutencao": "Tipo",
            "componente": "Componente",
            "descricao": "Descrição",
            "inicio": st.column_config.DatetimeColumn("Início", format="DD/MM/YYYY HH:mm"),
            "fim": st.column_config.DatetimeColumn("Fim", format="DD/MM/YYYY HH:mm"),
            "horas": st.column_config.NumberColumn("Horas", format="localized"),
        },
    )
