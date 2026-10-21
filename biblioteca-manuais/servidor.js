#!/usr/bin/env node
// Biblioteca de Manuais: servidor para a rede da empresa.
// Não tem dependências; precisa só do Node.js 18 ou mais novo.
"use strict";

const http = require("http");
const fs = require("fs");
const fsp = require("fs/promises");
const path = require("path");
const crypto = require("crypto");
const os = require("os");
const { Transform } = require("stream");
const { pipeline } = require("stream/promises");

const PUBLICO = path.join(__dirname, "public");
const DADOS = process.env.PASTA_DADOS ? path.resolve(process.env.PASTA_DADOS) : path.join(__dirname, "dados");
const ARQUIVOS = path.join(DADOS, "arquivos");
const BANCO = path.join(DADOS, "manuais.json");
const CONFIG = path.join(DADOS, "config.json");

const AREAS = ["mecanica", "eletrica", "ambas"];
const TIPOS_DOC = ["manutencao", "operacao", "diagrama", "pecas", "procedimento", "outro"];

// Extensões aceitas. As marcadas com abrir: true abrem direto no navegador; as outras são baixadas.
const TIPOS_ARQUIVO = {
  pdf: { mime: "application/pdf", abrir: true },
  png: { mime: "image/png", abrir: true },
  jpg: { mime: "image/jpeg", abrir: true },
  jpeg: { mime: "image/jpeg", abrir: true },
  webp: { mime: "image/webp", abrir: true },
  gif: { mime: "image/gif", abrir: true },
  mp4: { mime: "video/mp4", abrir: true },
  webm: { mime: "video/webm", abrir: true },
  txt: { mime: "text/plain; charset=utf-8", abrir: true },
  doc: { mime: "application/msword" },
  docx: { mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },
  xls: { mime: "application/vnd.ms-excel" },
  xlsx: { mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
  dwg: { mime: "application/acad" },
  dxf: { mime: "application/dxf" },
  zip: { mime: "application/zip" },
};

const ESTATICOS = {
  "/": { arquivo: "index.html", tipo: "text/html; charset=utf-8" },
  "/index.html": { arquivo: "index.html", tipo: "text/html; charset=utf-8" },
  "/app.js": { arquivo: "app.js", tipo: "text/javascript; charset=utf-8" },
  "/estilo.css": { arquivo: "estilo.css", tipo: "text/css; charset=utf-8" },
};

const CSP = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; " +
  "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'";

let config = {};
let banco = [];
let porta = 3000;
let limiteBytes = 200 * 1024 * 1024;

const sessoes = new Map();     // token -> validade (ms)
const tentativas = new Map();  // ip -> { n, desde }
const ouvintes = new Set();    // conexões abertas em /api/eventos

// ---------- utilidades ----------
function erro(status, mensagem) {
  const e = new Error(mensagem);
  e.status = status;
  return e;
}
const novoId = () => crypto.randomBytes(16).toString("hex");
const extensao = (nome) => { const m = /\.([a-z0-9]+)$/i.exec(nome || ""); return m ? m[1].toLowerCase() : ""; };
const espera = (ms) => new Promise((r) => setTimeout(r, ms));
const texto = (v, max) => (typeof v === "string" ? v.trim().slice(0, max) : "");

function nomeSeguro(nome, ext) {
  const base = path.basename(String(nome || "").replace(/\\/g, "/")).replace(/[\u0000-\u001f\u007f"]/g, "").trim().slice(0, 200);
  return base || "manual." + ext;
}

function decodificar(v) {
  if (typeof v !== "string" || !v) return "";
  try { return decodeURIComponent(v); } catch { throw erro(400, "Cabeçalho da requisição inválido."); }
}

function enviarJson(res, status, corpo, extras = {}) {
  const dados = JSON.stringify(corpo);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(dados),
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    ...extras,
  });
  res.end(dados);
}

function lerCookies(req) {
  const out = {};
  for (const parte of String(req.headers.cookie || "").split(";")) {
    const i = parte.indexOf("=");
    if (i > 0) out[parte.slice(0, i).trim()] = parte.slice(i + 1).trim();
  }
  return out;
}

function ehAdmin(req) {
  const token = lerCookies(req).sessao;
  const validade = token && sessoes.get(token);
  if (!validade) return false;
  if (validade < Date.now()) { sessoes.delete(token); return false; }
  return true;
}

function exigirAdmin(req) {
  // O cabeçalho próprio impede que outro site dispare alterações usando o cookie do administrador.
  if (req.headers["x-biblioteca"] !== "1") throw erro(403, "Requisição recusada.");
  if (!ehAdmin(req)) throw erro(401, "Entre como administrador para alterar a biblioteca.");
}

async function lerJson(req, limite = 64 * 1024) {
  let tamanho = 0;
  const partes = [];
  for await (const parte of req) {
    tamanho += parte.length;
    if (tamanho > limite) throw erro(413, "Dados grandes demais.");
    partes.push(parte);
  }
  try { return JSON.parse(Buffer.concat(partes).toString("utf8") || "{}"); }
  catch { throw erro(400, "Dados inválidos."); }
}

function limparDados(d) {
  if (!d || typeof d !== "object") throw erro(400, "Dados do manual inválidos.");
  const titulo = texto(d.titulo, 200);
  if (!titulo) throw erro(400, "Dê um título ao manual.");
  return {
    titulo,
    area: AREAS.includes(d.area) ? d.area : "mecanica",
    tipo: TIPOS_DOC.includes(d.tipo) ? d.tipo : "outro",
    equipamento: texto(d.equipamento, 120),
    fabricante: texto(d.fabricante, 80),
    modelo: texto(d.modelo, 80),
    setor: texto(d.setor, 80),
    revisao: texto(d.revisao, 30),
    tags: Array.isArray(d.tags) ? d.tags.map((t) => texto(t, 40)).filter(Boolean).slice(0, 20) : [],
    observacoes: texto(d.observacoes, 1000),
  };
}

function dadosDoCabecalho(req) {
  const bruto = decodificar(req.headers["x-dados"]);
  if (!bruto) throw erro(400, "Faltam os dados do manual.");
  try { return limparDados(JSON.parse(bruto)); }
  catch (e) { throw e.status ? e : erro(400, "Dados do manual inválidos."); }
}

// ---------- banco de dados (um arquivo JSON) ----------
let fila = Promise.resolve();
function emFila(fn) {
  const p = fila.then(fn);
  fila = p.catch(() => {});
  return p;
}

async function trocarArquivo(origem, destino) {
  for (let i = 0; ; i++) {
    try { return await fsp.rename(origem, destino); }
    catch (e) {
      // No Windows o antivírus pode segurar o arquivo por um instante.
      if (i >= 5 || !["EPERM", "EBUSY", "EACCES"].includes(e.code)) throw e;
      await espera(100 * (i + 1));
    }
  }
}

async function salvarBanco() {
  const tmp = BANCO + ".tmp";
  await fsp.writeFile(tmp, JSON.stringify({ versao: 1, manuais: banco }, null, 2));
  try { await fsp.copyFile(BANCO, BANCO + ".bak"); } catch (e) { if (e.code !== "ENOENT") throw e; }
  await trocarArquivo(tmp, BANCO);
}

async function carregarBanco() {
  try {
    const d = JSON.parse(await fsp.readFile(BANCO, "utf8"));
    return Array.isArray(d.manuais) ? d.manuais : [];
  } catch (e) {
    if (e.code === "ENOENT") return [];
    throw new Error(`Não consegui ler ${BANCO}. Se o arquivo estiver corrompido, restaure a cópia ${BANCO}.bak.`);
  }
}

async function carregarConfig() {
  let c = {};
  try { c = JSON.parse(await fsp.readFile(CONFIG, "utf8")); }
  catch (e) { if (e.code !== "ENOENT") throw new Error(`Não consegui ler ${CONFIG}: ${e.message}`); }
  let criouSenha = false;
  if (typeof c.senhaAdmin !== "string" || c.senhaAdmin.length < 4) {
    const letras = "abcdefghjkmnpqrstuvwxyz23456789";
    c.senhaAdmin = Array.from(crypto.randomBytes(10), (b) => letras[b % letras.length]).join("");
    criouSenha = true;
  }
  if (!Number.isInteger(c.porta)) c.porta = 3000;
  if (!(Number(c.limiteMb) > 0)) c.limiteMb = 200;
  if (criouSenha) await fsp.writeFile(CONFIG, JSON.stringify(c, null, 2));
  return { config: c, criouSenha };
}

// Apaga envios interrompidos e arquivos que nenhum manual usa mais.
async function limparSobras() {
  const usados = new Set(banco.map((m) => m.arquivo && m.arquivo.id));
  for (const nome of await fsp.readdir(ARQUIVOS)) {
    if (nome.endsWith(".part") || (/^[a-f0-9]{32}$/.test(nome) && !usados.has(nome))) {
      await fsp.rm(path.join(ARQUIVOS, nome), { force: true });
    }
  }
}

// ---------- arquivos ----------
async function receberArquivo(req, nomeOriginal) {
  const ext = extensao(nomeOriginal);
  if (!TIPOS_ARQUIVO[ext]) {
    throw erro(415, "Esse tipo de arquivo não é aceito. Envie PDF, imagem, vídeo, Word, Excel, DWG, DXF, TXT ou ZIP.");
  }
  const limiteMb = Math.round(limiteBytes / (1024 * 1024));
  const declarado = Number(req.headers["content-length"] || 0);
  if (declarado > limiteBytes) throw erro(413, `O arquivo passa de ${limiteMb} MB, o limite da biblioteca.`);

  const id = novoId();
  const destino = path.join(ARQUIVOS, id);
  const temporario = destino + ".part";
  let recebidos = 0;
  const contador = new Transform({
    transform(parte, _cod, cb) {
      recebidos += parte.length;
      if (recebidos > limiteBytes) cb(erro(413, `O arquivo passa de ${limiteMb} MB, o limite da biblioteca.`));
      else cb(null, parte);
    },
  });
  try {
    await pipeline(req, contador, fs.createWriteStream(temporario));
    if (!recebidos) throw erro(400, "O arquivo está vazio.");
    await trocarArquivo(temporario, destino);
  } catch (e) {
    await fsp.rm(temporario, { force: true });
    throw e.status ? e : erro(400, "O envio foi interrompido. Tente de novo.");
  }
  return { id, nome: nomeSeguro(nomeOriginal, ext), tamanho: recebidos, ext };
}

async function servirArquivo(req, res, id, baixar) {
  const manual = banco.find((m) => m.arquivo && m.arquivo.id === id);
  if (!manual) throw erro(404, "Arquivo não encontrado. Ele pode ter sido excluído.");
  const arq = manual.arquivo;
  const info = TIPOS_ARQUIVO[arq.ext] || { mime: "application/octet-stream" };
  const caminho = path.join(ARQUIVOS, id);
  let tamanho;
  try { tamanho = (await fsp.stat(caminho)).size; }
  catch { throw erro(404, "O arquivo deste manual não está mais no computador da biblioteca."); }

  const disposicao = baixar || !info.abrir ? "attachment" : "inline";
  const nomeAscii = arq.nome.replace(/[^\x20-\x7e]/g, "_").replace(/["\\]/g, "_");
  const cabecalhos = {
    "Content-Type": info.mime,
    "Content-Disposition": `${disposicao}; filename="${nomeAscii}"; filename*=UTF-8''${encodeURIComponent(arq.nome)}`,
    "Accept-Ranges": "bytes",
    "Cache-Control": "private, max-age=3600",
    "X-Content-Type-Options": "nosniff",
  };

  // Pedidos parciais deixam avançar vídeos e abrir PDFs grandes aos poucos.
  const faixa = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || "");
  let inicio = 0;
  let fim = tamanho - 1;
  let status = 200;
  if (faixa && (faixa[1] || faixa[2])) {
    if (faixa[1]) {
      inicio = Number(faixa[1]);
      if (faixa[2]) fim = Math.min(Number(faixa[2]), tamanho - 1);
    } else {
      inicio = Math.max(0, tamanho - Number(faixa[2]));
    }
    if (inicio > fim || inicio >= tamanho) {
      res.writeHead(416, { "Content-Range": `bytes */${tamanho}` });
      return res.end();
    }
    status = 206;
    cabecalhos["Content-Range"] = `bytes ${inicio}-${fim}/${tamanho}`;
  }
  cabecalhos["Content-Length"] = fim - inicio + 1;
  res.writeHead(status, cabecalhos);
  if (req.method === "HEAD") return res.end();
  await pipeline(fs.createReadStream(caminho, { start: inicio, end: fim }), res).catch(() => {});
}

async function servirEstatico(res, item) {
  const conteudo = await fsp.readFile(path.join(PUBLICO, item.arquivo));
  const cabecalhos = {
    "Content-Type": item.tipo,
    "Content-Length": conteudo.length,
    "Cache-Control": "no-cache",
    "X-Content-Type-Options": "nosniff",
  };
  if (item.tipo.startsWith("text/html")) {
    cabecalhos["Content-Security-Policy"] = CSP;
    cabecalhos["Referrer-Policy"] = "same-origin";
  }
  res.writeHead(200, cabecalhos);
  res.end(conteudo);
}

// ---------- avisos em tempo real ----------
function abrirEventos(req, res) {
  res.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-store",
    Connection: "keep-alive",
  });
  res.write("retry: 5000\n\n");
  ouvintes.add(res);
  req.on("close", () => ouvintes.delete(res));
}

