"""Vocabulário fixo do sistema.

São os identificadores que ligam o formulário, os arquivos de ``data/`` e o núcleo
de cálculo. Nenhum valor normativo fica aqui: só nomes e as opções que o código
sabe tratar.
"""

# Tipos de cômodo (decisão D1). As regras de cada tipo ficam em
# data/nbr5410/previsao_cargas.yaml e data/nbr5410/exigencias_dr.yaml.
TIPOS_COMODO: dict[str, str] = {
    "sala": "Sala",
    "dormitorio": "Dormitório",
    "cozinha": "Cozinha",
    "copa": "Copa",
    "copa_cozinha": "Copa-cozinha",
    "area_servico": "Área de serviço",
    "lavanderia": "Lavanderia",
    "banheiro": "Banheiro (com chuveiro ou banheira)",
    "lavabo": "Lavabo (sem chuveiro)",
    "varanda": "Varanda",
    "garagem": "Garagem",
    "corredor_hall": "Corredor / hall",
    "escritorio": "Escritório",
    "area_externa": "Área externa",
    "outro": "Outro",
}

TIPOS_CIRCUITO: dict[str, str] = {
    "iluminacao": "Iluminação",
    "tug": "Tomadas de uso geral (TUG)",
    "tue": "Tomadas e pontos de uso específico (TUE)",
}

SISTEMAS_TENSAO: dict[str, str] = {
    "127/220": "127/220 V",
    "220/380": "220/380 V",
}

ESQUEMAS_ATERRAMENTO: dict[str, str] = {
    "TN-S": "TN-S",
    "TN-C-S": "TN-C-S",
    "TT": "TT",
}

ISOLACOES: dict[str, str] = {
    "PVC_70C": "PVC (70 °C)",
    "EPR_XLPE_90C": "EPR ou XLPE (90 °C)",
}

# Regras de quantidade mínima de TUG que o núcleo sabe aplicar, com os campos
# que cada uma exige em data/nbr5410/previsao_cargas.yaml.
REGRAS_TUG: dict[str, tuple[str, ...]] = {
    "quantidade_fixa": ("quantidade",),
    "por_perimetro": ("perimetro_por_ponto_m", "parcelas"),
    "por_area_e_perimetro": (
        "area_limite_m2",
        "pontos_ate_area_limite",
        "perimetro_por_ponto_m",
        "parcelas",
    ),
}

# Opções aceitas em data/criterios_projeto.yaml (caminho do campo -> opções).
OPCOES_CRITERIOS: dict[tuple[str, ...], tuple[str, ...]] = {
    ("dimensionamento", "ordem"): ("disjuntor_primeiro", "cabo_primeiro"),
    ("dimensionamento", "metodo_queda_tensao"): ("resistividade", "queda_unitaria_catalogo"),
    ("dimensionamento", "temperatura_intermediaria"): ("usar_linha_superior",),
    ("agrupamento", "sem_trechos_informados"): ("todos_os_circuitos_do_quadro",),
    ("protecao", "dr_aplicar_em"): ("circuitos_exigidos", "todos"),
    ("protecao", "dr_arranjo"): ("por_circuito", "por_grupo", "geral"),
}
