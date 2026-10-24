"""Cruzamento das bases do SAP: IWBK (componentes das ordens) + ME2N (pedidos com o fornecedor).

Grão da tabela: uma linha por componente da IWBK (material x RC x OS, com sequencial quando o trio se
repete). Toda linha da IWBK termina em exatamente um lugar: no Follow-up, no Histórico SAP (material já
retirado para a ordem) ou em Outras OS (não preventivas). A ME2N só completa as linhas que têm pedido
(fornecedor, data do pedido, preço e, se o layout tiver, a RC); item da ME2N sem componente na IWBK vai para
Divergências.
"""
import os

import numpy as np
import pandas as pd

ETAPAS = {
    0: "0 - Falta em estoque (reserva SAP)",
    1: "1 - RC não liberada (aguardando aprovação)",
    3: "3 - RC liberada, sem pedido",
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
    5: "✅ RECEBIDO (entrada no SAP)",
}
RECEBIMENTO_OPCOES = ("SIM", "PARCIAL", "NÃO")

PARAMETROS_PADRAO = {"x_aprov": 3, "y_sem_pedido": 2, "z_entrega": 5}

# vínculo do item da IWBK com a ME2N
VINCULO = {
    "PM": "Pedido + material",
    "P": "Só o pedido (material diferente na ME2N)",
    "FORA": "Pedido fora da ME2N",
    "SO": "Só na ME2N (pedido da OS sem componente na IWBK)",
}
SEM_DESCRICAO_OS = "(OS sem componente na IWBK)"


def _na(v):
    try:
        return v is None or bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _int(v):
    return None if _na(v) else int(v)


def dias(d1, d0):
    """Dias inteiros entre duas datas (ignora hora), como INT(d1)-INT(d0) no Excel."""
    if _na(d1) or _na(d0):
        return None
    return (pd.Timestamp(d1).normalize() - pd.Timestamp(d0).normalize()).days


def prioridade(etapa, data_nec, inicio, hoje, prm, disponivel=None, remessa=None):
    """Espelho em Python da fórmula de risco da planilha (usado para ordenar e validar)."""
    d_etapa = dias(hoje, inicio)
    d_nec = dias(data_nec, hoje)
    if disponivel is None:
        disponivel = etapa == 5
    if disponivel:
        return 6
    if d_nec is not None and d_nec < 0:
        return 1
    if etapa == 1 and (d_etapa or 0) > prm["x_aprov"]:
        return 2
    if etapa == 3 and (d_etapa or 0) > prm["y_sem_pedido"]:
        return 3
    # pedido (ou falta em estoque) perto da necessidade, ou pedido com entrega prometida depois dela
    if etapa in (0, 4) and d_nec is not None and (
            d_nec <= prm["z_entrega"] or (etapa == 4 and (dias(remessa, data_nec) or 0) > 0)):
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
    """Item está aqui? Marca manual manda; sem marca vale a entrada / o estoque registrado no SAP."""
    if marca == "SIM":
        return True
    if marca in ("PARCIAL", "NÃO"):
        return False
    return etapa == 5


def situacao_recebimento(marca, recebido_sap, data_nec, hoje, etapa=None):
    """Espelho da fórmula 'Situação' da aba Recebimento."""
    if marca == "SIM":
        return SITUACAO_REC[4]
    if marca == "PARCIAL":
        return SITUACAO_REC[2]
    if marca == "NÃO":
        return SITUACAO_REC[3]
    if recebido_sap:
        return SITUACAO_REC[5]
    if etapa == 0:
        return SITUACAO_REC[6]
    d = dias(data_nec, hoje)
    return SITUACAO_REC[0] if d is not None and d < 0 else SITUACAO_REC[1]


