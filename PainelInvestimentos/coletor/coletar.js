#!/usr/bin/env node
/* Coletor do Painel do Investidor. Roda no GitHub Actions a cada 30 minutos:
   busca todas as fontes num servidor (sem as limitações do navegador), junta com
   o histórico da coleta anterior e grava um único JSON que o painel lê ao abrir.

   Uso: node coletar.js <anterior.json> <saida.json>
   Variáveis de ambiente (opcionais): TWELVE_DATA_KEY, BRAPI_TOKEN, AWESOME_API_KEY, TICKERS_B3 */
'use strict';

const fs = require('fs');
const path = require('path');

// Os módulos do painel foram escritos para o navegador; estes substitutos permitem reaproveitá-los aqui.
globalThis.window = globalThis;
const memoria = new Map();
globalThis.localStorage = {
  getItem: (k) => (memoria.has(k) ? memoria.get(k) : null),
  setItem: (k, v) => { memoria.set(k, String(v)); },
  removeItem: (k) => { memoria.delete(k); },
  clear: () => { memoria.clear(); },
};
// Alguns sites (como o do FMI) recusam programas sem identificação; o coletor se apresenta.
const fetchOriginal = globalThis.fetch;
globalThis.fetch = (url, opcoes = {}) => fetchOriginal(url, Object.assign({}, opcoes, {
  headers: Object.assign({
    'User-Agent': 'Mozilla/5.0 (compatible; PainelDoInvestidor/1.0; +https://github.com/stragalinos/aula1)',
    Accept: 'application/json, text/plain, */*',
  }, opcoes.headers),
}));
require(path.join(__dirname, '..', 'js', 'util.js'));
require(path.join(__dirname, '..', 'js', 'fontes.js'));
const P = globalThis.Painel;
const mesclar = P.serie.mesclar;

/* Pregão aberto (com folga para o fechamento), em dias úteis, no horário UTC. */
function pregaoAberto(agora, inicioUTC, fimUTC) {
  const d = new Date(agora);
  const dia = d.getUTCDay();
  const hora = d.getUTCHours();
  return dia >= 1 && dia <= 5 && hora >= inicioUTC && hora < fimUTC;
}

function lerTickers(texto, token) {
  const lista = String(texto || '').toUpperCase().split(/[\s,;]+/).filter((t) => /^[A-Z0-9^.]{2,12}$/.test(t));
  if (lista.length) return lista.slice(0, 15);
  return token ? P.B3_COM_TOKEN : P.B3_SEM_TOKEN;
}

