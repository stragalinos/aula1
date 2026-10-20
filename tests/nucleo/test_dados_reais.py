"""Testes de estrutura dos arquivos REAIS da pasta data/.

Estes testes não conferem os números (isso é com você); eles garantem que, ao
preencher os arquivos, nenhuma parte da estrutura foi quebrada e que os
arquivos continuam combinando entre si e com o código.
"""

from eletroprojeto.nucleo.tabelas import (
    ESQUEMA_MINIMO,
    interpretar_faixa,
    procurar_faixa,
)
from eletroprojeto.nucleo.vocabulario import (
    ESQUEMAS_ATERRAMENTO,
    OPCOES_CRITERIOS,
    REGRAS_TUG,
    SISTEMAS_TENSAO,
    TIPOS_CIRCUITO,
    TIPOS_COMODO,
)


def test_todos_os_arquivos_de_data_estao_bem_formados(dados_reais):
    erros = [str(erro) for resultado in dados_reais.verificar() for erro in resultado.erros]
    assert erros == []


def test_arquivos_esperados_existem(dados_reais):
    nomes = set(dados_reais.nomes())
    assert set(ESQUEMA_MINIMO) <= nomes
    assert {"concessionarias/energisa_ms", "concessionarias/_modelo"} <= nomes


def test_tabelas_da_norma_nunca_usam_valores_de_exemplo(dados_reais):
    # Regra do projeto: valores normativos só entram depois de validados por você.
    for nome in dados_reais.nomes():
        if nome.startswith("nbr5410/"):
            assert dados_reais.tabela(nome).status in {"A_VALIDAR", "VALIDADO"}, nome


def test_regras_de_tug_existem_para_todos_os_tipos_de_comodo(dados_reais):
    previsao = dados_reais.tabela("nbr5410/previsao_cargas")
    assert set(previsao.chaves("tug_quantidade")) == set(TIPOS_COMODO)
    for tipo in TIPOS_COMODO:
        regra = previsao.obter("tug_quantidade", tipo, "regra")
        assert regra in REGRAS_TUG, f"{tipo}: regra '{regra}' desconhecida"
        campos = set(previsao.chaves("tug_quantidade", tipo))
        assert set(REGRAS_TUG[regra]) <= campos, f"{tipo}: faltam campos da regra '{regra}'"


def test_listas_de_tipos_de_comodo_usam_nomes_conhecidos(dados_reais):
    previsao = dados_reais.tabela("nbr5410/previsao_cargas")
    regras = dados_reais.tabela("nbr5410/regras_circuitos")
    listas = [
        previsao.obter("tug_potencia", "comodos_com_potencia_maior", "tipos"),
        regras.obter("tipos_com_tomadas_em_circuito_exclusivo"),
    ]
    for lista in listas:
        assert set(lista) <= set(TIPOS_COMODO)


def test_exigencias_de_dr_cobrem_todos_os_comodos_e_circuitos(dados_reais):
    dr = dados_reais.tabela("nbr5410/exigencias_dr")
    assert set(dr.chaves("por_tipo_comodo")) == set(TIPOS_COMODO)
    for tipo in TIPOS_COMODO:
        assert set(dr.chaves("por_tipo_comodo", tipo)) == set(TIPOS_CIRCUITO)


def test_dps_cobre_todos_os_esquemas_e_sistemas_de_tensao(dados_reais):
    dps = dados_reais.tabela("nbr5410/dps")
    assert set(dps.chaves("por_esquema")) == set(ESQUEMAS_ATERRAMENTO)
    for esquema in ESQUEMAS_ATERRAMENTO:
        assert set(dps.chaves("por_esquema", esquema)) == set(SISTEMAS_TENSAO)


def test_secoes_do_catalogo_sao_as_mesmas_da_tabela_de_capacidade(dados_reais):
    capacidade = dados_reais.tabela("nbr5410/capacidade_conducao")
    condutores = dados_reais.tabela("catalogos/condutores")
    for tipo in condutores.chaves("tipos"):
        isolacao = condutores.obter("tipos", tipo, "isolacao")
        assert condutores.chaves("tipos", tipo, "diametro_externo_mm") == capacidade.chaves(
            "capacidade_A", isolacao
        ), tipo


