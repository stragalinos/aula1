"""ETAPA 0 - Reconhecimento das 3 bases do TracOS antes de construir o follow-up.

Uso:  python reconhecimento.py            (lê ./bases, imprime o relatório e salva em ./saida)
"""
import datetime as dt
import io
import os
import sys
from contextlib import redirect_stdout

import pandas as pd

import tracos_bases as tb

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_colwidth", 48)
pd.set_option("display.max_rows", 400)

AQUI = os.path.dirname(os.path.abspath(__file__))


def titulo(t):
    print("\n" + "=" * 100 + f"\n{t}\n" + "=" * 100)


def perfil(nome, info):
    bruto, norm = info["bruto"], info["norm"]
    print(f"\n--- {nome.upper()}  ({os.path.basename(info['arquivo'])})")
    if len(info["candidatos"]) > 1:
        print("    vários arquivos encontrados, usando o mais recente:",
              [os.path.basename(c) for c in info["candidatos"]])
    print(f"    linhas: {len(bruto)}   colunas: {bruto.shape[1]}")
    nulos = (bruto.isna().mean() * 100).round(0).astype(int)
    print("    % nulos por coluna:")
    for col, pct in nulos.items():
        marca = "  (100% vazia)" if pct == 100 else ""
        print(f"      {col:<38} {pct:>3}%{marca}")
    print("    Status:", bruto["Status"].value_counts(dropna=False).to_dict())
    falhas = norm["codigo"].isna().sum()
    print(f"    itens sem código de material reconhecido: {falhas}")
    if "os_tracos" in norm:
        print(f"    OS sem padrão reconhecido: {norm['os_tracos'].isna().sum()}  |  "
              f"OS distintas: {norm['os_tracos'].nunique()}  |  "
              f"OS com PREV na descrição: {norm.loc[norm.prev_na_descricao, 'os_tracos'].nunique()}  |  "
              f"preventivas (PREV ou plano): {norm.loc[norm.eh_preventiva, 'os_tracos'].nunique()}")


def taxa(a, b, chaves, nome_a, nome_b):
    """% de linhas de A que encontram ao menos 1 linha em B pela chave; e quantas são ambíguas (>1)."""
    a_ok = a.dropna(subset=chaves)
    cont = b.dropna(subset=chaves).groupby(chaves).size().rename("n_b")
    m = a_ok.join(cont, on=chaves)
    casou = m["n_b"].notna().sum()
    ambig = (m["n_b"] > 1).sum()
    return {
        "de → para": f"{nome_a} → {nome_b}",
        "chave": " + ".join(chaves),
        "linhas A": len(a),
        "A com chave": len(a_ok),
        "casaram": int(casou),
        "% casou": round(100 * casou / len(a), 1) if len(a) else 0,
        "ambíguas (>1)": int(ambig),
    }


