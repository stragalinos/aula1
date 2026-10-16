"""Gera um histórico FICTÍCIO de ordens de serviço de um frigorífico.

Os dados são inventados, mas imitam situações reais para o analisador ter o
que mostrar. Alguns problemas foram "plantados" de propósito:

- o ventilador do evaporador do Túnel de congelamento 02 quebra sem parar,
  e cada vez mais perto do fim do período;
- o rolamento da Esteira de desossa 03 é trocado repetidamente;
- a resistência de selagem da Embaladora a vácuo 02 queima com frequência.

Para gerar o arquivo de novo:  python gerar_dados_exemplo.py
"""

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

INICIO = datetime(2026, 4, 1)
DIAS = 183  # abril a setembro de 2026
ARQUIVO = Path(__file__).parent / "dados" / "os_exemplo.csv"

# Cada equipamento: área, componentes que falham (com peso = chance relativa),
# quantas corretivas no período, faixa de horas de reparo e se as falhas
# ficam mais frequentes com o tempo.
EQUIPAMENTOS = {
    "Compressor de amônia 01": {
        "area": "Sala de máquinas",
        "componentes": {"Selo mecânico": 3, "Válvula de sucção": 1, "Pressostato de óleo": 2},
        "falhas": 5, "horas": (2, 8), "piorando": False,
    },
    "Compressor de amônia 02": {
        "area": "Sala de máquinas",
        "componentes": {"Selo mecânico": 1, "Válvula de sucção": 2, "Pressostato de óleo": 1},
        "falhas": 3, "horas": (2, 8), "piorando": False,
    },
    "Condensador evaporativo 01": {
        "area": "Sala de máquinas",
        "componentes": {"Bomba de água": 2, "Correia do ventilador": 2},
        "falhas": 4, "horas": (1, 4), "piorando": False,
    },
    "Túnel de congelamento 01": {
        "area": "Congelamento",
        "componentes": {"Ventilador do evaporador": 1, "Porta / vedação": 2, "Sensor de temperatura": 1},
        "falhas": 4, "horas": (1, 4), "piorando": False,
    },
    "Túnel de congelamento 02": {
        "area": "Congelamento",
        "componentes": {"Ventilador do evaporador": 7, "Porta / vedação": 1, "Sensor de temperatura": 1},
        "falhas": 12, "horas": (2, 6), "piorando": True,
    },
    "Câmara fria 03": {
        "area": "Estocagem",
        "componentes": {"Porta / vedação": 2, "Válvula de expansão": 1},
        "falhas": 3, "horas": (1, 3), "piorando": False,
    },
    "Serra de carcaça": {
        "area": "Abate",
        "componentes": {"Lâmina": 3, "Mangueira hidráulica": 2, "Motor": 1},
        "falhas": 8, "horas": (0.5, 2), "piorando": False,
    },
    "Nória de abate": {
        "area": "Abate",
        "componentes": {"Corrente": 2, "Roldana": 2, "Redutor": 1},
        "falhas": 6, "horas": (0.5, 3), "piorando": False,
    },
    "Esteira de desossa 03": {
        "area": "Desossa",
        "componentes": {"Rolamento": 6, "Lona": 1, "Motor": 1},
        "falhas": 10, "horas": (0.5, 2), "piorando": False,
    },
    "Esteira de desossa 05": {
        "area": "Desossa",
        "componentes": {"Rolamento": 1, "Lona": 1, "Motor": 1},
        "falhas": 3, "horas": (0.5, 2), "piorando": False,
    },
    "Embaladora a vácuo 02": {
        "area": "Embalagem",
        "componentes": {"Resistência de selagem": 5, "Bomba de vácuo": 2, "Sensor de posição": 1},
        "falhas": 9, "horas": (0.5, 3), "piorando": False,
    },
    "Termoformadora 01": {
        "area": "Embalagem",
        "componentes": {"Molde": 1, "Resistência de selagem": 1, "Corrente de arraste": 2},
        "falhas": 4, "horas": (1, 4), "piorando": False,
    },
    "Caldeira 01": {
        "area": "Utilidades",
        "componentes": {"Bomba de alimentação": 1, "Queimador": 1},
        "falhas": 2, "horas": (2, 6), "piorando": False,
    },
    "Esteira de expedição 01": {
        "area": "Expedição",
        "componentes": {"Rolete": 2, "Sensor fotoelétrico": 2, "Motor": 1},
        "falhas": 4, "horas": (0.5, 2), "piorando": False,
    },
    "Lavador de caixas": {
        "area": "Higienização",
        "componentes": {"Bomba": 2, "Bico aspersor": 2, "Resistência": 1},
        "falhas": 5, "horas": (0.5, 2), "piorando": False,
    },
}

