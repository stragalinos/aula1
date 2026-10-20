"""Testes do leitor das tabelas de data/ (nucleo/tabelas.py).

Aqui não há conta elétrica: os testes conferem se o sistema lê os arquivos
corretamente e se avisa com clareza quando algo está faltando ou mal digitado.
"""

import math
import textwrap

import pytest

from eletroprojeto.nucleo.tabelas import (
    ArquivoInvalido,
    ChaveInexistente,
    ValorNaoAplicavel,
    ValorPendente,
    interpretar_faixa,
    procurar_faixa,
)

METADADOS = """\
metadados:
  titulo: Arquivo de teste
  status: EXEMPLO
"""


def arquivo(corpo: str, metadados: str = METADADOS) -> str:
    """Monta o texto de um arquivo de dados com cabeçalho válido."""
    return metadados + textwrap.dedent(corpo)


def erros_de(repositorio) -> list[str]:
    return [str(erro) for resultado in repositorio.verificar() for erro in resultado.erros]


def avisos_de(repositorio) -> list[str]:
    return [str(aviso) for resultado in repositorio.verificar() for aviso in resultado.avisos]


# ---------------------------------------------------------------------------
# Leitura de valores
# ---------------------------------------------------------------------------


def test_bloco_tabela_e_lido_por_linha_e_coluna(dados_ficticios):
    # Tabela fictícia: linha 2,5 mm², coluna B1 com 2 condutores carregados = 20 A.
    tabela = dados_ficticios.tabela("nbr5410/capacidade_conducao")
    assert tabela.obter("capacidade_A", "PVC_70C", "2.5", "B1-2") == 20
    assert tabela.obter("capacidade_A", "PVC_70C", "2.5", "B1-3") == 18


def test_secao_pode_ser_pedida_como_numero_ou_como_texto(dados_ficticios):
    tabela = dados_ficticios.tabela("nbr5410/capacidade_conducao")
    assert tabela.obter("capacidade_A", "PVC_70C", 2.5, "B1-2") == 20
    assert tabela.obter("capacidade_A", "PVC_70C", 4, "B1-2") == 30
    assert tabela.obter("capacidade_A", "PVC_70C", 4.0, "B1-2") == 30


def test_chaves_mantem_a_ordem_do_arquivo(dados_ficticios):
    tabela = dados_ficticios.tabela("nbr5410/capacidade_conducao")
    assert tabela.chaves("capacidade_A", "PVC_70C") == ["1.5", "2.5", "4", "6"]
    assert tabela.chaves("capacidade_A", "PVC_70C", "1.5") == ["B1-2", "B1-3"]


def test_chave_inexistente_mostra_as_opcoes(dados_ficticios):
    tabela = dados_ficticios.tabela("nbr5410/capacidade_conducao")
    with pytest.raises(ChaveInexistente, match="Opções existentes: 1.5, 2.5, 4, 6"):
        tabela.obter("capacidade_A", "PVC_70C", "3", "B1-2")


def test_valor_a_validar_interrompe_o_calculo_indicando_onde_preencher(criar_dados):
    repositorio = criar_dados({"teste": arquivo("limites:\n  terminal_pct: A_VALIDAR\n")})
    with pytest.raises(ValorPendente, match=r"data/teste\.yaml: limites > terminal_pct"):
        repositorio.tabela("teste").obter("limites", "terminal_pct")


def test_grupo_com_algum_valor_pendente_nao_e_entregue(criar_dados):
    repositorio = criar_dados({"teste": arquivo("correntes: [6, 10, A_VALIDAR]\n")})
    with pytest.raises(ValorPendente, match=r"correntes > \[3\]"):
        repositorio.tabela("teste").obter("correntes")


def test_valor_nao_se_aplica_gera_erro_proprio(criar_dados):
    repositorio = criar_dados({"teste": arquivo("fatores:\n  '80': NAO_SE_APLICA\n")})
    with pytest.raises(ValorNaoAplicavel, match="NAO_SE_APLICA"):
        repositorio.tabela("teste").obter("fatores", 80)


def test_pendencias_listam_todos_os_campos_sem_valor(criar_dados):
    metadados = 'metadados:\n  titulo: Teste\n  status: A_VALIDAR\n  referencia: "A_VALIDAR - nº"\n'
    corpo = """\
    limites:
      terminal_pct: A_VALIDAR
      total_pct: 5
    tabela:
      colunas: [x, y]
      linhas:
        "1": [1, A_VALIDAR]
    """
    repositorio = criar_dados({"teste": arquivo(corpo, metadados)})
    # O campo "status" não conta como pendência; a "referencia" com dica conta.
    assert repositorio.tabela("teste").pendencias() == [
        "metadados > referencia",
        "limites > terminal_pct",
        "tabela > 1 > y",
    ]


def test_campo_vazio_conta_como_pendente_e_gera_aviso(criar_dados):
    repositorio = criar_dados({"teste": arquivo("limites:\n  terminal_pct:\n")})
    assert repositorio.tabela("teste").pendencias() == ["limites > terminal_pct"]
    assert any("campo vazio" in aviso for aviso in avisos_de(repositorio))


# ---------------------------------------------------------------------------
# Erros de estrutura e de digitação
# ---------------------------------------------------------------------------


def test_linha_de_tabela_com_quantidade_errada_de_valores_e_erro(criar_dados):
    corpo = """\
    tabela:
      colunas: [B1-2, B1-3]
      linhas:
        "1.5": [10]
    """
    repositorio = criar_dados({"teste": arquivo(corpo)})
    assert any(
        "a linha tem 1 valores, mas existem 2 colunas" in erro for erro in erros_de(repositorio)
    )
    with pytest.raises(ArquivoInvalido):
        repositorio.tabela("teste")


