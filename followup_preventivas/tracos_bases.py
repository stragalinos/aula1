"""Leitura e normalização das exportações do TracOS (requisição, fluxo e pedido de compra).

Usado por reconhecimento.py e atualizar_followup.py.
"""
import fnmatch
import hashlib
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
    "iwbk": "*iwbk*.xls*",
    "me2n": "*me2n*.xls*",
}
OPCIONAIS = ("iwbk", "me2n")  # bases do SAP: o follow-up funciona sem elas
# colunas que identificam cada exportação: o arquivo é achado mesmo quando foi salvo com outro nome
ASSINATURAS = {
    "requisicao": ["Nº Requisição de Compra SAP", "Nível de Liberação Atual"],
    "fluxo": ["Quant. Pendente", "Código Identificador"],
    "pedido": ["Código Externo", "Custo Total"],
    "iwbk": ["Ordem", "Material", "Nº reserva", "Disponibilidade"],
    "me2n": ["Documento de compras", "Fornecedor/centro fornecedor", "Qtd.do pedido"],
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


def _cabecalho(caminho):
    """Colunas do arquivo (CSV do TracOS ou planilha do SAP), lendo só o começo dele."""
    try:
        if caminho.lower().endswith(".csv"):
            with open(caminho, "rb") as fh:
                raw = fh.read(8192)
            enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
            linhas = raw.decode(enc, errors="ignore").lstrip("\ufeff").splitlines()
            return [c.strip().lstrip("\ufeff") for c in linhas[0].split("\t")] if linhas else []
        return [str(c).strip() for c in pd.read_excel(caminho, nrows=0).columns]
    except Exception:
        return []


def candidatos(pasta, nome):
    """Arquivos da pasta que são a exportação 'nome': pelo nome do arquivo ou, se o nome for outro,
    pelas colunas do cabeçalho. A comparação do nome ignora maiúsculas/minúsculas e a forma Unicode."""
    exts = (".xlsx", ".xls", ".xlsm") if nome in OPCIONAIS else (".csv",)
    out = []
    for n in sorted(os.listdir(pasta)):
        c = os.path.join(pasta, n)
        if n.startswith("~$") or not os.path.isfile(c):
            continue
        if fnmatch.fnmatchcase(_norm(n), _norm(PADROES[nome])):
            out.append(c)
        elif n.lower().endswith(exts) and all(x in _cabecalho(c) for x in ASSINATURAS[nome]):
            out.append(c)
    return out


def md5(caminho):
    h = hashlib.md5()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def escolher(cands, anteriores=None):
    """Escolhe o arquivo de uma base entre os que estão na pasta.

    anteriores = arquivos que estavam na pasta na última atualização: {"md5": {...}} (ou {"nomes": {...}}
    nas planilhas antigas). Vale o arquivo NOVO, que não estava lá; havendo vários novos, o modificado
    por último. Sem arquivo novo, o modificado por último. A data de modificação sozinha engana: arquivo
    copiado ou descompactado pode ficar com data mais nova que a de uma exportação recente.
    Devolve (arquivo, motivo, arquivos substituídos, md5 de cada candidato)."""
    hs = {c: md5(c) for c in cands}
    ant = anteriores or {}

    def conhecido(c):
        if ant.get("md5"):
            return hs[c] in ant["md5"]
        return os.path.basename(c) in ant.get("nomes", set())

    novos = [c for c in cands if not conhecido(c)]
    if ant and novos and len(novos) < len(cands):
        esc = max(novos, key=os.path.getmtime)
        return esc, "arquivo novo desde a última atualização", [c for c in cands if conhecido(c)], hs
    esc = max(cands, key=os.path.getmtime)
    return esc, "único arquivo" if len(cands) == 1 else "modificado por último", [], hs


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
    t = s.str.replace(",", "", regex=False).str.strip()
    com_hora = pd.to_datetime(t, format="%d/%m/%Y %H:%M", errors="coerce")
    sem_hora = pd.to_datetime(t, format="%d/%m/%Y", errors="coerce")
    return com_hora.fillna(sem_hora)


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
    """'#589 4004640057 - 65079 - MSI_ME_SUG PREV ...' -> os_tracos, os_sap, plano, descricao_os,
    prev_na_descricao, eh_preventiva"""
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
    out["prev_na_descricao"] = out["descricao_os"].fillna("").str.upper().str.contains("PREV")
    out["eh_preventiva"] = eh_preventiva(out["descricao_os"], out["plano"])
    return out


def eh_preventiva(descricao_os, plano=None):
    """Preventiva = 'PREV' na descrição, OS gerada por plano, ou descrição 'MSI_' (manutenção sistemática;
    no TracOS, toda OS MSI_ tem plano ou PREV)."""
    d = descricao_os.fillna("").str.upper().str.strip()
    r = d.str.contains("PREV") | d.str.startswith("MSI")
    if plano is not None:
        r = r | plano.notna()
    return r


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


# ---------------------------------------------------------------- SAP IWBK (opcional)
PADRAO_IWBK = PADROES["iwbk"]
COLUNAS_IWBK = ["Ordem", "Item lis.téc.", "Requisição de compra", "Data da necessidade", "Material",
                "Txt.breve ordem", "UM básica", "Qtd.necessária", "Qtd.retirada", "Item ReqC",
                "Texto breve material", "Qtd.entrada", "Pedido", "Documento de compras", "Data de remessa",
                "Categoria do item", "Disponibilidade", "Nº reserva"]


def _id_sap(v, tirar_zeros=False):
    """Código vindo do Excel do SAP (texto ou número) -> texto; vazio -> NaN."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    if isinstance(v, (int, np.integer)) or (isinstance(v, float) and float(v).is_integer()):
        t = str(int(v))
    else:
        t = str(v).strip()
    if tirar_zeros:
        t = t.lstrip("0")
    return t if t and t != "-" else np.nan


def _num_sap(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    if isinstance(v, (int, float, np.integer, np.floating)):
        return float(v)
    return _num_br(v)


def _data_sap(v):
    if v is None or (isinstance(v, float) and np.isnan(v)) or (isinstance(v, str) and not v.strip()):
        return pd.NaT
    if isinstance(v, (pd.Timestamp, np.datetime64)) or hasattr(v, "year"):
        return pd.Timestamp(v)
    t = str(v).strip()
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return pd.Timestamp(pd.to_datetime(t, format=fmt))
        except ValueError:
            continue
    return pd.NaT


def ler_iwbk(caminho):
    df = pd.read_excel(caminho, dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    falta = [c for c in COLUNAS_IWBK if c not in df.columns]
    if falta:
        raise ValueError(f"A IWBK não tem as colunas {falta}. Exporte com o layout completo.")
    return df


def normalizar_iwbk(df):
    """Uma linha por componente de ordem. Linhas sem 'Ordem' (totais por unidade no fim do relatório)
    ficam de fora e são contadas em 'linhas_ignoradas'."""
    out = pd.DataFrame(index=df.index)
    out["linha_origem"] = df.index + 2
    out["os_sap"] = df["Ordem"].map(_id_sap)
    out["item_lista"] = df["Item lis.téc."].map(_id_sap)
    out["codigo"] = df["Material"].map(lambda v: _id_sap(v, tirar_zeros=True))
    out["descricao"] = df["Texto breve material"].map(lambda v: np.nan if pd.isna(v) else str(v).strip())
    out["descricao_os"] = df["Txt.breve ordem"].map(lambda v: np.nan if pd.isna(v) else str(v).strip())
    out["unidade"] = df["UM básica"]
    out["qtd"] = df["Qtd.necessária"].map(_num_sap)
    out["qtd_retirada"] = df["Qtd.retirada"].map(_num_sap)
    out["qtd_entrada"] = df["Qtd.entrada"].map(_num_sap)
    out["rc_sap"] = df["Requisição de compra"].map(lambda v: _id_sap(v, tirar_zeros=True))
    out["rc_item"] = df["Item ReqC"].map(_id_sap)
    out["pedido_sap"] = df["Documento de compras"].map(_id_sap)
    out["status_pedido_sap"] = df["Pedido"].map(lambda v: np.nan if pd.isna(v) or not str(v).strip() else str(v).strip())
    out["data_necessidade"] = pd.to_datetime(df["Data da necessidade"].map(_data_sap))
    out["data_remessa"] = pd.to_datetime(df["Data de remessa"].map(_data_sap))
    out["categoria"] = df["Categoria do item"]
    out["disponibilidade"] = df["Disponibilidade"].map(lambda v: np.nan if pd.isna(v) else str(v).strip())
    out["reserva"] = df["Nº reserva"].map(_id_sap)
    out["prev_na_descricao"] = out["descricao_os"].fillna("").str.upper().str.contains("PREV")
    out["eh_preventiva"] = eh_preventiva(out["descricao_os"])
    validas = out["os_sap"].notna() & out["codigo"].notna()
    # colunas opcionais do layout: item eliminado da ordem (ex.: 'Eliminado') e status da ordem (ENTE/ENCE =
    # encerrada, MREL/MAEL = marcada para eliminação). Esses componentes não precisam mais de material.
    fora = pd.Series(False, index=df.index)
    for c in df.columns:
        nc = unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode().lower()
        if "elimin" in nc or "exclu" in nc:
            fora |= df[c].map(lambda v: not pd.isna(v) and str(v).strip().upper() not in
                              ("", "0", "-", "N", "NAO", "NÃO", "FALSE", "FALSO"))
        elif "status" in nc:
            fora |= df[c].fillna("").astype(str).str.upper().str.contains(r"\b(?:ENTE|ENCE|MREL|MAEL|ELIM)\b")
    norm = out[validas & ~fora].copy()
    norm.attrs["linhas_ignoradas"] = int((~validas).sum())
    norm.attrs["eliminadas"] = int((validas & fora).sum())
    return norm


# ---------------------------------------------------------------- SAP ME2N (opcional): pedidos com fornecedor
COLUNAS_ME2N = ["Documento de compras", "Item", "Material", "Fornecedor/centro fornecedor", "Data do documento",
                "Qtd.do pedido", "Preço líquido", "Moeda"]


def ler_me2n(caminho):
    df = pd.read_excel(caminho, dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    falta = [c for c in COLUNAS_ME2N if c not in df.columns]
    if falta:
        raise ValueError(f"A ME2N não tem as colunas {falta}.")
    return df


def normalizar_me2n(df):
    """Uma linha por item de pedido do SAP. 'Fornecedor/centro fornecedor' vem como '5935   NOME'."""
    out = pd.DataFrame(index=df.index)
    out["linha_origem"] = df.index + 2
    out["pedido_sap"] = df["Documento de compras"].map(_id_sap)
    out["item_pedido"] = df["Item"].map(_id_sap)
    out["codigo"] = df["Material"].map(lambda v: _id_sap(v, tirar_zeros=True))
    out["os_sap"] = df["Ordem"].map(_id_sap) if "Ordem" in df else np.nan
    forn = df["Fornecedor/centro fornecedor"].map(lambda v: "" if pd.isna(v) else " ".join(str(v).split()))
    partes = forn.str.extract(r"^(\d+)\s+(.*)$")
    out["fornecedor_cod"] = partes[0]
    out["fornecedor"] = partes[1].fillna(forn).replace("", np.nan)
    out["data_pedido"] = pd.to_datetime(df["Data do documento"].map(_data_sap))
    out["qtd_pedido"] = df["Qtd.do pedido"].map(_num_sap)
    col_afor = next((c for c in df.columns if c.lower().startswith("a ser fornecida")), None)
    out["a_fornecer"] = df[col_afor].map(_num_sap) if col_afor else np.nan
    out["moeda"] = df["Moeda"].map(lambda v: np.nan if pd.isna(v) else str(v).strip())
    out["preco"] = df["Preço líquido"].map(_num_sap)
    validas = out["pedido_sap"].notna()
    return out[validas].copy()


def carregar_bases(pasta="bases", anteriores=None):
    """Localiza, lê e normaliza as 3 bases do TracOS e, se existirem, a IWBK e a ME2N do SAP.
    anteriores = {base: arquivos que estavam na pasta na última atualização} (ver escolher)."""
    anteriores = anteriores or {}
    res = {}
    for nome in PADROES:
        cands = candidatos(pasta, nome)
        if not cands:
            if nome in OPCIONAIS:
                res[nome] = None
                continue
            raise FileNotFoundError(f"Nenhum arquivo '{PADROES[nome]}' em {os.path.abspath(pasta)}")
        caminho, motivo, subst, hs = escolher(cands, anteriores.get(nome))
        if nome == "iwbk":
            bruto = ler_iwbk(caminho)
            norm = normalizar_iwbk(bruto)
        elif nome == "me2n":
            bruto = ler_me2n(caminho)
            norm = normalizar_me2n(bruto)
        else:
            bruto = ler_csv_tracos(caminho)
            norm = {"requisicao": normalizar_requisicao,
                    "fluxo": normalizar_fluxo,
                    "pedido": normalizar_pedido}[nome](bruto)
        res[nome] = {"arquivo": caminho, "candidatos": cands, "motivo": motivo, "substituidos": subst,
                     "md5": hs, "bruto": bruto, "norm": norm}
    return res
