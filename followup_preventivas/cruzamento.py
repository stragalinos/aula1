"""ETAPAS 1 e 2 - cruzamento das 3 bases do TracOS (+ IWBK do SAP), etapa do funil e status de risco.

Grão da tabela: uma linha por material x requisição x OS (com sequencial quando o mesmo trio se
repete). Toda linha de entrada termina em exatamente um lugar: numa linha do Follow-up
(coluna "Linhas de origem") ou na aba Divergências como NÃO CASADO. Componentes da IWBK que não casam
com o TracOS (RC só no SAP, itens de estoque) viram linhas próprias com origem "SAP".
"""
import numpy as np
import pandas as pd

ETAPAS = {
    0: "0 - Falta em estoque (reserva SAP)",
    1: "1 - Aguardando aprovação (gestor nível 01 / RC SAP)",
    2: "2 - Aguardando almox corporativo (nível 02)",
    3: "3 - Compra autorizada / RC liberada (sem pedido)",
    4: "4 - Pedido emitido (aguardando entrega)",
    5: "5 - Entregue / disponível",
}

# prioridade -> texto (a ordem é a prioridade do status de risco)
STATUS = {
    1: "🔴 NECESSIDADE VENCIDA",
    2: "🔴 PARADA NA APROVAÇÃO",
    3: "🟠 SEM PEDIDO",
    4: "🟠 ENTREGA EM RISCO",
    5: "🟢 NO PRAZO",
    6: "✅ ENTREGUE",
    7: "⚪ SEM DATA DE NECESSIDADE",
}

# situação na aba Recebimento (a ordem é a ordem de exibição)
SITUACAO_REC = {
    0: "🚚 A CAMINHO – ATRASADO",
    1: "🚚 A CAMINHO",
    6: "📦 FALTA EM ESTOQUE",
    2: "🟡 RECEBIDO PARCIAL",
    3: "⛔ NÃO RECEBIDO",
    4: "✅ RECEBIDO (manual)",
    5: "✅ RECEBIDO (TracOS/SAP)",
}
RECEBIMENTO_OPCOES = ("SIM", "PARCIAL", "NÃO")

PARAMETROS_PADRAO = {"x_nivel01": 3, "x_nivel02": 5, "y_sem_pedido": 2, "z_entrega": 5}

# o TracOS preenche o preço estimado com R$ 1,00 quando ninguém informou o preço
PRECO_PLACEHOLDER = 1.0

CONFIANCA = {
    "R1": "Alta – material + requisição + pedido",
    "R2": "Média – material + requisição",
    "R3": "Média – material + pedido",
    "R4": "Baixa – material + OS",
    "R5": "Baixa – OS inferida pela requisição",
    "SO_REQ": "Só requisição – pendente (sem vínculo esperado)",
    "SO_FLX": "Só fluxo – compra autorizada, sem pedido",
    "FLX_SEM_PED": "Só fluxo – pedido não encontrado na base de pedidos",
    "S1": "SAP – OS + material + RC",
    "S2": "SAP – OS + material + pedido",
    "S3": "SAP – OS + material",
    "S4": "SAP – material + RC",
    "S5": "SAP – material + pedido",
    "SO_SAP": "Só SAP (IWBK) – compra sem item no TracOS",
    "SO_SAP_L": "Só SAP (IWBK) – componente de estoque",
}
REGRAS_SAP = [("S1", ["os_sap", "codigo", "rc_n"]), ("S2", ["os_sap", "codigo", "pedido_sap"]),
              ("S3", ["os_sap", "codigo"]), ("S4", ["codigo", "rc_n"]), ("S5", ["codigo", "pedido_sap"])]
CAMPOS_SAP = ["categoria", "disponibilidade", "qtd_retirada", "data_remessa", "reserva"]


def _na(v):
    try:
        return v is None or bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _int(v):
    return None if _na(v) else int(v)


def _casar(a, b, chaves, usados_a, usados_b):
    """Casa 1:1 as linhas ainda livres de A e B pelas chaves. Retorna {idx_a: (idx_b, n_candidatos)}."""
    indice = {}
    for j, row in b[chaves].iterrows():
        if j in usados_b:
            continue
        k = tuple(row)
        if any(_na(x) for x in k):
            continue
        indice.setdefault(tuple(str(x) for x in k), []).append(j)
    res = {}
    for i, row in a[chaves].iterrows():
        if i in usados_a:
            continue
        k = tuple(row)
        if any(_na(x) for x in k):
            continue
        cands = [j for j in indice.get(tuple(str(x) for x in k), []) if j not in usados_b]
        if cands:
            res[i] = (cands[0], len(cands))
            usados_a.add(i)
            usados_b.add(cands[0])
    return res


def _etapa_pedido(status):
    s = str(status or "").lower()
    return 5 if ("conclu" in s or "entreg" in s or "recebid" in s) else 4


def _etapa_fluxo(fx):
    st = str(fx["status_fluxo"] or "").lower()
    if not _na(fx["entrada"]) or (not _na(fx["qtd_pendente"]) and fx["qtd_pendente"] == 0) \
            or "conclu" in st or "entreg" in st or "recebid" in st:
        return 5
    if "pedido" in st or not _na(fx["pedido"]):
        return 4
    return 3


def _ativo_txt(tag, nome):
    if _na(tag) and _na(nome):
        return None
    return f"{tag} - {nome}" if not _na(tag) else str(nome)


def _preco_linha(fx):
    """Preço unitário e origem a partir da linha do fluxo."""
    if fx is None:
        return None, None
    if not _na(fx["preco_entrada"]):
        return float(fx["preco_entrada"]), "entrada"
    if not _na(fx["preco_negociado"]):
        return float(fx["preco_negociado"]), "negociado"
    if not _na(fx["preco_estimado"]) and fx["preco_estimado"] != PRECO_PLACEHOLDER:
        return float(fx["preco_estimado"]), "estimado"
    return None, None


def dias(d1, d0):
    """Dias inteiros entre duas datas (ignora hora), como INT(d1)-INT(d0) no Excel."""
    if _na(d1) or _na(d0):
        return None
    return (pd.Timestamp(d1).normalize() - pd.Timestamp(d0).normalize()).days


def prioridade(etapa, data_nec, inicio, hoje, prm, disponivel=None):
    """Espelho em Python da fórmula de risco da planilha (usado para ordenar e validar)."""
    d_etapa = dias(hoje, inicio)
    d_nec = dias(data_nec, hoje)
    if disponivel is None:
        disponivel = etapa == 5
    if disponivel:
        return 6
    if d_nec is not None and d_nec < 0:
        return 1
    if 1 <= etapa <= 2 and (d_etapa or 0) > (prm["x_nivel01"] if etapa == 1 else prm["x_nivel02"]):
        return 2
    if etapa == 3 and (d_etapa or 0) > prm["y_sem_pedido"]:
        return 3
    if etapa in (0, 4) and d_nec is not None and d_nec <= prm["z_entrega"]:
        return 4
    if d_nec is None:
        return 7
    return 5


