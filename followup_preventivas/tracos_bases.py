"""Leitura e normalização das exportações do TracOS (requisição, fluxo e pedido de compra).

Usado por reconhecimento.py e atualizar_followup.py.
"""
import fnmatch
import io
import os
import re
import unicodedata

import numpy as np
import pandas as pd

PADROES = {
    "requisicao": "requisi*compra*.csv",
    "fluxo": "fluxo*compras*.csv",
    "pedido": "pedido*compra*.csv",
}

RE_ITEM = re.compile(r"^#?(\d+)\s+(\d+)\s*-\s*(.*)$", re.S)
RE_REQ = re.compile(r"#?\s*(\d+)(?:\s*/\s*(\d+))?")
RE_ID = re.compile(r"#?\s*(\d+)")
RE_OS = re.compile(r"^#(\d+)\s+(\d+)\s*-\s*(?:(\d+)\s*-\s*)?(.*)$", re.S)
RE_ATIVO = re.compile(r"^(\S+)\s*-\s*(.*)$", re.S)
RE_QTD = re.compile(r"^\s*([\d.,]+)\s*(.*)$")


# ---------------------------------------------------------------- arquivos
def _norm(s):
    return unicodedata.normalize("NFC", s).lower()


def localizar(pasta, padrao):
    """Arquivo mais recente (data de modificação) cujo nome casa com o padrão.

    A comparação ignora maiúsculas/minúsculas e a forma Unicode do nome.
    """
    candidatos = [
        os.path.join(pasta, n)
        for n in os.listdir(pasta)
        if fnmatch.fnmatchcase(_norm(n), _norm(padrao))
    ]
    if not candidatos:
        raise FileNotFoundError(f"Nenhum arquivo '{padrao}' em {os.path.abspath(pasta)}")
    return max(candidatos, key=os.path.getmtime), sorted(candidatos)


def ler_csv_tracos(caminho):
    """Lê o CSV do TracOS: UTF-16 com BOM duplicado, separado por TAB, '-' = vazio."""
    raw = open(caminho, "rb").read()
    try:
        txt = raw.decode("utf-16")
    except UnicodeDecodeError:
        txt = raw.decode("utf-8-sig")
    txt = txt.lstrip("﻿")
    df = pd.read_csv(io.StringIO(txt), sep="\t", dtype=str, keep_default_na=False)
    df.columns = [c.strip().lstrip("﻿") for c in df.columns]
    df = df.apply(lambda s: s.str.replace("\xa0", " ", regex=False).str.strip())
    return df.replace({"-": np.nan, "": np.nan})


# ---------------------------------------------------------------- parsers
def _num_br(txt):
    """'1.586,94' -> 1586.94 ; '100' -> 100.0"""
    if txt is None or (isinstance(txt, float) and np.isnan(txt)):
        return np.nan
    t = str(txt).replace("R$", "").replace(" ", "").strip()
    if not t:
        return np.nan
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return np.nan


def moeda(s):
    return s.map(_num_br)


def quantidade(s):
    """'6 PC' -> (6.0, 'PC')"""
    def um(v):
        if pd.isna(v):
            return (np.nan, np.nan)
        m = RE_QTD.match(str(v))
        if not m:
            return (np.nan, str(v))
        return (_num_br(m.group(1)), m.group(2).strip() or np.nan)
    pares = s.map(um)
    return pares.map(lambda p: p[0]), pares.map(lambda p: p[1])


def data(s):
    """'dd/mm/aaaa' ou 'dd/mm/aaaa, hh:mm' -> datetime"""
    return pd.to_datetime(s.str.replace(",", "", regex=False), dayfirst=True,
                          format="mixed", errors="coerce")


def item(s):
    """'#000000000000326627 326627 - TAMPA MET LCC 9659' -> ('326627', 'TAMPA MET LCC 9659')"""
    def um(v):
        if pd.isna(v):
            return (np.nan, np.nan)
        m = RE_ITEM.match(str(v))
        if not m:
            return (np.nan, str(v))
        return (str(int(m.group(1))), m.group(3).strip())
    pares = s.map(um)
    return pares.map(lambda p: p[0]), pares.map(lambda p: p[1])


def req(s):
    """'#5/11' -> (5, 11) ; '#96' -> (96, NaN)"""
    def um(v):
        if pd.isna(v):
            return (np.nan, np.nan)
        m = RE_REQ.search(str(v))
        if not m:
            return (np.nan, np.nan)
        return (int(m.group(1)), int(m.group(2)) if m.group(2) else np.nan)
    pares = s.map(um)
    return (pares.map(lambda p: p[0]).astype("Int64"),
            pares.map(lambda p: p[1]).astype("Int64"))


def ident(s):
    """'#14' -> 14"""
    def um(v):
        if pd.isna(v):
            return np.nan
        m = RE_ID.search(str(v))
        return int(m.group(1)) if m else np.nan
    return s.map(um).astype("Int64")