def test_colunas_de_capacidade_sao_iguais_para_todas_as_isolacoes(dados_reais):
    capacidade = dados_reais.tabela("nbr5410/capacidade_conducao")
    colunas = set()
    for isolacao in capacidade.chaves("capacidade_A"):
        primeira_linha = capacidade.chaves("capacidade_A", isolacao)[0]
        colunas.add(tuple(capacidade.chaves("capacidade_A", isolacao, primeira_linha)))
    assert len(colunas) == 1


def test_colunas_de_agrupamento_sao_faixas_sem_buracos_nem_sobreposicao(dados_reais):
    agrupamento = dados_reais.tabela("nbr5410/fator_agrupamento")
    assert set(agrupamento.chaves("fatores")) == set(agrupamento.chaves("arranjos"))
    for arranjo in agrupamento.chaves("fatores"):
        colunas = agrupamento.chaves("fatores", arranjo)
        for chave in colunas:
            interpretar_faixa(chave)
        # De 1 a 40 circuitos, cada quantidade deve cair em exatamente uma coluna.
        for quantidade in range(1, 41):
            procurar_faixa(colunas, quantidade)


def test_faixas_por_quantidade_da_concessionaria_cobrem_de_1_em_diante(dados_reais):
    for nome in dados_reais.nomes():
        if not nome.startswith("concessionarias/"):
            continue
        concessionaria = dados_reais.tabela(nome)
        for grupo in concessionaria.chaves("demanda", "grupos"):
            if concessionaria.obter("demanda", "grupos", grupo, "tipo") != "por_quantidade":
                continue
            chaves = concessionaria.chaves("demanda", "grupos", grupo, "fatores")
            for quantidade in range(1, 21):
                procurar_faixa(chaves, quantidade)


def test_taxa_de_ocupacao_cobre_qualquer_numero_de_condutores(dados_reais):
    taxa = dados_reais.tabela("nbr5410/taxa_ocupacao")
    for quantidade in range(1, 31):
        procurar_faixa(taxa.chaves("taxa_maxima_pct"), quantidade)


def test_criterios_de_projeto_usam_opcoes_conhecidas(dados_reais):
    criterios = dados_reais.tabela("criterios_projeto")
    for caminho, opcoes in OPCOES_CRITERIOS.items():
        assert criterios.obter(*caminho) in opcoes, " > ".join(caminho)
    for tipo in ("iluminacao", "tug"):
        assert 0 < criterios.obter("fator_potencia_padrao", tipo) <= 1


def test_curvas_dos_criterios_existem_no_catalogo(dados_reais):
    criterios = dados_reais.tabela("criterios_projeto")
    disjuntores = dados_reais.tabela("catalogos/disjuntores")
    curvas = disjuntores.obter("termomagneticos", "curvas")
    for campo in criterios.chaves("protecao"):
        if campo.startswith("curva_"):
            assert criterios.obter("protecao", campo) in curvas, campo


def test_equipamentos_tipicos_tem_campos_completos(dados_reais):
    equipamentos = dados_reais.tabela("catalogos/equipamentos_tipicos")
    for nome in equipamentos.chaves("equipamentos"):
        dados = equipamentos.obter("equipamentos", nome)
        assert set(dados) == {"descricao", "potencia_W", "fator_potencia", "tensao_V", "tem_motor"}
        assert 0 < dados["fator_potencia"] <= 1, nome
        assert dados["tensao_V"] in (127, 220), nome


def test_equipamentos_citados_na_concessionaria_existem(dados_reais):
    conhecidos = set(dados_reais.tabela("catalogos/equipamentos_tipicos").chaves("equipamentos"))
    for nome in dados_reais.nomes():
        if not nome.startswith("concessionarias/"):
            continue
        concessionaria = dados_reais.tabela(nome)
        for grupo in concessionaria.chaves("demanda", "grupos"):
            campos = concessionaria.chaves("demanda", "grupos", grupo)
            if "equipamentos" in campos:
                lista = concessionaria.obter("demanda", "grupos", grupo, "equipamentos")
                assert set(lista) <= conhecidos, f"{nome} > {grupo}"


def test_metodos_de_instalacao_tem_meio_ar_ou_solo(dados_reais):
    metodos = dados_reais.tabela("nbr5410/metodos_instalacao")
    for forma in metodos.chaves("formas_instalacao"):
        assert metodos.obter("formas_instalacao", forma, "meio") in {"ar", "solo"}, forma
        assert metodos.obter("formas_instalacao", forma, "descricao"), forma
