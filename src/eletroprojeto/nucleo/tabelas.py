"""Leitura e conferência das tabelas de dados da pasta ``data/``.

Regra do projeto: nenhum valor normativo fica escrito no código. Os valores
(NBR 5410, catálogos, concessionárias, critérios de projeto) ficam em arquivos
YAML que o responsável técnico preenche e valida. Este módulo:

* lê os arquivos e converte os blocos no formato "tabela" (``colunas`` + ``linhas``);
* confere se estão bem formados e lista o que ainda falta preencher;
* entrega valores ao núcleo de cálculo e para com uma mensagem clara quando
  um valor necessário ainda está como ``A_VALIDAR``.
"""

from __future__ import annotations

import math
import os
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PENDENTE = "A_VALIDAR"
NAO_SE_APLICA = "NAO_SE_APLICA"
SEM_LIMITE = "SEM_LIMITE"

STATUS_VALIDOS: dict[str, str] = {
    "A_VALIDAR": "ainda não conferido com a fonte",
    "VALIDADO": "conferido pelo responsável técnico",
    "EXEMPLO": "valores de exemplo; confira antes de usar em obra",
    "PROVISORIO": "decisão provisória, aguardando confirmação",
    "MODELO": "modelo para copiar; não entra nos cálculos",
}

# Seções obrigatórias de cada arquivo. Servem para avisar quando uma parte do
# arquivo foi apagada ou renomeada por engano.
ESQUEMA_MINIMO: dict[str, tuple[str, ...]] = {
    "nbr5410/previsao_cargas": ("iluminacao", "tug_quantidade", "tug_potencia"),
    "nbr5410/regras_circuitos": (
        "tue_circuito_independente_acima_de_A",
        "tipos_com_tomadas_em_circuito_exclusivo",
    ),
    "nbr5410/metodos_instalacao": ("formas_instalacao",),
    "nbr5410/capacidade_conducao": ("capacidade_A",),
    "nbr5410/fator_temperatura": ("temperatura_referencia_C", "fatores"),
    "nbr5410/fator_agrupamento": ("arranjos", "fatores"),
    "nbr5410/secoes_minimas": ("condutor_fase_cobre_mm2",),
    "nbr5410/condutor_protecao": ("faixas",),
    "nbr5410/queda_tensao": ("limites_pct",),
    "nbr5410/taxa_ocupacao": ("taxa_maxima_pct",),
    "nbr5410/exigencias_dr": ("sensibilidade_maxima_mA", "por_tipo_comodo"),
    "nbr5410/dps": ("por_esquema",),
    "catalogos/condutores": ("material", "tipos"),
    "catalogos/eletrodutos": ("tipos",),
    "catalogos/disjuntores": ("termomagneticos", "dr"),
    "catalogos/equipamentos_tipicos": ("equipamentos",),
    "criterios_projeto": (
        "circuitos",
        "fator_potencia_padrao",
        "dimensionamento",
        "agrupamento",
        "comprimentos",
        "protecao",
        "materiais",
    ),
}
ESQUEMA_CONCESSIONARIA: tuple[str, ...] = ("identificacao", "fornecimento", "demanda", "categorias")

SEPARADOR = " > "


class ErroDados(Exception):
    """Problema nos arquivos de ``data/``; a mensagem é escrita para o usuário."""


class ArquivoInvalido(ErroDados):
    """Arquivo com erro de digitação ou de estrutura."""


class ValorPendente(ErroDados):
    """O cálculo precisou de um valor que ainda está como A_VALIDAR."""


class ValorNaoAplicavel(ErroDados):
    """O cálculo pediu um valor marcado como NAO_SE_APLICA."""


class ChaveInexistente(ErroDados):
    """O cálculo pediu uma linha, coluna ou campo que não existe no arquivo."""


def pasta_dados_padrao() -> Path:
    """Pasta ``data/`` do projeto (pode ser trocada pela variável ELETROPROJETO_DADOS)."""
    variavel = os.environ.get("ELETROPROJETO_DADOS")
    if variavel:
        return Path(variavel)
    return Path(__file__).resolve().parents[3] / "data"


def eh_pendente(valor: Any) -> bool:
    """Indica se o valor ainda falta preencher (vazio ou começando com A_VALIDAR)."""
    if valor is None:
        return True
    return isinstance(valor, str) and valor.strip().startswith(PENDENTE)