def marca_recebimento(v):
    """Normaliza o que foi digitado em 'Recebido?' (SIM / PARCIAL / NÃO); outro texto = vazio."""
    if _na(v):
        return None
    t = str(v).strip().upper()
    return t if t in RECEBIMENTO_OPCOES else None


def disponivel(marca, etapa):
    """Item está aqui? Marca manual manda; sem marca vale a entrada registrada no TracOS."""
    if marca == "SIM":
        return True
    if marca in ("PARCIAL", "NÃO"):
        return False
    return etapa == 5


def situacao_recebimento(marca, recebido_tracos, data_nec, hoje, etapa=None):
    """Espelho da fórmula 'Situação' da aba Recebimento."""
    if marca == "SIM":
        return SITUACAO_REC[4]
    if marca == "PARCIAL":
        return SITUACAO_REC[2]
    if marca == "NÃO":
        return SITUACAO_REC[3]
    if recebido_tracos:
        return SITUACAO_REC[5]
    if etapa == 0:
        return SITUACAO_REC[6]
    d = dias(data_nec, hoje)
    return SITUACAO_REC[0] if d is not None and d < 0 else SITUACAO_REC[1]


def cruzar(B, hoje, historico=None, prm=None, manuais=None):
    """Cruza as bases. Retorna dict com linhas (Follow-up), recebimento, divergencias, por_os,
    por_fornecedor, requisicoes, historico novo, alertas e conciliacao.

    manuais = anotações da versão anterior da planilha:
      datas_os    {OS SAP: data de necessidade digitada na aba Por OS}
      recebimento {chave: SIM / PARCIAL / NÃO digitado na aba Recebimento}
      liberadas   {OS SAP já liberadas para a equipe}
    """
    hoje = pd.Timestamp(hoje).normalize()
    historico = historico or {}
    manuais = manuais or {}
    datas_os = {str(k): pd.Timestamp(v).normalize() for k, v in manuais.get("datas_os", {}).items()
                if not _na(v)}
    marcas = {k: marca_recebimento(v) for k, v in manuais.get("recebimento", {}).items()}
    liberadas = {str(k) for k in manuais.get("liberadas", set())}
    prm = {**PARAMETROS_PADRAO, **(prm or {})}
    r = B["requisicao"]["norm"]
    f = B["fluxo"]["norm"]
    p = B["pedido"]["norm"]

    regras = {"R1": ["codigo", "requisicao", "pedido"], "R2": ["codigo", "requisicao"],
              "R3": ["codigo", "pedido"], "R4": ["codigo", "os_tracos"]}

    # 1) fluxo <-> pedido : R1 -> R2 -> R3
    uf, up = set(), set()
    f2p = {}
    for regra in ("R1", "R2", "R3"):
        for i, (j, n) in _casar(f, p, regras[regra], uf, up).items():
            f2p[i] = (j, regra, n)

    # 2) requisição <-> fluxo : R2 -> R4  (hoje dá 0: a requisição sai da base quando vira pedido)
    ur, uf_r = set(), set()
    r2f = {}
    for regra in ("R2", "R4"):
        for i, (j, n) in _casar(r, f, regras[regra], ur, uf_r).items():
            r2f[i] = (j, regra, n)
    f2r = {j: (i, regra, n) for i, (j, regra, n) in r2f.items()}

    # 3) requisição restante <-> pedido restante : R2
    r2p = {}
    for i, (j, n) in _casar(r, p, regras["R2"], ur, up).items():
        r2p[i] = (j, "R2", n)

    # 4) OS por requisição (para inferir a OS de item de pedido que não está no fluxo)
    req_os = {}
    for df in (f, r):
        for req, os_ in df[["requisicao", "os_tracos"]].dropna().itertuples(index=False):
            req_os.setdefault(int(req), set()).add(int(os_))
    os_info = {}
    for df in (f, r):
        for _, row in df.dropna(subset=["os_tracos"]).iterrows():
            os_info.setdefault(int(row["os_tracos"]), row)

    # preço de referência por material (para linhas sem preço próprio)
    preco_ref = {}
    for _, fx in f.iterrows():
        pr, _o = _preco_linha(fx)
        if pr is not None and fx["codigo"] not in preco_ref:
            preco_ref[fx["codigo"]] = pr

    linhas, divs = [], []

    def nova(rq=None, fx=None, pd_=None, conf=None, os_row=None):
        L = {}
        base_os = fx if fx is not None else (rq if rq is not None else os_row)
        ref = fx if fx is not None else (rq if rq is not None else pd_)
        L["codigo"] = ref["codigo"]
        L["descricao"] = ref["descricao"]
        for c in ("os_tracos", "os_sap", "plano", "descricao_os", "eh_preventiva"):
            L[c] = None if base_os is None else base_os[c]
        L["ativo"] = None
        if rq is not None:
            L["ativo"] = _ativo_txt(rq["ativo_tag"], rq["ativo_nome"])
        if L["ativo"] is None and pd_ is not None:
            L["ativo"] = _ativo_txt(pd_["ativo_tag"], pd_["ativo_nome"])
        if fx is not None:
            L["qtd"], L["unidade"], L["qtd_pendente"] = fx["qtd"], fx["unidade"], fx["qtd_pendente"]
        elif rq is not None:
            L["qtd"], L["unidade"], L["qtd_pendente"] = rq["qtd"], rq["unidade"], rq["qtd"]
        else:
            L["qtd"] = L["unidade"] = L["qtd_pendente"] = None
        L["data_nec_tracos"] = fx["data_necessidade"] if fx is not None else None
        if fx is not None:
            L["requisicao"], L["req_item"] = fx["requisicao"], fx["req_item"]
        else:
            L["requisicao"] = (rq if rq is not None else pd_)["requisicao"]
            L["req_item"] = None
        L["req_sap"] = rq["req_sap"] if rq is not None else None
        L["nivel_liberacao"] = rq["nivel_liberacao"] if rq is not None else None
        L["grupo_compradores"] = rq["grupo_compradores"] if rq is not None else None
        L["criado_req"] = rq["criado_em"] if rq is not None else None
        L["pedido"] = pd_["pedido"] if pd_ is not None else (fx["pedido"] if fx is not None else None)
        L["pedido_sap"] = pd_["pedido_sap"] if pd_ is not None else None
        L["status_pedido"] = pd_["status_pedido"] if pd_ is not None else None
        L["criado_ped"] = pd_["criado_em"] if pd_ is not None else None
        L["atualizado_ped"] = pd_["atualizado_em"] if pd_ is not None else None
        L["fornecedor"] = pd_["fornecedor"] if pd_ is not None else (fx["fornecedor"] if fx is not None else None)
        L["entrada"] = pd_["entrada"] if pd_ is not None and not _na(pd_["entrada"]) else (
            fx["entrada"] if fx is not None else None)
        L["entrada_em"] = pd_["entrada_em"] if pd_ is not None else None
        L["nota_fiscal"] = pd_["nota_fiscal"] if pd_ is not None else None
        L["local_estoque"] = fx["local_estoque"] if fx is not None else None
        L["centro_custo"] = (fx if fx is not None else rq)["centro_custo"] if (fx is not None or rq is not None) else None
        L["status_fluxo"] = fx["status_fluxo"] if fx is not None else None
        L["status_req"] = rq["status_req"] if rq is not None else None
        preco, origem = _preco_linha(fx)
        if preco is None and L["codigo"] in preco_ref:
            preco, origem = preco_ref[L["codigo"]], "ref. (mesmo material no fluxo)"
        L["preco"], L["origem_preco"] = preco, origem
        if pd_ is not None:
            etapa = _etapa_pedido(pd_["status_pedido"])
            if not _na(pd_["entrada"]):
                etapa = 5
        elif fx is not None:
            etapa = _etapa_fluxo(fx)
        else:
            etapa = 2 if str(rq["nivel_liberacao"] or "").startswith("02") else 1
        L["etapa"] = etapa
        L["confianca"] = conf
        L["orig_req"] = _int(rq["linha_origem"]) if rq is not None else None
        L["orig_flx"] = _int(fx["linha_origem"]) if fx is not None else None
        L["orig_ped"] = _int(pd_["linha_origem"]) if pd_ is not None else None
        L["_tem_ped"] = pd_ is not None
        return L

    # linhas a partir do fluxo
    for i, fx in f.iterrows():
        partes = []
        rq = None
        if i in f2r:
            ir, regra, n = f2r[i]
            rq = r.loc[ir]
            partes.append(f"{CONFIANCA[regra]} (req↔fluxo)")
        pd_ = None
        if i in f2p:
            j, regra, n = f2p[i]
            pd_ = p.loc[j]
            partes.append(CONFIANCA[regra] + (" (req↔fluxo↔pedido)" if rq is not None else ""))
            if n > 1:
                divs.append(dict(tipo="VÍNCULO AMBÍGUO", gravidade="Média", base="fluxo",
                                 linha=_int(fx["linha_origem"]), codigo=fx["codigo"],
                                 descricao=fx["descricao"], requisicao=_int(fx["requisicao"]),
                                 pedido=_int(fx["pedido"]), os=_int(fx["os_tracos"]),
                                 fornecedor=fx["fornecedor"],
                                 detalhe=f"Regra {regra}: {n} itens de pedido candidatos; usado o 1º "
                                         f"(linha {_int(pd_['linha_origem'])}).", _ref="linha"))
            if regra != "R1" and not _na(fx["pedido"]) and _int(fx["pedido"]) != _int(pd_["pedido"]):
                divs.append(dict(tipo="PEDIDO DIFERENTE ENTRE FLUXO E PEDIDO", gravidade="Média",
                                 base="fluxo", linha=_int(fx["linha_origem"]), codigo=fx["codigo"],
                                 descricao=fx["descricao"], requisicao=_int(fx["requisicao"]),
                                 pedido=_int(fx["pedido"]), os=_int(fx["os_tracos"]),
                                 fornecedor=fx["fornecedor"],
                                 detalhe=f"Fluxo aponta pedido #{_int(fx['pedido'])}, casado com o "
                                         f"pedido #{_int(pd_['pedido'])} pela regra {regra}.", _ref="linha"))
        elif not _na(fx["pedido"]) or "pedido" in str(fx["status_fluxo"]).lower():
            partes.append(CONFIANCA["FLX_SEM_PED"])
            divs.append(dict(tipo="PEDIDO NÃO ENCONTRADO NA BASE DE PEDIDOS", gravidade="Média",
                             base="fluxo", linha=_int(fx["linha_origem"]), codigo=fx["codigo"],
                             descricao=fx["descricao"], requisicao=_int(fx["requisicao"]),
                             pedido=_int(fx["pedido"]), os=_int(fx["os_tracos"]),
                             fornecedor=fx["fornecedor"],
                             detalhe="Item com pedido no fluxo, mas o pedido não está na exportação de "
                                     "pedidos (sem nº SAP, entrada e NF).", _ref="linha"))
        else:
            partes.append(CONFIANCA["SO_FLX"])
        L = nova(rq=rq, fx=fx, pd_=pd_, conf="; ".join(partes))
        if rq is not None:
            if not _na(rq["qtd"]) and not _na(fx["qtd"]) and rq["qtd"] != fx["qtd"]:
                divs.append(dict(tipo="DIVERGÊNCIA DE QUANTIDADE (req × fluxo)", gravidade="Média",
                                 base="requisição", linha=_int(rq["linha_origem"]), codigo=fx["codigo"],
                                 descricao=fx["descricao"], requisicao=_int(fx["requisicao"]),
                                 pedido=_int(fx["pedido"]), os=_int(fx["os_tracos"]),
                                 fornecedor=fx["fornecedor"],
                                 detalhe=f"Requisição: {rq['qtd']:g} {rq['unidade']} | fluxo: "
                                         f"{fx['qtd']:g} {fx['unidade']}", _ref="linha"))
            if f2r[i][1] == "R4":
                divs.append(dict(tipo="BAIXA CONFIANÇA – material + OS", gravidade="Média",
                                 base="requisição", linha=_int(rq["linha_origem"]), codigo=fx["codigo"],
                                 descricao=fx["descricao"], requisicao=_int(rq["requisicao"]),
                                 pedido=_int(fx["pedido"]), os=_int(fx["os_tracos"]),
                                 fornecedor=fx["fornecedor"],
                                 detalhe=f"Requisição #{_int(rq['requisicao'])} casada com o item "
                                         f"#{_int(fx['requisicao'])}/{_int(fx['req_item'])} do fluxo só "
                                         f"pelo material e OS.", _ref="linha"))
        if pd_ is not None and not _na(fx["fornecedor"]) and fx["fornecedor"] != pd_["fornecedor"]:
            divs.append(dict(tipo="DIVERGÊNCIA DE FORNECEDOR (fluxo × pedido)", gravidade="Alta",
                             base="fluxo", linha=_int(fx["linha_origem"]), codigo=fx["codigo"],
                             descricao=fx["descricao"], requisicao=_int(fx["requisicao"]),
                             pedido=_int(pd_["pedido"]), os=_int(fx["os_tracos"]),
                             fornecedor=pd_["fornecedor"],
                             detalhe=f"Fluxo: {fx['fornecedor']} | pedido: {pd_['fornecedor']}", _ref="linha"))
        linhas.append(L)

    # linhas a partir da requisição (não absorvidas pelo fluxo)
    for i, rq in r.iterrows():
        if i in r2f:
            continue
        if i in r2p:
            j, regra, n = r2p[i]
            linhas.append(nova(rq=rq, pd_=p.loc[j], conf=f"{CONFIANCA[regra]} (req↔pedido)"))
        else:
            linhas.append(nova(rq=rq, conf=CONFIANCA["SO_REQ"]))

    # itens de pedido que sobraram
    orfaos_ped = []
    for j, pd_ in p.iterrows():
        if j in up:
            continue
        oss = req_os.get(_int(pd_["requisicao"]), set())
        if len(oss) == 1:
            os_ = next(iter(oss))
            L = nova(pd_=pd_, conf=f"{CONFIANCA['R5']} #{_int(pd_['requisicao'])}", os_row=os_info[os_])
            linhas.append(L)
            divs.append(dict(tipo="BAIXA CONFIANÇA – OS inferida pela requisição", gravidade="Média",
                             base="pedido", linha=_int(pd_["linha_origem"]), codigo=pd_["codigo"],
                             descricao=pd_["descricao"], requisicao=_int(pd_["requisicao"]),
                             pedido=_int(pd_["pedido"]), os=os_, fornecedor=pd_["fornecedor"],
                             detalhe=f"Item do pedido #{_int(pd_['pedido'])} fora do fluxo. Requisição "
                                     f"#{_int(pd_['requisicao'])} só tem a OS #{os_}; data de necessidade "
                                     f"herdada dos outros itens da OS.", _ref="linha"))
        else:
            orfaos_ped.append(j)
            motivo = ("requisição aponta para várias OS: " + ", ".join(f"#{o}" for o in sorted(oss))
                      if oss else "requisição não aparece no fluxo nem na base de requisição")
            divs.append(dict(tipo="NÃO CASADO – pedido sem OS identificável", gravidade="Alta"
                             if _etapa_pedido(pd_["status_pedido"]) == 4 else "Info",
                             base="pedido", linha=_int(pd_["linha_origem"]), codigo=pd_["codigo"],
                             descricao=pd_["descricao"], requisicao=_int(pd_["requisicao"]),
                             pedido=_int(pd_["pedido"]), os=None, fornecedor=pd_["fornecedor"],
                             detalhe=f"{pd_['status_pedido']} – pedido SAP {pd_['pedido_sap']}"
                                     f"{' – ativo ' + pd_['ativo_nome'] if not _na(pd_['ativo_nome']) else ''}"
                                     f". Sem vínculo com OS ({motivo}).",
                             chave=f"{pd_['codigo']}|R{_int(pd_['requisicao'])}|PED{_int(pd_['pedido'])}",
                             conta=True))

    L = pd.DataFrame(linhas)

    # ativo faltante: ativo mais comum da mesma OS
    ativo_os = (L.dropna(subset=["ativo", "os_tracos"]).groupby("os_tracos")["ativo"]
                .agg(lambda s: s.value_counts().index[0]))
    falta = L["ativo"].isna() & L["os_tracos"].notna()
    L.loc[falta, "ativo"] = L.loc[falta, "os_tracos"].map(ativo_os)
    L["data_nec_tracos"] = pd.to_datetime(L["data_nec_tracos"])
    L["origem_data_tracos"] = pd.Series(np.where(L["data_nec_tracos"].notna(), "TracOS (fluxo)", None),
                                        index=L.index, dtype=object)

    # SAP (IWBK): casa com as linhas do TracOS e acrescenta o que só existe no SAP
    L["origem"] = "TracOS"
    L["orig_sap"] = np.nan
    L["etapa_txt_sap"] = None
    L["sap_consumido"] = False
    for c in CAMPOS_SAP:
        L[c] = np.nan
    L, info_sap = _integrar_iwbk(L, B.get("iwbk"), preco_ref, hoje)

    # data de necessidade: do fluxo/IWBK; sem ela, herda a data dos outros itens da mesma OS
    nec_os = L.dropna(subset=["os_sap", "data_nec_tracos"]).groupby("os_sap")["data_nec_tracos"].min()
    falta = L["data_nec_tracos"].isna() & L["os_sap"].notna() & L["os_sap"].isin(nec_os.index)
    L.loc[falta, "data_nec_tracos"] = L.loc[falta, "os_sap"].map(nec_os)
    L.loc[falta, "origem_data_tracos"] = "Herdada de outro item da OS"

    # chave = material | requisição | OS (+ sequencial quando o trio se repete)
    L["_ord"] = L["req_item"].fillna(0).astype(float) * 1e6 + L["orig_req"].fillna(0) + \
        L["orig_flx"].fillna(0) * 1e3 + L["orig_ped"].fillna(0) * 1e4 + L["orig_sap"].fillna(0)
    L = L.sort_values(["codigo", "requisicao", "os_tracos", "os_sap", "_ord"], na_position="last")
    base_chave = (L["codigo"].astype(str) + "|R" + L["requisicao"].map(lambda v: "-" if _na(v) else str(int(v)))
                  + "|OS" + L["os_tracos"].map(lambda v: "-" if _na(v) else str(int(v))))
    # linha só do SAP: material | RC SAP | OS SAP
    so_sap = L["origem"].eq("SAP")
    base_chave = base_chave.where(~so_sap, L["codigo"].astype(str) + "|RC" + L["req_sap"].fillna("-").astype(str)
                                  + "|OS" + L["os_sap"].astype(str))
    L["seq"] = base_chave.groupby(base_chave).cumcount() + 1
    L["chave"] = base_chave + L["seq"].map(lambda s: "" if s == 1 else f"|{s}")
    L = L.drop(columns="_ord")

    # início da etapa (usa o histórico da execução anterior quando a base não tem a data)
    inicios, bases_ini = [], []
    for _, l in L.iterrows():
        h = historico.get(l["chave"])
        e = l["etapa"]
        if e == 1 and not _na(l["criado_req"]):
            ini, b = l["criado_req"], "Criado em (requisição)"
        elif e == 2:
            if h and h[0] == 2:
                ini, b = h[1], "1ª vez vista no nível 02"
            elif h and h[0] == 1:
                ini, b = hoje, "1ª vez vista no nível 02"
            else:
                ini, b = l["criado_req"], "Criado em (requisição) – inclui nível 01"
        elif e == 4 and not _na(l["criado_ped"]):
            ini, b = l["criado_ped"], "Criado em (pedido)"
        elif e == 5 and not _na(l["entrada_em"]):
            ini, b = l["entrada_em"], "Entrada registrada em"
        elif e == 5 and not _na(l["atualizado_ped"]):
            ini, b = l["atualizado_ped"], "Atualizado em (pedido)"
        elif h and h[0] == e and not _na(h[1]):
            ini, b = h[1], "1ª vez vista nesta etapa"
        else:
            ini, b = hoje, "1ª vez vista nesta etapa"
        if _na(ini):
            ini, b = hoje, "1ª vez vista nesta etapa"
        inicios.append(pd.Timestamp(ini))
        bases_ini.append(b)
    L["inicio_etapa"] = inicios
    L["base_inicio"] = bases_ini
    L["etapa_txt"] = L["etapa"].map(ETAPAS)
    L.loc[L["etapa_txt_sap"].notna(), "etapa_txt"] = L["etapa_txt_sap"]

    # anotações manuais: data de necessidade da OS (manda sobre a do TracOS) e recebimento
    L["data_nec_manual"] = pd.to_datetime(
        L["os_sap"].map(lambda o: None if _na(o) else datas_os.get(str(o))))
    L["data_necessidade"] = L["data_nec_manual"].fillna(L["data_nec_tracos"])
    L["origem_data"] = np.where(L["data_nec_manual"].notna(), "Manual (Por OS)", L["origem_data_tracos"])
    L["rec_manual"] = L["chave"].map(marcas)
    L["disponivel"] = [disponivel(m if isinstance(m, str) else None, e)
                       for m, e in zip(L["rec_manual"], L["etapa"])]
    L["prioridade"] = [prioridade(e, n, i, hoje, prm, d) for e, n, i, d in
                       zip(L["etapa"], L["data_necessidade"], L["inicio_etapa"], L["disponivel"])]
    L["status"] = L["prioridade"].map(STATUS)
    L["valor"] = L["qtd"] * L["preco"]
    L["requisicao_txt"] = [
        None if _na(rq) else (f"#{int(rq)}/{int(it)}" if not _na(it) else f"#{int(rq)}")
        for rq, it in zip(L["requisicao"], L["req_item"])]
    L["origens"] = [" | ".join(x for x in (
        f"REQ L{int(a)}" if not _na(a) else "", f"FLX L{int(b)}" if not _na(b) else "",
        f"PED L{int(c)}" if not _na(c) else "", f"IWBK L{int(d)}" if not _na(d) else "") if x)
        for a, b, c, d in zip(L["orig_req"], L["orig_flx"], L["orig_ped"], L["orig_sap"])]
    L["eh_preventiva"] = L["eh_preventiva"].fillna(False).astype(bool)
    L["sap_consumido"] = L["sap_consumido"].fillna(False).astype(bool)
    L = L.sort_values(["prioridade", "data_necessidade", "os_sap", "codigo", "seq"],
                      na_position="last").reset_index(drop=True)

    novo_hist = {c: (int(e), pd.Timestamp(i)) for c, e, i in zip(L["chave"], L["etapa"], L["inicio_etapa"])}

    # ------------------------------------------------ divergências adicionais
    chave_por_origem = {}
    for _, l in L.iterrows():
        for base, col in (("requisição", "orig_req"), ("fluxo", "orig_flx"), ("pedido", "orig_ped"),
                          ("iwbk", "orig_sap")):
            if not _na(l[col]):
                chave_por_origem[(base, int(l[col]))] = l["chave"]

    # itens repetidos na mesma requisição/OS
    rep = r[r.duplicated(["requisicao", "codigo", "os_tracos"], keep=False)]
    for (req, cod, os_), g in rep.groupby(["requisicao", "codigo", "os_tracos"]):
        qt = " + ".join(f"{q:g} {u}" for q, u in zip(g["qtd"], g["unidade"]))
        for _, rq in g.iterrows():
            divs.append(dict(tipo="ITEM REPETIDO NA MESMA REQUISIÇÃO/OS", gravidade="Média",
                             base="requisição", linha=_int(rq["linha_origem"]), codigo=cod,
                             descricao=rq["descricao"], requisicao=int(req), pedido=None, os=int(os_),
                             fornecedor=None,
                             detalhe=f"{len(g)} linhas iguais ({qt}). Mantidas separadas com sequencial; "
                                     f"confira se não é digitação em dobro.", _ref="linha"))

    # possível compra em duplicidade: requisição pendente com material+ativo já em pedido/fluxo
    abertos = L[L["etapa"].isin([3, 4, 5])].dropna(subset=["ativo"])
    idx_ab = {}
    for _, l in abertos.iterrows():
        idx_ab.setdefault((l["codigo"], l["ativo"]), []).append(l)
    for _, l in L[L["etapa"].isin([1, 2])].iterrows():
        for o in idx_ab.get((l["codigo"], l["ativo"]), []):
            if o["requisicao"] == l["requisicao"]:
                continue
            divs.append(dict(tipo="POSSÍVEL COMPRA EM DUPLICIDADE", gravidade="Alta", base="requisição",
                             linha=_int(l["orig_req"]), codigo=l["codigo"], descricao=l["descricao"],
                             requisicao=_int(l["requisicao"]), pedido=_int(o["pedido"]),
                             os=_int(l["os_tracos"]), fornecedor=o["fornecedor"],
                             detalhe=f"Requisição pendente #{_int(l['requisicao'])} (OS #{_int(l['os_tracos'])}) "
                                     f"pede o mesmo material para o mesmo ativo ({l['ativo']}) que já está "
                                     f"em {o['requisicao_txt']} / pedido #{_int(o['pedido'])} "
                                     f"({o['etapa_txt'][4:]}, OS #{_int(o['os_tracos'])}).",
                             chave=l["chave"]))

    # valor do pedido x soma dos itens do fluxo
    fv = f.assign(valor=f["qtd"] * f["preco_negociado"]).dropna(subset=["pedido"])
    soma = fv.groupby("pedido").agg(itens_f=("codigo", "size"), soma=("valor", "sum"))
    tot = p.groupby("pedido").agg(itens_p=("codigo", "size"), total=("custo_total_pedido", "first"),
                                  forn=("fornecedor", "first"), sap=("pedido_sap", "first"))
    comp = tot.join(soma, how="inner")
    for ped, c in comp.iterrows():
        dif = round(float(c["total"]) - float(c["soma"]), 2)
        if abs(dif) >= 0.01:
            divs.append(dict(tipo="DIVERGÊNCIA DE VALOR (pedido × fluxo)",
                             gravidade="Média" if c["itens_p"] > c["itens_f"] else "Alta",
                             base="pedido", linha=None, codigo=None, descricao=None, requisicao=None,
                             pedido=int(ped), os=None, fornecedor=c["forn"],
                             detalhe=f"Pedido SAP {c['sap']}: total R$ {c['total']:,.2f} × soma dos itens no "
                                     f"fluxo R$ {c['soma']:,.2f} (dif. R$ {dif:,.2f}). Itens no pedido: "
                                     f"{c['itens_p']}, no fluxo: {c['itens_f']}.".replace(",", "X")
                                     .replace(".", ",").replace("X", "."),
                             chave=f"PED{int(ped)}"))

    # local de estoque obsoleto
    for _, fx in f[f["local_estoque"].str.contains("obsolet", case=False, na=False)].iterrows():
        divs.append(dict(tipo="ATENÇÃO – local de estoque obsoleto", gravidade="Info", base="fluxo",
                         linha=_int(fx["linha_origem"]), codigo=fx["codigo"], descricao=fx["descricao"],
                         requisicao=_int(fx["requisicao"]), pedido=_int(fx["pedido"]),
                         os=_int(fx["os_tracos"]), fornecedor=fx["fornecedor"],
                         detalhe=f"Item comprado para o local '{fx['local_estoque']}'.", _ref="linha"))

    # requisição com status diferente de Pendente
    for _, rq in r[r["status_req"].fillna("").str.lower() != "pendente"].iterrows():
        divs.append(dict(tipo="ATENÇÃO – status de requisição inesperado", gravidade="Média",
                         base="requisição", linha=_int(rq["linha_origem"]), codigo=rq["codigo"],
                         descricao=rq["descricao"], requisicao=_int(rq["requisicao"]), pedido=None,
                         os=_int(rq["os_tracos"]), fornecedor=None,
                         detalhe=f"Status '{rq['status_req']}' (esperado: Pendente).", _ref="linha"))

    # alertas de carga
    alertas = []
    n_fora = int((~p.index.isin(list(up))).sum())
    if len(f) and len(f) % 20 == 0:
        alertas.append(f"O fluxo de compras tem exatamente {len(f)} linhas (múltiplo de 20): a exportação "
                       f"pode ter saído só com a 1ª página. Confira e reexporte se preciso.")
    n_inf = int((L["confianca"].str.startswith(CONFIANCA["R5"])).sum())
    if n_fora:
        alertas.append(f"{n_fora} de {len(p)} itens da base de pedidos não estão no fluxo "
                       f"({n_inf} com OS inferida pela requisição, {len(orfaos_ped)} sem OS → Divergências).")
    for nome in ("requisicao", "fluxo", "pedido"):
        if len(B[nome]["candidatos"]) > 1:
            alertas.append(f"Vários arquivos de {nome} na pasta bases; usado o mais recente: "
                           f"{B[nome]['arquivo']}")
    if info_sap:
        alertas.append(
            f"IWBK (SAP): {info_sap['linhas']} componentes de {info_sap['os']} OS; {info_sap['casados']} casados com "
            f"o TracOS e {info_sap['novos']} só no SAP ({info_sap['estoque']} de estoque). "
            f"{info_sap['os_comuns']} OS aparecem nas duas bases.")
        if info_sap["antigos"]:
            alertas.append(f"IWBK (SAP): {info_sap['antigos']} componentes em aberto com necessidade há mais de "
                           f"180 dias (reservas antigas): confira se ainda valem.")
    for a in alertas:
        divs.append(dict(tipo="ALERTA DE CARGA", gravidade="Alta", base="-", linha=None, codigo=None,
                         descricao=None, requisicao=None, pedido=None, os=None, fornecedor=None,
                         detalhe=a, chave="CARGA|" + a[:40]))

    D = pd.DataFrame(divs)
    if len(D):
        if "conta" not in D:
            D["conta"] = False
        D["conta"] = D["conta"].fillna(False).astype(bool)
        if "chave" not in D:
            D["chave"] = None
        if "_ref" in D:
            m = D["_ref"].eq("linha") & D["chave"].isna()
            D.loc[m, "chave"] = [chave_por_origem.get((b, int(li))) if not _na(li) else None
                                 for b, li in zip(D.loc[m, "base"], D.loc[m, "linha"])]
            D = D.drop(columns="_ref")
        D["no_followup"] = D["chave"].isin(set(L["chave"])).map({True: "SIM", False: "NÃO"})
        ordem_g = {"Alta": 0, "Média": 1, "Info": 2}
        D["_g"] = D["gravidade"].map(ordem_g)
        D = D.sort_values(["_g", "tipo", "pedido", "requisicao", "linha"], na_position="last") \
            .drop(columns="_g").reset_index(drop=True)

    # ------------------------------------------------ agregações
    receb = _recebimento(L, p.loc[orfaos_ped], marcas, hoje)
    por_os = _por_os(L, datas_os, liberadas)
    por_forn = _por_fornecedor(L, p, up, hoje)
    reqs = _requisicoes(L, hoje, prm)

    # ------------------------------------------------ conciliação de linhas
    conc = []
    bases_conc = [("requisição", "orig_req", r), ("fluxo", "orig_flx", f), ("pedido", "orig_ped", p)]
    if B.get("iwbk"):
        bases_conc.append(("iwbk", "orig_sap", B["iwbk"]["norm"]))
    for nome, col, df in bases_conc:
        em_fu = [int(x) for x in L[col].dropna()]
        em_dv = [int(x) for x in D.loc[D["conta"] & D["base"].eq(nome), "linha"].dropna()] if len(D) else []
        todas = set(int(x) for x in df["linha_origem"])
        conc.append(dict(base=nome, entrada=len(df), follow_up=len(em_fu), divergencias=len(em_dv),
                         total_saida=len(em_fu) + len(em_dv),
                         ok=(sorted(em_fu + em_dv) == sorted(todas))))
    return dict(info_sap=info_sap, linhas=L, recebimento=receb, divergencias=D, por_os=por_os, por_fornecedor=por_forn, requisicoes=reqs,
                historico=novo_hist, alertas=alertas, conciliacao=pd.DataFrame(conc), prm=prm, hoje=hoje)


