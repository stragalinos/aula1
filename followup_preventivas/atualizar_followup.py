"""Atualiza a planilha de follow-up de peças para manutenção (TracOS).

Uso:
    1. Jogue os downloads novos do TracOS na pasta ./bases
       (requisição de compra *.csv, fluxo de compras *.csv, pedido de compra *.csv)
    2. Rode:  python atualizar_followup.py        (ou dê dois cliques em atualizar_followup.bat)
    3. A planilha sai em ./saida/followup_preventivas_AAAA-MM-DD.xlsx

As observações digitadas na coluna "Observação / Follow-up" (e os parâmetros editados na aba
Parâmetros) da versão anterior são reaproveitadas automaticamente.
"""
import argparse
import datetime as dt
import glob
import math
import os
import sys
import warnings

import numpy as np
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.table import Table, TableStyleInfo

import cruzamento as cz
import tracos_bases as tb

AQUI = os.path.dirname(os.path.abspath(__file__))
PREFIXO = "followup_preventivas_"
COL_OBS = "Observação / Follow-up"
COL_CHAVE = "Chave"
ABAS_OBS = ("Follow-up", "Divergências", "Por OS", "Por Fornecedor")  # abas com observação preservada
TIPO_OBS_ORFA = "OBSERVAÇÃO SEM ITEM ATUAL"
LIN_CAB = 3          # linha do cabeçalho nas abas de tabela
LIN_1 = LIN_CAB + 1  # primeira linha de dados

# ------------------------------------------------------------------ estilo
FONTE = "Arial"
F_NORMAL = Font(name=FONTE, size=10)
F_NEGRITO = Font(name=FONTE, size=10, bold=True)
F_CAB = Font(name=FONTE, size=10, bold=True, color="FFFFFF")
F_TITULO = Font(name=FONTE, size=14, bold=True, color="1F3864")
F_SECAO = Font(name=FONTE, size=11, bold=True, color="1F3864")
F_NOTA = Font(name=FONTE, size=9, italic=True, color="595959")
F_ALERTA = Font(name=FONTE, size=10, bold=True, color="9C0006")
P_CAB = PatternFill("solid", fgColor="1F3864")
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
]

DESCR_STATUS = {
    1: "Data de necessidade já passou e o material não entrou.",
    2: "Requisição pendente há mais de X dias (X do nível atual).",
    3: "Compra autorizada há mais de Y dias e ainda sem pedido.",
    4: "Pedido emitido e faltam Z dias ou menos para a necessidade.",
    5: "Tem data de necessidade e está dentro dos limites.",
    6: "Material entregue (pedido concluído / entrada registrada).",
    7: "Item só na base de requisição: o TracOS não traz data de necessidade nessa etapa.",
}


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


def cabecalho(ws, linha, titulos, larguras=None):
    for j, t in enumerate(titulos, start=1):
        c = cel(ws, (linha, j), t, F_CAB, preench=P_CAB, alin=AL_CAB)
        c.border = BORDA
        if larguras:
            ws.column_dimensions[get_column_letter(j)].width = larguras[j - 1]
    ws.row_dimensions[linha].height = 32


def titulo(ws, texto, sub=None):
    cel(ws, "A1", texto, F_TITULO)
    if sub:
        cel(ws, "A2", sub, F_NOTA)


def cf_status(ws, rng, col_ref):
    """Formatação condicional pelas palavras do status (coluna col_ref, ex.: '$B4')."""
    for palavra, fundo, letra in CORES_STATUS:
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
        out.append({c: row[cab.index(c)] if cab.index(c) < len(row) else None for c in cab if c})
    return out


def ler_versao_anterior(pasta_saida):
    vazio = dict(arquivo=None, obs={a: {} for a in ABAS_OBS}, historico={}, prm={})
    arqs = [a for a in glob.glob(os.path.join(pasta_saida, PREFIXO + "*.xlsx"))
            if not os.path.basename(a).startswith("~$")]
    if not arqs:
        return vazio
    ant = max(arqs, key=os.path.getmtime)
    try:
        wb = load_workbook(ant, read_only=True, data_only=True)
    except Exception as e:  # arquivo corrompido / aberto de forma exclusiva
        print(f"AVISO: não consegui ler a versão anterior ({ant}): {e}. Observações não reaproveitadas.")
        return vazio
    obs = {a: {} for a in ABAS_OBS}
    chaves = {"Follow-up": [COL_CHAVE], "Divergências": ["Tipo", COL_CHAVE],
              "Por OS": ["OS TracOS"], "Por Fornecedor": ["Fornecedor"]}
    for aba, ks in chaves.items():
        if aba not in wb.sheetnames:
            continue
        for d in _tabela(wb[aba], ks + [COL_OBS]):
            texto = d.get(COL_OBS)
            if texto is None or str(texto).strip() == "":
                continue
            if aba == "Divergências" and d.get("Tipo") == TIPO_OBS_ORFA:
                destino = d.get("Base") if d.get("Base") in obs else "Divergências"
                k = d.get(COL_CHAVE) if destino != "Divergências" else d.get("Detalhe")
                obs[destino][str(k)] = texto
                continue
            k = "|".join(str(d.get(x)) for x in ks) if aba == "Divergências" else str(d.get(ks[0]))
            obs[aba][k] = texto
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
                if row[3].startswith("nome_"):
                    prm[row[3]] = "" if v is None else str(v)
                elif isinstance(v, (int, float)):
                    prm[row[3]] = v
    wb.close()
    return dict(arquivo=ant, obs=obs, historico=hist, prm=prm)


