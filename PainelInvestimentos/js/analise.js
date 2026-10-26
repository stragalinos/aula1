/* Análise de tendência com indicadores clássicos e transparentes:
   médias móveis (20 e 50 períodos), inclinação dos últimos 30 períodos,
   IFR/RSI de 14 períodos e volatilidade anualizada.
   Nada aqui prevê o futuro: descreve o comportamento recente do preço. */
(function (P) {
  'use strict';

  const A = {};
  const fmt = P.fmt;

  A.media = (arr) => arr.reduce((s, x) => s + x, 0) / arr.length;

  /* Média móvel simples; posições sem dados suficientes ficam null. */
  A.mms = function (vals, n) {
    const out = new Array(vals.length).fill(null);
    let soma = 0;
    for (let i = 0; i < vals.length; i++) {
      soma += vals[i];
      if (i >= n) soma -= vals[i - n];
      if (i >= n - 1) out[i] = soma / n;
    }
    return out;
  };

  /* Índice de Força Relativa (método de Wilder). */
  A.ifr = function (vals, n = 14) {
    if (vals.length <= n) return null;
    let ganho = 0;
    let perda = 0;
    for (let i = 1; i <= n; i++) {
      const d = vals[i] - vals[i - 1];
      if (d > 0) ganho += d; else perda -= d;
    }
    ganho /= n;
    perda /= n;
    for (let i = n + 1; i < vals.length; i++) {
      const d = vals[i] - vals[i - 1];
      ganho = (ganho * (n - 1) + Math.max(d, 0)) / n;
      perda = (perda * (n - 1) + Math.max(-d, 0)) / n;
    }
    if (perda === 0) return 100;
    return 100 - 100 / (1 + ganho / perda);
  };

  /* Desvio-padrão dos retornos diários, anualizado, em %. */
  A.volatilidade = function (vals, periodosAno) {
    const r = [];
    for (let i = 1; i < vals.length; i++) r.push(Math.log(vals[i] / vals[i - 1]));
    if (r.length < 10) return null;
    const m = A.media(r);
    const variancia = r.reduce((s, x) => s + (x - m) ** 2, 0) / (r.length - 1);
    return Math.sqrt(variancia) * Math.sqrt(periodosAno) * 100;
  };

  /* Inclinação da reta de regressão, em % do preço médio por período. */
  A.inclinacao = function (vals) {
    const n = vals.length;
    const xm = (n - 1) / 2;
    const ym = A.media(vals);
    let num = 0;
    let den = 0;
    for (let i = 0; i < n; i++) {
      num += (i - xm) * (vals[i] - ym);
      den += (i - xm) ** 2;
    }
    return den ? (num / den) / ym * 100 : 0;
  };

  A.classeVolatilidade = function (vol) {
    if (vol < 10) return { nome: 'baixa', texto: 'costuma variar pouco' };
    if (vol < 25) return { nome: 'moderada', texto: 'oscila de forma parecida com uma bolsa de valores' };
    if (vol < 50) return { nome: 'alta', texto: 'pode ter quedas fortes em poucas semanas' };
    return { nome: 'muito alta', texto: 'quedas de 50% ou mais já aconteceram e podem se repetir' };
  };

  /* Classifica a tendência a partir de três sinais independentes. */
  A.tendencia = function (serie, { periodosAno = 252, moeda = 'BRL' } = {}) {
    if (!serie || serie.length < 25) return null;
    const vals = serie.map((p) => p.v);
    const ultimo = vals[vals.length - 1];
    const nLonga = Math.min(50, vals.length - 5);
    const curta = A.mms(vals, 20);
    const longa = A.mms(vals, nLonga);
    const m20 = curta[curta.length - 1];
    const m50 = longa[longa.length - 1];
    const janela = vals.slice(-30);
    const movimento = A.inclinacao(janela) * (janela.length - 1); // % aproximada na janela
    const vol = A.volatilidade(vals.slice(-120), periodosAno);
    const limiar = Math.max(1, (vol || 10) * 0.1);
    const ifr = A.ifr(vals);

    let pontos = 0;
    pontos += ultimo > m20 ? 1 : -1;
    pontos += m20 > m50 ? 1 : -1;
    pontos += movimento > limiar ? 1 : movimento < -limiar ? -1 : 0;
    const sinal = pontos >= 2 ? 'alta' : pontos <= -2 ? 'baixa' : 'lateral';

    const textos = [];
    const preco = fmt.moeda(ultimo, moeda, ultimo < 10 ? 4 : 2);
    if (sinal === 'alta') {
      textos.push('Tendência de alta: o preço (' + preco + ') está acima da média dos últimos 20 dias, e essa média está acima da de ' + nLonga + ' dias. O movimento recente é de valorização.');
    } else if (sinal === 'baixa') {
      textos.push('Tendência de baixa: o preço (' + preco + ') está abaixo da média dos últimos 20 dias, e essa média está abaixo da de ' + nLonga + ' dias. O movimento recente é de desvalorização.');
    } else {
      textos.push('Sem tendência clara (lateral): os sinais se contradizem e o preço (' + preco + ') oscila sem direção definida.');
    }
    if (ifr != null) {
      const n = fmt.num(ifr, 0);
      if (ifr >= 70) textos.push('IFR em ' + n + ' (acima de 70): subiu rápido e pode corrigir. Se for comprar, faça em parcelas.');
      else if (ifr <= 30) textos.push('IFR em ' + n + ' (abaixo de 30): caiu muito em pouco tempo. Pode haver repique, mas não tente adivinhar o fundo.');
      else textos.push('IFR em ' + n + ': nem esticado para cima, nem para baixo.');
    }
    if (vol != null) {
      const c = A.classeVolatilidade(vol);
      textos.push('Volatilidade de ' + fmt.pct(vol, 0) + ' ao ano (' + c.nome + '): ' + c.texto + '.');
    }

    return { sinal, pontos, ultimo, m20, m50, nLonga, ifr, vol, movimento, curta, longa, textos };
  };

  A.ROTULO_SINAL = {
    alta: { seta: '▲', texto: 'Alta' },
    baixa: { seta: '▼', texto: 'Baixa' },
    lateral: { seta: '▶', texto: 'Lateral' },
  };

  P.analise = A;
})(window.Painel);