def _etapa_sap(x):
    """Etapa de um componente da IWBK: (etapa, texto da etapa, já consumido pela OS?)."""
    disp = str(x["disponibilidade"] if not _na(x["disponibilidade"]) else "").lower()
    nec = 0 if _na(x["qtd"]) else x["qtd"]
    ret = 0 if _na(x["qtd_retirada"]) else x["qtd_retirada"]
    ent = 0 if _na(x["qtd_entrada"]) else x["qtd_entrada"]
    if nec > 0 and ret >= nec:
        return 5, "5 - Retirado para a OS (SAP)", True
    if "registro final" in disp:
        return 5, "5 - Baixa final na reserva (SAP)", True
    if x["categoria"] == "L":
        if "falta" in disp or "não disponível" in disp:
            return 0, ETAPAS[0], False
        return 5, "5 - Disponível em estoque (SAP)", False
    if (nec > 0 and ent >= nec) or "efetuada a em" in disp:
        return 5, "5 - Entrada registrada (SAP)", False
    if not _na(x["pedido_sap"]):
        return 4, "4 - Pedido SAP emitido (aguardando entrega)", False
    if "não liberada" in disp:
        return 1, "1 - RC SAP não liberada", False
    if not _na(x["rc_sap"]):
        return 3, "3 - RC SAP liberada, sem pedido", False
    return 3, "3 - Componente sem RC no SAP", False