def ordem_servico(s):
    """'#589 4004640057 - 65079 - MSI_ME_SUG PREV ...' -> os_tracos, os_sap, plano, descricao, eh_preventiva"""
    def um(v):
        if pd.isna(v):
            return (np.nan, np.nan, np.nan, np.nan)
        m = RE_OS.match(str(v))
        if not m:
            return (np.nan, np.nan, np.nan, str(v))
        return (int(m.group(1)), m.group(2), m.group(3) or np.nan, m.group(4).strip())
    q = s.map(um)
    out = pd.DataFrame({
        "os_tracos": q.map(lambda p: p[0]).astype("Int64"),
        "os_sap": q.map(lambda p: p[1]),
        "plano": q.map(lambda p: p[2]),
        "descricao_os": q.map(lambda p: p[3]),
    }, index=s.index)
    out["eh_preventiva"] = out["descricao_os"].fillna("").str.upper().str.contains("PREV")
    return out


def ativo(s):
    """'SUG71020004 - SUGADORA DE MAMINHA' -> ('SUG71020004', 'SUGADORA DE MAMINHA')"""
    def um(v):
        if pd.isna(v):
            return (np.nan, np.nan)
        m = RE_ATIVO.match(str(v))
        if not m:
            return (np.nan, str(v))
        return (m.group(1), m.group(2).strip())
    pares = s.map(um)
    return pares.map(lambda p: p[0]), pares.map(lambda p: p[1])


# ---------------------------------------------------------------- bases normalizadas
def normalizar_requisicao(df):
    out = pd.DataFrame(index=df.index)
    out["linha_origem"] = df.index + 2  # linha no CSV (1 = cabeçalho)
    out["requisicao"], _ = req(df["ID"])
    out["status_req"] = df["Status"]
    out["codigo"], out["descricao"] = item(df["Itens"])
    out["qtd"], out["unidade"] = quantidade(df["Quantidade"])
    out = out.join(ordem_servico(df["Ordem de Serviço"]))
    out["ativo_tag"], out["ativo_nome"] = ativo(df["Ativos Relacionados"])
    out["centro_custo"] = df["Centro de Custo"]
    out["criado_em"] = data(df["Criado em"])
    out["atualizado_em"] = data(df["Atualizado em"])
    out["criado_por"] = df["Criado por"]
    out["grupo_compradores"] = df["Grupo de Compradores"]
    out["req_sap"] = df["Nº Requisição de Compra SAP"]
    out["nivel_liberacao"] = df["Nível de Liberação Atual"]
    out["oc_sap"] = df["Nº Ordem de Compra SAP"]
    return out


def normalizar_fluxo(df):
    out = pd.DataFrame(index=df.index)
    out["linha_origem"] = df.index + 2
    out["id_fluxo"] = df["Código Identificador"]
    out["codigo"], out["descricao"] = item(df["Itens"])
    out["status_fluxo"] = df["Status"]
    out["qtd"], out["unidade"] = quantidade(df["Quantidade"])
    out["qtd_pendente"], _ = quantidade(df["Quant. Pendente"])
    out["data_necessidade"] = data(df["Data de Necessidade"])
    out["data_limite"] = data(df["Data Limite"])
    out["requisicao"], out["req_item"] = req(df["Requisição de Compra"])
    out["pedido"] = ident(df["Pedido de Compra"])
    out["entrada"] = df["Entrada"]
    out["preco_estimado"] = moeda(df["Preço Unitário (estimado)"])
    out["preco_negociado"] = moeda(df["Preço Unitário (negociado)"])
    out["preco_entrada"] = moeda(df["Preço Unitário (entrada)"])
    out["fornecedor"] = df["Fornecedor"]
    out["local_estoque"] = df["Local de Estoque"]
    out = out.join(ordem_servico(df["Ordem de Serviço"]))
    out["centro_custo"] = df["Centro de Custo"]
    return out


def normalizar_pedido(df):
    out = pd.DataFrame(index=df.index)
    out["linha_origem"] = df.index + 2
    out["pedido"] = ident(df["ID"])
    out["status_pedido"] = df["Status"]
    out["codigo"], out["descricao"] = item(df["Itens"])
    out["custo_total_pedido"] = moeda(df["Custo Total"])  # valor do PEDIDO, repetido em cada item
    out["fornecedor"] = df["Fornecedor"]
    out["ativo_tag"], out["ativo_nome"] = ativo(df["Ativos Relacionados"])
    out["requisicao"], _ = req(df["Requisição de Compra"])
    out["entrada"] = df["Entrada"]
    out["entrada_em"] = data(df["Entrada Registrada em"])
    out["criado_em"] = data(df["Criado em"])
    out["atualizado_em"] = data(df["Atualizado em"])
    out["nota_fiscal"] = df["Número da Nota Fiscal"]
    out["pedido_sap"] = df["Código Externo"]
    return out


def carregar_bases(pasta="bases"):
    """Localiza, lê e normaliza as 3 bases. Retorna dict com brutos, normalizados e arquivos."""
    res = {}
    for nome, padrao in PADROES.items():
        caminho, todos = localizar(pasta, padrao)
        bruto = ler_csv_tracos(caminho)
        norm = {"requisicao": normalizar_requisicao,
                "fluxo": normalizar_fluxo,
                "pedido": normalizar_pedido}[nome](bruto)
        res[nome] = {"arquivo": caminho, "candidatos": todos, "bruto": bruto, "norm": norm}
    return res
