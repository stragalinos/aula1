"""Atualiza a planilha de follow-up de peças para manutenção (TracOS).

Uso:
    1. Jogue os downloads novos do TracOS na pasta ./bases
       (requisição de compra *.csv, fluxo de compras *.csv, pedido de compra *.csv)
    2. Rode:  python atualizar_followup.py        (ou dê dois cliques em atualizar_followup.bat)
    3. A planilha sai em ./saida/followup_preventivas_AAAA-MM-DD.xlsx

Tudo o que você digita nas células amarelas da versão anterior (observações, recebimento dos itens,
data de necessidade e liberação da OS, parâmetros) é reaproveitado automaticamente.
"""
import argparse
import datetime as dt
import glob
import math
import re
import os
import sys
import unicodedata
import urllib.parse
import warnings

import numpy as np
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.formula import ArrayFormula
from openpyxl.worksheet.table import Table, TableStyleInfo

import cruzamento as cz
import tracos_bases as tb

AQUI = os.path.dirname(os.path.abspath(__file__))
PREFIXO = "followup_preventivas_"
COL_OBS = "Observação / Follow-up"
COL_CHAVE = "Chave"
LIN_CAB = 4          # linha do cabeçalho nas abas de tabela (1 = voltar ao Painel, 2 = título, 3 = nota)
LIN_1 = LIN_CAB + 1  # primeira linha de dados

# colunas digitadas por você (amarelas), preservadas entre atualizações: aba -> (chave, colunas)
REC_MARCA = "Recebido?"
REC_QTD = "Qtd recebida"
REC_DATA = "Data do recebimento"
REC_LOCAL = "Local / kit de separação"
REC_OBS = "Observação do recebimento"
OS_DATA = "Data de necessidade (manual)"
OS_LIB = "Liberada para a equipe em"
FORN_EMAIL = "E-mail do fornecedor"
MANUAIS = {
    "Follow-up": ([COL_CHAVE], [COL_OBS]),
    "Recebimento": ([COL_CHAVE], [REC_MARCA, REC_QTD, REC_DATA, REC_LOCAL, REC_OBS]),
    "Por OS": (["OS TracOS"], [OS_DATA, OS_LIB, COL_OBS]),
    "Por Fornecedor": (["Fornecedor"], [FORN_EMAIL, COL_OBS]),
    "Divergências": (["Tipo", COL_CHAVE], [COL_OBS]),
}
TIPO_ORFA = "ANOTAÇÃO SEM ITEM ATUAL"
TIPO_ORFA_V1 = "OBSERVAÇÃO SEM ITEM ATUAL"  # nome usado na 1ª versão da planilha

# ------------------------------------------------------------------ estilo
FONTE = "Arial"
F_NORMAL = Font(name=FONTE, size=10)
F_NEGRITO = Font(name=FONTE, size=10, bold=True)
F_CAB = Font(name=FONTE, size=10, bold=True, color="FFFFFF")
F_CAB_ED = Font(name=FONTE, size=10, bold=True, color="1F3864")
F_TITULO = Font(name=FONTE, size=14, bold=True, color="1F3864")
F_SECAO = Font(name=FONTE, size=11, bold=True, color="1F3864")
F_NOTA = Font(name=FONTE, size=9, italic=True, color="595959")
F_ALERTA = Font(name=FONTE, size=10, bold=True, color="9C0006")
F_LINK = Font(name=FONTE, size=10, color="0563C1", underline="single")
F_LINK_B = Font(name=FONTE, size=10, bold=True, color="0563C1", underline="single")
F_BOTAO = Font(name=FONTE, size=10, bold=True, color="FFFFFF")
P_BOTAO = PatternFill("solid", fgColor="2F5597")
P_CAB = PatternFill("solid", fgColor="1F3864")
P_CAB_ED = PatternFill("solid", fgColor="FFD966")  # cabeçalho de coluna editável
P_EDITAVEL = PatternFill("solid", fgColor="FFF2CC")
P_TOTAL = PatternFill("solid", fgColor="D9E1F2")
P_PREV = PatternFill("solid", fgColor="EAF1FB")
BORDA = Border(bottom=Side(style="thin", color="BFBFBF"))
AL_CAB = Alignment(horizontal="center", vertical="center", wrap_text=True)
AL_CENTRO = Alignment(horizontal="center", vertical="top")
AL_TOPO = Alignment(vertical="top")

FMT_DATA = "dd/mm/yyyy"
FMT_DATAHORA = "dd/mm/yyyy hh:mm"
FMT_RS = '"R$" #,##0.00'
FMT_DIAS = "0;[Red]-0"
FMT_ATRASO = '0;-0;"-"'

# palavra do status -> (preenchimento, cor da fonte)
CORES_STATUS = [
    ("VENCIDA", "FFC7CE", "9C0006"),
    ("PARADA", "F4B6B6", "7F0000"),
    ("SEM PEDIDO", "FFD8A8", "843C0C"),
    ("EM RISCO", "FFE699", "7F6000"),
    ("NO PRAZO", "C6EFCE", "006100"),
    ("ENTREGUE", "DDEBF7", "1F4E78"),
    ("SEM DATA", "E7E6E6", "404040"),
]
CORES_REC = [
    ("ATRASADO", "FFC7CE", "9C0006"),
    ("A CAMINHO", "FFE699", "7F6000"),
    ("PARCIAL", "FFD8A8", "843C0C"),
    ("NÃO RECEBIDO", "F4B6B6", "7F0000"),
    ("RECEBIDO", "C6EFCE", "006100"),
]
CORES_APTA = [
    ("FALTANDO", "FF0000", "FFFFFF"),
    ("LIBERADA", "DDEBF7", "1F4E78"),
    ("APTA", "C6EFCE", "006100"),
    ("AGUARDANDO", "FFC7CE", "9C0006"),
]

PARAMETROS = [
    # id, nome definido, rótulo, padrão, descrição
    ("data_ref", "DATA_REF", "Data de referência", "=TODAY()",
     "Base de todos os cálculos de dias. Deixe =HOJE() para usar a data do dia; digite uma data fixa "
     "só para simular (volta a =HOJE() na próxima atualização)."),
    ("x_nivel01", "X_NIVEL01", "X – dias máx. aguardando o gestor (nível 01)", 3,
     "Requisição no nível 01 há mais dias que isso fica 🔴 PARADA NA APROVAÇÃO."),
    ("x_nivel02", "X_NIVEL02", "X – dias máx. aguardando o almox corporativo (nível 02)", 5,
     "Requisição no nível 02 há mais dias que isso fica 🔴 PARADA NA APROVAÇÃO."),
    ("y_sem_pedido", "Y_SEM_PEDIDO", "Y – dias máx. em compra autorizada sem pedido", 2,
     "Item autorizado há mais dias que isso, ainda sem pedido, fica 🟠 SEM PEDIDO."),
    ("z_entrega", "Z_ENTREGA", "Z – antecedência mínima (dias) para a entrega", 5,
     "Pedido emitido e faltando Z dias ou menos para a necessidade fica 🟠 ENTREGA EM RISCO."),
    ("nome_gestor", "NOME_GESTOR", "Nome do gestor da unidade (aprovador nível 01)", "",
     "Aparece na coluna 'Quem cobrar'. Ex.: João Silva – ramal 1234"),
    ("nome_almox", "NOME_ALMOX", "Contato do almox corporativo (nível 02)", "",
     "Aparece na coluna 'Quem cobrar'."),
    ("nome_comprador", "NOME_COMPRADOR", "Nome do comprador", "",
     "Aparece na coluna 'Quem cobrar' dos itens autorizados sem pedido."),
    ("email_gestor", "EMAIL_GESTOR", "E-mail do gestor da unidade (nível 01)", "",
     "Usado no botão ✉ Cobrar das requisições paradas no nível 01 (Painel). Vários: separe com ';'."),
    ("email_almox", "EMAIL_ALMOX", "E-mail do almox corporativo (nível 02)", "",
     "Usado no botão ✉ Cobrar das requisições paradas no nível 02 (Painel)."),
]

DESCR_STATUS = {
    1: "Data de necessidade já passou e o material não está disponível.",
    2: "Requisição pendente há mais de X dias (X do nível atual).",
    3: "Compra autorizada há mais de Y dias e ainda sem pedido.",
    4: "Pedido emitido e faltam Z dias ou menos para a necessidade.",
    5: "Tem data de necessidade e está dentro dos limites.",
    6: "Material disponível: marcado como recebido na aba Recebimento ou com entrada no TracOS.",
    7: "Sem data de necessidade: o TracOS só informa a data quando o item entra no fluxo de compras. "
       "Digite a data da OS na aba Por OS.",
}

