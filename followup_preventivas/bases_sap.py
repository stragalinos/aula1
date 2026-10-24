"""Leitura e normalização das exportações do SAP: IWBK (componentes das ordens) e ME2N (pedidos).

Usado por atualizar_followup.py.
"""
import fnmatch
import hashlib
import os
import unicodedata

import numpy as np
import pandas as pd

PADROES = {
    "iwbk": "*iwbk*.xls*",
    "me2n": "*me2n*.xls*",
}
OBRIGATORIAS = ("iwbk",)  # sem a ME2N o follow-up funciona, só fica sem o fornecedor dos pedidos
# colunas que identificam cada exportação: o arquivo é achado mesmo quando foi salvo com outro nome
ASSINATURAS = {
    "iwbk": ["Ordem", "Material", "Nº reserva", "Disponibilidade"],
    "me2n": ["Documento de compras", "Fornecedor/centro fornecedor", "Qtd.do pedido"],
}
COLUNAS_IWBK = ["Ordem", "Item lis.téc.", "Requisição de compra", "Data da necessidade", "Material",
                "Txt.breve ordem", "UM básica", "Qtd.necessária", "Qtd.retirada", "Item ReqC",
                "Texto breve material", "Qtd.entrada", "Pedido", "Documento de compras", "Data de remessa",
                "Categoria do item", "Disponibilidade", "Nº reserva"]
COLUNAS_ME2N = ["Documento de compras", "Item", "Material", "Fornecedor/centro fornecedor", "Data do documento",
                "Qtd.do pedido", "Preço líquido", "Moeda"]


# ---------------------------------------------------------------- arquivos
def _norm(s):
    return unicodedata.normalize("NFC", s).lower()


