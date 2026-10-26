#!/usr/bin/env node
/* Painel do Investidor no seu computador.
   Um pequeno servidor local que busca os dados (o mesmo coletor do GitHub Actions)
   e mostra o painel no navegador, em http://127.0.0.1:8765.
   As consultas às fontes saem deste programa, não do navegador, então bloqueadores
   de anúncios e restrições do navegador não atrapalham.

   Uso: node local/servidor.js   (ou dois cliques no atalho "Abrir painel") */
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const RAIZ = path.join(__dirname, '..');
const PASTA_DADOS = path.join(__dirname, 'dados');
const ARQUIVO_DADOS = path.join(PASTA_DADOS, 'painel.json');
const ARQUIVO_CHAVES = path.join(__dirname, 'chaves.txt');
const INTERVALO_MIN = 30;
const NOMES_CHAVES = ['TWELVE_DATA_KEY', 'BRAPI_TOKEN', 'AWESOME_API_KEY', 'TICKERS_B3'];
const TIPOS = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8' };
// Só a página, os estilos e os scripts podem ser servidos: nada de chaves ou outros arquivos.
const PERMITIDOS = /^(index\.html|css\/[a-z0-9_-]+\.css|js\/[a-z0-9_-]+\.js)$/;

const MODELO_CHAVES = [
  '# Chaves gratuitas do Painel do Investidor (opcionais).',
  '# Cole cada chave depois do sinal de igual (=), sem espaços. Salve o arquivo e reabra o painel.',
  '# Este arquivo fica só no seu computador.',
  '#',
  '# Bolsa americana: crie grátis em https://twelvedata.com (menu API Keys)',
  'TWELVE_DATA_KEY=',
  '# Mais ativos da B3: crie grátis em https://brapi.dev (Dashboard)',
  'BRAPI_TOKEN=',
  '# Dólar e euro comerciais: crie grátis em https://docs.awesomeapi.com.br/instrucoes-api-key',
  'AWESOME_API_KEY=',
  '# Ativos da B3 que você quer acompanhar (separados por vírgula). Deixe vazio para usar o padrão.',
  'TICKERS_B3=',
  '',
].join('\n');

const hora = () => new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

function lerChaves() {
  let texto;
  try {
    texto = fs.readFileSync(ARQUIVO_CHAVES, 'utf8');
  } catch (e) {
    if (e.code !== 'ENOENT') throw e;
    fs.writeFileSync(ARQUIVO_CHAVES, MODELO_CHAVES);
    console.log('Criei o arquivo de chaves (opcional): ' + ARQUIVO_CHAVES);
    texto = MODELO_CHAVES;
  }
  const chaves = {};
  for (const linha of texto.split(/\r?\n/)) {
    const m = linha.match(/^\s*([A-Z_]+)\s*=\s*(.*?)\s*$/);
    if (m && NOMES_CHAVES.includes(m[1]) && m[2]) chaves[m[1]] = m[2];
  }
  // Variáveis de ambiente também valem (úteis para quem usa terminal).
  for (const nome of NOMES_CHAVES) if (process.env[nome]) chaves[nome] = process.env[nome];
  return chaves;
}

function criarColetor(coletar, resumo, chaves) {
  let atual = null;
  try { atual = JSON.parse(fs.readFileSync(ARQUIVO_DADOS, 'utf8')); } catch (_) { /* primeira vez */ }
  let emAndamento = null;

  function coletarAgora() {
    if (emAndamento) return emAndamento;
    emAndamento = (async () => {
      console.log(hora() + ' Buscando dados nas fontes…');
      try {
        const novo = await coletar(atual || {}, { env: chaves });
        if (Object.values(novo.fontes).flat().some((s) => s.origem === 'rede')) {
          atual = novo;
          fs.mkdirSync(PASTA_DADOS, { recursive: true });
          fs.writeFileSync(ARQUIVO_DADOS, JSON.stringify(novo));
          console.log(resumo(novo).split('\n').map((l) => '   ' + l).join('\n'));
          console.log(hora() + ' Dados atualizados. Próxima busca em ' + INTERVALO_MIN + ' minutos.');
        } else {
          console.log(hora() + ' Nenhuma fonte respondeu. Confira sua internet; mantive os últimos dados.');
        }
      } catch (e) {
        console.log(hora() + ' Erro ao buscar os dados: ' + e.message);
      } finally {
        emAndamento = null;
      }
      return atual;
    })();
    return emAndamento;
  }

  return { coletarAgora, atual: () => atual };
}