function avisarMudanca() {
  for (const res of ouvintes) res.write("event: mudou\ndata: {}\n\n");
}

// ---------- rotas ----------
async function entrar(req, res) {
  if (req.headers["x-biblioteca"] !== "1") throw erro(403, "Requisição recusada.");
  const ip = req.socket.remoteAddress || "";
  const agora = Date.now();
  const t = tentativas.get(ip);
  if (t && agora - t.desde < 10 * 60 * 1000 && t.n >= 10) {
    throw erro(429, "Muitas tentativas de senha. Aguarde 10 minutos e tente de novo.");
  }
  const { senha } = await lerJson(req);
  const hash = (v) => crypto.createHash("sha256").update(String(v)).digest();
  if (typeof senha !== "string" || !crypto.timingSafeEqual(hash(senha), hash(config.senhaAdmin))) {
    if (!t || agora - t.desde >= 10 * 60 * 1000) tentativas.set(ip, { n: 1, desde: agora });
    else t.n++;
    throw erro(401, "Senha incorreta.");
  }
  tentativas.delete(ip);
  const token = crypto.randomBytes(32).toString("hex");
  const validade = 30 * 24 * 60 * 60 * 1000;
  sessoes.set(token, agora + validade);
  enviarJson(res, 200, { admin: true }, {
    "Set-Cookie": `sessao=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=${validade / 1000}`,
  });
}