def etapa_sap(x):
    """Etapa de um componente da IWBK: (etapa, texto da etapa, já consumido pela OS?)."""
    disp = str(x["disponibilidade"] if not _na(x["disponibilidade"]) else "").lower()
    nec = 0 if _na(x["qtd"]) else x["qtd"]
    ret = 0 if _na(x["qtd_retirada"]) else x["qtd_retirada"]
    ent = 0 if _na(x["qtd_entrada"]) else x["qtd_entrada"]
    if nec > 0 and ret >= nec:
        return 5, "5 - Retirado para a OS", True
    if "registro final" in disp:
        return 5, "5 - Baixa final na reserva", True
    if x["categoria"] == "L":
        if "falta" in disp or "não disponível" in disp:
            return 0, ETAPAS[0], False
        return 5, "5 - Disponível em estoque", False
    if (nec > 0 and ent >= nec) or "efetuada a em" in disp:
        return 5, "5 - Entrada registrada", False
    if not _na(x["pedido_sap"]):
        return 4, ETAPAS[4], False
    if "não liberada" in disp:
        return 1, ETAPAS[1], False
    if not _na(x["rc_sap"]):
        return 3, ETAPAS[3], False
    return 3, "3 - Componente sem RC", False


def cruzar(B, hoje, historico=None, prm=None, manuais=None, so_preventivas=False):
    """Monta o follow-up. Retorna dict com linhas (Follow-up), recebimento, divergencias, por_os,
    por_fornecedor, requisicoes (RC paradas), historico novo, alertas e conciliacao.

    manuais = anotações da versão anterior da planilha:
      datas_os    {OS SAP: data de necessidade digitada para a OS}
      recebimento {chave: SIM / PARCIAL / NÃO digitado em 'Recebido?'}
      liberadas   {OS SAP já liberadas para a equipe}
    so_preventivas: as abas de trabalho ficam só com OS preventivas; as demais vão para 'outras'.
    """
    hoje = pd.Timestamp(hoje).normalize()
    historico = historico or {}
    manuais = manuais or {}
    datas_os = {str(k): pd.Timestamp(v).normalize() for k, v in manuais.get("datas_os", {}).items()
                if not _na(v)}
    marcas = {k: marca_recebimento(v) for k, v in manuais.get("recebimento", {}).items()}
    liberadas = {str(k) for k in manuais.get("liberadas", set())}
    prm = {**PARAMETROS_PADRAO, **(prm or {})}
    iw = B["iwbk"]["norm"]
    me = B["me2n"]["norm"] if B.get("me2n") else None

    # ------------------------------------------------ uma linha por componente da IWBK
    L = iw.rename(columns={"linha_origem": "orig_sap", "rc_sap": "req_sap", "data_necessidade": "data_nec_sap",
                           "status_pedido_sap": "status_pedido"}).reset_index(drop=True)
    et = [etapa_sap(x) for _, x in iw.iterrows()]
    L["etapa"] = [e for e, _, _ in et]
    L["etapa_txt"] = [t for _, t, _ in et]
    L["sap_consumido"] = [c for _, _, c in et]
    feito = np.where(L["categoria"].eq("L"), L["qtd_retirada"].fillna(0), L["qtd_entrada"].fillna(0))
    L["qtd_pendente"] = np.maximum(L["qtd"].fillna(0) - feito, 0)
    L["origem_data_sap"] = np.where(L["data_nec_sap"].notna(), "SAP (IWBK)", None)
    L["origem"] = "IWBK"
    L["os_conhecida"] = True

    # ------------------------------------------------ ME2N: fornecedor, data do pedido, preço, RC
    for c in ("fornecedor", "fornecedor_cod", "origem_preco", "grupo_compradores", "vinculo_me2n", "moeda_me2n",
              "rc_me2n"):
        L[c] = pd.Series(None, index=L.index, dtype=object)
    for c in ("preco", "a_fornecer", "orig_me2n"):
        L[c] = np.nan
    L["data_pedido"] = pd.NaT
    usadas = _integrar_me2n(L, me)
    L, n_so_me2n = _linhas_so_me2n(L, me, usadas)
    if me is not None:  # a ME2N diz que não falta nada a fornecer: entregue
        m = L["etapa"].eq(4) & L["a_fornecer"].eq(0)
        L.loc[m, "etapa"] = 5
        L.loc[m, "etapa_txt"] = "5 - Entregue (ME2N: nada a fornecer)"

    # data de necessidade: sem ela, herda a data dos outros itens da mesma OS
    nec_os = L.dropna(subset=["data_nec_sap"]).groupby("os_sap")["data_nec_sap"].min()
    falta = L["data_nec_sap"].isna() & L["os_sap"].isin(nec_os.index)
    L.loc[falta, "data_nec_sap"] = L.loc[falta, "os_sap"].map(nec_os)
    L.loc[falta, "origem_data_sap"] = "Herdada de outro item da OS"

    # chave = material | RC SAP | OS SAP (+ sequencial quando o trio se repete)
    L = L.sort_values(["codigo", "req_sap", "os_sap", "orig_sap"], na_position="last")
    base_chave = (L["codigo"].astype(str) + "|RC" + L["req_sap"].fillna("-").astype(str)
                  + "|OS" + L["os_sap"].astype(str))
    L["seq"] = base_chave.groupby(base_chave).cumcount() + 1
    L["chave"] = base_chave + L["seq"].map(lambda s: "" if s == 1 else f"|{s}")

    # início da etapa: data do pedido (ME2N) na etapa 4; nas outras, a 1ª vez que o script viu o item nela
    inicios, bases_ini = [], []
    for ch, e, dp in zip(L["chave"], L["etapa"], L["data_pedido"]):
        h = historico.get(ch)
        if e == 4 and not _na(dp):
            ini, b = dp, "Data do pedido (ME2N)"
        elif h and h[0] == e and not _na(h[1]):
            ini, b = h[1], "1ª vez vista nesta etapa"
        else:
            ini, b = hoje, "1ª vez vista nesta etapa"
        inicios.append(pd.Timestamp(ini))
        bases_ini.append(b)
    L["inicio_etapa"] = inicios
    L["base_inicio"] = bases_ini

    # anotações manuais: data de necessidade da OS (manda sobre a do SAP) e recebimento
    L["data_nec_manual"] = pd.to_datetime(L["os_sap"].map(lambda o: datas_os.get(str(o))))
    L["data_necessidade"] = L["data_nec_manual"].fillna(L["data_nec_sap"])
    L["origem_data"] = np.where(L["data_nec_manual"].notna(), "Digitada para a OS", L["origem_data_sap"])
    L["rec_manual"] = L["chave"].map(marcas)
    L["disponivel"] = [disponivel(m if isinstance(m, str) else None, e)
                       for m, e in zip(L["rec_manual"], L["etapa"])]
    L["prioridade"] = [prioridade(e, n, i, hoje, prm, d, r) for e, n, i, d, r in
                       zip(L["etapa"], L["data_necessidade"], L["inicio_etapa"], L["disponivel"],
                           L["data_remessa"])]
    L["status"] = L["prioridade"].map(STATUS)
    L["valor"] = L["qtd"] * L["preco"]
    L["eh_preventiva"] = L["eh_preventiva"].fillna(False).astype(bool)
    L["sap_consumido"] = L["sap_consumido"].astype(bool)
    # tabela em blocos por OS: preventivas primeiro, depois a OS com o pior status e a data mais próxima;
    # OS só com reservas antigas (> 180 dias) no fim. Dentro da OS, por status e data.
    L["_antiga"] = L["data_necessidade"] < hoje - pd.Timedelta(days=180)
    rank = (L.groupby("os_sap").agg(_prev=("eh_preventiva", "max"), _ant=("_antiga", "all"),
                                    _p=("prioridade", "min"), _d=("data_necessidade", "min"))
            .sort_values(["_prev", "_ant", "_p", "_d"], ascending=[False, True, True, True], na_position="last"))
    L["_ros"] = L["os_sap"].map({o: i for i, o in enumerate(rank.index)})
    L = L.sort_values(["_ros", "prioridade", "data_necessidade", "codigo", "seq"], na_position="last") \
        .drop(columns=["_antiga", "_ros"]).reset_index(drop=True)

    novo_hist = {c: (int(e), pd.Timestamp(i)) for c, e, i in zip(L["chave"], L["etapa"], L["inicio_etapa"])}

    # material já retirado / baixado para a ordem: nada a fazer; vai para o Histórico SAP
    # (continua contando nos totais da OS e na conciliação)
    H = L[L["sap_consumido"]].sort_values(["os_sap", "codigo"]).reset_index(drop=True)
    L = L[~L["sap_consumido"]].reset_index(drop=True)
    # OS não preventivas: fora das abas de trabalho quando so_preventivas (aba Outras OS)
    O = L.iloc[0:0].copy()
    if so_preventivas:  # OS que só aparece na ME2N (tipo desconhecido) fica nas abas de trabalho
        nao = ~L["eh_preventiva"] & L["os_conhecida"]
        O = L[nao].sort_values(["os_sap", "codigo"]).reset_index(drop=True)
        L = L[~nao].reset_index(drop=True)
    L["faixa"] = (L["os_sap"] != L["os_sap"].shift()).cumsum() % 2

    # ------------------------------------------------ divergências
    divs = []
    antigas = L[~L["disponivel"] & (L["data_nec_sap"] < hoje - pd.Timedelta(days=180))]
    for _, l in antigas.iterrows():
        divs.append(dict(tipo="ATENÇÃO – reserva antiga no SAP (> 180 dias)", gravidade="Info", base="iwbk",
                         linha=_int(l["orig_sap"]), codigo=l["codigo"], descricao=l["descricao"],
                         rc=l["req_sap"], pedido=l["pedido_sap"], os=l["os_sap"], fornecedor=l["fornecedor"],
                         chave=l["chave"],
                         detalhe=f"Necessidade em {l['data_nec_sap']:%d/%m/%Y} ({(hoje - l['data_nec_sap']).days} "
                                 f"dias) – {l['etapa_txt']}. Confira se ainda vale ou encerre no SAP."))
    if me is not None:
        for _, l in L[L["etapa"].eq(4) & L["fornecedor"].isna()].iterrows():
            divs.append(dict(tipo="PEDIDO SAP FORA DA ME2N (sem fornecedor)", gravidade="Média", base="iwbk",
                             linha=_int(l["orig_sap"]), codigo=l["codigo"], descricao=l["descricao"],
                             rc=l["req_sap"], pedido=l["pedido_sap"], os=l["os_sap"], fornecedor=None,
                             chave=l["chave"],
                             detalhe=f"O pedido {l['pedido_sap']} não está na ME2N exportada: inclua-o na seleção "
                                     f"da ME2N para ter o fornecedor."))
        for i, x in me.iterrows():
            if i in usadas:
                continue
            divs.append(dict(tipo="ME2N – pedido sem OS", gravidade="Info", base="me2n",
                             linha=_int(x["linha_origem"]), codigo=x["codigo"], descricao=x["descricao"],
                             rc=x["rc_sap"], pedido=x["pedido_sap"], os=None, fornecedor=x["fornecedor"], conta=True,
                             detalhe=f"Pedido {x['pedido_sap']} item {x['item_pedido']} sem ordem (OS): pedido de "
                                     f"estoque ou de outra conta; fica fora do follow-up."))

    # alertas de carga
    alertas = []
    for nome, rot in (("iwbk", "IWBK"), ("me2n", "ME2N")):
        b = B.get(nome)
        if not b or len(b["candidatos"]) < 2:
            continue
        movidos = [os.path.basename(c) for c in b.get("substituidos", [])]
        outros = [os.path.basename(c) for c in b["candidatos"] if c != b["arquivo"] and c not in b.get("substituidos", [])]
        alertas.append(f"{len(b['candidatos'])} arquivos de {rot} na pasta bases: usado '{os.path.basename(b['arquivo'])}' "
                       f"({b.get('motivo', 'modificado por último')})."
                       + (f" Os antigos ({', '.join(movidos)}) foram para bases/antigos." if movidos else "")
                       + (f" Confira e apague os que não valem: {', '.join(outros)}." if outros else ""))
    todas = pd.concat([L, H, O], ignore_index=True)
    alertas.append(f"IWBK: {len(iw)} componentes de {iw['os_sap'].nunique()} OS "
                   f"({int(iw['categoria'].eq('L').sum())} de estoque); {len(H)} já retirados (Histórico SAP)"
                   + (f"; {int(O['origem'].eq('IWBK').sum())} de OS não preventivas (Outras OS)." if len(O) else "."))
    if iw.attrs.get("eliminadas"):
        alertas.append(f"IWBK: {iw.attrs['eliminadas']} componentes eliminados da ordem ou de OS encerradas "
                       f"ficaram de fora.")
    n_ant = int((~todas["disponivel"] & ~todas["sap_consumido"]
                 & (todas["data_nec_sap"] < hoje - pd.Timedelta(days=180))).sum())
    if n_ant:
        alertas.append(f"IWBK: {n_ant} componentes em aberto com necessidade há mais de 180 dias (reservas "
                       f"antigas): confira se ainda valem.")
    com_ped = todas["pedido_sap"].notna()
    if me is None:
        alertas.append(f"Sem a ME2N na pasta bases: os {int(com_ped.sum())} itens com pedido SAP ficam sem "
                       f"fornecedor. Exporte a ME2N com os pedidos das OS para ter o fornecedor.")
    else:
        sem = int((com_ped & todas["fornecedor"].isna()).sum())
        alertas.append(f"ME2N: {len(me)} itens de {me['pedido_sap'].nunique()} pedidos; fornecedor em "
                       f"{int((com_ped & todas['fornecedor'].notna()).sum())} dos {int(com_ped.sum())} itens com "
                       f"pedido SAP" + (f" ({sem} com pedido fora da ME2N → Divergências)" if sem else "")
                       + (f"; {n_so_me2n} itens de pedido de OS sem componente na IWBK entraram como linhas próprias "
                          f"(ex.: compras pedidas pelo TracOS)." if n_so_me2n else "."))
        usd = int((todas["moeda_me2n"].notna() & todas["moeda_me2n"].ne("BRL")).sum())
        if usd:
            alertas.append(f"ME2N: {usd} itens de pedido em moeda estrangeira ficaram sem preço (não convertido).")
    for a in alertas:
        divs.append(dict(tipo="ALERTA DE CARGA", gravidade="Alta" if "Sem a ME2N" in a or "arquivos de" in a
                         else "Info", base="-", linha=None, codigo=None, descricao=None, rc=None, pedido=None,
                         os=None, fornecedor=None, detalhe=a, chave="CARGA|" + a[:40]))

    D = pd.DataFrame(divs)
    if len(D):
        for c in ("conta", "chave"):
            if c not in D:
                D[c] = None
        D["conta"] = D["conta"].fillna(False).astype(bool)
        D["no_followup"] = D["chave"].isin(set(L["chave"])).map({True: "SIM", False: "NÃO"})
        ordem_g = {"Alta": 0, "Média": 1, "Info": 2}
        D["_g"] = D["gravidade"].map(ordem_g)
        D = D.sort_values(["_g", "tipo", "pedido", "linha"], na_position="last").drop(columns="_g") \
            .reset_index(drop=True)

    # ------------------------------------------------ agregações
    receb = _recebimento(L, marcas, hoje)
    por_os = _por_os(L, datas_os, liberadas, H)
    os_retiradas = (H[~H["os_sap"].isin(set(L["os_sap"]) | set(O["os_sap"]))]
                    .groupby("os_sap").agg(descricao_os=("descricao_os", "first"), preventiva=("eh_preventiva", "max"),
                                           itens=("codigo", "size")).reset_index())
    por_forn = _por_fornecedor(L, hoje)
    reqs = _requisicoes(L)

    # ------------------------------------------------ conciliação de linhas
    conc = []
    em = {k: [int(x) for x in df["orig_sap"].dropna()] for k, df in (("follow_up", L), ("historico", H), ("outras", O))}
    conc.append(dict(base="iwbk", entrada=len(iw), follow_up=len(em["follow_up"]), historico=len(em["historico"]),
                     outras=len(em["outras"]), divergencias=0,
                     ok=sorted(em["follow_up"] + em["historico"] + em["outras"]) == sorted(int(x) for x in iw["linha_origem"])))
    if me is not None:
        onde = {}
        for k, df in (("follow_up", L), ("historico", H), ("outras", O)):
            for x in df["orig_me2n"].dropna():
                onde.setdefault(int(x), k)
        n = {k: sum(1 for v in onde.values() if v == k) for k in ("follow_up", "historico", "outras")}
        dv = int(D["conta"].sum()) if len(D) else 0
        conc.append(dict(base="me2n", entrada=len(me), divergencias=dv, **n,
                         ok=len(onde) + dv == len(me)))
    return dict(linhas=L, historico_sap=H, outras=O, os_retiradas=os_retiradas, recebimento=receb,
                divergencias=D, por_os=por_os, por_fornecedor=por_forn, requisicoes=reqs,
                historico=novo_hist, alertas=alertas, conciliacao=pd.DataFrame(conc), prm=prm, hoje=hoje)