def normalizar_chave(chave: Any) -> str:
    """Converte chaves para texto, para que ``2.5`` e ``"2.5"`` sejam a mesma chave."""
    if isinstance(chave, float):
        return str(int(chave)) if chave.is_integer() else f"{chave:g}"
    return str(chave)


# ---------------------------------------------------------------------------
# Faixas ("3", "9-11", "20+")
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Faixa:
    """Faixa numérica indicada por uma chave como ``"3"``, ``"9-11"`` ou ``"20+"``."""

    minimo: float
    maximo: float

    def contem(self, valor: float) -> bool:
        return self.minimo <= valor <= self.maximo


_RE_FAIXA = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:-\s*(\d+(?:\.\d+)?)|(\+))?\s*$")


def interpretar_faixa(chave: Any) -> Faixa:
    """Lê uma chave de faixa: ``"3"`` (só 3), ``"9-11"`` (9 a 11) ou ``"20+"`` (20 ou mais)."""
    texto = normalizar_chave(chave)
    combinacao = _RE_FAIXA.match(texto)
    if not combinacao:
        raise ArquivoInvalido(
            f"'{texto}' não é uma faixa válida. Use um número (\"3\"), "
            f'um intervalo ("9-11") ou "20+" para "20 ou mais".'
        )
    minimo = float(combinacao.group(1))
    if combinacao.group(3):
        return Faixa(minimo, math.inf)
    maximo = float(combinacao.group(2)) if combinacao.group(2) else minimo
    if maximo < minimo:
        raise ArquivoInvalido(f"Faixa '{texto}' está invertida: o início é maior que o fim.")
    return Faixa(minimo, maximo)


def procurar_faixa(chaves: Iterable[Any], valor: float) -> str:
    """Devolve a chave cuja faixa contém ``valor`` (ex.: 10 circuitos -> ``"9-11"``)."""
    lista = [normalizar_chave(chave) for chave in chaves]
    encontradas = [chave for chave in lista if interpretar_faixa(chave).contem(valor)]
    if not encontradas:
        raise ChaveInexistente(f"Nenhuma das faixas ({', '.join(lista)}) contém o valor {valor:g}.")
    if len(encontradas) > 1:
        raise ArquivoInvalido(
            f"As faixas {', '.join(encontradas)} se sobrepõem no valor {valor:g}; "
            "cada valor deve caber em uma faixa só."
        )
    return encontradas[0]


# ---------------------------------------------------------------------------
# Tabela já lida
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ocorrencia:
    """Erro ou aviso encontrado ao ler um arquivo de dados."""

    arquivo: str
    onde: str
    mensagem: str

    def __str__(self) -> str:
        local = f" ({self.onde})" if self.onde else ""
        return f"{self.arquivo}{local}: {self.mensagem}"


def _caminhos_pendentes(no: Any, prefixo: tuple[str, ...]) -> Iterator[tuple[str, ...]]:
    if isinstance(no, dict):
        for chave, valor in no.items():
            yield from _caminhos_pendentes(valor, (*prefixo, chave))
    elif isinstance(no, list):
        for posicao, valor in enumerate(no, start=1):
            yield from _caminhos_pendentes(valor, (*prefixo, f"[{posicao}]"))
    elif eh_pendente(no):
        yield prefixo


