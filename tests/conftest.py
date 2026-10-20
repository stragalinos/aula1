"""Configurações comuns dos testes."""

import textwrap
from pathlib import Path

import pytest

from eletroprojeto.nucleo.tabelas import RepositorioDados

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_DADOS_REAIS = RAIZ_PROJETO / "data"
PASTA_FICTICIA = Path(__file__).parent / "fixtures" / "tabelas_ficticias"


@pytest.fixture
def pasta_ficticia() -> Path:
    """Pasta com tabelas de números INVENTADOS, só para testar a lógica do sistema."""
    return PASTA_FICTICIA


@pytest.fixture
def dados_reais() -> RepositorioDados:
    """Os arquivos da pasta data/ do projeto (os que você preenche)."""
    return RepositorioDados(PASTA_DADOS_REAIS)


@pytest.fixture
def dados_ficticios() -> RepositorioDados:
    return RepositorioDados(PASTA_FICTICIA)


@pytest.fixture
def criar_dados(tmp_path):
    """Cria uma pasta de dados temporária com os arquivos indicados.

    Uso: ``criar_dados({"pasta/nome": "conteúdo yaml"})``.
    """

    def _criar(arquivos: dict[str, str]) -> RepositorioDados:
        for nome, conteudo in arquivos.items():
            caminho = tmp_path / f"{nome}.yaml"
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_text(textwrap.dedent(conteudo), encoding="utf-8")
        return RepositorioDados(tmp_path)

    return _criar
