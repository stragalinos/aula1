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
import shutil
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

# o que você digita (colunas amarelas) fica todo na aba Follow-up e é preservado entre atualizações.
# Por item (chave material | requisição | OS):
REC_MARCA = "Recebido?"
REC_DATA = "Data do recebimento"
REC_LOCAL = "Local / kit de separação"
CAMPOS_ITEM = [REC_MARCA, REC_DATA, REC_LOCAL, COL_OBS]
# Por OS (digitados na 1ª linha da OS; vale o maior valor das linhas da OS):
OS_DATA = "Data de necessidade da OS"
OS_LIB = "OS liberada para a equipe em"
CAMPOS_OS = [OS_DATA, OS_LIB]
# cadastro (aba Parâmetros)
FORN_EMAIL = "E-mail do fornecedor"
ID_FORN = "forn_email"  # marca das linhas do cadastro de e-mails na coluna oculta 'id' de Parâmetros

# versões anteriores tinham colunas digitadas em outras abas: são lidas só para migrar para o Follow-up
REC_QTD_V = "Qtd recebida"
REC_OBS_V = "Observação do recebimento"
OS_DATA_V = "Data de necessidade (manual)"
OS_LIB_V = "Liberada para a equipe em"
LEGADO = {
    "Recebimento": ([COL_CHAVE], [REC_MARCA, REC_QTD_V, REC_DATA, REC_LOCAL, REC_OBS_V]),
    "Por OS": (["OS SAP"], [OS_DATA_V, OS_LIB_V, COL_OBS]),
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
P_CAB = PatternFill("solid", fgColor="1F3864")
P_CAB_ED = PatternFill("solid", fgColor="FFD966")  # cabeçalho de coluna editável
P_EDITAVEL = PatternFill("solid", fgColor="FFF2CC")
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
    ("FALTA EM ESTOQUE", "F8CBAD", "833C0B"),
    ("A CAMINHO", "FFE699", "7F6000"),
    ("PARCIAL", "FFD8A8", "843C0C"),
    ("NÃO RECEBIDO", "F4B6B6", "7F0000"),
    ("RECEBIDO", "C6EFCE", "006100"),
]
CORES_MARCA = [("SIM", "C6EFCE", "006100"), ("PARCIAL", "FFD8A8", "843C0C"), ("NÃO", "F4B6B6", "7F0000")]
CORES_APTA = [
    ("FALTANDO", "FF0000", "FFFFFF"),
    ("RETIRADO", "E2EFDA", "375623"),
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
    ("so_preventivas", "SO_PREVENTIVAS", "Abas de trabalho só com OS preventivas? (SIM / NÃO)", "SIM",
     "SIM = Por OS, Recebimento e Follow-up mostram só OS preventivas; as demais ficam na aba Outras OS. "
     "Mude para NÃO para ver todas. Vale a partir da próxima atualização."),
]

DESCR_STATUS = {
    1: "Data de necessidade já passou e o material não está disponível.",
    2: "Requisição pendente há mais de X dias (X do nível atual).",
    3: "Compra autorizada há mais de Y dias e ainda sem pedido.",
    4: "Pedido emitido e faltam Z dias ou menos para a necessidade.",
    5: "Tem data de necessidade e está dentro dos limites.",
    6: "Material disponível: marcado SIM em 'Recebido?' no Follow-up ou com entrada no TracOS/SAP.",
    7: "Sem data de necessidade: o TracOS só informa a data quando o item entra no fluxo de compras. "
       "Digite a data da OS no Follow-up (coluna 'Data de necessidade da OS').",
}

# ------------------------------------------------------------------ colunas das abas
# (cabeçalho, largura, chave interna). Chaves 'f_' = fórmula; 'm_' = digitada por você.
COLS_FU = [
    ("Status de risco", 26, "f_status"), ("Item disponível?", 10, "f_disp"), ("OS SAP", 12, "os_sap"),
    ("Pedido SAP", 12, "pedido_sap"), ("Descrição da OS", 34, "descricao_os"), ("Código material", 10, "codigo"),
    ("Descrição do material", 34, "descricao"), ("Qtd", 6, "qtd"),
    ("Data de necessidade", 12, "f_nec"), ("Dias até a necessidade", 12, "f_dias_nec"),
    ("Etapa do funil", 30, "etapa_txt"), ("Quem cobrar", 38, "f_quem"),
    # o que você preenche: por item ...
    (REC_MARCA, 10, "m_rec"), (REC_DATA, 12, "m_data"), (REC_LOCAL, 16, "m_local"), (COL_OBS, 36, "m_obs"),
    # ... e por OS (na 1ª linha da OS)
    (OS_DATA, 12, "m_osdata"), (OS_LIB, 13, "m_oslib"),
    # detalhes (recolhidos: clique no + acima das colunas para abrir)
    ("Prioridade", 8, "f_prio"), ("Un", 5, "unidade"), ("Preventiva", 9, "prev"), ("Origem da OS", 11, "origem_os"),
    ("Ativo", 36, "ativo"), ("Dias de atraso", 9, "f_atraso"), ("Dias na etapa atual", 10, "f_dias_etapa"),
    ("Req. SAP", 12, "req_sap"), ("Fornecedor", 36, "fornecedor"),
    ("Valor do item (R$)", 14, "f_valor"), ("Etapa nº", 7, "etapa"), ("OS TracOS", 9, "os_tracos"),
    ("Qtd pendente", 9, "qtd_pendente"), ("Origem da data de necessidade", 26, "f_origem"),
    ("Data de necessidade (TracOS/SAP)", 12, "data_nec_tracos"), ("Data digitada para a OS", 12, "f_nec_manual"),
    ("Início da etapa", 12, "inicio_etapa"), ("Base do início da etapa", 30, "base_inicio"),
    ("Requisição (TracOS)", 10, "requisicao_txt"), ("Nível de liberação", 22, "nivel_liberacao"),
    ("Pedido (TracOS)", 8, "pedido"), ("Status do pedido", 15, "status_pedido"),
    ("Preço unitário (R$)", 13, "preco"), ("Origem do preço", 17, "origem_preco"),
    ("Entrada", 8, "entrada"), ("Data da entrada", 12, "entrada_em"), ("Nota fiscal", 11, "nota_fiscal"),
    ("Local de estoque", 20, "local_estoque"), ("Centro de custo", 28, "centro_custo"),
    ("Grupo de compradores", 30, "grupo_compradores"), ("Plano", 8, "plano"),
    ("Confiança do vínculo", 44, "confianca"), ("Linhas de origem", 24, "origens"),
    ("Categoria SAP (N compra / L estoque)", 10, "categoria"), ("Disponibilidade no SAP (IWBK)", 44, "disponibilidade"),
    ("Qtd retirada (SAP)", 9, "qtd_retirada"), ("Data de remessa do pedido (SAP)", 12, "data_remessa"),
    ("Reserva SAP", 12, "reserva"), ("Fonte do item (técnico)", 12, "origem"), (COL_CHAVE, 24, "chave"),
    ("Faixa (auxiliar)", 6, "faixa"),
]
DETALHE_FU = {k for _, _, k in COLS_FU[COLS_FU.index(("Prioridade", 8, "f_prio")):]}
# as outras abas só mostram o que foi digitado no Follow-up (cabeçalhos diferentes dos do Follow-up de propósito)
COLS_REC = [
    ("Situação", 28, "f_sit"), ("Recebido? (Follow-up)", 12, "f_marcar"), ("Pedido SAP", 12, "pedido_sap"),
    ("OS SAP", 12, "os_sap"), ("Fornecedor", 32, "fornecedor"), ("Descrição do material", 34, "descricao"),
    ("Qtd pedida", 8, "qtd"), ("Data de necessidade", 12, "f_nec"), ("Dias até a necessidade", 12, "f_dias"),
    ("Itens que faltam na OS", 10, "f_falta_os"), ("Data receb. (Follow-up)", 12, "f_data_rec"),
    ("Local / kit (Follow-up)", 16, "f_local"),
    # detalhes (recolhidos)
    ("Código material", 10, "codigo"), ("Un", 5, "unidade"), ("Preventiva", 9, "prev"),
    ("Descrição da OS", 40, "descricao_os"), ("Data da entrada (TracOS)", 12, "entrada_em"),
    ("OS TracOS", 9, "os_tracos"), ("Origem da OS", 10, "origem_os"), ("Etapa nº", 7, "etapa"), ("Ativo", 34, "ativo"),
    ("Pedido (TracOS)", 8, "pedido"), ("Status do pedido (TracOS/SAP)", 15, "status_pedido"),
    ("Entrada registrada (TracOS/SAP)?", 11, "rec_tracos"), ("Entrada", 8, "entrada"),
    ("Nota fiscal", 11, "nota_fiscal"), (COL_CHAVE, 24, "chave"),
    ("Marca (auxiliar)", 8, "f_marca"), ("Faixa (auxiliar)", 6, "faixa"),
]
DETALHE_REC = {k for _, _, k in COLS_REC[COLS_REC.index(("Código material", 10, "codigo")):]}
COLS_OS = [
    ("OS SAP", 12, "os_sap"), ("Descrição da OS", 38, "descricao_os"), ("Ativo", 28, "ativo"),
    ("APTA PARA PROGRAMAR?", 27, "f_apta"), ("Itens que faltam", 50, "f_lista"), ("Pedidos SAP da OS", 24, "pedidos_sap"),
    ("Data de necessidade (usada)", 12, "f_data"), ("Dias até a necessidade", 12, "f_dias"),
    ("Total de itens", 8, "f_total"), ("Itens faltando", 9, "f_falt"), ("✎ Preencher", 14, "f_ir"),
    ("Liberada em (Follow-up)", 12, "f_lib"), ("Observações dos itens (Follow-up)", 40, "f_obs"),
    # detalhes (recolhidos)
    ("Preventiva", 9, "prev"), ("Itens disponíveis", 9, "f_disp"), ("A caminho (com pedido)", 9, "f_caminho"),
    ("Em compra / aprovação", 10, "f_compra"), ("Falta em estoque (SAP)", 9, "f_estoque"),
    ("Itens em risco 🔴", 9, "f_risco"), ("Lista de itens", 30, "lista_ok"),
    ("OS TracOS", 9, "os_tracos"), ("Itens já retirados (SAP)", 9, "retirados"),
    ("Valor pendente (R$)", 14, "f_valor"), ("Data digitada (Follow-up)", 11, "f_mdata"),
    ("Data de necessidade (TracOS/SAP)", 12, "data_tracos"),
    ("Origem da OS", 13, "origem_itens"), ("Situação das peças (na geração)", 34, "situacao"),
    ("Plano", 8, "plano"), ("Centro de custo", 26, "centro_custo"),
    # auxiliares do Painel (ocultas)
    ("Grupo (painel)", 12, "f_grupo"), ("Janela (painel)", 10, "f_janela"), ("Nº apta (painel)", 8, "f_seq"),
]
DETALHE_OS = {k for _, _, k in COLS_OS[COLS_OS.index(("Preventiva", 9, "prev")):]} - {"f_grupo", "f_janela", "f_seq"}
COLS_HIST = [
    ("OS SAP", 12, "os_sap"), ("OS TracOS", 9, "os_tracos"), ("Descrição da OS", 40, "descricao_os"),
    ("Preventiva", 9, "prev"), ("Código material", 10, "codigo"), ("Descrição do material", 36, "descricao"),
    ("Qtd necessária", 9, "qtd"), ("Qtd retirada", 9, "qtd_retirada"), ("Un", 5, "unidade"),
    ("Data de necessidade", 12, "data_nec_tracos"), ("Situação", 30, "etapa_txt"),
    ("Disponibilidade no SAP (IWBK)", 44, "disponibilidade"), ("Reserva SAP", 12, "reserva"),
    ("RC SAP", 11, "req_sap"), ("Pedido SAP", 12, "pedido_sap"), ("Linha na IWBK", 9, "orig_sap"),
    (COL_CHAVE, 24, "chave"),
]
COLS_OUTRAS = [
    ("OS SAP", 12, "os_sap"), ("OS TracOS", 9, "os_tracos"), ("Descrição da OS", 40, "descricao_os"),
    ("Origem da OS", 11, "origem_os"), ("Código material", 10, "codigo"), ("Descrição do material", 36, "descricao"),
    ("Qtd", 7, "qtd"), ("Un", 5, "unidade"), ("Data de necessidade", 12, "data_necessidade"),
    ("Status (na geração)", 28, "status"), ("Etapa do funil", 36, "etapa_txt"), ("Req. SAP", 12, "req_sap"),
    ("Pedido SAP", 12, "pedido_sap"), ("Fornecedor", 34, "fornecedor"), ("Linhas de origem", 24, "origens"),
    (COL_CHAVE, 24, "chave"),
]
COLS_FORN = [
    ("Fornecedor", 38, "fornecedor"), ("✉ Cobrar", 20, "f_mail"), ("Pedidos SAP (TracOS)", 48, "pedidos"),
    ("OS SAP afetadas", 26, "os_afetadas"), ("Pedidos abertos", 9, "n_pedidos"),
    ("Itens em aberto no TracOS", 9, "itens_abertos"),
    ("Itens a receber (follow-up)", 10, "f_receber"), ("Itens com necessidade vencida", 11, "f_vencidos"),
    ("Atraso mais antigo (dias)", 10, "f_atraso"), ("Valor em aberto (R$)", 14, "valor_aberto"),
    ("Pedido mais antigo (emissão)", 13, "pedido_mais_antigo"), ("Dias desde a emissão", 10, "f_dias"),
    ("E-mail (cadastro em Parâmetros)", 30, "f_email"), ("Itens sem OS identificada", 10, "itens_sem_os"),
    ("Link do e-mail (auxiliar)", 10, "f_url"),
]
OCULTAS = {"f_grupo", "f_janela", "f_seq", "f_url", "f_marca", "faixa"}
P_FAIXA = PatternFill("solid", fgColor="EDF2F9", bgColor="EDF2F9")
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
    ws.row_dimensions[linha].height = 42


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
        formula=[f'OR(LEFT({canto},1)="(",LEFT({canto},1)="—",LEFT({canto},7)="Nenhuma")'],
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


