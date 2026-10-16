"""Testes das contas. Rode com:  pytest"""

import math
from datetime import time, timedelta

import pandas as pd
import pytest

from indicadores import (
    converter_horas,
    falhas_repetitivas,
    indicadores_por_equipamento,
    numero_br,
    os_por_mes,
    padronizar_tipo,
    pareto,
    preparar_dados,
    resumo_geral,
    sugerir_colunas,
)


def montar(linhas):
    """Cria uma tabela de OS a partir de tuplas (equipamento, tipo, componente, data, horas)."""
    bruto = pd.DataFrame(linhas, columns=["equipamento", "tipo_manutencao", "componente", "data", "horas"])
    dados, _ = preparar_dados(bruto)
    return dados


@pytest.fixture
def exemplo():
    # Esteira: 2 falhas de rolamento (1 h e 3 h) + 1 preventiva de 2 h
    # Serra: só uma preventiva
    return montar([
        ("Esteira", "Corretiva", "Rolamento", "01/04/2026", "1"),
        ("Esteira", "corretiva", "Rolamento", "10/04/2026", "3,0"),
        ("Esteira", "PREVENTIVA", "Plano", "15/04/2026", 2),
        ("Serra", "Preventiva", "Plano", "20/04/2026", 1.0),
    ])


def test_padronizar_tipo():
    assert padronizar_tipo("CORRETIVA") == "Corretiva"
    assert padronizar_tipo("Corr. emergencial") == "Corretiva"
    assert padronizar_tipo(" preventiva ") == "Preventiva"
    assert padronizar_tipo("Preditiva") == "Preditiva"
    assert padronizar_tipo("melhoria") == "Melhoria"
    assert padronizar_tipo(None) == "Não informado"


def test_converter_horas_aceita_os_formatos_comuns():
    assert converter_horas(1.5) == 1.5
    assert converter_horas("1,5") == 1.5
    assert converter_horas("1.5") == 1.5
    assert converter_horas("1:30") == 1.5
    assert converter_horas("01:30:00") == 1.5
    assert converter_horas("1.234,5") == 1234.5
    assert converter_horas(time(2, 15)) == 2.25              # célula do Excel em formato h:mm
    assert converter_horas(timedelta(hours=26)) == 26        # célula do Excel em formato [h]:mm


def test_converter_horas_recusa_valores_invalidos():
    for valor in ["", "abc", "-2", None, float("nan")]:
        assert math.isnan(converter_horas(valor)), valor


def test_sugerir_colunas_reconhece_titulos_do_modelo():
    colunas = ["Número da OS", "EQUIPAMENTO", "Tipo de manutenção", "Data", "Horas apontadas", "Outra coisa"]
    sugestoes = sugerir_colunas(colunas)
    assert sugestoes["numero_os"] == "Número da OS"
    assert sugestoes["equipamento"] == "EQUIPAMENTO"
    assert sugestoes["tipo_manutencao"] == "Tipo de manutenção"
    assert sugestoes["horas"] == "Horas apontadas"
    assert sugestoes["area"] is None


def test_preparar_dados_le_data_brasileira_e_horas(exemplo):
    primeira = exemplo.iloc[0]
    assert primeira["data"] == pd.Timestamp(2026, 4, 1)
    assert primeira["horas"] == 1
    # Colunas opcionais que não vieram são preenchidas
    assert primeira["area"] == "Não informado"


def test_preparar_dados_descarta_linhas_invalidas():
    bruto = pd.DataFrame({
        "equipamento": ["A", "B", "C"],
        "tipo_manutencao": ["Corretiva"] * 3,
        "data": ["01/04/2026", "sem data", "05/04/2026"],
        "horas": ["1,5", "2", "duas"],
    })
    dados, descartadas = preparar_dados(bruto)
    assert descartadas == 2
    assert list(dados["equipamento"]) == ["A"]
    assert dados["horas"].iloc[0] == 1.5


def test_preparar_dados_reclama_de_coluna_obrigatoria():
    with pytest.raises(ValueError, match="Horas apontadas"):
        preparar_dados(pd.DataFrame({"equipamento": ["A"], "tipo_manutencao": ["Corretiva"], "data": ["01/04/2026"]}))


def test_resumo_geral(exemplo):
    resumo = resumo_geral(exemplo)
    assert resumo["total_os"] == 4
    assert resumo["falhas"] == 2
    assert resumo["percentual_corretiva"] == 50
    assert resumo["horas_paradas"] == 4
    assert resumo["mttr"] == 2


def test_indicadores_por_equipamento(exemplo):
    tabela = indicadores_por_equipamento(exemplo, horas_planejadas=100).set_index("equipamento")

    esteira = tabela.loc["Esteira"]
    assert esteira["falhas"] == 2
    assert esteira["horas_paradas"] == 4
    assert esteira["mttr"] == 2                 # 4 h / 2 falhas
    assert esteira["mtbf"] == 48                # (100 - 4) / 2
    assert esteira["disponibilidade"] == 96     # (100 - 4) / 100

    serra = tabela.loc["Serra"]                 # só preventiva: sem falhas
    assert serra["falhas"] == 0
    assert math.isnan(serra["mttr"]) and math.isnan(serra["mtbf"])
    assert serra["disponibilidade"] == 100


def test_pareto_marca_classe_a():
    linhas = []
    for equipamento, quantidade in [("A", 5), ("B", 3), ("C", 1), ("D", 1)]:
        for _ in range(quantidade):
            linhas.append((equipamento, "Corretiva", "X", "01/04/2026", 1))
    tabela = pareto(montar(linhas))

    assert list(tabela["equipamento"]) == ["A", "B", "C", "D"]
    assert list(tabela["acumulado"]) == [50, 80, 90, 100]
    # A e B somam 80% das falhas: são a classe A
    assert list(tabela["classe_a"]) == [True, True, False, False]


def test_falhas_repetitivas():
    dados = montar([
        ("Esteira", "Corretiva", "Rolamento", "01/04/2026", 1),
        ("Esteira", "Corretiva", "Rolamento", "11/04/2026", 1),
        ("Esteira", "Corretiva", "Rolamento", "21/04/2026", 2),
        ("Esteira", "Corretiva", "Motor", "05/04/2026", 1),
        ("Esteira", "Preventiva", "Rolamento", "15/04/2026", 1),
    ])
    tabela = falhas_repetitivas(dados, minimo=3)

    assert len(tabela) == 1
    linha = tabela.iloc[0]
    assert (linha["componente"], linha["ocorrencias"], linha["horas_paradas"]) == ("Rolamento", 3, 4)
    assert linha["dias_entre_falhas"] == 10


def test_os_por_mes(exemplo):
    tabela = os_por_mes(exemplo)
    assert tabela.to_dict("records") == [
        {"mes": "2026-04", "tipo_manutencao": "Corretiva", "quantidade": 2},
        {"mes": "2026-04", "tipo_manutencao": "Preventiva", "quantidade": 2},
    ]


def test_numero_br():
    assert numero_br(1234.56) == "1.234,6"
    assert numero_br(None) == "–"