# Como o técnico costuma descrever cada tipo de problema.
DESCRICOES = {
    "Selo mecânico": ["Vazamento de óleo pelo selo, substituído selo mecânico", "Selo com vazamento, troca do kit de vedação"],
    "Válvula de sucção": ["Ruído anormal na sucção, válvula substituída", "Válvula de sucção travada, feita limpeza e ajuste"],
    "Pressostato de óleo": ["Compressor desarmando por baixa pressão de óleo, pressostato trocado", "Pressostato descalibrado, recalibrado"],
    "Bomba de água": ["Bomba de água sem pressão, troca do rotor", "Vazamento na bomba de água, troca de gaxeta"],
    "Correia do ventilador": ["Correia rompida, substituída", "Correia patinando, tensionada e alinhada"],
    "Ventilador do evaporador": [
        "Ventilador do evaporador com vibração alta, trocado rolamento do motor",
        "Motor do ventilador do evaporador queimado, motor substituído",
        "Ventilador parado por gelo acumulado na hélice, feito degelo e limpeza",
        "Hélice do ventilador desbalanceada, substituída",
    ],
    "Porta / vedação": ["Vedação da porta danificada, perda de frio, borracha trocada", "Porta não fechando, ajuste de dobradiça e trinco"],
    "Sensor de temperatura": ["Leitura de temperatura incoerente, sensor trocado", "Sensor com mau contato, refeita conexão"],
    "Válvula de expansão": ["Superaquecimento alto, válvula de expansão ajustada", "Válvula de expansão obstruída, substituída"],
    "Lâmina": ["Lâmina sem corte, substituída", "Lâmina trincada, troca imediata"],
    "Mangueira hidráulica": ["Vazamento de óleo hidráulico, mangueira substituída", "Mangueira ressecada rompeu, trocada"],
    "Motor": ["Motor desarmando por sobrecarga, verificado e substituído", "Motor com aquecimento excessivo, troca de rolamentos"],
    "Corrente": ["Corrente com elo quebrado, emenda substituída", "Corrente esticada, ajuste de tensão"],
    "Roldana": ["Roldana travada no trilho, substituída", "Roldana com desgaste, troca do conjunto"],
    "Redutor": ["Redutor com ruído, troca de óleo e rolamento", "Vazamento no retentor do redutor, retentor trocado"],
    "Rolamento": [
        "Esteira fazendo barulho, rolamento do tambor trocado",
        "Rolamento travado no lado do motor, substituído",
        "Rolamento com folga, trocado",
    ],
    "Lona": ["Lona rasgada, emenda feita", "Lona desalinhada, ajuste de alinhamento"],
    "Resistência de selagem": [
        "Selagem falhando, resistência queimada substituída",
        "Embalagem com solda fraca, resistência trocada",
    ],
    "Bomba de vácuo": ["Vácuo insuficiente, troca de palhetas da bomba", "Bomba de vácuo com óleo contaminado, troca de óleo"],
    "Sensor de posição": ["Máquina parando no meio do ciclo, sensor de posição trocado", "Sensor sujo, limpeza e ajuste"],
    "Molde": ["Molde desalinhado, ajustado", "Molde danificado, substituído"],
    "Corrente de arraste": ["Corrente de arraste saindo da guia, ajustada", "Elo quebrado na corrente de arraste, trocado"],
    "Bomba de alimentação": ["Bomba de alimentação sem vazão, troca de selo", "Bomba de alimentação com ruído, rolamento trocado"],
    "Queimador": ["Falha na ignição do queimador, eletrodo trocado", "Chama instável, limpeza do queimador"],
    "Rolete": ["Rolete travado, substituído", "Rolete com ruído, trocado"],
    "Sensor fotoelétrico": ["Esteira não para no ponto, sensor fotoelétrico trocado", "Sensor desalinhado, ajustado"],
    "Bomba": ["Bomba sem pressão, troca de rotor", "Vazamento no selo da bomba, selo trocado"],
    "Bico aspersor": ["Bicos entupidos, limpeza dos bicos", "Bico quebrado, substituído"],
    "Resistência": ["Água sem aquecer, resistência substituída", "Resistência em curto, trocada"],
}