def test_chave_repetida_e_erro(criar_dados):
    corpo = """\
    secoes:
      "2.5": 1
      "2.5": 2
    """
    repositorio = criar_dados({"teste": arquivo(corpo)})
    assert any("aparece repetida" in erro for erro in erros_de(repositorio))


def test_mesma_chave_escrita_como_numero_e_como_texto_e_erro(criar_dados):
    corpo = """\
    secoes:
      2.5: 1
      "2.5": 2
    """
    repositorio = criar_dados({"teste": arquivo(corpo)})
    assert any("aparece duas vezes" in erro for erro in erros_de(repositorio))


def test_erro_de_digitacao_no_yaml_informa_a_linha(criar_dados):
    corpo = """\
    limites:
      terminal_pct: 4
     total_pct: 5
    """
    repositorio = criar_dados({"teste": arquivo(corpo)})
    erros = erros_de(repositorio)
    assert len(erros) == 1
    assert "linha" in erros[0] and "erro de digitação" in erros[0]


def test_falta_de_metadados_e_erro(criar_dados):
    repositorio = criar_dados({"teste": "limites:\n  total_pct: 5\n"})
    assert any("falta o bloco 'metadados'" in erro for erro in erros_de(repositorio))


def test_situacao_desconhecida_e_erro(criar_dados):
    metadados = "metadados:\n  titulo: Teste\n  status: CONFERIDO\n"
    repositorio = criar_dados({"teste": arquivo("x: 1\n", metadados)})
    assert any("situação 'CONFERIDO' desconhecida" in erro for erro in erros_de(repositorio))


def test_arquivo_validado_com_valor_pendente_e_erro(criar_dados):
    metadados = "metadados:\n  titulo: Teste\n  status: VALIDADO\n  validado_por: Fulano\n"
    repositorio = criar_dados({"teste": arquivo("x: A_VALIDAR\n", metadados)})
    assert any("marcado como VALIDADO" in erro for erro in erros_de(repositorio))


def test_arquivo_validado_sem_responsavel_gera_aviso(criar_dados):
    metadados = "metadados:\n  titulo: Teste\n  status: VALIDADO\n"
    repositorio = criar_dados({"teste": arquivo("x: 1\n", metadados)})
    assert erros_de(repositorio) == []
    assert any("sem o nome de quem validou" in aviso for aviso in avisos_de(repositorio))


def test_secao_obrigatoria_apagada_e_erro(criar_dados):
    repositorio = criar_dados({"nbr5410/queda_tensao": arquivo("outra_coisa: 1\n")})
    assert any("limites_pct" in erro and "obrigatória" in erro for erro in erros_de(repositorio))


def test_virgula_decimal_e_erro(criar_dados):
    # "0,87" seria lido como texto e o cálculo não poderia usá-lo como número.
    repositorio = criar_dados({"teste": arquivo("fator: 0,87\n")})
    assert any("Use ponto decimal: 0.87" in erro for erro in erros_de(repositorio))


def test_virgula_em_texto_descritivo_e_aceita(criar_dados):
    repositorio = criar_dados({"teste": arquivo("descricao: Cabo 0,6/1 kV\n")})
    assert erros_de(repositorio) == []


@pytest.mark.parametrize("escrita", ["A VALIDAR", "a_validar", "A-VALIDAR"])
def test_grafia_parecida_com_a_validar_e_erro(criar_dados, escrita):
    # Escrito de outro jeito, o valor não seria reconhecido como pendente.
    repositorio = criar_dados({"teste": arquivo(f"fator: {escrita}\n")})
    assert any("parece A_VALIDAR" in erro for erro in erros_de(repositorio))


def test_chave_lida_como_sim_ou_nao_e_erro(criar_dados):
    # No YAML, "yes" sem aspas vira verdadeiro; como chave isso confunde o sistema.
    repositorio = criar_dados({"teste": arquivo("opcoes:\n  yes: 1\n")})
    assert any("entre aspas" in erro for erro in erros_de(repositorio))


# ---------------------------------------------------------------------------
# Faixas ("3", "9-11", "20+")
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("chave", "minimo", "maximo"),
    [("3", 3, 3), ("9-11", 9, 11), ("20+", 20, math.inf), (4, 4, 4), ("1.5-2.5", 1.5, 2.5)],
)
def test_interpretar_faixa(chave, minimo, maximo):
    faixa = interpretar_faixa(chave)
    assert (faixa.minimo, faixa.maximo) == (minimo, maximo)


@pytest.mark.parametrize("chave", ["abc", "11-9", "3 a 5", ""])
def test_faixa_mal_escrita_e_erro(chave):
    with pytest.raises(ArquivoInvalido):
        interpretar_faixa(chave)


@pytest.mark.parametrize(
    ("valor", "esperado"), [(1, "1"), (2, "2"), (4, "3-5"), (6, "6+"), (100, "6+")]
)
def test_procurar_faixa(valor, esperado):
    assert procurar_faixa(["1", "2", "3-5", "6+"], valor) == esperado


def test_procurar_faixa_sem_correspondencia():
    with pytest.raises(ChaveInexistente, match="Nenhuma das faixas"):
        procurar_faixa(["1", "2"], 3)


def test_faixas_sobrepostas_sao_erro():
    with pytest.raises(ArquivoInvalido, match="se sobrepõem"):
        procurar_faixa(["1-3", "3-5"], 3)
