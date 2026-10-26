/* Gráficos em SVG puro (sem bibliotecas): linhas com mira e dica ao passar
   o mouse/teclado, minigráficos e barra empilhada de alocação.
   Cada gráfico de linhas também oferece os dados em tabela. */
(function (P) {
  'use strict';

  const NS = 'http://www.w3.org/2000/svg';
  const G = {};

  function s(tag, attrs, pai) {
    const e = document.createElementNS(NS, tag);
    if (attrs) for (const k in attrs) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    if (pai) pai.appendChild(e);
    return e;
  }

  function ticksBonitos(min, max, alvo) {
    if (min === max) {
      const d = Math.abs(min) * 0.05 || 1;
      min -= d;
      max += d;
    }
    const bruto = (max - min) / alvo;
    const mag = Math.pow(10, Math.floor(Math.log10(bruto)));
    const norm = bruto / mag;
    const passo = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
    const ini = Math.floor(min / passo) * passo;
    const fim = Math.ceil(max / passo) * passo;
    const ticks = [];
    for (let v = ini; v <= fim + passo / 2; v += passo) ticks.push(Number(v.toFixed(10)));
    return { ticks, min: ini, max: fim };
  }

  function legenda(series, tipo) {
    const ul = P.el('ul', { class: 'legenda' });
    for (const se of series) {
      const chave = P.el('span', { class: tipo === 'bloco' ? 'chave-bloco' : 'chave-linha', 'aria-hidden': 'true' });
      chave.style.background = se.cor;
      ul.append(P.el('li', null, chave, P.el('span', { texto: se.nome })));
    }
    return ul;
  }

  function tabela(op) {
    const det = P.el('details', { class: 'tabela-dados' }, P.el('summary', { texto: 'Ver dados em tabela' }));
    det.addEventListener('toggle', () => {
      if (!det.open || det.querySelector('table')) return;
      const fx = op.formatoXLongo || op.formatoX || String;
      const fy = op.formatoYLongo || op.formatoY;
      const t = P.el('table');
      t.append(P.el('thead', null, P.el('tr', null,
        P.el('th', { scope: 'col', texto: op.rotuloX || 'Data' }),
        op.series.map((se) => P.el('th', { scope: 'col', texto: se.nome })))));
      const corpo = P.el('tbody');
      for (let i = op.x.length - 1; i >= 0; i--) {
        corpo.append(P.el('tr', null,
          P.el('th', { scope: 'row', texto: fx(op.x[i]) }),
          op.series.map((se) => P.el('td', { texto: se.y[i] == null ? '—' : fy(se.y[i]) }))));
      }
      t.append(corpo);
      det.append(P.el('div', { class: 'tabela-rolagem' }, t));
    });
    return det;
  }

  function observarLargura(cont, desenhar) {
    if (cont._observador) cont._observador.disconnect();
    if (typeof ResizeObserver === 'undefined') return;
    let largura = cont.clientWidth;
    let pendente = false;
    cont._observador = new ResizeObserver(() => {
      if (pendente || cont.clientWidth === largura) return;
      pendente = true;
      requestAnimationFrame(() => {
        pendente = false;
        largura = cont.clientWidth;
        desenhar();
      });
    });
    cont._observador.observe(cont);
  }

  /* op: { x: [], series: [{nome, cor, y: []}], formatoX, formatoXLongo, formatoY,
           formatoYLongo, altura, sombraDesde, rotuloSombra, referencias: [{valor, rotulo}],
           incluirZero, rotuloX, titulo } */
  G.linha = function (cont, op) {
    P.limpar(cont);
    const raiz = P.el('div', { class: 'grafico' });
    if (op.series.length > 1) raiz.append(legenda(op.series, 'linha'));
    const area = P.el('div', { class: 'grafico-area' });
    const dica = P.el('div', { class: 'dica' });
    dica.hidden = true;
    area.append(dica);
    raiz.append(area);
    if (op.tabela !== false) raiz.append(tabela(op));
    cont.append(raiz);
    const desenhar = () => desenharLinha(area, dica, op);
    desenhar();
    observarLargura(cont, desenhar);
  };

  function desenharLinha(area, dica, op) {
    const antigo = area.querySelector('svg');
    if (antigo) antigo.remove();
    dica.hidden = true;

    const L = Math.max(area.clientWidth || 0, 260);
    const H = op.altura || 240;
    const n = op.x.length;
    const valores = op.series.flatMap((se) => se.y).filter((v) => v != null && isFinite(v));
    if (!valores.length || n < 2) {
      area.append(P.el('p', { class: 'vazio', texto: 'Sem dados suficientes para o gráfico.' }));
      return;
    }
    let min = Math.min(...valores, ...(op.referencias || []).map((r) => r.valor));
    let max = Math.max(...valores, ...(op.referencias || []).map((r) => r.valor));
    if (op.incluirZero) { min = Math.min(0, min); max = Math.max(0, max); }
    const esc = ticksBonitos(min, max, H < 200 ? 3 : 5);
    const fy = op.formatoY || ((v) => P.fmt.num(v));
    const fyLongo = op.formatoYLongo || fy;
    const fx = op.formatoX || String;

    const finais = [];
    for (const se of op.series) {
      let i = se.y.length - 1;
      while (i >= 0 && (se.y[i] == null || !isFinite(se.y[i]))) i--;
      if (i >= 0) finais.push({ se, i, v: se.y[i] });
    }
    const rotularFinais = op.rotuloFinal !== false && op.series.length <= 4;
    const largRotulo = rotularFinais ? Math.max(...finais.map((f) => fy(f.v).length)) * 6.6 + 14 : 12;
    const m = {
      e: Math.max(...esc.ticks.map((t) => fy(t).length)) * 6.6 + 10,
      d: largRotulo,
      t: 14,
      b: 26,
    };
    const px = (i) => m.e + i * (L - m.e - m.d) / (n - 1);
    const py = (v) => m.t + (esc.max - v) / (esc.max - esc.min) * (H - m.t - m.b);

    const svg = s('svg', {
      viewBox: '0 0 ' + L + ' ' + H, width: L, height: H, class: 'grafico-svg',
      tabindex: 0, role: 'img',
      'aria-label': (op.titulo || 'Gráfico de linhas') + '. Use as setas do teclado para percorrer os valores.',
    });

    if (op.sombraDesde != null) {
      const i0 = op.x.findIndex((x) => x >= op.sombraDesde);
      if (i0 >= 0) {
        const x0 = i0 === 0 ? px(0) : (px(i0 - 1) + px(i0)) / 2;
        s('rect', { x: x0, y: m.t, width: px(n - 1) - x0, height: H - m.t - m.b, class: 'g-projecao' }, svg);
        s('text', { x: x0 + 6, y: m.t + 12, class: 'g-rotulo-projecao' }, svg).textContent = op.rotuloSombra || 'Projeção';
      }
    }

    esc.ticks.forEach((t, k) => {
      const y = py(t);
      s('line', { x1: m.e, x2: L - m.d, y1: y, y2: y, class: k === 0 ? 'g-eixo' : 'g-grade' }, svg);
      s('text', { x: m.e - 8, y: y + 4, class: 'g-tick', 'text-anchor': 'end' }, svg).textContent = fy(t);
    });

    for (const r of op.referencias || []) {
      const y = py(r.valor);
      s('line', { x1: m.e, x2: L - m.d, y1: y, y2: y, class: 'g-referencia' }, svg);
      s('text', { x: m.e + 4, y: y - 4, class: 'g-rotulo-ref' }, svg).textContent = r.rotulo;
    }

    const qtd = Math.max(2, Math.min(n, Math.floor((L - m.e - m.d) / 84)));
    const usados = new Set();
    for (let k = 0; k < qtd; k++) {
      const i = Math.round(k * (n - 1) / (qtd - 1));
      if (usados.has(i)) continue;
      usados.add(i);
      const ancora = k === 0 ? 'start' : k === qtd - 1 ? 'end' : 'middle';
      s('text', { x: px(i), y: H - 8, class: 'g-tick', 'text-anchor': ancora }, svg).textContent = fx(op.x[i]);
    }

    for (const se of op.series) {
      let d = '';
      let caneta = false;
      se.y.forEach((v, i) => {
        if (v == null || !isFinite(v)) { caneta = false; return; }
        d += (caneta ? 'L' : 'M') + px(i).toFixed(1) + ' ' + py(v).toFixed(1);
        caneta = true;
      });
      s('path', { d, class: 'g-linha' }, svg).style.stroke = se.cor;
    }

    for (const f of finais) {
      s('circle', { cx: px(f.i), cy: py(f.v), r: 4, class: 'g-ponto' }, svg).style.fill = f.se.cor;
    }
    if (rotularFinais) {
      const ordem = finais.map((f) => py(f.v)).sort((a, b) => a - b);
      const colide = ordem.some((y, j) => j > 0 && y - ordem[j - 1] < 13);
      if (!colide) {
        for (const f of finais) {
          s('text', { x: px(f.i) + 8, y: py(f.v) + 4, class: 'g-rotulo-final' }, svg).textContent = fy(f.v);
        }
      }
    }

    // Camada de interação: mira vertical + dica com todas as séries.
    const mira = s('line', { y1: m.t, y2: H - m.b, class: 'g-mira' }, svg);
    mira.style.display = 'none';
    const marcadores = op.series.map((se) => {
      const c = s('circle', { r: 4, class: 'g-ponto' }, svg);
      c.style.fill = se.cor;
      c.style.display = 'none';
      return c;
    });
    const alvo = s('rect', { x: m.e - 6, y: 0, width: L - m.e - m.d + 12, height: H, class: 'g-alvo' }, svg);
    let atual = -1;

    function mostrar(i) {
      atual = i;
      const x = px(i);
      mira.setAttribute('x1', x);
      mira.setAttribute('x2', x);
      mira.style.display = '';
      P.limpar(dica);
      dica.append(P.el('div', { class: 'dica-titulo', texto: (op.formatoXLongo || fx)(op.x[i]) }));
      op.series.forEach((se, k) => {
        const v = se.y[i];
        if (v == null || !isFinite(v)) { marcadores[k].style.display = 'none'; return; }
        marcadores[k].setAttribute('cx', x);
        marcadores[k].setAttribute('cy', py(v));
        marcadores[k].style.display = '';
        const chave = P.el('span', { class: 'chave-linha', 'aria-hidden': 'true' });
        chave.style.background = se.cor;
        dica.append(P.el('div', { class: 'dica-linha' }, chave, P.el('strong', { texto: fyLongo(v) }), P.el('span', { texto: se.nome })));
      });
      dica.hidden = false;
      const largura = dica.offsetWidth;
      let esquerda = x + 14;
      if (esquerda + largura > L) esquerda = x - 14 - largura;
      dica.style.left = Math.max(0, esquerda) + 'px';
      dica.style.top = m.t + 'px';
    }
    function esconder() {
      atual = -1;
      dica.hidden = true;
      mira.style.display = 'none';
      marcadores.forEach((c) => { c.style.display = 'none'; });
    }
    function indice(ev) {
      const r = svg.getBoundingClientRect();
      const x = (ev.clientX - r.left) * (L / r.width);
      const i = Math.round((x - m.e) / ((L - m.e - m.d) / (n - 1)));
      return Math.max(0, Math.min(n - 1, i));
    }
    alvo.addEventListener('pointermove', (ev) => mostrar(indice(ev)));
    alvo.addEventListener('pointerdown', (ev) => mostrar(indice(ev)));
    svg.addEventListener('pointerleave', esconder);
    svg.addEventListener('focus', () => mostrar(atual >= 0 ? atual : n - 1));
    svg.addEventListener('blur', esconder);
    svg.addEventListener('keydown', (ev) => {
      const base = atual < 0 ? n - 1 : atual;
      if (ev.key === 'ArrowLeft') { mostrar(Math.max(0, base - 1)); ev.preventDefault(); }
      else if (ev.key === 'ArrowRight') { mostrar(Math.min(n - 1, base + 1)); ev.preventDefault(); }
      else if (ev.key === 'Home') { mostrar(0); ev.preventDefault(); }
      else if (ev.key === 'End') { mostrar(n - 1); ev.preventDefault(); }
      else if (ev.key === 'Escape') esconder();
    });

    area.insertBefore(svg, dica);
  }

  /* Minigráfico de tendência para os cartões (decorativo; o valor está no texto). */
  G.mini = function (cont, valores) {
    P.limpar(cont);
    const v = valores.filter((x) => isFinite(x));
    if (v.length < 2) return;
    const L = 120;
    const H = 32;
    const min = Math.min(...v);
    const max = Math.max(...v);
    const dy = max - min || 1;
    const pts = v.map((y, i) => [2 + i / (v.length - 1) * (L - 8), 3 + (max - y) / dy * (H - 6)]);
    const svg = s('svg', { viewBox: '0 0 ' + L + ' ' + H, class: 'mini', 'aria-hidden': 'true', focusable: 'false' });
    s('polyline', { points: pts.map((p) => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' '), class: 'mini-linha' }, svg);
    const u = pts[pts.length - 1];
    s('circle', { cx: u[0], cy: u[1], r: 3, class: 'mini-ponto' }, svg);
    cont.append(svg);
  };

  /* Barra 100% empilhada. itens: [{nome, valor, cor, corTexto, detalhe}] */
  G.barraEmpilhada = function (cont, itens) {
    P.limpar(cont);
    const visiveis = itens.filter((i) => i.valor > 0);
    const total = visiveis.reduce((soma, i) => soma + i.valor, 0) || 1;
    const area = P.el('div', { class: 'grafico-area' });
    const barra = P.el('div', {
      class: 'barra-empilhada', role: 'img',
      'aria-label': visiveis.map((i) => i.nome + ' ' + P.fmt.pct(i.valor / total * 100, 0)).join(', '),
    });
    const dica = P.el('div', { class: 'dica' });
    dica.hidden = true;
    const rotulos = [];
    for (const i of visiveis) {
      const pct = i.valor / total * 100;
      const seg = P.el('div', { class: 'segmento', tabindex: 0, 'aria-label': i.nome + ': ' + P.fmt.pct(pct, 0) });
      seg.style.flexGrow = String(pct);
      seg.style.background = i.cor;
      seg.style.color = i.corTexto || '#ffffff';
      const rotulo = P.el('span', { texto: P.fmt.pct(pct, 0) });
      seg.append(rotulo);
      rotulos.push([seg, rotulo]);
      const mostrar = () => {
        P.limpar(dica);
        const chave = P.el('span', { class: 'chave-bloco', 'aria-hidden': 'true' });
        chave.style.background = i.cor;
        dica.append(P.el('div', { class: 'dica-linha' }, chave, P.el('strong', { texto: P.fmt.pct(pct, 0) }), P.el('span', { texto: i.nome })));
        if (i.detalhe) dica.append(P.el('div', { class: 'dica-extra', texto: i.detalhe }));
        dica.hidden = false;
        const x = seg.offsetLeft + seg.offsetWidth / 2;
        const largura = dica.offsetWidth;
        dica.style.left = Math.max(0, Math.min(area.clientWidth - largura, x - largura / 2)) + 'px';
        dica.style.top = (barra.offsetHeight + 8) + 'px';
      };
      seg.addEventListener('pointerenter', mostrar);
      seg.addEventListener('focus', mostrar);
      seg.addEventListener('pointerleave', () => { dica.hidden = true; });
      seg.addEventListener('blur', () => { dica.hidden = true; });
      barra.append(seg);
    }
    area.append(barra, dica);
    cont.append(area, legenda(visiveis, 'bloco'));
    requestAnimationFrame(() => {
      for (const [seg, rotulo] of rotulos) rotulo.hidden = rotulo.offsetWidth + 12 > seg.clientWidth;
    });
  };

  P.graficos = G;
})(window.Painel);