@dataclass
class Tabela:
    """Conteúdo de um arquivo de ``data/`` já conferido e pronto para consulta."""

    nome: str
    caminho: Path
    metadados: dict[str, Any]
    dados: dict[str, Any]
    avisos: list[Ocorrencia] = field(default_factory=list)

    @property
    def status(self) -> str:
        return str(self.metadados.get("status", ""))

    @property
    def validada(self) -> bool:
        return self.status == "VALIDADO"

    def chaves(self, *caminho: Any) -> list[str]:
        """Lista as chaves existentes num ponto do arquivo, na ordem em que aparecem."""
        no = self._navegar(caminho)
        if not isinstance(no, dict):
            raise ChaveInexistente(
                f"Em data/{self.nome}.yaml, '{SEPARADOR.join(map(normalizar_chave, caminho))}' "
                "é um valor, não um grupo de campos."
            )
        return list(no)

    def obter(self, *caminho: Any) -> Any:
        """Devolve o valor no caminho indicado, exigindo que esteja totalmente preenchido.

        Exemplo: ``obter("capacidade_A", "PVC_70C", "2.5", "B1-2")`` lê a linha 2,5 mm²,
        coluna B1 com 2 condutores carregados.
        """
        valor = self._navegar(caminho)
        inicio = tuple(normalizar_chave(parte) for parte in caminho)
        pendentes = [SEPARADOR.join(c) for c in _caminhos_pendentes(valor, inicio)]
        if pendentes:
            exemplos = "; ".join(pendentes[:3]) + (" ..." if len(pendentes) > 3 else "")
            raise ValorPendente(
                f"O cálculo precisa de um valor que ainda não foi preenchido em "
                f"data/{self.nome}.yaml: {exemplos}. Troque A_VALIDAR pelo valor da fonte "
                "e rode 'python -m eletroprojeto verificar-dados'."
            )
        if valor == NAO_SE_APLICA:
            raise ValorNaoAplicavel(
                f"Em data/{self.nome}.yaml, {SEPARADOR.join(inicio)} está marcado como "
                "NAO_SE_APLICA: a tabela não tem valor para essa situação."
            )
        return valor

    def pendencias(self) -> list[str]:
        """Lista todos os campos que ainda faltam preencher (inclusive nos metadados)."""
        metadados = {chave: valor for chave, valor in self.metadados.items() if chave != "status"}
        caminhos = list(_caminhos_pendentes(metadados, ("metadados",)))
        caminhos += list(_caminhos_pendentes(self.dados, ()))
        return [SEPARADOR.join(caminho) for caminho in caminhos]

    def _navegar(self, caminho: tuple[Any, ...]) -> Any:
        no: Any = self.dados
        percorrido: list[str] = []
        for parte in caminho:
            chave = normalizar_chave(parte)
            if not isinstance(no, dict) or chave not in no:
                opcoes = ", ".join(no) if isinstance(no, dict) else "nenhuma"
                raise ChaveInexistente(
                    f"Em data/{self.nome}.yaml não existe '{chave}' dentro de "
                    f"'{SEPARADOR.join(percorrido) or 'início do arquivo'}'. "
                    f"Opções existentes: {opcoes}."
                )
            no = no[chave]
            percorrido.append(chave)
        return no


# ---------------------------------------------------------------------------
# Leitura e conferência dos arquivos
# ---------------------------------------------------------------------------


class _CarregadorYaml(yaml.SafeLoader):
    """Leitor YAML que recusa chaves repetidas (o padrão aceitaria em silêncio)."""


def _mapa_sem_repeticao(carregador: yaml.SafeLoader, no: yaml.MappingNode, deep: bool = False):
    carregador.flatten_mapping(no)
    mapa: dict[Any, Any] = {}
    for no_chave, no_valor in no.value:
        chave = carregador.construct_object(no_chave, deep=deep)
        if chave in mapa:
            raise yaml.constructor.ConstructorError(
                None, None, f"a chave {chave!r} aparece repetida", no_chave.start_mark
            )
        mapa[chave] = carregador.construct_object(no_valor, deep=deep)
    return mapa


_CarregadorYaml.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapa_sem_repeticao)

_RE_VIRGULA_DECIMAL = re.compile(r"^\s*-?\d+,\d+\s*$")


class _Leitura:
    """Acumula erros e avisos enquanto um arquivo é lido."""

    def __init__(self, nome: str) -> None:
        self.arquivo = f"{nome}.yaml"
        self.erros: list[Ocorrencia] = []
        self.avisos: list[Ocorrencia] = []

    def erro(self, onde: tuple[str, ...], mensagem: str) -> None:
        self.erros.append(Ocorrencia(self.arquivo, SEPARADOR.join(onde), mensagem))

    def aviso(self, onde: tuple[str, ...], mensagem: str) -> None:
        self.avisos.append(Ocorrencia(self.arquivo, SEPARADOR.join(onde), mensagem))