async function coletar(anterior, { agora = Date.now(), env = process.env } = {}) {
  const ant = (anterior && anterior.dados) || {};
  const antFontes = (anterior && anterior.fontes) || {};
  const quandoAnterior = (fonte) => {
    const ok = (antFontes[fonte] || []).filter((s) => s.quando);
    return ok.length ? Math.max(...ok.map((s) => s.quando)) : anterior && anterior.geradoEm;
  };
  const fontes = {};
  const dados = {};

  function anotar(fonte, r, erro) {
    (fontes[fonte] = fontes[fonte] || []).push(r
      ? { origem: r.origem, quando: r.quando }
      : { origem: 'erro', erro: erro ? erro.message : 'erro desconhecido' });
  }
  /* Se a fonte falhar, mantém o dado anterior e registra a data dele. */
  function manterAnterior(fonte, erro) {
    const lista = fontes[fonte] || [];
    const ultimo = lista[lista.length - 1];
    const quando = quandoAnterior(fonte);
    if (ultimo && ultimo.origem === 'erro' && quando) {
      lista[lista.length - 1] = { origem: 'anterior', quando, erro: erro || ultimo.erro };
    }
  }
  async function guardar(fonte, promessa) {
    try {
      const r = await promessa;
      anotar(fonte, r);
      return r.dados;
    } catch (e) {
      anotar(fonte, null, e);
      return null;
    }
  }

  // Banco Central: séries do SGS (histórico acumulado entre coletas).
  const sgs = (codigo, op) => guardar('bcb', P.dados.sgs(codigo, Object.assign({ forcar: true }, op)));
  const series = {
    selic: [432, { anos: 2, faixa: [0, 60] }],
    cdi: [4389, { ultimos: 10, faixa: [0, 60] }],
    ipca12: [13522, { anos: 3, faixa: [-10, 100] }],
    dolar: [1, { anos: 1, faixa: [1, 20] }],
    euro: [21619, { anos: 1, faixa: [1, 25] }],
  };
  for (const [chave, [codigo, op]] of Object.entries(series)) {
    const nova = await sgs(codigo, op);
    if (!nova && ant[chave]) manterAnterior('bcb');
    dados[chave] = mesclar(ant[chave], nova);
  }

  // Boletim Focus.
  dados.focus = await guardar('focus', P.dados.focus(true));
  if (!dados.focus && ant.focus) { dados.focus = ant.focus; manterAnterior('focus'); }

  // FMI, com o Banco Mundial como reserva.
  dados.fmi = {};
  dados.fmiOrigem = {};
  for (const chave of Object.keys(P.FMI_INDICADORES)) {
    let d = await guardar('fmi', P.dados.fmi(chave, true));
    let origem = 'fmi';
    if (!d && P.FMI_INDICADORES[chave].bancoMundial) {
      d = await guardar('bancoMundial', P.dados.bancoMundial(chave, true));
      origem = 'bancoMundial';
    }
    if (d) {
      dados.fmi[chave] = d;
      dados.fmiOrigem[chave] = origem;
    } else if (ant.fmi && ant.fmi[chave]) {
      dados.fmi[chave] = ant.fmi[chave];
      dados.fmiOrigem[chave] = (ant.fmiOrigem || {})[chave];
      manterAnterior('fmi');
    }
  }

  // Câmbio: BCE e cotação comercial.
  dados.bce = await guardar('bce', P.dados.bce(true));
  if (!dados.bce && ant.bce) { dados.bce = ant.bce; manterAnterior('bce'); }
  dados.agora = await guardar('awesome', P.dados.cambioAgora(true, env.AWESOME_API_KEY));
  if (!dados.agora && ant.agora) { dados.agora = ant.agora; manterAnterior('awesome'); }

  // Cripto e ouro (24 horas por dia).
  dados.cripto = {};
  for (const c of P.CRIPTO) {
    const antiga = ant.cripto && ant.cripto[c.ativo];
    const nova = await guardar('coingecko', P.dados.cripto(c.id, true));
    if (!nova && antiga) manterAnterior('coingecko');
    dados.cripto[c.ativo] = mesclar(antiga, nova);
  }

  // B3: só consulta durante o pregão; fora dele, repete a última coleta (economiza a cota gratuita).
  const token = env.BRAPI_TOKEN || '';
  const tickers = lerTickers(env.TICKERS_B3, token);
  const b3Aberta = pregaoAberto(agora, 12, 22);
  dados.b3 = {};
  dados.b3Erros = {};
  for (const tk of tickers) {
    const antigo = ant.b3 && ant.b3[tk];
    const erroAntigo = ant.b3Erros && ant.b3Erros[tk];
    if (!b3Aberta && (antigo || erroAntigo)) {
      if (antigo) dados.b3[tk] = antigo; else dados.b3Erros[tk] = erroAntigo;
      continue;
    }
    try {
      const r = await P.dados.b3(tk, token, true);
      anotar('brapi', r);
      dados.b3[tk] = Object.assign({}, r.dados, { serie: mesclar(antigo && antigo.serie, r.dados.serie) });
    } catch (e) {
      anotar('brapi', null, e);
      if (antigo) { dados.b3[tk] = antigo; manterAnterior('brapi', e.message); } else dados.b3Erros[tk] = e.message;
    }
  }
  if (!fontes.brapi && antFontes.brapi) fontes.brapi = antFontes.brapi;

  // Bolsa americana: precisa da chave da Twelve Data; também respeita o horário do pregão.
  const chave = env.TWELVE_DATA_KEY || '';
  dados.eua = null;
  if (chave) {
    if (!pregaoAberto(agora, 13, 22) && ant.eua) {
      dados.eua = ant.eua;
      if (antFontes.twelve) fontes.twelve = antFontes.twelve;
    } else {
      try {
        const r = await P.dados.eua(chave, true);
        anotar('twelve', r);
        dados.eua = {};
        for (const s of Object.keys(r.dados)) {
          const antigo = ant.eua && ant.eua[s];
          const novo = r.dados[s];
          dados.eua[s] = novo.serie ? { serie: mesclar(antigo && antigo.serie, novo.serie) } : antigo || novo;
        }
      } catch (e) {
        anotar('twelve', null, e);
        if (ant.eua) { dados.eua = ant.eua; manterAnterior('twelve', e.message); } else dados.euaErro = e.message;
      }
    }
  }

  return { versao: 1, geradoEm: agora, fontes, dados };
}

function resumo(resultado) {
  const linhas = [];
  for (const [fonte, lista] of Object.entries(resultado.fontes)) {
    const ok = lista.filter((s) => s.origem === 'rede').length;
    const erro = lista.find((s) => s.erro);
    linhas.push(fonte.padEnd(13) + ok + '/' + lista.length + ' ok' + (erro ? '  · ' + erro.erro : ''));
  }
  return linhas.join('\n');
}

async function principal() {
  const [entrada, saida] = process.argv.slice(2);
  if (!saida) {
    console.error('Uso: node coletar.js <anterior.json> <saida.json>');
    process.exit(2);
  }
  let anterior = {};
  try { anterior = JSON.parse(fs.readFileSync(entrada, 'utf8')); } catch (_) { /* primeira coleta */ }
  const resultado = await coletar(anterior);
  console.log(resumo(resultado));
  const algumOk = Object.values(resultado.fontes).flat().some((s) => s.origem === 'rede');
  if (!algumOk) {
    console.error('Nenhuma fonte respondeu: o arquivo anterior foi mantido.');
    process.exit(1);
  }
  fs.writeFileSync(saida, JSON.stringify(resultado));
  console.log('Gravado ' + saida + ' (' + Math.round(fs.statSync(saida).size / 1024) + ' KB)');
}

if (require.main === module) {
  principal().catch((e) => { console.error(e); process.exit(1); });
}

module.exports = { coletar, lerTickers, pregaoAberto };
