"use strict";
(() => {
  const $ = (s) => document.querySelector(s);

  const TIPOS = {
    manutencao: { nome: "Manual de manutenção", cod: "MNT" },
    operacao: { nome: "Manual de operação", cod: "OPR" },
    diagrama: { nome: "Diagrama elétrico", cod: "DIA" },
    pecas: { nome: "Catálogo de peças", cod: "PEC" },
    procedimento: { nome: "Procedimento (POP)", cod: "POP" },
    outro: { nome: "Outro documento", cod: "DOC" },
  };
  const AREAS = { mecanica: "Mecânica", eletrica: "Elétrica", ambas: "Mecânica e elétrica" };
  const AREA_COD = { mecanica: "MEC", eletrica: "ELE", ambas: "M+E" };
  const ROTULO_EXT = {
    pdf: "PDF", png: "Imagem", jpg: "Imagem", jpeg: "Imagem", webp: "Imagem", gif: "Imagem",
    mp4: "Vídeo", webm: "Vídeo", txt: "Texto", doc: "Word", docx: "Word", xls: "Excel", xlsx: "Excel",
    dwg: "Desenho DWG", dxf: "Desenho DXF", zip: "ZIP",
  };
  const ABRE_NO_NAVEGADOR = new Set(["pdf", "png", "jpg", "jpeg", "webp", "gif", "mp4", "webm", "txt"]);
  const CAMPOS = ["equipamento", "fabricante", "modelo", "setor", "revisao"];

  const st = {
    manuais: [], pronto: false, erro: "", admin: false, limiteMb: 200,
    busca: "", area: "todas", tipo: "", setor: "", ordem: "recentes",
    editandoId: null, confirmarId: null, arquivo: null, enviando: false,
  };
  const reduzMovimento = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- utilidades ----------
  function el(tag, props = {}, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const c of kids.flat()) if (c != null && c !== false) n.append(c);
    return n;
  }
  const norm = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const extensao = (nome) => { const m = /\.([a-z0-9]+)$/i.exec(nome || ""); return m ? m[1].toLowerCase() : ""; };
  function formatarTamanho(b) {
    if (!b && b !== 0) return "";
    if (b < 1024 * 1024) return Math.max(1, Math.round(b / 1024)) + " KB";
    return (b / (1024 * 1024)).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " MB";
  }
  function formatarData(iso) {
    const d = new Date(iso);
    return isNaN(d) ? "" : d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
  }
  const urlArquivo = (arq) => `/arquivos/${arq.id}/${encodeURIComponent(arq.nome || "manual")}`;

  let toastTimer;
  function toast(txt) {
    const t = $("#toast");
    t.textContent = txt;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 4200);
  }

  function lerPreferencia() {
    try {
      const a = localStorage.getItem("biblioteca-area");
      if (a && ["todas", "mecanica", "eletrica"].includes(a)) st.area = a;
    } catch {}
  }
  function salvarPreferencia() {
    try { localStorage.setItem("biblioteca-area", st.area); } catch {}
  }

  // ---------- comunicação com o servidor ----------
  const SEM_CONEXAO = "Sem conexão com o computador da biblioteca. Verifique se ele está ligado e na rede.";

  async function chamar(metodo, url, corpo) {
    let r;
    try {
      r = await fetch(url, {
        method: metodo,
        headers: { "X-Biblioteca": "1", ...(corpo ? { "Content-Type": "application/json" } : {}) },
        body: corpo ? JSON.stringify(corpo) : undefined,
      });
    } catch {
      throw { status: 0, mensagem: SEM_CONEXAO };
    }
    let d = {};
    try { d = await r.json(); } catch {}
    if (!r.ok) throw { status: r.status, mensagem: d.erro };
    return d;
  }

  // Envio com XMLHttpRequest para mostrar o progresso de arquivos grandes.
  function enviarComArquivo(metodo, url, dados, arquivo, aoProgredir) {
    return new Promise((ok, falha) => {
      const x = new XMLHttpRequest();
      x.open(metodo, url);
      x.setRequestHeader("X-Biblioteca", "1");
      x.setRequestHeader("X-Dados", encodeURIComponent(JSON.stringify(dados)));
      if (arquivo) {
        x.setRequestHeader("X-Nome-Arquivo", encodeURIComponent(arquivo.name));
        x.setRequestHeader("Content-Type", "application/octet-stream");
        x.upload.onprogress = (e) => { if (e.lengthComputable) aoProgredir(e.loaded / e.total); };
      }
      x.onload = () => {
        let corpo = {};
        try { corpo = JSON.parse(x.responseText || "{}"); } catch {}
        if (x.status >= 200 && x.status < 300) ok(corpo);
        else falha({ status: x.status, mensagem: corpo.erro });
      };
      x.onerror = () => falha({ status: 0, mensagem: SEM_CONEXAO });
      x.send(arquivo || null);
    });
  }

  function mensagemErro(e) {
    if (e?.status === 401) {
      st.admin = false;
      aplicarAdmin();
      renderTudo();
      return "Sua sessão de administrador terminou. Entre de novo na área do administrador.";
    }
    return e?.mensagem || "Não foi possível concluir. Tente de novo.";
  }

  let carregando = false;
  let recarregarDepois = false;
  async function recarregar() {
    if (carregando) { recarregarDepois = true; return; }
    carregando = true;
    try {
      const r = await fetch("/api/manuais", { cache: "no-store" });
      if (!r.ok) throw new Error();
      const d = await r.json();
      st.manuais = Array.isArray(d.manuais) ? d.manuais : [];
      st.admin = !!d.admin;
      st.limiteMb = d.limiteMb || st.limiteMb;
      st.pronto = true;
      st.erro = "";
      if (st.confirmarId && !st.manuais.some((m) => m.id === st.confirmarId)) st.confirmarId = null;
      if (st.editandoId && !st.enviando && (!st.admin || !st.manuais.some((m) => m.id === st.editandoId))) {
        limparFormulario();
        if (st.admin) toast("O manual que você editava foi excluído.");
      }
    } catch {
      if (!st.pronto) st.erro = SEM_CONEXAO;
      else toast("Sem conexão com o computador da biblioteca. A lista pode estar desatualizada.");
    } finally {
      carregando = false;
    }
    aplicarAdmin();
    renderTudo();
    if (recarregarDepois) { recarregarDepois = false; recarregar(); }
  }

  function ouvirMudancas() {
    if (!window.EventSource) { setInterval(recarregar, 60000); return; }
    const es = new EventSource("/api/eventos");
    let caiu = false;
    es.addEventListener("mudou", () => recarregar());
    es.onerror = () => { caiu = true; };
    es.onopen = () => { if (caiu) { caiu = false; recarregar(); } };
  }

  // ---------- filtros e busca ----------
  function filtrados() {
    const termos = norm(st.busca).split(/\s+/).filter(Boolean);
    const l = st.manuais.filter((m) => {
      if (st.area !== "todas" && m.area !== st.area && m.area !== "ambas") return false;
      if (st.tipo && m.tipo !== st.tipo) return false;
      if (st.setor && (m.setor || "").trim() !== st.setor) return false;
      if (!termos.length) return true;
      const alvo = norm([
        m.titulo, m.equipamento, m.fabricante, m.modelo, m.setor, m.revisao,
        (m.tags || []).join(" "), m.observacoes, m.arquivo?.nome, TIPOS[m.tipo]?.nome,
      ].join(" "));
      return termos.every((t) => alvo.includes(t));
    });
    const cmp = (a, b) => norm(a).localeCompare(norm(b), "pt-BR");
    if (st.ordem === "titulo") l.sort((a, b) => cmp(a.titulo, b.titulo));
    else if (st.ordem === "equipamento") l.sort((a, b) => cmp(a.equipamento || "￿", b.equipamento || "￿") || cmp(a.titulo, b.titulo));
    else l.sort((a, b) => String(b.criadoEm || "").localeCompare(String(a.criadoEm || "")));
    return l;
  }
  const filtrando = () => !!(st.busca.trim() || st.area !== "todas" || st.tipo || st.setor);

  // ---------- renderização ----------
  function aplicarAdmin() {
    const p = $("#papel");
    p.textContent = st.admin ? "Administrador" : "Consulta";
    p.dataset.nivel = st.admin ? "admin" : "";
    $("#btn-entrar").hidden = st.admin;
    $("#btn-sair").hidden = !st.admin;
    $("#lado").hidden = !st.admin;
    $("#layout").classList.toggle("com-lado", st.admin);
    $("#limite-txt").textContent = `PDF, imagem, vídeo, Word, Excel ou DWG · até ${st.limiteMb} MB`;
  }

  function renderContagem() {
    const ms = st.manuais;
    $("#c-total").textContent = st.pronto ? ms.length : "–";
    $("#c-mec").textContent = st.pronto ? ms.filter((m) => m.area !== "eletrica").length : "–";
    $("#c-ele").textContent = st.pronto ? ms.filter((m) => m.area !== "mecanica").length : "–";
  }

  function renderSetores() {
    const setores = [...new Set(st.manuais.map((m) => (m.setor || "").trim()).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, "pt-BR"));
    if (st.setor && !setores.includes(st.setor)) st.setor = "";
    const sel = $("#filtro-setor");
    sel.replaceChildren(el("option", { value: "", text: "Todos os setores" }), ...setores.map((s) => el("option", { value: s, text: s })));
    sel.value = st.setor;
    sel.hidden = setores.length === 0;
    $("#setores-lista").replaceChildren(...setores.map((s) => el("option", { value: s })));
  }

  function vazio(titulo, texto, extra) {
    return el("div", { class: "vazio" }, el("h3", { text: titulo }), texto ? el("p", { text: texto }) : null, extra || null);
  }

  function metaItem(rotulo, valor) {
    return el("li", {}, rotulo + " ", el("b", { text: valor }));
  }

  function ficha(m) {
    const tipo = TIPOS[m.tipo] || TIPOS.outro;
    const area = AREAS[m.area] ? m.area : "ambas";
    const arq = m.arquivo || {};
    const titulo = m.titulo || arq.nome || "Sem título";
    const url = arq.id ? urlArquivo(arq) : null;
    const abre = ABRE_NO_NAVEGADOR.has(arq.ext);

    const meta = [];
    if (m.setor) meta.push(metaItem("Setor", m.setor));
    if (m.revisao) meta.push(metaItem("Revisão", m.revisao));
    if (arq.tamanho) meta.push(metaItem(ROTULO_EXT[arq.ext] || "Arquivo", formatarTamanho(arq.tamanho)));
    if (m.criadoEm) meta.push(metaItem("Adicionado em", formatarData(m.criadoEm)));
    if (m.atualizadoEm && m.criadoEm && m.atualizadoEm.slice(0, 10) !== m.criadoEm.slice(0, 10)) meta.push(metaItem("Atualizado em", formatarData(m.atualizadoEm)));

    const fabModelo = [m.fabricante, m.modelo].filter(Boolean).join(" · ");
    const tags = Array.isArray(m.tags) ? m.tags.filter(Boolean) : [];
    const rotuloSr = el("span", { class: "sr-only", text: " " + titulo });

    const acoes = el("div", { class: "ficha-acoes" },
      !url ? el("span", { class: "sem-arq", text: "Arquivo indisponível" }) : null,
      url && abre ? el("a", { class: "btn btn-prim", href: url, target: "_blank", rel: "noopener" }, "Abrir", rotuloSr) : null,
      url ? el("a", { class: abre ? "btn" : "btn btn-prim", href: url + "?baixar=1" }, "Baixar", rotuloSr.cloneNode(true)) : null,
      st.admin
        ? el("div", { class: "editar-excluir" },
            el("button", { type: "button", class: "btn-link", onclick: () => editar(m) }, "Editar"),
            el("button", { type: "button", class: "btn-link perigo", onclick: () => { st.confirmarId = m.id; renderLista(); } }, "Excluir"))
        : null,
    );

    return el("article", { class: "ficha", "data-area": area, id: "m-" + m.id },
      el("div", { class: "ficha-cod", "aria-hidden": "true" },
        el("span", { class: "cod", text: tipo.cod }),
        el("span", { class: "cod-area", text: AREA_COD[area] })),
      el("div", { class: "ficha-corpo" },
        el("p", { class: "ficha-tipo", text: tipo.nome + " · " + AREAS[area] }),
        el("h3", { class: "ficha-titulo", text: titulo }),
        m.equipamento || fabModelo
          ? el("p", { class: "ficha-equip" },
              m.equipamento ? el("span", { text: m.equipamento }) : null,
              fabModelo ? el("span", { class: "fab", text: fabModelo }) : null)
          : null,
        meta.length ? el("ul", { class: "ficha-meta" }, meta) : null,
        m.observacoes ? el("p", { class: "ficha-obs", text: m.observacoes }) : null,
        tags.length ? el("ul", { class: "tags", "aria-label": "Tags" }, tags.map((t) => el("li", { text: t }))) : null),
      acoes,
      st.confirmarId === m.id
        ? el("div", { class: "confirma" },
            el("p", { text: "Excluir este manual? O arquivo será apagado para toda a equipe." }),
            el("div", { class: "confirma-acoes" },
              el("button", { type: "button", class: "btn btn-perigo", onclick: (e) => excluir(m, e.currentTarget) }, "Excluir manual"),
              el("button", { type: "button", class: "btn", onclick: () => { st.confirmarId = null; renderLista(); } }, "Cancelar")))
        : null,
    );
  }

  function renderLista() {
    const lista = $("#lista");
    const res = $("#resultado");
    const limpar = $("#limpar");
    if (st.erro) {
      res.textContent = ""; limpar.hidden = true;
      lista.replaceChildren(vazio("Não foi possível abrir a biblioteca", st.erro));
      return;
    }
    if (!st.pronto) {
      res.textContent = ""; limpar.hidden = true;
      lista.replaceChildren(vazio("Carregando a biblioteca…", "Os manuais aparecem aqui em instantes."));
      return;
    }
    if (!st.manuais.length) {
      res.textContent = ""; limpar.hidden = true;
      lista.replaceChildren(st.admin
        ? vazio("A biblioteca ainda está vazia", "Comece pelos equipamentos que mais param. Cada manual enviado aparece na hora para toda a equipe.",
            el("ol", {},
              el("li", { text: "Envie o arquivo no painel Enviar manual." }),
              el("li", { text: "Preencha equipamento, fabricante e modelo, que é o que a equipe vai digitar na busca." }),
              el("li", { text: "Passe para a equipe o endereço que aparece na janela do servidor." })))
        : vazio("Nenhum manual publicado ainda", "Quando a coordenação da manutenção enviar os manuais, eles aparecem aqui."));
      return;
    }
    const l = filtrados();
    const total = st.manuais.length;
    const palavra = total === 1 ? "manual" : "manuais";
    res.textContent = filtrando() ? `${l.length} de ${total} ${palavra}` : `${total} ${palavra}`;
    limpar.hidden = !filtrando();
    if (!l.length) {
      const b = st.busca.trim();
      lista.replaceChildren(vazio("Nenhum manual encontrado",
        b ? `Nada corresponde a “${b}” com os filtros atuais. Tente o modelo, o fabricante ou só parte do nome do equipamento.`
          : "Nenhum manual com esses filtros. Use Limpar filtros para ver todos."));
      return;
    }
    lista.replaceChildren(...l.map(ficha));
  }

  function renderTudo() {
    renderContagem();
    renderSetores();
    renderLista();
  }

  // ---------- ações da lista ----------
  async function excluir(m, btn) {
    btn.disabled = true;
    try {
      await chamar("DELETE", "/api/manuais/" + m.id);
      st.confirmarId = null;
      if (st.editandoId === m.id) limparFormulario();
      toast("Manual excluído.");
      recarregar();
    } catch (e) {
      btn.disabled = false;
      toast(mensagemErro(e));
    }
  }

  // ---------- formulário ----------
  const form = $("#form-manual");
  const inputArq = $("#f-arquivo");

  function mostrarErro(txt) { const e = $("#form-erro"); e.textContent = txt; e.hidden = false; }
  function limparErro() { const e = $("#form-erro"); e.textContent = ""; e.hidden = true; }

  function renderArquivoEscolhido() {
    const info = $("#drop-arquivo");
    const txt = $("#drop-txt");
    const editando = st.editandoId ? st.manuais.find((m) => m.id === st.editandoId) : null;
    const forte = (a, b) => [el("b", { text: a }), b];
    if (st.arquivo) {
      info.textContent = `${st.arquivo.name} · ${formatarTamanho(st.arquivo.size)}`;
      info.hidden = false;
      txt.replaceChildren(...(editando ? forte("Novo arquivo escolhido", " · substitui o atual ao salvar") : forte("Arquivo pronto", " · clique para trocar")));
    } else if (editando?.arquivo) {
      info.textContent = `Atual: ${editando.arquivo.nome || "arquivo"} · ${formatarTamanho(editando.arquivo.tamanho)}`;
      info.hidden = false;
      txt.replaceChildren(...forte("Para uma revisão nova", ", arraste ou clique para substituir o arquivo"));
    } else {
      info.hidden = true;
      txt.replaceChildren(...forte("Arraste o arquivo aqui", " ou clique para escolher"));
    }
  }

  const tituloDoNome = (n) => n.replace(/\.[^.]+$/, "").replace(/_+/g, " ").replace(/\s+/g, " ").trim();

  function escolherArquivo(f) {
    limparErro();
    if (!f) return;
    if (!ROTULO_EXT[extensao(f.name)]) {
      mostrarErro("Esse tipo de arquivo não é aceito. Envie PDF, imagem, vídeo, Word, Excel, DWG, DXF, TXT ou ZIP.");
      inputArq.value = "";
      return;
    }
    if (f.size > st.limiteMb * 1024 * 1024) {
      mostrarErro(`O arquivo tem ${formatarTamanho(f.size)} e o limite é ${st.limiteMb} MB. Comprima o arquivo ou divida em partes.`);
      inputArq.value = "";
      return;
    }
    st.arquivo = f;
    const t = $("#f-titulo");
    if (!t.value.trim()) t.value = tituloDoNome(f.name);
    renderArquivoEscolhido();
  }

  function setEnviando(sim, txt, fracao) {
    st.enviando = sim;
    $("#btn-salvar").disabled = sim;
    $("#btn-cancelar").disabled = sim;
    $("#progresso").hidden = !sim;
    $("#progresso-txt").textContent = txt || "";
    const barra = $("#barra");
    if (fracao == null) barra.removeAttribute("value");
    else barra.value = Math.round(fracao * 100);
  }

  function limparFormulario() {
    form.reset();
    inputArq.value = "";
    st.arquivo = null;
    st.editandoId = null;
    $("#painel-titulo").textContent = "Enviar manual";
    $("#btn-salvar").textContent = "Publicar manual";
    $("#btn-cancelar").hidden = true;
    limparErro();
    renderArquivoEscolhido();
  }

  function editar(m) {
    limparFormulario();
    st.editandoId = m.id;
    st.confirmarId = null;
    $("#f-titulo").value = m.titulo || "";
    const radio = document.querySelector(`input[name="f-area"][value="${AREAS[m.area] ? m.area : "ambas"}"]`);
    if (radio) radio.checked = true;
    $("#f-tipo").value = TIPOS[m.tipo] ? m.tipo : "outro";
    for (const c of CAMPOS) $("#f-" + c).value = m[c] || "";
    $("#f-tags").value = (m.tags || []).join(", ");
    $("#f-obs").value = m.observacoes || "";
    $("#painel-titulo").textContent = "Editar manual";
    $("#btn-salvar").textContent = "Salvar alterações";
    $("#btn-cancelar").hidden = false;
    renderArquivoEscolhido();
    renderLista();
    $("#painel").open = true;
    $("#lado").scrollIntoView({ behavior: reduzMovimento ? "auto" : "smooth", block: "start" });
    $("#f-titulo").focus({ preventScroll: true });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (st.enviando || !st.admin) return;
    limparErro();
    const editando = st.editandoId ? st.manuais.find((m) => m.id === st.editandoId) : null;
    if (st.editandoId && !editando) {
      limparFormulario();
      mostrarErro("Esse manual foi excluído enquanto você editava.");
      return;
    }
    const titulo = $("#f-titulo").value.trim();
    if (!editando && !st.arquivo) { mostrarErro("Escolha o arquivo do manual."); inputArq.focus(); return; }
    if (!titulo) { mostrarErro("Dê um título ao manual."); $("#f-titulo").focus(); return; }

    const dados = {
      titulo,
      area: form.elements["f-area"].value || "mecanica",
      tipo: $("#f-tipo").value || "manutencao",
      tags: $("#f-tags").value.split(",").map((t) => t.trim()).filter(Boolean).slice(0, 20),
      observacoes: $("#f-obs").value.trim(),
    };
    for (const c of CAMPOS) dados[c] = $("#f-" + c).value.trim();

    const arquivo = st.arquivo;
    const total = arquivo ? formatarTamanho(arquivo.size) : "";
    setEnviando(true, arquivo ? `Enviando 0% de ${total}…` : "Salvando…", arquivo ? 0 : null);
    const progresso = (f) => {
      if (f >= 1) setEnviando(true, "Salvando na biblioteca…", null);
      else setEnviando(true, `Enviando ${Math.round(f * 100)}% de ${total}…`, f);
    };
    try {
      if (editando) {
        await enviarComArquivo("PUT", "/api/manuais/" + editando.id, dados, arquivo, progresso);
        toast("Manual atualizado.");
      } else {
        await enviarComArquivo("POST", "/api/manuais", dados, arquivo, progresso);
        toast("Manual publicado. A equipe já pode consultar.");
      }
      setEnviando(false);
      limparFormulario();
      recarregar();
    } catch (err) {
      setEnviando(false);
      mostrarErro(mensagemErro(err));
    }
  });

  inputArq.addEventListener("change", () => escolherArquivo(inputArq.files[0]));
  const drop = $("#drop");
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("arrastando"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("arrastando"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("arrastando");
    escolherArquivo(e.dataTransfer?.files?.[0]);
  });
  $("#btn-cancelar").addEventListener("click", () => { limparFormulario(); renderLista(); });

  // ---------- área do administrador ----------
  const dlg = $("#dlg-login");
  function abrirLogin() {
    $("#f-senha").value = "";
    $("#login-erro").hidden = true;
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
    $("#f-senha").focus();
  }
  function fecharLogin() {
    if (dlg.close) dlg.close(); else dlg.removeAttribute("open");
  }
  $("#btn-entrar").addEventListener("click", abrirLogin);
  $("#btn-login-cancelar").addEventListener("click", fecharLogin);
  $("#form-login").addEventListener("submit", async (e) => {
    e.preventDefault();
    const senha = $("#f-senha").value;
    const erroLogin = $("#login-erro");
    if (!senha) { erroLogin.textContent = "Digite a senha."; erroLogin.hidden = false; return; }
    const btn = $("#btn-login");
    btn.disabled = true;
    try {
      await chamar("POST", "/api/login", { senha });
      fecharLogin();
      toast("Você entrou como administrador.");
      await recarregar();
      if (matchMedia("(max-width: 999px)").matches) $("#painel").open = false;
    } catch (err) {
      erroLogin.textContent = err.mensagem || "Não foi possível entrar. Tente de novo.";
      erroLogin.hidden = false;
      $("#f-senha").select();
    } finally {
      btn.disabled = false;
    }
  });
  $("#btn-sair").addEventListener("click", async () => {
    try { await chamar("POST", "/api/logout"); } catch {}
    st.admin = false;
    limparFormulario();
    aplicarAdmin();
    renderTudo();
    toast("Você saiu da área do administrador.");
  });

  // ---------- controles de busca ----------
  function preencherSelectsDeTipo() {
    $("#filtro-tipo").replaceChildren(el("option", { value: "", text: "Todos os tipos" }),
      ...Object.entries(TIPOS).map(([k, t]) => el("option", { value: k, text: t.nome })));
    $("#f-tipo").replaceChildren(...Object.entries(TIPOS).map(([k, t]) => el("option", { value: k, text: t.nome })));
  }

  function ligarControles() {
    $("#busca").addEventListener("input", (e) => { st.busca = e.target.value; renderLista(); });
    document.querySelectorAll('input[name="filtro-area"]').forEach((r) => {
      r.checked = r.value === st.area;
      r.addEventListener("change", () => { st.area = r.value; salvarPreferencia(); renderLista(); });
    });
    $("#filtro-tipo").addEventListener("change", (e) => { st.tipo = e.target.value; renderLista(); });
    $("#filtro-setor").addEventListener("change", (e) => { st.setor = e.target.value; renderLista(); });
    $("#ordem").addEventListener("change", (e) => { st.ordem = e.target.value; renderLista(); });
    $("#limpar").addEventListener("click", () => {
      st.busca = ""; st.area = "todas"; st.tipo = ""; st.setor = "";
      $("#busca").value = ""; $("#fa-todas").checked = true; $("#filtro-tipo").value = ""; $("#filtro-setor").value = "";
      salvarPreferencia();
      renderLista();
      $("#busca").focus();
    });
  }

  // ---------- início ----------
  lerPreferencia();
  preencherSelectsDeTipo();
  ligarControles();
  if (matchMedia("(max-width: 999px)").matches) $("#painel").open = false;
  renderTudo();
  recarregar();
  ouvirMudancas();
})();