def _conferir_texto(texto: str, onde: tuple[str, ...], leitura: _Leitura) -> None:
    if _RE_VIRGULA_DECIMAL.match(texto):
        corrigido = texto.strip().replace(",", ".")
        leitura.erro(
            onde,
            f"o valor '{texto}' foi lido como texto. Use ponto decimal: {corrigido}",
        )
    compacto = re.sub(r"[\s_\-]", "", texto.upper())
    if compacto.startswith("AVALIDAR") and not eh_pendente(texto):
        leitura.erro(
            onde,
            f"'{texto}' parece A_VALIDAR escrito de outro jeito; "
            "escreva exatamente A_VALIDAR ou o valor definitivo.",
        )


def _chave_valida(chave: Any, onde: tuple[str, ...], leitura: _Leitura) -> str | None:
    if isinstance(chave, bool) or chave is None:
        leitura.erro(
            onde,
            f"uma chave foi lida como '{chave}' (palavras como yes, no, on, off e chaves "
            "vazias têm significado especial no YAML). Coloque a chave entre aspas.",
        )
        return None
    return normalizar_chave(chave)


def _converter_bloco_tabela(
    no: dict[str, Any], onde: tuple[str, ...], leitura: _Leitura
) -> dict[str, Any]:
    colunas, linhas = no["colunas"], no["linhas"]
    if not isinstance(colunas, list) or not colunas:
        leitura.erro(onde, "'colunas' deve ser uma lista entre colchetes, ex.: [B1-2, B1-3].")
        return {}
    nomes_colunas = [normalizar_chave(coluna) for coluna in colunas]
    if len(set(nomes_colunas)) != len(nomes_colunas):
        leitura.erro(onde, f"há colunas com o mesmo nome: {', '.join(nomes_colunas)}.")
        return {}
    if not isinstance(linhas, dict) or not linhas:
        leitura.erro(onde, "'linhas' deve conter uma linha por item, no formato chave: [valores].")
        return {}

    resultado: dict[str, Any] = {}
    for chave_linha, valores in linhas.items():
        nome_linha = _chave_valida(chave_linha, onde, leitura)
        if nome_linha is None:
            continue
        local = (*onde, nome_linha)
        if nome_linha in resultado:
            leitura.erro(local, 'esta linha aparece duas vezes (ex.: 2.5 e "2.5").')
            continue
        if not isinstance(valores, list):
            leitura.erro(local, "a linha deve ser uma lista entre colchetes, um valor por coluna.")
            continue
        if len(valores) != len(nomes_colunas):
            leitura.erro(
                local,
                f"a linha tem {len(valores)} valores, mas existem {len(nomes_colunas)} "
                f"colunas ({', '.join(nomes_colunas)}).",
            )
            continue
        resultado[nome_linha] = {
            coluna: _converter(valor, (*local, coluna), leitura)
            for coluna, valor in zip(nomes_colunas, valores, strict=True)
        }
    return resultado


def _converter(no: Any, onde: tuple[str, ...], leitura: _Leitura) -> Any:
    if isinstance(no, dict):
        if set(no) == {"colunas", "linhas"}:
            return _converter_bloco_tabela(no, onde, leitura)
        resultado: dict[str, Any] = {}
        for chave, valor in no.items():
            nome = _chave_valida(chave, onde, leitura)
            if nome is None:
                continue
            if nome in resultado:
                leitura.erro((*onde, nome), 'esta chave aparece duas vezes (ex.: 2.5 e "2.5").')
                continue
            resultado[nome] = _converter(valor, (*onde, nome), leitura)
        return resultado
    if isinstance(no, list):
        return [
            _converter(valor, (*onde, f"[{posicao}]"), leitura)
            for posicao, valor in enumerate(no, start=1)
        ]
    if no is None:
        leitura.aviso(onde, "campo vazio: preencha o valor ou escreva A_VALIDAR.")
    elif isinstance(no, str):
        _conferir_texto(no, onde, leitura)
    return no


def _secoes_obrigatorias(nome: str) -> tuple[str, ...]:
    if nome in ESQUEMA_MINIMO:
        return ESQUEMA_MINIMO[nome]
    if nome.startswith("concessionarias/"):
        return ESQUEMA_CONCESSIONARIA
    return ()