# ------------------------------------------------------------------ abas
def aba_parametros(wb, prm, B, R, hoje, data_fixa, info_ant):
    ws = wb.create_sheet("Parâmetros")
    ws.sheet_properties.tabColor = "808080"
    titulo(ws, "Parâmetros e legenda",
           "Células amarelas são editáveis e são reaproveitadas na próxima atualização "
           "(exceto a data de referência, que volta para =HOJE()).")
    cabecalho(ws, LIN_CAB, ["Parâmetro", "Valor", "Descrição", "id"], [52, 26, 95, 12])
    pos = {}
    for k, (pid, nome, rotulo, padrao, desc) in enumerate(PARAMETROS):
        lin = LIN_1 + k
        valor = padrao
        if pid == "data_ref":
            valor = data_fixa if data_fixa is not None else "=TODAY()"
        elif pid in prm:
            valor = prm[pid]
        cel(ws, (lin, 1), rotulo, F_NEGRITO)
        c = cel(ws, (lin, 2), valor, F_NORMAL, preench=P_EDITAVEL,
                fmt=FMT_DATA if pid == "data_ref" else None,
                alin=Alignment(horizontal="left"))
        if pid == "data_ref" and data_fixa is not None:
            c.value = data_fixa
        cel(ws, (lin, 3), desc, F_NOTA)
        cel(ws, (lin, 4), pid, F_NOTA)
        nome_definido(wb, nome, f"'Parâmetros'!$B${lin}")
        pos[pid] = lin
    ws.column_dimensions["D"].hidden = True
    lin = LIN_1 + len(PARAMETROS) + 1

    def secao(t):
        nonlocal lin
        lin += 1
        cel(ws, (lin, 1), t, F_SECAO)
        lin += 1

    secao("Regras fixas (no script)")
    for a, b in [
        ("Preventiva", "OS com 'PREV' na descrição OU com nº de plano de manutenção."),
        ("Preço do item", "Entrada > negociado > estimado (R$ 1,00 do TracOS é ignorado como 'sem preço') > "
                          "preço do mesmo material em outra linha do fluxo ('ref.')."),
        ("Valor do item", "Quantidade × preço unitário. A requisição e o pedido não trazem preço por item: "
                          "itens sem preço ficam sem valor."),
        ("Dias na etapa", "Etapas 1/2: 'Criado em' da requisição (no nível 02, a partir da 1ª vez que o script "
                          "viu o item no nível 02). Etapa 3: 1ª vez que o script viu o item autorizado. "
                          "Etapa 4: 'Criado em' do pedido. Etapa 5: data da entrada."),
        ("Chave das observações", "Material | requisição | OS (+ sequencial quando o mesmo trio se repete)."),
    ]:
        cel(ws, (lin, 1), a, F_NEGRITO)
        cel(ws, (lin, 2), b, F_NORMAL)
        lin += 1

    secao("Legenda – status de risco (em ordem de prioridade)")
    for p_, txt in cz.STATUS.items():
        fundo, letra = next((f, l) for w, f, l in CORES_STATUS if w in txt)
        cel(ws, (lin, 1), txt, Font(name=FONTE, bold=True, color=letra),
            preench=PatternFill("solid", fgColor=fundo))
        cel(ws, (lin, 2), f"Prioridade {p_}", F_NORMAL)
        cel(ws, (lin, 3), DESCR_STATUS[p_], F_NORMAL)
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
    for k, txt in cz.CONFIANCA.items():
        cel(ws, (lin, 1), txt, F_NEGRITO)
        cel(ws, (lin, 2), expl[k], F_NORMAL)
        lin += 1

    secao("Esta atualização")
    cel(ws, (lin, 1), "Gerado em", F_NEGRITO)
    cel(ws, (lin, 2), dt.datetime.now().replace(microsecond=0), F_NORMAL, fmt=FMT_DATAHORA,
        alin=Alignment(horizontal="left"))
    lin += 1
    cel(ws, (lin, 1), "Observações reaproveitadas de", F_NEGRITO)
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
    return pos


