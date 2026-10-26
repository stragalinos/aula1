/* Consultor: perfil de investidor, leitura do momento a partir dos dados
   reais, plano de alocação (com parte no exterior) e simulador.
   As regras são simples e explicadas na tela — nada de caixa-preta. */
(function (P) {
  'use strict';

  const C = {};
  const f = P.fmt;
  const num = P.ehNumero;

  C.PERGUNTAS = [
    {
      id: 'objetivo',
      texto: 'Qual é o seu principal objetivo com esse dinheiro?',
      opcoes: ['Proteger o que tenho, com o mínimo de risco', 'Crescer aos poucos, aceitando algum sobe e desce', 'Crescer o máximo possível no longo prazo'],
    },
    {
      id: 'prazo',
      texto: 'Quando você pode precisar desse dinheiro?',
      opcoes: ['Em menos de 1 ano', 'Entre 1 e 5 anos', 'Daqui a mais de 5 anos'],
    },
    {
      id: 'queda',
      texto: 'Se seus investimentos caíssem 20% em um mês, você…',
      opcoes: ['Venderia tudo para não perder mais', 'Esperaria recuperar, mesmo preocupado', 'Aproveitaria para comprar mais barato'],
    },
    {
      id: 'experiencia',
      texto: 'Qual é a sua experiência com investimentos?',
      opcoes: ['Nenhuma, ou só poupança', 'Já investi em renda fixa (CDB, Tesouro)', 'Já investi em ações, fundos ou no exterior'],
    },
    {
      id: 'renda',
      texto: 'Como é a sua renda?',
      opcoes: ['Instável ou variável (autônomo, comissão)', 'Razoavelmente estável', 'Estável (emprego fixo há anos, servidor, aposentadoria)'],
    },
    {
      id: 'reserva',
      texto: 'Você já tem uma reserva de emergência (6 meses de gastos)?',
      opcoes: ['Não', 'Tenho uma parte', 'Sim, completa'],
    },
  ];

  C.PERFIS = {
    conservador: {
      nome: 'Conservador',
      descricao: 'Prioriza a segurança. Aceita ganhar menos para evitar quedas grandes. A maior parte fica em renda fixa — no Brasil e em dólar.',
    },
    moderado: {
      nome: 'Moderado',
      descricao: 'Equilibra segurança e crescimento. Aceita oscilações no curto prazo para ganhar mais em alguns anos, com boa parte do patrimônio no exterior.',
    },
    arrojado: {
      nome: 'Arrojado',
      descricao: 'Busca crescimento no longo prazo e tolera quedas fortes no caminho. A maior parte vai para ações, principalmente globais.',
    },
  };

  C.avaliarPerfil = function (resp) {
    const ids = C.PERGUNTAS.map((p) => p.id);
    if (!ids.every((id) => resp[id] != null)) return null;
    const total = ids.reduce((soma, id) => soma + Number(resp[id]), 0);
    let perfil = total <= 4 ? 'conservador' : total <= 8 ? 'moderado' : 'arrojado';
    const notas = [];
    if (Number(resp.prazo) === 0 && perfil !== 'conservador') {
      perfil = 'conservador';
      notas.push('Como você pode precisar do dinheiro em menos de 1 ano, o perfil foi ajustado para conservador: dinheiro de curto prazo não deve ficar em algo que oscila.');
    }
    if (Number(resp.experiencia) === 0 && perfil === 'arrojado') {
      perfil = 'moderado';
      notas.push('Como você está começando, a sugestão é iniciar como moderado e evoluir conforme ganhar experiência com as oscilações.');
    }
    return Object.assign({ perfil, total, notas, rendaInstavel: Number(resp.renda) === 0 }, C.PERFIS[perfil]);
  };

  /* Classes de investimento. A ordem fixa define a cor de cada uma. */
  C.CLASSES = [
    {
      id: 'rfbr', nome: 'Renda fixa no Brasil', cor: 'var(--serie-1)', exterior: false,
      onde: 'Tesouro Selic, Tesouro IPCA+, CDBs, LCIs e LCAs de bancos sólidos (garantia do FGC até R$ 250 mil por banco).',
      risco: 'Baixo',
    },
    {
      id: 'rfusd', nome: 'Renda fixa em dólar', cor: 'var(--serie-2)', exterior: true,
      onde: 'ETFs de títulos do Tesouro americano de curto prazo (ex.: BIL, SGOV ou versões irlandesas) ou fundos cambiais no Brasil.',
      risco: 'Baixo em dólar; em reais, acompanha o câmbio',
    },
    {
      id: 'acoesmundo', nome: 'Ações globais', cor: 'var(--serie-3)', exterior: true,
      onde: 'ETFs amplos: mundo todo (VT, VWRA) ou EUA (VOO, CSPX). Na B3, em reais: IVVB11 (S&P 500) e BDRs de ETFs.',
      risco: 'Alto no curto prazo; diminui com o tempo',
    },
    {
      id: 'acoesbr', nome: 'Ações no Brasil', cor: 'var(--serie-4)', corTexto: 'var(--texto-sobre-amarelo)', exterior: false,
      onde: 'Um ETF do Ibovespa (BOVA11) em vez de escolher ações sozinho no começo.',
      risco: 'Alto',
    },
    {
      id: 'ouro', nome: 'Ouro', cor: 'var(--serie-5)', exterior: true,
      onde: 'ETFs de ouro: GOLD11 na B3, ou GLD, IAU e SGLN no exterior.',
      risco: 'Médio; costuma proteger em crises',
    },
    {
      id: 'cripto', nome: 'Criptomoedas', cor: 'var(--serie-6)', exterior: true,
      onde: 'Apenas Bitcoin e Ethereum, via ETFs regulados (na B3 ou no exterior). Nunca em plataformas desconhecidas.',
      risco: 'Muito alto',
    },
  ];

  /* Divisão base depois da reserva de emergência (soma 100%). */
  C.BASE = {
    conservador: { rfbr: 50, rfusd: 25, acoesmundo: 15, acoesbr: 5, ouro: 5, cripto: 0 },
    moderado: { rfbr: 30, rfusd: 15, acoesmundo: 35, acoesbr: 10, ouro: 5, cripto: 5 },
    arrojado: { rfbr: 15, rfusd: 10, acoesmundo: 50, acoesbr: 15, ouro: 5, cripto: 5 },
  };

  function focusItem(ctx, ind, ano) {
    return ctx.focus && ctx.focus.ind[ind] && ctx.focus.ind[ind][ano] ? ctx.focus.ind[ind][ano] : null;
  }
  C.focusItem = focusItem;

  /* Média de um indicador do FMI entre dois anos (inclusive). */
  function mediaFmi(dados, pais, de, ate) {
    if (!dados || !dados[pais]) return null;
    const v = [];
    for (let a = de; a <= ate; a++) if (num(dados[pais][a])) v.push(dados[pais][a]);
    return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null;
  }
  C.mediaFmi = mediaFmi;

  function ultimoAno(dados, pais, limite) {
    if (!dados || !dados[pais]) return null;
    const anos = Object.keys(dados[pais]).map(Number).filter((a) => a <= limite).sort((a, b) => b - a);
    return anos.length ? anos[0] : null;
  }

  /* O que fazer, em uma frase simples, para cada ponto da leitura do momento. */
  C.ACOES = {
    'Movimento forte no câmbio hoje': 'Hoje não é dia de decisões grandes. Siga o plano e compre dólar só em parcelas.',
    'Bolsa brasileira com oscilação forte': 'Não venda no susto. Entenda o motivo antes de mexer nos seus investimentos.',
    'A renda fixa brasileira paga muito acima da inflação': 'Deixe a reserva e uma parte do dinheiro em renda fixa no Brasil.',
    'Juro real em nível razoável': 'A renda fixa continua sendo uma boa base para a carteira.',
    'Juro real baixo': 'Vale diversificar além da renda fixa, inclusive no exterior.',
    'O mercado espera queda dos juros': 'Para dinheiro de longo prazo, considere também Tesouro IPCA+ ou prefixado.',
    'O mercado espera alta dos juros': 'Prefira renda fixa que acompanha a Selic (Tesouro Selic, CDB pós-fixado).',
    'Juros devem ficar perto do nível atual': 'Nada muda para quem está começando.',
    'Inflação pede atenção': 'Proteja-se com investimentos atrelados à inflação, como o Tesouro IPCA+.',
    'Inflação sob controle relativo': 'Nada urgente: siga o seu plano.',
    'Câmbio: como levar dinheiro para fora': 'Compre dólar aos poucos, em parcelas mensais.',
    'Contas públicas do Brasil': 'Ter uma parte do patrimônio fora do Brasil reduz esse risco.',
    'Crescimento: Brasil × mundo': 'Investir em vários países é mais seguro do que em um só.',
    'Diversificar fora faz sentido': 'Considere ter uma parte do seu dinheiro em investimentos no exterior.',
    'Bolsa americana': 'Se for investir lá, faça aportes mensais em vez de tudo de uma vez.',
    'Cripto: só uma fatia pequena': 'No máximo 5% do patrimônio, e só depois da reserva de emergência.',
  };

  /* Leitura do momento: frases geradas a partir dos dados, sempre com a fonte. */
  C.leitura = function (ctx) {
    const itens = [];
    const add = (tipo, titulo, texto, fonte) => itens.push({ tipo, titulo, texto, fonte, acao: C.ACOES[titulo] || null });
    const ano = ctx.ano;

    // Movimentos fortes de um dia vêm primeiro: são os que mais levam a decisões por impulso.
    const dol = ctx.dolar;
    if (dol && num(dol.varDia) && Math.abs(dol.varDia) >= 2) {
      add('atencao', 'Movimento forte no câmbio hoje',
        'O dólar ' + (dol.varDia > 0 ? 'subiu ' : 'caiu ') + f.pct(Math.abs(dol.varDia), 1) + ' desde o último fechamento, algo raro (num dia comum ele varia menos de 1%). '
        + 'Em dias de pânico ou euforia, evite decisões grandes: se for dolarizar, mantenha as compras em parcelas e espere a poeira baixar antes de mudar o plano.',
        dol.fonte || 'Câmbio');
    }
    const fortes = Object.values(ctx.ativos || {}).filter((a) => a.grupo === 'brasil' && num(a.varDia) && Math.abs(a.varDia) >= 5);
    if (fortes.length) {
      add('atencao', 'Bolsa brasileira com oscilação forte',
        'No último pregão: ' + fortes.map((a) => a.codigo + ' ' + f.pct(a.varDia, 1, true)).join(', ') + '. '
        + 'Variações desse tamanho num só dia costumam vir de notícias (eleição, balanço, decisão do governo). Entenda o motivo antes de agir e não venda no susto.',
        'brapi (dados da B3)');
    }

    if (num(ctx.juroReal)) {
      const base = 'Com a Selic em ' + f.pct(ctx.selic) + ' e a inflação em ' + f.pct(ctx.ipca12) + ' nos últimos 12 meses, o juro real está em ' + f.pct(ctx.juroReal) + ' ao ano';
      if (ctx.juroReal >= 6) {
        add('oportunidade', 'A renda fixa brasileira paga muito acima da inflação',
          base + ' — um dos mais altos do mundo. Mesmo querendo levar dinheiro para fora, vale manter a reserva de emergência e uma parte do patrimônio em renda fixa aqui enquanto isso durar.', 'Banco Central (SGS)');
      } else if (ctx.juroReal >= 3) {
        add('contexto', 'Juro real em nível razoável', base + '. A renda fixa ainda protege bem contra a inflação, sem ser excepcional.', 'Banco Central (SGS)');
      } else {
        add('atencao', 'Juro real baixo', base + '. A renda fixa pós-fixada rende pouco acima da inflação; diversificar em outras classes e moedas ganha importância.', 'Banco Central (SGS)');
      }
    }

    const fs = focusItem(ctx, 'Selic', ano + 1);
    if (fs && num(ctx.selic)) {
      const dif = fs.mediana - ctx.selic;
      const texto = 'Os economistas consultados pelo Banco Central projetam a Selic em ' + f.pct(fs.mediana) + ' no fim de ' + (ano + 1) + ' (hoje: ' + f.pct(ctx.selic) + ').';
      if (dif <= -0.5) {
        add('contexto', 'O mercado espera queda dos juros', texto + ' Com cortes, Tesouro Selic e CDBs passam a render menos, e títulos prefixados e IPCA+ tendem a se valorizar.', 'Boletim Focus');
      } else if (dif >= 0.5) {
        add('atencao', 'O mercado espera alta dos juros', texto + ' Juros subindo favorecem a renda fixa pós-fixada e costumam pesar sobre a bolsa brasileira.', 'Boletim Focus');
      } else {
        add('contexto', 'Juros devem ficar perto do nível atual', texto, 'Boletim Focus');
      }
    }

    const fi = focusItem(ctx, 'IPCA', ano + 1);
    if (fi) {
      const delta = num(fi.ha4sem) ? fi.mediana - fi.ha4sem : 0;
      let texto = 'A inflação esperada para ' + (ano + 1) + ' é de ' + f.pct(fi.mediana) + ' (meta: 3%, com tolerância até 4,5%)';
      if (delta >= 0.1) texto += ', e essa projeção subiu nas últimas 4 semanas (era ' + f.pct(fi.ha4sem) + ')';
      else if (delta <= -0.1) texto += ', e essa projeção caiu nas últimas 4 semanas (era ' + f.pct(fi.ha4sem) + ')';
      texto += '.';
      const preocupa = fi.mediana > 4.5 || delta >= 0.1;
      if (preocupa) texto += ' Investimentos atrelados ao IPCA (como o Tesouro IPCA+) protegem seu poder de compra.';
      add(preocupa ? 'atencao' : 'contexto', preocupa ? 'Inflação pede atenção' : 'Inflação sob controle relativo', texto, 'Boletim Focus');
    }

    if (ctx.dolar && ctx.dolar.tendencia) {
      const t = ctx.dolar.tendencia;
      let texto = 'O dólar está em ' + f.brl(ctx.dolar.valor, 4);
      if (num(ctx.dolar.var30)) texto += ' (' + f.pct(ctx.dolar.var30, 1, true) + ' em 30 dias';
      if (num(ctx.dolar.var365)) texto += ', ' + f.pct(ctx.dolar.var365, 1, true) + ' em 12 meses';
      if (num(ctx.dolar.var30)) texto += ')';
      texto += '. ';
      if (t.sinal === 'alta') texto += 'A tendência recente é de alta: para dolarizar agora, divida as compras em parcelas (por exemplo, mensais) para não comprar tudo no pico.';
      else if (t.sinal === 'baixa') texto += 'A tendência recente é de baixa, o que barateia a compra de ativos lá fora. Mesmo assim, compre em parcelas: ninguém acerta o fundo.';
      else texto += 'Sem direção clara: comprar em parcelas continua sendo a forma mais segura de dolarizar.';
      const fc = focusItem(ctx, 'Câmbio', ano + 1);
      if (fc) texto += ' O mercado projeta o dólar a ' + f.brl(fc.mediana) + ' no fim de ' + (ano + 1) + '.';
      add('contexto', 'Câmbio: como levar dinheiro para fora', texto, 'Banco Central (PTAX) e Boletim Focus');
    }

    const div = ctx.fmi && ctx.fmi.divida;
    if (div && div.BRA && num(div.BRA[ano])) {
      const fim = ultimoAno(div, 'BRA', ano + 6);
      const vFim = fim ? div.BRA[fim] : null;
      if (num(vFim) && fim > ano) {
        const subindo = vFim > div.BRA[ano] + 2;
        let texto = 'O FMI projeta a dívida bruta do governo brasileiro ' + (subindo ? 'subindo' : 'indo') + ' de ' + f.pct(div.BRA[ano], 0) + ' para ' + f.pct(vFim, 0) + ' do PIB até ' + fim + '.';
        if (div.USA && num(div.USA[ano])) texto += ' Nos EUA, ela está em ' + f.pct(div.USA[ano], 0) + ' do PIB — alta também, mas lá o governo se endivida na moeda de reserva do mundo.';
        texto += subindo
          ? ' Risco fiscal maior costuma pressionar juros e câmbio: é um argumento concreto para ter parte do patrimônio em outras moedas e países.'
          : ' Mesmo estável, o nível é alto para um país emergente; diversificar continua prudente.';
        add(subindo ? 'atencao' : 'contexto', 'Contas públicas do Brasil', texto, 'FMI (World Economic Outlook)');
      }
    }

    const cres = ctx.fmi && ctx.fmi.crescimento;
    if (cres) {
      const br = mediaFmi(cres, 'BRA', ano + 1, ano + 5);
      const mundo = mediaFmi(cres, 'WEOWORLD', ano + 1, ano + 5);
      const eua = mediaFmi(cres, 'USA', ano + 1, ano + 5);
      if (num(br) && num(mundo)) {
        let texto = 'Para os próximos 5 anos, o FMI projeta o Brasil crescendo em média ' + f.pct(br, 1) + ' ao ano, contra ' + f.pct(mundo, 1) + ' da economia mundial';
        if (num(eua)) texto += ' e ' + f.pct(eua, 1) + ' dos EUA';
        texto += '. Investir só no Brasil é apostar em uma única economia.';
        add('contexto', 'Crescimento: Brasil × mundo', texto, 'FMI (World Economic Outlook)');
      }
    }

    const part = ctx.fmi && ctx.fmi.participacao;
    if (part && part.BRA) {
      const a = ultimoAno(part, 'BRA', ano);
      if (a) {
        add('oportunidade', 'Diversificar fora faz sentido',
          'O Brasil representa cerca de ' + f.pct(part.BRA[a], 1) + ' da economia mundial (FMI, ' + a + ', em paridade de poder de compra). Quem investe só aqui concentra todo o risco em uma economia e uma moeda.',
          'FMI (World Economic Outlook)');
      }
    }

    const spy = ctx.ativos && ctx.ativos.SPY;
    if (spy && spy.tendencia) {
      const t = spy.tendencia;
      const sinal = t.sinal === 'lateral' ? 'sem tendência definida' : 'em tendência de ' + t.sinal;
      let texto = 'O S&P 500 (as 500 maiores empresas americanas) está ' + sinal + ' (' + f.pct(spy.var30, 1, true) + ' em 30 dias).';
      if (t.ifr >= 70) texto += ' Subiu rápido: ótimo momento para lembrar de entrar aos poucos.';
      else if (t.sinal === 'baixa') texto += ' Quedas são normais em ações; aportes mensais compram mais cotas quando o preço cai.';
      else texto += ' Para quem investe todo mês, o importante é a constância, não o momento.';
      add('contexto', 'Bolsa americana', texto, 'Twelve Data (NYSE)');
    }

    const btc = ctx.ativos && ctx.ativos.btc;
    if (btc && btc.tendencia && num(btc.tendencia.vol)) {
      add('atencao', 'Cripto: só uma fatia pequena',
        'O Bitcoin oscila cerca de ' + f.pct(btc.tendencia.vol, 0) + ' ao ano (tendência atual: ' + btc.tendencia.sinal + '). Se quiser ter, limite a no máximo 5% do patrimônio e só depois de montar a reserva.',
        'CoinGecko');
    }

    return itens;
  };

  function aliquotaIR(meses) {
    if (meses <= 6) return 22.5;
    if (meses <= 12) return 20;
    if (meses <= 24) return 17.5;
    return 15;
  }

  C.plano = function (perfil, ent, ctx, ajustar) {
    const pesos = Object.assign({}, C.BASE[perfil.perfil]);
    const ajustes = [];
    if (ajustar && num(ctx.juroReal) && ctx.juroReal >= 6 && pesos.acoesmundo >= 10) {
      pesos.rfbr += 5;
      pesos.acoesmundo -= 5;
      ajustes.push('+5 p.p. em renda fixa no Brasil e −5 p.p. em ações globais, porque o juro real de ' + f.pct(ctx.juroReal) + ' ao ano paga bem com pouco risco. Quando os juros caírem, volte à divisão base.');
    }
    const tDolar = ctx.dolar && ctx.dolar.tendencia;
    if (ajustar && tDolar && tDolar.sinal === 'alta' && num(tDolar.ifr) && tDolar.ifr >= 65) {
      ajustes.push('O dólar subiu rápido nas últimas semanas: mantenha a divisão, mas faça a parte em dólar em 4 a 6 parcelas mensais.');
    }

    const multiplo = perfil.rendaInstavel ? 12 : 6;
    const alvo = ent.gasto * multiplo;
    const falta = Math.max(0, alvo - ent.reserva);
    const usarHoje = Math.min(falta, ent.disponivel);
    const investirHoje = Math.max(0, ent.disponivel - usarHoje);
    const faltaDepois = falta - usarHoje;
    const mesesReserva = faltaDepois > 0 ? (ent.aporte > 0 ? Math.ceil(faltaDepois / ent.aporte) : Infinity) : 0;

    const alocacao = C.CLASSES.map((c) => Object.assign({}, c, {
      pct: pesos[c.id],
      hoje: investirHoje * pesos[c.id] / 100,
      mes: ent.aporte * pesos[c.id] / 100,
    }));
    const exteriorPct = alocacao.filter((c) => c.exterior).reduce((soma, c) => soma + c.pct, 0);
    const exteriorHoje = investirHoje * exteriorPct / 100;
    const exteriorMes = ent.aporte * exteriorPct / 100;
    const exteriorAno = exteriorHoje + exteriorMes * 12;

    const caminho = exteriorAno < 20000
      ? {
        titulo: 'Comece pela B3, em reais',
        texto: 'Com até cerca de R$ 20 mil por ano indo para o exterior (no seu caso, ' + f.brl(exteriorAno, 0) + '), comprar ETFs globais e BDRs na sua corretora brasileira costuma ser mais simples e barato: não há câmbio para fazer nem conta para abrir lá fora.',
      }
      : {
        titulo: 'Avalie uma conta em corretora no exterior',
        texto: 'Com cerca de ' + f.brl(exteriorAno, 0) + ' por ano indo para fora, uma conta em corretora internacional regulada passa a compensar: mais opções (ETFs irlandeses, títulos do Tesouro americano) e o patrimônio fica de fato fora do Brasil. Pesquise custo de câmbio e IOF antes de enviar.',
      };

    const passos = [];
    if (ent.gasto <= 0) {
      passos.push({ titulo: 'Reserva de emergência', texto: 'Informe seu gasto mensal para calcular a reserva ideal (' + multiplo + ' meses de gastos), que deve ficar em reais com resgate imediato: Tesouro Selic ou CDB de liquidez diária que pague 100% do CDI ou mais.' });
    } else if (falta > 0) {
      let texto = 'Sua reserva ideal é ' + f.brl(alvo, 0) + ' (' + multiplo + ' meses de gastos). Faltam ' + f.brl(falta, 0) + '. ';
      texto += usarHoje > 0 ? 'Use ' + f.brl(usarHoje, 0) + ' do valor disponível hoje para isso. ' : '';
      if (faltaDepois > 0) texto += mesesReserva === Infinity ? 'Defina um valor mensal para completá-la. ' : 'Com seus aportes, ela fica completa em cerca de ' + mesesReserva + ' meses; até lá, os aportes vão para a reserva. ';
      texto += 'Ela fica em reais, com resgate imediato (Tesouro Selic ou CDB de liquidez diária com 100% do CDI ou mais), porque suas contas são pagas em reais.';
      passos.push({ titulo: 'Primeiro, a reserva de emergência', texto });
    } else {
      passos.push({ titulo: 'Reserva de emergência', texto: 'Sua reserva já cobre ' + multiplo + ' meses de gastos. Mantenha-a em reais com resgate imediato e passe para os próximos passos.' });
    }
    passos.push({
      titulo: 'Divida o restante conforme seu perfil',
      texto: 'Pela divisão abaixo, ' + f.pct(exteriorPct, 0) + ' do que você investir fica exposto ao exterior (dólar, ações globais, ouro e cripto).' + (investirHoje > 0 ? ' Hoje isso representa ' + f.brl(exteriorHoje, 0) + '.' : ''),
    });
    passos.push({ titulo: caminho.titulo, texto: caminho.texto });
    passos.push({ titulo: 'Entre aos poucos', texto: 'Faça a parte em dólar em parcelas (por exemplo, ao longo de 6 meses). Assim você paga um câmbio médio e não depende de acertar o melhor dia.' });
    passos.push({ titulo: 'Revise uma vez por ano', texto: 'Uma vez por ano, confira se a divisão saiu muito do planejado e reequilibre usando os novos aportes. Refaça o questionário se sua vida mudar.' });

    return {
      alocacao, ajustes, passos, caminho, exteriorPct, exteriorHoje, exteriorMes, investirHoje,
      reserva: { alvo, falta, usarHoje, faltaDepois, mesesReserva, multiplo },
    };
  };

  /* Simulação mês a mês. Taxas em % ao ano; selicCaminho: uma taxa por ano. */
  C.simular = function ({ inicial, mensal, anos, selicCaminho, retornoUsd, cambio, custo }) {
    const meses = Math.round(anos * 12);
    const fatorCusto = 1 - custo / 100;
    let poup = inicial;
    let cdb = inicial;
    let glob = inicial * fatorCusto;
    let aportado = inicial;
    const out = { x: [0], poupanca: [inicial], cdb: [inicial], global: [glob], aportado: [inicial] };
    const rGlobal = Math.pow((1 + retornoUsd / 100) * (1 + cambio / 100), 1 / 12) - 1;
    const liquido = (bruto, aliq) => (bruto > aportado ? bruto - (bruto - aportado) * aliq / 100 : bruto);
    for (let m = 1; m <= meses; m++) {
      const selic = selicCaminho[Math.min(Math.floor((m - 1) / 12), selicCaminho.length - 1)];
      const rPoup = selic > 8.5 ? 0.005 : Math.pow(1 + 0.7 * selic / 100, 1 / 12) - 1;
      const rCdb = Math.pow(1 + (selic - 0.1) / 100, 1 / 12) - 1;
      poup = poup * (1 + rPoup) + mensal;
      cdb = cdb * (1 + rCdb) + mensal;
      glob = glob * (1 + rGlobal) + mensal * fatorCusto;
      aportado += mensal;
      if (m % 12 === 0 || m === meses) {
        out.x.push(Math.round(m / 12 * 10) / 10);
        out.poupanca.push(poup);
        out.cdb.push(liquido(cdb, aliquotaIR(m)));
        out.global.push(liquido(glob, 15));
        out.aportado.push(aportado);
      }
    }
    return out;
  };

  P.consultor = C;
})(window.Painel);