def _integrar_me2n(L, me):
    """Completa as linhas que têm pedido SAP com a ME2N: casa 1:1 por pedido + material (havendo mais
    componentes que itens do pedido, repete o item); sem o material, pelo pedido (um pedido tem um fornecedor
    só). Traz fornecedor, data do pedido, preço (só em reais), grupo de compradores, o que falta fornecer e,
    se o layout tiver, a RC e a data de remessa. Devolve os índices das linhas da ME2N usadas."""
    if me is None:
        return set()
    por_item, por_ped = {}, {}
    for i, (ped, cod) in me[["pedido_sap", "codigo"]].iterrows():
        por_item.setdefault((str(ped), str(cod)), []).append(i)
        por_ped.setdefault(str(ped), i)
    livres = {k: list(v) for k, v in por_item.items()}
    usadas = set()
    for j in L.index[L["pedido_sap"].notna()]:
        ped, cod = str(L.at[j, "pedido_sap"]), str(L.at[j, "codigo"])
        if (ped, cod) in por_item:
            i = livres[(ped, cod)].pop(0) if livres[(ped, cod)] else por_item[(ped, cod)][0]
            vinc = "PM"
        elif ped in por_ped:
            i, vinc = por_ped[ped], "P"
        else:
            L.at[j, "vinculo_me2n"] = VINCULO["FORA"]
            continue
        x = me.loc[i]
        usadas.add(i)
        L.at[j, "vinculo_me2n"] = VINCULO[vinc]
        L.at[j, "fornecedor"] = x["fornecedor"]
        L.at[j, "fornecedor_cod"] = x["fornecedor_cod"]
        L.at[j, "data_pedido"] = x["data_pedido"]
        L.at[j, "grupo_compradores"] = x["grupo_compradores"]
        L.at[j, "moeda_me2n"] = x["moeda"]
        L.at[j, "orig_me2n"] = x["linha_origem"]
        if vinc == "PM":
            L.at[j, "a_fornecer"] = x["a_fornecer"]
            if x["moeda"] == "BRL" and not _na(x["preco"]) and x["preco"] > 0:
                L.at[j, "preco"] = float(x["preco"])
                L.at[j, "origem_preco"] = "Preço líquido do pedido (ME2N)"
            if not _na(x["data_remessa"]):
                L.at[j, "data_remessa"] = x["data_remessa"]
        if _na(L.at[j, "req_sap"]) and not _na(x["rc_sap"]):
            L.at[j, "rc_me2n"] = x["rc_sap"]  # só para mostrar: a RC da IWBK faz parte da chave
    return usadas


