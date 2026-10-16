"""Cálculo dos indicadores de manutenção.

Este arquivo não sabe nada de tela nem de IA: recebe uma tabela de ordens de
serviço (OS) e devolve números. Assim dá para testar cada conta sozinha
(veja a pasta tests/).
"""

import numbers
import unicodedata
from datetime import time, timedelta

import pandas as pd

# Informações que o analisador usa. A chave é o nome interno da coluna; o valor
# é o título da coluna no modelo de planilha (modelo/modelo_ordens_de_servico.xlsx).
COLUNAS = {
    "equipamento": "Equipamento",
    "tipo_manutencao": "Tipo de manutenção",
    "data": "Data",
    "horas": "Horas apontadas",
    "numero_os": "Número da OS",
    "area": "Área",
    "componente": "Componente",
    "descricao": "Descrição do serviço",
}

# Sem estas não dá para calcular nada. As outras são opcionais.
COLUNAS_OBRIGATORIAS = ["equipamento", "tipo_manutencao", "data", "horas"]

CORRETIVA = "Corretiva"
NAO_INFORMADO = "Não informado"


# ---------------------------------------------------------------------------
# Preparação dos dados
# ---------------------------------------------------------------------------

def normalizar_nome(texto) -> str:
    """'Número da OS' -> 'numero_da_os'. Ajuda a reconhecer colunas da planilha."""
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return sem_acento.strip().lower().replace(" ", "_").replace("-", "_")


def sugerir_colunas(colunas_planilha) -> dict:
    """Para cada informação, procura na planilha uma coluna com o mesmo título.

    Aceita tanto o título do modelo ('Horas apontadas') quanto o nome interno
    ('horas'). Devolve None para o que não encontrar.
    """
    por_nome = {normalizar_nome(c): c for c in colunas_planilha}
    return {
        chave: por_nome.get(normalizar_nome(titulo)) or por_nome.get(chave)
        for chave, titulo in COLUNAS.items()
    }


def padronizar_tipo(valor) -> str:
    """Junta as várias formas de escrever o tipo ('CORRETIVA', 'corr. emergencial'...)."""
    if pd.isna(valor) or not str(valor).strip():
        return NAO_INFORMADO
    texto = str(valor).strip().lower()
    if texto.startswith("corr") or "emerg" in texto or "quebra" in texto:
        return CORRETIVA
    if texto.startswith("prev"):
        return "Preventiva"
    if texto.startswith("pred"):
        return "Preditiva"
    return str(valor).strip().capitalize()


def _converter_data(serie: pd.Series) -> pd.Series:
    """Converte textos como '03/04/2026' em datas. O que não der vira vazio (NaT)."""
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie
    return pd.to_datetime(serie, dayfirst=True, format="mixed", errors="coerce")


def converter_horas(valor) -> float:
    """Entende as formas comuns de escrever horas: 1,5 / 1.5 / 1:30 / 01:30:00.

    Também aceita células de Excel formatadas como hora. O que não der para
    entender, ou for negativo, vira vazio (NaN).
    """
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return float("nan")
    if isinstance(valor, timedelta):                          # Excel: [h]:mm
        horas = valor.total_seconds() / 3600
    elif isinstance(valor, time):                             # Excel: h:mm
        horas = valor.hour + valor.minute / 60 + valor.second / 3600
    elif isinstance(valor, numbers.Real):
        horas = float(valor)
    else:
        texto = str(valor).strip()
        try:
            if ":" in texto:                                  # 1:30 ou 01:30:00
                partes = [float(p) for p in texto.split(":")] + [0, 0]
                horas = partes[0] + partes[1] / 60 + partes[2] / 3600
            else:                                             # 1,5 / 1.5 / 1.234,5
                if "," in texto:
                    texto = texto.replace(".", "").replace(",", ".")
                horas = float(texto)
        except ValueError:
            return float("nan")
    return horas if horas >= 0 else float("nan")


