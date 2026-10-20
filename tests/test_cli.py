"""Testes do comando de terminal ``python -m eletroprojeto verificar-dados``."""

from eletroprojeto.cli import main

METADADOS = "metadados:\n  titulo: Teste\n  status: A_VALIDAR\n"


def test_verificar_dados_lista_arquivos_e_resumo(pasta_ficticia, capsys):
    codigo = main(["verificar-dados", "--pasta", str(pasta_ficticia)])
    saida = capsys.readouterr().out
    assert codigo == 0
    assert "nbr5410/capacidade_conducao.yaml" in saida
    assert "EXEMPLO" in saida
    assert "Resumo: 0 de 1 arquivos validados; 0 valores a preencher." in saida


def test_verificar_dados_com_detalhes_mostra_cada_pendencia(criar_dados, capsys):
    repositorio = criar_dados(
        {"nbr5410/teste": METADADOS + "limites:\n  terminal_pct: A_VALIDAR\n"}
    )
    codigo = main(["verificar-dados", "--pasta", str(repositorio.pasta), "--detalhes"])
    saida = capsys.readouterr().out
    assert codigo == 0
    assert "VALORES PENDENTES" in saida
    assert "limites > terminal_pct" in saida


def test_verificar_dados_retorna_1_quando_ha_erro(criar_dados, capsys):
    repositorio = criar_dados({"teste": "sem_metadados: 1\n"})
    codigo = main(["verificar-dados", "--pasta", str(repositorio.pasta)])
    saida = capsys.readouterr().out
    assert codigo == 1
    assert "ERROS" in saida
    assert "falta o bloco 'metadados'" in saida


def test_verificar_dados_com_pasta_inexistente(tmp_path, capsys):
    codigo = main(["verificar-dados", "--pasta", str(tmp_path / "nao_existe")])
    assert codigo == 1
    assert "Pasta de dados não encontrada" in capsys.readouterr().out


def test_verificar_dados_reais_sem_erros(capsys):
    # Usa a pasta data/ do projeto: deve continuar sem erros de estrutura.
    assert main(["verificar-dados"]) == 0