def aba_followup(wb, L, obs):
    ws = wb.create_sheet("Follow-up")
    ws.sheet_properties.tabColor = "548235"
    titulo(ws, "Follow-up de peças por OS",
           "Ordenado por prioridade de risco e data de necessidade no momento da geração. "
           "Status, dias e valores recalculam com a data de referência (Parâmetros). "
           "Coluna amarela = sua observação (preservada nas próximas atualizações).")
    colunas = [
        ("Prioridade", 8, "f_prio"), ("Status de risco", 28, "f_status"), ("Etapa nº", 7, "etapa"),
        ("Etapa do funil", 38, "etapa_txt"), ("Quem cobrar", 44, "f_quem"), (COL_OBS, 42, "obs"),
        ("Preventiva", 9, "prev"), ("OS TracOS", 9, "os_tracos"), ("OS SAP", 12, "os_sap"),
        ("Descrição da OS", 42, "descricao_os"), ("Ativo", 36, "ativo"),
        ("Código material", 10, "codigo"), ("Descrição do material", 36, "descricao"),
        ("Qtd", 7, "qtd"), ("Qtd pendente", 9, "qtd_pendente"), ("Un", 5, "unidade"),
        ("Data de necessidade", 12, "data_necessidade"), ("Dias até a necessidade", 11, "f_dias_nec"),
        ("Dias de atraso", 9, "f_atraso"), ("Início da etapa", 12, "inicio_etapa"),
        ("Base do início da etapa", 30, "base_inicio"), ("Dias na etapa atual", 10, "f_dias_etapa"),
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
    cabecalho(ws, LIN_CAB, [c[0] for c in colunas], [c[1] for c in colunas])
    L_ = {c[2]: get_column_letter(j) for j, c in enumerate(colunas, 1)}
    E, N, DN, DE, I, Q, PR, FO, PS, P = (L_[k] for k in (
        "etapa", "data_necessidade", "f_dias_nec", "f_dias_etapa", "inicio_etapa", "qtd", "preco",
        "fornecedor", "pedido_sap", "f_prio"))
    status_txt = ",".join(f'"{cz.STATUS[i]}"' for i in range(1, 8))
    formulas = {
        "f_prio": (f'=IF({E}{{r}}=5,6,IF(AND({N}{{r}}<>"",N({DN}{{r}})<0),1,'
                   f'IF(AND({E}{{r}}<=2,N({DE}{{r}})>IF({E}{{r}}=1,X_NIVEL01,X_NIVEL02)),2,'
                   f'IF(AND({E}{{r}}=3,N({DE}{{r}})>Y_SEM_PEDIDO),3,'
                   f'IF(AND({E}{{r}}=4,{N}{{r}}<>"",N({DN}{{r}})<=Z_ENTREGA),4,'
                   f'IF({N}{{r}}="",7,5))))))'),
        "f_status": f"=CHOOSE({P}{{r}},{status_txt})",
        "f_quem": (f'=CHOOSE({E}{{r}},"Gestor da unidade"&IF(NOME_GESTOR="",""," – "&NOME_GESTOR),'
                   f'"Almox corporativo"&IF(NOME_ALMOX="",""," – "&NOME_ALMOX),'
                   f'"Comprador"&IF(NOME_COMPRADOR="",""," – "&NOME_COMPRADOR)&" (emitir o pedido)",'
                   f'IF({FO}{{r}}="","Comprador (pedido sem fornecedor)","Fornecedor: "&{FO}{{r}}'
                   f'&IF({PS}{{r}}="",""," – pedido SAP "&{PS}{{r}})),'
                   f'"Ninguém – material entregue")'),
        "f_dias_nec": f'=IF({N}{{r}}="","",{N}{{r}}-INT(DATA_REF))',
        "f_atraso": f'=IF(AND({E}{{r}}<5,{N}{{r}}<>""),MAX(0,INT(DATA_REF)-{N}{{r}}),0)',
        "f_dias_etapa": f'=IF({I}{{r}}="","",INT(DATA_REF)-INT({I}{{r}}))',
        "f_valor": f'=IF(OR({Q}{{r}}="",{PR}{{r}}=""),"",{Q}{{r}}*{PR}{{r}})',
    }
    fmts = {"data_necessidade": FMT_DATA, "inicio_etapa": FMT_DATA, "entrada_em": FMT_DATA,
            "preco": FMT_RS, "f_valor": FMT_RS, "f_dias_nec": FMT_DIAS, "f_dias_etapa": "0",
            "f_atraso": FMT_ATRASO, "qtd": "General", "qtd_pendente": "General"}
    centro = {"f_prio", "etapa", "prev", "os_tracos", "codigo", "qtd", "qtd_pendente", "unidade",
              "f_dias_nec", "f_atraso", "f_dias_etapa", "requisicao_txt", "pedido", "entrada"}
    for i, (_, l) in enumerate(L.iterrows()):
        r = LIN_1 + i
        for j, (_, _, k) in enumerate(colunas, 1):
            if k in formulas:
                v = formulas[k].format(r=r)
            elif k == "obs":
                v = obs.get(l["chave"])
            elif k == "prev":
                v = "SIM" if l["eh_preventiva"] else "NÃO"
            else:
                v = l[k]
            cel(ws, (r, j), v, F_NORMAL, fmt=fmts.get(k),
                preench=P_EDITAVEL if k == "obs" else None,
                alin=AL_CENTRO if k in centro else AL_TOPO)
    ult = max(LIN_1 + len(L) - 1, LIN_1)
    ultcol = get_column_letter(len(colunas))
    ws.auto_filter.ref = f"A{LIN_CAB}:{ultcol}{ult}"
    ws.freeze_panes = f"C{LIN_1}"
    cf_status(ws, f"{L_['f_status']}{LIN_1}:{L_['f_status']}{ult}", f"${L_['f_status']}{LIN_1}")
    ws.conditional_formatting.add(f"{DN}{LIN_1}:{DN}{ult}", CellIsRule(
        operator="lessThan", formula=["0"], font=Font(name=FONTE, color="9C0006", bold=True)))
    ws.conditional_formatting.add(f"{L_['f_atraso']}{LIN_1}:{L_['f_atraso']}{ult}", CellIsRule(
        operator="greaterThan", formula=["0"], font=Font(name=FONTE, color="9C0006", bold=True)))
    paisagem(ws, caber_largura=False)
    rng = {k: f"'Follow-up'!${c}${LIN_1}:${c}${ult}" for k, c in L_.items()}
    return rng


def aba_por_os(wb, por_os, fu, obs):
    ws = wb.create_sheet("Por OS")
    ws.sheet_properties.tabColor = "2F75B5"
    titulo(ws, "Peças por OS (preventivas em destaque)",
           "Peças = itens do Follow-up. Se a exportação do fluxo estiver incompleta, a OS pode ter mais "
           "peças do que aparece aqui.")
    cols = ["OS TracOS", "OS SAP", "Descrição da OS", "Preventiva", "Ativo", "PRONTA PARA EXECUTAR?",
            "Data de necessidade", "Dias até a necessidade", "Total de peças", "Peças entregues",
            "Peças pendentes", "Peças em risco 🔴", "Valor pendente (R$)", "Situação das peças",
            "Plano", "Centro de custo", COL_OBS]
    cabecalho(ws, LIN_CAB, cols, [9, 12, 42, 10, 38, 13, 12, 11, 9, 9, 9, 10, 14, 34, 8, 28, 40])
    for i, (_, o) in enumerate(por_os.iterrows()):
        r = LIN_1 + i
        a = f"$A{r}"
        vals = [
            o["os_tracos"], o["os_sap"], o["descricao_os"], "SIM" if o["preventiva"] else "NÃO", o["ativo"],
            f'=IF(K{r}=0,"SIM","NÃO")', o["data_necessidade"],
            f'=IF(G{r}="","",G{r}-INT(DATA_REF))',
            f"=COUNTIFS({fu['os_tracos']},{a})",
            f"=COUNTIFS({fu['os_tracos']},{a},{fu['etapa']},5)",
            f"=I{r}-J{r}",
            f'=COUNTIFS({fu["os_tracos"]},{a},{fu["f_prio"]},"<=2")',
            f'=SUMIFS({fu["f_valor"]},{fu["os_tracos"]},{a},{fu["etapa"]},"<5")',
            o["situacao"], o["plano"], o["centro_custo"], obs.get(str(int(o["os_tracos"]))),
        ]
        fm = {7: FMT_DATA, 8: FMT_DIAS, 13: FMT_RS}
        for j, v in enumerate(vals, 1):
            cel(ws, (r, j), v, F_NEGRITO if j == 6 else F_NORMAL, fmt=fm.get(j),
                preench=P_EDITAVEL if j == len(cols) else None,
                alin=AL_CENTRO if j in (1, 4, 6, 8, 9, 10, 11, 12, 15) else AL_TOPO)
    ult = max(LIN_1 + len(por_os) - 1, LIN_1)
    ws.auto_filter.ref = f"A{LIN_CAB}:{get_column_letter(len(cols))}{ult}"
    ws.freeze_panes = f"D{LIN_1}"
    ws.conditional_formatting.add(f"A{LIN_1}:E{ult}", FormulaRule(
        formula=[f'$D{LIN_1}="SIM"'], fill=P_PREV, font=Font(name=FONTE, bold=True)))
    ws.conditional_formatting.add(f"F{LIN_1}:F{ult}", FormulaRule(
        formula=[f'F{LIN_1}="SIM"'], fill=PatternFill("solid", fgColor="C6EFCE", bgColor="C6EFCE"),
        font=Font(name=FONTE, bold=True, color="006100")))
    ws.conditional_formatting.add(f"F{LIN_1}:F{ult}", FormulaRule(
        formula=[f'F{LIN_1}="NÃO"'], fill=PatternFill("solid", fgColor="FFC7CE", bgColor="FFC7CE"),
        font=Font(name=FONTE, bold=True, color="9C0006")))
    ws.conditional_formatting.add(f"H{LIN_1}:H{ult}", CellIsRule(
        operator="lessThan", formula=["0"], font=Font(name=FONTE, color="9C0006", bold=True)))
    paisagem(ws)
    return {"os": f"'Por OS'!$A${LIN_1}:$A${ult}", "prev": f"'Por OS'!$D${LIN_1}:$D${ult}",
            "data": f"'Por OS'!$G${LIN_1}:$G${ult}", "dias": f"'Por OS'!$H${LIN_1}:$H${ult}",
            "pend": f"'Por OS'!$K${LIN_1}:$K${ult}"}


def aba_por_fornecedor(wb, pf, fu, obs):
    ws = wb.create_sheet("Por Fornecedor")
    ws.sheet_properties.tabColor = "BF8F00"
    titulo(ws, "Pedidos abertos por fornecedor (para cobrança)",
           "Pedidos e valor vêm da base de pedidos (inclui itens sem OS). Itens vencidos e atraso vêm do "
           "Follow-up (data de necessidade já passou e o pedido não entrou).")
    cols = ["Fornecedor", "Pedidos abertos", "Pedidos (TracOS / SAP)", "Itens em aberto",
            "Itens no follow-up (etapa 4)", "Itens com necessidade vencida", "Atraso mais antigo (dias)",
            "Valor em aberto (R$)", "Pedido mais antigo (emissão)", "Dias desde a emissão", "OS afetadas",
            "Itens sem OS identificada", COL_OBS]
    cabecalho(ws, LIN_CAB, cols, [38, 9, 48, 9, 11, 11, 10, 14, 13, 10, 22, 10, 40])
    for i, (_, x) in enumerate(pf.iterrows()):
        r = LIN_1 + i
        a = f"$A{r}"
        vals = [
            x["fornecedor"], x["n_pedidos"], x["pedidos"], x["itens_abertos"],
            f"=COUNTIFS({fu['fornecedor']},{a},{fu['etapa']},4)",
            f"=COUNTIFS({fu['fornecedor']},{a},{fu['etapa']},4,{fu['f_prio']},1)",
            f"=SUMPRODUCT(MAX(({fu['fornecedor']}={a})*({fu['etapa']}=4)*{fu['f_atraso']}))",
            x["valor_aberto"], x["pedido_mais_antigo"],
            f'=IF(I{r}="","",INT(DATA_REF)-INT(I{r}))', x["os_afetadas"], x["itens_sem_os"],
            obs.get(str(x["fornecedor"])),
        ]
        fm = {7: FMT_ATRASO, 8: FMT_RS, 9: FMT_DATA}
        for j, v in enumerate(vals, 1):
            cel(ws, (r, j), v, F_NEGRITO if j == 1 else F_NORMAL, fmt=fm.get(j),
                preench=P_EDITAVEL if j == len(cols) else None,
                alin=AL_TOPO if j in (1, 3, 11, 13) else AL_CENTRO)
    ult = max(LIN_1 + len(pf) - 1, LIN_1)
    ws.auto_filter.ref = f"A{LIN_CAB}:{get_column_letter(len(cols))}{ult}"
    ws.freeze_panes = f"B{LIN_1}"
    ws.conditional_formatting.add(f"F{LIN_1}:G{ult}", CellIsRule(
        operator="greaterThan", formula=["0"], fill=PatternFill("solid", fgColor="FFC7CE", bgColor="FFC7CE"),
        font=Font(name=FONTE, color="9C0006", bold=True)))
    paisagem(ws)
    return ult


def aba_divergencias(wb, D, obs_dv, orfas):
    ws = wb.create_sheet("Divergências")
    ws.sheet_properties.tabColor = "C00000"
    titulo(ws, "Divergências e registros não casados",
           "As linhas 'NÃO CASADO' são as únicas que NÃO estão no Follow-up (contam na conciliação). "
           "As demais apontam para uma linha do Follow-up pela Chave.")
    cols = ["Tipo", "Gravidade", "Base", "Linha de origem", COL_CHAVE, "Está no Follow-up?",
            "Código material", "Descrição do material", "Requisição", "Pedido", "OS TracOS", "Fornecedor",
            "Detalhe", COL_OBS]
    cabecalho(ws, LIN_CAB, cols, [40, 9, 11, 9, 24, 10, 10, 34, 10, 8, 9, 34, 90, 40])
    regs = [] if D is None or not len(D) else D.to_dict("records")
    regs += orfas
    for i, d in enumerate(regs):
        r = LIN_1 + i
        k = f"{d['tipo']}|{d.get('chave')}"
        vals = [d["tipo"], d["gravidade"], d["base"], d.get("linha"), d.get("chave"), d.get("no_followup"),
                d.get("codigo"), d.get("descricao"), d.get("requisicao"), d.get("pedido"), d.get("os"),
                d.get("fornecedor"), d.get("detalhe"),
                d.get("obs") if d["tipo"] == TIPO_OBS_ORFA else obs_dv.get(k)]
        for j, v in enumerate(vals, 1):
            cel(ws, (r, j), v, F_NORMAL, preench=P_EDITAVEL if j == len(cols) else None,
                alin=AL_CENTRO if j in (2, 4, 6, 7, 9, 10, 11) else AL_TOPO)
    ult = max(LIN_1 + len(regs) - 1, LIN_1)
    ws.auto_filter.ref = f"A{LIN_CAB}:{get_column_letter(len(cols))}{ult}"
    ws.freeze_panes = f"B{LIN_1}"
    for g, fundo, letra in (("Alta", "FFC7CE", "9C0006"), ("Média", "FFE699", "7F6000"),
                            ("Info", "E7E6E6", "404040")):
        ws.conditional_formatting.add(f"B{LIN_1}:B{ult}", FormulaRule(
            formula=[f'$B{LIN_1}="{g}"'], fill=PatternFill("solid", fgColor=fundo, bgColor=fundo),
            font=Font(name=FONTE, color=letra, bold=True)))
    ws.conditional_formatting.add(f"A{LIN_1}:A{ult}", FormulaRule(
        formula=[f'LEFT($A{LIN_1},10)="NÃO CASAD"'], font=Font(name=FONTE, color="9C0006", bold=True)))
    paisagem(ws)


def aba_painel(wb, R, fu, po, ult_forn):
    ws = wb.create_sheet("Painel", 0)
    ws.sheet_properties.tabColor = "1F3864"
    L, pf, reqs = R["linhas"], R["por_fornecedor"], R["requisicoes"]
    titulo(ws, "Follow-up de peças – manutenção preventiva")
    for col, w in zip("ABCDEFGHIJ", [46, 13, 16, 14, 16, 13, 12, 40, 10, 12]):
        ws.column_dimensions[col].width = w
    cel(ws, "A2", "Data de referência", F_NEGRITO)
    cel(ws, "B2", "=DATA_REF", F_NEGRITO, fmt=FMT_DATA, alin=Alignment(horizontal="left"))
    cel(ws, "C2", "Gerado em", F_NOTA)
    cel(ws, "D2", dt.datetime.now().replace(microsecond=0), F_NOTA, fmt=FMT_DATAHORA,
        alin=Alignment(horizontal="left"))
    lin = 3
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

    # 1. funil
    secao("1. Funil de compras por etapa", "Valor só dos itens com preço conhecido (ver 'Itens sem preço').")
    cab(["Etapa", "Itens", "Valor (R$)", "Itens preventiva", "Valor preventiva (R$)", "Itens sem preço"])
    ini = lin
    for e, txt in cz.ETAPAS.items():
        vals = [txt,
                f"=COUNTIFS({fu['etapa']},{e})",
                f"=SUMIFS({fu['f_valor']},{fu['etapa']},{e})",
                f'=COUNTIFS({fu["etapa"]},{e},{fu["prev"]},"SIM")',
                f'=SUMIFS({fu["f_valor"]},{fu["etapa"]},{e},{fu["prev"]},"SIM")',
                f'=B{lin}-COUNTIFS({fu["etapa"]},{e},{fu["preco"]},"<>")']
        for j, v in enumerate(vals, 1):
            cel(ws, (lin, j), v, fmt=FMT_RS if j in (3, 5) else None)
        lin += 1
    for j, v in enumerate(["Total"] + [f"=SUM({c}{ini}:{c}{lin - 1})" for c in "BCDEF"], 1):
        cel(ws, (lin, j), v, F_NEGRITO, fmt=FMT_RS if j in (3, 5) else None, preench=P_TOTAL)
    lin += 1

    # 2. status
    secao("2. Itens por status de risco")
    cab(["Status de risco", "Itens", "Itens preventiva", "Valor (R$)"])
    ini = lin
    for p_, txt in cz.STATUS.items():
        fundo, letra = next((f, l) for w, f, l in CORES_STATUS if w in txt)
        cel(ws, (lin, 1), txt, Font(name=FONTE, bold=True, color=letra), preench=PatternFill("solid", fgColor=fundo))
        cel(ws, (lin, 2), f"=COUNTIFS({fu['f_prio']},{p_})")
        cel(ws, (lin, 3), f'=COUNTIFS({fu["f_prio"]},{p_},{fu["prev"]},"SIM")')
        cel(ws, (lin, 4), f"=SUMIFS({fu['f_valor']},{fu['f_prio']},{p_})", fmt=FMT_RS)
        lin += 1
    for j, v in enumerate(["Total"] + [f"=SUM({c}{ini}:{c}{lin - 1})" for c in "BCD"], 1):
        cel(ws, (lin, j), v, F_NEGRITO, fmt=FMT_RS if j == 4 else None, preench=P_TOTAL)
    lin += 1

    # 3. OS preventivas
    secao("3. OS preventivas com peças pendentes", "Janela pela data de necessidade (contagem acumulada).")
    cab(["Janela", "OS", "Peças pendentes"])
    base = f'{po["prev"]},"SIM",{po["pend"]},">0"'
    janelas = [
        ("Necessidade já vencida", f'{po["dias"]},"<0"'),
        ("Próximos 7 dias", f'{po["dias"]},">=0",{po["dias"]},"<=7"'),
        ("Próximos 15 dias", f'{po["dias"]},">=0",{po["dias"]},"<=15"'),
        ("Próximos 30 dias", f'{po["dias"]},">=0",{po["dias"]},"<=30"'),
    ]
    for rot, crit in janelas:
        cel(ws, (lin, 1), rot)
        cel(ws, (lin, 2), f"=COUNTIFS({base},{crit})")
        cel(ws, (lin, 3), f"=SUMIFS({po['pend']},{base},{crit})")
        lin += 1
    cel(ws, (lin, 1), "Sem data de necessidade (só requisição)")
    cel(ws, (lin, 2), f'=COUNTIFS({base})-COUNTIFS({base},{po["data"]},"<>")')
    cel(ws, (lin, 3), f'=SUMIFS({po["pend"]},{base})-SUMIFS({po["pend"]},{base},{po["data"]},"<>")')
    lin += 1
    cel(ws, (lin, 1), "Total de OS preventivas com peças pendentes", F_NEGRITO, preench=P_TOTAL)
    cel(ws, (lin, 2), f"=COUNTIFS({base})", F_NEGRITO, preench=P_TOTAL)
    cel(ws, (lin, 3), f"=SUMIFS({po['pend']},{base})", F_NEGRITO, preench=P_TOTAL)
    lin += 1

    # 4. fornecedores
    secao("4. Ranking de fornecedores com pedidos atrasados",
          "Ordem calculada na geração; números recalculam com a data de referência.")
    cab(["Fornecedor", "Pedidos abertos", "Itens com necessidade vencida", "Atraso mais antigo (dias)",
         "Valor em aberto (R$)"])
    atrasados = [i for i, (_, x) in enumerate(pf.iterrows()) if x["_atraso"] > 0] if len(pf) else []
    if not atrasados:
        cel(ws, (lin, 1), "Nenhum fornecedor com itens atrasados.", F_NOTA)
        lin += 1
    for i in atrasados[:10]:
        rf = LIN_1 + i
        for j, c in enumerate("ABFGH", 1):
            cel(ws, (lin, j), f"='Por Fornecedor'!{c}{rf}", F_NEGRITO if j == 1 else F_NORMAL,
                fmt={4: FMT_ATRASO, 5: FMT_RS}.get(j))
        lin += 1

    # 5. requisições paradas
    secao("5. Requisições paradas por nível de aprovação")
    cab(["Nível", "Requisições pendentes", "Itens", "Itens parados (> X dias)", "Dias da mais antiga"])
    for e, rot in ((1, "01 - Gestor da unidade"), (2, "02 - Almox corporativo")):
        n_req = int((reqs["etapa"] == e).sum()) if len(reqs) else 0
        cel(ws, (lin, 1), rot, F_NEGRITO)
        cel(ws, (lin, 2), n_req)
        cel(ws, (lin, 3), f"=COUNTIFS({fu['etapa']},{e})")
        cel(ws, (lin, 4), f"=COUNTIFS({fu['etapa']},{e},{fu['f_prio']},2)")
        cel(ws, (lin, 5), f"=SUMPRODUCT(MAX(({fu['etapa']}={e})*{fu['f_dias_etapa']}))")
        lin += 1
    lin += 1
    cab(["OS / ativo", "Requisição", "Req. SAP", "Nível", "Itens", "Início", "Dias parada", "Situação",
         "Preventiva"])
    for e in (1, 2):
        sub = reqs[reqs["etapa"] == e].head(10) if len(reqs) else reqs
        lim = "X_NIVEL01" if e == 1 else "X_NIVEL02"
        for _, q in sub.iterrows():
            os_txt = f"#{int(q['os_tracos'])} {q['descricao_os']}" if not pd.isna(q["os_tracos"]) else ""
            vals = [os_txt + (f" – {q['ativo']}" if isinstance(q["ativo"], str) else ""),
                    f"#{int(q['requisicao'])}", q["req_sap"], "01" if e == 1 else "02", q["itens"],
                    q["inicio"], f"=INT(DATA_REF)-INT(F{lin})",
                    f'=IF(G{lin}>{lim},"🔴 PARADA","dentro do prazo")', "SIM" if q["preventiva"] else "NÃO"]
            for j, v in enumerate(vals, 1):
                cel(ws, (lin, j), v, fmt=FMT_DATA if j == 6 else None,
                    alin=AL_TOPO if j == 1 else AL_CENTRO)
            lin += 1
    ws.conditional_formatting.add(f"H1:H{lin}", FormulaRule(
        formula=['ISNUMBER(SEARCH("PARADA",H1))'], font=Font(name=FONTE, color="9C0006", bold=True)))
    ws.freeze_panes = "A3"
    paisagem(ws)


def aba_bases(wb, B):
    ws = wb.create_sheet("Bases tratadas")
    ws.sheet_properties.tabColor = "A6A6A6"
    titulo(ws, "Bases tratadas (auditoria)",
           "As 3 exportações já normalizadas. 'linha_origem' = linha no CSV (1 = cabeçalho); é a "
           "referência usada em 'Linhas de origem' no Follow-up e em Divergências.")
    lin = 4
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


def aba_historico(wb, hist):
    ws = wb.create_sheet("_historico")
    ws.append(["Chave", "Etapa", "Desde"])
    for k, (e, d) in sorted(hist.items()):
        ws.append([k, e, val(d)])
    for c in ws["C"][1:]:
        c.number_format = FMT_DATAHORA
    ws.sheet_state = "hidden"


# ------------------------------------------------------------------ principal
def gerar(pasta_bases, pasta_saida, hoje=None, data_fixa=None, silencioso=False):
    hoje = pd.Timestamp(hoje or dt.date.today()).normalize()
    os.makedirs(pasta_saida, exist_ok=True)
    B = tb.carregar_bases(pasta_bases)
    ant = ler_versao_anterior(pasta_saida)
    prm = {k: v for k, v in ant["prm"].items()}
    R = cz.cruzar(B, hoje, ant["historico"], {k: v for k, v in prm.items() if not k.startswith("nome_")})

    # observações cujo item sumiu: não se perdem, vão para Divergências
    obs = ant["obs"]
    orfas = []
    chaves_atuais = {
        "Follow-up": set(R["linhas"]["chave"]),
        "Por OS": {str(int(x)) for x in R["por_os"]["os_tracos"]} if len(R["por_os"]) else set(),
        "Por Fornecedor": set(R["por_fornecedor"]["fornecedor"]) if len(R["por_fornecedor"]) else set(),
        "Divergências": ({f"{t}|{c}" for t, c in zip(R["divergencias"]["tipo"], R["divergencias"]["chave"])}
                         if len(R["divergencias"]) else set()),
    }
    for aba, d in obs.items():
        for k, texto in d.items():
            if k not in chaves_atuais[aba]:
                orfas.append(dict(tipo=TIPO_OBS_ORFA, gravidade="Info", base=aba, linha=None,
                                  chave=k if aba != "Divergências" else None, no_followup="NÃO",
                                  detalhe=k, obs=texto))

    wb = Workbook()
    wb.remove(wb.active)
    pos = aba_parametros(wb, {**cz.PARAMETROS_PADRAO, **prm}, B, R, hoje, data_fixa, ant)
    fu = aba_followup(wb, R["linhas"], obs["Follow-up"])
    po = aba_por_os(wb, R["por_os"], fu, obs["Por OS"])
    ult_forn = aba_por_fornecedor(wb, R["por_fornecedor"], fu, obs["Por Fornecedor"])
    aba_divergencias(wb, R["divergencias"], obs["Divergências"], orfas)
    aba_painel(wb, R, fu, po, ult_forn)
    aba_bases(wb, B)
    aba_historico(wb, R["historico"])
    ordem = ["Painel", "Follow-up", "Por OS", "Por Fornecedor", "Divergências", "Parâmetros",
             "Bases tratadas", "_historico"]
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
    L = R["linhas"]
    print("=" * 78)
    print("FOLLOW-UP DE PEÇAS – atualização concluída")
    print("=" * 78)
    print(f"Arquivo gerado: {destino}")
    print(f"Observações reaproveitadas de: {os.path.basename(ant['arquivo']) if ant['arquivo'] else '(primeira versão)'}"
          f"  |  {sum(len(v) for v in ant['obs'].values())} observações lidas, {len(orfas)} sem item atual")
    print("\nConciliação (entrada = Follow-up + Divergências não casadas):")
    for _, c in R["conciliacao"].iterrows():
        print(f"  {c['base']:<11} entrada {c['entrada']:>4} | follow-up {c['follow_up']:>4} | "
              f"divergências {c['divergencias']:>3} | {'OK' if c['ok'] else 'DIFERENÇA!'}")
    print("\nItens por etapa:")
    for e, n in L["etapa"].value_counts().sort_index().items():
        print(f"  {cz.ETAPAS[e]:<46} {n:>4}")
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