function sair(req, res) {
  const token = lerCookies(req).sessao;
  if (token) sessoes.delete(token);
  enviarJson(res, 200, { admin: false }, { "Set-Cookie": "sessao=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0" });
}

async function criarManual(req, res) {
  exigirAdmin(req);
  const dados = dadosDoCabecalho(req);
  const nome = decodificar(req.headers["x-nome-arquivo"]);
  if (!nome) throw erro(400, "Escolha o arquivo do manual.");
  const arquivo = await receberArquivo(req, nome);
  const agora = new Date().toISOString();
  const manual = { id: novoId(), ...dados, arquivo, criadoEm: agora, atualizadoEm: agora };
  try {
    await emFila(async () => {
      banco.push(manual);
      try { await salvarBanco(); }
      catch (e) { banco = banco.filter((m) => m !== manual); throw e; }
    });
  } catch (e) {
    await fsp.rm(path.join(ARQUIVOS, arquivo.id), { force: true });
    throw e;
  }
  avisarMudanca();
  enviarJson(res, 201, { manual });
}

async function atualizarManual(req, res, id) {
  exigirAdmin(req);
  const dados = dadosDoCabecalho(req);
  if (!banco.some((m) => m.id === id)) throw erro(404, "Esse manual não existe mais.");
  let novo = null;
  if (Number(req.headers["content-length"] || 0) > 0) {
    const atual = banco.find((m) => m.id === id);
    novo = await receberArquivo(req, decodificar(req.headers["x-nome-arquivo"]) || atual.arquivo.nome);
  } else {
    req.resume();
  }
  let antigo = null;
  let salvo = null;
  try {
    await emFila(async () => {
      const i = banco.findIndex((m) => m.id === id);
      if (i < 0) throw erro(404, "Esse manual foi excluído enquanto você editava.");
      const anterior = banco[i];
      salvo = { ...anterior, ...dados, atualizadoEm: new Date().toISOString() };
      if (novo) salvo.arquivo = novo;
      banco[i] = salvo;
      try { await salvarBanco(); }
      catch (e) { banco[i] = anterior; throw e; }
      if (novo) antigo = anterior.arquivo && anterior.arquivo.id;
    });
  } catch (e) {
    if (novo) await fsp.rm(path.join(ARQUIVOS, novo.id), { force: true });
    throw e;
  }
  if (antigo) await fsp.rm(path.join(ARQUIVOS, antigo), { force: true });
  avisarMudanca();
  enviarJson(res, 200, { manual: salvo });
}