def preparar_dados(bruto: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Limpa a tabela de OS: converte datas e horas e padroniza os textos.

    Devolve a tabela limpa e quantas linhas foram descartadas por terem data
    ou horas vazias ou inválidas.
    """
    faltando = [COLUNAS[c] for c in COLUNAS_OBRIGATORIAS if c not in bruto.columns]
    if faltando:
        raise ValueError(f"Faltam colunas obrigatórias: {', '.join(faltando)}")

    dados = bruto.copy()
    for coluna in COLUNAS:
        if coluna not in dados.columns:
            dados[coluna] = NAO_INFORMADO
    dados = dados[list(COLUNAS)]

    for coluna in ["equipamento", "numero_os", "area", "componente", "descricao"]:
        dados[coluna] = dados[coluna].fillna("").astype(str).str.strip().replace("", NAO_INFORMADO)
    dados["tipo_manutencao"] = dados["tipo_manutencao"].map(padronizar_tipo)
    dados["data"] = _converter_data(dados["data"]).dt.normalize()
    dados["horas"] = dados["horas"].map(converter_horas).astype(float)

    validas = dados["data"].notna() & dados["horas"].notna()
    descartadas = int((~validas).sum())
    dados = dados[validas]
    return dados.sort_values("data", kind="stable").reset_index(drop=True), descartadas


def so_corretivas(dados: pd.DataFrame) -> pd.DataFrame:
    """Só as OS corretivas, ou seja, as falhas."""
    return dados[dados["tipo_manutencao"] == CORRETIVA]


# ---------------------------------------------------------------------------
# Indicadores
# ---------------------------------------------------------------------------

def resumo_geral(dados: pd.DataFrame) -> dict:
    """Números gerais do período: total de OS, falhas, horas paradas e MTTR."""
    corretivas = so_corretivas(dados)
    total = len(dados)
    falhas = len(corretivas)
    horas_paradas = float(corretivas["horas"].sum())
    return {
        "total_os": total,
        "falhas": falhas,
        "percentual_corretiva": 100 * falhas / total if total else 0.0,
        "horas_paradas": horas_paradas,
        "mttr": horas_paradas / falhas if falhas else None,
        "equipamentos": dados["equipamento"].nunique(),
    }


def indicadores_por_equipamento(dados: pd.DataFrame, horas_planejadas: float) -> pd.DataFrame:
    """MTBF, MTTR e disponibilidade de cada equipamento.

    horas_planejadas é quanto tempo cada equipamento deveria estar disponível
    no período (ex.: 30 dias x 24 h = 720 h).

    - MTTR = horas paradas por falha / número de falhas
    - MTBF = (horas planejadas - horas paradas) / número de falhas
    - Disponibilidade = (horas planejadas - horas paradas) / horas planejadas
      (é o mesmo que MTBF / (MTBF + MTTR))

    Equipamentos sem nenhuma corretiva aparecem com MTBF e MTTR vazios.
    """
    corretivas = so_corretivas(dados)
    tabela = corretivas.groupby("equipamento").agg(
        falhas=("horas", "size"),
        horas_paradas=("horas", "sum"),
    )
    # Equipamentos que só tiveram preventiva também entram, com zero falhas
    areas = dados.groupby("equipamento")["area"].first()
    tabela = tabela.reindex(areas.index)
    tabela.insert(0, "area", areas)
    tabela["falhas"] = tabela["falhas"].fillna(0).astype(int)
    tabela["horas_paradas"] = tabela["horas_paradas"].fillna(0.0)

    tem_falha = tabela["falhas"] > 0
    horas_funcionando = (horas_planejadas - tabela["horas_paradas"]).clip(lower=0)
    tabela["mttr"] = (tabela["horas_paradas"] / tabela["falhas"]).where(tem_falha)
    tabela["mtbf"] = (horas_funcionando / tabela["falhas"]).where(tem_falha)
    tabela["disponibilidade"] = 100 * horas_funcionando / horas_planejadas

    tabela = tabela.reset_index()
    return tabela.sort_values(["falhas", "horas_paradas", "equipamento"], ascending=[False, False, True]).reset_index(drop=True)


def pareto(dados: pd.DataFrame, coluna: str = "equipamento", medida: str = "falhas") -> pd.DataFrame:
    """Ordena do maior para o menor e marca a "classe A".

    medida pode ser "falhas" (número de corretivas) ou "horas" (horas paradas).
    Classe A são os itens que, somados, respondem por até 80% do total: é onde
    vale concentrar esforço primeiro (a regra 80/20).
    """
    corretivas = so_corretivas(dados)
    if medida == "falhas":
        valores = corretivas.groupby(coluna).size()
    else:
        valores = corretivas.groupby(coluna)["horas"].sum()

    tabela = valores.rename("valor").reset_index()
    tabela = tabela.sort_values(["valor", coluna], ascending=[False, True]).reset_index(drop=True)
    total = tabela["valor"].sum()
    tabela["percentual"] = 100 * tabela["valor"] / total if total else 0.0
    tabela["acumulado"] = tabela["percentual"].cumsum()
    # Um item é classe A se, antes dele, o acumulado ainda não tinha chegado a 80%
    tabela["classe_a"] = (tabela["acumulado"] - tabela["percentual"]) < 80
    return tabela


def falhas_repetitivas(dados: pd.DataFrame, minimo: int = 3) -> pd.DataFrame:
    """O mesmo componente do mesmo equipamento quebrando várias vezes.

    É o sinal clássico de que a causa raiz não foi resolvida: troca-se a peça,
    mas o motivo da quebra continua lá.
    """
    corretivas = so_corretivas(dados)
    grupos = corretivas.groupby(["equipamento", "componente"]).agg(
        ocorrencias=("horas", "size"),
        horas_paradas=("horas", "sum"),
        primeira=("data", "min"),
        ultima=("data", "max"),
    )
    grupos = grupos[grupos["ocorrencias"] >= minimo].copy()
    dias = (grupos["ultima"] - grupos["primeira"]).dt.total_seconds() / 86400
    grupos["dias_entre_falhas"] = dias / (grupos["ocorrencias"] - 1)
    grupos = grupos.reset_index()
    return grupos.sort_values(["ocorrencias", "horas_paradas"], ascending=False).reset_index(drop=True)


def os_por_mes(dados: pd.DataFrame) -> pd.DataFrame:
    """Quantidade de OS por mês e por tipo de manutenção (formato longo)."""
    tabela = dados.assign(mes=dados["data"].dt.strftime("%Y-%m"))
    tabela = tabela.groupby(["mes", "tipo_manutencao"]).size().rename("quantidade").reset_index()
    return tabela.sort_values(["mes", "tipo_manutencao"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------

def numero_br(valor, casas: int = 1) -> str:
    """1234.5 -> '1.234,5' (padrão brasileiro). Valores vazios viram '–'."""
    if valor is None or pd.isna(valor):
        return "–"
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")