def _integrar_iwbk(L, iwbk, preco_ref, hoje):
    """Casa a IWBK com as linhas do TracOS (S1..S5) e acrescenta como linhas novas o que só existe no SAP."""
    if not iwbk:
        return L, None
    iw = iwbk["norm"].copy()
    iw["rc_n"] = iw["rc_sap"]
    tr = L[L["origem"] == "TracOS"][["os_sap", "codigo", "req_sap", "pedido_sap"]].copy()
    tr["rc_n"] = tr["req_sap"].map(lambda v: np.nan if _na(v) else str(v).lstrip("0"))
    ua, ub, s2l = set(), set(), {}
    for nome, chaves in REGRAS_SAP:
        for i, (j, n) in _casar(iw, tr, chaves, ua, ub).items():
            s2l[i] = (j, nome)

    for i, (j, nome) in s2l.items():
        x = iw.loc[i]
        e, txt, consumido = _etapa_sap(x)
        L.at[j, "origem"] = "TracOS + SAP"
        L.at[j, "orig_sap"] = x["linha_origem"]
        L.at[j, "confianca"] = f"{L.at[j, 'confianca']}; {CONFIANCA[nome]}"
        for c in CAMPOS_SAP:
            L.at[j, c] = x[c]
        if _na(L.at[j, "data_nec_tracos"]) and not _na(x["data_necessidade"]):
            L.at[j, "data_nec_tracos"] = x["data_necessidade"]
            L.at[j, "origem_data_tracos"] = "SAP (IWBK)"
        if _na(L.at[j, "pedido_sap"]) and not _na(x["pedido_sap"]):
            L.at[j, "pedido_sap"] = x["pedido_sap"]
        if e == 5 and L.at[j, "etapa"] < 5:  # o SAP já tem entrada/retirada que o TracOS ainda não mostra
            L.at[j, "etapa"] = 5
            L.at[j, "etapa_txt_sap"] = txt
            L.at[j, "sap_consumido"] = consumido

    # dados da OS que já existem no TracOS (nº TracOS, plano, ativo, descrição)
    info_os = {}
    for _, l in L[L["origem"] != "SAP"].iterrows():
        d = info_os.setdefault(l["os_sap"], {})
        for c in ("os_tracos", "plano", "descricao_os", "ativo"):
            if d.get(c) is None and not _na(l[c]):
                d[c] = l[c]
        d["eh_preventiva"] = d.get("eh_preventiva", False) or bool(l["eh_preventiva"])

    novos = []
    for i, x in iw.iterrows():
        if i in s2l:
            continue
        e, txt, consumido = _etapa_sap(x)
        o = info_os.get(x["os_sap"], {})
        nec = 0 if _na(x["qtd"]) else x["qtd"]
        feito = x["qtd_retirada"] if x["categoria"] == "L" else x["qtd_entrada"]
        preco = preco_ref.get(x["codigo"])
        novos.append(dict(
            codigo=x["codigo"], descricao=x["descricao"], os_tracos=o.get("os_tracos"), os_sap=x["os_sap"],
            plano=o.get("plano"), descricao_os=o.get("descricao_os", x["descricao_os"]),
            eh_preventiva=bool(x["eh_preventiva"]) or o.get("eh_preventiva", False), ativo=o.get("ativo"),
            qtd=x["qtd"], unidade=x["unidade"], qtd_pendente=max(nec - (0 if _na(feito) else feito), 0),
            data_nec_tracos=x["data_necessidade"],
            origem_data_tracos="SAP (IWBK)" if not _na(x["data_necessidade"]) else None,
            requisicao=None, req_item=None, req_sap=x["rc_n"],
            nivel_liberacao="RC SAP não liberada" if e == 1 else None, grupo_compradores=None, criado_req=None,
            pedido=None, pedido_sap=x["pedido_sap"], status_pedido=x["status_pedido_sap"], criado_ped=None,
            atualizado_ped=None, fornecedor=None,
            entrada=None if _na(x["qtd_entrada"]) or not x["qtd_entrada"] else f"{x['qtd_entrada']:g} {x['unidade']}",
            entrada_em=None, nota_fiscal=None, local_estoque=None, centro_custo=None, status_fluxo=None,
            status_req=None, preco=preco, origem_preco="ref. (mesmo material no fluxo)" if preco else None,
            etapa=e, etapa_txt_sap=txt,
            confianca=CONFIANCA["SO_SAP_L" if x["categoria"] == "L" else "SO_SAP"],
            orig_req=None, orig_flx=None, orig_ped=None, orig_sap=x["linha_origem"], _tem_ped=False,
            origem="SAP", sap_consumido=consumido, **{c: x[c] for c in CAMPOS_SAP}))
    if novos:
        L = pd.concat([L, pd.DataFrame(novos)], ignore_index=True)
        L["data_nec_tracos"] = pd.to_datetime(L["data_nec_tracos"])
    abertos = [i for i, x in iw.iterrows() if _etapa_sap(x)[0] < 5]
    antigos = int((iw.loc[abertos, "data_necessidade"] < hoje - pd.Timedelta(days=180)).sum())
    info = dict(linhas=len(iw), os=iw["os_sap"].nunique(), casados=len(s2l), novos=len(novos),
                estoque=int(sum(1 for n in novos if n["categoria"] == "L")), antigos=antigos,
                os_comuns=len(set(iw["os_sap"]) & set(tr["os_sap"].dropna())),
                ignoradas=iwbk["norm"].attrs.get("linhas_ignoradas", 0))
    return L, info