def _sem_acento(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()


def _cabecalho(caminho):
    """Colunas da planilha, lendo só a 1ª linha."""
    try:
        return [str(c).strip() for c in pd.read_excel(caminho, nrows=0).columns]
    except Exception:
        return []


def candidatos(pasta, nome):
    """Arquivos da pasta que são a exportação 'nome': pelo nome do arquivo ou, se o nome for outro,
    pelas colunas do cabeçalho. A comparação do nome ignora maiúsculas/minúsculas e a forma Unicode."""
    out = []
    for n in sorted(os.listdir(pasta)):
        c = os.path.join(pasta, n)
        if n.startswith("~$") or not os.path.isfile(c):
            continue
        if fnmatch.fnmatchcase(_norm(n), _norm(PADROES[nome])):
            out.append(c)
        elif n.lower().endswith((".xlsx", ".xls", ".xlsm")) and all(x in _cabecalho(c) for x in ASSINATURAS[nome]):
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


# ---------------------------------------------------------------- valores do Excel do SAP
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


def _texto(v):
    return np.nan if pd.isna(v) or not str(v).strip() else " ".join(str(v).split())


def _coluna(df, *nomes):
    """1ª coluna do layout com um destes nomes (sem diferenciar acentos/maiúsculas), ou None."""
    alvo = {_sem_acento(n) for n in nomes}
    return next((c for c in df.columns if _sem_acento(c) in alvo), None)


def eh_preventiva(descricao_os):
    """Preventiva = 'PREV' na descrição da OS ou descrição iniciada por 'MSI' (manutenção sistemática)."""
    d = descricao_os.fillna("").str.upper().str.strip()
    return d.str.contains("PREV") | d.str.startswith("MSI")


# ---------------------------------------------------------------- IWBK
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
    out["linha_origem"] = df.index + 2  # linha no Excel (1 = cabeçalho)
    out["os_sap"] = df["Ordem"].map(_id_sap)
    out["item_lista"] = df["Item lis.téc."].map(_id_sap)
    out["codigo"] = df["Material"].map(lambda v: _id_sap(v, tirar_zeros=True))
    out["descricao"] = df["Texto breve material"].map(_texto)
    out["descricao_os"] = df["Txt.breve ordem"].map(_texto)
    out["unidade"] = df["UM básica"]
    out["qtd"] = df["Qtd.necessária"].map(_num_sap)
    out["qtd_retirada"] = df["Qtd.retirada"].map(_num_sap)
    out["qtd_entrada"] = df["Qtd.entrada"].map(_num_sap)
    out["rc_sap"] = df["Requisição de compra"].map(lambda v: _id_sap(v, tirar_zeros=True))
    out["rc_item"] = df["Item ReqC"].map(_id_sap)
    out["pedido_sap"] = df["Documento de compras"].map(_id_sap)
    out["status_pedido_sap"] = df["Pedido"].map(_texto)
    out["data_necessidade"] = pd.to_datetime(df["Data da necessidade"].map(_data_sap))
    out["data_remessa"] = pd.to_datetime(df["Data de remessa"].map(_data_sap))
    out["categoria"] = df["Categoria do item"]
    out["disponibilidade"] = df["Disponibilidade"].map(_texto)
    out["reserva"] = df["Nº reserva"].map(_id_sap)
    # colunas opcionais do layout: equipamento / local de instalação da OS
    col_eq = _coluna(df, "Denominação do equipamento", "Equipamento", "Denominação do local de instalação",
                     "Local de instalação")
    out["ativo"] = df[col_eq].map(_texto) if col_eq else np.nan
    out["eh_preventiva"] = eh_preventiva(out["descricao_os"])
    validas = out["os_sap"].notna() & out["codigo"].notna()
    # colunas opcionais do layout: item eliminado da ordem (ex.: 'Eliminado') e status da ordem (ENTE/ENCE =
    # encerrada, MREL/MAEL = marcada para eliminação). Esses componentes não precisam mais de material.
    fora = pd.Series(False, index=df.index)
    for c in df.columns:
        nc = _sem_acento(c)
        if "elimin" in nc or "exclu" in nc:
            fora |= df[c].map(lambda v: not pd.isna(v) and str(v).strip().upper() not in
                              ("", "0", "-", "N", "NAO", "NÃO", "FALSE", "FALSO"))
        elif "status" in nc:
            fora |= df[c].fillna("").astype(str).str.upper().str.contains(r"\b(?:ENTE|ENCE|MREL|MAEL|ELIM)\b")
    norm = out[validas & ~fora].copy()
    norm.attrs["linhas_ignoradas"] = int((~validas).sum())
    norm.attrs["eliminadas"] = int((validas & fora).sum())
    return norm


# ---------------------------------------------------------------- ME2N (opcional): pedidos com fornecedor
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
    col = _coluna(df, "Texto breve")
    out["descricao"] = df[col].map(_texto) if col else np.nan
    col = _coluna(df, "UM pedido")
    out["unidade"] = df[col].map(_texto) if col else np.nan
    out["os_sap"] = df["Ordem"].map(_id_sap) if "Ordem" in df else np.nan
    forn = df["Fornecedor/centro fornecedor"].map(lambda v: "" if pd.isna(v) else " ".join(str(v).split()))
    partes = forn.str.extract(r"^(\d+)\s+(.*)$")
    out["fornecedor_cod"] = partes[0]
    out["fornecedor"] = partes[1].fillna(forn).replace("", np.nan)
    out["data_pedido"] = pd.to_datetime(df["Data do documento"].map(_data_sap))
    out["qtd_pedido"] = df["Qtd.do pedido"].map(_num_sap)
    col = next((c for c in df.columns if c.lower().startswith("a ser fornecida")), None)
    out["a_fornecer"] = df[col].map(_num_sap) if col else np.nan
    out["moeda"] = df["Moeda"].map(_texto)
    out["preco"] = df["Preço líquido"].map(_num_sap)
    col = _coluna(df, "Grupo de compradores")
    out["grupo_compradores"] = df[col].map(_texto) if col else np.nan
    # opcionais no layout: a RC que originou o pedido e a data de remessa do pedido
    col = _coluna(df, "Requisição de compra", "Req.compra")
    out["rc_sap"] = df[col].map(lambda v: _id_sap(v, tirar_zeros=True)) if col else np.nan
    col = _coluna(df, "Data de remessa", "Data remessa")
    out["data_remessa"] = pd.to_datetime(df[col].map(_data_sap)) if col else pd.NaT
    return out[out["pedido_sap"].notna()].copy()


# ---------------------------------------------------------------- carga
def carregar_bases(pasta="bases", anteriores=None):
    """Localiza, lê e normaliza a IWBK e, se existir, a ME2N.
    anteriores = {base: arquivos que estavam na pasta na última atualização} (ver escolher)."""
    anteriores = anteriores or {}
    res = {}
    for nome in PADROES:
        cands = candidatos(pasta, nome)
        if not cands:
            if nome in OBRIGATORIAS:
                raise FileNotFoundError(f"Nenhum arquivo da {nome.upper()} ('{PADROES[nome]}' ou com as colunas "
                                        f"{', '.join(ASSINATURAS[nome])}) em {os.path.abspath(pasta)}")
            res[nome] = None
            continue
        caminho, motivo, subst, hs = escolher(cands, anteriores.get(nome))
        if nome == "iwbk":
            bruto = ler_iwbk(caminho)
            norm = normalizar_iwbk(bruto)
        else:
            bruto = ler_me2n(caminho)
            norm = normalizar_me2n(bruto)
        res[nome] = {"arquivo": caminho, "candidatos": cands, "motivo": motivo, "substituidos": subst,
                     "md5": hs, "bruto": bruto, "norm": norm}
    return res