def faixas_alternadas(ws, colunas, ult):
    """Fundo alternado por bloco (OS no Follow-up, pedido no Recebimento) usando a coluna auxiliar 'faixa'."""
    c = letras(colunas)
    vis = [j for j, (_, _, k) in enumerate(colunas, 1) if not k.startswith("m_") and k not in OCULTAS]
    blocos, ini = [], None
    for a, b in zip(vis, vis[1:] + [None]):
        ini = a if ini is None else ini
        if b != a + 1:
            blocos.append(f"{get_column_letter(ini)}{LIN_1}:{get_column_letter(a)}{ult}")
            ini = None
    ws.conditional_formatting.add(" ".join(blocos), FormulaRule(formula=[f"${c['faixa']}{LIN_1}=1"], fill=P_FAIXA))


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


def _anotacoes_vazias():
    """item: {chave: {campo: valor}}; os: {OS SAP: {campo: valor}}; forn: {fornecedor: e-mail};
    nota_os / nota_div / nota_forn: observações das versões antigas (Por OS, Divergências, Por Fornecedor),
    que vão para a observação de um item do Follow-up quando ele existe."""
    return dict(item={}, os={}, forn={}, nota_os={}, nota_div={}, nota_forn={})


def _juntar(a, b):
    """Acrescenta o texto b à observação a, sem repetir."""
    a, b = ("" if _vazio(a) else str(a).strip()), ("" if _vazio(b) else str(b).strip())
    if not b or b in a:
        return a or None
    return f"{a} | {b}" if a else b


def _maior(a, b):
    """Valor de um campo por OS digitado em mais de uma linha: vale a maior data."""
    if _vazio(a):
        return b
    if _vazio(b):
        return a
    da, db = _data(a), _data(b)
    if da is None or db is None:
        return a if db is None else b
    return a if da >= db else b


def guardar(man, aba, chave, col, v):
    """Põe uma anotação lida (da aba atual, de uma aba antiga ou de _anotacoes) no lugar dela."""
    if _vazio(v) or chave in (None, "None", ""):
        return
    if aba in ("Follow-up", "Recebimento"):
        d = man["item"].setdefault(chave, {})
        if col in (REC_MARCA, REC_DATA, REC_LOCAL):
            d.setdefault(col, v)  # o Follow-up (lido primeiro) manda sobre a aba Recebimento antiga
        elif col == COL_OBS:
            d[COL_OBS] = _juntar(d.get(COL_OBS), v)
        elif col == REC_QTD_V:
            d[COL_OBS] = _juntar(d.get(COL_OBS), f"Qtd recebida: {_k(v)}")
        elif col == REC_OBS_V:
            d[COL_OBS] = _juntar(d.get(COL_OBS), f"Recebimento: {v}")
    elif aba in ("OS", "Por OS"):
        col = {OS_DATA_V: OS_DATA, OS_LIB_V: OS_LIB}.get(col, col)
        if col in CAMPOS_OS:
            d = man["os"].setdefault(chave, {})
            d[col] = _maior(d.get(col), v)
        elif col == COL_OBS:
            man["nota_os"][chave] = _juntar(man["nota_os"].get(chave), v)
    elif aba in ("Fornecedor", "Por Fornecedor"):
        if col == FORN_EMAIL:
            man["forn"].setdefault(chave, str(v).strip())
        elif col == COL_OBS:
            man["nota_forn"][chave] = _juntar(man["nota_forn"].get(chave), v)
    elif aba == "Divergências" and col == COL_OBS:
        man["nota_div"][chave] = _juntar(man["nota_div"].get(chave), v)


def ler_versao_anterior(pasta_saida):
    vazio = dict(arquivo=None, manuais=_anotacoes_vazias(), historico={}, prm={}, migrou=False, arquivos={})
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
    man = _anotacoes_vazias()
    # 1) Follow-up: onde tudo é digitado (nas versões antigas, só a observação)
    novo_formato = False
    if "Follow-up" in wb.sheetnames:
        for d in _tabela(wb["Follow-up"], [COL_CHAVE]):
            novo_formato = novo_formato or REC_MARCA in d
            ch = _k(d.get(COL_CHAVE))
            for c in CAMPOS_ITEM:
                guardar(man, "Follow-up", ch, c, d.get(c))
            os_ = d.get("OS SAP")
            if not _vazio(os_):
                for c in CAMPOS_OS:
                    guardar(man, "OS", _k(os_), c, d.get(c))
    # 2) versões antigas: Recebimento, Por OS, Por Fornecedor e Divergências tinham colunas digitadas
    if not novo_formato:
        for aba, (ks, cols) in LEGADO.items():
            if aba not in wb.sheetnames:
                continue
            for d in _tabela(wb[aba], ks):
                if aba == "Divergências" and d.get("Tipo") in (TIPO_ORFA, TIPO_ORFA_V1):
                    if d.get("Tipo") == TIPO_ORFA_V1 and d.get("Base") in ("Follow-up", "Recebimento", "Por OS",
                                                                          "Por Fornecedor"):  # 1ª versão
                        guardar(man, d["Base"], _k(d.get(COL_CHAVE)), COL_OBS, d.get(COL_OBS))
                    continue
                chave = "|".join(_k(d.get(x)) for x in ks)
                for c in cols:
                    guardar(man, aba, chave, c, d.get(c))
    # 3) anotações guardadas porque o item/OS tinha sumido das bases
    if "_anotacoes" in wb.sheetnames:
        for d in _tabela(wb["_anotacoes"], ["Aba", "Chave", "Coluna", "Valor"]):
            guardar(man, d.get("Aba"), _k(d.get("Chave")), d.get("Coluna"), d.get("Valor"))
    # 4) cadastro de e-mails dos fornecedores (aba Parâmetros) e parâmetros
    prm, nomes_usados = {}, {}
    if "Parâmetros" in wb.sheetnames:
        ids = {p[0] for p in PARAMETROS}
        for row in wb["Parâmetros"].iter_rows(min_row=1, values_only=True):
            if not row or len(row) < 4:
                continue
            if isinstance(row[0], str) and row[0].startswith("Arquivo de ") and row[1]:
                nomes_usados[row[0][len("Arquivo de "):]] = {"nomes": {str(row[1])}}
            elif row[3] == ID_FORN:
                guardar(man, "Fornecedor", _k(row[0]), FORN_EMAIL, row[1])
            elif row[3] in ids and row[3] != "data_ref":
                v = row[1]
                if row[3].startswith(("nome_", "email_", "so_")):
                    prm[row[3]] = "" if v is None else str(v)
                elif isinstance(v, (int, float)):
                    prm[row[3]] = v
    # arquivos que estavam na pasta bases na última atualização (planilhas antigas: só o nome do usado)
    arquivos = {}
    if "_arquivos" in wb.sheetnames:
        for d in _tabela(wb["_arquivos"], ["Base", "Arquivo", "MD5"]):
            if d.get("Base") and d.get("MD5"):
                arquivos.setdefault(d["Base"], {"md5": set()})["md5"].add(str(d["MD5"]))
    else:
        arquivos = nomes_usados
    hist = {}
    if "_historico" in wb.sheetnames:
        for d in _tabela(wb["_historico"], ["Chave", "Etapa", "Desde"]):
            if d.get("Chave") and d.get("Etapa") and d.get("Desde"):
                hist[str(d["Chave"])] = (int(d["Etapa"]), pd.Timestamp(d["Desde"]))
    wb.close()
    return dict(arquivo=ant, manuais=man, historico=hist, prm=prm, migrou=not novo_formato, arquivos=arquivos)


def migrar_chaves_os(man, B):
    """Versões antigas guardavam anotações por nº da OS no TracOS; agora a chave é o nº SAP."""
    mapa = {}
    for nome in ("requisicao", "fluxo"):
        for t, s_ in B[nome]["norm"][["os_tracos", "os_sap"]].dropna().itertuples(index=False):
            mapa[str(int(t))] = str(s_)
    for parte in ("os", "nota_os"):
        novo = {}
        for k, d in man[parte].items():
            k2 = mapa.get(k, k) if len(k) < 8 else k
            if parte == "os":
                alvo = novo.setdefault(k2, {})
                for c, v in d.items():
                    alvo[c] = _maior(alvo.get(c), v)
            else:
                novo[k2] = _juntar(novo.get(k2), d)
        man[parte] = novo


def distribuir_notas(man, L):
    """Observações antigas por OS e de Divergências vão para a observação de um item do Follow-up
    (a 1ª linha da OS / o item apontado). O que não tiver lugar fica como anotação sem item."""
    primeira = {}
    for ch, o in zip(L["chave"], L["os_sap"]):
        if not pd.isna(o):
            primeira.setdefault(str(o), ch)
    chaves = set(L["chave"])
    for os_, v in list(man["nota_os"].items()):
        if os_ in primeira:
            d = man["item"].setdefault(primeira[os_], {})
            d[COL_OBS] = _juntar(d.get(COL_OBS), f"OS: {v}")
            del man["nota_os"][os_]
    for k, v in list(man["nota_div"].items()):
        tipo, _, ch = k.partition("|")
        if ch in chaves:
            d = man["item"].setdefault(ch, {})
            d[COL_OBS] = _juntar(d.get(COL_OBS), f"Divergência ({tipo.split(' –')[0].strip()}): {v}")
            del man["nota_div"][k]


def manuais_para_cruzamento(man):
    datas, lib = {}, set()
    for k, d in man["os"].items():
        dd = _data(d.get(OS_DATA))
        if dd is not None:
            datas[str(k)] = dd
        if not _vazio(d.get(OS_LIB)):
            lib.add(str(k))
    rec = {k: d.get(REC_MARCA) for k, d in man["item"].items() if not _vazio(d.get(REC_MARCA))}
    return {"datas_os": datas, "liberadas": lib, "recebimento": rec}


def anotacoes_sem_lugar(man, R):
    """Anotações cujo item/OS sumiu das bases: guardadas na aba oculta _anotacoes (voltam quando o item
    reaparecer) e listadas em Divergências."""
    L = R["linhas"]
    chaves = set(L["chave"])
    oss = {str(o) for o in L["os_sap"].dropna()}
    grupos = [("Follow-up", {k: d for k, d in man["item"].items() if k not in chaves}),
              ("OS", {k: d for k, d in man["os"].items() if k not in oss}),
              ("OS", {k: {COL_OBS: v} for k, v in man["nota_os"].items()}),
              ("Divergências", {k: {COL_OBS: v} for k, v in man["nota_div"].items()}),
              ("Fornecedor", {k: {COL_OBS: v} for k, v in man["nota_forn"].items()})]
    orfas, regs = [], []
    for aba, itens in grupos:
        for k, cols in itens.items():
            cols = {c: v for c, v in cols.items() if not _vazio(v)}
            if not cols:
                continue
            for col, v in cols.items():
                regs.append([aba, k, col, v])
            orfas.append(dict(tipo=TIPO_ORFA, gravidade="Info", base=aba, linha=None, chave=f"{aba}:{k}",
                              no_followup="NÃO",
                              detalhe=" | ".join(f"{col}: {v:%d/%m/%Y}" if isinstance(v, dt.datetime) else
                                                 f"{col}: {v}" for col, v in cols.items())))
    return orfas, regs


