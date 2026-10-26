/* Utilidades do painel: formatação em pt-BR, criação segura de elementos
   (sem innerHTML com dados externos) e busca de dados com cache local. */
window.Painel = window.Painel || {};

(function (P) {
  'use strict';

  const LOCALE = 'pt-BR';
  const formatadores = {};

  function nf(min, max, extra) {
    const chave = min + '|' + max + '|' + JSON.stringify(extra || {});
    if (!formatadores[chave]) {
      formatadores[chave] = new Intl.NumberFormat(LOCALE, Object.assign({
        minimumFractionDigits: min,
        maximumFractionDigits: max,
      }, extra));
    }
    return formatadores[chave];
  }

  const ehNumero = (v) => typeof v === 'number' && isFinite(v);
  P.ehNumero = ehNumero;
  P.DIA = 86400000;

  P.fmt = {
    num: (v, c = 2) => ehNumero(v) ? nf(c, c).format(v) : '—',
    pct: (v, c = 2, sinal = false) => ehNumero(v) ? (sinal && v > 0 ? '+' : '') + nf(c, c).format(v) + '%' : '—',
    pp: (v, c = 2) => ehNumero(v) ? (v > 0 ? '+' : '') + nf(c, c).format(v) + ' p.p.' : '—',
    brl: (v, c = 2) => ehNumero(v) ? nf(c, c, { style: 'currency', currency: 'BRL' }).format(v) : '—',
    usd: (v, c = 2) => ehNumero(v) ? nf(c, c, { style: 'currency', currency: 'USD' }).format(v) : '—',
    moeda: (v, moeda, c = 2) => moeda === 'USD' ? P.fmt.usd(v, c) : P.fmt.brl(v, c),
    brlCompacto: (v) => ehNumero(v) ? nf(0, 1, { style: 'currency', currency: 'BRL', notation: 'compact' }).format(v) : '—',
    compacto: (v) => ehNumero(v) ? nf(0, 1, { notation: 'compact' }).format(v) : '—',
    data: (t) => ehNumero(t) ? new Date(t).toLocaleDateString(LOCALE) : '—',
    diaMes: (t) => new Date(t).toLocaleDateString(LOCALE, { day: '2-digit', month: 'short' }).replace('.', ''),
    mesAno: (t) => new Date(t).toLocaleDateString(LOCALE, { month: 'short', year: '2-digit' }).replace('.', ''),
    dataHora: (t) => new Date(t).toLocaleString(LOCALE, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }),
    hora: (t) => new Date(t).toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' }),
  };

  /* Cria um elemento. Textos sempre entram como textContent. */
  P.el = function (tag, props, ...filhos) {
    const e = document.createElement(tag);
    if (props) {
      for (const [k, v] of Object.entries(props)) {
        if (v == null || v === false) continue;
        if (k === 'class') e.className = v;
        else if (k === 'texto') e.textContent = v;
        else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
        else if (k === 'dataset') Object.assign(e.dataset, v);
        else e.setAttribute(k, v === true ? '' : v);
      }
    }
    for (const f of filhos.flat()) {
      if (f == null || f === false) continue;
      e.append(f instanceof Node ? f : String(f));
    }
    return e;
  };

  P.limpar = function (e) {
    while (e.firstChild) e.removeChild(e.firstChild);
    return e;
  };

  /* Armazenamento local (só neste navegador). Falhas são ignoradas. */
  P.armazenamento = {
    ler(chave, padrao) {
      try {
        const v = localStorage.getItem('painel:' + chave);
        return v == null ? padrao : JSON.parse(v);
      } catch (_) { return padrao; }
    },
    gravar(chave, valor) {
      try { localStorage.setItem('painel:' + chave, JSON.stringify(valor)); } catch (_) { /* sem espaço ou bloqueado */ }
    },
    remover(chave) {
      try { localStorage.removeItem('painel:' + chave); } catch (_) { /* ignorado */ }
    },
  };

  class ErroFonte extends Error {
    constructor(mensagem, tipo) { super(mensagem); this.tipo = tipo; }
  }
  P.ErroFonte = ErroFonte;

  async function baixar(url, timeout) {
    const ctrl = new AbortController();
    const relogio = setTimeout(() => ctrl.abort(), timeout);
    let resp;
    try {
      resp = await fetch(url, { signal: ctrl.signal, credentials: 'omit', referrerPolicy: 'no-referrer' });
    } catch (e) {
      throw new ErroFonte(e.name === 'AbortError'
        ? 'A fonte demorou demais para responder.'
        : 'Sem conexão com a fonte (internet indisponível ou bloqueio do navegador).', 'rede');
    } finally {
      clearTimeout(relogio);
    }
    if (resp.status === 429) throw new ErroFonte('Limite de consultas da fonte atingido. Tente de novo em alguns minutos.', 'limite');
    if (resp.status === 401 || resp.status === 403) throw new ErroFonte('Acesso negado pela fonte: confira a chave/token informado.', 'acesso');
    if (!resp.ok) throw new ErroFonte('A fonte respondeu com erro ' + resp.status + '.', 'http');
    try { return await resp.json(); } catch (_) { throw new ErroFonte('A fonte respondeu em formato inesperado.', 'formato'); }
  }

  /* Busca JSON com cache: devolve o cache se ainda estiver no prazo (ttlMin),
     e usa o último dado bom (marcado como antigo) se a fonte falhar.
     `urls` pode ser uma lista de endereços alternativos, tentados em ordem.
     A chave do cache nunca inclui tokens. */
  P.buscar = async function (chave, urls, opcoes = {}) {
    const { ttlMin = 30, forcar = false, transformar, validar, timeout = 15000 } = opcoes;
    const salvo = P.armazenamento.ler('cache:' + chave, null);
    const agora = Date.now();
    if (salvo && !forcar && agora - salvo.t < ttlMin * 60000) {
      return { dados: salvo.dados, quando: salvo.t, origem: 'cache-recente' };
    }
    const lista = Array.isArray(urls) ? urls : [urls];
    let ultimoErro;
    for (const url of lista) {
      try {
        const bruto = await baixar(url, timeout);
        let dados;
        try {
          dados = transformar ? transformar(bruto) : bruto;
        } catch (e) {
          throw e instanceof ErroFonte ? e : new ErroFonte('A fonte respondeu em formato inesperado.', 'formato');
        }
        const problema = validar ? validar(dados) : null;
        if (problema) throw new ErroFonte('Dado reprovado na verificação de segurança: ' + problema + '.', 'validacao');
        P.armazenamento.gravar('cache:' + chave, { t: agora, dados });
        return { dados, quando: agora, origem: 'rede' };
      } catch (e) {
        ultimoErro = e;
      }
    }
    if (salvo) return { dados: salvo.dados, quando: salvo.t, origem: 'cache-antigo', erro: ultimoErro.message };
    throw ultimoErro;
  };

  /* Série de pontos {t, v}: utilidades comuns. */
  P.serie = {
    ultimo: (s) => (s && s.length ? s[s.length - 1] : null),
    valorHaDias(s, dias) {
      if (!s || !s.length) return null;
      const limite = s[s.length - 1].t - dias * P.DIA;
      for (let i = s.length - 1; i >= 0; i--) if (s[i].t <= limite) return s[i];
      return null;
    },
    variacaoDias(s, dias) {
      const u = P.serie.ultimo(s);
      const a = P.serie.valorHaDias(s, dias);
      return u && a && a.v ? (u.v / a.v - 1) * 100 : null;
    },
    variacaoUltima(s) {
      return s && s.length > 1 && s[s.length - 2].v ? (s[s.length - 1].v / s[s.length - 2].v - 1) * 100 : null;
    },
  };
})(window.Painel);