function responder(res, status, tipo, corpo) {
  res.writeHead(status, {
    'Content-Type': tipo,
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
  });
  res.end(corpo);
}

function abrirNavegador(url) {
  const [cmd, args] = process.platform === 'win32' ? ['cmd', ['/c', 'start', '', url]]
    : process.platform === 'darwin' ? ['open', [url]] : ['xdg-open', [url]];
  try {
    const p = spawn(cmd, args, { stdio: 'ignore', detached: true });
    p.on('error', () => {});
    p.unref();
  } catch (_) { /* sem navegador: o endereço aparece na tela */ }
}

function iniciar({ porta = 8765, abrir = true, tentativas = 10 } = {}) {
  const versao = Number(process.versions.node.split('.')[0]);
  if (versao < 18) {
    console.log('Este painel precisa do Node.js 18 ou mais novo (você tem a versão ' + process.versions.node + ').');
    console.log('Baixe a versão LTS em https://nodejs.org/pt-br/download e abra o painel de novo.');
    process.exit(1);
  }
  const { coletar, resumo } = require(path.join(RAIZ, 'coletor', 'coletar.js'));
  const chaves = lerChaves();
  const usadas = NOMES_CHAVES.filter((n) => n !== 'TICKERS_B3' && chaves[n]);
  console.log('Chaves configuradas: ' + (usadas.length ? usadas.join(', ') : 'nenhuma (tudo bem: elas são opcionais)'));

  const coletor = criarColetor(coletar, resumo, chaves);
  coletor.coletarAgora();
  setInterval(() => coletor.coletarAgora(), INTERVALO_MIN * 60000);

  const servidor = http.createServer(async (req, res) => {
    if (req.method !== 'GET' && req.method !== 'HEAD') return responder(res, 405, 'text/plain; charset=utf-8', 'Método não permitido');
    let url;
    let caminho;
    try {
      url = new URL(req.url, 'http://127.0.0.1');
      caminho = decodeURIComponent(url.pathname).replace(/^\/+/, '') || 'index.html';
    } catch (_) {
      return responder(res, 400, 'text/plain; charset=utf-8', 'Endereço inválido');
    }

    if (caminho === 'dados/painel.json') {
      let dados = coletor.atual();
      const pediuAtualizar = url.searchParams.has('atualizar') && (!dados || Date.now() - dados.geradoEm > 60000);
      if (!dados || pediuAtualizar) dados = await coletor.coletarAgora();
      if (!dados) return responder(res, 503, 'application/json; charset=utf-8', JSON.stringify({ erro: 'Ainda não foi possível buscar os dados. Confira sua internet.' }));
      return responder(res, 200, 'application/json; charset=utf-8', JSON.stringify(dados));
    }

    if (!PERMITIDOS.test(caminho)) return responder(res, 404, 'text/plain; charset=utf-8', 'Não encontrado');
    fs.readFile(path.join(RAIZ, caminho), (erro, conteudo) => {
      if (erro) return responder(res, 404, 'text/plain; charset=utf-8', 'Não encontrado');
      responder(res, 200, TIPOS[path.extname(caminho)], conteudo);
    });
  });

  return new Promise((resolve) => {
    let atual = porta;
    servidor.on('error', (e) => {
      if (e.code === 'EADDRINUSE' && atual < porta + tentativas) {
        atual++;
        servidor.listen(atual, '127.0.0.1');
      } else {
        console.log('Não consegui abrir o painel: ' + e.message);
        process.exit(1);
      }
    });
    servidor.on('listening', () => {
      const endereco = 'http://127.0.0.1:' + atual + '/';
      console.log('');
      console.log('Painel do Investidor aberto em: ' + endereco);
      console.log('Deixe esta janela aberta enquanto usa o painel. Para fechar, feche esta janela (ou Ctrl+C).');
      console.log('');
      if (abrir) abrirNavegador(endereco);
      resolve({ servidor, endereco, coletor });
    });
    // Só aceita conexões do próprio computador.
    servidor.listen(atual, '127.0.0.1');
  });
}

if (require.main === module) iniciar({ abrir: !process.argv.includes('--sem-navegador') });

module.exports = { iniciar, lerChaves };