# ------------------------------------------------------------------ abas
def aba_parametros(wb, prm, B, R, data_fixa, info_ant, forn_emails):
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
        if pid == "so_preventivas":
            dv = DataValidation(type="list", formula1='"SIM,NÃO"', allow_blank=False)
            dv.add(f"B{lin}")
            ws.add_data_validation(dv)
        nome_definido(wb, nome, f"'Parâmetros'!$B${lin}")
    ws.column_dimensions["D"].hidden = True
    lin = LIN_1 + len(PARAMETROS) + 1

    # cadastro de e-mails dos fornecedores (botão ✉ Cobrar); fica salvo mesmo sem pedido aberto
    lin += 1
    cel(ws, (lin, 1), "E-mails dos fornecedores (botão ✉ Cobrar)", F_SECAO)
    cel(ws, (lin, 3), "Cadastre uma vez: o e-mail fica salvo nas próximas atualizações. Vários e-mails: separe "
                      "com ';'.", F_NOTA)
    lin += 1
    for j, t in enumerate(["Fornecedor", FORN_EMAIL, "Pedidos abertos nesta atualização"], 1):
        cel(ws, (lin, j), t, F_CAB_ED if j == 2 else F_CAB, preench=P_CAB_ED if j == 2 else P_CAB, alin=AL_CAB)
    lin += 1
    pf = R["por_fornecedor"]
    abertos = dict(zip(pf["fornecedor"], pf["n_pedidos"])) if len(pf) else {}
    forns = sorted(set(abertos) | set(forn_emails), key=lambda x: _ascii(x).upper())
    ini_forn = lin
    for fo in forns or [None]:
        cel(ws, (lin, 1), fo, F_NORMAL)
        cel(ws, (lin, 2), forn_emails.get(fo), F_NORMAL, preench=P_EDITAVEL)
        n = abertos.get(fo, 0)
        cel(ws, (lin, 3), f"{n} pedido{'s' if n != 1 else ''} aberto{'s' if n != 1 else ''}" if n else
            "sem pedido aberto agora", F_NOTA)
        cel(ws, (lin, 4), ID_FORN, F_NOTA)
        lin += 1
    nome_definido(wb, "FORN_NOMES", f"'Parâmetros'!$A${ini_forn}:$A${lin - 1}")
    nome_definido(wb, "FORN_EMAILS", f"'Parâmetros'!$B${ini_forn}:$B${lin - 1}")

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

    secao("Gestão dos materiais – o que você preenche (tudo na aba Follow-up)")
    linhas_texto([
        ("Recebido?", "SIM = o material chegou e está separado para a OS. PARCIAL = chegou só parte (não libera a "
         "OS). NÃO = não chegou, mesmo que o TracOS mostre entrada. Em branco = vale a entrada registrada no "
         "TracOS/SAP. Data do recebimento e Local / kit são opcionais."),
        (OS_DATA, "Na 1ª linha de cada OS (célula amarela). Data em que a OS precisa das peças (ex.: data "
         "programada). Vale para todos os itens da OS e manda sobre a data do TracOS/SAP."),
        (OS_LIB, "Na 1ª linha da OS. Data em que você passou a OS para os colaboradores. Se faltar item, a OS "
         "aparece em vermelho: ⚠ LIBERADA FALTANDO."),
        (COL_OBS, "Anotação livre do item: cobrança, previsão de entrega, o que foi combinado."),
        ("Outras abas", "Recebimento, Por OS, Por Fornecedor e Divergências só mostram: o que você digita no "
         "Follow-up aparece nelas na hora. '✎ marcar' e '✎ Preencher' levam à linha certa do Follow-up."),
        ("Links e botões", "Textos e números do Painel levam direto aos itens. ✉ Cobrar abre o e-mail pronto: "
         "cadastre aqui os e-mails do gestor, do almox e dos fornecedores. Em cada aba, '⬅ Voltar ao Painel' "
         "fica na célula A1."),
        ("APTA PARA PROGRAMAR", "Só quando TODOS os itens da OS estão disponíveis. Item disponível = marcado SIM "
         "em Recebido? ou com entrada no TracOS/SAP (sem marca PARCIAL/NÃO)."),
    ])

    secao("Regras fixas (no script)")
    linhas_texto([
        ("Preventiva", "OS com 'PREV' na descrição, com nº de plano de manutenção ou com descrição iniciada por "
         "'MSI_' (manutenção sistemática)."),
        ("Data de necessidade", "1º a data digitada para a OS (Follow-up); 2º a do item no fluxo do TracOS ou na IWBK do "
         "SAP; 3º a de outro item da mesma OS. A base de requisição do TracOS não traz data."),
        ("IWBK (SAP) – opcional", "Arquivo '*IWBK*.xlsx' na pasta bases. Casa com o TracOS por OS + material + RC, "
         "OS + material + pedido, OS + material, material + RC e material + pedido. O que não casar entra como "
         "item 'SAP': estoque (L) em falta = etapa 0; RC não liberada = 1; RC liberada sem pedido = 3; com pedido = 4; "
         "entrada, retirada ou disponível em estoque = 5. A IWBK não traz fornecedor."),
        ("Material já retirado (SAP)", "Itens já retirados/baixados para a ordem vão para a aba Histórico SAP e saem "
         "do Follow-up, do Recebimento e da Por OS (contam como disponíveis no total da OS). OS com todo o material "
         "retirado aparecem no Painel como ✔ MATERIAL JÁ RETIRADO (SAP)."),
        ("Preço do item", "Entrada > negociado > estimado (R$ 1,00 do TracOS é ignorado como 'sem preço') > "
         "preço do mesmo material em outra linha do fluxo ('ref.')."),
        ("Valor do item", "Quantidade × preço unitário. A requisição e o pedido não trazem preço por item: "
         "itens sem preço ficam sem valor."),
        ("Dias na etapa", "Etapas 1/2: 'Criado em' da requisição (no nível 02, a partir da 1ª vez que o script "
         "viu o item no nível 02). Etapa 3: 1ª vez que o script viu o item autorizado. "
         "Etapa 4: 'Criado em' do pedido. Etapa 5: data da entrada."),
        ("Chave das anotações", "Item: material | requisição | OS (+ sequencial quando o trio se repete). "
         "OS: nº SAP. Se o item sumir das bases, a anotação vai para Divergências e volta quando ele "
         "reaparecer."),
    ])

    secao("Legenda – status de risco (em ordem de prioridade)")
    for p_, txt in cz.STATUS.items():
        fundo, letra = next((f, l) for w, f, l in CORES_STATUS if w in txt)
        cel(ws, (lin, 1), txt, Font(name=FONTE, bold=True, color=letra), preench=PatternFill("solid", fgColor=fundo))
        cel(ws, (lin, 2), f"Prioridade {p_}", F_NORMAL)
        cel(ws, (lin, 3), DESCR_STATUS[p_], F_NORMAL)
        lin += 1

    secao("Legenda – situação no Recebimento")
    descr_rec = {6: "Componente de estoque (SAP) em falta: aguarda reposição do almoxarifado.",
                 0: "Tem pedido, não chegou e a data de necessidade já passou.",
                 1: "Tem pedido e ainda não chegou.", 2: "Você marcou PARCIAL no Follow-up: não libera a OS.",
                 3: "Você marcou NÃO no Follow-up.", 4: "Você marcou SIM no Follow-up.",
                 5: "Entrada registrada no TracOS ou no SAP (sem marca sua)."}
    for k, txt in cz.SITUACAO_REC.items():
        fundo, letra = next((f, l) for w, f, l in CORES_REC if w in txt)
        cel(ws, (lin, 1), txt, Font(name=FONTE, bold=True, color=letra), preench=PatternFill("solid", fgColor=fundo))
        cel(ws, (lin, 2), descr_rec[k], F_NORMAL)
        lin += 1

    secao("Legenda – etapas do funil")
    quem = {0: "Almoxarifado (reposição do estoque)", 1: "Gestor da unidade / aprovador da RC no SAP",
            2: "Almox corporativo", 3: "Comprador", 4: "Fornecedor (ou comprador, se o pedido for só do SAP)",
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
        "S1": "IWBK ↔ TracOS pela OS SAP + material + nº da RC SAP.",
        "S2": "IWBK ↔ TracOS pela OS SAP + material + nº do pedido SAP.",
        "S3": "IWBK ↔ TracOS pela OS SAP + material.",
        "S4": "IWBK ↔ TracOS pelo material + nº da RC SAP.",
        "S5": "IWBK ↔ TracOS pelo material + nº do pedido SAP.",
        "SO_SAP": "Item de compra que só existe no SAP (RC/pedido criado direto no SAP).",
        "SO_SAP_L": "Componente de estoque reservado para a ordem no SAP (o TracOS não mostra).",
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
    lin_arquivos = lin
    for nome in ("requisicao", "fluxo", "pedido", "iwbk"):
        if not B.get(nome):
            continue
        arq = B[nome]["arquivo"]
        outros = [os.path.basename(c) for c in B[nome]["candidatos"] if c != arq]
        cel(ws, (lin, 1), f"Arquivo de {nome}", F_NEGRITO)
        cel(ws, (lin, 2), os.path.basename(arq))
        cel(ws, (lin, 3), f"{len(B[nome]['bruto'])} linhas – modificado em "
                          f"{dt.datetime.fromtimestamp(os.path.getmtime(arq)):%d/%m/%Y %H:%M} – {B[nome]['motivo']}"
                          + (f". Também na pasta: {', '.join(outros)}"
                             + (" (movidos para bases/antigos)" if B[nome]["substituidos"] else "") if outros else ""))
        lin += 1
    lin += 1
    cel(ws, (lin, 1), "Conciliação (linhas de entrada × saída)", F_SECAO)
    lin += 1
    for j, t in enumerate(["Base", "Linhas de entrada", "No Follow-up", "Histórico SAP (já retirado)",
                           "Outras OS (não preventivas)", "Divergências (não casadas)", "OK?"], 1):
        cel(ws, (lin, j), t, F_CAB, preench=P_CAB, alin=AL_CAB)
    for col in "EFG":
        ws.column_dimensions[col].width = 12
    lin += 1
    for _, c in R["conciliacao"].iterrows():
        for j, v in enumerate([c["base"], c["entrada"], c["follow_up"], c["historico"], c["outras"],
                               c["divergencias"], "SIM" if c["ok"] else "NÃO"], 1):
            cel(ws, (lin, j), v)
        lin += 1
    lin += 1
    cel(ws, (lin, 1), "Avisos sobre as bases", F_SECAO)
    lin_avisos = lin + 1
    for a in R["alertas"]:
        lin += 1
        cel(ws, (lin, 1), "⚠ " + a, F_ALERTA)
    return lin_avisos, ini_forn, lin_arquivos


def escrever_tabela(ws, colunas, registros, valor_de, fmts, centro, negrito=(), links=(), detalhe=()):
    """Escreve as linhas de uma tabela. valor_de(k, registro, linha) devolve o valor/fórmula da célula.
    Colunas em 'detalhe' ficam agrupadas e recolhidas (botão + do Excel para abrir)."""
    for j, (_, _, k) in enumerate(colunas, 1):
        dim = ws.column_dimensions[get_column_letter(j)]
        if k in OCULTAS:
            dim.hidden = True
        elif k in detalhe:
            dim.outline_level = 1
            dim.hidden = True
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


def aba_followup(wb, L, man, FU, POS):
    ws = wb.create_sheet("Follow-up")
    ws.sheet_properties.tabColor = "548235"
    titulo(ws, "Follow-up de peças por OS – é aqui que você preenche",
           "Itens agrupados por OS (faixas de cor), as mais urgentes primeiro. Colunas amarelas = o que você "
           "preenche: recebimento e observação em cada item; data de necessidade e liberação da OS na 1ª linha "
           "da OS. As outras abas e o Painel se atualizam na hora. Colunas técnicas: clique no + acima das colunas.")
    cabecalho(ws, LIN_CAB, COLS_FU)
    c = letras(COLS_FU)
    # rótulos dos dois grupos de colunas amarelas, acima do cabeçalho
    for k1, k2, txt in (("m_rec", "m_obs", "✎ VOCÊ PREENCHE – ITEM"), ("m_osdata", "m_oslib", "✎ OS (1ª linha da OS)")):
        ws.merge_cells(f"{c[k1]}{LIN_CAB - 1}:{c[k2]}{LIN_CAB - 1}")
        cel(ws, f"{c[k1]}{LIN_CAB - 1}", txt, F_CAB_ED, preench=P_CAB_ED, alin=AL_CAB)
    E, N, DN, DE, I, Q, PR, FO, PS, P, D, M, NM, NT, OS = (c[k] for k in (
        "etapa", "f_nec", "f_dias_nec", "f_dias_etapa", "inicio_etapa", "qtd", "preco", "fornecedor",
        "pedido_sap", "f_prio", "f_disp", "m_rec", "f_nec_manual", "data_nec_tracos", "os_sap"))
    status_txt = ",".join(f'"{cz.STATUS[i]}"' for i in range(1, 8))
    marca = f"UPPER(TRIM({M}{{r}}))"
    f = {
        "f_prio": (f'=IF({D}{{r}}="SIM",6,IF(AND({N}{{r}}<>"",N({DN}{{r}})<0),1,'
                   f'IF(AND({E}{{r}}>=1,{E}{{r}}<=2,N({DE}{{r}})>IF({E}{{r}}=1,X_NIVEL01,X_NIVEL02)),2,'
                   f'IF(AND({E}{{r}}=3,N({DE}{{r}})>Y_SEM_PEDIDO),3,'
                   f'IF(AND(OR({E}{{r}}=4,{E}{{r}}=0),{N}{{r}}<>"",N({DN}{{r}})<=Z_ENTREGA),4,'
                   f'IF({N}{{r}}="",7,5))))))'),
        "f_status": f"=CHOOSE({P}{{r}},{status_txt})",
        "f_disp": (f'=IF({marca}="SIM","SIM",IF(OR({marca}="PARCIAL",{marca}="NÃO"),"NÃO",'
                   f'IF({E}{{r}}=5,"SIM","NÃO")))'),
        "f_quem": (f'=IF({D}{{r}}="SIM","Ninguém – material disponível",IF({E}{{r}}=0,'
                   f'"Almoxarifado – material em falta no estoque (SAP)",CHOOSE({E}{{r}},'
                   f'"Gestor da unidade"&IF(NOME_GESTOR="",""," – "&NOME_GESTOR),'
                   f'"Almox corporativo"&IF(NOME_ALMOX="",""," – "&NOME_ALMOX),'
                   f'"Comprador"&IF(NOME_COMPRADOR="",""," – "&NOME_COMPRADOR)&" (emitir o pedido)",'
                   f'IF({FO}{{r}}="",IF({PS}{{r}}="","Comprador (pedido sem fornecedor)",'
                   f'"Comprador – acompanhar o pedido SAP "&{PS}{{r}}),"Fornecedor: "&{FO}{{r}}'
                   f'&IF({PS}{{r}}="",""," – pedido SAP "&{PS}{{r}})),'
                   f'"Almoxarifado – sistema tem entrada, conferir o físico")))'),
        # data digitada em qualquer linha da OS (a aba Por OS junta as linhas da OS)
        "f_nec_manual": f'=IFERROR(INDEX({POS["f_mdata"]},MATCH({OS}{{r}},{POS["os_sap"]},0)),0)',
        "f_nec": f'=IF(N({NM}{{r}})>0,{NM}{{r}},IF({NT}{{r}}="","",{NT}{{r}}))',
        "f_dias_nec": f'=IF({N}{{r}}="","",{N}{{r}}-INT(DATA_REF))',
        "f_atraso": f'=IF(AND({D}{{r}}<>"SIM",{N}{{r}}<>""),MAX(0,INT(DATA_REF)-{N}{{r}}),0)',
        "f_dias_etapa": f'=IF({I}{{r}}="","",INT(DATA_REF)-INT({I}{{r}}))',
        "f_valor": f'=IF(OR({Q}{{r}}="",{PR}{{r}}=""),"",{Q}{{r}}*{PR}{{r}})',
    }
    campo = {"m_rec": REC_MARCA, "m_data": REC_DATA, "m_local": REC_LOCAL, "m_obs": COL_OBS,
             "m_osdata": OS_DATA, "m_oslib": OS_LIB}
    # campos da OS vão na 1ª linha de cada OS
    primeira = set(L.reset_index(drop=True).dropna(subset=["os_sap"]).drop_duplicates("os_sap").index)
    regs = [l for _, l in L.reset_index(drop=True).iterrows()]

    def valor_de(k, l, r):
        if k in f:
            return f[k].format(r=r)
        if k == "f_origem":
            orig = l["origem_data_tracos"] if isinstance(l["origem_data_tracos"], str) else ""
            return f'=IF(N({NM}{r})>0,"Digitada para a OS","{orig}")'
        if k in ("m_osdata", "m_oslib"):
            if r - LIN_1 not in primeira:
                return None
            v = man["os"].get(str(l["os_sap"]), {}).get(campo[k])
            return _data(v) or v
        if k.startswith("m_"):
            v = man["item"].get(l["chave"], {}).get(campo[k])
            return (_data(v) or v) if k == "m_data" else v
        if k == "prev":
            return "SIM" if l["eh_preventiva"] else "NÃO"
        return l[k]

    fmts = {"f_nec": FMT_DATA, "data_nec_tracos": FMT_DATA, "f_nec_manual": FMT_DATA + ";;", "inicio_etapa": FMT_DATA,
            "data_remessa": FMT_DATA, "m_data": FMT_DATA, "m_osdata": FMT_DATA, "m_oslib": FMT_DATA,
            "entrada_em": FMT_DATA, "preco": FMT_RS, "f_valor": FMT_RS, "f_dias_nec": FMT_DIAS,
            "f_dias_etapa": "0", "f_atraso": FMT_ATRASO}
    centro = {"f_prio", "f_disp", "etapa", "prev", "os_tracos", "codigo", "qtd", "qtd_pendente", "m_rec", "m_data",
              "m_osdata", "m_oslib", "unidade", "f_dias_nec", "f_atraso", "f_dias_etapa", "requisicao_txt", "pedido",
              "entrada"}
    ult = escrever_tabela(ws, COLS_FU, regs, valor_de, fmts, centro, detalhe=DETALHE_FU)
    # campos da OS: amarelos só na 1ª linha da OS (digitar em outra linha da mesma OS também vale)
    for k in ("m_osdata", "m_oslib"):
        for i in range(len(regs)):
            if i not in primeira:
                ws[f"{c[k]}{LIN_1 + i}"].fill = PatternFill()
    ws.freeze_panes = f"{get_column_letter(COLS_FU.index(('Pedido SAP', 12, 'pedido_sap')) + 2)}{LIN_1}"
    cf_palavras(ws, f"{c['f_status']}{LIN_1}:{c['f_status']}{ult}", f"${c['f_status']}{LIN_1}", CORES_STATUS)
    faixas_alternadas(ws, COLS_FU, ult)
    ws.conditional_formatting.add(f"{D}{LIN_1}:{D}{ult}", FormulaRule(
        formula=[f'{D}{LIN_1}="SIM"'], fill=PatternFill("solid", fgColor="C6EFCE", bgColor="C6EFCE"),
        font=Font(name=FONTE, bold=True, color="006100")))
    for col in (DN, c["f_atraso"]):
        ws.conditional_formatting.add(f"{col}{LIN_1}:{col}{ult}", CellIsRule(
            operator="lessThan" if col == DN else "greaterThan", formula=["0"],
            font=Font(name=FONTE, color="9C0006", bold=True)))
    dv = DataValidation(type="list", formula1='"SIM,PARCIAL,NÃO"', allow_blank=True,
                        errorTitle="Recebido?", error="Use SIM, PARCIAL ou NÃO (ou deixe em branco).",
                        promptTitle="Recebido?", prompt="SIM = chegou e está separado para a OS")
    dv.add(f"{M}{LIN_1}:{M}{ult}")
    ws.add_data_validation(dv)
    for k in ("m_data", "m_osdata", "m_oslib"):
        validar_data(ws, f"{c[k]}{LIN_1}:{c[k]}{ult}")
    paisagem(ws, caber_largura=False)


def aba_recebimento(wb, rec, FU, POS):
    ws = wb.create_sheet("Recebimento")
    ws.sheet_properties.tabColor = "70AD47"
    titulo(ws, "Recebimento de materiais – o que está chegando",
           "Agrupado por situação, fornecedor e pedido SAP (como o material chega). Só para consulta: marque o que "
           "chegou na coluna 'Recebido?' do Follow-up – clique em '✎ marcar' para ir direto à linha do item.")
    cabecalho(ws, LIN_CAB, COLS_REC)
    c = letras(COLS_REC)
    MK, P_, Q_, H_, V_, ET, CH = (c[k] for k in ("f_marca", "f_nec", "f_dias", "os_sap", "rec_tracos", "etapa",
                                                  "chave"))
    no_fu = f"MATCH({CH}{{r}},{FU['chave']},0)"

    def do_fu(k):
        """Valor que você digitou no Follow-up para o item (vazio se não digitou)."""
        return f'=IFERROR(IF(INDEX({FU[k]},{no_fu})="","",INDEX({FU[k]},{no_fu})),"")'

    col_fu = letras(COLS_FU)["m_rec"]
    f = {
        "f_marca": f'=IFERROR(UPPER(TRIM(INDEX({FU["m_rec"]},{no_fu})&"")),"")',
        "f_marcar": (f'=IFERROR(HYPERLINK("#\'Follow-up\'!{col_fu}"&({no_fu}+{LIN_CAB}),'
                     f'IF({MK}{{r}}="","✎ marcar",{MK}{{r}})),"— (sem OS)")'),
        "f_data_rec": do_fu("m_data"),
        "f_local": do_fu("m_local"),
        "f_sit": (f'=IF({MK}{{r}}="SIM","{cz.SITUACAO_REC[4]}",IF({MK}{{r}}="PARCIAL","{cz.SITUACAO_REC[2]}",'
                  f'IF({MK}{{r}}="NÃO","{cz.SITUACAO_REC[3]}",IF({V_}{{r}}="SIM","{cz.SITUACAO_REC[5]}",'
                  f'IF({ET}{{r}}=0,"{cz.SITUACAO_REC[6]}",'
                  f'IF(AND({P_}{{r}}<>"",N({Q_}{{r}})<0),"{cz.SITUACAO_REC[0]}","{cz.SITUACAO_REC[1]}"))))))'),
        "f_dias": f'=IF({P_}{{r}}="","",{P_}{{r}}-INT(DATA_REF))',
        "f_falta_os": (f'=IF({H_}{{r}}="","",IFERROR(HYPERLINK("#\'Por OS\'!E"&(MATCH({H_}{{r}},{POS["os_sap"]},0)'
                       f'+{LIN_CAB}),INDEX({POS["f_falt"]},MATCH({H_}{{r}},{POS["os_sap"]},0))),""))'),
        "f_nec": do_fu("f_nec"),
    }

    def valor_de(k, x, r):
        if k in ("f_nec", "f_marcar", "f_data_rec", "f_local", "f_marca") and not x["no_followup"]:
            return "— (sem OS)" if k == "f_marcar" else None
        if k in f:
            return f[k].format(r=r)
        if k == "prev":
            return "SIM" if x["eh_preventiva"] else "NÃO"
        if k == "rec_tracos":
            return "SIM" if x["recebido_tracos"] else "NÃO"
        return x[k]

    fmts = {"f_nec": FMT_DATA, "f_data_rec": FMT_DATA, "entrada_em": FMT_DATA, "f_dias": FMT_DIAS}
    centro = {"f_marcar", "f_data_rec", "f_falta_os", "os_tracos", "os_sap", "etapa", "origem_os", "prev", "codigo",
              "qtd", "unidade", "f_dias", "pedido", "rec_tracos", "entrada"}
    ult = escrever_tabela(ws, COLS_REC, [x for _, x in rec.iterrows()], valor_de, fmts, centro, negrito={"f_sit"},
                          links={"f_falta_os", "f_marcar"}, detalhe=DETALHE_REC)
    ws.freeze_panes = f"{get_column_letter(COLS_REC.index(('OS SAP', 12, 'os_sap')) + 2)}{LIN_1}"
    cf_palavras(ws, f"A{LIN_1}:A{ult}", f"$A{LIN_1}", CORES_REC)
    faixas_alternadas(ws, COLS_REC, ult)
    sem_link(ws, f"{c['f_marcar']}{LIN_1}:{c['f_marcar']}{ult}", f"{c['f_marcar']}{LIN_1}")
    cf_palavras(ws, f"{c['f_marcar']}{LIN_1}:{c['f_marcar']}{ult}", f"${c['f_marcar']}{LIN_1}", CORES_MARCA)
    ws.conditional_formatting.add(f"{c['f_falta_os']}{LIN_1}:{c['f_falta_os']}{ult}", CellIsRule(
        operator="equal", formula=["0"], fill=PatternFill("solid", fgColor="C6EFCE", bgColor="C6EFCE"),
        font=Font(name=FONTE, bold=True, color="006100")))
    paisagem(ws)


def aba_por_os(wb, por_os, FU):
    ws = wb.create_sheet("Por OS")
    ws.sheet_properties.tabColor = "2F75B5"
    titulo(ws, "OS – prontas para programar só com todos os itens disponíveis",
           "Preventivas primeiro; dentro delas, as aptas e depois as que faltam menos itens. Só para consulta: a data "
           "de necessidade e a liberação da OS são digitadas no Follow-up (clique em '✎ Preencher'). "
           "OS com todo o material já retirado no SAP estão na aba Histórico SAP.")
    cabecalho(ws, LIN_CAB, COLS_OS)
    c = letras(COLS_OS)
    A, TOT, DSP, FAL, LIB, MD, FD, DT_, PV, DI, G, RT = (c[k] for k in (
        "os_sap", "f_total", "f_disp", "f_falt", "f_lib", "f_mdata", "f_data", "data_tracos", "prev", "f_dias",
        "f_grupo", "retirados"))
    a = f"${A}{{r}}"
    # maior data digitada nas linhas da OS (fórmula matricial: funciona em qualquer versão do Excel)
    maior = "MAX(IF({os}={a},IF(ISNUMBER({col}),{col},0),0))"
    m_lib = maior.format(col=FU["m_oslib"], os=FU["os_sap"], a=a)
    m_data = maior.format(col=FU["m_osdata"], os=FU["os_sap"], a=a)
    col_fu = letras(COLS_FU)["m_rec"]
    f = {
        "f_apta": (f'=IF({LIB}{{r}}<>"",IF({FAL}{{r}}=0,"▶ LIBERADA PARA A EQUIPE",'
                   f'"⚠ LIBERADA FALTANDO "&{FAL}{{r}}&IF({FAL}{{r}}=1," ITEM"," ITENS")),'
                   f'IF(AND({TOT}{{r}}>0,{FAL}{{r}}=0),'
                   f'"✅ APTA PARA PROGRAMAR","⛔ AGUARDANDO "&{FAL}{{r}}&IF({FAL}{{r}}=1," ITEM"," ITENS")))'),
        # digitado no Follow-up em qualquer linha da OS: vale a maior data (0 = nada digitado;
        # texto em 'liberada' = SIM)
        "f_mdata": f"={m_data}",
        "f_lib": (f'=IF(COUNTIFS({FU["os_sap"]},{a},{FU["m_oslib"]},"<>")=0,"",'
                  f'IF({m_lib}>0,{m_lib},"SIM"))'),
        "f_data": f'=IF(N({MD}{{r}})>0,{MD}{{r}},IF({DT_}{{r}}="","",{DT_}{{r}}))',
        "f_dias": f'=IF({FD}{{r}}="","",{FD}{{r}}-INT(DATA_REF))',
        "f_total": f"=COUNTIFS({FU['os_sap']},{a})+{RT}{{r}}",
        "f_disp": f'=COUNTIFS({FU["os_sap"]},{a},{FU["f_disp"]},"SIM")+{RT}{{r}}',
        "f_falt": f"={TOT}{{r}}-{DSP}{{r}}",
        "f_caminho": f'=COUNTIFS({FU["os_sap"]},{a},{FU["etapa"]},">=4",{FU["f_disp"]},"NÃO")',
        "f_compra": f'=COUNTIFS({FU["os_sap"]},{a},{FU["etapa"]},">=1",{FU["etapa"]},"<=3")',
        "f_estoque": f'=COUNTIFS({FU["os_sap"]},{a},{FU["etapa"]},0,{FU["f_disp"]},"NÃO")',
        "f_risco": f'=COUNTIFS({FU["os_sap"]},{a},{FU["f_prio"]},"<=2")',
        "f_valor": f'=SUMIFS({FU["f_valor"]},{FU["os_sap"]},{a},{FU["f_disp"]},"NÃO")',
        "f_ir": (f'=IFERROR(HYPERLINK("#\'Follow-up\'!{col_fu}"&(MATCH({a},{FU["os_sap"]},0)+{LIN_CAB}),'
                 f'"✎ Preencher"),"")'),
        "f_grupo": (f'=IF({LIB}{{r}}<>"",IF({FAL}{{r}}=0,"LIBERADA","LIBERADA FALTANDO"),'
                    f'IF(AND({TOT}{{r}}>0,{FAL}{{r}}=0),"APTA",IF({FAL}{{r}}=1,"FALTA 1",'
                    f'IF({FAL}{{r}}<=3,"FALTA 2-3","FALTA 4+"))))'),
        "f_janela": (f'=IF(OR({FAL}{{r}}=0,{PV}{{r}}<>"SIM"),"",IF({FD}{{r}}="","SEM DATA",'
                     f'IF({DI}{{r}}<0,"VENCIDA",IF({DI}{{r}}<=7,"ATE 7",IF({DI}{{r}}<=15,"ATE 15",'
                     f'IF({DI}{{r}}<=30,"ATE 30","MAIS DE 30"))))))'),
        "f_seq": f'=IF({G}{{r}}="APTA",COUNTIF({G}${LIN_1}:{G}{{r}},"APTA"),"")',
    }

    def valor_de(k, o, r):
        if k in ("f_mdata", "f_lib"):
            return ArrayFormula(f"{c[k]}{r}", f[k].format(r=r))
        if k in f:
            return f[k].format(r=r)
        if k == "f_lista":
            return ArrayFormula(f"{c['f_lista']}{r}", (
                f'=IFERROR(_xlfn.TEXTJOIN("; ",TRUE,IF(({FU["os_sap"]}={A}{r})*({FU["f_disp"]}="NÃO"),'
                f'{FU["codigo"]}&" "&{FU["descricao"]},"")),"ver aba Follow-up")'))
        if k == "f_obs":
            return ArrayFormula(f"{c['f_obs']}{r}", (
                f'=IFERROR(_xlfn.TEXTJOIN(" | ",TRUE,IF({FU["os_sap"]}={A}{r},{FU["m_obs"]}&"","")),"")'))
        if k == "prev":
            return "SIM" if o["preventiva"] else "NÃO"
        if k == "lista_ok":
            return LISTA_INCOMPLETA if o["fluxo_incompleto"] else "OK"
        return o[k]

    fmts = {"f_mdata": FMT_DATA + ";;", "f_data": FMT_DATA, "f_dias": FMT_DIAS, "f_valor": FMT_RS,
            "data_tracos": FMT_DATA, "f_lib": FMT_DATA}
    centro = {"os_tracos", "prev", "f_mdata", "f_data", "f_dias", "f_total", "f_disp", "f_falt", "f_caminho",
              "f_compra", "f_estoque", "retirados", "f_risco", "data_tracos", "f_lib", "plano", "origem_itens", "f_ir"}
    ult = escrever_tabela(ws, COLS_OS, [o for _, o in por_os.iterrows()], valor_de, fmts, centro,
                          negrito={"f_apta"}, links={"f_ir"}, detalhe=DETALHE_OS)
    ws.freeze_panes = f"C{LIN_1}"
    ws.conditional_formatting.add(f"A{LIN_1}:{c['ativo']}{ult}", FormulaRule(
        formula=[f'${c["prev"]}{LIN_1}="SIM"'], fill=P_PREV, font=Font(name=FONTE, bold=True)))
    cf_palavras(ws, f"{c['f_apta']}{LIN_1}:{c['f_apta']}{ult}", f"${c['f_apta']}{LIN_1}", CORES_APTA)
    ws.conditional_formatting.add(f"{c['f_dias']}{LIN_1}:{c['f_dias']}{ult}", CellIsRule(
        operator="lessThan", formula=["0"], font=Font(name=FONTE, color="9C0006", bold=True)))
    ws.conditional_formatting.add(f"{c['lista_ok']}{LIN_1}:{c['lista_ok']}{ult}", FormulaRule(
        formula=[f'LEFT(${c["lista_ok"]}{LIN_1},1)="⚠"'], font=Font(name=FONTE, color="9C0006", bold=True)))
    paisagem(ws)


def aba_por_fornecedor(wb, pf, FU, ini_forn):
    ws = wb.create_sheet("Por Fornecedor")
    ws.sheet_properties.tabColor = "BF8F00"
    titulo(ws, "Pedidos abertos por fornecedor (para cobrança)",
           "Pedidos e valor vêm da base de pedidos (inclui itens sem OS). Itens a receber, vencidos e atraso vêm "
           "do Follow-up e já descontam o que você marcou como recebido. O e-mail é cadastrado uma vez na aba "
           "Parâmetros ('✎ cadastrar e-mail').")
    cabecalho(ws, LIN_CAB, COLS_FORN)
    c = letras(COLS_FORN)
    f = {
        "f_receber": f'=COUNTIFS({FU["fornecedor"]},$A{{r}},{FU["etapa"]},4,{FU["f_disp"]},"NÃO")',
        "f_vencidos": f"=COUNTIFS({FU['fornecedor']},$A{{r}},{FU['etapa']},4,{FU['f_prio']},1)",
        "f_atraso": f"=SUMPRODUCT(MAX(({FU['fornecedor']}=$A{{r}})*({FU['etapa']}=4)*{FU['f_atraso']}))",
        "f_dias": f'=IF({c["pedido_mais_antigo"]}{{r}}="","",INT(DATA_REF)-INT({c["pedido_mais_antigo"]}{{r}}))',
    }
    EM, URL = c["f_email"], c["f_url"]
    f["f_email"] = '=IFERROR(INDEX(FORN_EMAILS,MATCH($A{r},FORN_NOMES,0))&"","")'

    def valor_de(k, x, r):
        if k in f:
            return f[k].format(r=r)
        if k == "f_mail":
            cad = f'"#\'Parâmetros\'!B"&IFERROR(MATCH($A{r},FORN_NOMES,0)+{ini_forn - 1},{ini_forn})'
            return (f'=IF({EM}{r}="",HYPERLINK({cad},"✎ cadastrar e-mail"),'
                    f'HYPERLINK({URL}{r},"✉ Cobrar por e-mail"))')
        if k == "f_url":
            saps = [v for v in str(x["pedidos_sap"]).split(", ") if v]
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


def aba_divergencias(wb, D, orfas):
    ws = wb.create_sheet("Divergências")
    ws.sheet_properties.tabColor = "C00000"
    titulo(ws, "Divergências e registros não casados",
           "As linhas 'NÃO CASADO' são as únicas que NÃO estão no Follow-up (contam na conciliação; elas aparecem "
           "na aba Recebimento). As demais apontam para uma linha do Follow-up pela Chave: anote lá, na coluna "
           "'Observação / Follow-up'.")
    cols = [("Tipo", 40, "tipo"), ("Gravidade", 9, "gravidade"), ("Base", 11, "base"),
            ("Linha de origem", 9, "linha"), (COL_CHAVE, 24, "chave"), ("Está no Follow-up?", 10, "no_followup"),
            ("Código material", 10, "codigo"), ("Descrição do material", 34, "descricao"),
            ("Requisição", 10, "requisicao"), ("Pedido", 12, "pedido"), ("OS (TracOS ou SAP)", 12, "os"),
            ("Fornecedor", 34, "fornecedor"), ("Detalhe", 90, "detalhe")]
    cabecalho(ws, LIN_CAB, cols)
    regs = ([] if D is None or not len(D) else D.to_dict("records")) + orfas
    ult = escrever_tabela(ws, cols, regs, lambda k, d, r: d.get(k), {},
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


# ------------------------------------------------------------------ painel
# cores de estado (fixas) e tons neutros do painel
COR_OK, COR_ATENCAO, COR_SERIO, COR_CRITICO = "0CA30C", "FAB219", "EC835A", "D03B3B"
COR_AZUL, COR_MUDO = "2A78D6", "898781"
TINTA, TINTA_2, LINHA, LINHA_BASE = "0B0B0B", "52514E", "E1E0D9", "C3C2B7"
FUNDO_PAG, FUNDO_TOPO, TEXTO_TOPO, COR_LINK = "F2F2EF", "1F3864", "C9D3E6", "1F5FAD"
ROT_GRUPO = [("APTA", "✅ Apta para programar", COR_OK), ("FALTA 1", "⛔ Aguardando 1 item", COR_ATENCAO),
             ("FALTA 2-3", "⛔ Aguardando 2 a 3 itens", COR_SERIO), ("FALTA 4+", "⛔ Aguardando 4 ou mais", COR_SERIO),
             ("LIBERADA", "▶ Liberada para a equipe", COR_AZUL),
             ("LIBERADA FALTANDO", "⚠ Liberada faltando itens", COR_CRITICO)]
ROT_REC = {0: ("🚚 A caminho – atrasado", COR_CRITICO), 1: ("🚚 A caminho", COR_AZUL),
           6: ("📦 Falta em estoque (SAP)", COR_SERIO), 2: ("🟡 Recebido parcial", COR_ATENCAO),
           3: ("⛔ Não recebido", COR_CRITICO), 4: ("✅ Recebido (marcado por você)", COR_OK),
           5: ("✅ Recebido (entrada TracOS/SAP)", COR_OK)}
ROT_STATUS = {1: ("🔴 Necessidade vencida", COR_CRITICO), 2: ("🔴 Parada na aprovação", COR_CRITICO),
              3: ("🟠 Sem pedido", COR_SERIO), 4: ("🟠 Entrega em risco", COR_ATENCAO), 5: ("🟢 No prazo", COR_OK),
              6: ("✅ Entregue", COR_MUDO), 7: ("⚪ Sem data de necessidade", COR_ATENCAO)}
N_APTAS = 8  # OS aptas listadas no Painel
ROT_ETAPA = {0: "Falta em estoque (SAP)", 1: "Aprovação – gestor / RC SAP", 2: "Aprovação – almox corporativo",
             3: "Autorizada, sem pedido", 4: "Pedido emitido", 5: "Entregue / disponível"}


def _fonte(tam=10, cor=TINTA, negrito=False, italico=False):
    return Font(name=FONTE, size=tam, color=cor, bold=negrito, italic=italico)


def aba_painel(wb, R, FU, REC, POS, lin_avisos, ini_forn, B, lin_arquivos):
    """Painel em cartões: faixa de título, menu, indicadores clicáveis e tabelas curtas lado a lado."""
    ws = wb.create_sheet("Painel", 0)
    ws.sheet_properties.tabColor = FUNDO_TOPO
    ws.sheet_view.showGridLines = False
    pf, reqs = R["por_fornecedor"], R["requisicoes"]
    # grade: A e O = margens; B–G = bloco esquerdo; H = espaço; I–N = bloco direito
    for j in range(1, 16):
        ws.column_dimensions[get_column_letter(j)].width = 2 if j in (1, 8, 15) else 12
    ESQ, DIR, FIM = 2, 9, 14
    cartoes, zeros = [], []
    al = {"l": Alignment(horizontal="left", vertical="center", indent=1),
          "c": Alignment(horizontal="center", vertical="center"),
          "r": Alignment(horizontal="right", vertical="center", indent=1),
          "b": Alignment(horizontal="left", vertical="center")}

    def escrever(lin, c0, c1, valor, fonte, h="l", fmt=None, preench=None):
        if c1 > c0:
            ws.merge_cells(start_row=lin, start_column=c0, end_row=lin, end_column=c1)
        return cel(ws, (lin, c0), valor, fonte, fmt=fmt, preench=preench, alin=al[h])

    def bordas(lin, c0, c1, **lados):
        for j in range(c0, c1 + 1):
            b = ws.cell(row=lin, column=j).border
            ws.cell(row=lin, column=j).border = Border(
                left=lados.get("left", b.left), right=lados.get("right", b.right),
                top=lados.get("top", b.top), bottom=lados.get("bottom", b.bottom))

    fino = Side(style="thin", color=LINHA)

    # ---------------------------------------------------------------- faixa de título
    for r in range(1, 5):
        for j in range(1, 16):
            ws.cell(row=r, column=j).fill = PatternFill("solid", fgColor=FUNDO_TOPO)
    ws.row_dimensions[1].height = 8
    ws.row_dimensions[2].height = 30
    ws.row_dimensions[3].height = 18
    ws.row_dimensions[4].height = 20
    ws.row_dimensions[5].height = 10
    # arquivos usados: para conferir de relance se a atualização pegou as exportações novas
    rot = {"requisicao": "Requisição", "fluxo": "Fluxo", "pedido": "Pedido", "iwbk": "IWBK"}
    usados = "   ·   ".join(
        f"{rot[n]}: {os.path.basename(b['arquivo'])} ({dt.datetime.fromtimestamp(os.path.getmtime(b['arquivo'])):%d/%m %H:%M})"
        for n, b in B.items() if b)
    texto = "Bases usadas  ·  " + usados.replace('"', "'")
    escrever(4, ESQ, FIM, link(f"\"#'Parâmetros'!A{lin_arquivos}\"", f'"{texto}"') if len(texto) <= 250 else texto,
             _fonte(8, TEXTO_TOPO))  # texto entre aspas numa fórmula: máx. 255 caracteres
    escrever(2, ESQ, 10, "Follow-up de peças · Manutenção preventiva", _fonte(16, "FFFFFF", True))
    escrever(3, ESQ, 3, "Data de referência", _fonte(9, TEXTO_TOPO))
    escrever(3, 4, 4, "=DATA_REF", _fonte(10, "FFFFFF", True), fmt=FMT_DATA)
    escrever(3, 5, 7, f"Gerado em {dt.datetime.now():%d/%m/%Y %H:%M}", _fonte(9, TEXTO_TOPO))
    if R["alertas"]:
        n = len(R["alertas"])
        escrever(3, 10, FIM, link(f"\"#'Parâmetros'!A{lin_avisos}\"",
                                  f'"⚠ {n} aviso{"s" if n > 1 else ""} sobre as bases – ler"'),
                 _fonte(9, COR_ATENCAO, True), h="r")

    # ---------------------------------------------------------------- menu
    menu = [("✎ Follow-up (preencher)", "Follow-up", letras(COLS_FU)["m_rec"]), ("Por OS", "Por OS", "A"),
            ("Recebimento", "Recebimento", "A"), ("Fornecedores", "Por Fornecedor", "A"),
            ("Divergências", "Divergências", "A"), ("Parâmetros", "Parâmetros", "B")]
    for i, (txt, aba, col) in enumerate(menu):
        c0 = [2, 4, 6, 9, 11, 13][i]
        prim = i == 0
        escrever(6, c0, c0 + 1, link(local(aba, col), f'"{txt}"'), _fonte(10, "FFFFFF" if prim else COR_LINK, True),
                 h="c", preench=PatternFill("solid", fgColor=COR_AZUL if prim else "FFFFFF"))
        lado = Side(style="thin", color=COR_AZUL if prim else LINHA_BASE)
        bordas(6, c0, c0 + 1, top=lado, bottom=lado)
        bordas(6, c0, c0, left=lado)
        bordas(6, c0 + 1, c0 + 1, right=lado)
    ws.row_dimensions[6].height = 26
    escrever(7, ESQ, FIM, "Tudo o que você preenche fica no Follow-up (colunas amarelas). Clique nos números e nomes "
                          "para abrir os itens; em cada aba, a célula A1 volta para cá.", _fonte(9, TINTA_2, italico=True))
    ws.row_dimensions[7].height = 20

    # ---------------------------------------------------------------- indicadores
    def achar(valores, faixa):
        """MATCH do 1º valor encontrado (tenta na ordem)."""
        expr = f"MATCH({valores[-1]},{faixa},0)"
        for v in reversed(valores[:-1]):
            expr = f"IFERROR(MATCH({v},{faixa},0),{expr})"
        return expr

    g, sit = POS["f_grupo"], REC["f_sit"]
    falta = ['"FALTA 1"', '"FALTA 2-3"', '"FALTA 4+"']
    tiles = [
        (ESQ, 5, "OS APTAS PARA PROGRAMAR", COR_OK, local("Por OS", "A", f'MATCH("APTA",{g},0)'),
         f'COUNTIFS({g},"APTA")',
         f'="de "&COUNTA({POS["os_sap"]})&" OS em aberto · "&COUNTIFS({g},"LIBERADA*")'
         f'&IF(COUNTIFS({g},"LIBERADA*")=1," já liberada"," já liberadas")'),
        (6, 7, "AGUARDANDO ITENS", COR_ATENCAO, local("Por OS", "A", achar(falta, g)),
         "+".join(f"COUNTIFS({g},{x})" for x in falta), f'=COUNTIFS({g},"FALTA 1")&" com só 1 item faltando"'),
        (8, 10, "ITENS ATRASADOS", COR_CRITICO,
         local("Recebimento", "A", f'MATCH("{cz.SITUACAO_REC[0]}",{sit},0)'),
         f'COUNTIFS({sit},"{cz.SITUACAO_REC[0]}")', "com pedido, data vencida"),
        (11, 12, "FALTA EM ESTOQUE", COR_SERIO, local("Recebimento", "A", f'MATCH("{cz.SITUACAO_REC[6]}",{sit},0)'),
         f'COUNTIFS({sit},"{cz.SITUACAO_REC[6]}")', "reservas SAP sem saldo"),
        (13, 14, "PARADOS NA APROVAÇÃO", COR_CRITICO, local("Follow-up", "A", f"MATCH(2,{FU['f_prio']},0)"),
         f"COUNTIFS({FU['f_prio']},2)", "itens além do prazo"),
    ]
    T = 9
    for c0, c1, rot, cor, loc, n, sub in tiles:
        escrever(T, c0, c1, rot, _fonte(8, TINTA_2, True))
        escrever(T + 1, c0, c1, link(loc, n), _fonte(30 if c0 == ESQ else 24, TINTA, True))
        escrever(T + 2, c0, c1, sub, _fonte(9, TINTA_2))
        bordas(T, c0, c1, top=Side(style="thick", color=cor))
        if c0 != ESQ:
            for r in range(T, T + 3):
                bordas(r, c0, c0, left=fino)
    ws.row_dimensions[T].height = 22
    ws.row_dimensions[T + 1].height = 44
    ws.row_dimensions[T + 2].height = 20
    cartoes.append((T, T + 2, ESQ, FIM))

    # ---------------------------------------------------------------- cartões com tabela
    def cartao(r0, c0, titulo_, nota, cab, linhas, vazio=None):
        """cab = [(título, nº de colunas, alinhamento)]; cada linha = lista de células, uma por coluna do cab:
        dict(v=valor ou função da linha, f=fonte, fmt=formato, acento=cor da faixa à esquerda,
        barra=índice da coluna com o número, cor=cor da barra)."""
        c1 = c0 + sum(n for _, n, _ in cab) - 1
        escrever(r0, c0, c0 + 2, titulo_, _fonte(11, TINTA, True))
        if nota:
            escrever(r0, c0 + 3, c1, nota, _fonte(8, COR_MUDO, italico=True), h="r")
        ws.row_dimensions[r0].height = 26
        inicio = [c0 + sum(n for _, n, _ in cab[:i]) for i in range(len(cab))]
        for (t, n, h), j in zip(cab, inicio):
            escrever(r0 + 1, j, j + n - 1, t, _fonte(8, TINTA_2, True), h=h)
        bordas(r0 + 1, c0, c1, bottom=Side(style="thin", color=LINHA_BASE))
        ws.row_dimensions[r0 + 1].height = 18
        lin = r0 + 1
        if not linhas and vazio:
            lin += 1
            escrever(lin, c0, c1, vazio, _fonte(9, COR_MUDO, italico=True))
            ws.row_dimensions[lin].height = 20
        r_ini, r_fim = r0 + 2, r0 + 1 + len(linhas)
        for cells in linhas:
            lin += 1
            for (t, n, h), j, d in zip(cab, inicio, cells):
                if d is None:
                    continue
                if "barra" in d:
                    num = f"{get_column_letter(inicio[d['barra']])}"
                    largura = 8 * n - 1  # blocos que cabem na coluna (█ em Arial 9 ≈ 9 px)
                    v = (f'=IF(N({num}{lin})<=0,"",REPT("█",MAX(1,ROUND({num}{lin}/MAX(1,MAX({num}{r_ini}:{num}{r_fim}))'
                         f'*{largura},0))))')
                    escrever(lin, j, j + n - 1, v, _fonte(9, d.get("cor", COR_AZUL)), h="b")
                    continue
                v = d["v"](lin) if callable(d["v"]) else d["v"]
                escrever(lin, j, j + n - 1, v, d.get("f", _fonte()), h=d.get("h", h), fmt=d.get("fmt"))
                if d.get("acento"):
                    bordas(lin, j, j, left=Side(style="thick", color=d["acento"]))
                if d.get("zero"):
                    zeros.append(f"{get_column_letter(j)}{lin}")
            bordas(lin, c0, c1, bottom=fino)
            ws.row_dimensions[lin].height = 20
        return lin

    F_ROT = _fonte(10, TINTA)
    F_NUM = _fonte(11, COR_LINK, True)

    def rotulo(loc, txt, cor):
        return dict(v=link(loc, f'"{txt}"'), f=F_ROT, acento=cor)

    def numero(loc, expr, zero=True):
        return dict(v=link(loc, expr), f=F_NUM, zero=zero)

    def par(r0, esq, dir_):
        """Dois cartões lado a lado com a mesma altura."""
        f1, f2 = esq(r0), dir_(r0)
        fim = max(f1, f2)
        cartoes.append((r0, fim + 1, ESQ, 7))
        cartoes.append((r0, fim + 1, DIR, FIM))
        ws.row_dimensions[fim + 1].height = 8
        return fim + 3

    # 1) situação das OS  |  recebimento
    def c_os(r0):
        linhas = []
        for grp, txt, cor in ROT_GRUPO:
            loc = local("Por OS", "A", f'MATCH("{grp}",{g},0)')
            linhas.append([rotulo(loc, txt, cor), numero(loc, f'COUNTIFS({g},"{grp}")'), dict(barra=1, cor=cor)])
        ret = R.get("os_retiradas")
        if ret is not None and len(ret):
            loc = local("Histórico SAP", "A")
            linhas.append([rotulo(loc, "✔ Material já retirado (SAP)", COR_MUDO), numero(loc, len(ret)),
                           dict(barra=1, cor=COR_MUDO)])
        loc = local("Por OS", "A", f'MATCH("{LISTA_INCOMPLETA}",{POS["lista_ok"]},0)')
        linhas.append([rotulo(loc, "⚠ Lista de itens a conferir no TracOS", COR_ATENCAO),
                       numero(loc, f'COUNTIFS({POS["lista_ok"]},"{LISTA_INCOMPLETA}")'), dict(barra=1, cor=COR_ATENCAO)])
        return cartao(r0, ESQ, "Situação das OS", "apta = todos os itens disponíveis",
                      [("SITUAÇÃO", 3, "l"), ("OS", 1, "c"), ("", 2, "l")], linhas)

    def c_rec(r0):
        linhas = []
        for k, txt in cz.SITUACAO_REC.items():
            rot, cor = ROT_REC[k]
            loc = local("Recebimento", "A", f'MATCH("{txt}",{sit},0)')
            linhas.append([rotulo(loc, rot, cor), numero(loc, f'COUNTIFS({sit},"{txt}")'), dict(barra=1, cor=cor)])
        return cartao(r0, DIR, "Recebimento de materiais", "marque no Follow-up → Recebido?",
                      [("SITUAÇÃO DO ITEM", 3, "l"), ("ITENS", 1, "c"), ("", 2, "l")], linhas)

    lin = par(13, c_os, c_rec)

    # 2) OS aptas agora  |  OS com itens faltando por janela
    def c_aptas(r0):
        linhas = []
        for k in range(1, N_APTAS + 1):
            m = f'MATCH({k},{POS["f_seq"]},0)'
            vazio = '"Nenhuma OS apta no momento."' if k == 1 else '""'
            linhas.append([
                dict(v=f'=IFERROR(HYPERLINK("#\'Por OS\'!A"&({m}+{LIN_CAB}),INDEX({POS["os_sap"]},{m})&"  ·  "'
                       f'&INDEX({POS["descricao_os"]},{m})),{vazio})', f=_fonte(10, COR_LINK, True)),
                dict(v=f'=IFERROR(INDEX({POS["f_total"]},{m}),"")', f=_fonte(10, TINTA)),
                dict(v=f'=IFERROR(IF(INDEX({POS["f_data"]},{m})="","",INDEX({POS["f_data"]},{m})),"")',
                     f=_fonte(10, TINTA), fmt=FMT_DATA)])
        nota = (f'=IF(COUNTIFS({g},"APTA")>{N_APTAS},"{N_APTAS} de "&COUNTIFS({g},"APTA")&" – todas na aba Por OS",'
                f'"clique na OS para abrir")')
        return cartao(r0, ESQ, "OS aptas para programar agora", nota,
                      [("OS", 4, "l"), ("ITENS", 1, "c"), ("NECESSIDADE", 1, "c")], linhas)

    def c_janela(r0):
        J, F_ = POS["f_janela"], POS["f_falt"]
        janelas = [("Necessidade já vencida", ["VENCIDA"], COR_CRITICO), ("Próximos 7 dias", ["ATE 7"], COR_SERIO),
                   ("Próximos 15 dias", ["ATE 7", "ATE 15"], COR_ATENCAO),
                   ("Próximos 30 dias", ["ATE 7", "ATE 15", "ATE 30"], COR_AZUL),
                   ("Sem data – digite no Follow-up", ["SEM DATA"], COR_MUDO)]
        linhas = []
        for rot, chaves, cor in janelas:
            loc = local("Por OS", "A", achar([f'"{x}"' for x in chaves], J))
            linhas.append([rotulo(loc, rot, cor), numero(loc, "+".join(f'COUNTIFS({J},"{x}")' for x in chaves)),
                           dict(v="=" + "+".join(f'SUMIFS({F_},{J},"{x}")' for x in chaves), f=_fonte(10, TINTA),
                                zero=True),
                           dict(barra=1, cor=cor)])
        todas = ["VENCIDA", "ATE 7", "ATE 15", "ATE 30", "MAIS DE 30", "SEM DATA"]
        linhas.append([dict(v="Total com itens faltando", f=_fonte(10, TINTA, True)),
                       dict(v="=" + "+".join(f'COUNTIFS({J},"{x}")' for x in todas), f=_fonte(11, TINTA, True)),
                       dict(v="=" + "+".join(f'SUMIFS({F_},{J},"{x}")' for x in todas), f=_fonte(10, TINTA, True)),
                       None])
        return cartao(r0, DIR, "OS com itens faltando", "pela data de necessidade (acumulado)",
                      [("JANELA", 3, "l"), ("OS", 1, "c"), ("ITENS", 1, "c"), ("", 1, "l")], linhas)

    lin = par(lin, c_aptas, c_janela)

    # 3) status de risco  |  funil de compras
    def c_status(r0):
        linhas = []
        for p_, (rot, cor) in ROT_STATUS.items():
            loc = local("Follow-up", "A", f"MATCH({p_},{FU['f_prio']},0)")
            linhas.append([rotulo(loc, rot, cor), numero(loc, f"COUNTIFS({FU['f_prio']},{p_})"),
                           dict(barra=1, cor=cor)])
        return cartao(r0, ESQ, "Itens por status de risco", "clique para abrir no Follow-up",
                      [("STATUS", 3, "l"), ("ITENS", 1, "c"), ("", 2, "l")], linhas)

    def c_funil(r0):
        linhas = []
        for e, rot in ROT_ETAPA.items():
            loc = local("Follow-up", "A", f"MATCH({e},{FU['etapa']},0)")
            linhas.append([dict(v=link(loc, f'"{e} · {rot}"'), f=F_ROT), numero(loc, f"COUNTIFS({FU['etapa']},{e})"),
                           dict(v=f"=SUMIFS({FU['f_valor']},{FU['etapa']},{e})", f=_fonte(10, TINTA),
                                fmt='"R$" #,##0;-"R$" #,##0;"–"'),
                           dict(barra=1, cor=COR_AZUL)])
        return cartao(r0, DIR, "Funil de compras", "valor só dos itens com preço",
                      [("ETAPA", 3, "l"), ("ITENS", 1, "c"), ("VALOR", 1, "r"), ("", 1, "l")], linhas)

    lin = par(lin, c_status, c_funil)

    # 4) fornecedores atrasados (largura toda)
    cf = letras(COLS_FORN)
    atrasados = [i for i, (_, x) in enumerate(pf.iterrows()) if x["_atraso"] > 0] if len(pf) else []
    linhas = []
    for i in atrasados[:10]:
        rf = LIN_1 + i
        pfr = lambda k: f"'Por Fornecedor'!{cf[k]}{rf}"
        cad = f'"#\'Parâmetros\'!B"&IFERROR(MATCH({pfr("fornecedor")},FORN_NOMES,0)+{ini_forn - 1},{ini_forn})'
        saps = [v for v in str(pf.iloc[i]["pedidos_sap"]).split(", ") if v]
        peds = ", ".join(saps[:3]) + (f" +{len(saps) - 3}" if len(saps) > 3 else "") if saps else \
            f"{pf.iloc[i]['n_pedidos']} sem nº SAP"
        linhas.append([
            dict(v=f"=HYPERLINK(\"#'Por Fornecedor'!A{rf}\",{pfr('fornecedor')})", f=_fonte(10, COR_LINK, True)),
            dict(v=peds, f=_fonte(10, TINTA)),
            dict(v=f"={pfr('f_vencidos')}", f=_fonte(10, TINTA, True), zero=True),
            dict(v=f"={pfr('f_atraso')}", f=_fonte(10, TINTA), fmt='0" dias";-0;"–"'),
            dict(v=f"={pfr('valor_aberto')}", f=_fonte(10, TINTA), fmt='"R$" #,##0'),
            dict(v=f'=IF({pfr("f_email")}="",HYPERLINK({cad},"✎ cadastrar e-mail"),'
                   f'HYPERLINK({pfr("f_url")},"✉ Cobrar"))', f=_fonte(10, COR_LINK, True))])
    nota = "clique no fornecedor para ver os pedidos" if len(atrasados) <= 10 else \
        f"10 de {len(atrasados)} – todos na aba Por Fornecedor"
    fim = cartao(lin, ESQ, "Fornecedores com pedidos atrasados", nota,
                 [("FORNECEDOR", 3, "l"), ("PEDIDOS SAP", 3, "l"), ("VENCIDOS", 2, "c"),
                  ("MAIOR ATRASO", 1, "c"), ("VALOR EM ABERTO", 2, "r"), ("COBRAR", 2, "c")], linhas,
                 vazio="Nenhum fornecedor com itens atrasados.")
    cartoes.append((lin, fim + 1, ESQ, FIM))
    ws.row_dimensions[fim + 1].height = 8
    lin = fim + 3

    # 5) requisições paradas na aprovação (largura toda)
    tr = f'{FU["origem"]},"<>SAP"'
    nota = (f'="Gestor (01): "&COUNTIFS({FU["etapa"]},1,{FU["f_prio"]},2,{tr})&" itens parados  ·  Almox (02): "'
            f'&COUNTIFS({FU["etapa"]},2,{FU["f_prio"]},2,{tr})&" itens parados"')
    if len(R["linhas"][(R["linhas"]["origem"] == "SAP") & (R["linhas"]["etapa"] == 1)]):
        nota += f'&"  ·  RC só no SAP: "&COUNTIFS({FU["etapa"]},1,{FU["origem"]},"SAP")&" itens"'
    linhas = []
    for e in (1, 2):
        sub = reqs[reqs["etapa"] == e].head(10) if len(reqs) else reqs
        lim = "X_NIVEL01" if e == 1 else "X_NIVEL02"
        email = "EMAIL_GESTOR" if e == 1 else "EMAIL_ALMOX"
        for _, q in sub.iterrows():
            os_txt = f"{q['os_sap']}  ·  {q['descricao_os']}" if not pd.isna(q["os_sap"]) else "(sem OS)"
            os_txt = os_txt if len(os_txt) <= 44 else os_txt[:43] + "…"
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
            linhas.append([
                dict(v=link(loc, '"' + os_txt.replace('"', "'") + '"'), f=_fonte(10, COR_LINK, True)),
                dict(v=req_txt, f=_fonte(10, TINTA)), dict(v=q["req_sap"], f=_fonte(10, TINTA)),
                dict(v="01 Gestor" if e == 1 else "02 Almox", f=_fonte(10, TINTA)),
                dict(v=q["itens"], f=_fonte(10, TINTA)), dict(v=q["inicio"], f=_fonte(10, TINTA), fmt=FMT_DATA),
                dict(v=lambda r: f"=INT(DATA_REF)-INT(K{r})", f=_fonte(10, TINTA, True)),
                dict(v=lambda r, lim=lim: f'=IF(L{r}>{lim},"🔴 Parada","no prazo")', f=_fonte(10, TINTA)),
                dict(v=formula_mailto(email, completo, curto, "✉ Cobrar", "(sem e-mail)"),
                     f=_fonte(10, COR_LINK, True))])
    fim = cartao(lin, ESQ, "Requisições paradas na aprovação", nota,
                 [("OS (clique para ver os itens)", 4, "l"), ("REQUISIÇÃO", 1, "c"), ("REQ. SAP", 2, "c"),
                  ("NÍVEL", 1, "c"), ("ITENS", 1, "c"), ("DESDE", 1, "c"), ("DIAS", 1, "c"), ("SITUAÇÃO", 1, "c"),
                  ("COBRAR", 1, "c")], linhas, vazio="Nenhuma requisição aguardando aprovação.")
    cartoes.append((lin, fim + 1, ESQ, FIM))
    ws.conditional_formatting.add(f"M{lin}:M{fim}", FormulaRule(
        formula=[f'ISNUMBER(SEARCH("PARADA",M{lin}))'], font=Font(name=FONTE, color="B42318", bold=True)))
    ult = fim + 2

    # ---------------------------------------------------------------- acabamento: cartões brancos sobre fundo cinza
    branco = PatternFill("solid", fgColor="FFFFFF")
    for r0, r1, c0, c1 in cartoes:
        for r in range(r0, r1 + 1):
            for j in range(c0, c1 + 1):
                c = ws.cell(row=r, column=j)
                if c.fill is None or c.fill.fill_type is None:
                    c.fill = branco
        for r in range(r0, r1 + 1):
            if ws.cell(row=r, column=c0).border.left.style is None:
                bordas(r, c0, c0, left=fino)
            bordas(r, c1, c1, right=fino)
        for j in range(c0, c1 + 1):
            if ws.cell(row=r0, column=j).border.top.style is None:
                bordas(r0, j, j, top=fino)
        bordas(r1, c0, c1, bottom=fino)
    fundo = PatternFill("solid", fgColor=FUNDO_PAG)
    for r in range(5, ult + 1):
        for j in range(1, 16):
            c = ws.cell(row=r, column=j)
            if c.fill is None or c.fill.fill_type is None:
                c.fill = fundo
    for a in zeros:
        ws.conditional_formatting.add(a, CellIsRule(operator="equal", formula=["0"],
                                                    font=Font(name=FONTE, color=COR_MUDO, bold=False)))
    sem_link(ws, f"A1:O{ult}", "A1")
    ws.freeze_panes = "A8"
    ws.sheet_view.zoomScale = 100
    paisagem(ws)


def aba_historico_sap(wb, H):
    ws = wb.create_sheet("Histórico SAP")
    ws.sheet_properties.tabColor = "A9D08E"
    titulo(ws, "Histórico SAP – material já retirado / baixado para a ordem",
           "Itens da IWBK sem ação pendente: o material já saiu para a OS. Ficam fora do Follow-up, do Recebimento "
           "e da Por OS (mas contam como disponíveis no total da OS). OS em que todos os itens estão aqui provavelmente "
           "já estão em execução ou concluídas.")
    cabecalho(ws, LIN_CAB, COLS_HIST)
    regs = [] if H is None or not len(H) else [h for _, h in H.iterrows()]

    def valor_de(k, h, r):
        if k == "prev":
            return "SIM" if h["eh_preventiva"] else "NÃO"
        return h[k]

    escrever_tabela(ws, COLS_HIST, regs, valor_de, {"data_nec_tracos": FMT_DATA},
                    {"os_tracos", "prev", "codigo", "qtd", "qtd_retirada", "unidade", "data_nec_tracos", "orig_sap"})
    ws.freeze_panes = f"C{LIN_1}"
    paisagem(ws)


def aba_outras_os(wb, O, ativo):
    ws = wb.create_sheet("Outras OS")
    ws.sheet_properties.tabColor = "BFBFBF"
    titulo(ws, "Outras OS (não preventivas)",
           "Corretivas, compras, giro de estoque etc. Fora das abas de trabalho porque o parâmetro 'Abas de trabalho "
           "só com OS preventivas' está como SIM (aba Parâmetros). Status calculado na geração.")
    cabecalho(ws, LIN_CAB, COLS_OUTRAS)
    regs = [] if O is None or not len(O) else [o for _, o in O.iterrows()]
    if not ativo:
        cel(ws, (LIN_1, 1), "Parâmetro como NÃO: todas as OS estão nas abas de trabalho.", F_NOTA)
    escrever_tabela(ws, COLS_OUTRAS, regs, lambda k, o, r: o[k], {"data_necessidade": FMT_DATA},
                    {"os_tracos", "codigo", "qtd", "unidade", "data_necessidade"})
    ws.freeze_panes = f"C{LIN_1}"
    if regs:
        cf_palavras(ws, f"J{LIN_1}:J{LIN_1 + len(regs) - 1}", f"$J{LIN_1}", CORES_STATUS)
    paisagem(ws)


def aba_bases(wb, B):
    ws = wb.create_sheet("Bases tratadas")
    ws.sheet_properties.tabColor = "A6A6A6"
    titulo(ws, "Bases tratadas (auditoria)",
           "As exportações (TracOS e IWBK do SAP) já normalizadas. 'linha_origem' = linha no CSV (1 = cabeçalho); é a "
           "referência usada em 'Linhas de origem' no Follow-up e em Divergências.")
    lin = LIN_CAB + 1
    larg = {}
    for nome, tab in (("requisicao", "tbRequisicao"), ("fluxo", "tbFluxo"), ("pedido", "tbPedido"),
                      ("iwbk", "tbIWBK")):
        if not B.get(nome):
            continue
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
    ant = ler_versao_anterior(pasta_saida)
    B = tb.carregar_bases(pasta_bases, ant["arquivos"])
    man = ant["manuais"]
    migrar_chaves_os(man, B)
    prm = dict(ant["prm"])
    so_prev = str(prm.get("so_preventivas", "SIM")).strip().upper() not in ("NÃO", "NAO", "N")
    R = cz.cruzar(B, hoje, ant["historico"],
                  {k: v for k, v in prm.items() if not k.startswith(("nome_", "email_", "so_"))},
                  manuais=manuais_para_cruzamento(man), so_preventivas=so_prev)

    # observações antigas por OS / de Divergências vão para um item; o que sumiu das bases não se perde
    distribuir_notas(man, R["linhas"])
    orfas, orfas_reg = anotacoes_sem_lugar(man, R)

    FU = faixas("Follow-up", COLS_FU, len(R["linhas"]))
    REC = faixas("Recebimento", COLS_REC, len(R["recebimento"]))
    POS = faixas("Por OS", COLS_OS, len(R["por_os"]))

    wb = Workbook()
    wb.remove(wb.active)
    lin_avisos, ini_forn, lin_arquivos = aba_parametros(wb, {**cz.PARAMETROS_PADRAO, **prm}, B, R, data_fixa, ant, man["forn"])
    aba_followup(wb, R["linhas"], man, FU, POS)
    aba_recebimento(wb, R["recebimento"], FU, POS)
    aba_por_os(wb, R["por_os"], FU)
    aba_por_fornecedor(wb, R["por_fornecedor"], FU, ini_forn)
    aba_divergencias(wb, R["divergencias"], orfas)
    aba_painel(wb, R, FU, REC, POS, lin_avisos, ini_forn, B, lin_arquivos)
    aba_historico_sap(wb, R["historico_sap"])
    aba_outras_os(wb, R["outras"], so_prev)
    aba_bases(wb, B)
    aba_oculta(wb, "_historico", ["Chave", "Etapa", "Desde"],
               [[k, e, d] for k, (e, d) in sorted(R["historico"].items())], fmt_col="C")
    aba_oculta(wb, "_anotacoes", ["Aba", "Chave", "Coluna", "Valor"], orfas_reg)
    aba_oculta(wb, "_arquivos", ["Base", "Arquivo", "MD5", "Modificado em", "Usado"],
               [[nome, os.path.basename(c), b["md5"][c], dt.datetime.fromtimestamp(os.path.getmtime(c)),
                 "SIM" if c == b["arquivo"] else "NÃO"]
                for nome, b in B.items() if b for c in b["candidatos"]], fmt_col="D")
    ordem = ["Painel", "Follow-up", "Por OS", "Recebimento", "Por Fornecedor", "Divergências", "Histórico SAP",
             "Outras OS", "Parâmetros", "Bases tratadas", "_historico", "_anotacoes", "_arquivos"]
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
    movidos = arquivar_substituidos(B, pasta_bases)

    if not silencioso:
        resumo(R, destino, ant, orfas, B, movidos)
    return destino, R


def arquivar_substituidos(B, pasta_bases):
    """Exportações antigas que foram substituídas por uma nova vão para bases/antigos, para que a pasta
    bases fique só com as exportações atuais."""
    pasta = os.path.join(pasta_bases, "antigos")
    movidos = []
    for b in B.values():
        for c in (b or {}).get("substituidos", []):
            os.makedirs(pasta, exist_ok=True)
            raiz, ext = os.path.splitext(os.path.join(pasta, os.path.basename(c)))
            alvo, k = raiz + ext, 1
            while os.path.exists(alvo):
                alvo, k = f"{raiz} ({k}){ext}", k + 1
            try:
                shutil.move(c, alvo)
                movidos.append(os.path.basename(c))
            except OSError as e:
                print(f"AVISO: não consegui mover {c} para {pasta}: {e}")
    return movidos


def resumo(R, destino, ant, orfas, B, movidos):
    L, po, rc = R["linhas"], R["por_os"], R["recebimento"]
    print("=" * 78)
    print("FOLLOW-UP DE PEÇAS – atualização concluída")
    print("=" * 78)
    print(f"Arquivo gerado: {destino}")
    print("Bases usadas:")
    for nome, b in B.items():
        if b:
            print(f"  {nome:<11} {os.path.basename(b['arquivo'])}  (modificado em "
                  f"{dt.datetime.fromtimestamp(os.path.getmtime(b['arquivo'])):%d/%m/%Y %H:%M}; {b['motivo']})")
    if movidos:
        print(f"  exportações antigas movidas para bases/antigos: {', '.join(movidos)}")
    m = ant["manuais"]
    print(f"Anotações reaproveitadas de: {os.path.basename(ant['arquivo']) if ant['arquivo'] else '(primeira versão)'}"
          f"  |  {len(m['item'])} itens e {len(m['os'])} OS com anotação, {len(m['forn'])} e-mails de fornecedor, "
          f"{len(orfas)} sem item atual")
    if ant.get("migrou") and (m["item"] or m["os"] or m["forn"]):
        print("  (versão anterior no formato antigo: o que estava digitado em Recebimento / Por OS / Por Fornecedor "
              "foi levado para o Follow-up e para Parâmetros)")
    print("\nConciliação (entrada = Follow-up + Histórico SAP + Outras OS + Divergências não casadas):")
    for _, c in R["conciliacao"].iterrows():
        print(f"  {c['base']:<11} entrada {c['entrada']:>4} | follow-up {c['follow_up']:>4} | "
              f"histórico {c['historico']:>4} | outras OS {c['outras']:>4} | divergências {c['divergencias']:>3} | "
              f"{'OK' if c['ok'] else 'DIFERENÇA!'}")
    if len(po):
        aptas = po[po["apta"] & ~po["liberada"]]
        print(f"\nOS: {len(po)} | aptas para programar: {len(aptas)} | liberadas: {int(po['liberada'].sum())} | "
              f"aguardando itens: {int((~po['apta'] & ~po['liberada']).sum())} | "
              f"material já retirado (Histórico SAP): {len(R.get('os_retiradas', []))}")
        for _, o in aptas.head(10).iterrows():
            print(f"  ✅ OS {o['os_sap']} {o['descricao_os']} ({int(o['itens'])} itens)")
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
