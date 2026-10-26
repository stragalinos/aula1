/* Fontes de dados. Cada função busca em uma fonte pública, converte para um
   formato simples ({t, v} para séries) e verifica se os valores são plausíveis
   antes de exibi-los. Nenhuma chave fica gravada no código. */
(function (P) {
  'use strict';

  const DIA = P.DIA;

  /* Repositório usado quando o painel é aberto fora do GitHub Pages (ex.: arquivo local). */
  P.REPOSITORIO = ['stragalinos', 'aula1'];

  P.FONTES = {
    coletor: {
      nome: 'Coletor automático (GitHub Actions)',
      tipo: 'Próprio · a cada 30 min, 24 h',
      site: 'https://github.com/' + P.REPOSITORIO.join('/') + '/actions',
      uso: 'Busca todas as fontes num servidor do GitHub, inclusive as que exigem chave, e guarda o histórico. O painel abre com esses dados e completa com cotações ao vivo.',
    },
    bcb: {
      nome: 'Banco Central do Brasil (SGS)',
      tipo: 'Oficial · Brasil',
      site: 'https://www3.bcb.gov.br/sgspub/',
      uso: 'Selic, CDI, IPCA e dólar/euro PTAX oficiais.',
    },
    focus: {
      nome: 'Boletim Focus (Banco Central)',
      tipo: 'Oficial · Brasil',
      site: 'https://www.bcb.gov.br/publicacoes/focus',
      uso: 'Mediana das projeções de cerca de 100 bancos, gestoras e consultorias.',
    },
    fmi: {
      nome: 'FMI · World Economic Outlook',
      tipo: 'Oficial · Internacional',
      site: 'https://www.imf.org/external/datamapper/',
      uso: 'Crescimento, inflação, dívida pública e peso de cada país na economia mundial, com projeções.',
    },
    bancoMundial: {
      nome: 'Banco Mundial (World Development Indicators)',
      tipo: 'Oficial · Internacional',
      site: 'https://data.worldbank.org/',
      uso: 'Reserva: usado só se o FMI não responder (apenas dados históricos).',
    },
    bce: {
      nome: 'Banco Central Europeu (via Frankfurter)',
      tipo: 'Oficial · Internacional',
      site: 'https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html',
      uso: 'Taxas de referência do BCE, usadas para conferir o dólar e o euro do Banco Central.',
    },
    awesome: {
      nome: 'AwesomeAPI (câmbio comercial)',
      tipo: 'Mercado · agregador',
      site: 'https://docs.awesomeapi.com.br/api-de-moedas',
      uso: 'Cotação comercial do dólar e do euro ao longo do dia.',
    },
    coingecko: {
      nome: 'CoinGecko',
      tipo: 'Mercado · agregador global',
      site: 'https://www.coingecko.com/',
      uso: 'Bitcoin, Ethereum e ouro tokenizado (PAXG), com preço médio de centenas de corretoras.',
    },
    brapi: {
      nome: 'brapi (dados da B3)',
      tipo: 'Mercado · Brasil',
      site: 'https://brapi.dev/',
      uso: 'Ações e ETFs da B3. Sem token: PETR4, VALE3, ITUB4 e MGLU3. Atraso de até ~30 min.',
    },
    twelve: {
      nome: 'Twelve Data (bolsas dos EUA)',
      tipo: 'Mercado · EUA',
      site: 'https://twelvedata.com/',
      uso: 'ETFs americanos: S&P 500, Nasdaq, ações do mundo, Tesouro dos EUA e ouro. Exige chave gratuita.',
    },
  };

  P.dados = {};

  function validarFaixa(faixa) {
    return (serie) => {
      if (!Array.isArray(serie) || !serie.length) return 'série vazia';
      if (faixa) {
        const fora = serie.find((p) => p.v < faixa[0] || p.v > faixa[1]);
        if (fora) return 'valor fora da faixa plausível (' + fora.v + ')';
      }
      return null;
    };
  }

  /* ---------- Banco Central: SGS ---------- */
  const SGS = 'https://api.bcb.gov.br/dados/serie/bcdata.sgs.';
  const ddmmaaaa = (d) => String(d.getDate()).padStart(2, '0') + '/' + String(d.getMonth() + 1).padStart(2, '0') + '/' + d.getFullYear();

  function lerSGS(lista) {
    if (!Array.isArray(lista)) throw new P.ErroFonte('Resposta do Banco Central em formato inesperado.', 'formato');
    return lista.map((r) => {
      const [d, m, a] = String(r.data).split('/').map(Number);
      return { t: Date.UTC(a, m - 1, d, 12), v: parseFloat(String(r.valor).replace(',', '.')) };
    }).filter((p) => isFinite(p.t) && isFinite(p.v)).sort((a, b) => a.t - b.t); // "últimos N" vem do mais novo para o mais antigo
  }

  /* A API do SGS exige período de no máximo 10 anos, ou "últimos N" (N ≤ 20). */
  P.dados.sgs = function (codigo, { anos, ultimos, faixa, ttlMin = 60, forcar } = {}) {
    let url;
    if (ultimos) {
      url = SGS + codigo + '/dados/ultimos/' + Math.min(ultimos, 20) + '?formato=json';
    } else {
      const fim = new Date();
      const inicio = new Date(fim.getTime() - anos * 365 * DIA);
      url = SGS + codigo + '/dados?formato=json&dataInicial=' + ddmmaaaa(inicio) + '&dataFinal=' + ddmmaaaa(fim);
    }
    return P.buscar('sgs-' + codigo + '-' + (anos ? anos + 'a' : 'u' + ultimos), url, {
      ttlMin, forcar, transformar: lerSGS, validar: validarFaixa(faixa),
    });
  };

  /* ---------- Banco Central: Boletim Focus (Olinda) ---------- */
  const OLINDA = 'https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais';
  P.FOCUS_INDICADORES = ['IPCA', 'Selic', 'PIB Total', 'Câmbio'];

  function lerFocus(j) {
    const linhas = (j && j.value) || [];
    if (!linhas.length) throw new P.ErroFonte('O Focus não retornou dados.', 'formato');
    const agrupado = {};
    let dataBase = '';
    for (const r of linhas) {
      const ind = r.Indicador;
      const ano = String(r.DataReferencia);
      agrupado[ind] = agrupado[ind] || {};
      agrupado[ind][ano] = agrupado[ind][ano] || [];
      agrupado[ind][ano].push({ d: String(r.Data), v: Number(r.Mediana), n: r.numeroRespondentes });
      if (String(r.Data) > dataBase) dataBase = String(r.Data);
    }
    const ind = {};
    for (const k in agrupado) {
      ind[k] = {};
      for (const ano in agrupado[k]) {
        const pts = agrupado[k][ano].sort((a, b) => (a.d < b.d ? 1 : -1));
        const atual = pts[0];
        const limite = new Date(Date.parse(atual.d) - 28 * DIA).toISOString().slice(0, 10);
        const antigo = pts.find((p) => p.d <= limite);
        ind[k][ano] = { mediana: atual.v, data: atual.d, respondentes: atual.n, ha4sem: antigo ? antigo.v : null };
      }
    }
    return { dataBase, ind };
  }

  P.dados.focus = function (forcar) {
    const ano = new Date().getFullYear();
    const anos = [ano, ano + 1, ano + 2, ano + 3];
    const filtro = '(' + P.FOCUS_INDICADORES.map((i) => "Indicador eq '" + i + "'").join(' or ') + ')'
      + ' and (' + anos.map((a) => "DataReferencia eq '" + a + "'").join(' or ') + ')'
      + ' and baseCalculo eq 0';
    const q = (k, v) => '$' + k + '=' + encodeURIComponent(v);
    const url = OLINDA + '?' + [
      q('filter', filtro),
      q('orderby', 'Data desc'),
      q('top', '1200'),
      q('select', 'Indicador,Data,DataReferencia,Mediana,numeroRespondentes'),
      q('format', 'json'),
    ].join('&');
    return P.buscar('focus-' + ano, url, {
      ttlMin: 360,
      forcar,
      transformar: lerFocus,
      validar: (d) => {
        const ipca = d.ind.IPCA && d.ind.IPCA[ano + 1];
        if (!ipca) return 'IPCA ausente';
        if (ipca.mediana < -5 || ipca.mediana > 50) return 'IPCA implausível';
        return null;
      },
    });
  };

  /* ---------- FMI (com Banco Mundial como reserva) ---------- */
  const FMI = 'https://www.imf.org/external/datamapper/api/v1/';
  P.FMI_INDICADORES = {
    crescimento: { codigo: 'NGDP_RPCH', paises: ['BRA', 'USA', 'WEOWORLD'], bancoMundial: 'NY.GDP.MKTP.KD.ZG', faixa: [-30, 30] },
    inflacao: { codigo: 'PCPIPCH', paises: ['BRA', 'USA', 'WEOWORLD'], bancoMundial: 'FP.CPI.TOTL.ZG', faixa: [-10, 100] },
    divida: { codigo: 'GGXWDG_NGDP', paises: ['BRA', 'USA', 'WEOWORLD'], bancoMundial: 'GC.DOD.TOTL.GD.ZS', faixa: [0, 300] },
    // Reserva: PIB em paridade de poder de compra de cada país dividido pelo do mundo.
    participacao: { codigo: 'PPPSH', paises: ['BRA', 'USA', 'CHN'], bancoMundial: 'NY.GDP.MKTP.PP.CD', bancoMundialPaises: 'BRA;USA;CHN;WLD', razaoDoMundo: true, faixa: [0, 50] },
  };

  function validarPaises(faixa) {
    return (d) => {
      const paises = Object.keys(d);
      if (!paises.length || !d.BRA || !Object.keys(d.BRA).length) return 'Brasil ausente';
      for (const p of paises) for (const a in d[p]) if (d[p][a] < faixa[0] || d[p][a] > faixa[1]) return 'valor implausível (' + p + ' ' + a + ')';
      return null;
    };
  }

  P.dados.fmi = function (chave, forcar) {
    const cfg = P.FMI_INDICADORES[chave];
    const desde = new Date().getFullYear() - 15;
    return P.buscar('fmi-' + chave, FMI + cfg.codigo + '/' + cfg.paises.join('/'), {
      ttlMin: 1440,
      forcar,
      transformar: (j) => {
        const v = j && j.values && j.values[cfg.codigo];
        if (!v) throw new P.ErroFonte('Indicador não encontrado na resposta do FMI.', 'formato');
        const saida = {};
        // A API pode devolver todos os países; ficamos só com os pedidos.
        for (const pais of cfg.paises) {
          if (!v[pais]) continue;
          saida[pais] = {};
          for (const ano in v[pais]) {
            if (Number(ano) < desde) continue; // o painel mostra só os anos recentes
            const n = Number(v[pais][ano]);
            if (v[pais][ano] !== null && isFinite(n)) saida[pais][ano] = n;
          }
        }
        return saida;
      },
      validar: validarPaises(cfg.faixa),
    });
  };

  P.dados.bancoMundial = function (chave, forcar) {
    const cfg = P.FMI_INDICADORES[chave];
    const ano = new Date().getFullYear();
    const url = 'https://api.worldbank.org/v2/country/' + (cfg.bancoMundialPaises || 'BRA;USA;WLD') + '/indicator/' + cfg.bancoMundial
      + '?format=json&per_page=500&date=' + (ano - 12) + ':' + ano;
    return P.buscar('bm-' + chave, url, {
      ttlMin: 1440,
      forcar,
      transformar: (j) => {
        const linhas = Array.isArray(j) && Array.isArray(j[1]) ? j[1] : null;
        if (!linhas) throw new P.ErroFonte('Resposta do Banco Mundial em formato inesperado.', 'formato');
        const saida = {};
        for (const r of linhas) {
          if (r.value == null) continue;
          const pais = r.countryiso3code === 'WLD' ? 'WEOWORLD' : r.countryiso3code;
          saida[pais] = saida[pais] || {};
          saida[pais][r.date] = Number(r.value);
        }
        if (cfg.razaoDoMundo) {
          const mundo = saida.WEOWORLD || {};
          delete saida.WEOWORLD;
          for (const pais in saida) {
            for (const ano in saida[pais]) {
              if (mundo[ano]) saida[pais][ano] = saida[pais][ano] / mundo[ano] * 100;
              else delete saida[pais][ano];
            }
          }
        }
        return saida;
      },
      validar: validarPaises(cfg.faixa),
    });
  };

  /* ---------- Câmbio: BCE (via Frankfurter) e AwesomeAPI ---------- */
  P.dados.bce = function (forcar) {
    return P.buscar('bce-ultimo', [
      'https://api.frankfurter.dev/v1/latest?base=USD&symbols=BRL,EUR',
      'https://api.frankfurter.app/latest?from=USD&to=BRL,EUR',
    ], {
      ttlMin: 60,
      forcar,
      transformar: (j) => ({
        data: j.date,
        usd: Number(j.rates.BRL),
        eur: Number(j.rates.BRL) / Number(j.rates.EUR),
      }),
      validar: (d) => (d.usd > 1 && d.usd < 20 && d.eur > 1 && d.eur < 25 ? null : 'cotação implausível'),
    });
  };

  P.dados.cambioAgora = function (forcar, token) {
    const url = 'https://economia.awesomeapi.com.br/json/last/USD-BRL,EUR-BRL' + (token ? '?token=' + encodeURIComponent(token) : '');
    return P.buscar('awesome-agora', url, {
      ttlMin: 2,
      forcar,
      timeout: 10000,
      transformar: (j) => {
        const ler = (x) => ({ v: Number(x.bid), varDia: Number(x.pctChange), t: Number(x.timestamp) * 1000 });
        return { usd: ler(j.USDBRL), eur: ler(j.EURBRL) };
      },
      validar: (d) => (d.usd.v > 1 && d.usd.v < 20 && d.eur.v > 1 && d.eur.v < 25 ? null : 'cotação implausível'),
    });
  };

  /* ---------- CoinGecko: cripto e ouro tokenizado ---------- */
  P.CRIPTO = [
    { id: 'bitcoin', ativo: 'btc', nome: 'Bitcoin', codigo: 'BTC', grupo: 'cripto' },
    { id: 'ethereum', ativo: 'eth', nome: 'Ethereum', codigo: 'ETH', grupo: 'cripto' },
    { id: 'pax-gold', ativo: 'ouro', nome: 'Ouro (1 onça troy)', codigo: 'PAXG', grupo: 'cripto' },
  ];

  P.dados.cripto = function (id, forcar) {
    return P.buscar('cg-' + id, 'https://api.coingecko.com/api/v3/coins/' + id + '/market_chart?vs_currency=brl&days=365&interval=daily', {
      ttlMin: 10,
      forcar,
      transformar: (j) => (j.prices || [])
        .map(([t, v]) => ({ t: Number(t), v: Number(v) }))
        .filter((p) => isFinite(p.t) && isFinite(p.v) && p.v > 0),
      validar: (s) => (s.length > 30 ? null : 'histórico curto demais'),
    });
  };

  /* ---------- brapi: ações e ETFs da B3 ---------- */
  P.B3_SEM_TOKEN = ['PETR4', 'VALE3', 'ITUB4', 'MGLU3'];
  P.B3_COM_TOKEN = ['BOVA11', 'IVVB11', 'GOLD11', 'PETR4', 'VALE3', 'ITUB4'];

  P.dados.b3 = function (ticker, token, forcar) {
    let url = 'https://brapi.dev/api/quote/' + encodeURIComponent(ticker) + '?range=3mo&interval=1d';
    if (token) url += '&token=' + encodeURIComponent(token);
    return P.buscar('brapi-' + ticker, url, {
      ttlMin: 15,
      forcar,
      transformar: (j) => {
        const r = j && Array.isArray(j.results) ? j.results[0] : null;
        if (!r) throw new P.ErroFonte((j && j.message) || 'Ativo não encontrado na brapi.', 'formato');
        const serie = (r.historicalDataPrice || [])
          .map((h) => ({ t: Number(h.date) * 1000, v: Number(h.adjustedClose != null ? h.adjustedClose : h.close) }))
          .filter((p) => isFinite(p.t) && isFinite(p.v) && p.v > 0)
          .sort((a, b) => a.t - b.t);
        return {
          simbolo: String(r.symbol || ticker),
          nome: String(r.shortName || r.longName || ticker),
          moeda: r.currency === 'USD' ? 'USD' : 'BRL',
          preco: Number(r.regularMarketPrice),
          varDia: Number(r.regularMarketChangePercent),
          serie,
        };
      },
      validar: (d) => (d.serie.length >= 20 || isFinite(d.preco) ? null : 'sem histórico'),
    });
  };

  /* ---------- Twelve Data: ETFs dos EUA ---------- */
  P.EUA = [
    { simbolo: 'SPY', nome: 'S&P 500', desc: 'As 500 maiores empresas dos EUA' },
    { simbolo: 'QQQ', nome: 'Nasdaq-100', desc: 'As 100 maiores empresas não financeiras da Nasdaq (muita tecnologia)' },
    { simbolo: 'VT', nome: 'Ações do mundo todo', desc: 'Milhares de empresas de dezenas de países' },
    { simbolo: 'BIL', nome: 'Tesouro dos EUA · curto prazo', desc: 'Títulos do governo americano de 1 a 3 meses (renda fixa em dólar)' },
    { simbolo: 'TLT', nome: 'Tesouro dos EUA · longo prazo', desc: 'Títulos do governo americano de mais de 20 anos (oscila bastante)' },
    { simbolo: 'GLD', nome: 'Ouro em dólar', desc: 'ETF lastreado em ouro físico' },
    { simbolo: 'EWZ', nome: 'Bolsa brasileira em dólar', desc: 'Ações brasileiras medidas em dólar' },
  ];

  P.dados.eua = function (chave, forcar) {
    const simbolos = P.EUA.map((a) => a.simbolo);
    const url = 'https://api.twelvedata.com/time_series?symbol=' + simbolos.join(',')
      + '&interval=1day&outputsize=260&apikey=' + encodeURIComponent(chave);
    return P.buscar('twelve-eua', url, {
      ttlMin: 30,
      forcar,
      timeout: 20000,
      transformar: (j) => {
        if (j && j.status === 'error') throw new P.ErroFonte('Twelve Data: ' + (j.message || 'erro'), j.code === 401 ? 'acesso' : 'http');
        const saida = {};
        for (const s of simbolos) {
          const b = j[s];
          if (!b || b.status !== 'ok' || !Array.isArray(b.values)) {
            saida[s] = { erro: (b && b.message) || 'sem dados' };
            continue;
          }
          saida[s] = {
            serie: b.values
              .map((x) => ({ t: Date.parse(x.datetime + 'T12:00:00Z'), v: parseFloat(x.close) }))
              .filter((p) => isFinite(p.t) && isFinite(p.v) && p.v > 0)
              .sort((a, b2) => a.t - b2.t),
          };
        }
        return saida;
      },
      validar: (d) => (Object.values(d).some((x) => x.serie && x.serie.length > 30) ? null : 'nenhum ativo com histórico'),
    });
  };
})(window.Painel);