async function excluirManual(req, res, id) {
  exigirAdmin(req);
  let removido = null;
  await emFila(async () => {
    const i = banco.findIndex((m) => m.id === id);
    if (i < 0) return;
    [removido] = banco.splice(i, 1);
    try { await salvarBanco(); }
    catch (e) { banco.splice(i, 0, removido); removido = null; throw e; }
  });
  if (removido && removido.arquivo) await fsp.rm(path.join(ARQUIVOS, removido.arquivo.id), { force: true });
  if (removido) avisarMudanca();
  enviarJson(res, 200, { excluido: !!removido });
}

async function rotear(req, res) {
  const { pathname } = new URL(req.url, "http://biblioteca");
  const metodo = req.method;

  if ((metodo === "GET" || metodo === "HEAD") && ESTATICOS[pathname]) return servirEstatico(res, ESTATICOS[pathname]);

  if (pathname === "/api/manuais") {
    if (metodo === "GET") {
      return enviarJson(res, 200, { manuais: banco, admin: ehAdmin(req), limiteMb: Math.round(limiteBytes / (1024 * 1024)) });
    }
    if (metodo === "POST") return criarManual(req, res);
  }
  const doManual = /^\/api\/manuais\/([a-f0-9]{32})$/.exec(pathname);
  if (doManual) {
    if (metodo === "PUT") return atualizarManual(req, res, doManual[1]);
    if (metodo === "DELETE") return excluirManual(req, res, doManual[1]);
  }
  if (pathname === "/api/eventos" && metodo === "GET") return abrirEventos(req, res);
  if (pathname === "/api/login" && metodo === "POST") return entrar(req, res);
  if (pathname === "/api/logout" && metodo === "POST") return sair(req, res);

  const doArquivo = /^\/arquivos\/([a-f0-9]{32})(?:\/[^/]*)?$/.exec(pathname);
  if (doArquivo && (metodo === "GET" || metodo === "HEAD")) {
    return servirArquivo(req, res, doArquivo[1], new URL(req.url, "http://biblioteca").searchParams.has("baixar"));
  }
  throw erro(404, "Página não encontrada.");
}