def momento_aleatorio(rng, piorando):
    """Sorteia um momento dentro do período (concentrado no fim se 'piorando')."""
    if piorando:
        dia = rng.triangular(0, DIAS, DIAS)
    else:
        dia = rng.uniform(0, DIAS)
    dia = min(int(dia), DIAS - 1)
    return INICIO + timedelta(days=dia, hours=rng.randint(0, 23), minutes=rng.choice(range(0, 60, 5)))


def gerar(semente=42):
    rng = random.Random(semente)
    ordens = []

    for equipamento, info in EQUIPAMENTOS.items():
        # Corretivas (falhas)
        nomes = list(info["componentes"])
        pesos = list(info["componentes"].values())
        for _ in range(info["falhas"]):
            componente = rng.choices(nomes, weights=pesos)[0]
            inicio = momento_aleatorio(rng, info["piorando"])
            horas = round(rng.uniform(*info["horas"]) * 4) / 4  # arredonda para 15 min
            ordens.append({
                "equipamento": equipamento,
                "area": info["area"],
                "tipo_manutencao": "Corretiva",
                "componente": componente,
                "descricao": rng.choice(DESCRICOES[componente]),
                "inicio": inicio,
                "fim": inicio + timedelta(hours=max(horas, 0.25)),
            })

        # Uma preventiva por mês, em um dia útil de manhã
        for mes in range(4, 10):
            inicio = datetime(2026, mes, rng.randint(5, 25), rng.choice([7, 8, 13]), 0)
            ordens.append({
                "equipamento": equipamento,
                "area": info["area"],
                "tipo_manutencao": "Preventiva",
                "componente": "Plano preventivo",
                "descricao": "Execução do plano preventivo mensal (inspeção, lubrificação e reapertos)",
                "inicio": inicio,
                "fim": inicio + timedelta(hours=rng.choice([1, 1.5, 2, 3])),
            })

        # Compressores também recebem análise de vibração mensal (preditiva)
        if "Compressor" in equipamento:
            for mes in range(4, 10):
                inicio = datetime(2026, mes, rng.randint(1, 28), 10, 0)
                ordens.append({
                    "equipamento": equipamento,
                    "area": info["area"],
                    "tipo_manutencao": "Preditiva",
                    "componente": "Análise de vibração",
                    "descricao": "Coleta e análise de vibração dos mancais",
                    "inicio": inicio,
                    "fim": inicio + timedelta(minutes=30),
                })

    ordens.sort(key=lambda os_: os_["inicio"])
    for numero, os_ in enumerate(ordens, start=1):
        os_["numero_os"] = f"OS-2026-{numero:04d}"
    return ordens


def salvar(ordens, arquivo=ARQUIVO):
    """Salva em CSV no padrão do Excel brasileiro (separador ';' e data dd/mm/aaaa)."""
    arquivo.parent.mkdir(exist_ok=True)
    colunas = ["numero_os", "equipamento", "area", "tipo_manutencao", "componente", "descricao", "inicio", "fim"]
    with open(arquivo, "w", newline="", encoding="utf-8-sig") as saida:
        escritor = csv.DictWriter(saida, fieldnames=colunas, delimiter=";")
        escritor.writeheader()
        for os_ in ordens:
            linha = dict(os_)
            linha["inicio"] = os_["inicio"].strftime("%d/%m/%Y %H:%M")
            linha["fim"] = os_["fim"].strftime("%d/%m/%Y %H:%M")
            escritor.writerow({c: linha[c] for c in colunas})


if __name__ == "__main__":
    ordens = gerar()
    salvar(ordens)
    print(f"{len(ordens)} ordens de serviço salvas em {ARQUIVO}")
