/* Dicionário do investidor: explicações curtas, em linguagem simples, usadas
   nos botões ⓘ espalhados pelo painel e na seção "Dicionário". */
(function (P) {
  'use strict';

  P.GLOSSARIO = {
    selic: {
      termo: 'Selic',
      texto: 'É a taxa básica de juros do Brasil, decidida pelo Banco Central a cada 45 dias. Ela serve de base para quase todos os juros do país.',
      exemplo: 'Selic alta: a renda fixa rende mais e os empréstimos ficam mais caros. Selic baixa: o contrário.',
    },
    cdi: {
      termo: 'CDI',
      texto: 'É a taxa de juros que os bancos usam para emprestar dinheiro entre si. Fica quase igual à Selic e é a régua da renda fixa.',
      exemplo: 'Um CDB que paga "100% do CDI" rende o mesmo que o CDI. "110% do CDI" rende um pouco mais.',
    },
    ipca: {
      termo: 'IPCA (inflação)',
      texto: 'É o índice oficial de inflação do Brasil, medido pelo IBGE. Mostra quanto os preços subiram em média.',
      exemplo: 'IPCA de 4,5% em 12 meses: o que custava R$ 100 há um ano hoje custa cerca de R$ 104,50.',
    },
    meta: {
      termo: 'Meta de inflação',
      texto: 'É o nível de inflação que o governo quer manter. Hoje a meta é 3% ao ano, aceitando de 1,5% a 4,5%.',
      exemplo: 'Quando a inflação passa de 4,5%, o Banco Central costuma subir os juros para segurar os preços.',
    },
    juroReal: {
      termo: 'Juro real',
      texto: 'É quanto um investimento rende acima da inflação. É o ganho de verdade, o aumento do seu poder de compra.',
      exemplo: 'Se você ganha 13% ao ano e a inflação é 4%, seu ganho real é perto de 9%.',
    },
    poupanca: {
      termo: 'Poupança',
      texto: 'Aplicação simples dos bancos, sem imposto de renda. Com a Selic acima de 8,5%, rende 0,5% ao mês (6,17% ao ano) mais a TR, uma pequena correção.',
      exemplo: 'Com juros altos, a poupança costuma render bem menos que um CDB ou o Tesouro Selic.',
    },
    rendaFixa: {
      termo: 'Renda fixa',
      texto: 'Investimentos em que você empresta dinheiro (ao governo ou a um banco) e sabe a regra de quanto vai receber.',
      exemplo: 'Tesouro Selic, Tesouro IPCA+, CDB, LCI e LCA são exemplos.',
    },
    tesouroSelic: {
      termo: 'Tesouro Selic',
      texto: 'Título do governo que rende a Selic. É considerado o investimento mais seguro do país e pode ser resgatado a qualquer dia.',
      exemplo: 'É um dos lugares mais indicados para a reserva de emergência.',
    },
    tesouroIpca: {
      termo: 'Tesouro IPCA+',
      texto: 'Título do governo que paga a inflação mais uma taxa fixa. Protege seu poder de compra no longo prazo.',
      exemplo: 'IPCA + 6%: se a inflação for 4%, você ganha cerca de 10% no ano. Se resgatar antes do prazo, o valor pode oscilar.',
    },
    cdb: {
      termo: 'CDB',
      texto: 'Empréstimo que você faz a um banco em troca de juros. Tem garantia do FGC até R$ 250 mil por banco.',
      exemplo: 'Prefira os de "liquidez diária" para a reserva: dá para sacar a qualquer dia.',
    },
    lci: {
      termo: 'LCI e LCA',
      texto: 'Parecidas com o CDB, mas isentas de imposto de renda para pessoa física. Também têm garantia do FGC.',
      exemplo: 'Uma LCI de 90% do CDI rende parecido com um CDB de 106% a 116% do CDI (depende do prazo), porque o CDB paga imposto.',
    },
    fgc: {
      termo: 'FGC',
      texto: 'Fundo Garantidor de Créditos: devolve seu dinheiro (até R$ 250 mil por CPF e por banco) se um banco quebrar.',
      exemplo: 'Cobre CDB, LCI, LCA e poupança. Não cobre ações, fundos nem Tesouro (o Tesouro é garantido pelo governo).',
    },
    liquidez: {
      termo: 'Liquidez',
      texto: 'É a facilidade de transformar um investimento em dinheiro na conta, rápido e sem perda.',
      exemplo: 'Tesouro Selic tem liquidez diária. Um imóvel tem liquidez baixa: pode levar meses para vender.',
    },
    reserva: {
      termo: 'Reserva de emergência',
      texto: 'Dinheiro guardado para imprevistos (perder o emprego, uma doença, um conserto). O ideal são 6 meses dos seus gastos, ou 12 se a renda varia.',
      exemplo: 'Fica em algo seguro e fácil de sacar, em reais: Tesouro Selic ou CDB de liquidez diária.',
    },
    acao: {
      termo: 'Ação',
      texto: 'É um pedacinho de uma empresa. Se a empresa vai bem, a ação tende a valer mais e pode pagar parte do lucro (dividendos).',
      exemplo: 'PETR4 é uma ação da Petrobras. O preço sobe e desce todos os dias.',
    },
    etf: {
      termo: 'ETF (fundo de índice)',
      texto: 'Um fundo negociado na bolsa que compra de uma vez todas as empresas de um índice. É a forma mais simples de diversificar.',
      exemplo: 'BOVA11 compra as maiores empresas do Brasil; IVVB11 compra as 500 maiores dos EUA, e você paga em reais.',
    },
    bdr: {
      termo: 'BDR',
      texto: 'Recibo vendido na bolsa brasileira que representa uma ação ou um ETF de fora. Você compra em reais, sem abrir conta no exterior.',
      exemplo: 'Dá para ter Apple ou um ETF americano pela sua corretora brasileira.',
    },
    indice: {
      termo: 'Índice de bolsa',
      texto: 'Uma "cesta" que mostra o desempenho médio de um grupo de ações.',
      exemplo: 'Ibovespa (maiores empresas do Brasil), S&P 500 (500 maiores dos EUA), Nasdaq-100 (tecnologia dos EUA).',
    },
    dolarizar: {
      termo: 'Dolarizar',
      texto: 'Colocar parte do seu dinheiro em investimentos que acompanham o dólar.',
      exemplo: 'Se o real perder valor, a parte em dólar compensa. Se o real se valorizar, ela rende menos em reais.',
    },
    ptax: {
      termo: 'PTAX',
      texto: 'É a cotação oficial do dólar calculada pelo Banco Central uma vez por dia, com base nos negócios do mercado.',
      exemplo: 'Serve de referência para contratos e para o imposto de renda. Pode diferir um pouco do dólar da casa de câmbio.',
    },
    focus: {
      termo: 'Boletim Focus',
      texto: 'Pesquisa semanal do Banco Central com cerca de 100 bancos e consultorias sobre o que eles esperam para inflação, juros, dólar e economia.',
      exemplo: 'Não é garantia: é a melhor estimativa média dos especialistas naquele momento.',
    },
    pib: {
      termo: 'PIB',
      texto: 'Tudo o que um país produz em um ano. O crescimento do PIB mostra se a economia está andando.',
      exemplo: 'PIB crescendo 2% ao ano: a economia produz 2% a mais que no ano anterior.',
    },
    dividaPublica: {
      termo: 'Dívida pública',
      texto: 'Quanto o governo deve, comparado a tudo que o país produz em um ano (PIB).',
      exemplo: 'Dívida subindo sem controle costuma pressionar juros e dólar para cima.',
    },
    ppp: {
      termo: 'Paridade de poder de compra (PPC)',
      texto: 'Forma de comparar países ajustando pelo custo de vida de cada um, para comparar o que realmente se produz.',
      exemplo: 'O FMI usa essa medida para calcular quanto cada país representa na economia mundial.',
    },
    tendencia: {
      termo: 'Tendência',
      texto: 'A direção que o preço vem seguindo nas últimas semanas: subindo, caindo ou sem direção clara.',
      exemplo: 'Tendência descreve o passado recente. Não é garantia de que vai continuar.',
    },
    volatilidade: {
      termo: 'Volatilidade (risco)',
      texto: 'Quanto o preço costuma balançar para cima e para baixo em um ano. Quanto maior, maior o risco.',
      exemplo: 'Volatilidade de 15%: é normal o preço subir ou cair uns 15% em um ano. Bitcoin costuma passar de 40%.',
    },
    mediaMovel: {
      termo: 'Média móvel',
      texto: 'É a média do preço dos últimos dias (20 ou 50, por exemplo), recalculada todo dia. Suaviza o sobe e desce para mostrar a direção.',
      exemplo: 'Preço acima da média costuma indicar alta; abaixo, baixa.',
    },
    ifr: {
      termo: 'IFR (Índice de Força Relativa)',
      texto: 'Um "termômetro" de 0 a 100 que mostra se o preço subiu ou caiu rápido demais nos últimos dias.',
      exemplo: 'Acima de 70: subiu rápido e pode devolver parte. Abaixo de 30: caiu rápido e pode repicar.',
    },
    precoMedio: {
      termo: 'Comprar em parcelas (preço médio)',
      texto: 'Investir aos poucos, por exemplo todo mês, em vez de tudo de uma vez. Assim você não depende de acertar o melhor dia.',
      exemplo: 'Se o dólar estiver caro num mês e barato no outro, você paga um valor no meio.',
    },
    diversificacao: {
      termo: 'Diversificação',
      texto: 'Dividir o dinheiro em tipos de investimento, empresas e países diferentes, para não depender de um só.',
      exemplo: '"Não colocar todos os ovos na mesma cesta."',
    },
    perfil: {
      termo: 'Perfil de investidor',
      texto: 'Mostra quanto risco você aceita: conservador (prioriza segurança), moderado (equilíbrio) ou arrojado (busca crescimento e aceita quedas).',
      exemplo: 'As corretoras são obrigadas a perguntar seu perfil antes de oferecer produtos (é a chamada "suitability").',
    },
    aporte: {
      termo: 'Aporte',
      texto: 'Cada valor novo que você coloca nos investimentos.',
      exemplo: 'Investir R$ 500 todo mês é fazer um aporte mensal de R$ 500.',
    },
    ir: {
      termo: 'Imposto de renda nos investimentos',
      texto: 'Na renda fixa, o imposto cai com o tempo: de 22,5% (até 6 meses) até 15% (acima de 2 anos), cobrado só sobre o lucro.',
      exemplo: 'Poupança, LCI e LCA são isentas para pessoa física. No exterior, o lucro paga 15% ao ano.',
    },
    ucits: {
      termo: 'ETF irlandês (UCITS)',
      texto: 'ETF registrado na Irlanda e vendido em bolsas da Europa. Para brasileiros, evita o imposto americano sobre herança.',
      exemplo: 'Exemplos: VWRA (mundo todo) e CSPX (S&P 500).',
    },
    cripto: {
      termo: 'Criptomoedas',
      texto: 'Moedas digitais, como Bitcoin e Ethereum, sem governo ou banco por trás. Podem subir muito, mas também cair mais de 50%.',
      exemplo: 'Se quiser ter, no máximo uma fatia pequena (até 5%) e só depois da reserva de emergência.',
    },
    ouro: {
      termo: 'Ouro',
      texto: 'Metal precioso usado há séculos como reserva de valor. Costuma se valorizar em crises.',
      exemplo: 'Não paga juros nem dividendos; serve como proteção, não como motor de crescimento.',
    },
  };

  /* Botão ⓘ que abre a explicação de um termo. */
  P.termo = function (chave, rotulo) {
    const g = P.GLOSSARIO[chave];
    if (!g) return null;
    return P.el('button', {
      type: 'button', class: 'termo', 'data-termo': chave,
      'aria-label': 'O que é ' + (rotulo || g.termo) + '?', title: 'O que é ' + (rotulo || g.termo) + '?',
      texto: 'i',
    });
  };

  /* Balão de explicação (um só, reaproveitado). */
  let balao = null;
  let origem = null;

  function fechar() {
    if (!balao) return;
    balao.hidden = true;
    if (origem) origem.setAttribute('aria-expanded', 'false');
    origem = null;
  }

  function abrir(botao) {
    const g = P.GLOSSARIO[botao.dataset.termo];
    if (!g) return;
    if (origem === botao) { fechar(); return; }
    fechar();
    if (!balao) {
      balao = P.el('div', { class: 'balao', role: 'dialog', 'aria-modal': 'false' });
      document.body.append(balao);
    }
    P.limpar(balao);
    balao.setAttribute('aria-label', g.termo);
    balao.append(
      P.el('strong', { texto: g.termo }),
      P.el('p', { texto: g.texto }),
      g.exemplo ? P.el('p', { class: 'balao-exemplo', texto: g.exemplo }) : null,
      P.el('a', { href: '#glossario', texto: 'Ver todos os termos', onclick: fechar }));
    balao.hidden = false;
    const r = botao.getBoundingClientRect();
    const largura = Math.min(320, window.innerWidth - 32);
    balao.style.width = largura + 'px';
    const esquerda = Math.max(16, Math.min(window.innerWidth - largura - 16, r.left + r.width / 2 - largura / 2));
    balao.style.left = (esquerda + window.scrollX) + 'px';
    balao.style.top = (r.bottom + 8 + window.scrollY) + 'px';
    origem = botao;
    botao.setAttribute('aria-expanded', 'true');
  }

  document.addEventListener('click', (ev) => {
    const botao = ev.target.closest && ev.target.closest('.termo');
    if (botao) { ev.preventDefault(); ev.stopPropagation(); abrir(botao); return; }
    if (balao && !balao.hidden && !balao.contains(ev.target)) fechar();
  });
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && origem) { const b = origem; fechar(); b.focus(); }
  });
  window.addEventListener('resize', fechar);

  /* Seção "Dicionário": lista com busca. */
  P.montarGlossario = function (cont, busca) {
    const desenhar = () => {
      const q = (busca.value || '').trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
      P.limpar(cont);
      const itens = Object.entries(P.GLOSSARIO)
        .filter(([, g]) => !q || (g.termo + ' ' + g.texto).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').includes(q))
        .sort((a, b) => a[1].termo.localeCompare(b[1].termo, 'pt-BR'));
      for (const [chave, g] of itens) {
        cont.append(P.el('div', { class: 'verbete', id: 'termo-' + chave },
          P.el('strong', { texto: g.termo }),
          P.el('p', { texto: g.texto }),
          g.exemplo ? P.el('p', { class: 'balao-exemplo', texto: g.exemplo }) : null));
      }
      if (!itens.length) cont.append(P.el('p', { class: 'vazio', texto: 'Nenhum termo encontrado.' }));
    };
    busca.addEventListener('input', desenhar);
    desenhar();
  };
})(window.Painel);
