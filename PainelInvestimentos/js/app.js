/* Orquestra o painel: carrega cada fonte de forma independente (uma falha
   não derruba as outras), monta as seções e liga o consultor aos dados. */
(function (P) {
  'use strict';

  const fmt = P.fmt;
  const A = P.analise;
  const C = P.consultor;
  const G = P.graficos;
  const num = P.ehNumero;
  const $ = (id) => document.getElementById(id);
  const ANO = new Date().getFullYear();

  const CORES = { brasil: 'var(--serie-1)', eua: 'var(--serie-2)', mundo: 'var(--serie-3)' };

  const E = {
    selic: null, cdi: null, ipca12: null, dolar: null, euro: null,
    focus: null, fmi: {}, fmiOrigem: {}, bce: null, agora: null,
    cripto: {}, b3: {}, b3Erros: {}, eua: null, euaErro: null,
    status: {}, carregando: 0, selecionado: 'usd', filtro: 'todos',
  };

  /* ---------- Configuração (fica só neste navegador) ---------- */
  function config() {
    return Object.assign({ twelve: '', brapi: '', b3: '' }, P.armazenamento.ler('config', {}));
  }
  function tickersB3(cfg) {
    const lista = (cfg.b3 || '').toUpperCase().split(/[\s,;]+/).filter((t) => /^[A-Z0-9^.]{2,12}$/.test(t));
    if (lista.length) return lista.slice(0, 10);
    return cfg.brapi ? P.B3_COM_TOKEN : P.B3_SEM_TOKEN;
  }

  /* ---------- Registro da situação de cada fonte ---------- */
  function anotar(fonte, resultado, erro) {
    (E.status[fonte] = E.status[fonte] || []).push(resultado
      ? { origem: resultado.origem, quando: resultado.quando, erro: resultado.erro, deColetor: resultado.deColetor }
      : { origem: 'erro', erro: erro ? erro.message : 'erro desconhecido' });
  }
  function resumoFonte(fonte) {
    const lista = E.status[fonte];
    if (!lista || !lista.length) return null;
    const diretas = lista.filter((r) => !r.deColetor);
    const boas = diretas.filter((r) => r.origem === 'rede' || r.origem === 'cache-recente');
    if (boas.length) return { estado: 'ok', quando: Math.min(...boas.map((r) => r.quando)), parcial: boas.length < diretas.length, erro: (diretas.find((r) => r.erro) || {}).erro };
    const coletadas = lista.filter((r) => r.deColetor && r.origem === 'rede');
    if (coletadas.length) return { estado: 'ok', quando: Math.min(...coletadas.map((r) => r.quando)), viaColetor: true };
    const antigas = lista.filter((r) => r.origem === 'cache-antigo');
    if (antigas.length) return { estado: 'cache', quando: Math.min(...antigas.map((r) => r.quando)), erro: antigas[0].erro };
    return { estado: 'erro', erro: lista[0].erro };
  }
  function selo(fonte, quando) {
    const r = resumoFonte(fonte);
    const nome = P.FONTES[fonte].nome;
    if (r && r.estado === 'cache') return P.el('span', { class: 'fonte fonte-cache', texto: nome + ' · dado de ' + fmt.dataHora(r.quando) + ' (fonte fora do ar)' });
    return P.el('span', { class: 'fonte', texto: nome + (quando ? ' · ' + quando : '') });
  }

  async function guardar(fonte, promessa, aplicar) {
    try {
      const r = await promessa;
      anotar(fonte, r);
      aplicar(r.dados, r);
      return true;
    } catch (e) {
      anotar(fonte, null, e);
      return false;
    }
  }

  /* ---------- Coletor automático (GitHub Actions) ---------- */
  function enderecoColetor() {
    const host = location.hostname;
    const repo = location.pathname.split('/').filter(Boolean)[0];
    const [dono, nome] = host.endsWith('.github.io') && repo ? [host.split('.')[0], repo] : P.REPOSITORIO;
    return {
      json: 'https://raw.githubusercontent.com/' + dono + '/' + nome + '/dados/painel.json',
      actions: 'https://github.com/' + dono + '/' + nome + '/actions/workflows/coletar-dados.yml',
    };
  }

  async function carregarColetor(forcar) {
    const end = enderecoColetor();
    P.FONTES.coletor.site = end.actions;
    try {
      const r = await P.buscar('coletor', end.json, {
        ttlMin: 5,
        forcar,
        timeout: 12000,
        validar: (d) => (d && d.versao === 1 && d.dados && num(d.geradoEm) ? null : 'formato desconhecido'),
      });
      anotar('coletor', { origem: r.origem, quando: r.dados.geradoEm, erro: r.erro });
      aplicarColetor(r.dados);
    } catch (e) {
      anotar('coletor', null, e);
    }
  }

  /* O arquivo do coletor vira o ponto de partida; as fontes ao vivo só substituem quando respondem. */
  function aplicarColetor(snap) {
    const d = snap.dados;
    for (const k of ['selic', 'cdi', 'ipca12', 'dolar', 'euro', 'focus', 'bce', 'agora']) if (d[k]) E[k] = d[k];
    if (d.fmi) { Object.assign(E.fmi, d.fmi); Object.assign(E.fmiOrigem, d.fmiOrigem || {}); }
    if (d.cripto) Object.assign(E.cripto, d.cripto);
    E.coletor = { geradoEm: snap.geradoEm, b3: d.b3 || {}, b3Erros: d.b3Erros || {}, eua: d.eua || null, euaErro: d.euaErro || null };
    for (const fonte in snap.fontes || {}) {
      if (!P.FONTES[fonte] || fonte === 'coletor') continue;
      for (const s of snap.fontes[fonte]) {
        if (s.origem === 'rede') anotar(fonte, { origem: 'rede', quando: s.quando, deColetor: true });
        else if (s.origem === 'anterior') anotar(fonte, { origem: 'cache-antigo', quando: s.quando, erro: s.erro, deColetor: true });
      }
    }
    renderBrasil();
    renderFocus();
    renderMundo();
  }

  /* ---------- Carregamento ao vivo ---------- */
  const juntar = (chave) => (d) => { E[chave] = P.serie.mesclar(E[chave], d); };

  function carregarBrasil(forcar) {
    const sgs = P.dados.sgs;
    return Promise.all([
      guardar('bcb', sgs(432, { anos: 2, faixa: [0, 60], forcar }), juntar('selic')),
      guardar('bcb', sgs(4389, { ultimos: 10, faixa: [0, 60], forcar }), juntar('cdi')),
      guardar('bcb', sgs(13522, { anos: 3, faixa: [-10, 100], ttlMin: 360, forcar }), juntar('ipca12')),
      guardar('bcb', sgs(1, { anos: 1, faixa: [1, 20], forcar }), juntar('dolar')),
      guardar('bcb', sgs(21619, { anos: 1, faixa: [1, 25], forcar }), juntar('euro')),
    ]).then(() => { renderBrasil(); agendar(); });
  }

  function carregarFocus(forcar) {
    return guardar('focus', P.dados.focus(forcar), (d) => { E.focus = d; }).then(() => { renderFocus(); agendar(); });
  }

  function carregarMundo(forcar) {
    return Promise.all(Object.keys(P.FMI_INDICADORES).map(async (chave) => {
      const ok = await guardar('fmi', P.dados.fmi(chave, forcar), (d) => { E.fmi[chave] = d; E.fmiOrigem[chave] = 'fmi'; });
      if (!ok && !E.fmi[chave] && P.FMI_INDICADORES[chave].bancoMundial) {
        await guardar('bancoMundial', P.dados.bancoMundial(chave, forcar), (d) => { E.fmi[chave] = d; E.fmiOrigem[chave] = 'bancoMundial'; });
      }
    })).then(() => { renderMundo(); agendar(); });
  }

  function carregarCambio(forcar) {
    return Promise.all([
      guardar('bce', P.dados.bce(forcar), (d) => { E.bce = d; }),
      guardar('awesome', P.dados.cambioAgora(forcar), (d) => { E.agora = d; }),
    ]).then(agendar);
  }

  function carregarCripto(forcar) {
    return Promise.all(P.CRIPTO.map((c) => guardar('coingecko', P.dados.cripto(c.id, forcar), (d) => {
      E.cripto[c.ativo] = P.serie.mesclar(E.cripto[c.ativo], d);
    }))).then(agendar);
  }

  function carregarB3(forcar) {
    const cfg = config();
    const col = E.coletor || { b3: {}, b3Erros: {} };
    E.status.brapi = (E.status.brapi || []).filter((r) => r.deColetor);
    if (!cfg.brapi && Object.keys(col.b3).length) {
      // Sem token neste navegador: usa o que o coletor buscou (com o token guardado no GitHub).
      E.b3 = Object.assign({}, col.b3);
      E.b3Erros = Object.assign({}, col.b3Erros);
      return Promise.resolve(agendar());
    }
    E.b3 = {};
    E.b3Erros = {};
    return Promise.all(tickersB3(cfg).map(async (tk) => {
      const antigo = col.b3[tk];
      try {
        const r = await P.dados.b3(tk, cfg.brapi, forcar);
        anotar('brapi', r);
        E.b3[tk] = Object.assign({}, r.dados, { serie: P.serie.mesclar(antigo && antigo.serie, r.dados.serie) });
      } catch (e) {
        anotar('brapi', null, e);
        if (antigo) E.b3[tk] = antigo; else E.b3Erros[tk] = e.message;
      }
    })).then(agendar);
  }

  function carregarEua(forcar) {
    const cfg = config();
    const col = E.coletor || {};
    E.status.twelve = (E.status.twelve || []).filter((r) => r.deColetor);
    E.eua = col.eua || null;
    E.euaErro = col.eua ? null : col.euaErro || null;
    if (!cfg.twelve) return Promise.resolve(agendar());
    return P.dados.eua(cfg.twelve, forcar)
      .then((r) => {
        anotar('twelve', r);
        const novo = {};
        for (const s of Object.keys(r.dados)) {
          const antigo = col.eua && col.eua[s];
          novo[s] = r.dados[s].serie ? { serie: P.serie.mesclar(antigo && antigo.serie, r.dados[s].serie) } : antigo || r.dados[s];
        }
        E.eua = novo;
        E.euaErro = null;
      })
      .catch((e) => { anotar('twelve', null, e); if (!E.eua) E.euaErro = e.message; })
      .then(agendar);
  }

  async function carregar(forcar) {
    E.status = {};
    E.carregando++;
    situacao();
    await carregarColetor(forcar);
    agendar();
    await Promise.all([
      carregarBrasil(forcar), carregarFocus(forcar), carregarMundo(forcar), carregarCambio(forcar),
      carregarCripto(forcar), carregarB3(forcar), carregarEua(forcar),
    ]);
    E.carregando--;
    E.ultimaAtualizacao = Date.now();
    situacao();
    renderTudo();
  }

  function situacao() {
    const el = $('situacao');
    if (E.carregando > 0) { el.textContent = 'Atualizando dados…'; return; }
    const resumos = Object.keys(P.FONTES).map(resumoFonte).filter(Boolean);
    const falhas = resumos.filter((r) => r.estado !== 'ok' || r.parcial).length;
    let texto = 'Atualizado às ' + fmt.hora(E.ultimaAtualizacao);
    if (E.coletor) {
      const parado = Date.now() - E.coletor.geradoEm > 3 * 3600000;
      texto += parado ? ' · coletor parado desde ' + fmt.dataHora(E.coletor.geradoEm) : ' · coletor ' + fmt.hora(E.coletor.geradoEm);
    }
    el.textContent = texto + (falhas ? ' · ' + falhas + (falhas > 1 ? ' fontes com problema' : ' fonte com problema') : ' · todas as fontes ok');
  }

  let agendado = false;
  function agendar() {
    if (agendado) return;
    agendado = true;
    requestAnimationFrame(() => {
      agendado = false;
      renderTudo();
    });
  }

  function renderTudo() {
    const ativos = montarAtivos();
    E.ativos = ativos;
    renderIndicadores();
    renderMercados();
    renderLeitura();
    renderPlano();
    renderSimulador();
    renderFontes();
  }

  /* ---------- Contexto usado pelo consultor ---------- */
  function contexto() {
    const u = P.serie.ultimo;
    const selic = u(E.selic) ? u(E.selic).v : null;
    const ipca12 = u(E.ipca12) ? u(E.ipca12).v : null;
    const cdi = u(E.cdi) ? u(E.cdi).v : null;
    const juroReal = num(selic) && num(ipca12) ? ((1 + selic / 100) / (1 + ipca12 / 100) - 1) * 100 : null;
    const porId = {};
    for (const a of E.ativos || []) porId[a.id] = a;
    const usd = porId.usd;
    return {
      ano: ANO, selic, ipca12, cdi, juroReal, focus: E.focus, fmi: E.fmi, ativos: porId,
      dolar: usd ? { valor: usd.preco, tendencia: usd.tendencia, var30: usd.var30, var365: usd.var365, varDia: usd.varDia, fonte: P.FONTES[usd.fonte].nome } : null,
    };
  }

  /* ---------- Modo simples × completo ---------- */
  const simples = () => document.body.classList.contains('modo-simples');

  function aplicarModo(modo) {
    document.body.classList.toggle('modo-simples', modo !== 'completo');
    document.querySelectorAll('[data-modo]').forEach((b) => b.setAttribute('aria-pressed', b.dataset.modo === modo ? 'true' : 'false'));
  }

  function montarModo() {
    aplicarModo(P.armazenamento.ler('modo', 'simples'));
    document.querySelectorAll('[data-modo]').forEach((b) => b.addEventListener('click', () => {
      aplicarModo(b.dataset.modo);
      P.armazenamento.gravar('modo', b.dataset.modo);
      renderTudo();
    }));
  }

  /* ---------- Visão geral ---------- */
  function bloco({ rotulo, termo, valor, paraVoce, detalhe, delta, mini, rodape, extra }) {
    const card = P.el('div', { class: 'indicador cartao' });
    card.append(P.el('div', { class: 'ind-rotulo' }, rotulo, termo ? P.termo(termo, rotulo) : null));
    card.append(P.el('div', { class: 'ind-valor', texto: valor }));
    if (delta) card.append(P.el('div', { class: 'ind-delta' }, P.el('span', { class: 'seta', 'aria-hidden': 'true', texto: delta.seta }), delta.texto));
    if (paraVoce) card.append(P.el('p', { class: 'para-voce' }, P.el('strong', { texto: 'Para você: ' }), paraVoce));
    if (detalhe) card.append(P.el('div', { class: 'ind-detalhe avancado', texto: detalhe }));
    if (extra) card.append(extra);
    if (mini && mini.length > 1) {
      const m = P.el('div', { class: 'ind-mini' });
      G.mini(m, mini);
      card.append(m);
    }
    if (rodape) card.append(P.el('div', { class: 'ind-fonte' }, rodape));
    return card;
  }

  function deltaPP(serie, dias, sufixo) {
    const u = P.serie.ultimo(serie);
    const a = P.serie.valorHaDias(serie, dias);
    if (!u || !a) return null;
    const d = u.v - a.v;
    return { seta: d > 0.005 ? '▲' : d < -0.005 ? '▼' : '▶', texto: (Math.abs(d) < 0.005 ? 'estável' : fmt.pp(d)) + ' ' + sufixo };
  }

  function amostra(serie, n) {
    if (!serie) return [];
    const passo = Math.max(1, Math.floor(serie.length / n));
    const out = [];
    for (let i = serie.length - 1; i >= 0 && out.length < n; i -= passo) out.unshift(serie[i].v);
    return out;
  }

  /* Compara a mesma cotação em fontes diferentes. lista: [{nome, v, t}] */
  function conferenciaCambio(lista) {
    const validas = lista.filter((x) => num(x.v));
    if (validas.length < 2) return null;
    const valores = validas.map((x) => x.v);
    const dif = (Math.max(...valores) / Math.min(...valores) - 1) * 100;
    const ok = dif <= 1.5;
    const alerta = !ok && !(dif <= 3 && new Set(validas.map((x) => (num(x.t) ? Math.floor(x.t / P.DIA) : null))).size === 1);
    const dias = new Set(validas.map((x) => (num(x.t) ? Math.floor(x.t / P.DIA) : null)));
    let texto;
    if (ok) texto = validas.length + ' fontes conferem (diferença de ' + fmt.pct(dif, 1) + ')';
    else if (dias.size === 1 && dif <= 3) {
      texto = 'Pequena diferença entre as fontes (' + fmt.pct(dif, 1) + '): normal em dias agitados, porque cada uma mede num horário diferente.';
    } else if (dias.size > 1) {
      texto = 'Diferença de ' + fmt.pct(dif, 1) + ' entre datas diferentes ('
        + validas.map((x) => x.nome + ' ' + (num(x.t) ? fmt.diaMes(x.t) : '?')).join(', ') + '): o câmbio se moveu forte.';
    } else texto = 'Fontes divergem ' + fmt.pct(dif, 1) + ' no mesmo dia: algum dado pode estar errado. Confira na fonte oficial.';
    return P.el('div', { class: 'conferencia ' + (alerta ? 'conferencia-alerta' : 'conferencia-ok') },
      P.el('span', { 'aria-hidden': 'true', texto: alerta ? '⚠ ' : '✓ ' }), texto);
  }

  function fontesCambio(moeda, serie) {
    const u = P.serie.ultimo(serie);
    return [
      { nome: 'PTAX', v: u && u.v, t: u && u.t },
      { nome: 'BCE', v: E.bce && E.bce[moeda], t: E.bce && Date.parse(E.bce.data + 'T12:00:00Z') },
      { nome: 'comercial', v: E.agora && E.agora[moeda].v, t: E.agora && E.agora[moeda].t },
    ];
  }

  function detalheCambio(moeda, serie) {
    return fontesCambio(moeda, serie).filter((x) => num(x.v))
      .map((x) => x.nome + ' ' + (num(x.t) ? fmt.diaMes(x.t) : '') + ': ' + fmt.brl(x.v, 4)).join(' · ');
  }

  /* "Para você": o que cada número significa na prática. */
  const PARA_VOCE = {
    selic(s) {
      if (!num(s)) return null;
      if (s >= 10) return 'juros altos. A renda fixa está rendendo bem, e empréstimos e financiamentos estão caros.';
      if (s >= 6) return 'juros médios. A renda fixa rende de forma razoável.';
      return 'juros baixos. A renda fixa rende pouco; vale diversificar.';
    },
    ipca(i) {
      if (!num(i)) return null;
      const meta = i > 4.5 ? ' Está acima do limite da meta do governo (4,5%).' : i < 1.5 ? ' Está abaixo do piso da meta (1,5%).' : ' Está dentro da meta do governo.';
      return 'o que custava R$ 100 há um ano hoje custa cerca de ' + fmt.brl(100 * (1 + i / 100)) + '. Seu dinheiro precisa render mais que isso para não perder valor.' + meta;
    },
    juroReal(j) {
      if (!num(j)) return null;
      if (j >= 6) return 'excelente. A renda fixa está rendendo bem acima da inflação.';
      if (j >= 3) return 'bom. A renda fixa rende acima da inflação.';
      if (j >= 0) return 'fraco. A renda fixa rende pouco acima da inflação.';
      return 'negativo. A renda fixa está perdendo para a inflação.';
    },
    cdi(c, poupanca) {
      if (!num(c)) return null;
      // Para 1 ano, o imposto da renda fixa é de 17,5% sobre o ganho.
      const cdb = 1000 * (1 + c / 100 * (1 - 0.175));
      return 'R$ 1.000 num CDB de 100% do CDI viram cerca de ' + fmt.brl(cdb, 0) + ' em 1 ano, já descontado o imposto.'
        + (num(poupanca) ? ' Na poupança, cerca de ' + fmt.brl(1000 * (1 + poupanca / 100), 0) + '.' : '');
    },
    moeda(a, simbolo) {
      if (!a || !num(a.preco)) return null;
      let t = 'para comprar ' + simbolo + ' 100, você precisa de cerca de ' + fmt.brl(a.preco * 100, 0) + ', sem contar taxas.';
      if (num(a.varDia) && Math.abs(a.varDia) >= 2) t += ' Hoje ele se moveu bastante: evite decisões por impulso.';
      return t;
    },
  };

  function renderIndicadores() {
    const ctx = contexto();
    const cont = P.limpar($('indicadores'));
    const u = P.serie.ultimo;

    cont.append(bloco({
      rotulo: 'Juros (Selic)', termo: 'selic',
      valor: num(ctx.selic) ? fmt.pct(ctx.selic) + ' ao ano' : '—',
      delta: deltaPP(E.selic, 365, 'em 12 meses'),
      paraVoce: PARA_VOCE.selic(ctx.selic),
      mini: amostra(E.selic, 24),
      rodape: selo('bcb', u(E.selic) ? fmt.data(u(E.selic).t) : ''),
    }));
    cont.append(bloco({
      rotulo: 'Inflação (IPCA, 12 meses)', termo: 'ipca',
      valor: num(ctx.ipca12) ? fmt.pct(ctx.ipca12) : '—',
      delta: deltaPP(E.ipca12, 365, 'em 12 meses'),
      paraVoce: PARA_VOCE.ipca(ctx.ipca12),
      mini: amostra(E.ipca12, 24),
      rodape: selo('bcb', u(E.ipca12) ? fmt.mesAno(u(E.ipca12).t) : ''),
    }));
    cont.append(bloco({
      rotulo: 'Ganho acima da inflação (juro real)', termo: 'juroReal',
      valor: num(ctx.juroReal) ? fmt.pct(ctx.juroReal) + ' ao ano' : '—',
      paraVoce: PARA_VOCE.juroReal(ctx.juroReal),
      detalhe: 'Cálculo: Selic descontada a inflação dos últimos 12 meses.',
      rodape: selo('bcb', 'cálculo do painel'),
    }));
    const poupanca = num(ctx.selic) ? (ctx.selic > 8.5 ? (Math.pow(1.005, 12) - 1) * 100 : ctx.selic * 0.7) : null;
    cont.append(bloco({
      rotulo: 'Rendimento da renda fixa (CDI)', termo: 'cdi',
      valor: num(ctx.cdi) ? fmt.pct(ctx.cdi) + ' ao ano' : '—',
      paraVoce: PARA_VOCE.cdi(ctx.cdi, poupanca),
      detalhe: num(poupanca) ? 'Poupança: cerca de ' + fmt.pct(poupanca) + ' ao ano + TR. CDB de 100% do CDI após 2 anos: ' + fmt.pct((ctx.cdi || 0) * 0.85) + ' ao ano líquido.' : null,
      rodape: selo('bcb', u(E.cdi) ? fmt.data(u(E.cdi).t) : ''),
    }));

    for (const [id, rotulo, serie, simbolo] of [['usd', 'Dólar', E.dolar, 'US$'], ['eur', 'Euro', E.euro, '€']]) {
      const a = (E.ativos || []).find((x) => x.id === id);
      cont.append(bloco({
        rotulo, termo: id === 'usd' ? 'dolarizar' : null,
        valor: a ? fmt.brl(a.preco, 2) : '—',
        delta: a && num(a.varDia) ? { seta: a.varDia > 0 ? '▲' : a.varDia < 0 ? '▼' : '▶', texto: fmt.pct(a.varDia, 2, true) + ' no dia' } : null,
        paraVoce: PARA_VOCE.moeda(a, simbolo),
        detalhe: detalheCambio(id, serie),
        extra: conferenciaCambio(fontesCambio(id, serie)),
        mini: amostra(a ? a.serie : serie, 30),
        rodape: selo(a ? a.fonte : 'bcb', a && a.quando ? (a.fonte === 'awesome' ? fmt.dataHora(a.quando) : fmt.data(a.quando)) : ''),
      }));
    }
  }

  const ROTULO_TIPO = {
    oportunidade: { icone: '●', texto: 'Oportunidade' },
    atencao: { icone: '▲', texto: 'Atenção' },
    contexto: { icone: 'i', texto: 'Contexto' },
  };

  function renderLeitura() {
    const lista = P.limpar($('leitura'));
    const itens = C.leitura(contexto());
    if (!itens.length) {
      lista.append(P.el('li', { class: 'carregando', texto: E.carregando ? 'Analisando os dados…' : 'Sem dados suficientes agora. Veja a seção Fontes para entender o motivo.' }));
      return;
    }
    for (const it of itens) {
      const t = ROTULO_TIPO[it.tipo];
      const porque = P.el('details', { class: 'entenda' },
        P.el('summary', { texto: 'Entenda o porquê' }),
        P.el('p', { texto: it.texto }),
        P.el('span', { class: 'fonte', texto: 'Fonte: ' + it.fonte }));
      porque.open = !simples();
      lista.append(P.el('li', { class: 'item-leitura tipo-' + it.tipo },
        P.el('span', { class: 'chip chip-' + it.tipo }, P.el('span', { 'aria-hidden': 'true', class: 'chip-icone', texto: t.icone }), t.texto),
        P.el('strong', { class: 'leitura-titulo', texto: it.titulo }),
        it.acao ? P.el('p', { class: 'leitura-acao' }, P.el('span', { class: 'leitura-acao-rotulo', texto: 'O que fazer: ' }), it.acao) : null,
        porque));
    }
  }

  /* ---------- Brasil ---------- */
  function serieParaGrafico(serie) {
    return { x: serie.map((p) => p.t), y: serie.map((p) => p.v) };
  }

  function renderBrasil() {
    if (E.selic && E.selic.length > 1) {
      const d = serieParaGrafico(E.selic);
      G.linha($('graf-selic'), {
        titulo: 'Selic meta nos últimos 2 anos', x: d.x, series: [{ nome: 'Selic meta', cor: CORES.brasil, y: d.y }],
        formatoX: fmt.mesAno, formatoXLongo: fmt.data, formatoY: (v) => fmt.pct(v, 1), formatoYLongo: (v) => fmt.pct(v), altura: 220,
      });
    } else {
      falha($('graf-selic'), 'bcb');
    }
    if (E.ipca12 && E.ipca12.length > 1) {
      const d = serieParaGrafico(E.ipca12);
      G.linha($('graf-ipca'), {
        titulo: 'IPCA acumulado em 12 meses', x: d.x, series: [{ nome: 'IPCA 12 meses', cor: CORES.brasil, y: d.y }],
        formatoX: fmt.mesAno, formatoXLongo: fmt.mesAno, formatoY: (v) => fmt.pct(v, 1), formatoYLongo: (v) => fmt.pct(v),
        referencias: [{ valor: 3, rotulo: 'Meta 3%' }, { valor: 4.5, rotulo: 'Teto 4,5%' }], altura: 220,
      });
    } else {
      falha($('graf-ipca'), 'bcb');
    }
  }

  function falha(cont, fonte) {
    P.limpar(cont);
    const r = resumoFonte(fonte);
    cont.append(P.el('p', { class: 'vazio' },
      E.carregando && !r ? 'Carregando…' : 'Não foi possível carregar agora' + (r && r.erro ? ': ' + r.erro : '.') + ' ',
      P.el('a', { href: P.FONTES[fonte].site, target: '_blank', rel: 'noopener noreferrer', texto: 'Ver na fonte' })));
  }

  function renderFocus() {
    const cont = P.limpar($('focus'));
    if (!E.focus) { falha(cont, 'focus'); return; }
    const anos = [ANO, ANO + 1, ANO + 2];
    const nomes = { IPCA: 'Inflação no ano (%)', Selic: 'Juros (Selic) no fim do ano (%)', 'PIB Total': 'Crescimento da economia (%)', 'Câmbio': 'Dólar no fim do ano (R$)' };
    const termos = { IPCA: 'ipca', Selic: 'selic', 'PIB Total': 'pib', 'Câmbio': 'ptax' };
    const t = P.el('table', { class: 'tabela-focus' });
    t.append(P.el('thead', null, P.el('tr', null, P.el('th', { scope: 'col', texto: 'Indicador' }), anos.map((a) => P.el('th', { scope: 'col', texto: String(a) })))));
    const corpo = P.el('tbody');
    for (const ind of P.FOCUS_INDICADORES) {
      const linha = P.el('tr', null, P.el('th', { scope: 'row' }, nomes[ind], P.termo(termos[ind])));
      for (const a of anos) {
        const it = C.focusItem(E, ind, a);
        if (!it) { linha.append(P.el('td', { texto: '—' })); continue; }
        const valor = fmt.num(it.mediana, 2);
        let seta = '';
        let mudou = 'sem mudança em 4 semanas';
        if (num(it.ha4sem)) {
          const d = it.mediana - it.ha4sem;
          if (Math.abs(d) >= 0.005) {
            seta = d > 0 ? '▲' : '▼';
            mudou = (d > 0 ? 'subiu ' : 'caiu ') + fmt.num(Math.abs(d), 2) + ' em 4 semanas (era ' + fmt.num(it.ha4sem, 2) + ')';
          } else {
            seta = '=';
          }
        }
        linha.append(P.el('td', { title: mudou },
          P.el('span', { class: 'valor-focus', texto: valor }),
          seta ? P.el('span', { class: 'seta-focus', 'aria-hidden': 'true', texto: ' ' + seta }) : null,
          P.el('span', { class: 'sr', texto: ' (' + mudou + ')' })));
      }
      corpo.append(linha);
    }
    t.append(corpo);
    cont.append(t, P.el('p', { class: 'legenda-setas', texto: '▲ a previsão subiu nas últimas 4 semanas · ▼ caiu · = não mudou' }));
    const ipca = C.focusItem(E, 'IPCA', ANO + 1);
    $('focus-fonte').textContent = 'Fonte: Banco Central do Brasil, Sistema de Expectativas de Mercado · data-base '
      + (E.focus.dataBase ? fmt.data(Date.parse(E.focus.dataBase + 'T12:00:00Z')) : '—')
      + (ipca && ipca.respondentes ? ' · ' + ipca.respondentes + ' instituições responderam' : '');
  }

  /* ---------- Mundo (FMI) ---------- */
  function renderMundo() {
    const anos = [];
    for (let a = ANO - 8; a <= ANO + 5; a++) anos.push(a);
    const paises = [['BRA', 'Brasil', CORES.brasil], ['USA', 'EUA', CORES.eua], ['WEOWORLD', 'Mundo', CORES.mundo]];
    const graficos = { crescimento: 'graf-crescimento', inflacao: 'graf-inflacao', divida: 'graf-divida' };
    for (const chave in graficos) {
      const dados = E.fmi[chave];
      const cont = $(graficos[chave]);
      if (!dados) { falha(cont, 'fmi'); continue; }
      const daFmi = E.fmiOrigem[chave] === 'fmi';
      const xs = anos.filter((a) => paises.some(([p]) => dados[p] && num(dados[p][a])));
      const series = paises.filter(([p]) => dados[p]).map(([p, nome, cor]) => ({ nome, cor, y: xs.map((a) => (num(dados[p][a]) ? dados[p][a] : null)) }));
      G.linha(cont, {
        titulo: chave, x: xs, series, rotuloX: 'Ano', formatoX: String, formatoY: (v) => fmt.num(v, chave === 'divida' ? 0 : 1),
        formatoYLongo: (v) => fmt.pct(v, 1), sombraDesde: daFmi ? ANO : null, rotuloSombra: 'Projeção do FMI',
        incluirZero: chave !== 'inflacao', altura: 220,
      });
    }
    const usouBM = Object.values(E.fmiOrigem).includes('bancoMundial');
    $('mundo-fonte').textContent = 'Fonte: FMI, World Economic Outlook (DataMapper)' + (usouBM ? ' · alguns gráficos vieram do Banco Mundial (sem projeções), porque o FMI não respondeu' : '');

    const cont = P.limpar($('participacao'));
    const part = E.fmi.participacao;
    const anoPart = part && part.BRA ? Object.keys(part.BRA).map(Number).filter((a) => a <= ANO).sort((a, b) => b - a)[0] : null;
    if (anoPart) {
      const br = part.BRA[anoPart];
      cont.append(
        P.el('div', { class: 'numero-grande', texto: fmt.pct(br, 1) }),
        P.el('div', null,
          P.el('strong', null, 'é o tamanho da economia brasileira no mundo', P.termo('ppp')),
          P.el('p', { texto: 'EUA: ' + fmt.pct(part.USA && part.USA[anoPart], 1) + ' · China: ' + fmt.pct(part.CHN && part.CHN[anoPart], 1) + '. Investir só no Brasil concentra todo o seu patrimônio em uma fatia pequena da economia global.' }),
          P.el('span', { class: 'fonte', texto: 'FMI, participação no PIB mundial em paridade de poder de compra, ' + anoPart })));
      $('ext-participacao').textContent = 'Segundo o FMI, o Brasil representa cerca de ' + fmt.pct(br, 1) + ' da economia mundial (' + anoPart + '). Os outros ' + fmt.pct(100 - br, 1) + ' estão fora daqui.';
    }
    cont.hidden = !anoPart;
  }

  /* ---------- Mercados ---------- */
  function ativoDeSerie(base, serie, extra) {
    const t = A.tendencia(serie, { periodosAno: base.periodosAno || 252, moeda: base.moeda });
    const ultimo = P.serie.ultimo(serie);
    return Object.assign({
      serie,
      tendencia: t,
      preco: ultimo ? ultimo.v : null,
      quando: ultimo ? ultimo.t : null,
      varDia: P.serie.variacaoUltima(serie),
      var30: P.serie.variacaoDias(serie, 30),
      var365: P.serie.variacaoDias(serie, 360),
    }, base, extra || {});
  }

  function montarAtivos() {
    const lista = [];
    const SIGNIFICADO = {
      moedas: 'Para quem quer investir fora, o dólar em alta encarece a compra e, em queda, barateia. Como ninguém acerta o câmbio, a regra é comprar em parcelas.',
      exterior: 'ETF negociado nos EUA, em dólar. Para comprar, é preciso conta em corretora internacional; na B3 há alternativas em reais (ETFs e BDRs).',
      brasil: 'Ativo da B3, em reais. Para começar, ETFs (como BOVA11 e IVVB11) diversificam mais do que ações isoladas.',
      cripto: 'Ativo muito volátil, sem lastro em lucros ou juros. Se quiser ter, no máximo uma fatia pequena (até 5%).',
      ouro: 'Proteção clássica em crises e contra a desvalorização das moedas. Não paga juros nem dividendos. Aqui o preço vem do PAXG, um token lastreado em ouro físico.',
    };
    // Histórico oficial (PTAX) + a cotação mais recente disponível (comercial ou BCE) como último ponto.
    for (const [id, nome, codigo, serie] of [['usd', 'Dólar', 'USD/BRL', E.dolar], ['eur', 'Euro', 'EUR/BRL', E.euro]]) {
      if (!serie || serie.length <= 25) continue;
      const candidatos = [];
      if (E.agora && num(E.agora[id].v)) candidatos.push({ t: E.agora[id].t, v: E.agora[id].v, varDia: E.agora[id].varDia, fonte: 'awesome' });
      if (E.bce && num(E.bce[id])) candidatos.push({ t: Date.parse(E.bce.data + 'T12:00:00Z'), v: E.bce[id], fonte: 'bce' });
      const hoje = candidatos.filter((c) => num(c.t)).sort((a, b) => b.t - a.t)[0];
      const diaPtax = Math.floor(P.serie.ultimo(serie).t / P.DIA);
      const diaHoje = hoje ? Math.floor(hoje.t / P.DIA) : -1;
      let s2 = serie;
      if (diaHoje > diaPtax) s2 = serie.concat([{ t: hoje.t, v: hoje.v }]);
      else if (diaHoje === diaPtax) s2 = serie.slice(0, -1).concat([{ t: hoje.t, v: hoje.v }]);
      const usouHoje = s2 !== serie;
      lista.push(ativoDeSerie({
        id, nome, codigo, grupo: 'moedas', moeda: 'BRL', casas: 4, significado: SIGNIFICADO.moedas,
        explica: id === 'usd' ? 'Quanto custa 1 dólar americano em reais.' : 'Quanto custa 1 euro em reais.',
        fonte: usouHoje ? hoje.fonte : 'bcb',
        desc: usouHoje
          ? 'Histórico: PTAX do Banco Central. Último ponto: ' + P.FONTES[hoje.fonte].nome + ', ' + (hoje.fonte === 'awesome' ? fmt.dataHora(hoje.t) : fmt.data(hoje.t)) + '.'
          : 'Cotação PTAX do Banco Central.',
      }, s2, usouHoje && num(hoje.varDia) ? { varDia: hoje.varDia } : {}));
    }
    for (const c of P.CRIPTO) {
      const s = E.cripto[c.ativo];
      if (!s) continue;
      lista.push(ativoDeSerie({
        id: c.ativo, nome: c.nome, codigo: c.codigo, grupo: 'cripto', moeda: 'BRL', fonte: 'coingecko', periodosAno: 365, explica: c.explica,
        significado: c.ativo === 'ouro' ? SIGNIFICADO.ouro : SIGNIFICADO.cripto,
      }, s));
    }
    if (E.eua) {
      for (const a of P.EUA) {
        const d = E.eua[a.simbolo];
        if (!d || !d.serie || d.serie.length < 25) continue;
        lista.push(ativoDeSerie({ id: a.simbolo, nome: a.nome, codigo: a.simbolo, explica: a.desc + '. Cotado em dólar.', grupo: 'exterior', moeda: 'USD', fonte: 'twelve', significado: SIGNIFICADO.exterior }, d.serie));
      }
    }
    for (const tk in E.b3) {
      const d = E.b3[tk];
      if (!d.serie || d.serie.length < 2) continue;
      lista.push(ativoDeSerie({ id: 'b3-' + tk, nome: d.nome, codigo: d.simbolo, explica: P.DESCRICOES_B3[tk] || 'Negociado na bolsa brasileira (B3), em reais.', grupo: 'brasil', moeda: d.moeda, fonte: 'brapi', significado: SIGNIFICADO.brasil },
        d.serie, num(d.preco) ? { preco: d.preco, varDia: num(d.varDia) ? d.varDia : P.serie.variacaoUltima(d.serie) } : {}));
    }
    return lista;
  }

  function chipTendencia(t) {
    if (!t) return P.el('span', { class: 'chip chip-neutro', texto: 'Histórico curto' });
    const r = A.ROTULO_SINAL[t.sinal];
    return P.el('span', { class: 'chip chip-' + t.sinal, title: 'Tendência das últimas semanas' },
      P.el('span', { class: 'chip-icone', 'aria-hidden': 'true', texto: r.seta }), simples() ? r.simples : r.texto);
  }

  function seloRisco(t) {
    const r = t && t.risco;
    if (!r) return null;
    const pontos = '●'.repeat(r.nivel) + '○'.repeat(4 - r.nivel);
    return P.el('span', { class: 'risco risco-' + r.nivel, title: 'Risco ' + r.rotulo.toLowerCase() + ': ' + r.texto },
      'Risco ', P.el('span', { class: 'risco-pontos', 'aria-hidden': 'true', texto: pontos }),
      P.el('span', { class: 'sr', texto: r.rotulo + ' (' + r.nivel + ' de 4)' }));
  }

  function variacao(rotulo, v) {
    return P.el('span', { class: 'var ' + (v > 0 ? 'sobe' : v < 0 ? 'desce' : '') },
      rotulo + ' ', P.el('strong', { texto: num(v) ? fmt.pct(v, 1, true) : '—' }));
  }

  function renderMercados() {
    const cont = P.limpar($('ativos'));
    const visiveis = (E.ativos || []).filter((a) => E.filtro === 'todos' || a.grupo === E.filtro);
    for (const a of visiveis) {
      const ativo = a.id === E.selecionado;
      const card = P.el('button', {
        type: 'button', class: 'ativo cartao' + (ativo ? ' selecionado' : ''), 'aria-pressed': ativo ? 'true' : 'false',
        onclick: () => { E.selecionado = a.id; renderMercados(); $('detalhe').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); },
      });
      const mini = P.el('div', { class: 'ind-mini' });
      G.mini(mini, a.serie.slice(-90).map((p) => p.v));
      card.append(
        P.el('div', { class: 'ativo-topo' }, P.el('span', { class: 'ativo-nome', texto: a.nome }), P.el('span', { class: 'ativo-codigo', texto: a.codigo })),
        a.explica ? P.el('div', { class: 'ativo-explica', texto: a.explica }) : null,
        P.el('div', { class: 'ativo-preco', texto: fmt.moeda(a.preco, a.moeda, a.grupo === 'moedas' ? 2 : a.casas || (a.preco < 10 ? 4 : 2)) }),
        P.el('div', { class: 'ativo-vars' }, variacao('Hoje', a.varDia), variacao('30 dias', a.var30)),
        mini,
        P.el('div', { class: 'ativo-rodape' }, chipTendencia(a.tendencia), seloRisco(a.tendencia)),
        P.el('span', { class: 'fonte avancado', texto: P.FONTES[a.fonte].nome.split(' (')[0] }));
      cont.append(card);
    }

    // Avisos de grupos que dependem de chave ou que falharam.
    const cfg = config();
    if ((E.filtro === 'todos' || E.filtro === 'exterior') && !E.eua) {
      cont.append(P.el('div', { class: 'ativo cartao ativo-aviso' },
        P.el('strong', { texto: E.euaErro ? 'Bolsa americana indisponível' : 'Bolsa americana (S&P 500, Nasdaq, mundo, Treasuries)' }),
        P.el('p', { texto: E.euaErro ? E.euaErro : cfg.twelve ? 'Carregando…' : 'Crie uma chave gratuita na Twelve Data e guarde como segredo TWELVE_DATA_KEY no GitHub (veja a seção Fontes) para o coletor buscar os ETFs americanos 24 horas.' }),
        P.el('a', { href: '#fontes', texto: 'Configurar chave' })));
    }
    const errosB3 = Object.entries(E.b3Erros);
    if ((E.filtro === 'todos' || E.filtro === 'brasil') && errosB3.length) {
      cont.append(P.el('div', { class: 'ativo cartao ativo-aviso' },
        P.el('strong', { texto: 'B3: ' + errosB3.map(([tk]) => tk).join(', ') + ' indisponível' }),
        P.el('p', { texto: errosB3[0][1] + (cfg.brapi ? '' : ' Sem token, a brapi libera só PETR4, VALE3, ITUB4 e MGLU3.') }),
        P.el('a', { href: '#fontes', texto: 'Ver configurações' })));
    }
    if (!visiveis.length && !cont.childNodes.length) {
      cont.append(P.el('p', { class: 'vazio', texto: E.carregando ? 'Carregando cotações…' : 'Nenhum ativo disponível neste filtro agora.' }));
    }
    renderDetalhe();
  }

  function renderDetalhe() {
    const cont = P.limpar($('detalhe'));
    const lista = E.ativos || [];
    const a = lista.find((x) => x.id === E.selecionado) || lista[0];
    if (!a) {
      cont.append(P.el('p', { class: 'vazio', texto: E.carregando ? 'Carregando…' : 'Escolha um ativo acima para ver a análise.' }));
      return;
    }
    const t = a.tendencia;
    const casas = a.grupo === 'moedas' && simples() ? 2 : a.casas || (a.preco < 10 ? 4 : 2);
    cont.append(
      P.el('div', { class: 'detalhe-topo' },
        P.el('div', null,
          P.el('h3', { texto: a.nome + ' (' + a.codigo + ')' }),
          a.explica ? P.el('p', { class: 'sub', texto: a.explica }) : null,
          a.desc ? P.el('p', { class: 'sub avancado', texto: a.desc }) : null),
        P.el('div', { class: 'detalhe-preco' },
          P.el('span', { class: 'ind-valor', texto: fmt.moeda(a.preco, a.moeda, casas) }),
          chipTendencia(t), seloRisco(t))),
      P.el('div', { class: 'ativo-vars' }, variacao('Hoje', a.varDia), variacao('30 dias', a.var30), variacao('12 meses', a.var365)));

    const graf = P.el('div', { class: 'detalhe-grafico' });
    cont.append(graf);
    const n = Math.min(a.serie.length, 260);
    const ini = a.serie.length - n;
    const x = a.serie.slice(ini).map((p) => p.t);
    const series = [{ nome: 'Preço', cor: 'var(--serie-1)', y: a.serie.slice(ini).map((p) => p.v) }];
    if (t && !simples()) {
      series.push({ nome: 'Média de 20 dias', cor: 'var(--serie-2)', y: t.curta.slice(ini) });
      series.push({ nome: 'Média de ' + t.nLonga + ' dias', cor: 'var(--serie-3)', y: t.longa.slice(ini) });
    }
    const fy = (v) => fmt.moeda(v, a.moeda, casas);
    G.linha(graf, {
      titulo: 'Preço de ' + a.nome + (series.length > 1 ? ' com médias móveis' : ' no último ano'), x, series,
      formatoX: n > 120 ? fmt.mesAno : fmt.diaMes, formatoXLongo: fmt.data, formatoY: (v) => fmt.num(v, v < 10 ? 2 : 0), formatoYLongo: fy, altura: 280,
    });

    const analise = P.el('div', { class: 'duas-colunas analise' });
    const ul = P.el('ul', { class: 'lista' });
    (t ? (simples() ? t.simples : t.textos) : ['Histórico ainda curto para calcular a tendência com segurança.']).forEach((x2) => ul.append(P.el('li', { texto: x2 })));
    analise.append(
      P.el('div', null, P.el('h4', null, simples() ? 'O que os números mostram' : 'Leitura técnica', P.termo(simples() ? 'tendencia' : 'mediaMovel')), ul),
      P.el('div', null, P.el('h4', { texto: 'O que isso significa para você' }), P.el('p', { texto: a.significado })));
    cont.append(analise, P.el('p', { class: 'fonte' }, selo(a.fonte, a.quando ? 'último dado: ' + fmt.data(a.quando) : '')));
  }

  /* ---------- Consultor ---------- */
  function montarQuestionario() {
    const form = $('questionario');
    const salvas = P.armazenamento.ler('respostas', {});
    C.PERGUNTAS.forEach((q, k) => {
      const grupo = P.el('fieldset', { class: 'pergunta' }, P.el('legend', { texto: (k + 1) + '. ' + q.texto }));
      q.opcoes.forEach((op, i) => {
        const input = P.el('input', { type: 'radio', name: q.id, value: String(i) });
        if (String(salvas[q.id]) === String(i)) input.checked = true;
        grupo.append(P.el('label', { class: 'opcao' }, input, P.el('span', { texto: op })));
      });
      form.append(grupo);
    });
    form.addEventListener('change', () => {
      const resp = {};
      for (const q of C.PERGUNTAS) {
        const marcado = form.querySelector('input[name="' + q.id + '"]:checked');
        if (marcado) resp[q.id] = Number(marcado.value);
      }
      P.armazenamento.gravar('respostas', resp);
      renderPlano();
      renderSimulador();
    });
  }

  function respostas() {
    return P.armazenamento.ler('respostas', {});
  }

  const CAMPOS_VALORES = ['disponivel', 'aporte', 'gasto', 'reserva'];
  function montarValores() {
    const salvos = P.armazenamento.ler('valores', {});
    for (const c of CAMPOS_VALORES) if (num(salvos[c])) $('v-' + c).value = salvos[c];
    if (salvos.ajustar === false) $('v-ajustar').checked = false;
    $('valores').addEventListener('input', () => {
      const v = valores();
      P.armazenamento.gravar('valores', v);
      sincronizarSimulador(v);
      renderPlano();
      renderSimulador();
    });
    $('valores').addEventListener('submit', (ev) => ev.preventDefault());
  }
  function valores() {
    const v = {};
    for (const c of CAMPOS_VALORES) {
      const n = parseFloat($('v-' + c).value);
      v[c] = num(n) && n > 0 ? n : 0;
    }
    v.ajustar = $('v-ajustar').checked;
    return v;
  }

  function renderPlano() {
    const perfil = C.avaliarPerfil(respostas());
    const res = P.limpar($('perfil-resultado'));
    const cont = P.limpar($('plano'));
    if (!perfil) {
      const faltam = C.PERGUNTAS.filter((q) => respostas()[q.id] == null).length;
      res.append(P.el('p', { class: 'sub', texto: 'Responda ' + (faltam === C.PERGUNTAS.length ? 'as perguntas' : 'mais ' + faltam + (faltam > 1 ? ' perguntas' : ' pergunta')) + ' para ver seu perfil e seu plano.' }));
      cont.append(P.el('h3', { texto: 'Seu plano aparece aqui' }), P.el('p', { class: 'sub', texto: 'Depois do questionário, o consultor monta um plano com reserva de emergência, divisão entre Brasil e exterior e o caminho mais simples para começar.' }));
      return;
    }
    res.append(
      P.el('div', { class: 'perfil-nome' }, P.el('span', { class: 'sub', texto: 'Seu perfil' }), P.el('strong', { texto: perfil.nome })),
      P.el('p', { texto: perfil.descricao }),
      perfil.notas.map((n) => P.el('p', { class: 'nota', texto: n })));

    const ent = valores();
    const ctx = contexto();
    const plano = C.plano(perfil, ent, ctx, ent.ajustar);

    cont.append(P.el('h3', { texto: 'Seu plano · perfil ' + perfil.nome.toLowerCase() }));
    const passos = P.el('ol', { class: 'passos' });
    plano.passos.forEach((p) => passos.append(P.el('li', null, P.el('strong', { texto: p.titulo }), P.el('p', { texto: p.texto }))));
    cont.append(passos);

    cont.append(P.el('h4', { texto: 'Divisão sugerida (depois da reserva)' }));
    const barra = P.el('div', { class: 'alocacao' });
    cont.append(barra);
    G.barraEmpilhada(barra, plano.alocacao.map((c) => ({
      nome: c.nome, valor: c.pct, cor: c.cor, corTexto: c.corTexto,
      detalhe: (c.exterior ? 'Exterior · ' : 'Brasil · ') + 'risco: ' + c.risco.toLowerCase(),
    })));
    cont.append(P.el('p', { class: 'resumo-exterior' },
      P.el('strong', { texto: fmt.pct(plano.exteriorPct, 0) + ' no exterior' }),
      ' · ' + fmt.pct(100 - plano.exteriorPct, 0) + ' no Brasil, além da reserva de emergência em reais.'));
    if (plano.ajustes.length) {
      cont.append(P.el('div', { class: 'ajustes' },
        P.el('strong', { texto: 'Ajustes ao momento atual' }),
        P.el('ul', { class: 'lista' }, plano.ajustes.map((a) => P.el('li', { texto: a })))));
    }

    const temValores = ent.disponivel > 0 || ent.aporte > 0;
    const t = P.el('table', { class: 'tabela-plano tabela-alocacao' });
    t.append(P.el('thead', null, P.el('tr', null,
      P.el('th', { scope: 'col', texto: 'Classe' }),
      P.el('th', { scope: 'col', texto: '%' }),
      temValores ? P.el('th', { scope: 'col', texto: 'Hoje' }) : null,
      temValores ? P.el('th', { scope: 'col', texto: 'Por mês' }) : null,
      P.el('th', { scope: 'col', texto: 'Onde investir (exemplos)' }),
      P.el('th', { scope: 'col', texto: 'Risco' }))));
    const corpo = P.el('tbody');
    for (const c of plano.alocacao) {
      if (!c.pct) continue;
      const chave = P.el('span', { class: 'chave-bloco', 'aria-hidden': 'true' });
      chave.style.background = c.cor;
      corpo.append(P.el('tr', null,
        P.el('th', { scope: 'row' }, chave, c.nome, c.exterior ? P.el('span', { class: 'etiqueta', texto: 'exterior' }) : null),
        P.el('td', { class: 'numero', 'data-rotulo': 'Fatia', texto: fmt.pct(c.pct, 0) }),
        temValores ? P.el('td', { class: 'numero', 'data-rotulo': 'Hoje', texto: fmt.brl(c.hoje, 0) }) : null,
        temValores ? P.el('td', { class: 'numero', 'data-rotulo': 'Por mês', texto: plano.reserva.faltaDepois > 0 ? 'após a reserva' : fmt.brl(c.mes, 0) }) : null,
        P.el('td', { 'data-rotulo': 'Onde', texto: c.onde }),
        P.el('td', { 'data-rotulo': 'Risco', texto: c.risco })));
    }
    t.append(corpo);
    cont.append(P.el('div', { class: 'tabela-rolagem' }, t));
    cont.append(P.el('p', { class: 'nota', texto: 'Os nomes de ETFs são exemplos de produtos amplos e de baixo custo, para você pesquisar — não são recomendação de compra. Confira taxas, liquidez e tributação antes de investir.' }));
  }

  /* ---------- Simulador ---------- */
  const CAMPOS_SIM = ['inicial', 'mensal', 'anos', 'retorno', 'cambio', 'custo'];

  function montarSimulador() {
    const salvos = P.armazenamento.ler('simulador', {});
    for (const c of CAMPOS_SIM) if (num(salvos[c])) { $('s-' + c).value = salvos[c]; $('s-' + c).dataset.editado = '1'; }
    $('simulador').addEventListener('input', (ev) => {
      if (ev.target && ev.target.id) ev.target.dataset.editado = '1';
      const s = {};
      for (const c of CAMPOS_SIM) if ($('s-' + c).dataset.editado) s[c] = parseFloat($('s-' + c).value);
      P.armazenamento.gravar('simulador', s);
      renderSimulador();
    });
    $('simulador').addEventListener('submit', (ev) => ev.preventDefault());
  }

  function sincronizarSimulador(v) {
    if (!$('s-inicial').dataset.editado && v.disponivel > 0) $('s-inicial').value = v.disponivel;
    if (!$('s-mensal').dataset.editado && v.aporte > 0) $('s-mensal').value = v.aporte;
  }

  function cambioPadrao(ctx) {
    // Paridade de inflação: no longo prazo, o real tende a perder valor na diferença entre a inflação daqui e a dos EUA.
    const ipcaBr = C.focusItem(ctx, 'IPCA', ANO + 1);
    const infl = ctx.fmi && ctx.fmi.inflacao;
    const eua = infl && infl.USA ? C.mediaFmi(infl, 'USA', ANO + 1, ANO + 3) : null;
    const br = ipcaBr ? ipcaBr.mediana : infl && infl.BRA ? C.mediaFmi(infl, 'BRA', ANO + 1, ANO + 3) : null;
    if (num(br) && num(eua)) return { valor: Math.round((((1 + br / 100) / (1 + eua / 100)) - 1) * 1000) / 10, br, eua };
    return null;
  }

  function renderSimulador() {
    const ctx = contexto();
    const cp = cambioPadrao(ctx);
    if (cp && !$('s-cambio').dataset.editado) $('s-cambio').value = cp.valor;

    const ler = (c, padrao) => { const n = parseFloat($('s-' + c).value); return num(n) ? n : padrao; };
    const anos = Math.max(1, Math.min(40, Math.round(ler('anos', 10))));
    const caminho = [];
    if (num(ctx.selic)) caminho.push(ctx.selic);
    for (let a = ANO + 1; a <= ANO + 3; a++) {
      const it = C.focusItem(ctx, 'Selic', a);
      if (it) caminho.push(it.mediana);
    }
    const premissas = $('s-premissas');
    const graf = $('graf-simulador');
    const resultado = P.limpar($('s-resultado'));
    if (!caminho.length) {
      premissas.textContent = 'Aguardando a Selic do Banco Central para simular a renda fixa…';
      P.limpar(graf);
      return;
    }
    const p = {
      inicial: Math.max(0, ler('inicial', 0)), mensal: Math.max(0, ler('mensal', 0)), anos,
      selicCaminho: caminho, retornoUsd: ler('retorno', 7), cambio: ler('cambio', 3), custo: Math.max(0, ler('custo', 1.5)),
    };
    premissas.textContent = 'Premissas: Selic de ' + caminho.map((v) => fmt.pct(v, 2)).join(' → ') + ' nos próximos anos (atual e Focus), depois estável. '
      + 'Carteira global: ' + fmt.pct(p.retornoUsd, 1) + ' ao ano em dólar e dólar subindo ' + fmt.pct(p.cambio, 1) + ' ao ano'
      + (cp ? ' (padrão calculado pela diferença de inflação: Brasil ' + fmt.pct(cp.br, 1) + ' × EUA ' + fmt.pct(cp.eua, 1) + ')' : '')
      + '. No longo prazo, as ações globais renderam algo entre 7% e 10% ao ano em dólar, com anos de queda forte.';

    const r = C.simular(p);
    const series = [
      { nome: 'Poupança', cor: 'var(--serie-4)', y: r.poupanca },
      { nome: 'CDB 100% do CDI', cor: 'var(--serie-1)', y: r.cdb },
      { nome: 'Carteira global (hipótese)', cor: 'var(--serie-3)', y: r.global },
      { nome: 'Total investido', cor: 'var(--mudo)', y: r.aportado },
    ];
    G.linha(graf, {
      titulo: 'Simulação de patrimônio', x: r.x, series, rotuloX: 'Ano',
      formatoX: (a) => (a === 0 ? 'hoje' : 'ano ' + fmt.num(a, Number.isInteger(a) ? 0 : 1)), formatoXLongo: (a) => (a === 0 ? 'Hoje' : 'Após ' + fmt.num(a, Number.isInteger(a) ? 0 : 1) + (a === 1 ? ' ano' : ' anos')),
      formatoY: fmt.brlCompacto, formatoYLongo: (v) => fmt.brl(v, 0), incluirZero: true, altura: 280,
    });

    const fim = r.x.length - 1;
    const investido = r.aportado[fim];
    const t = P.el('table', { class: 'tabela-plano' });
    t.append(P.el('thead', null, P.el('tr', null, ['Cenário', 'Valor final', 'Ganho líquido', 'Em relação ao investido'].map((h) => P.el('th', { scope: 'col', texto: h })))));
    const corpo = P.el('tbody');
    for (const se of series.slice(0, 3)) {
      const v = se.y[fim];
      const chave = P.el('span', { class: 'chave-linha', 'aria-hidden': 'true' });
      chave.style.background = se.cor;
      corpo.append(P.el('tr', null,
        P.el('th', { scope: 'row' }, chave, se.nome),
        P.el('td', { class: 'numero', texto: fmt.brl(v, 0) }),
        P.el('td', { class: 'numero', texto: fmt.brl(v - investido, 0) }),
        P.el('td', { class: 'numero', texto: investido ? fmt.pct((v / investido - 1) * 100, 0, true) : '—' })));
    }
    corpo.append(P.el('tr', null, P.el('th', { scope: 'row', texto: 'Total investido' }), P.el('td', { class: 'numero', texto: fmt.brl(investido, 0) }), P.el('td', { texto: '' }), P.el('td', { texto: '' })));
    t.append(corpo);
    const [poup, cdb, glob] = series.slice(0, 3).map((se) => se.y[fim]);
    const anosTexto = fmt.num(r.x[fim], Number.isInteger(r.x[fim]) ? 0 : 1) + (r.x[fim] === 1 ? ' ano' : ' anos');
    resultado.append(
      P.el('p', { class: 'resumo-simulacao' },
        P.el('strong', { texto: 'Em resumo: ' }),
        'colocando ' + fmt.brl(p.inicial, 0) + ' agora e ' + fmt.brl(p.mensal, 0) + ' por mês durante ' + anosTexto
        + ', você terá investido ' + fmt.brl(investido, 0) + ' do seu bolso. Com os juros, isso viraria cerca de '
        + fmt.brl(cdb, 0) + ' num CDB, ' + fmt.brl(poup, 0) + ' na poupança e ' + fmt.brl(glob, 0)
        + ' na carteira global, se as hipóteses se confirmarem. A diferença mostra a força dos juros compostos (juros sobre juros).'),
      t);
  }

  /* ---------- Fontes e configurações ---------- */
  function renderFontes() {
    const cont = P.limpar($('tabela-fontes'));
    const t = P.el('table', { class: 'tabela-fontes' });
    t.append(P.el('thead', null, P.el('tr', null, ['Fonte', 'Tipo', 'Para que serve', 'Situação'].map((h) => P.el('th', { scope: 'col', texto: h })))));
    const corpo = P.el('tbody');
    const cfg = config();
    for (const id in P.FONTES) {
      const f = P.FONTES[id];
      const r = resumoFonte(id);
      let estado;
      if (!r) {
        if (id === 'twelve' && !cfg.twelve) estado = P.el('span', { class: 'estado estado-neutro', texto: '○ Sem chave (opcional)' });
        else if (id === 'bancoMundial') estado = P.el('span', { class: 'estado estado-neutro', texto: '○ Não foi necessário' });
        else estado = P.el('span', { class: 'estado estado-neutro', texto: E.carregando ? '… Carregando' : '○ Sem consulta' });
      } else if (r.estado === 'ok') {
        estado = P.el('span', { class: 'estado estado-ok', texto: '✓ Ok · ' + fmt.dataHora(r.quando) + (r.viaColetor ? ' (via coletor)' : r.parcial ? ' (parcial)' : '') });
      } else if (id === 'coletor' && /404/.test(r.erro || '')) {
        estado = P.el('span', { class: 'estado estado-neutro', texto: '○ Ainda não rodou: veja o passo a passo abaixo' });
      } else if (r.estado === 'cache') {
        estado = P.el('span', { class: 'estado estado-cache', texto: '⚠ Usando dado salvo de ' + fmt.dataHora(r.quando) });
      } else {
        estado = P.el('span', { class: 'estado estado-erro', texto: '✕ Indisponível' });
      }
      const detalheErro = r && r.erro && r.estado !== 'ok' && !(id === 'coletor' && /404/.test(r.erro)) ? P.el('div', { class: 'sub', texto: r.erro }) : null;
      corpo.append(P.el('tr', null,
        P.el('th', { scope: 'row' }, P.el('a', { href: f.site, target: '_blank', rel: 'noopener noreferrer', texto: f.nome })),
        P.el('td', { texto: f.tipo }),
        P.el('td', { texto: f.uso }),
        P.el('td', null, estado, detalheErro)));
    }
    t.append(corpo);
    cont.append(t);
  }

  function montarConfig() {
    const cfg = config();
    $('c-twelve').value = cfg.twelve;
    $('c-brapi').value = cfg.brapi;
    $('c-b3').value = cfg.b3;
    $('c-b3').placeholder = (cfg.brapi ? P.B3_COM_TOKEN : P.B3_SEM_TOKEN).join(',');
    $('config').addEventListener('submit', (ev) => {
      ev.preventDefault();
      const limpa = (s) => s.trim().replace(/[^A-Za-z0-9_-]/g, '');
      const novo = { twelve: limpa($('c-twelve').value), brapi: limpa($('c-brapi').value), b3: $('c-b3').value.trim().toUpperCase() };
      P.armazenamento.gravar('config', novo);
      $('c-b3').placeholder = (novo.brapi ? P.B3_COM_TOKEN : P.B3_SEM_TOKEN).join(',');
      $('c-mensagem').textContent = 'Configurações salvas neste navegador. Atualizando…';
      Promise.all([carregarB3(true), carregarEua(true)]).then(() => {
        $('c-mensagem').textContent = 'Pronto. Veja a situação de cada fonte na tabela acima.';
        renderTudo();
        situacao();
      });
    });
    $('c-apagar').addEventListener('click', () => {
      P.armazenamento.gravar('config', { twelve: '', brapi: '', b3: $('c-b3').value.trim().toUpperCase() });
      P.armazenamento.remover('cache:twelve-eua');
      $('c-twelve').value = '';
      $('c-brapi').value = '';
      $('c-mensagem').textContent = 'Chaves apagadas deste navegador.';
      Promise.all([carregarB3(false), carregarEua(false)]).then(renderTudo);
    });
  }

  /* ---------- Tema, filtros e início ---------- */
  function montarTema() {
    const salvo = P.armazenamento.ler('tema', null);
    if (salvo) document.documentElement.dataset.theme = salvo;
    $('btn-tema').addEventListener('click', () => {
      const atual = document.documentElement.dataset.theme
        || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      const novo = atual === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = novo;
      P.armazenamento.gravar('tema', novo);
    });
  }

  function montarFiltros() {
    document.querySelectorAll('.filtro').forEach((b) => {
      b.addEventListener('click', () => {
        E.filtro = b.dataset.filtro;
        document.querySelectorAll('.filtro').forEach((x) => x.setAttribute('aria-pressed', x === b ? 'true' : 'false'));
        const primeiro = (E.ativos || []).find((a) => E.filtro === 'todos' || a.grupo === E.filtro);
        if (primeiro && E.filtro !== 'todos') E.selecionado = primeiro.id;
        renderMercados();
      });
    });
  }

  function iniciar() {
    montarModo();
    montarTema();
    P.montarGlossario($('verbetes'), $('busca-termo'));
    montarFiltros();
    montarQuestionario();
    montarValores();
    montarSimulador();
    montarConfig();
    sincronizarSimulador(valores());
    renderTudo();
    $('btn-atualizar').addEventListener('click', () => carregar(true));
    carregar(false);
    // Atualiza sozinho a cada 10 minutos (o cache evita excesso de consultas).
    setInterval(() => { if (!document.hidden) carregar(false); }, 10 * 60000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})(window.Painel);
