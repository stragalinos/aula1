# Painel do Investidor

Painel do mercado financeiro para quem está começando a investir, com foco em
**diversificar para fora do Brasil**. Ele busca dados em fontes oficiais do Brasil
e do exterior, mostra tendências e funciona como um consultor: descobre seu perfil,
monta um plano com reserva de emergência, sugere a divisão Brasil/exterior
e simula quanto seu dinheiro pode render.

> Painel educativo. Não é recomendação individual de investimento e não substitui
> um consultor registrado na CVM. Tendências descrevem o passado recente e não
> garantem resultados futuros.

## Como abrir

- **Pela internet:** <https://stragalinos.github.io/aula1/> (abre o painel direto).
- **No computador:** dê dois cliques em `index.html` (não precisa instalar nada).

### Publicar no GitHub Pages (uma vez só)

1. No GitHub, abra o repositório e vá em **Settings → Pages**.
2. Em *Build and deployment*, escolha **Source: Deploy from a branch**.
3. Em *Branch*, escolha **master** e a pasta **/ (root)**. Clique em **Save**.
4. Em 1 a 2 minutos o endereço aparece no topo da página. Cada novo commit na
   `master` atualiza o site sozinho.

## Como usar

1. **Visão geral:** comece pela leitura do consultor. Cada ponto diz o que está
   acontecendo agora e de onde veio o dado.
2. **Consultor:** responda as 6 perguntas e preencha seus números (valor disponível,
   aporte mensal, gasto mensal e reserva). O plano aparece logo abaixo, com quanto
   colocar em cada classe hoje e por mês.
3. **Simulador:** ajuste prazo e hipóteses para comparar poupança, CDB e uma carteira global.
4. **Mercados:** clique em um ativo para ver o gráfico com médias móveis e a explicação da tendência.
5. **Fontes:** confira se todas as fontes estão com ✓. Se quiser a bolsa americana e mais
   ativos da B3, cole as chaves gratuitas ali (veja abaixo).

Suas respostas, números e chaves ficam salvos só no seu navegador; ninguém mais vê.

## O que tem no painel

| Seção | O que mostra |
|---|---|
| Visão geral | Selic, IPCA, juro real, CDI/poupança, dólar e euro (com conferência entre 3 fontes) e a **leitura do consultor** sobre o momento |
| Brasil | Boletim Focus (projeções do mercado para IPCA, Selic, PIB e dólar), gráficos de Selic e inflação |
| Mundo | Brasil × EUA × mundo segundo o FMI: crescimento, inflação, dívida pública (com projeções) e o peso do Brasil na economia mundial |
| Mercados | Dólar, euro, ouro, Bitcoin, Ethereum, ações e ETFs da B3 e ETFs dos EUA, cada um com tendência (alta, baixa ou lateral), IFR e volatilidade |
| Consultor | Questionário de perfil, plano passo a passo, divisão sugerida (com fatia no exterior) e simulador Brasil × exterior |
| Investir no exterior | Os dois caminhos (B3 ou conta lá fora), impostos (Lei 14.754/2023, estate tax) e cuidados de segurança |
| Fontes | Situação de cada fonte em tempo real e configuração das chaves opcionais |

## Fontes de dados