def _linhas_so_me2n(L, me, usadas):
    """Item de pedido da ME2N com OS mas sem componente na IWBK (ex.: compra pedida pelo TracOS, que cai no
    SAP como RC/pedido da ordem sem virar componente dela) vira uma linha própria do follow-up."""
    if me is None:
        return L, 0
    so = me[~me.index.isin(usadas) & me["os_sap"].notna()]
    if not len(so):
        return L, 0
    info = L.groupby("os_sap").agg(descricao_os=("descricao_os", "first"), eh_preventiva=("eh_preventiva", "max"),
                                   ativo=("ativo", "first"))
    novos = []
    for i, x in so.iterrows():
        o = info.loc[x["os_sap"]] if x["os_sap"] in info.index else None
        entregue = not _na(x["a_fornecer"]) and x["a_fornecer"] == 0
        brl = x["moeda"] == "BRL" and not _na(x["preco"]) and x["preco"] > 0
        novos.append(dict(
            orig_sap=np.nan, os_sap=x["os_sap"], codigo=x["codigo"], descricao=x["descricao"],
            descricao_os=o["descricao_os"] if o is not None else SEM_DESCRICAO_OS,
            eh_preventiva=bool(o["eh_preventiva"]) if o is not None else False, os_conhecida=o is not None,
            ativo=o["ativo"] if o is not None else np.nan, unidade=x["unidade"], qtd=x["qtd_pedido"],
            qtd_retirada=np.nan, qtd_entrada=(x["qtd_pedido"] - x["a_fornecer"]) if not _na(x["a_fornecer"]) else np.nan,
            qtd_pendente=x["a_fornecer"] if not _na(x["a_fornecer"]) else x["qtd_pedido"],
            req_sap=x["rc_sap"], rc_item=np.nan, pedido_sap=x["pedido_sap"], status_pedido="Pedido (ME2N)",
            data_nec_sap=pd.NaT, data_remessa=x["data_remessa"], categoria="N", disponibilidade=np.nan,
            reserva=np.nan, item_lista=np.nan, origem_data_sap=None, origem="ME2N",
            etapa=5 if entregue else 4,
            etapa_txt="5 - Entregue (ME2N: nada a fornecer)" if entregue else ETAPAS[4], sap_consumido=False,
            fornecedor=x["fornecedor"], fornecedor_cod=x["fornecedor_cod"], data_pedido=x["data_pedido"],
            grupo_compradores=x["grupo_compradores"], moeda_me2n=x["moeda"], a_fornecer=x["a_fornecer"],
            preco=float(x["preco"]) if brl else np.nan, origem_preco="Preço líquido do pedido (ME2N)" if brl else None,
            orig_me2n=x["linha_origem"], vinculo_me2n=VINCULO["SO"], rc_me2n=np.nan))
        usadas.add(i)
    L = pd.concat([L, pd.DataFrame(novos)], ignore_index=True)
    for c in ("data_nec_sap", "data_remessa", "data_pedido"):
        L[c] = pd.to_datetime(L[c])
    return L, len(novos)