def _ler_arquivo(caminho: Path, nome: str) -> tuple[Tabela | None, _Leitura]:
    leitura = _Leitura(nome)
    try:
        texto = caminho.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        leitura.erro((), "o arquivo não está em UTF-8. No editor, salve com a codificação UTF-8.")
        return None, leitura
    try:
        bruto = yaml.load(texto, Loader=_CarregadorYaml)
    except yaml.YAMLError as erro:
        marca = getattr(erro, "problem_mark", None)
        onde = (f"linha {marca.line + 1}",) if marca else ()
        problema = getattr(erro, "problem", None) or str(erro)
        leitura.erro(
            onde,
            f"erro de digitação: {problema}. Confira o recuo (espaços), os dois-pontos e as aspas.",
        )
        return None, leitura
    if not isinstance(bruto, dict):
        leitura.erro((), "o arquivo deve ser formado por campos no formato 'nome: valor'.")
        return None, leitura

    conteudo = _converter(bruto, (), leitura)
    metadados = conteudo.pop("metadados", None)
    if not isinstance(metadados, dict):
        leitura.erro(("metadados",), "falta o bloco 'metadados' no início do arquivo.")
        metadados = {}
    if not metadados.get("titulo"):
        leitura.erro(("metadados", "titulo"), "falta o título do arquivo.")
    status = metadados.get("status")
    if status not in STATUS_VALIDOS:
        leitura.erro(
            ("metadados", "status"),
            f"situação '{status}' desconhecida. Use uma destas: {', '.join(STATUS_VALIDOS)}.",
        )
    for secao in _secoes_obrigatorias(nome):
        if secao not in conteudo:
            leitura.erro((secao,), "seção obrigatória não encontrada (foi apagada ou renomeada?).")

    tabela = Tabela(nome, caminho, metadados, conteudo, leitura.avisos)
    if tabela.validada:
        pendentes = tabela.pendencias()
        if pendentes:
            leitura.erro(
                ("metadados", "status"),
                f"o arquivo está marcado como VALIDADO, mas ainda tem {len(pendentes)} "
                "valor(es) por preencher.",
            )
        if not metadados.get("validado_por"):
            leitura.aviso(
                ("metadados", "validado_por"), "arquivo VALIDADO sem o nome de quem validou."
            )
    return tabela, leitura


@dataclass
class ResultadoVerificacao:
    """Resumo da conferência de um arquivo de dados."""

    nome: str
    status: str
    pendencias: list[str]
    erros: list[Ocorrencia]
    avisos: list[Ocorrencia]

    @property
    def ok(self) -> bool:
        return not self.erros


class RepositorioDados:
    """Acesso às tabelas da pasta ``data/``; cada arquivo é lido uma única vez."""

    def __init__(self, pasta: Path | str | None = None) -> None:
        self.pasta = Path(pasta) if pasta is not None else pasta_dados_padrao()
        self._tabelas: dict[str, Tabela] = {}

    def nomes(self) -> list[str]:
        """Nomes dos arquivos (sem ``.yaml``), ex.: ``"nbr5410/capacidade_conducao"``."""
        if not self.pasta.is_dir():
            raise ErroDados(f"Pasta de dados não encontrada: {self.pasta}")
        return sorted(
            caminho.relative_to(self.pasta).with_suffix("").as_posix()
            for caminho in self.pasta.rglob("*.yaml")
        )

    def tabela(self, nome: str) -> Tabela:
        """Devolve a tabela pronta para consulta; recusa arquivos com erro."""
        if nome not in self._tabelas:
            caminho = self.pasta / f"{nome}.yaml"
            if not caminho.is_file():
                raise ErroDados(f"Arquivo de dados não encontrado: {caminho}")
            tabela, leitura = _ler_arquivo(caminho, nome)
            if tabela is None or leitura.erros:
                lista = "\n".join(f"  - {erro}" for erro in leitura.erros)
                raise ArquivoInvalido(
                    f"Corrija o arquivo data/{nome}.yaml antes de calcular:\n{lista}"
                )
            self._tabelas[nome] = tabela
        return self._tabelas[nome]

    def verificar(self) -> list[ResultadoVerificacao]:
        """Confere todos os arquivos da pasta, sem parar no primeiro erro."""
        resultados = []
        for nome in self.nomes():
            tabela, leitura = _ler_arquivo(self.pasta / f"{nome}.yaml", nome)
            resultados.append(
                ResultadoVerificacao(
                    nome=nome,
                    status=tabela.status if tabela else "?",
                    pendencias=tabela.pendencias() if tabela else [],
                    erros=leitura.erros,
                    avisos=leitura.avisos,
                )
            )
        return resultados
