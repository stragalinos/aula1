"""Comandos de terminal do eletroprojeto.

Uso:
    python -m eletroprojeto verificar-dados [--pasta CAMINHO] [--detalhes]
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

from eletroprojeto.nucleo.tabelas import STATUS_VALIDOS, ErroDados, RepositorioDados


def _verificar_dados(pasta: Path | None, detalhes: bool) -> int:
    repositorio = RepositorioDados(pasta)
    try:
        resultados = repositorio.verificar()
    except ErroDados as erro:
        print(f"ERRO: {erro}")
        return 1
    if not resultados:
        print(f"Nenhum arquivo .yaml encontrado em {repositorio.pasta}")
        return 1

    print(f"Verificação dos dados em: {repositorio.pasta}\n")
    largura = max(len(resultado.nome) for resultado in resultados) + len(".yaml")
    print(f"{'ARQUIVO':<{largura}}  {'SITUAÇÃO':<11}  PENDENTES")
    for resultado in resultados:
        situacao = "ERRO" if resultado.erros else resultado.status
        print(f"{resultado.nome + '.yaml':<{largura}}  {situacao:<11}  {len(resultado.pendencias)}")

    print("\nSituações:")
    for status, significado in STATUS_VALIDOS.items():
        print(f"  {status:<11} {significado}")

    erros = [erro for resultado in resultados for erro in resultado.erros]
    avisos = [aviso for resultado in resultados for aviso in resultado.avisos]
    if erros:
        print("\nERROS (precisam ser corrigidos antes de calcular):")
        for erro in erros:
            print(f"  - {erro}")
    if avisos:
        print("\nAVISOS:")
        for aviso in avisos:
            print(f"  - {aviso}")
    if detalhes:
        print("\nVALORES PENDENTES:")
        for resultado in resultados:
            if resultado.pendencias:
                print(f"  {resultado.nome}.yaml")
                for pendencia in resultado.pendencias:
                    print(f"    - {pendencia}")

    usados = [resultado for resultado in resultados if resultado.status != "MODELO"]
    validados = sum(1 for resultado in usados if resultado.status == "VALIDADO" and resultado.ok)
    total_pendentes = sum(len(resultado.pendencias) for resultado in usados)
    print(
        f"\nResumo: {validados} de {len(usados)} arquivos validados; "
        f"{total_pendentes} valores a preencher."
    )
    if total_pendentes and not detalhes:
        print("Use --detalhes para ver cada valor pendente.")
    print("Lembrete: o cálculo só exige os valores que usar e avisa quando faltar algum.")
    return 1 if erros else 0


def main(argv: list[str] | None = None) -> int:
    # Evita que o terminal do Windows trave em algum caractere especial.
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(
        prog="eletroprojeto",
        description="Ferramenta de apoio a projetos elétricos residenciais (NBR 5410).",
    )
    comandos = parser.add_subparsers(dest="comando", required=True, metavar="comando")
    verificar = comandos.add_parser(
        "verificar-dados",
        help="confere os arquivos da pasta data/ e lista o que falta preencher",
    )
    verificar.add_argument(
        "--pasta", type=Path, default=None, help="pasta de dados (padrão: data/)"
    )
    verificar.add_argument(
        "--detalhes", action="store_true", help="mostra cada valor que falta preencher"
    )

    argumentos = parser.parse_args(argv)
    if argumentos.comando == "verificar-dados":
        return _verificar_dados(argumentos.pasta, argumentos.detalhes)
    return 2