# ------------------------------------------------------------------ colunas das abas
# (cabeçalho, largura, chave interna). Chaves 'f_' = fórmula; 'm_' = digitada por você.
COLS_FU = [
    ("Prioridade", 8, "f_prio"), ("Status de risco", 28, "f_status"), ("Item disponível?", 10, "f_disp"),
    ("Recebimento (aba Recebimento)", 13, "f_rec"), ("Etapa nº", 7, "etapa"),
    ("Etapa do funil", 38, "etapa_txt"), ("Quem cobrar", 44, "f_quem"), (COL_OBS, 42, "m_obs"),
    ("Preventiva", 9, "prev"), ("OS TracOS", 9, "os_tracos"), ("OS SAP", 12, "os_sap"),
    ("Descrição da OS", 42, "descricao_os"), ("Ativo", 36, "ativo"),
    ("Código material", 10, "codigo"), ("Descrição do material", 36, "descricao"),
    ("Qtd", 7, "qtd"), ("Qtd pendente", 9, "qtd_pendente"), ("Un", 5, "unidade"),
    ("Data de necessidade", 12, "f_nec"), ("Origem da data de necessidade", 26, "f_origem"),
    ("Dias até a necessidade", 11, "f_dias_nec"), ("Dias de atraso", 9, "f_atraso"),
    ("Data de necessidade TracOS", 12, "data_nec_tracos"), ("Data manual da OS (aba Por OS)", 13, "f_nec_manual"),
    ("Início da etapa", 12, "inicio_etapa"), ("Base do início da etapa", 30, "base_inicio"),
    ("Dias na etapa atual", 10, "f_dias_etapa"),
    ("Requisição", 10, "requisicao_txt"), ("Req. SAP", 12, "req_sap"),
    ("Nível de liberação", 22, "nivel_liberacao"), ("Pedido", 8, "pedido"),
    ("Pedido SAP", 12, "pedido_sap"), ("Status do pedido", 15, "status_pedido"),
    ("Fornecedor", 36, "fornecedor"), ("Preço unitário (R$)", 13, "preco"),
    ("Origem do preço", 17, "origem_preco"), ("Valor do item (R$)", 14, "f_valor"),
    ("Entrada", 8, "entrada"), ("Data da entrada", 12, "entrada_em"), ("Nota fiscal", 11, "nota_fiscal"),
    ("Local de estoque", 20, "local_estoque"), ("Centro de custo", 28, "centro_custo"),
    ("Grupo de compradores", 30, "grupo_compradores"), ("Plano", 8, "plano"),
    ("Confiança do vínculo", 44, "confianca"), ("Linhas de origem", 24, "origens"),
    (COL_CHAVE, 24, "chave"),
]
COLS_REC = [
    ("Situação", 26, "f_sit"), (REC_MARCA, 11, "m_rec"), (REC_QTD, 9, "m_qtd"), (REC_DATA, 12, "m_data"),
    (REC_LOCAL, 22, "m_local"), (REC_OBS, 34, "m_obs"), ("Itens que faltam na OS", 10, "f_falta_os"),
    ("OS TracOS", 9, "os_tracos"), ("Preventiva", 9, "prev"), ("Descrição da OS", 40, "descricao_os"),
    ("Ativo", 34, "ativo"), ("Código material", 10, "codigo"), ("Descrição do material", 36, "descricao"),
    ("Qtd pedida", 8, "qtd"), ("Un", 5, "unidade"), ("Data de necessidade", 12, "f_nec"),
    ("Dias até a necessidade", 11, "f_dias"), ("Fornecedor", 34, "fornecedor"), ("Pedido", 8, "pedido"),
    ("Pedido SAP", 12, "pedido_sap"), ("Status do pedido (TracOS)", 15, "status_pedido"),
    ("Entrada no TracOS?", 10, "rec_tracos"), ("Entrada", 8, "entrada"),
    ("Data da entrada (TracOS)", 12, "entrada_em"), ("Nota fiscal", 11, "nota_fiscal"),
    (COL_CHAVE, 24, "chave"),
]
COLS_OS = [
    ("OS TracOS", 9, "os_tracos"), ("OS SAP", 12, "os_sap"), ("Descrição da OS", 40, "descricao_os"),
    ("Preventiva", 9, "prev"), ("Ativo", 34, "ativo"), ("APTA PARA PROGRAMAR?", 25, "f_apta"),
    ("Itens que faltam", 55, "f_lista"), ("Ir para os itens", 15, "f_ir"), (OS_DATA, 13, "m_data"),
    ("Data de necessidade (usada)", 12, "f_data"),
    ("Dias até a necessidade", 11, "f_dias"), ("Total de itens", 8, "f_total"),
    ("Itens disponíveis", 9, "f_disp"), ("Itens faltando", 9, "f_falt"),
    ("A caminho (com pedido)", 9, "f_caminho"), ("Em compra / aprovação", 10, "f_compra"),
    ("Itens em risco 🔴", 9, "f_risco"), ("Valor pendente (R$)", 14, "f_valor"),
    ("Data de necessidade TracOS", 12, "data_tracos"), ("Lista de itens", 30, "lista_ok"),
    ("Situação das peças (na geração)", 34, "situacao"), (OS_LIB, 13, "m_lib"),
    ("Plano", 8, "plano"), ("Centro de custo", 26, "centro_custo"), (COL_OBS, 40, "m_obs"),
    # auxiliares do Painel (ocultas)
    ("Grupo (painel)", 12, "f_grupo"), ("Janela (painel)", 10, "f_janela"), ("Nº apta (painel)", 8, "f_seq"),
]
COLS_FORN = [
    ("Fornecedor", 38, "fornecedor"), ("✉ Cobrar", 20, "f_mail"), (FORN_EMAIL, 30, "m_email"),
    ("Pedidos abertos", 9, "n_pedidos"),
    ("Pedidos (TracOS / SAP)", 48, "pedidos"), ("Itens em aberto no TracOS", 9, "itens_abertos"),
    ("Itens a receber (follow-up)", 10, "f_receber"), ("Itens com necessidade vencida", 11, "f_vencidos"),
    ("Atraso mais antigo (dias)", 10, "f_atraso"), ("Valor em aberto (R$)", 14, "valor_aberto"),
    ("Pedido mais antigo (emissão)", 13, "pedido_mais_antigo"), ("Dias desde a emissão", 10, "f_dias"),
    ("OS afetadas", 22, "os_afetadas"), ("Itens sem OS identificada", 10, "itens_sem_os"),
    (COL_OBS, 40, "m_obs"), ("Link do e-mail (auxiliar)", 10, "f_url"),
]
OCULTAS = {"f_grupo", "f_janela", "f_seq", "f_url"}
LISTA_INCOMPLETA = "⚠ conferir no TracOS (fluxo incompleto)"


# ------------------------------------------------------------------ utilidades
def val(x):
    """Converte valores pandas/numpy para tipos que o openpyxl grava."""
    if x is None:
        return None
    if isinstance(x, pd.Timestamp):
        return None if pd.isna(x) else x.to_pydatetime()
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if math.isnan(x) else float(x)
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    return x


def cel(ws, ref, valor=None, fonte=F_NORMAL, fmt=None, preench=None, alin=None):
    c = ws[ref] if isinstance(ref, str) else ws.cell(row=ref[0], column=ref[1])
    c.value = val(valor)
    c.font = fonte
    if fmt:
        c.number_format = fmt
    if preench:
        c.fill = preench
    if alin:
        c.alignment = alin
    return c


def cabecalho(ws, linha, colunas):
    """Cabeçalho de tabela; colunas digitadas (chave 'm_') ganham cabeçalho amarelo."""
    for j, (t, larg, k) in enumerate(colunas, start=1):
        ed = k.startswith("m_")
        c = cel(ws, (linha, j), t, F_CAB_ED if ed else F_CAB, preench=P_CAB_ED if ed else P_CAB, alin=AL_CAB)
        c.border = BORDA
        ws.column_dimensions[get_column_letter(j)].width = larg
    ws.row_dimensions[linha].height = 32


def titulo(ws, texto, sub=None):
    cel(ws, "A1", "=HYPERLINK(\"#'Painel'!A1\",\"⬅ Voltar ao Painel\")", F_LINK_B)
    cel(ws, "A2", texto, F_TITULO)
    if sub:
        cel(ws, "A3", sub, F_NOTA)


def local(aba, col, achar=None):
    """Destino de link interno. achar = expressão MATCH(...) que devolve a posição na tabela."""
    if achar is None:
        return f"\"#'{aba}'!{col}{LIN_1}\""
    return f"\"#'{aba}'!{col}\"&IFERROR({achar}+{LIN_CAB},{LIN_1})"


def link(loc, texto):
    """Fórmula HIPERLINK; texto pode ser outra fórmula (ex.: uma contagem)."""
    return f"=HYPERLINK({loc},{texto})"


def _ascii(t):
    return unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode()


def mailto_partes(assunto, corpos, limite=215):
    """'?subject=...&body=...' codificado, escolhendo o 1º corpo que cabe no limite do HIPERLINK
    (255 caracteres, contando 'mailto:' e o e-mail). Devolve (completo, só assunto)."""
    q = "?subject=" + urllib.parse.quote(_ascii(assunto), safe="")
    for c in corpos:
        completo = q + "&body=" + urllib.parse.quote(_ascii(c), safe="")
        if len(completo) <= limite:
            return completo, q
    return q, q


def sem_link(ws, rng, canto):
    """Texto de aviso que sai de fórmula com link (ex.: '(sem e-mail)') não deve parecer clicável."""
    ws.conditional_formatting.add(rng, FormulaRule(
        formula=[f'OR(LEFT({canto},1)="(",LEFT({canto},1)="✎",LEFT({canto},7)="Nenhuma")'],
        font=Font(name=FONTE, italic=True, color="808080", underline="none", bold=False)))


def formula_mailto(email_ref, completo, curto, texto, vazio):
    return (f'=IF({email_ref}="","{vazio}",HYPERLINK(IF(LEN("mailto:"&{email_ref}&"{completo}")<=255,'
            f'"mailto:"&{email_ref}&"{completo}","mailto:"&{email_ref}&"{curto}"),"{texto}"))')


def cf_palavras(ws, rng, col_ref, cores):
    """Formatação condicional pelas palavras do texto da célula col_ref (ex.: '$B4')."""
    for palavra, fundo, letra in cores:
        ws.conditional_formatting.add(rng, FormulaRule(
            formula=[f'ISNUMBER(SEARCH("{palavra}",{col_ref}))'], stopIfTrue=True,
            fill=PatternFill("solid", fgColor=fundo, bgColor=fundo),
            font=Font(name=FONTE, color=letra, bold=True)))


def paisagem(ws, caber_largura=True):
    ws.page_setup.orientation = "landscape"
    if not caber_largura:
        return
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def nome_definido(wb, nome, ref):
    dn = DefinedName(nome, attr_text=ref)
    try:
        wb.defined_names.add(dn)
    except AttributeError:  # openpyxl < 3.1
        wb.defined_names.append(dn)


def validar_data(ws, rng):
    dv = DataValidation(type="date", operator="greaterThan", formula1="36526", allow_blank=True,
                        errorTitle="Data", error="Digite uma data (dd/mm/aaaa).")
    dv.add(rng)
    ws.add_data_validation(dv)


def letras(colunas):
    return {k: get_column_letter(j) for j, (_, _, k) in enumerate(colunas, 1)}


def faixas(aba, colunas, n):
    """Intervalos absolutos de cada coluna da tabela (ex.: 'Follow-up'!$J$4:$J$264)."""
    ult = max(LIN_1 + n - 1, LIN_1)
    return {k: f"'{aba}'!${c}${LIN_1}:${c}${ult}" for k, c in letras(colunas).items()}