def main():
    hoje = pd.Timestamp(dt.date.today())
    B = tb.carregar_bases(os.path.join(AQUI, "bases"))
    r, f, p = (B[k]["norm"] for k in ("requisicao", "fluxo", "pedido"))

    titulo(f"ETAPA 0 - RECONHECIMENTO   (data de referência: {hoje:%d/%m/%Y})")

    # ------------------------------------------------------------ 1. perfil
    titulo("1. PERFIL DAS BASES")
    for nome in ("requisicao", "fluxo", "pedido"):
        perfil(nome, B[nome])
    print("\n    Nível de liberação (requisição):",
          r["nivel_liberacao"].value_counts().to_dict())
    print("    Unidades: requisição", r["unidade"].value_counts().to_dict(),
          "| fluxo", f["unidade"].value_counts().to_dict(), "| pedido: (sem coluna de quantidade)")
    print("    Faixa de IDs de requisição: base requisição "
          f"#{r.requisicao.min()}..#{r.requisicao.max()} | fluxo "
          f"#{f.requisicao.min()}..#{f.requisicao.max()} | pedido "
          f"#{p.requisicao.min()}..#{p.requisicao.max()}")

    # ------------------------------------------------------------ 2. casamento
    titulo("2. TAXA DE CASAMENTO ENTRE AS BASES")
    linhas = []
    for chaves in (["codigo", "requisicao", "pedido"], ["codigo", "requisicao"],
                   ["codigo", "pedido"], ["codigo"]):
        linhas.append(taxa(f, p, chaves, "fluxo", "pedido"))
        linhas.append(taxa(p, f, chaves, "pedido", "fluxo"))
    for chaves in (["codigo", "requisicao"], ["codigo", "os_tracos"], ["codigo"]):
        linhas.append(taxa(r, f, chaves, "requisição", "fluxo"))
    for chaves in (["codigo", "requisicao"], ["codigo", "ativo_tag"], ["codigo"]):
        linhas.append(taxa(r, p, chaves, "requisição", "pedido"))
    print(pd.DataFrame(linhas).to_string(index=False))
    print("\n  (pedido não tem coluna de OS; requisição não tem nº de pedido nem nº do item da requisição)")

    # ------------------------------------------------------------ 3. casos estranhos
    titulo("3. CASOS ESTRANHOS")

    print("\n3.1 Mesma requisição + material repetidos na base de requisição (sem nº de item para diferenciar)")
    d = r[r.duplicated(["requisicao", "codigo", "os_tracos"], keep=False)]
    print(d[["linha_origem", "requisicao", "codigo", "descricao", "qtd", "unidade", "os_tracos"]]
          .to_string(index=False))

    print("\n3.2 Mesmo material em várias OS")
    todas = pd.concat([
        r[["codigo", "descricao", "os_tracos"]].assign(base="req"),
        f[["codigo", "descricao", "os_tracos"]].assign(base="fluxo"),
    ])
    g = todas.groupby("codigo").agg(desc=("descricao", "first"), n_os=("os_tracos", "nunique"),
                                    bases=("base", lambda s: "+".join(sorted(set(s)))))
    g = g[g.n_os > 1].sort_values("n_os", ascending=False)
    print(f"    {len(g)} materiais aparecem em mais de uma OS. Os 10 primeiros:")
    print(g.head(10).to_string())

    print("\n3.3 Mesma requisição em vários pedidos")
    rp = pd.concat([f[["requisicao", "pedido"]], p[["requisicao", "pedido"]]]).dropna()
    rp = rp.drop_duplicates().groupby("requisicao")["pedido"].agg(lambda s: sorted(s.astype(int)))
    print(rp[rp.map(len) > 1].to_string())

    print("\n3.4 Itens no pedido sem correspondente no fluxo (material + requisição + pedido)")
    fp = p.merge(f[["codigo", "requisicao", "pedido", "os_tracos"]],
                 on=["codigo", "requisicao", "pedido"], how="left", indicator=True)
    orf = fp[fp["_merge"] == "left_only"].copy()
    req_os = f.groupby("requisicao")["os_tracos"].agg(lambda s: sorted(s.dropna().unique()))
    orf["os inferível pela req."] = orf["requisicao"].map(
        lambda x: f"#{req_os[x][0]}" if x in req_os and len(req_os[x]) == 1 else "-")
    print(orf[["linha_origem", "pedido", "status_pedido", "codigo", "descricao", "requisicao",
               "fornecedor", "ativo_nome", "os inferível pela req."]].to_string(index=False))
    print(f"    -> {len(orf)} de {len(p)} linhas do pedido não estão no fluxo; "
          f"{(orf['os inferível pela req.'] != '-').sum()} têm OS inferível pela requisição.")

    print("\n3.5 Itens do fluxo sem correspondente no pedido")
    fp2 = f.merge(p[["codigo", "requisicao", "pedido"]], on=["codigo", "requisicao", "pedido"],
                  how="left", indicator=True)
    print(fp2[fp2["_merge"] == "left_only"][["linha_origem", "codigo", "descricao", "status_fluxo",
                                             "requisicao", "req_item", "pedido"]].to_string(index=False))

    print("\n3.6 Divergência de fornecedor / valor entre fluxo e pedido")
    both = f.merge(p, on=["codigo", "requisicao", "pedido"], suffixes=("_f", "_p"))
    div = both[both.fornecedor_f.fillna("") != both.fornecedor_p.fillna("")]
    print(f"    fornecedor divergente: {len(div)} de {len(both)} vínculos")
    print("    quantidade: o pedido NÃO traz quantidade por item -> só dá para comparar valor do pedido.")
    fv = f.assign(valor=f.qtd * f.preco_negociado.fillna(f.preco_estimado)).dropna(subset=["pedido"])
    v = (fv.groupby("pedido").agg(itens_fluxo=("codigo", "size"), soma_fluxo=("valor", "sum"))
         .join(p.groupby("pedido").agg(itens_pedido=("codigo", "size"),
                                       custo_total_pedido=("custo_total_pedido", "first"))))
    v["diferença"] = (v.custo_total_pedido - v.soma_fluxo).round(2)
    print(v.round(2).to_string())

    print("\n3.7 Possível compra em duplicidade: material + ativo em requisição PENDENTE e já em pedido")
    dup = r.merge(p[["codigo", "ativo_tag", "pedido", "status_pedido", "requisicao"]],
                  on=["codigo", "ativo_tag"], suffixes=("", "_ped"))
    print(dup[["requisicao", "codigo", "descricao", "ativo_nome", "os_tracos", "pedido",
               "status_pedido", "requisicao_ped"]].to_string(index=False) if len(dup) else "    nenhum")

    print("\n3.8 Outros pontos")
    print(f"    - fluxo tem exatamente {len(f)} linhas (tamanho típico de página): "
          "export pode estar truncado.")
    print(f"    - 'Atualizado em' da requisição: {r.atualizado_em.nunique()} valor(es) distinto(s) "
          f"({r.atualizado_em.min():%d/%m/%Y %H:%M}) -> é a sincronização, não serve como data de etapa.")
    print(f"    - fluxo não tem data de autorização/criação -> 'dias na etapa' de Compra Autorizada não é calculável.")
    print(f"    - preço estimado = R$ 1,00 em {(f.preco_estimado == 1).sum()} de {len(f)} linhas do fluxo (placeholder).")
    print(f"    - requisição não tem preço; materiais da requisição com preço conhecido no fluxo: "
          f"{r.codigo.isin(f.codigo).sum()} de {len(r)} linhas.")
    print(f"    - 'Custo Total' do pedido é do PEDIDO inteiro e se repete em cada item (não somar por linha).")
    ven = f[f.data_necessidade < hoje]
    print(f"    - fluxo: {len(ven)} de {len(f)} itens com data de necessidade já vencida "
          f"({sorted(f.data_necessidade.dt.strftime('%d/%m/%Y').unique())}).")
    print(f"    - OS com nº de plano mas SEM 'PREV' na descrição (requisição): "
          f"{r.loc[r.plano.notna() & ~r.prev_na_descricao, 'os_tracos'].nunique()} OS / "
          f"{(r.plano.notna() & ~r.prev_na_descricao).sum()} linhas "
          f"{sorted(r.loc[r.plano.notna() & ~r.prev_na_descricao, 'descricao_os'].unique())}")
    print(f"    - local de estoque '0038 - Obsoleto' no fluxo: "
          f"{f.loc[f.local_estoque.str.contains('Obsoleto', na=False), 'descricao'].tolist()}")
    print(f"    - fornecedor 'MINERVA S.A' (a própria empresa?) no pedido: "
          f"{sorted(int(x) for x in p.loc[p.fornecedor.str.contains('MINERVA', na=False), 'pedido'].unique())}")
    dias = (hoje - r.criado_em.dt.normalize()).dt.days
    print(f"    - requisição pendente mais antiga: {r.criado_em.min():%d/%m/%Y} ({dias.max()} dias)")
    print("    - dias pendentes (desde 'Criado em') por nível:")
    print(dias.groupby(r.nivel_liberacao).describe()[["count", "min", "50%", "max"]].to_string())


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    buf = io.StringIO()
    with redirect_stdout(buf):
        main()
    texto = buf.getvalue()
    sys.stdout.write(texto)
    os.makedirs(os.path.join(AQUI, "saida"), exist_ok=True)
    destino = os.path.join(AQUI, "saida", f"reconhecimento_{dt.date.today():%Y-%m-%d}.txt")
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write(texto)
    print(f"\nRelatório salvo em {destino}")