def _por_os(L, datas_os, liberadas):
    g = L.dropna(subset=["os_sap"]).copy()
    if not len(g):
        return pd.DataFrame()
    g["_falta"] = ~g["disponivel"]
    g["_caminho"] = (g["etapa"] >= 4) & ~g["disponivel"]
    g["_compra"] = g["etapa"].between(1, 3)
    g["_estoque"] = (g["etapa"] == 0) & ~g["disponivel"]
    g["_r5"] = g["confianca"].str.startswith(CONFIANCA["R5"])

    def resumo(s):
        c = s.value_counts().sort_index()
        nomes = {0: "falta em estoque", 1: "aprovação", 2: "almox corp.", 3: "sem pedido", 4: "em pedido",
                 5: "disponível"}
        return ", ".join(f"{n} {nomes[e]}" for e, n in c.items())

    def origem(s):
        t = {"TracOS" if "TracOS" in v else "" for v in s} | {"SAP" if "SAP" in v else "" for v in s}
        t.discard("")
        return " + ".join(sorted(t, reverse=True))

    out = g.groupby("os_sap").agg(
        os_tracos=("os_tracos", "first"), plano=("plano", "first"), descricao_os=("descricao_os", "first"),
        preventiva=("eh_preventiva", "max"),
        ativo=("ativo", lambda s: s.dropna().value_counts().index[0] if s.notna().any() else None),
        centro_custo=("centro_custo", "first"), data_tracos=("data_nec_tracos", "min"),
        itens=("codigo", "size"), disponiveis=("disponivel", "sum"), faltando=("_falta", "sum"),
        a_caminho=("_caminho", "sum"), em_compra=("_compra", "sum"), falta_estoque=("_estoque", "sum"),
        fluxo_incompleto=("_r5", "any"), situacao=("etapa", resumo), origem_itens=("origem", origem),
        retirados=("sap_consumido", "sum"), pior_prio=("prioridade", "min"),
    ).reset_index()
    out["data_manual"] = pd.to_datetime(out["os_sap"].map(lambda o: datas_os.get(str(o))))
    out["data_usada"] = out["data_manual"].fillna(out["data_tracos"])
    out["liberada"] = out["os_sap"].map(lambda o: str(o) in liberadas)
    # todo o material já foi retirado para a ordem no SAP: OS já em execução / concluída
    out["ja_retirada"] = (out["itens"] > 0) & (out["retirados"] == out["itens"])
    out["apta"] = (out["itens"] > 0) & (out["faltando"] == 0) & ~out["ja_retirada"]
    # preventivas primeiro; dentro delas: aptas ainda não liberadas, depois as que faltam menos itens
    out["_ordem"] = np.where(out["liberada"], 2, np.where(out["ja_retirada"], 3, np.where(out["apta"], 0, 1)))
    out = out.sort_values(["preventiva", "_ordem", "faltando", "data_usada", "os_sap"],
                          ascending=[False, True, True, True, True], na_position="last")
    return out.drop(columns="_ordem").reset_index(drop=True)