def _por_os(L, datas_os, liberadas, H=None):
    g = L.copy()
    if not len(g):
        return pd.DataFrame()
    g["_falta"] = ~g["disponivel"]
    g["_caminho"] = (g["etapa"] >= 4) & ~g["disponivel"]
    g["_compra"] = g["etapa"].between(1, 3)
    g["_estoque"] = (g["etapa"] == 0) & ~g["disponivel"]

    def resumo(s):
        c = s.value_counts().sort_index()
        nomes = {0: "falta em estoque", 1: "RC não liberada", 3: "sem pedido", 4: "em pedido", 5: "disponível"}
        return ", ".join(f"{n} {nomes[e]}" for e, n in c.items())

    out = g.groupby("os_sap").agg(
        descricao_os=("descricao_os", "first"), preventiva=("eh_preventiva", "max"),
        ativo=("ativo", lambda s: s.dropna().value_counts().index[0] if s.notna().any() else None),
        data_sap=("data_nec_sap", "min"), itens=("codigo", "size"), disponiveis=("disponivel", "sum"),
        faltando=("_falta", "sum"), a_caminho=("_caminho", "sum"), em_compra=("_compra", "sum"),
        falta_estoque=("_estoque", "sum"), situacao=("etapa", resumo), pior_prio=("prioridade", "min"),
        pedidos_sap=("pedido_sap", lambda s: ", ".join(sorted({str(x) for x in s.dropna()}))),
    ).reset_index()
    ret = H.groupby("os_sap").size() if H is not None and len(H) else pd.Series(dtype=int)
    out["retirados"] = out["os_sap"].map(ret).fillna(0).astype(int)
    out["itens"] += out["retirados"]
    out["disponiveis"] += out["retirados"]
    out["data_manual"] = pd.to_datetime(out["os_sap"].map(lambda o: datas_os.get(str(o))))
    out["data_usada"] = out["data_manual"].fillna(out["data_sap"])
    out["liberada"] = out["os_sap"].map(lambda o: str(o) in liberadas)
    out["apta"] = (out["itens"] > 0) & (out["faltando"] == 0)
    # preventivas primeiro; dentro delas: aptas ainda não liberadas, depois as que faltam menos itens
    out["_ordem"] = np.where(out["liberada"], 2, np.where(out["apta"], 0, 1))
    out = out.sort_values(["preventiva", "_ordem", "faltando", "data_usada", "os_sap"],
                          ascending=[False, True, True, True, True], na_position="last")
    return out.drop(columns="_ordem").reset_index(drop=True)