def _k(v):
    """Chave de leitura: 411.0 -> '411'."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


def _data(v):
    """Data digitada (datetime do Excel ou texto dd/mm/aaaa) -> Timestamp; senão None."""
    if v is None or v == "":
        return None
    if isinstance(v, (dt.datetime, dt.date)):
        return pd.Timestamp(v)
    try:
        return pd.Timestamp(dt.datetime.strptime(str(v).strip(), "%d/%m/%Y"))
    except ValueError:
        return None


def _vazio(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


# ------------------------------------------------------------------ versão anterior
def _tabela(ws, colunas):
    """Lê uma aba de tabela da versão anterior: acha o cabeçalho e devolve lista de dicts."""
    linhas = ws.iter_rows(values_only=True)
    cab = None
    for _ in range(10):
        try:
            row = next(linhas)
        except StopIteration:
            return []
        if row and all(c in row for c in colunas):
            cab = list(row)
            break
    if cab is None:
        return []
    out = []
    for row in linhas:
        if row is None:
            continue
        out.append({c: row[i] if i < len(row) else None for i, c in enumerate(cab) if c})
    return out


def ler_versao_anterior(pasta_saida):
    vazio = dict(arquivo=None, manuais={a: {} for a in MANUAIS}, historico={}, prm={})
    arqs = [a for a in glob.glob(os.path.join(pasta_saida, PREFIXO + "*.xlsx"))
            if not os.path.basename(a).startswith("~$")]
    if not arqs:
        return vazio
    ant = max(arqs, key=os.path.getmtime)
    try:
        wb = load_workbook(ant, read_only=True, data_only=True)
    except Exception as e:  # arquivo corrompido / aberto de forma exclusiva
        print(f"AVISO: não consegui ler a versão anterior ({ant}): {e}. Anotações não reaproveitadas.")
        return vazio
    man = {a: {} for a in MANUAIS}

    def guardar(aba, chave, col, v):
        if not _vazio(v) and chave not in (None, "None"):
            man[aba].setdefault(chave, {})[col] = v

    # anotações órfãs guardadas por versões anteriores (itens que tinham sumido das bases)
    if "_anotacoes" in wb.sheetnames:
        for d in _tabela(wb["_anotacoes"], ["Aba", "Chave", "Coluna", "Valor"]):
            if d.get("Aba") in man:
                guardar(d["Aba"], _k(d["Chave"]), d["Coluna"], d["Valor"])
    for aba, (ks, cols) in MANUAIS.items():
        if aba not in wb.sheetnames:
            continue
        for d in _tabela(wb[aba], ks):
            if aba == "Divergências" and d.get("Tipo") in (TIPO_ORFA, TIPO_ORFA_V1):
                if d.get("Tipo") == TIPO_ORFA_V1 and d.get("Base") in man:  # formato da 1ª versão
                    destino = d["Base"]
                    k = d.get(COL_CHAVE) if destino != "Divergências" else d.get("Detalhe")
                    guardar(destino, _k(k), COL_OBS, d.get(COL_OBS))
                continue
            chave = "|".join(_k(d.get(x)) for x in ks)
            for c in cols:
                guardar(aba, chave, c, d.get(c))
    hist = {}
    if "_historico" in wb.sheetnames:
        for d in _tabela(wb["_historico"], ["Chave", "Etapa", "Desde"]):
            if d.get("Chave") and d.get("Etapa") and d.get("Desde"):
                hist[str(d["Chave"])] = (int(d["Etapa"]), pd.Timestamp(d["Desde"]))
    prm = {}
    if "Parâmetros" in wb.sheetnames:
        ids = {p[0] for p in PARAMETROS}
        for row in wb["Parâmetros"].iter_rows(min_row=1, max_row=40, values_only=True):
            if row and len(row) >= 4 and row[3] in ids and row[3] != "data_ref":
                v = row[1]
                if row[3].startswith(("nome_", "email_")):
                    prm[row[3]] = "" if v is None else str(v)
                elif isinstance(v, (int, float)):
                    prm[row[3]] = v
    wb.close()
    return dict(arquivo=ant, manuais=man, historico=hist, prm=prm)


def manuais_para_cruzamento(man):
    datas, lib = {}, set()
    for k, d in man["Por OS"].items():
        try:
            os_ = int(k)
        except ValueError:
            continue
        dd = _data(d.get(OS_DATA))
        if dd is not None:
            datas[os_] = dd
        if not _vazio(d.get(OS_LIB)):
            lib.add(os_)
    rec = {k: d.get(REC_MARCA) for k, d in man["Recebimento"].items() if not _vazio(d.get(REC_MARCA))}
    return {"datas_os": datas, "liberadas": lib, "recebimento": rec}


# ------------------------------------------------------------------ abas
def aba_parametros(wb, prm, B, R, data_fixa, info_ant):
    ws = wb.create_sheet("Parâmetros")
    ws.sheet_properties.tabColor = "808080"
    titulo(ws, "Parâmetros e legenda",
           "Células amarelas são editáveis e são reaproveitadas na próxima atualização "
           "(exceto a data de referência, que volta para =HOJE()).")
    for j, (t, w) in enumerate([("Parâmetro", 52), ("Valor", 26), ("Descrição", 95), ("id", 12)], 1):
        cel(ws, (LIN_CAB, j), t, F_CAB, preench=P_CAB, alin=AL_CAB)
        ws.column_dimensions[get_column_letter(j)].width = w
    for k, (pid, nome, rotulo, padrao, desc) in enumerate(PARAMETROS):
        lin = LIN_1 + k
        valor = padrao
        if pid == "data_ref":
            valor = data_fixa if data_fixa is not None else "=TODAY()"
        elif pid in prm:
            valor = prm[pid]
        cel(ws, (lin, 1), rotulo, F_NEGRITO)
        cel(ws, (lin, 2), valor, F_NORMAL, preench=P_EDITAVEL, fmt=FMT_DATA if pid == "data_ref" else None,
            alin=Alignment(horizontal="left"))
        cel(ws, (lin, 3), desc, F_NOTA)
        cel(ws, (lin, 4), pid, F_NOTA)
        nome_definido(wb, nome, f"'Parâmetros'!$B${lin}")
    ws.column_dimensions["D"].hidden = True
    lin = LIN_1 + len(PARAMETROS) + 1

    def secao(t):
        nonlocal lin
        lin += 1
        cel(ws, (lin, 1), t, F_SECAO)
        lin += 1

    def linhas_texto(pares):
        nonlocal lin
        for a, b in pares:
            cel(ws, (lin, 1), a, F_NEGRITO)
            cel(ws, (lin, 2), b, F_NORMAL)
            lin += 1

    secao("Gestão dos materiais – o que você preenche")
    linhas_texto([
        ("Aba Recebimento → Recebido?", "SIM = o material chegou e está separado para a OS. PARCIAL = chegou só "
         "parte (não libera a OS). NÃO = não chegou, mesmo que o TracOS mostre entrada. Em branco = vale a "
         "entrada registrada no TracOS."),
        ("Aba Por OS → Data de necessidade (manual)", "Data em que a OS precisa das peças (ex.: data programada). "
         "Vale para todos os itens da OS e manda sobre a data do TracOS. Use quando a OS não tem data."),
        ("Aba Por OS → Liberada para a equipe em", "Data em que você passou a OS para os colaboradores. Se "
         "faltar item, a OS aparece em vermelho: ⚠ LIBERADA FALTANDO."),
        ("Links e botões", "Textos e números sublinhados levam direto aos itens. ✉ Cobrar abre o e-mail "
         "pronto: preencha os e-mails do gestor/almox aqui e o do fornecedor na aba Por Fornecedor. Em cada aba, "
         "'⬅ Voltar ao Painel' fica na célula A1."),
        ("APTA PARA PROGRAMAR", "Só quando TODOS os itens da OS estão disponíveis. Item disponível = marcado SIM "
         "no Recebimento ou com entrada no TracOS (sem marca PARCIAL/NÃO)."),
    ])

    secao("Regras fixas (no script)")
    linhas_texto([
        ("Preventiva", "OS com 'PREV' na descrição OU com nº de plano de manutenção."),
        ("Data de necessidade", "1º a data manual da OS (aba Por OS); 2º a do item no fluxo do TracOS; 3º a de "
         "outro item da mesma OS no fluxo. A base de requisição não traz data."),
        ("Preço do item", "Entrada > negociado > estimado (R$ 1,00 do TracOS é ignorado como 'sem preço') > "
         "preço do mesmo material em outra linha do fluxo ('ref.')."),
        ("Valor do item", "Quantidade × preço unitário. A requisição e o pedido não trazem preço por item: "
         "itens sem preço ficam sem valor."),
        ("Dias na etapa", "Etapas 1/2: 'Criado em' da requisição (no nível 02, a partir da 1ª vez que o script "
         "viu o item no nível 02). Etapa 3: 1ª vez que o script viu o item autorizado. "
         "Etapa 4: 'Criado em' do pedido. Etapa 5: data da entrada."),
        ("Chave das anotações", "Item: material | requisição | OS (+ sequencial quando o trio se repete). "
         "OS: nº da OS no TracOS. Se o item sumir das bases, a anotação vai para Divergências e volta "
         "quando ele reaparecer."),
    ])

    secao("Legenda – status de risco (em ordem de prioridade)")
    for p_, txt in cz.STATUS.items():
        fundo, letra = next((f, l) for w, f, l in CORES_STATUS if w in txt)
        cel(ws, (lin, 1), txt, Font(name=FONTE, bold=True, color=letra), preench=PatternFill("solid", fgColor=fundo))
        cel(ws, (lin, 2), f"Prioridade {p_}", F_NORMAL)
        cel(ws, (lin, 3), DESCR_STATUS[p_], F_NORMAL)
        lin += 1

    secao("Legenda – situação no Recebimento")
    descr_rec = {0: "Tem pedido, não chegou e a data de necessidade já passou.",
                 1: "Tem pedido e ainda não chegou.", 2: "Você marcou PARCIAL: não libera a OS.",
                 3: "Você marcou NÃO.", 4: "Você marcou SIM.",
                 5: "Entrada registrada no TracOS (sem marca sua)."}
    for k, txt in cz.SITUACAO_REC.items():
        fundo, letra = next((f, l) for w, f, l in CORES_REC if w in txt)
        cel(ws, (lin, 1), txt, Font(name=FONTE, bold=True, color=letra), preench=PatternFill("solid", fgColor=fundo))
        cel(ws, (lin, 2), descr_rec[k], F_NORMAL)
        lin += 1

    secao("Legenda – etapas do funil")
    quem = {1: "Gestor da unidade", 2: "Almox corporativo", 3: "Comprador", 4: "Fornecedor",
            5: "— (retirar no almoxarifado)"}
    for e, txt in cz.ETAPAS.items():
        cel(ws, (lin, 1), txt, F_NEGRITO)
        cel(ws, (lin, 2), f"Quem cobrar: {quem[e]}", F_NORMAL)
        lin += 1

    secao("Legenda – confiança do vínculo (ordem em que as regras são testadas)")
    expl = {
        "R1": "Fluxo ↔ pedido pelo material + requisição + nº do pedido.",
        "R2": "Material + nº da requisição (fluxo ↔ pedido, requisição ↔ fluxo ou requisição ↔ pedido).",
        "R3": "Material + nº do pedido.",
        "R4": "Material + OS (requisição ↔ fluxo). Vai também para Divergências.",
        "R5": "Item do pedido fora do fluxo: a requisição dele só tem uma OS, então a OS foi deduzida. "
              "Vai também para Divergências.",
        "SO_REQ": "Requisição pendente: ainda não tem fluxo nem pedido (é o esperado).",
        "SO_FLX": "Compra autorizada que ainda não virou pedido.",
        "FLX_SEM_PED": "Fluxo diz que há pedido, mas ele não veio na exportação de pedidos.",
    }
    linhas_texto([(txt, expl[k]) for k, txt in cz.CONFIANCA.items()])

    secao("Esta atualização")
    cel(ws, (lin, 1), "Gerado em", F_NEGRITO)
    cel(ws, (lin, 2), dt.datetime.now().replace(microsecond=0), F_NORMAL, fmt=FMT_DATAHORA,
        alin=Alignment(horizontal="left"))
    lin += 1
    cel(ws, (lin, 1), "Anotações reaproveitadas de", F_NEGRITO)
    cel(ws, (lin, 2), os.path.basename(info_ant["arquivo"]) if info_ant["arquivo"] else "(primeira versão)")
    lin += 1
    for nome in ("requisicao", "fluxo", "pedido"):
        arq = B[nome]["arquivo"]
        cel(ws, (lin, 1), f"Arquivo de {nome}", F_NEGRITO)
        cel(ws, (lin, 2), os.path.basename(arq))
        cel(ws, (lin, 3), f"{len(B[nome]['bruto'])} linhas – modificado em "
                          f"{dt.datetime.fromtimestamp(os.path.getmtime(arq)):%d/%m/%Y %H:%M}")
        lin += 1
    lin += 1
    cel(ws, (lin, 1), "Conciliação (linhas de entrada × saída)", F_SECAO)
    lin += 1
    for j, t in enumerate(["Base", "Linhas de entrada", "No Follow-up", "Divergências (não casadas)", "OK?"], 1):
        cel(ws, (lin, j), t, F_CAB, preench=P_CAB, alin=AL_CAB)
    ws.column_dimensions["E"].width = 10
    lin += 1
    for _, c in R["conciliacao"].iterrows():
        for j, v in enumerate([c["base"], c["entrada"], c["follow_up"], c["divergencias"],
                               "SIM" if c["ok"] else "NÃO"], 1):
            cel(ws, (lin, j), v)
        lin += 1
    for a in R["alertas"]:
        lin += 1
        cel(ws, (lin, 1), "⚠ " + a, F_ALERTA)


def escrever_tabela(ws, colunas, registros, valor_de, fmts, centro, negrito=(), links=()):
    """Escreve as linhas de uma tabela. valor_de(k, registro, linha) devolve o valor/fórmula da célula."""
    for j, (_, _, k) in enumerate(colunas, 1):
        if k in OCULTAS:
            ws.column_dimensions[get_column_letter(j)].hidden = True
    for i, reg in enumerate(registros):
        r = LIN_1 + i
        for j, (_, _, k) in enumerate(colunas, 1):
            fonte = F_LINK if k in links else (F_NEGRITO if k in negrito else F_NORMAL)
            cel(ws, (r, j), valor_de(k, reg, r), fonte, fmt=fmts.get(k),
                preench=P_EDITAVEL if k.startswith("m_") else None,
                alin=AL_CENTRO if k in centro else AL_TOPO)
    ult = max(LIN_1 + len(registros) - 1, LIN_1)
    ws.auto_filter.ref = f"A{LIN_CAB}:{get_column_letter(len(colunas))}{ult}"
    return ult


def aba_followup(wb, L, man, FU, REC, POS):
    ws = wb.create_sheet("Follow-up")
    ws.sheet_properties.tabColor = "548235"
    titulo(ws, "Follow-up de peças por OS",
           "Ordenado por prioridade de risco e data de necessidade no momento da geração. Status, dias e "
           "disponibilidade recalculam com a data de referência e com o que você marca nas abas Recebimento e "
           "Por OS. Coluna amarela = sua observação.")
    cabecalho(ws, LIN_CAB, COLS_FU)
    c = letras(COLS_FU)
    E, N, DN, DE, I, Q, PR, FO, PS, P, D, RC, NM, NT, OS, CH = (c[k] for k in (
        "etapa", "f_nec", "f_dias_nec", "f_dias_etapa", "inicio_etapa", "qtd", "preco", "fornecedor",
        "pedido_sap", "f_prio", "f_disp", "f_rec", "f_nec_manual", "data_nec_tracos", "os_tracos", "chave"))
    status_txt = ",".join(f'"{cz.STATUS[i]}"' for i in range(1, 8))
    f = {
        "f_prio": (f'=IF({D}{{r}}="SIM",6,IF(AND({N}{{r}}<>"",N({DN}{{r}})<0),1,'
                   f'IF(AND({E}{{r}}<=2,N({DE}{{r}})>IF({E}{{r}}=1,X_NIVEL01,X_NIVEL02)),2,'
                   f'IF(AND({E}{{r}}=3,N({DE}{{r}})>Y_SEM_PEDIDO),3,'
                   f'IF(AND({E}{{r}}=4,{N}{{r}}<>"",N({DN}{{r}})<=Z_ENTREGA),4,'
                   f'IF({N}{{r}}="",7,5))))))'),
        "f_status": f"=CHOOSE({P}{{r}},{status_txt})",
        "f_rec": (f'=IFERROR(IF(INDEX({REC["m_rec"]},MATCH({CH}{{r}},{REC["chave"]},0))="","",'
                  f'UPPER(TRIM(INDEX({REC["m_rec"]},MATCH({CH}{{r}},{REC["chave"]},0))))),"")'),
        "f_disp": (f'=IF({RC}{{r}}="SIM","SIM",IF(OR({RC}{{r}}="PARCIAL",{RC}{{r}}="NÃO"),"NÃO",'
                   f'IF({E}{{r}}=5,"SIM","NÃO")))'),
        "f_quem": (f'=IF({D}{{r}}="SIM","Ninguém – material disponível",CHOOSE({E}{{r}},'
                   f'"Gestor da unidade"&IF(NOME_GESTOR="",""," – "&NOME_GESTOR),'
                   f'"Almox corporativo"&IF(NOME_ALMOX="",""," – "&NOME_ALMOX),'
                   f'"Comprador"&IF(NOME_COMPRADOR="",""," – "&NOME_COMPRADOR)&" (emitir o pedido)",'
                   f'IF({FO}{{r}}="","Comprador (pedido sem fornecedor)","Fornecedor: "&{FO}{{r}}'
                   f'&IF({PS}{{r}}="",""," – pedido SAP "&{PS}{{r}})),'
                   f'"Almoxarifado – TracOS tem entrada, conferir o físico"))'),
        "f_nec_manual": (f'=IFERROR(IF(INDEX({POS["m_data"]},MATCH({OS}{{r}},{POS["os_tracos"]},0))="","",'
                         f'INDEX({POS["m_data"]},MATCH({OS}{{r}},{POS["os_tracos"]},0))),"")'),
        "f_nec": f'=IF(ISNUMBER({NM}{{r}}),{NM}{{r}},IF({NT}{{r}}="","",{NT}{{r}}))',
        "f_dias_nec": f'=IF({N}{{r}}="","",{N}{{r}}-INT(DATA_REF))',
        "f_atraso": f'=IF(AND({D}{{r}}<>"SIM",{N}{{r}}<>""),MAX(0,INT(DATA_REF)-{N}{{r}}),0)',
        "f_dias_etapa": f'=IF({I}{{r}}="","",INT(DATA_REF)-INT({I}{{r}}))',
        "f_valor": f'=IF(OR({Q}{{r}}="",{PR}{{r}}=""),"",{Q}{{r}}*{PR}{{r}})',
    }
    obs = man["Follow-up"]

    def valor_de(k, l, r):
        if k in f:
            return f[k].format(r=r)
        if k == "f_origem":
            orig = l["origem_data_tracos"] if isinstance(l["origem_data_tracos"], str) else ""
            return f'=IF(ISNUMBER({NM}{r}),"Manual (Por OS)","{orig}")'
        if k == "m_obs":
            return obs.get(l["chave"], {}).get(COL_OBS)
        if k == "prev":
            return "SIM" if l["eh_preventiva"] else "NÃO"
        return l[k]

    fmts = {"f_nec": FMT_DATA, "data_nec_tracos": FMT_DATA, "f_nec_manual": FMT_DATA, "inicio_etapa": FMT_DATA,
            "entrada_em": FMT_DATA, "preco": FMT_RS, "f_valor": FMT_RS, "f_dias_nec": FMT_DIAS,
            "f_dias_etapa": "0", "f_atraso": FMT_ATRASO}
    centro = {"f_prio", "f_disp", "f_rec", "etapa", "prev", "os_tracos", "codigo", "qtd", "qtd_pendente",
              "unidade", "f_dias_nec", "f_atraso", "f_dias_etapa", "requisicao_txt", "pedido", "entrada"}
    ult = escrever_tabela(ws, COLS_FU, [l for _, l in L.iterrows()], valor_de, fmts, centro)
    ws.freeze_panes = f"D{LIN_1}"
    cf_palavras(ws, f"{c['f_status']}{LIN_1}:{c['f_status']}{ult}", f"${c['f_status']}{LIN_1}", CORES_STATUS)
    ws.conditional_formatting.add(f"{D}{LIN_1}:{D}{ult}", FormulaRule(
        formula=[f'{D}{LIN_1}="SIM"'], fill=PatternFill("solid", fgColor="C6EFCE", bgColor="C6EFCE"),
        font=Font(name=FONTE, bold=True, color="006100")))
    for col in (DN, c["f_atraso"]):
        ws.conditional_formatting.add(f"{col}{LIN_1}:{col}{ult}", CellIsRule(
            operator="lessThan" if col == DN else "greaterThan", formula=["0"],
            font=Font(name=FONTE, color="9C0006", bold=True)))
    paisagem(ws, caber_largura=False)


def aba_recebimento(wb, rec, man, FU, POS):
    ws = wb.create_sheet("Recebimento")
    ws.sheet_properties.tabColor = "70AD47"
    titulo(ws, "Recebimento de materiais – controle dos itens que estão chegando",
           "Todos os itens com pedido (inclusive pedidos sem OS). Marque 'Recebido?' quando o material chegar e "
           "for separado para a OS: SIM / PARCIAL / NÃO. Em branco = vale a entrada do TracOS. "
           "As colunas amarelas são preservadas nas próximas atualizações.")
    cabecalho(ws, LIN_CAB, COLS_REC)
    c = letras(COLS_REC)
    B_, P_, Q_, H_, V_ = c["m_rec"], c["f_nec"], c["f_dias"], c["os_tracos"], c["rec_tracos"]
    m = f"UPPER(TRIM({B_}{{r}}))"
    f = {
        "f_sit": (f'=IF({m}="SIM","{cz.SITUACAO_REC[4]}",IF({m}="PARCIAL","{cz.SITUACAO_REC[2]}",'
                  f'IF({m}="NÃO","{cz.SITUACAO_REC[3]}",IF({V_}{{r}}="SIM","{cz.SITUACAO_REC[5]}",'
                  f'IF(AND({P_}{{r}}<>"",N({Q_}{{r}})<0),"{cz.SITUACAO_REC[0]}","{cz.SITUACAO_REC[1]}")))))'),
        "f_dias": f'=IF({P_}{{r}}="","",{P_}{{r}}-INT(DATA_REF))',
        "f_falta_os": (f'=IF({H_}{{r}}="","",IFERROR(HYPERLINK("#\'Por OS\'!F"&(MATCH({H_}{{r}},{POS["os_tracos"]},0)'
                       f'+{LIN_CAB}),INDEX({POS["f_falt"]},MATCH({H_}{{r}},{POS["os_tracos"]},0))),""))'),
    }
    mm = man["Recebimento"]

    def valor_de(k, x, r):
        if k in f:
            return f[k].format(r=r)
        if k == "f_nec":
            if not x["no_followup"]:
                return None
            ch = f"{c['chave']}{r}"
            return (f'=IFERROR(IF(INDEX({FU["f_nec"]},MATCH({ch},{FU["chave"]},0))="","",'
                    f'INDEX({FU["f_nec"]},MATCH({ch},{FU["chave"]},0))),"")')
        if k.startswith("m_"):
            col = {"m_rec": REC_MARCA, "m_qtd": REC_QTD, "m_data": REC_DATA, "m_local": REC_LOCAL,
                   "m_obs": REC_OBS}[k]
            return mm.get(x["chave"], {}).get(col)
        if k == "prev":
            return "SIM" if x["eh_preventiva"] else "NÃO"
        if k == "rec_tracos":
            return "SIM" if x["recebido_tracos"] else "NÃO"
        return x[k]

    fmts = {"f_nec": FMT_DATA, "m_data": FMT_DATA, "entrada_em": FMT_DATA, "f_dias": FMT_DIAS}
    centro = {"m_rec", "m_qtd", "m_data", "f_falta_os", "os_tracos", "prev", "codigo", "qtd", "unidade",
              "f_dias", "pedido", "rec_tracos", "entrada"}
    ult = escrever_tabela(ws, COLS_REC, [x for _, x in rec.iterrows()], valor_de, fmts, centro, negrito={"f_sit"},
                          links={"f_falta_os"})
    dv = DataValidation(type="list", formula1='"SIM,PARCIAL,NÃO"', allow_blank=True,
                        errorTitle="Recebido?", error="Use SIM, PARCIAL ou NÃO (ou deixe em branco).",
                        promptTitle="Recebido?", prompt="SIM = chegou e está separado para a OS")
    dv.add(f"{B_}{LIN_1}:{B_}{ult}")
    ws.add_data_validation(dv)
    validar_data(ws, f"{c['m_data']}{LIN_1}:{c['m_data']}{ult}")
    ws.freeze_panes = f"C{LIN_1}"
    cf_palavras(ws, f"A{LIN_1}:A{ult}", f"$A{LIN_1}", CORES_REC)
    ws.conditional_formatting.add(f"{c['f_falta_os']}{LIN_1}:{c['f_falta_os']}{ult}", CellIsRule(
        operator="equal", formula=["0"], fill=PatternFill("solid", fgColor="C6EFCE", bgColor="C6EFCE"),
        font=Font(name=FONTE, bold=True, color="006100")))
    paisagem(ws)


def aba_por_os(wb, por_os, man, FU, REC):
    ws = wb.create_sheet("Por OS")
    ws.sheet_properties.tabColor = "2F75B5"
    titulo(ws, "OS – prontas para programar só com todos os itens disponíveis",
           "Preventivas primeiro; dentro delas, as aptas e depois as que faltam menos itens. Digite a data de "
           "necessidade quando a OS não tiver (vale para todos os itens dela) e a data em que liberou para a equipe.")
    cabecalho(ws, LIN_CAB, COLS_OS)
    c = letras(COLS_OS)
    A, TOT, DSP, FAL, LIB, MD, FD, DT_, PV, DI, G = (c[k] for k in (
        "os_tracos", "f_total", "f_disp", "f_falt", "m_lib", "m_data", "f_data", "data_tracos", "prev", "f_dias",
        "f_grupo"))
    a = f"${A}{{r}}"
    f = {
        "f_apta": (f'=IF({LIB}{{r}}<>"",IF({FAL}{{r}}=0,"▶ LIBERADA PARA A EQUIPE",'
                   f'"⚠ LIBERADA FALTANDO "&{FAL}{{r}}&IF({FAL}{{r}}=1," ITEM"," ITENS")),'
                   f'IF(AND({TOT}{{r}}>0,{FAL}{{r}}=0),'
                   f'"✅ APTA PARA PROGRAMAR","⛔ AGUARDANDO "&{FAL}{{r}}&IF({FAL}{{r}}=1," ITEM"," ITENS")))'),
        "f_data": f'=IF(ISNUMBER({MD}{{r}}),{MD}{{r}},IF({DT_}{{r}}="","",{DT_}{{r}}))',
        "f_dias": f'=IF({FD}{{r}}="","",{FD}{{r}}-INT(DATA_REF))',
        "f_total": f"=COUNTIFS({FU['os_tracos']},{a})",
        "f_disp": f'=COUNTIFS({FU["os_tracos"]},{a},{FU["f_disp"]},"SIM")',
        "f_falt": f"={TOT}{{r}}-{DSP}{{r}}",
        "f_caminho": f'=COUNTIFS({FU["os_tracos"]},{a},{FU["etapa"]},">=4",{FU["f_disp"]},"NÃO")',
        "f_compra": f'=COUNTIFS({FU["os_tracos"]},{a},{FU["etapa"]},"<=3")',
        "f_risco": f'=COUNTIFS({FU["os_tracos"]},{a},{FU["f_prio"]},"<=2")',
        "f_valor": f'=SUMIFS({FU["f_valor"]},{FU["os_tracos"]},{a},{FU["f_disp"]},"NÃO")',
        "f_ir": (f'=IFERROR(HYPERLINK("#\'Recebimento\'!B"&(MATCH({a},{REC["os_tracos"]},0)+{LIN_CAB}),"➜ Recebimento"),'
                 f'IFERROR(HYPERLINK("#\'Follow-up\'!A"&(MATCH({a},{FU["os_tracos"]},0)+{LIN_CAB}),"➜ Follow-up"),""))'),
        "f_grupo": (f'=IF({LIB}{{r}}<>"",IF({FAL}{{r}}=0,"LIBERADA","LIBERADA FALTANDO"),'
                    f'IF(AND({TOT}{{r}}>0,{FAL}{{r}}=0),"APTA",IF({FAL}{{r}}=1,"FALTA 1",'
                    f'IF({FAL}{{r}}<=3,"FALTA 2-3","FALTA 4+"))))'),
        "f_janela": (f'=IF(OR({FAL}{{r}}=0,{PV}{{r}}<>"SIM"),"",IF({FD}{{r}}="","SEM DATA",'
                     f'IF({DI}{{r}}<0,"VENCIDA",IF({DI}{{r}}<=7,"ATE 7",IF({DI}{{r}}<=15,"ATE 15",'
                     f'IF({DI}{{r}}<=30,"ATE 30","MAIS DE 30"))))))'),
        "f_seq": f'=IF({G}{{r}}="APTA",COUNTIF({G}${LIN_1}:{G}{{r}},"APTA"),"")',
    }
    mm = man["Por OS"]

    def valor_de(k, o, r):
        if k in f:
            return f[k].format(r=r)
        if k == "f_lista":
            ref = f"{c['f_lista']}{r}"
            return ArrayFormula(ref, (
                f'=IFERROR(_xlfn.TEXTJOIN("; ",TRUE,IF(({FU["os_tracos"]}={A}{r})*({FU["f_disp"]}="NÃO"),'
                f'{FU["codigo"]}&" "&{FU["descricao"]},"")),"ver aba Follow-up")'))
        if k.startswith("m_"):
            col = {"m_data": OS_DATA, "m_lib": OS_LIB, "m_obs": COL_OBS}[k]
            v = mm.get(_k(o["os_tracos"]), {}).get(col)
            return (_data(v) or v) if k in ("m_data", "m_lib") and v is not None else v
        if k == "prev":
            return "SIM" if o["preventiva"] else "NÃO"
        if k == "lista_ok":
            return LISTA_INCOMPLETA if o["fluxo_incompleto"] else "OK"
        return o[k]

    fmts = {"m_data": FMT_DATA, "f_data": FMT_DATA, "f_dias": FMT_DIAS, "f_valor": FMT_RS,
            "data_tracos": FMT_DATA, "m_lib": FMT_DATA}
    centro = {"os_tracos", "prev", "m_data", "f_data", "f_dias", "f_total", "f_disp", "f_falt", "f_caminho",
              "f_compra", "f_risco", "data_tracos", "m_lib", "plano"}
    ult = escrever_tabela(ws, COLS_OS, [o for _, o in por_os.iterrows()], valor_de, fmts, centro,
                          negrito={"f_apta"}, links={"f_ir"})
    ws.freeze_panes = f"D{LIN_1}"
    for k in ("m_data", "m_lib"):
        validar_data(ws, f"{c[k]}{LIN_1}:{c[k]}{ult}")
    ws.conditional_formatting.add(f"A{LIN_1}:E{ult}", FormulaRule(
        formula=[f'$D{LIN_1}="SIM"'], fill=P_PREV, font=Font(name=FONTE, bold=True)))
    cf_palavras(ws, f"{c['f_apta']}{LIN_1}:{c['f_apta']}{ult}", f"${c['f_apta']}{LIN_1}", CORES_APTA)
    ws.conditional_formatting.add(f"{c['f_dias']}{LIN_1}:{c['f_dias']}{ult}", CellIsRule(
        operator="lessThan", formula=["0"], font=Font(name=FONTE, color="9C0006", bold=True)))
    ws.conditional_formatting.add(f"{c['lista_ok']}{LIN_1}:{c['lista_ok']}{ult}", FormulaRule(
        formula=[f'LEFT(${c["lista_ok"]}{LIN_1},1)="⚠"'], font=Font(name=FONTE, color="9C0006", bold=True)))
    paisagem(ws)


def aba_por_fornecedor(wb, pf, man, FU):
    ws = wb.create_sheet("Por Fornecedor")
    ws.sheet_properties.tabColor = "BF8F00"
    titulo(ws, "Pedidos abertos por fornecedor (para cobrança)",
           "Pedidos e valor vêm da base de pedidos (inclui itens sem OS). Itens a receber, vencidos e atraso vêm "
           "do Follow-up e já descontam o que você marcou como recebido.")
    cabecalho(ws, LIN_CAB, COLS_FORN)
    c = letras(COLS_FORN)
    f = {
        "f_receber": f'=COUNTIFS({FU["fornecedor"]},$A{{r}},{FU["etapa"]},4,{FU["f_disp"]},"NÃO")',
        "f_vencidos": f"=COUNTIFS({FU['fornecedor']},$A{{r}},{FU['etapa']},4,{FU['f_prio']},1)",
        "f_atraso": f"=SUMPRODUCT(MAX(({FU['fornecedor']}=$A{{r}})*({FU['etapa']}=4)*{FU['f_atraso']}))",
        "f_dias": f'=IF({c["pedido_mais_antigo"]}{{r}}="","",INT(DATA_REF)-INT({c["pedido_mais_antigo"]}{{r}}))',
    }
    mm = man["Por Fornecedor"]
    EM, URL = c["m_email"], c["f_url"]

    def valor_de(k, x, r):
        if k in f:
            return f[k].format(r=r)
        if k in ("m_obs", "m_email"):
            return mm.get(str(x["fornecedor"]), {}).get(COL_OBS if k == "m_obs" else FORN_EMAIL)
        if k == "f_mail":
            return f'=IF({EM}{r}="","✎ preencha o e-mail →",HYPERLINK({URL}{r},"✉ Cobrar por e-mail"))'
        if k == "f_url":
            saps = re.findall(r"SAP (\d+)", str(x["pedidos"]))
            lista = ", ".join(saps)
            venc = " Os itens ja estao com a data de necessidade vencida." if x["_atraso"] > 0 else ""
            completo, curto = mailto_partes(
                f"Previsao de entrega - pedidos SAP {lista}" if len(saps) <= 2 else "Previsao de entrega - pedidos em aberto",
                [f"Prezados, favor informar a previsao de entrega dos pedidos SAP {lista}.{venc} Obrigado.",
                 f"Prezados, favor informar a previsao de entrega dos pedidos SAP {lista}.",
                 f"Previsao de entrega dos pedidos SAP {lista}?"])
            return (f'=IF({EM}{r}="","",IF(LEN("mailto:"&{EM}{r}&"{completo}")<=255,"mailto:"&{EM}{r}&"{completo}",'
                    f'"mailto:"&{EM}{r}&"{curto}"))')
        return x[k]

    fmts = {"f_atraso": FMT_ATRASO, "valor_aberto": FMT_RS, "pedido_mais_antigo": FMT_DATA}
    centro = {"n_pedidos", "itens_abertos", "f_receber", "f_vencidos", "f_atraso", "f_dias", "itens_sem_os",
              "pedido_mais_antigo", "valor_aberto"}
    ult = escrever_tabela(ws, COLS_FORN, [x for _, x in pf.iterrows()], valor_de, fmts, centro,
                          negrito={"fornecedor"}, links={"f_mail"})
    ws.freeze_panes = f"B{LIN_1}"
    sem_link(ws, f"{c['f_mail']}{LIN_1}:{c['f_mail']}{ult}", f"{c['f_mail']}{LIN_1}")
    ws.conditional_formatting.add(f"{c['f_vencidos']}{LIN_1}:{c['f_atraso']}{ult}", CellIsRule(
        operator="greaterThan", formula=["0"], fill=PatternFill("solid", fgColor="FFC7CE", bgColor="FFC7CE"),
        font=Font(name=FONTE, color="9C0006", bold=True)))
    paisagem(ws)


def aba_divergencias(wb, D, man, orfas):
    ws = wb.create_sheet("Divergências")
    ws.sheet_properties.tabColor = "C00000"
    titulo(ws, "Divergências e registros não casados",
           "As linhas 'NÃO CASADO' são as únicas que NÃO estão no Follow-up (contam na conciliação; elas aparecem "
           "na aba Recebimento). As demais apontam para uma linha do Follow-up pela Chave.")
    cols = [("Tipo", 40, "tipo"), ("Gravidade", 9, "gravidade"), ("Base", 11, "base"),
            ("Linha de origem", 9, "linha"), (COL_CHAVE, 24, "chave"), ("Está no Follow-up?", 10, "no_followup"),
            ("Código material", 10, "codigo"), ("Descrição do material", 34, "descricao"),
            ("Requisição", 10, "requisicao"), ("Pedido", 8, "pedido"), ("OS TracOS", 9, "os"),
            ("Fornecedor", 34, "fornecedor"), ("Detalhe", 90, "detalhe"), (COL_OBS, 40, "m_obs")]
    cabecalho(ws, LIN_CAB, cols)
    regs = ([] if D is None or not len(D) else D.to_dict("records")) + orfas
    mm = man["Divergências"]

    def valor_de(k, d, r):
        if k == "m_obs":
            return mm.get(f"{d['tipo']}|{d.get('chave')}", {}).get(COL_OBS)
        return d.get(k)

    ult = escrever_tabela(ws, cols, regs, valor_de, {},
                          {"gravidade", "linha", "no_followup", "codigo", "requisicao", "pedido", "os"})
    ws.freeze_panes = f"B{LIN_1}"
    for g, fundo, letra in (("Alta", "FFC7CE", "9C0006"), ("Média", "FFE699", "7F6000"),
                            ("Info", "E7E6E6", "404040")):
        ws.conditional_formatting.add(f"B{LIN_1}:B{ult}", FormulaRule(
            formula=[f'$B{LIN_1}="{g}"'], fill=PatternFill("solid", fgColor=fundo, bgColor=fundo),
            font=Font(name=FONTE, color=letra, bold=True)))
    ws.conditional_formatting.add(f"A{LIN_1}:A{ult}", FormulaRule(
        formula=[f'LEFT($A{LIN_1},10)="NÃO CASAD"'], font=Font(name=FONTE, color="9C0006", bold=True)))
    paisagem(ws)


def aba_painel(wb, R, FU, REC, POS):
    ws = wb.create_sheet("Painel", 0)
    ws.sheet_properties.tabColor = "1F3864"
    pf, reqs = R["por_fornecedor"], R["requisicoes"]
    cel(ws, "A1", "Follow-up de peças – manutenção preventiva", F_TITULO)
    for col, w in zip("ABCDEFGHIJ", [52, 15, 16, 15, 16, 14, 12, 40, 10, 22]):
        ws.column_dimensions[col].width = w
    cel(ws, "A2", "Data de referência", F_NEGRITO)
    cel(ws, "B2", "=DATA_REF", F_NEGRITO, fmt=FMT_DATA, alin=Alignment(horizontal="left"))
    cel(ws, "C2", "Gerado em", F_NOTA)
    cel(ws, "D2", dt.datetime.now().replace(microsecond=0), F_NOTA, fmt=FMT_DATAHORA,
        alin=Alignment(horizontal="left"))
    # menu de navegação
    menu = [("📦 Recebimento – marcar o que chegou", "Recebimento", "B"), ("🛠 Por OS", "Por OS", "A"),
            ("📋 Follow-up", "Follow-up", "A"), ("🏭 Fornecedores", "Por Fornecedor", "A"),
            ("⚠ Divergências", "Divergências", "A"), ("⚙ Parâmetros", "Parâmetros", "B")]
    for j, (txt, aba, col) in enumerate(menu, 1):
        cel(ws, (3, j), link(local(aba, col), f'"{txt}"'), F_BOTAO, preench=P_BOTAO, alin=AL_CAB)
    ws.row_dimensions[3].height = 24
    cel(ws, "A4", "Clique nos textos e números sublinhados para ir direto aos itens. Em cada aba, "
                  "'⬅ Voltar ao Painel' fica na célula A1. ✉ Cobrar abre o e-mail pronto.", F_NOTA)
    lin = 5
    for a in R["alertas"]:
        cel(ws, (lin, 1), "⚠ " + a, F_ALERTA)
        lin += 1

    def secao(t, nota=None):
        nonlocal lin
        lin += 1
        cel(ws, (lin, 1), t, F_SECAO)
        if nota:
            cel(ws, (lin, 3), nota, F_NOTA)
        lin += 1

    def cab(titulos):
        nonlocal lin
        for j, t in enumerate(titulos, 1):
            cel(ws, (lin, j), t, F_CAB, preench=P_CAB, alin=AL_CAB)
        ws.row_dimensions[lin].height = 30
        lin += 1

    def total(cols, fmt_cols=()):
        nonlocal lin
        for j, v in enumerate(["Total"] + [f"=SUM({c}{ini}:{c}{lin - 1})" for c in cols], 1):
            cel(ws, (lin, j), v, F_NEGRITO, fmt=FMT_RS if j in fmt_cols else None, preench=P_TOTAL)
        lin += 1

    def rotulo(loc, txt, cores):
        """Rótulo colorido e clicável na coluna A."""
        fundo, letra = next((f, l) for w, f, l in cores if w in txt)
        cel(ws, (lin, 1), link(loc, f'"{txt}"'), Font(name=FONTE, bold=True, color=letra, underline="single"),
            preench=PatternFill("solid", fgColor=fundo))

    def achar(valores, faixa):
        """MATCH do 1º valor encontrado (tenta na ordem)."""
        expr = f"MATCH({valores[-1]},{faixa},0)"
        for v in reversed(valores[:-1]):
            expr = f"IFERROR(MATCH({v},{faixa},0),{expr})"
        return expr

    # 1. OS prontas para programar
    secao("1. OS prontas para programar (todos os itens disponíveis)", "Clique para abrir a lista na aba Por OS.")
    cab(["Situação da OS", "OS preventivas", "Todas as OS", "O que fazer"])
    grupos = [
        ("✅ APTA PARA PROGRAMAR", "APTA", "Programar e passar para a equipe (anotar a data na Por OS)"),
        ("⛔ AGUARDANDO 1 ITEM", "FALTA 1", "Cobrar o item que falta (coluna 'Itens que faltam')"),
        ("⛔ AGUARDANDO 2 A 3 ITENS", "FALTA 2-3", "Cobrar os itens que faltam"),
        ("⛔ AGUARDANDO 4 OU MAIS ITENS", "FALTA 4+", "Acompanhar compra / aprovação"),
        ("▶ LIBERADA PARA A EQUIPE", "LIBERADA", "—"),
        ("⚠ LIBERADA FALTANDO ITENS", "LIBERADA FALTANDO", "Conferir: OS na equipe sem todos os itens"),
    ]
    for txt, g, acao in grupos:
        loc = local("Por OS", "A", f'MATCH("{g}",{POS["f_grupo"]},0)')
        rotulo(loc, txt, CORES_APTA)
        cel(ws, (lin, 2), link(loc, f'COUNTIFS({POS["f_grupo"]},"{g}",{POS["prev"]},"SIM")'), F_LINK)
        cel(ws, (lin, 3), link(loc, f'COUNTIFS({POS["f_grupo"]},"{g}")'), F_LINK)
        cel(ws, (lin, 4), acao, F_NOTA)
        lin += 1
    loc = local("Por OS", "A", f'MATCH("{LISTA_INCOMPLETA}",{POS["lista_ok"]},0)')
    cel(ws, (lin, 1), link(loc, '"⚠ OS com lista de itens possivelmente incompleta"'),
        Font(name=FONTE, bold=True, color="9C0006", underline="single"))
    cel(ws, (lin, 2), link(loc, f'COUNTIFS({POS["prev"]},"SIM",{POS["lista_ok"]},"{LISTA_INCOMPLETA}")'), F_LINK)
    cel(ws, (lin, 3), link(loc, f'COUNTIFS({POS["lista_ok"]},"{LISTA_INCOMPLETA}")'), F_LINK)
    cel(ws, (lin, 4), "Conferir no TracOS se a OS tem mais itens", F_NOTA)
    lin += 2
    cel(ws, (lin, 1), "OS aptas para programar agora (clique na OS para abrir)", F_NEGRITO)
    cel(ws, (lin, 3), f'=IF(COUNTIFS({POS["f_grupo"]},"APTA")>10,"Mostrando 10 de "&COUNTIFS({POS["f_grupo"]},'
                      f'"APTA")&" – veja todas na aba Por OS","")', F_NOTA)
    lin += 1
    cab(["OS", "Itens", "Data de necessidade", "Ativo"])
    for k in range(1, 11):
        m = f'MATCH({k},{POS["f_seq"]},0)'
        vazio = '"Nenhuma OS apta no momento – marque os itens que chegaram na aba Recebimento."' if k == 1 else '""'
        cel(ws, (lin, 1), f'=IFERROR(HYPERLINK("#\'Por OS\'!A"&({m}+{LIN_CAB}),"OS #"&INDEX({POS["os_tracos"]},{m})'
                          f'&" – "&INDEX({POS["descricao_os"]},{m})),{vazio})', F_LINK_B)
        cel(ws, (lin, 2), f'=IFERROR(INDEX({POS["f_total"]},{m}),"")', alin=AL_CENTRO)
        cel(ws, (lin, 3), f'=IFERROR(IF(INDEX({POS["f_data"]},{m})="","",INDEX({POS["f_data"]},{m})),"")',
            fmt=FMT_DATA, alin=AL_CENTRO)
        cel(ws, (lin, 4), f'=IFERROR(INDEX({POS["ativo"]},{m}),"")')
        lin += 1

    # 2. recebimento
    secao("2. Recebimento de materiais", "Clique para ir à aba Recebimento já na coluna 'Recebido?'.")
    cab(["Situação do item", "Itens", "O que fazer"])
    acoes = {0: "Cobrar o fornecedor e conferir se já chegou", 1: "Acompanhar a entrega",
             2: "Cobrar o saldo do fornecedor", 3: "Conferir com o almoxarifado / TracOS",
             4: "Separado – verificar se a OS ficou apta", 5: "Conferir o físico e marcar SIM"}
    ini = lin
    for k, txt in cz.SITUACAO_REC.items():
        loc = local("Recebimento", "B", f'MATCH("{txt}",{REC["f_sit"]},0)')
        rotulo(loc, txt, CORES_REC)
        cel(ws, (lin, 2), link(loc, f'COUNTIFS({REC["f_sit"]},"{txt}")'), F_LINK)
        cel(ws, (lin, 3), acoes[k], F_NOTA)
        lin += 1
    total("B")

    # 3. funil
    secao("3. Funil de compras por etapa", "Valor só dos itens com preço conhecido (ver 'Itens sem preço').")
    cab(["Etapa", "Itens", "Valor (R$)", "Itens preventiva", "Valor preventiva (R$)", "Itens sem preço"])
    ini = lin
    for e, txt in cz.ETAPAS.items():
        loc = local("Follow-up", "A", f"MATCH({e},{FU['etapa']},0)")
        cel(ws, (lin, 1), link(loc, f'"{txt}"'), F_LINK)
        cel(ws, (lin, 2), link(loc, f"COUNTIFS({FU['etapa']},{e})"), F_LINK)
        cel(ws, (lin, 3), f"=SUMIFS({FU['f_valor']},{FU['etapa']},{e})", fmt=FMT_RS)
        cel(ws, (lin, 4), f'=COUNTIFS({FU["etapa"]},{e},{FU["prev"]},"SIM")')
        cel(ws, (lin, 5), f'=SUMIFS({FU["f_valor"]},{FU["etapa"]},{e},{FU["prev"]},"SIM")', fmt=FMT_RS)
        cel(ws, (lin, 6), f'=COUNTIFS({FU["etapa"]},{e})-COUNTIFS({FU["etapa"]},{e},{FU["preco"]},"<>")')
        lin += 1
    total("BCDEF", (3, 5))

    # 4. status
    secao("4. Itens por status de risco", "Clique para ir ao 1º item do status no Follow-up.")
    cab(["Status de risco", "Itens", "Itens preventiva", "Valor (R$)"])
    ini = lin
    for p_, txt in cz.STATUS.items():
        loc = local("Follow-up", "A", f"MATCH({p_},{FU['f_prio']},0)")
        rotulo(loc, txt, CORES_STATUS)
        cel(ws, (lin, 2), link(loc, f"COUNTIFS({FU['f_prio']},{p_})"), F_LINK)
        cel(ws, (lin, 3), f'=COUNTIFS({FU["f_prio"]},{p_},{FU["prev"]},"SIM")')
        cel(ws, (lin, 4), f"=SUMIFS({FU['f_valor']},{FU['f_prio']},{p_})", fmt=FMT_RS)
        lin += 1
    total("BCD", (4,))

    # 5. OS preventivas por janela de necessidade
    secao("5. OS preventivas com itens faltando", "Janela pela data de necessidade usada (contagem acumulada).")
    cab(["Janela", "OS", "Itens faltando"])
    J, F_ = POS["f_janela"], POS["f_falt"]
    janelas = [("Necessidade já vencida", ["VENCIDA"]), ("Próximos 7 dias", ["ATE 7"]),
               ("Próximos 15 dias", ["ATE 7", "ATE 15"]), ("Próximos 30 dias", ["ATE 7", "ATE 15", "ATE 30"]),
               ("Sem data de necessidade (preencha na aba Por OS)", ["SEM DATA"])]
    for rot, chaves in janelas:
        loc = local("Por OS", "A", achar([f'"{x}"' for x in chaves], J))
        cel(ws, (lin, 1), link(loc, f'"{rot}"'), F_LINK)
        cel(ws, (lin, 2), link(loc, "+".join(f'COUNTIFS({J},"{x}")' for x in chaves)), F_LINK)
        cel(ws, (lin, 3), "=" + "+".join(f'SUMIFS({F_},{J},"{x}")' for x in chaves))
        lin += 1
    todas = ["VENCIDA", "ATE 7", "ATE 15", "ATE 30", "MAIS DE 30", "SEM DATA"]
    cel(ws, (lin, 1), "Total de OS preventivas com itens faltando", F_NEGRITO, preench=P_TOTAL)
    cel(ws, (lin, 2), "=" + "+".join(f'COUNTIFS({J},"{x}")' for x in todas), F_NEGRITO, preench=P_TOTAL)
    cel(ws, (lin, 3), "=" + "+".join(f'SUMIFS({F_},{J},"{x}")' for x in todas), F_NEGRITO, preench=P_TOTAL)
    lin += 1

    # 6. fornecedores
    secao("6. Fornecedores com pedidos atrasados", "Preencha o e-mail na aba Por Fornecedor para ativar ✉ Cobrar.")
    cab(["Fornecedor (clique para abrir)", "Pedidos abertos", "Itens com necessidade vencida",
         "Atraso mais antigo (dias)", "Valor em aberto (R$)", "Cobrar"])
    cf = letras(COLS_FORN)
    atrasados = [i for i, (_, x) in enumerate(pf.iterrows()) if x["_atraso"] > 0] if len(pf) else []
    if not atrasados:
        cel(ws, (lin, 1), "Nenhum fornecedor com itens atrasados.", F_NOTA)
        lin += 1
    for i in atrasados[:10]:
        rf = LIN_1 + i
        cel(ws, (lin, 1), f"=HYPERLINK(\"#'Por Fornecedor'!A{rf}\",'Por Fornecedor'!{cf['fornecedor']}{rf})", F_LINK_B)
        for j, k in enumerate(["n_pedidos", "f_vencidos", "f_atraso", "valor_aberto"], 2):
            cel(ws, (lin, j), f"='Por Fornecedor'!{cf[k]}{rf}", fmt={4: FMT_ATRASO, 5: FMT_RS}.get(j),
                alin=AL_CENTRO)
        cel(ws, (lin, 6), f"=IF('Por Fornecedor'!{cf['m_email']}{rf}=\"\",\"(sem e-mail)\","
                          f"HYPERLINK('Por Fornecedor'!{cf['f_url']}{rf},\"✉ Cobrar\"))", F_LINK_B, alin=AL_CENTRO)
        lin += 1

    # 7. requisições paradas
    secao("7. Requisições paradas por nível de aprovação",
          "Preencha os e-mails do gestor e do almox em Parâmetros para ativar ✉ Cobrar.")
    cab(["Nível", "Requisições pendentes", "Itens", "Itens parados (> X dias)", "Dias da mais antiga"])
    for e, rot in ((1, "01 - Gestor da unidade"), (2, "02 - Almox corporativo")):
        loc = local("Follow-up", "A", f"MATCH({e},{FU['etapa']},0)")
        cel(ws, (lin, 1), link(loc, f'"{rot}"'), F_LINK_B)
        cel(ws, (lin, 2), int((reqs["etapa"] == e).sum()) if len(reqs) else 0)
        cel(ws, (lin, 3), link(loc, f"COUNTIFS({FU['etapa']},{e})"), F_LINK)
        cel(ws, (lin, 4), f"=COUNTIFS({FU['etapa']},{e},{FU['f_prio']},2)")
        cel(ws, (lin, 5), f"=SUMPRODUCT(MAX(({FU['etapa']}={e})*{FU['f_dias_etapa']}))")
        lin += 1
    lin += 1
    cab(["OS / ativo (clique para ver os itens)", "Requisição", "Req. SAP", "Nível", "Itens", "Início",
         "Dias parada", "Situação", "Preventiva", "Cobrar"])
    for e in (1, 2):
        sub = reqs[reqs["etapa"] == e].head(10) if len(reqs) else reqs
        lim = "X_NIVEL01" if e == 1 else "X_NIVEL02"
        email = "EMAIL_GESTOR" if e == 1 else "EMAIL_ALMOX"
        for _, q in sub.iterrows():
            os_txt = f"#{int(q['os_tracos'])} {q['descricao_os']}" if not pd.isna(q["os_tracos"]) else ""
            os_txt += f" – {q['ativo']}" if isinstance(q["ativo"], str) else ""
            req_txt = f"#{int(q['requisicao'])}"
            loc = local("Follow-up", "A", f'MATCH("{req_txt}",{FU["requisicao_txt"]},0)')
            desde = f"{pd.Timestamp(q['inicio']):%d/%m/%Y}"
            ativo = q["ativo"] if isinstance(q["ativo"], str) else ""
            completo, curto = mailto_partes(
                f"Aprovacao pendente - requisicao SAP {q['req_sap']}",
                [f"Favor aprovar a requisicao SAP {q['req_sap']} (TracOS {req_txt}) da OS {q['os_sap']} - {ativo}, "
                 f"pendente desde {desde}. Obrigado.",
                 f"Favor aprovar a requisicao SAP {q['req_sap']} da OS {q['os_sap']}, pendente desde {desde}.",
                 f"Favor aprovar a requisicao SAP {q['req_sap']}."])
            vals = [link(loc, '"' + os_txt.replace('"', "'") + '"'), req_txt, q["req_sap"], "01" if e == 1 else "02",
                    q["itens"], q["inicio"], f"=INT(DATA_REF)-INT(F{lin})",
                    f'=IF(G{lin}>{lim},"🔴 PARADA","dentro do prazo")', "SIM" if q["preventiva"] else "NÃO",
                    formula_mailto(email, completo, curto, "✉ Cobrar", "(e-mail em Parâmetros)")]
            for j, v in enumerate(vals, 1):
                cel(ws, (lin, j), v, F_LINK if j in (1, 10) else F_NORMAL, fmt=FMT_DATA if j == 6 else None,
                    alin=AL_TOPO if j == 1 else AL_CENTRO)
            lin += 1
    ws.conditional_formatting.add(f"H1:H{lin}", FormulaRule(
        formula=['ISNUMBER(SEARCH("PARADA",H1))'], font=Font(name=FONTE, color="9C0006", bold=True)))
    sem_link(ws, f"A1:J{lin}", "A1")
    ws.freeze_panes = "A4"
    paisagem(ws)


def aba_bases(wb, B):
    ws = wb.create_sheet("Bases tratadas")
    ws.sheet_properties.tabColor = "A6A6A6"
    titulo(ws, "Bases tratadas (auditoria)",
           "As 3 exportações já normalizadas. 'linha_origem' = linha no CSV (1 = cabeçalho); é a "
           "referência usada em 'Linhas de origem' no Follow-up e em Divergências.")
    lin = LIN_CAB + 1
    larg = {}
    for nome, tab in (("requisicao", "tbRequisicao"), ("fluxo", "tbFluxo"), ("pedido", "tbPedido")):
        df = B[nome]["norm"]
        cel(ws, (lin, 1), f"{nome.upper()} – {os.path.basename(B[nome]['arquivo'])} ({len(df)} linhas)", F_SECAO)
        lin += 1
        cols = list(df.columns)
        for j, c in enumerate(cols, 1):
            cel(ws, (lin, j), c, F_NEGRITO)
            larg[j] = max(larg.get(j, 0), min(40, len(c) + 2))
        for i, row in enumerate(df.itertuples(index=False), 1):
            for j, v in enumerate(row, 1):
                fmt = FMT_DATAHORA if isinstance(v, pd.Timestamp) and not pd.isna(v) else None
                cel(ws, (lin + i, j), v, fmt=fmt)
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    larg[j] = max(larg.get(j, 0), min(40, len(str(v)) + 1))
        fim = lin + max(len(df), 1)
        t = Table(displayName=tab, ref=f"A{lin}:{get_column_letter(len(cols))}{fim}")
        t.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
        ws.add_table(t)
        lin = fim + 3
    for j, w in larg.items():
        ws.column_dimensions[get_column_letter(j)].width = w


def aba_oculta(wb, nome, cabec, linhas, fmt_col=None):
    ws = wb.create_sheet(nome)
    ws.append(cabec)
    for l in linhas:
        ws.append([val(v) for v in l])
    if fmt_col:
        for c in ws[fmt_col][1:]:
            c.number_format = FMT_DATAHORA
    ws.sheet_state = "hidden"


# ------------------------------------------------------------------ principal
def gerar(pasta_bases, pasta_saida, hoje=None, data_fixa=None, silencioso=False):
    hoje = pd.Timestamp(hoje or dt.date.today()).normalize()
    os.makedirs(pasta_saida, exist_ok=True)
    B = tb.carregar_bases(pasta_bases)
    ant = ler_versao_anterior(pasta_saida)
    man = ant["manuais"]
    prm = dict(ant["prm"])
    R = cz.cruzar(B, hoje, ant["historico"],
                  {k: v for k, v in prm.items() if not k.startswith(("nome_", "email_"))},
                  manuais=manuais_para_cruzamento(man))

    # anotações cujo item/OS sumiu: não se perdem (aba oculta _anotacoes + aviso em Divergências)
    Dv = R["divergencias"]
    atuais = {
        "Follow-up": set(R["linhas"]["chave"]),
        "Recebimento": set(R["recebimento"]["chave"]),
        "Por OS": {_k(int(x)) for x in R["por_os"]["os_tracos"]} if len(R["por_os"]) else set(),
        "Por Fornecedor": set(R["por_fornecedor"]["fornecedor"]) if len(R["por_fornecedor"]) else set(),
        "Divergências": {f"{t}|{c}" for t, c in zip(Dv["tipo"], Dv["chave"])} if len(Dv) else set(),
    }
    orfas, orfas_reg = [], []
    for aba, d in man.items():
        for k, cols in d.items():
            if k in atuais[aba] or (aba == "Divergências" and k.startswith(TIPO_ORFA + "|")):
                continue
            for col, v in cols.items():
                orfas_reg.append([aba, k, col, v])
            orfas.append(dict(tipo=TIPO_ORFA, gravidade="Info", base=aba, linha=None, chave=f"{aba}:{k}",
                              no_followup="NÃO",
                              detalhe=" | ".join(f"{col}: {v:%d/%m/%Y}" if isinstance(v, dt.datetime) else
                                                 f"{col}: {v}" for col, v in cols.items())))

    FU = faixas("Follow-up", COLS_FU, len(R["linhas"]))
    REC = faixas("Recebimento", COLS_REC, len(R["recebimento"]))
    POS = faixas("Por OS", COLS_OS, len(R["por_os"]))

    wb = Workbook()
    wb.remove(wb.active)
    aba_parametros(wb, {**cz.PARAMETROS_PADRAO, **prm}, B, R, data_fixa, ant)
    aba_followup(wb, R["linhas"], man, FU, REC, POS)
    aba_recebimento(wb, R["recebimento"], man, FU, POS)
    aba_por_os(wb, R["por_os"], man, FU, REC)
    aba_por_fornecedor(wb, R["por_fornecedor"], man, FU)
    aba_divergencias(wb, Dv, man, orfas)
    aba_painel(wb, R, FU, REC, POS)
    aba_bases(wb, B)
    aba_oculta(wb, "_historico", ["Chave", "Etapa", "Desde"],
               [[k, e, d] for k, (e, d) in sorted(R["historico"].items())], fmt_col="C")
    aba_oculta(wb, "_anotacoes", ["Aba", "Chave", "Coluna", "Valor"], orfas_reg)
    ordem = ["Painel", "Por OS", "Recebimento", "Follow-up", "Por Fornecedor", "Divergências", "Parâmetros",
             "Bases tratadas", "_historico", "_anotacoes"]
    wb._sheets = [wb[n] for n in ordem]
    wb.active = 0
    wb.calculation.fullCalcOnLoad = True

    destino = os.path.join(pasta_saida, f"{PREFIXO}{hoje:%Y-%m-%d}.xlsx")
    try:
        wb.save(destino)
    except PermissionError:
        destino = os.path.join(pasta_saida, f"{PREFIXO}{hoje:%Y-%m-%d}_{dt.datetime.now():%H%M%S}.xlsx")
        wb.save(destino)
        print("AVISO: a planilha do dia estava aberta no Excel; salvei com outro nome.")

    if not silencioso:
        resumo(R, destino, ant, orfas)
    return destino, R


def resumo(R, destino, ant, orfas):
    L, po, rc = R["linhas"], R["por_os"], R["recebimento"]
    print("=" * 78)
    print("FOLLOW-UP DE PEÇAS – atualização concluída")
    print("=" * 78)
    print(f"Arquivo gerado: {destino}")
    n_anot = sum(len(v) for v in ant["manuais"].values())
    print(f"Anotações reaproveitadas de: {os.path.basename(ant['arquivo']) if ant['arquivo'] else '(primeira versão)'}"
          f"  |  {n_anot} itens/OS com anotação, {len(orfas)} sem item atual")
    print("\nConciliação (entrada = Follow-up + Divergências não casadas):")
    for _, c in R["conciliacao"].iterrows():
        print(f"  {c['base']:<11} entrada {c['entrada']:>4} | follow-up {c['follow_up']:>4} | "
              f"divergências {c['divergencias']:>3} | {'OK' if c['ok'] else 'DIFERENÇA!'}")
    if len(po):
        aptas = po[po["apta"] & ~po["liberada"]]
        print(f"\nOS: {len(po)} | aptas para programar: {len(aptas)} | liberadas: {int(po['liberada'].sum())} | "
              f"aguardando itens: {int((~po['apta'] & ~po['liberada']).sum())}")
        for _, o in aptas.head(10).iterrows():
            print(f"  ✅ OS #{int(o['os_tracos'])} {o['descricao_os']} ({int(o['itens'])} itens)")
    print("\nRecebimento:")
    for s, n in rc["situacao"].value_counts().reindex(list(cz.SITUACAO_REC.values())).dropna().items():
        print(f"  {s:<28} {int(n):>4}")
    print("\nItens por status de risco (na data de hoje):")
    for p_, n in L["prioridade"].value_counts().sort_index().items():
        print(f"  {cz.STATUS[p_]:<30} {n:>4}")
    for a in R["alertas"]:
        print("\nATENÇÃO: " + a)
    if not R["conciliacao"]["ok"].all():
        print("\nERRO: a conciliação não fechou. Veja a aba Parâmetros.")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
    ap = argparse.ArgumentParser(description="Gera a planilha de follow-up de peças (TracOS).")
    ap.add_argument("--bases", default=os.path.join(AQUI, "bases"))
    ap.add_argument("--saida", default=os.path.join(AQUI, "saida"))
    ap.add_argument("--hoje", help="simula outra data (AAAA-MM-DD); também fixa a data de referência")
    ap.add_argument("--abrir", action="store_true", help="abre a planilha no final (Windows)")
    a = ap.parse_args()
    hoje = pd.Timestamp(a.hoje).to_pydatetime() if a.hoje else None
    try:
        destino, R = gerar(a.bases, a.saida, hoje=hoje, data_fixa=hoje)
    except FileNotFoundError as e:
        print(f"ERRO: {e}")
        print("Coloque os 3 arquivos exportados do TracOS na pasta 'bases' e rode de novo.")
        return 1
    if a.abrir and hasattr(os, "startfile"):
        os.startfile(destino)
    return 0 if R["conciliacao"]["ok"].all() else 2


if __name__ == "__main__":
    sys.exit(main())