const servidor = http.createServer(async (req, res) => {
  try {
    await rotear(req, res);
  } catch (e) {
    if (!e.status) console.error(e);
    if (res.headersSent) return res.destroy();
    // Quando o arquivo é recusado antes de chegar inteiro, a conexão é fechada para não receber o resto.
    const extras = req.complete ? {} : { Connection: "close" };
    enviarJson(res, e.status || 500, { erro: e.status ? e.message : "Erro interno no servidor da biblioteca." }, extras);
  }
});
// Envios grandes pela rede podem levar vários minutos.
servidor.requestTimeout = 60 * 60 * 1000;

setInterval(() => { for (const res of ouvintes) res.write(": ping\n\n"); }, 25000).unref();

function enderecosDaRede() {
  const lista = [];
  for (const placas of Object.values(os.networkInterfaces())) {
    for (const p of placas || []) if (p.family === "IPv4" && !p.internal) lista.push(p.address);
  }
  return lista;
}

async function iniciar() {
  await fsp.mkdir(ARQUIVOS, { recursive: true });
  const carregado = await carregarConfig();
  config = carregado.config;
  porta = Number(process.env.PORTA) || config.porta;
  limiteBytes = (Number(process.env.LIMITE_MB) || Number(config.limiteMb)) * 1024 * 1024;
  banco = await carregarBanco();
  await limparSobras();

  servidor.on("error", (e) => {
    if (e.code === "EADDRINUSE") console.error(`\nA porta ${porta} já está em uso. A biblioteca já está aberta em outra janela, ou troque "porta" em ${CONFIG}.`);
    else console.error(e);
    process.exit(1);
  });
  servidor.listen(porta, "0.0.0.0", () => {
    console.log("\n  Biblioteca de Manuais funcionando.\n");
    console.log("  Neste computador:     http://localhost:" + porta);
    for (const ip of enderecosDaRede()) console.log("  Para a equipe na rede: http://" + ip + ":" + porta);
    console.log("  Pelo nome do computador: http://" + os.hostname() + ":" + porta);
    console.log(`\n  ${banco.length} manuais. Arquivos guardados em ${DADOS}`);
    if (carregado.criouSenha) {
      console.log(`\n  Senha da área do administrador: ${config.senhaAdmin}`);
      console.log(`  Ela fica salva em ${CONFIG}. Para trocar, edite "senhaAdmin" nesse arquivo e reinicie.`);
    }
    console.log("\n  Deixe esta janela aberta. Fechar a janela desliga a biblioteca.\n");
  });
}

iniciar().catch((e) => {
  console.error("\nNão foi possível iniciar a biblioteca:\n" + e.message);
  process.exit(1);
});