def _recebimento(L, marcas, hoje):
    """Itens que podem chegar: tudo que tem pedido e o que falta no estoque."""
    cols = ["chave", "os_sap", "eh_preventiva", "descricao_os", "ativo", "codigo", "descricao", "qtd", "unidade",
            "fornecedor", "pedido_sap", "status_pedido", "data_remessa", "data_pedido", "qtd_entrada",
            "data_necessidade", "etapa"]
    out = L[(L["etapa"] >= 4) | (L["etapa"] == 0)][cols].reset_index(drop=True)
    out["no_followup"] = True
    out["recebido_sap"] = out["etapa"] == 5
    out["marca"] = out["chave"].map(marcas)
    out["situacao"] = [situacao_recebimento(m if isinstance(m, str) else None, t, d, hoje, e)
                       for m, t, d, e in zip(out["marca"], out["recebido_sap"], out["data_necessidade"], out["etapa"])]
    rank = {v: i for i, v in enumerate(SITUACAO_REC.values())}
    out["_r"] = out["situacao"].map(rank)
    # agrupado como o material chega: por situação, fornecedor e pedido (falta em estoque: por OS)
    out["_antiga"] = out["data_necessidade"] < hoje - pd.Timedelta(days=180)
    out = out.sort_values(["_r", "fornecedor", "pedido_sap", "_antiga", "os_sap", "data_necessidade"],
                          na_position="last").reset_index(drop=True)
    grupo = (out["_r"].astype(str) + "|" + out["fornecedor"].fillna(out["os_sap"]).fillna("").astype(str) + "|"
             + out["pedido_sap"].fillna("").astype(str))
    out["faixa"] = (grupo != grupo.shift()).cumsum() % 2
    return out.drop(columns=["_r", "_antiga"])