| Fonte | Tipo | Uso |
|---|---|---|
| [Banco Central do Brasil (SGS)](https://www3.bcb.gov.br/sgspub/) | Oficial | Selic, CDI, IPCA, dólar e euro PTAX |
| [Boletim Focus](https://www.bcb.gov.br/publicacoes/focus) | Oficial | Projeções de cerca de 100 instituições |
| [FMI · World Economic Outlook](https://www.imf.org/external/datamapper/) | Oficial internacional | Crescimento, inflação, dívida e participação no PIB mundial, com projeções |
| [Banco Mundial](https://data.worldbank.org/) | Oficial internacional | Reserva caso o FMI não responda |
| [Banco Central Europeu](https://www.ecb.europa.eu/) (via Frankfurter) | Oficial internacional | Confere o câmbio do Banco Central |
| [AwesomeAPI](https://docs.awesomeapi.com.br/) | Mercado | Dólar e euro comerciais ao longo do dia |
| [CoinGecko](https://www.coingecko.com/) | Mercado | Bitcoin, Ethereum e ouro (PAXG) |
| [brapi](https://brapi.dev/) | Mercado (B3) | Ações e ETFs brasileiros |
| [Twelve Data](https://twelvedata.com/) | Mercado (EUA) | S&P 500, Nasdaq, ações do mundo, Tesouro americano e ouro |

### Chaves gratuitas (opcional)

Sem chaves, o painel já mostra Brasil, mundo, câmbio, ouro, cripto e 4 ações da B3
(PETR4, VALE3, ITUB4, MGLU3). Para liberar mais:

1. **Bolsa americana:** crie uma conta grátis em [twelvedata.com](https://twelvedata.com/), copie a
   chave em *API Keys* e cole na seção **Fontes** do painel.
2. **Mais ativos da B3 (BOVA11, IVVB11, GOLD11…):** crie uma conta grátis em
   [brapi.dev](https://brapi.dev/), copie o token e cole na seção **Fontes**.

As chaves ficam salvas só no seu navegador (`localStorage`) e são enviadas apenas
ao próprio provedor. Nunca coloque chaves no código nem as publique no GitHub.

## Como o painel cuida da qualidade dos dados

- **Fontes oficiais primeiro** (Banco Central, FMI, BCE); provedores de mercado completam o resto.
- **Conferência cruzada:** o dólar e o euro são comparados entre Banco Central, BCE e cotação comercial; se divergirem mais de 1,5%, o painel avisa.
- **Verificação de faixa:** cada número passa por um teste de valor plausível antes de aparecer.
- **Transparência:** cada cartão mostra a fonte e a data do dado. Se uma fonte cair, o painel usa o último dado válido e avisa.
- **Segurança da página:** política de segurança (CSP) que só permite conexões com as fontes listadas, sem scripts de terceiros e sem rastreadores.

## Como o consultor decide

- **Perfil:** 6 perguntas (objetivo, prazo, reação a quedas, experiência, renda, reserva) geram conservador, moderado ou arrojado. Quem precisa do dinheiro em menos de 1 ano é tratado como conservador; quem nunca investiu começa no máximo como moderado.
- **Plano:** primeiro a reserva de emergência em reais (6 meses de gastos, ou 12 com renda instável); depois a divisão do perfil:

  | Classe | Conservador | Moderado | Arrojado |
  |---|---|---|---|
  | Renda fixa no Brasil | 50% | 30% | 15% |
  | Renda fixa em dólar | 25% | 15% | 10% |
  | Ações globais | 15% | 35% | 50% |
  | Ações no Brasil | 5% | 10% | 15% |
  | Ouro | 5% | 5% | 5% |
  | Criptomoedas | 0% | 5% | 5% |

- **Ajuste ao momento (opcional):** com juro real acima de 6% ao ano, move 5 p.p. de ações globais para renda fixa no Brasil; com o dólar subindo rápido, recomenda dolarizar em parcelas.
- **Tendência dos ativos:** médias móveis de 20 e 50 dias, inclinação dos últimos 30 dias, IFR de 14 dias e volatilidade anualizada.

## Arquivos

```
PainelInvestimentos/
├── index.html        página e guia de investimento no exterior
├── css/estilo.css    visual (tema claro e escuro, celular)
└── js/
    ├── util.js       formatação, busca com cache e verificações
    ├── fontes.js     acesso a cada fonte de dados
    ├── analise.js    cálculo de tendência
    ├── graficos.js   gráficos em SVG (sem bibliotecas externas)
    ├── consultor.js  perfil, leitura do momento, plano e simulador
    └── app.js        junta tudo na tela
```