def _recebimento(L, ped_sem_os, marcas, hoje):
    """Itens que podem chegar: tudo que tem pedido (inclusive pedidos sem OS) e o que falta no estoque.
    Componentes do SAP já retirados/baixados pela OS ficam de fora."""
    cols = ["chave", "os_sap", "os_tracos", "eh_preventiva", "descricao_os", "ativo", "codigo", "descricao",
            "qtd", "unidade", "fornecedor", "pedido", "pedido_sap", "status_pedido", "entrada", "entrada_em",
            "nota_fiscal", "data_necessidade", "etapa", "origem"]
    a = L[((L["etapa"] >= 4) | (L["etapa"] == 0)) & ~L["sap_consumido"]][cols].copy()
    a["no_followup"] = True
    b = pd.DataFrame({
        "chave": [f"{x['codigo']}|R{_int(x['requisicao'])}|PED{_int(x['pedido'])}" for _, x in ped_sem_os.iterrows()],
        "os_sap": None, "os_tracos": None, "eh_preventiva": False, "descricao_os": "(pedido sem OS identificada)",
        "ativo": [_ativo_txt(t, n) for t, n in zip(ped_sem_os["ativo_tag"], ped_sem_os["ativo_nome"])],
        "codigo": ped_sem_os["codigo"].values, "descricao": ped_sem_os["descricao"].values, "qtd": None,
        "unidade": None, "fornecedor": ped_sem_os["fornecedor"].values, "pedido": ped_sem_os["pedido"].values,
        "pedido_sap": ped_sem_os["pedido_sap"].values, "status_pedido": ped_sem_os["status_pedido"].values,
        "entrada": ped_sem_os["entrada"].values, "entrada_em": ped_sem_os["entrada_em"].values,
        "nota_fiscal": ped_sem_os["nota_fiscal"].values, "data_necessidade": pd.NaT,
        "etapa": [5 if (_etapa_pedido(s) == 5 or not _na(e)) else 4
                  for s, e in zip(ped_sem_os["status_pedido"], ped_sem_os["entrada"])],
        "origem": "TracOS", "no_followup": False,
    })
    out = pd.concat([a, b], ignore_index=True) if len(b) else a.reset_index(drop=True)
    out["recebido_tracos"] = out["etapa"] == 5
    out["marca"] = out["chave"].map(marcas)
    out["situacao"] = [situacao_recebimento(m if isinstance(m, str) else None, t, d, hoje, e)
                       for m, t, d, e in zip(out["marca"], out["recebido_tracos"], out["data_necessidade"],
                                             out["etapa"])]
    rank = {v: i for i, v in enumerate(SITUACAO_REC.values())}
    out["_r"] = out["situacao"].map(rank)
    out["_sem_os"] = out["os_sap"].isna()
    out = out.sort_values(["_r", "_sem_os", "data_necessidade", "os_sap", "fornecedor", "pedido"],
                          na_position="last")
    return out.drop(columns=["_r", "_sem_os"]).reset_index(drop=True)