def _por_fornecedor(L, hoje):
    """Fornecedores com itens de pedido ainda não disponíveis."""
    l4 = L[(L["etapa"] == 4) & L["fornecedor"].notna() & ~L["disponivel"]]
    linhas = []
    for fo, lf in l4.groupby("fornecedor"):
        peds = sorted({str(x) for x in lf["pedido_sap"].dropna()})
        atrasos = [(hoje - d).days for d in lf["data_necessidade"].dropna() if d < hoje]
        linhas.append(dict(
            fornecedor=fo, n_pedidos=len(peds), pedidos_sap=", ".join(peds), pedidos="; ".join(peds),
            valor_aberto=float(lf["valor"].fillna(0).sum()),
            pedido_mais_antigo=lf["data_pedido"].min() if lf["data_pedido"].notna().any() else None,
            entrega_prevista=lf["data_remessa"].min() if lf["data_remessa"].notna().any() else None,
            os_afetadas=", ".join(sorted({str(o) for o in lf["os_sap"].dropna()})),
            _atraso=max(atrasos) if atrasos else 0,
        ))
    out = pd.DataFrame(linhas)
    if len(out):
        out = out.sort_values(["_atraso", "valor_aberto"], ascending=[False, False]).reset_index(drop=True)
    return out


def _requisicoes(L):
    """RC SAP não liberadas: uma linha por RC (OS, itens e desde quando o script a vê)."""
    g = L[L["etapa"] == 1].copy()
    if not len(g):
        return pd.DataFrame()
    g["req_sap"] = g["req_sap"].fillna("-")
    out = g.groupby("req_sap").agg(
        os_sap=("os_sap", "first"), n_os=("os_sap", "nunique"), descricao_os=("descricao_os", "first"),
        preventiva=("eh_preventiva", "max"), itens=("codigo", "size"), inicio=("inicio_etapa", "min"),
    ).reset_index()
    return out.sort_values(["inicio", "req_sap"]).reset_index(drop=True)