def _por_fornecedor(L, p, usados_p, hoje):
    abertos_p = p[p["status_pedido"].map(_etapa_pedido) == 4]
    l4 = L[(L["etapa"] == 4) & L["fornecedor"].notna() & ~L["disponivel"]]
    forns = sorted(set(abertos_p["fornecedor"].dropna()) | set(l4["fornecedor"]))
    linhas = []
    for fo in forns:
        ap = abertos_p[abertos_p["fornecedor"] == fo]
        lf = l4[l4["fornecedor"] == fo]
        peds = {}
        for _, x in ap.iterrows():
            peds[int(x["pedido"])] = dict(sap=x["pedido_sap"], total=x["custo_total_pedido"], criado=x["criado_em"])
        for _, x in lf.iterrows():
            if not _na(x["pedido"]) and int(x["pedido"]) not in peds:
                peds[int(x["pedido"])] = dict(sap=x["pedido_sap"], total=None, criado=x["inicio_etapa"])
        valor = sum(v["total"] for v in peds.values() if not _na(v["total"]))
        sem_total = lf["pedido"].map(lambda v: not _na(v) and _na(peds[int(v)]["total"])).astype(bool)
        valor += float(lf.loc[sem_total, "valor"].fillna(0).sum())
        criados = [v["criado"] for v in peds.values() if not _na(v["criado"])]
        sem_os = ap[[j not in usados_p for j in ap.index]]
        sem_os = sem_os[~sem_os["linha_origem"].isin(L["orig_ped"].dropna().astype(int))]
        atrasos = [(hoje - d).days for d in lf["data_necessidade"].dropna() if d < hoje]
        linhas.append(dict(
            fornecedor=fo, n_pedidos=len(peds),
            pedidos="; ".join(f"#{k}" + (f" (SAP {v['sap']})" if not _na(v["sap"]) else "")
                              for k, v in sorted(peds.items())),
            itens_abertos=len(ap) + int(lf["orig_ped"].isna().sum()),
            valor_aberto=valor, pedido_mais_antigo=min(criados) if criados else None,
            os_afetadas=", ".join(f"#{int(o)}" for o in sorted(lf["os_tracos"].dropna().unique())),
            itens_sem_os=len(sem_os), _atraso=max(atrasos) if atrasos else 0,
        ))
    out = pd.DataFrame(linhas)
    if len(out):
        out = out.sort_values(["_atraso", "valor_aberto"], ascending=[False, False]).reset_index(drop=True)
    return out


def _requisicoes(L, hoje, prm):
    g = L[L["etapa"].isin([1, 2])]
    if not len(g):
        return pd.DataFrame()
    out = g.groupby(["etapa", "requisicao"]).agg(
        req_sap=("req_sap", "first"), os_tracos=("os_tracos", "first"), os_sap=("os_sap", "first"),
        descricao_os=("descricao_os", "first"),
        ativo=("ativo", "first"), preventiva=("eh_preventiva", "max"), itens=("codigo", "size"),
        inicio=("inicio_etapa", "min"), criado=("criado_req", "min"),
    ).reset_index()
    out["_dias"] = [(hoje - pd.Timestamp(d).normalize()).days for d in out["inicio"]]
    return out.sort_values(["etapa", "_dias", "requisicao"], ascending=[True, False, True]).reset_index(drop=True)
