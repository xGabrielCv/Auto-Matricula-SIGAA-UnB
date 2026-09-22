/* SIGAA Sniper — Interface Web local.
 *
 * Regras deste arquivo:
 *  - Todo texto vindo do servidor/logs é inserido com textContent (nunca
 *    innerHTML): mensagens de erro do SIGAA podem conter HTML.
 *  - Nenhuma confirmação é decidida aqui: o servidor responde 409
 *    (precisa_confirmar) e a página só pergunta e reenvia com confirmado=true.
 */
"use strict";

(() => {
  // ── Utilidades de DOM ────────────────────────────────────────────────
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const $$ = (sel, raiz = document) => Array.from(raiz.querySelectorAll(sel));

  function h(tag, attrs, ...filhos) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else if (k === "dataset") Object.assign(el.dataset, v);
      else if (v === true) el.setAttribute(k, "");
      else el.setAttribute(k, v);
    }
    for (const f of filhos.flat()) {
      if (f === null || f === undefined || f === false) continue;
      el.append(f instanceof Node ? f : document.createTextNode(String(f)));
    }
    return el;
  }

  function limpar(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }

  // Campos que o usuário já editou não são sobrescritos por um carregamento
  // assíncrono que chegue depois (evita apagar o que acabou de ser digitado).
  document.addEventListener("input", (ev) => { if (ev.target.form) ev.target.dataset.editado = "1"; });
  document.addEventListener("change", (ev) => { if (ev.target.form) ev.target.dataset.editado = "1"; });
  function definir(campo, valor, forcar = false) {
    if (!campo || (!forcar && campo.dataset.editado)) return;
    if (campo.type === "checkbox") campo.checked = !!valor; else campo.value = valor === null || valor === undefined ? "" : valor;
  }
  function formularioSalvo(form) { $$("[data-editado]", form).forEach((c) => delete c.dataset.editado); }

  const estadoApp = {
    estado: null,
    telaAtual: null,
    encerrado: false,
    timers: [],
    ajuda: {},
    carregado: {},
  };

  // ── Toasts e diálogos ────────────────────────────────────────────────
  function toast(mensagem, tipo = "info", ms = 5000) {
    const icone = { sucesso: "✅", aviso: "⚠️", erro: "❌", info: "ℹ️" }[tipo] || "ℹ️";
    const el = h("div", { class: `toast toast-${tipo}`, role: tipo === "erro" ? "alert" : "status" },
      h("span", { "aria-hidden": "true" }, icone), h("span", {}, mensagem),
      h("button", { type: "button", "aria-label": "Fechar aviso", onclick: () => el.remove() }, "×"));
    const pilha = $("#toasts");
    pilha.append(el);
    while (pilha.children.length > 4) pilha.firstElementChild.remove();
    if (ms) setTimeout(() => el.remove(), ms);
  }

  function dialogo({ titulo, texto, nos, lista, botoes }) {
    const dlg = $("#dialogo");
    $("#dialogo-titulo").textContent = titulo || "Aviso";
    const conteudo = limpar($("#dialogo-conteudo"));
    if (texto) conteudo.append(texto);
    if (lista && lista.length) conteudo.append(h("ul", {}, lista.map((i) => h("li", {}, i))));
    if (nos) conteudo.append(nos);
    const barra = limpar($("#dialogo-botoes"));
    const defs = botoes || [{ rotulo: "OK", valor: true, classe: "botao-primario" }];
    return new Promise((resolver) => {
      defs.forEach((b, i) => {
        barra.append(h("button", {
          type: "button", class: `botao ${b.classe || "botao-secundario"}`,
          onclick: () => { dlg.close(); resolver(b.valor); },
          autofocus: i === defs.length - 1 && !b.perigoso,
        }, b.rotulo));
      });
      dlg.oncancel = (ev) => { ev.preventDefault(); dlg.close(); resolver(null); };
      dlg.showModal();
    });
  }

  const confirmar = (titulo, texto, rotuloSim = "Sim", perigoso = false) => dialogo({
    titulo, texto,
    botoes: [
      { rotulo: "Cancelar", valor: false, classe: "botao-secundario" },
      { rotulo: rotuloSim, valor: true, classe: perigoso ? "botao-perigo" : "botao-primario", perigoso },
    ],
  }).then((v) => v === true);

  function informar(titulo, texto) { return dialogo({ titulo, nos: h("pre", { class: "bloco-codigo" }, texto) }); }

  // ── API ──────────────────────────────────────────────────────────────
  class ErroHttp extends Error {
    constructor(status, dados) { super((dados && dados.erro) || `Erro HTTP ${status}`); this.status = status; this.dados = dados || {}; }
  }

  async function api(metodo, caminho, corpo) {
    let resp;
    try {
      resp = await fetch(caminho, {
        method: metodo, cache: "no-store", credentials: "same-origin",
        headers: { "X-Requested-With": "SIGAA-Sniper", ...(corpo !== undefined ? { "Content-Type": "application/json" } : {}) },
        body: corpo !== undefined ? JSON.stringify(corpo) : undefined,
      });
    } catch (e) {
      servidorIndisponivel();
      throw new ErroHttp(0, { erro: "Sem conexão com o SIGAA Sniper (o programa foi fechado?)." });
    }
    let dados = {};
    try { dados = await resp.json(); } catch (e) { /* resposta sem JSON */ }
    if (resp.status === 401) { acessoNegado(); throw new ErroHttp(401, dados); }
    if (resp.status === 403 && dados.aviso_pendente) { exigirAviso(); throw new ErroHttp(403, dados); }
    if (!resp.ok) throw new ErroHttp(resp.status, dados);
    return dados;
  }

  function mostrarErro(e) {
    if (!(e instanceof ErroHttp)) { console.error(e); toast(String(e.message || e), "erro"); return; }
    if (e.status === 0 || e.status === 401 || (e.status === 403 && e.dados.aviso_pendente)) return;
    const d = e.dados;
    if (d.problemas && d.problemas.length) {
      dialogo({ titulo: "Verifique antes de continuar", texto: d.erro, lista: d.problemas });
    } else if (d.guia_manual) {
      dialogo({ titulo: "Não foi possível concluir", texto: d.erro, nos: h("pre", { class: "bloco-codigo" }, d.guia_manual) });
    } else {
      toast(d.erro || e.message, e.status >= 500 ? "erro" : "aviso", 7000);
    }
  }

  /** Executa uma ação; trata confirmação (409) e erros de forma padronizada. */
  async function acao(metodo, caminho, corpo = {}, { botao, rotuloSim } = {}) {
    if (botao) { botao.setAttribute("aria-busy", "true"); botao.disabled = true; }
    try {
      return await api(metodo, caminho, corpo);
    } catch (e) {
      if (e instanceof ErroHttp && e.status === 409 && e.dados.precisa_confirmar) {
        const perigoso = /REAL|TUDO|Remover|URLs/i.test(`${e.dados.titulo} ${e.dados.erro}`);
        const ok = await confirmar(e.dados.titulo || "Confirmar", e.dados.erro, rotuloSim || "Sim, continuar", perigoso);
        if (!ok) return null;
        if (botao) { botao.removeAttribute("aria-busy"); botao.disabled = false; }
        return acao(metodo, caminho, { ...corpo, confirmado: true }, { botao });
      }
      mostrarErro(e);
      return null;
    } finally {
      if (botao) { botao.removeAttribute("aria-busy"); botao.disabled = false; }
    }
  }

  async function baixar(caminho, nomeArquivo) {
    try {
      const resp = await fetch(caminho, { headers: { "X-Requested-With": "SIGAA-Sniper" }, credentials: "same-origin", cache: "no-store" });
      if (!resp.ok) {
        let d = {}; try { d = await resp.json(); } catch (e) { /* */ }
        throw new ErroHttp(resp.status, d);
      }
      salvarBlob(await resp.blob(), nomeArquivo);
    } catch (e) { mostrarErro(e); }
  }

  function salvarBlob(blob, nomeArquivo) {
    const url = URL.createObjectURL(blob);
    const a = h("a", { href: url, download: nomeArquivo });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  // ── Telas de bloqueio (sem acesso / encerrado) ───────────────────────
  function bloquear(titulo, ...paragrafos) {
    estadoApp.encerrado = true;
    estadoApp.timers.forEach(clearInterval);
    $$("dialog[open]").forEach((d) => d.close());
    $("#app").hidden = true;
    const c = limpar($("#tela-bloqueio-conteudo"));
    c.append(h("h1", {}, titulo), ...paragrafos.map((p) => h("p", {}, p)));
    $("#tela-bloqueio").hidden = false;
  }
  function servidorIndisponivel() {
    if (estadoApp.encerrado) return;
    bloquear("🔌 Interface Web encerrada",
      "Não há mais conexão com o SIGAA Sniper — a Interface Web foi encerrada no terminal ou o programa foi fechado.",
      "Para usar de novo, abra o programa e escolha a opção [0] 🌐 Interface Web no menu.");
  }
  function acessoNegado() {
    bloquear("🔒 Acesso não autorizado",
      "Esta página não tem a chave de acesso desta execução (ela muda sempre que a Interface Web é aberta).",
      "Volte ao terminal do SIGAA Sniper e abra o link completo exibido lá.");
  }

  // ── Aviso legal (obrigatório em toda execução) ───────────────────────
  let avisoCarregando = false;
  async function exigirAviso() {
    if (avisoCarregando || $("#dialogo-aviso").open) return;
    avisoCarregando = true;
    try {
      const aviso = await api("GET", "/api/aviso-legal");
      $("#aviso-titulo").textContent = `⚠️ ${aviso.titulo}`;
      // Mesmo texto, só sem as quebras de linha "duras" do meio dos parágrafos
      // (o original foi escrito para 80 colunas de terminal). Listas e
      // parágrafos continuam separados.
      $("#aviso-texto").textContent = aviso.texto.replace(/([^\n])\n(?!\n|\s*- )\s*/g, "$1 ");
      $("#aviso-repo").href = aviso.repositorio;
      const itens = limpar($("#aviso-itens"));
      aviso.confirmacoes.forEach((c, i) => {
        const idTexto = `aviso-resumo-${i}`;
        // De propósito, o texto NÃO é um <label>: clicar no texto não marca a
        // caixa (mesma regra da GUI — evita concordar sem ler).
        itens.append(h("div", { class: "item-confirmacao" },
          h("input", { type: "checkbox", name: c.chave, "aria-labelledby": idTexto, onchange: atualizarBotaoAviso }),
          h("details", {}, h("summary", { id: idTexto }, c.resumo), h("p", {}, c.texto))));
      });
      atualizarBotaoAviso();
      const dlg = $("#dialogo-aviso");
      dlg.oncancel = (ev) => ev.preventDefault(); // Esc não fecha: é preciso aceitar ou recusar
      if (!dlg.open) dlg.showModal();
      $("#aviso-texto").focus();
    } catch (e) { mostrarErro(e); } finally { avisoCarregando = false; }
  }
  function atualizarBotaoAviso() {
    const caixas = $$("#aviso-itens input[type=checkbox]");
    $("#aviso-aceitar").disabled = !(caixas.length && caixas.every((c) => c.checked));
  }
  $("#form-aviso").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const confirmacoes = {};
    $$("#aviso-itens input[type=checkbox]").forEach((c) => { confirmacoes[c.name] = c.checked; });
    const r = await acao("POST", "/api/aviso-legal/aceitar", { confirmacoes }, { botao: $("#aviso-aceitar") });
    if (r && r.ok) { $("#dialogo-aviso").close(); iniciarAplicacao(); }
  });
  $("#aviso-recusar").addEventListener("click", async () => {
    const r = await acao("POST", "/api/aviso-legal/recusar");
    bloquear("Termos não aceitos", (r && r.mensagem) || "Você optou por não aceitar os termos.", "A Interface Web foi encerrada. Você já pode fechar esta aba.");
  });

  // ── Navegação ────────────────────────────────────────────────────────
  const CARREGADORES = {};
  function irPara(tela) {
    if (!$(`#tela-${tela}`)) tela = "execucao";
    estadoApp.telaAtual = tela;
    $$(".tela").forEach((s) => { s.hidden = s.id !== `tela-${tela}`; });
    $$("#menu button").forEach((b) => { if (b.dataset.tela === tela) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
    $("#titulo-tela").textContent = $(`#tela-${tela}`).dataset.titulo;
    document.title = `${$(`#tela-${tela}`).dataset.titulo} — SIGAA Sniper`;
    if (location.hash !== `#/${tela}`) history.replaceState(null, "", `#/${tela}`);
    fecharMenu();
    if (CARREGADORES[tela]) CARREGADORES[tela]();
    $("#conteudo").focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }
  $$("#menu button").forEach((b) => b.addEventListener("click", () => irPara(b.dataset.tela)));
  document.addEventListener("click", (ev) => {
    const alvo = ev.target.closest("[data-ir-para]");
    if (alvo) { ev.preventDefault(); irPara(alvo.dataset.irPara); }
    const ajuda = ev.target.closest("[data-ajuda]");
    if (ajuda) { ev.preventDefault(); informar("Ajuda", estadoApp.ajuda[ajuda.dataset.ajuda] || "Ajuda indisponível."); }
  });
  window.addEventListener("hashchange", () => { const t = location.hash.replace("#/", ""); if (t && t !== estadoApp.telaAtual) irPara(t); });

  function abrirMenu() { $("#barra-lateral").classList.add("aberta"); $("#fundo-menu").hidden = false; $("#botao-menu").setAttribute("aria-expanded", "true"); }
  function fecharMenu() { $("#barra-lateral").classList.remove("aberta"); $("#fundo-menu").hidden = true; $("#botao-menu").setAttribute("aria-expanded", "false"); }
  $("#botao-menu").addEventListener("click", abrirMenu);
  $("#fundo-menu").addEventListener("click", fecharMenu);

  // Tema (preferência só visual deste navegador)
  function aplicarTema(tema) { if (tema) document.documentElement.dataset.tema = tema; else delete document.documentElement.dataset.tema; }
  try { aplicarTema(localStorage.getItem("sniper-tema")); } catch (e) { /* armazenamento indisponível */ }
  $("#botao-tema").addEventListener("click", () => {
    const escuroAgora = document.documentElement.dataset.tema
      ? document.documentElement.dataset.tema === "escuro"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    const novo = escuroAgora ? "claro" : "escuro";
    aplicarTema(novo);
    try { localStorage.setItem("sniper-tema", novo); } catch (e) { /* */ }
  });

  // ── Estado geral / cabeçalho ─────────────────────────────────────────
  async function atualizarEstado() {
    if (estadoApp.encerrado) return;
    try {
      const est = await api("GET", "/api/estado");
      estadoApp.estado = est;
      estadoApp.ajuda = est.ajuda || estadoApp.ajuda;
      $("#versao-app").textContent = `Versão ${est.versao}`;
      renderStatus(est.execucao);
      renderChecklist(est);
    } catch (e) { /* tratado em api() */ }
  }

  function renderStatus(exec) {
    const caixa = $("#status-execucao");
    const estado = exec.em_execucao ? (exec.estado === "parando" ? "parando" : "executando") : (exec.estado === "erro" ? "erro" : "parado");
    caixa.dataset.estado = estado;
    const texto = { executando: exec.mensagem.replace("Em execução — ", "Em execução · "), parando: "Parando…", erro: "Encerrado com erro", parado: "Parado" }[estado];
    $(".status-texto", caixa).textContent = texto;
    caixa.title = exec.mensagem;
    const rodando = exec.em_execucao;
    $("#botao-iniciar").disabled = rodando;
    $("#botao-parar").disabled = !rodando || exec.estado === "parando";
    $$("#tela-execucao input").forEach((i) => { i.disabled = rodando; });
    $("#exec-agendar-limpar").disabled = rodando;
    const status = $("#exec-status");
    status.textContent = (rodando ? "🟢 " : estado === "erro" ? "🔴 " : "⚪ ") + exec.mensagem;
    status.style.color = rodando ? "var(--sucesso)" : estado === "erro" ? "var(--perigo)" : "";
  }

  function renderChecklist(est) {
    const lista = limpar($("#checklist"));
    const item = (ok, texto, tela, rotulo) => lista.append(h("li", {},
      h("span", { class: "icone", "aria-hidden": "true" }, ok === null ? "ℹ️" : ok ? "✅" : "⚠️"),
      h("span", {}, texto),
      tela ? h("button", { type: "button", class: "botao botao-fantasma botao-pequeno", "data-ir-para": tela }, rotulo) : null));
    item(est.credenciais_preenchidas, est.credenciais_preenchidas ? "Credenciais do SIGAA preenchidas (só em memória)." : "Credenciais do SIGAA não preenchidas.", "credenciais", est.credenciais_preenchidas ? "Revisar" : "Preencher");
    item(est.qtd_disciplinas_ativas > 0, `${est.qtd_disciplinas_ativas} disciplina(s) ativa(s) de ${est.qtd_disciplinas} cadastrada(s).`, "disciplinas", "Gerenciar");
    const modo = modoSelecionado();
    const dry = $("#exec-dry-run").checked;
    item(null, modo === "monitoramento"
      ? "SOMENTE MONITORAMENTO — nunca confirma matrícula."
      : dry ? "MATRÍCULA em modo DRY RUN — simula tudo, mas NÃO confirma matrícula real."
        : "⚠️ MATRÍCULA REAL — vai confirmar matrícula de verdade quando achar vaga.");
  }

  // ── ▶️ Execução ──────────────────────────────────────────────────────
  const modoSelecionado = () => ($("input[name=modo]:checked") || {}).value || "monitoramento";
  function paraDatetimeLocal(texto) {
    const m = /^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2}):(\d{2})$/.exec(texto || "");
    return m ? `${m[3]}-${m[2]}-${m[1]}T${m[4]}:${m[5]}:${m[6]}` : "";
  }
  function deDatetimeLocal(valor) {
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?/.exec(valor || "");
    return m ? `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}:${m[6] || "00"}` : "";
  }
  function preencherExecucao(est) {
    if (est.execucao && est.execucao.em_execucao) return; // não mexe na execução em andamento
    const r = $(`input[name=modo][value="${est.modo}"]`);
    if (r) r.checked = true;
    $("#exec-dry-run").checked = !!est.dry_run;
    $("#exec-agendar").value = paraDatetimeLocal(est.agendar_inicio);
    atualizarVisibilidadeModo();
  }
  function atualizarVisibilidadeModo() {
    const matricula = modoSelecionado() === "matricula";
    $("#bloco-dry-run").hidden = !matricula;
    $("#aviso-matricula-real").hidden = !(matricula && !$("#exec-dry-run").checked);
    if (estadoApp.estado) renderChecklist(estadoApp.estado);
  }
  $$("input[name=modo]").forEach((r) => r.addEventListener("change", atualizarVisibilidadeModo));
  $("#exec-dry-run").addEventListener("change", atualizarVisibilidadeModo);
  $("#exec-agendar-limpar").addEventListener("click", () => { $("#exec-agendar").value = ""; });

  $("#botao-iniciar").addEventListener("click", async () => {
    const corpo = { modo: modoSelecionado(), dry_run: $("#exec-dry-run").checked, agendar_inicio: deDatetimeLocal($("#exec-agendar").value) };
    const r = await acao("POST", "/api/execucao/iniciar", corpo, { botao: $("#botao-iniciar"), rotuloSim: "Sim, iniciar matrícula real" });
    if (!r) { await atualizarEstado(); return; }
    toast("Execução iniciada.", "sucesso");
    renderStatus(r.execucao);
    await atualizarEstado();
    if (r.abrir_dashboard) irPara("dashboard");
  });
  $("#botao-parar").addEventListener("click", async () => {
    const r = await acao("POST", "/api/execucao/parar", {}, { botao: $("#botao-parar") });
    if (r) { renderStatus(r.execucao); toast("Parando — aguardando os workers atuais encerrarem.", "info"); }
  });

  // ── 📊 Dashboard ─────────────────────────────────────────────────────
  const fmt = (v, suf = "", casas = 1) => (v === null || v === undefined ? null : `${Number(v).toFixed(casas)}${suf}`);
  const fmtMs = (v) => (v === null || v === undefined ? null : `${Math.round(v)} ms`);
  let historicoVagas = {};

  async function atualizarDashboard() {
    if (estadoApp.telaAtual !== "dashboard" || estadoApp.encerrado) return;
    let m;
    try { m = await api("GET", "/api/dashboard"); } catch (e) { return; }
    historicoVagas = m.historico_vagas || {};
    const saude = {
      aguardando_trafego: ["Aguardando tráfego", "selo-neutro"], estavel: ["✅ Sistema estável", "selo-sucesso"],
      degradado: ["⚠️ Degradado", "selo-aviso"], critico: ["📛 Crítico", "selo-perigo"],
    }[m.saude.status] || ["—", "selo-neutro"];
    const selo = $("#dash-saude");
    selo.className = `selo ${saude[1]}`;
    selo.textContent = saude[0] + (m.saude.taxa_erro !== null && m.saude.status !== "estavel" && m.saude.status !== "aguardando_trafego" ? ` (erros: ${Math.round(m.saude.taxa_erro * 100)}%)` : "");

    const cards = [
      ["Requisições/s", fmt(m.rps_atual, " req/s")], ["Buscas/s", fmt(m.bps_atual, " bps")],
      ["Latência (últ. 100)", fmtMs(m.latencia_recente_ms)], ["Total de buscas", String(m.total_buscas)],
      ["Vagas encontradas", String(m.vagas_encontradas)], ["Tempo rodando", m.uptime === "sem dados" ? null : m.uptime],
      ["Média histórica", fmt(m.avg_rps, " req/s")], ["Latência mín / máx",
        m.latencia_min_ms === null ? null : `${fmtMs(m.latencia_min_ms)} / ${fmtMs(m.latencia_max_ms)}`],
      ["Total de requisições", `${m.total_reqs}${m.total_reqs_falha_rede ? ` (${m.total_reqs_falha_rede} c/ falha)` : ""}`],
    ];
    const grade = limpar($("#dash-cards"));
    cards.forEach(([rotulo, valor]) => grade.append(h("div", { class: "card-metrica" },
      h("div", { class: "rotulo" }, rotulo), h("div", { class: `valor${valor === null ? " sem-dados" : ""}` }, valor === null ? "sem dados" : valor))));

    const alerta = $("#dash-alerta");
    alerta.hidden = !m.workers_com_alerta.length;
    alerta.textContent = m.workers_com_alerta.length ? `⚠ Possível problema detectado: ${m.workers_com_alerta.join(" | ")}` : "";

    const ordem = (id) => { const x = /^W(\d+)$/.exec(id); return x ? Number(x[1]) : 9999; };
    const corpo = limpar($("#dash-workers"));
    m.workers.sort((a, b) => ordem(a.id) - ordem(b.id)).forEach((w) => corpo.append(h("tr", {},
      h("td", {}, h("strong", {}, w.id)),
      h("td", { class: `num${w.erros ? " lat-vermelho" : ""}` }, String(w.erros)),
      h("td", { class: "num" }, String(w.buscas)),
      h("td", {}, w.ultima_acao),
      h("td", { class: `num lat-${w.cor_latencia || ""}` }, w.latencia ? `${w.latencia} ms` : "–"),
      h("td", { class: `num${w.ocioso_seg > 5 ? " lat-vermelho" : ""}` }, `${w.ocioso_seg.toFixed(1)}s`))));
    $("#dash-workers-vazio").hidden = m.workers.length > 0;

    const listar = (sel, linhas, vazio) => {
      const ul = limpar($(sel));
      if (!linhas.length) ul.append(h("li", { class: "vazio" }, vazio));
      linhas.forEach((l) => ul.append(h("li", {}, l)));
    };
    listar("#dash-vagas", m.registro_vagas, "Aguardando o surgimento de vagas…");
    listar("#dash-erros", m.log_erros, "Sistema rodando liso e sem falhas.");
    renderStatus(m.execucao);
  }
  $("#dash-historico").addEventListener("click", () => {
    const chaves = Object.keys(historicoVagas);
    if (!chaves.length) { dialogo({ titulo: "Histórico de vagas por disciplina", texto: "Ainda não há histórico suficiente nesta execução." }); return; }
    const nos = h("div", {}, chaves.map((d) => h("div", {},
      h("h3", {}, d), h("ul", {}, historicoVagas[d].map(([hora, vagas]) => h("li", {}, `${hora} — ${vagas} vaga(s)`))))));
    dialogo({ titulo: "Histórico de vagas por disciplina", nos });
  });
  CARREGADORES.dashboard = atualizarDashboard;

  // ── 📜 Logs ──────────────────────────────────────────────────────────
  const logs = { registros: [], ultimoSeq: 0, selecionado: null, workers: new Set(), categoriasProntas: false };
  async function atualizarLogs(forcar = false) {
    if (estadoApp.telaAtual !== "logs" || estadoApp.encerrado) return;
    if ($("#log-pausar").checked && !forcar) return;
    let r;
    try { r = await api("GET", `/api/logs?desde=${logs.ultimoSeq}`); } catch (e) { return; }
    if (!logs.categoriasProntas) {
      const sel = $("#log-categoria");
      r.categorias.forEach((c) => sel.append(h("option", {}, c)));
      logs.categoriasProntas = true;
    }
    if (r.ultimo_seq < logs.ultimoSeq) logs.ultimoSeq = 0; // servidor reiniciado
    if (!r.registros.length && !forcar) return;
    r.registros.forEach((reg) => {
      logs.registros.push(reg);
      if (!logs.workers.has(reg.worker)) {
        logs.workers.add(reg.worker);
        const sel = $("#log-worker");
        const atual = sel.value;
        limpar(sel).append(h("option", {}, "Todos"), ...[...logs.workers].sort().map((w) => h("option", {}, w)));
        sel.value = atual;
      }
    });
    if (logs.registros.length > 1000) logs.registros.splice(0, logs.registros.length - 1000);
    logs.ultimoSeq = Math.max(logs.ultimoSeq, r.ultimo_seq);
    renderLogs();
  }
  function passaFiltro(reg) {
    const nivel = $("#log-nivel").value, cat = $("#log-categoria").value, worker = $("#log-worker").value;
    const busca = $("#log-busca").value.trim().toLowerCase();
    if (nivel !== "Todos" && reg.nivel !== nivel) return false;
    if (cat !== "Todas" && reg.categoria !== cat) return false;
    if (worker !== "Todos" && reg.worker !== worker) return false;
    if (busca && !(`${reg.titulo} ${reg.corpo} ${reg.bruto.message || ""}`.toLowerCase().includes(busca))) return false;
    return true;
  }
  function renderLogs() {
    const lista = $(".logs-lista");
    const noFim = lista.scrollHeight - lista.scrollTop - lista.clientHeight < 40;
    const corpo = limpar($("#log-linhas"));
    const visiveis = logs.registros.filter(passaFiltro);
    const frag = document.createDocumentFragment();
    visiveis.forEach((reg) => frag.append(h("tr", {
      "aria-selected": reg.seq === logs.selecionado ? "true" : "false", tabindex: "0", dataset: { seq: reg.seq },
    }, h("td", { class: "num" }, reg.hora), h("td", {}, reg.worker), h("td", { class: `cat cat-${reg.categoria}` }, reg.categoria),
    h("td", {}, reg.nivel), h("td", {}, reg.titulo))));
    corpo.append(frag);
    $("#log-vazio").hidden = visiveis.length > 0;
    $("#log-contagem").textContent = `${visiveis.length} de ${logs.registros.length} evento(s)`;
    if (noFim) lista.scrollTop = lista.scrollHeight;
  }
  function selecionarLog(seq) {
    logs.selecionado = seq;
    $$("#log-linhas tr").forEach((tr) => tr.setAttribute("aria-selected", Number(tr.dataset.seq) === seq ? "true" : "false"));
    const reg = logs.registros.find((r) => r.seq === seq);
    $("#log-detalhe-corpo").textContent = reg ? reg.corpo : "Selecione um evento para ver a explicação.";
    $("#log-detalhe-corpo").classList.toggle("texto-suave", !reg);
    renderDetalheTecnico();
  }
  function renderDetalheTecnico() {
    const reg = logs.registros.find((r) => r.seq === logs.selecionado);
    const pre = $("#log-detalhe-tecnico");
    pre.hidden = !($("#log-tecnico").checked && reg);
    pre.textContent = reg ? JSON.stringify(reg.bruto, null, 2) : "";
  }
  $("#log-linhas").addEventListener("click", (ev) => { const tr = ev.target.closest("tr"); if (tr) selecionarLog(Number(tr.dataset.seq)); });
  $("#log-linhas").addEventListener("keydown", (ev) => {
    const tr = ev.target.closest("tr"); if (!tr) return;
    if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); selecionarLog(Number(tr.dataset.seq)); }
    if (ev.key === "ArrowDown" && tr.nextElementSibling) { ev.preventDefault(); tr.nextElementSibling.focus(); }
    if (ev.key === "ArrowUp" && tr.previousElementSibling) { ev.preventDefault(); tr.previousElementSibling.focus(); }
  });
  ["#log-nivel", "#log-categoria", "#log-worker"].forEach((s) => $(s).addEventListener("change", renderLogs));
  $("#log-busca").addEventListener("input", renderLogs);
  $("#log-tecnico").addEventListener("change", renderDetalheTecnico);
  $("#log-limpar").addEventListener("click", () => { logs.registros = []; logs.selecionado = null; selecionarLog(null); renderLogs(); toast("Tela limpa — o arquivo de log continua intacto.", "info"); });
  $("#log-abrir").addEventListener("click", async (ev) => { const r = await acao("POST", "/api/logs/abrir-arquivo", {}, { botao: ev.currentTarget }); if (r) toast(r.mensagem, "sucesso"); });
  $("#log-baixar").addEventListener("click", (ev) => { ev.preventDefault(); baixar("/api/logs/arquivo", "sigaa_sniper_audit.json"); });
  CARREGADORES.logs = () => atualizarLogs(true);

  // ── 🔑 Credenciais ───────────────────────────────────────────────────
  let temSenha = false;
  async function carregarCredenciais() {
    let c;
    try { c = await api("GET", "/api/credenciais"); } catch (e) { mostrarErro(e); return; }
    const f = $("#form-credenciais");
    definir(f.usuario, c.usuario); definir(f.cpf, c.cpf); definir(f.nascimento, c.nascimento); definir(f.senha, "");
    temSenha = c.tem_senha;
    $("#cred-senha-dica").hidden = !temSenha;
    f.senha.placeholder = temSenha ? "•••••••• (mantida)" : "";
  }
  $("#form-credenciais").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.currentTarget;
    const corpo = { usuario: f.usuario.value, senha: f.senha.value, cpf: f.cpf.value, nascimento: f.nascimento.value, manter_senha: temSenha && !f.senha.value };
    const r = await acao("POST", "/api/credenciais", corpo, { botao: $("button[type=submit]", f) });
    if (r) { formularioSalvo(f); toast(r.mensagem, "sucesso"); carregarCredenciais(); atualizarEstado(); }
  });
  $("#cred-limpar").addEventListener("click", async () => {
    const r = await acao("POST", "/api/credenciais/limpar");
    if (r) { formularioSalvo($("#form-credenciais")); toast(r.mensagem, "info"); carregarCredenciais(); atualizarEstado(); }
  });
  CARREGADORES.credenciais = carregarCredenciais;

  // ── 📚 Disciplinas ───────────────────────────────────────────────────
  let disciplinas = [];
  let edicao = null; // { indice, chave } quando editando
  async function carregarDisciplinas() {
    try { disciplinas = (await api("GET", "/api/disciplinas")).disciplinas; } catch (e) { mostrarErro(e); return; }
    renderDisciplinas();
  }
  function renderDisciplinas() {
    const corpo = limpar($("#disc-linhas"));
    disciplinas.forEach((d) => {
      const corpoAcao = { chave: d.chave };
      corpo.append(h("tr", { class: d.ativa ? "" : "linha-inativa" },
        h("td", {}, h("strong", {}, d.codigo)), h("td", {}, d.turma),
        h("td", { title: d.nome_departamento || "Código fora da lista de referência" },
          String(d.departamento), d.departamento_conhecido ? "" : h("span", { class: "selo selo-aviso selo-espacado" }, "não reconhecido")),
        h("td", {}, d.professor || "—"),
        h("td", {}, h("span", { class: `selo ${d.ativa ? "selo-sucesso" : "selo-neutro"}` }, d.ativa ? "Sim" : "Não")),
        h("td", {}, h("div", { class: "acoes-linha" },
          h("button", { type: "button", class: "botao botao-fantasma botao-pequeno", onclick: () => abrirDisciplina(d) }, "✏️ Editar"),
          h("button", { type: "button", class: "botao botao-fantasma botao-pequeno", onclick: async (ev) => {
            const r = await acao("POST", `/api/disciplinas/${d.indice}/alternar`, corpoAcao, { botao: ev.currentTarget });
            if (r) { disciplinas = r.disciplinas; renderDisciplinas(); toast(r.mensagem, "sucesso"); atualizarEstado(); } else carregarDisciplinas();
          } }, d.ativa ? "⏸ Desativar" : "▶ Ativar"),
          h("button", { type: "button", class: "botao botao-fantasma botao-pequeno texto-perigo", onclick: async (ev) => {
            const r = await acao("POST", `/api/disciplinas/${d.indice}/remover`, corpoAcao, { botao: ev.currentTarget, rotuloSim: "Remover" });
            if (r) { disciplinas = r.disciplinas; renderDisciplinas(); toast(r.mensagem, "sucesso"); atualizarEstado(); } else carregarDisciplinas();
          } }, "🗑️ Remover")))));
    });
    $("#disc-vazio").hidden = disciplinas.length > 0;
  }

  // Busca de departamento (combobox simples)
  let deptoSelecionado = 0;
  let buscaTimer = null;
  function definirDepto(codigo, nome) {
    deptoSelecionado = codigo;
    $("#disc-depto-busca").value = codigo ? (nome ? `${codigo} — ${nome}` : String(codigo)) : "";
    $("#disc-depto-selecionado").textContent = codigo ? `Selecionado: ${codigo}${nome ? ` — ${nome}` : " (fora da lista de referência — confira o código)"}` : "Nenhum departamento selecionado.";
    fecharSugestoes();
  }
  function fecharSugestoes() { $("#disc-depto-lista").hidden = true; $("#disc-depto-busca").setAttribute("aria-expanded", "false"); }
  $("#disc-depto-busca").addEventListener("input", (ev) => {
    const termo = ev.target.value.trim();
    const m = /^(\d+)(\s*—.*)?$/.exec(termo);
    deptoSelecionado = m ? Number(m[1]) : 0;
    $("#disc-depto-selecionado").textContent = deptoSelecionado ? `Código digitado: ${deptoSelecionado}` : "Nenhum departamento selecionado.";
    clearTimeout(buscaTimer);
    buscaTimer = setTimeout(async () => {
      let r; try { r = await api("GET", `/api/departamentos?q=${encodeURIComponent(termo)}`); } catch (e) { return; }
      const ul = limpar($("#disc-depto-lista"));
      r.departamentos.forEach((d) => ul.append(h("li", { role: "option", tabindex: "-1", onclick: () => definirDepto(d.codigo, d.nome),
        onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); definirDepto(d.codigo, d.nome); } } }, `${d.codigo} — ${d.nome}`)));
      ul.hidden = !r.departamentos.length;
      $("#disc-depto-busca").setAttribute("aria-expanded", String(!ul.hidden));
    }, 150);
  });
  $("#disc-depto-busca").addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowDown" && !$("#disc-depto-lista").hidden) { ev.preventDefault(); const p = $("#disc-depto-lista li"); if (p) p.focus(); }
    if (ev.key === "Escape" && !$("#disc-depto-lista").hidden) { ev.preventDefault(); ev.stopPropagation(); fecharSugestoes(); }
  });
  $("#disc-depto-lista").addEventListener("keydown", (ev) => {
    const li = ev.target.closest("li"); if (!li) return;
    if (ev.key === "ArrowDown" && li.nextElementSibling) { ev.preventDefault(); li.nextElementSibling.focus(); }
    if (ev.key === "ArrowUp") { ev.preventDefault(); (li.previousElementSibling || $("#disc-depto-busca")).focus(); }
  });

  function abrirDisciplina(d) {
    const f = $("#form-disciplina");
    f.reset();
    edicao = d ? { indice: d.indice, chave: d.chave } : null;
    $("#disc-titulo").textContent = d ? `Editar ${d.chave}` : "Adicionar disciplina";
    if (d) { f.codigo.value = d.codigo; f.turma.value = d.turma; f.professor.value = d.professor; definirDepto(d.departamento, d.nome_departamento); } else definirDepto(0);
    $("#dialogo-disciplina").showModal();
    f.codigo.focus();
  }
  $("#disc-adicionar").addEventListener("click", () => abrirDisciplina(null));
  $("#disc-cancelar").addEventListener("click", () => $("#dialogo-disciplina").close());
  $("#form-disciplina").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.currentTarget;
    const corpo = { codigo: f.codigo.value, turma: f.turma.value, departamento: deptoSelecionado, professor: f.professor.value };
    let r;
    if (edicao) r = await acao("POST", `/api/disciplinas/${edicao.indice}/editar`, { ...corpo, chave_original: edicao.chave }, { botao: $("button[type=submit]", f), rotuloSim: "Salvar mesmo assim" });
    else r = await acao("POST", "/api/disciplinas", corpo, { botao: $("button[type=submit]", f), rotuloSim: "Salvar mesmo assim" });
    if (r) { $("#dialogo-disciplina").close(); disciplinas = r.disciplinas; renderDisciplinas(); toast(r.mensagem, "sucesso"); atualizarEstado(); }
  });
  CARREGADORES.disciplinas = carregarDisciplinas;

  // ── 🔔 Notificações ──────────────────────────────────────────────────
  const ROTULOS_EVENTOS = {
    vaga_detectada: "Vaga encontrada", matricula_sucesso: "Matrícula confirmada",
    matricula_falha: "Tentativa de matrícula falhou (retry automático)",
    matricula_bloqueada: "Disciplina bloqueada pelo SIGAA (pré-requisito/choque)", erro_critico: "Erro crítico",
  };
  function dadosNotificacoes() {
    const f = $("#form-notificacoes");
    const eventos = {};
    $$("#notif-eventos input").forEach((c) => { eventos[c.name] = c.checked; });
    return {
      telegram_ativo: f.telegram_ativo.checked, ntfy_ativo: f.ntfy_ativo.checked, alarme_ativo: f.alarme_ativo.checked,
      telegram_token: f.telegram_token.value, telegram_chat_id: f.telegram_chat_id.value,
      ntfy_topic: f.ntfy_topic.value, ntfy_servidor: f.ntfy_servidor.value,
      alarme_repeticoes: f.alarme_repeticoes.value, alarme_duracao: f.alarme_duracao.value,
      eventos, lembrar: f.lembrar.checked,
    };
  }
  async function carregarNotificacoes() {
    let n; try { n = await api("GET", "/api/notificacoes"); } catch (e) { mostrarErro(e); return; }
    const f = $("#form-notificacoes");
    ["telegram_ativo", "ntfy_ativo", "alarme_ativo", "lembrar"].forEach((k) => definir(f[k], n[k]));
    ["telegram_token", "telegram_chat_id", "ntfy_topic", "ntfy_servidor"].forEach((k) => definir(f[k], n[k] || ""));
    definir(f.alarme_repeticoes, n.alarme_repeticoes); definir(f.alarme_duracao, n.alarme_duracao);
    const caixa = $("#notif-eventos");
    if (!caixa.children.length) {
      Object.entries(ROTULOS_EVENTOS).forEach(([chave, rotulo]) => caixa.append(
        h("label", { class: "caixa" }, h("input", { type: "checkbox", name: chave }), rotulo)));
    }
    $$("input", caixa).forEach((c) => definir(c, n.eventos[c.name]));
  }
  $("#notif-lembrar").addEventListener("change", async (ev) => {
    if (ev.target.checked) return;
    const r = await acao("POST", "/api/notificacoes/persistencia", { lembrar: false });
    if (r) toast(r.mensagem, "info");
  });
  $("#form-notificacoes").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.currentTarget;
    const r = await acao("POST", "/api/notificacoes", dadosNotificacoes(), { botao: $("button[type=submit]", f) });
    if (r) { formularioSalvo(f); toast(r.mensagem, "sucesso"); }
  });
  $$("[data-testar]").forEach((b) => b.addEventListener("click", async (ev) => {
    const canal = ev.currentTarget.dataset.testar;
    const caixa = limpar($("#notif-resultado"));
    caixa.append(h("p", { class: "texto-suave" }, canal === "todos" ? "Testando todos os canais habilitados…" : `Enviando teste (${canal})…`));
    const r = await acao("POST", "/api/notificacoes/testar", { ...dadosNotificacoes(), canal }, { botao: ev.currentTarget });
    limpar(caixa);
    if (!r) return;
    caixa.append(h("div", { class: `alerta ${r.ok ? "alerta-sucesso" : "alerta-erro"}` },
      r.resultados.map((l) => h("p", {}, `${l.ok ? "✅" : "❌"} ${l.canal}: ${l.mensagem}`))));
  }));
  CARREGADORES.notificacoes = carregarNotificacoes;

  // ── ⚙️ Avançado ──────────────────────────────────────────────────────
  const ROTULOS_URLS = { cas_login: "Login (CAS)", portal_discente: "Portal do discente", matricula_extra: "Matrícula extraordinária", confirmacao: "Confirmação", sigaa_base: "Base do SIGAA" };
  const ROTULOS_SECOES = { monitoramento: "Monitoramento (modo, workers, intervalos)", dashboard: "Dashboard", notificacoes: "Notificações", avancado: "Avançado (logs, debug, Interface Web)", urls: "URLs do SIGAA" };
  function textoEspaco(e) { return `logs/: ${e.logs_mb} MB · data/: ${e.data_mb} MB · config/: ${e.config_mb} MB`; }
  function preencherAvancado(a, forcar = false) {
    const f = $("#form-avancado");
    if (forcar) formularioSalvo(f);
    const d = (campo, valor) => definir(f[campo], valor);
    d("num_workers", a.num_workers); d("intervalo_busca", a.intervalo_busca); d("timeout_req", a.timeout_req);
    d("abrir_dashboard_ao_iniciar", a.abrir_dashboard_ao_iniciar); d("nivel_log_console", a.nivel_log_console);
    d("logs.tamanho_max_mb", a.logs.tamanho_max_mb); d("logs.arquivos_mantidos", a.logs.arquivos_mantidos);
    d("json_audit.tamanho_max_mb", a.json_audit.tamanho_max_mb); d("json_audit.arquivos_mantidos", a.json_audit.arquivos_mantidos);
    d("web.host", a.web.host); d("web.porta", a.web.porta); d("web.abrir_navegador", a.web.abrir_navegador);
    const urls = $("#avancado-urls");
    if (!urls.children.length) {
      Object.keys(a.urls).forEach((k) => urls.append(h("label", {}, ROTULOS_URLS[k] || k, h("input", { name: `url.${k}`, spellcheck: "false", autocomplete: "off" }))));
    }
    Object.keys(a.urls).forEach((k) => definir(f[`url.${k}`], a.urls[k]));
    $("#avancado-espaco").textContent = textoEspaco(a.espaco);
    const secoes = $("#avancado-secoes");
    if (!secoes.children.length) {
      a.secoes_restauraveis.forEach((s) => secoes.append(h("label", { class: "caixa" }, h("input", { type: "checkbox", value: s }), ROTULOS_SECOES[s] || s)));
    }
  }
  async function carregarAvancado() {
    try { preencherAvancado(await api("GET", "/api/avancado")); } catch (e) { mostrarErro(e); }
  }
  $("#form-avancado").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.currentTarget;
    const urls = {};
    $$("#avancado-urls input").forEach((i) => { urls[i.name.slice(4)] = i.value; });
    const corpo = {
      num_workers: f.num_workers.value, intervalo_busca: f.intervalo_busca.value, timeout_req: f.timeout_req.value,
      abrir_dashboard_ao_iniciar: f.abrir_dashboard_ao_iniciar.checked, nivel_log_console: f.nivel_log_console.value,
      logs: { tamanho_max_mb: f["logs.tamanho_max_mb"].value, arquivos_mantidos: f["logs.arquivos_mantidos"].value },
      json_audit: { tamanho_max_mb: f["json_audit.tamanho_max_mb"].value, arquivos_mantidos: f["json_audit.arquivos_mantidos"].value },
      web: { host: f["web.host"].value, porta: f["web.porta"].value, abrir_navegador: f["web.abrir_navegador"].checked },
      urls,
    };
    const r = await acao("POST", "/api/avancado", corpo, { botao: $("button[type=submit]", f), rotuloSim: "Salvar assim mesmo" });
    if (r) { preencherAvancado(r.avancado, true); toast(r.mensagem, "sucesso", 8000); recarregarTudo(); }
  });
  async function restaurar(todas, botao) {
    const secoes = $$("#avancado-secoes input:checked").map((c) => c.value);
    const r = await acao("POST", "/api/avancado/restaurar", { todas, secoes }, { botao, rotuloSim: "Restaurar" });
    if (r) { preencherAvancado(r.avancado, true); $$("#avancado-secoes input").forEach((c) => { c.checked = false; }); toast(r.mensagem, "sucesso"); recarregarTudo(); }
  }
  $("#avancado-restaurar").addEventListener("click", (ev) => restaurar(false, ev.currentTarget));
  $("#avancado-restaurar-tudo").addEventListener("click", (ev) => restaurar(true, ev.currentTarget));
  $("#avancado-espaco-atualizar").addEventListener("click", async () => {
    try { $("#avancado-espaco").textContent = textoEspaco((await api("GET", "/api/avancado")).espaco); } catch (e) { mostrarErro(e); }
  });
  $("#avancado-limpar-dumps").addEventListener("click", async (ev) => {
    const r = await acao("POST", "/api/avancado/limpar-dumps", {}, { botao: ev.currentTarget });
    if (r) { toast(r.mensagem, "sucesso"); $("#avancado-espaco").textContent = textoEspaco(r.espaco); }
  });
  $("#avancado-exportar").addEventListener("click", (ev) => { ev.preventDefault(); baixar("/api/config/exportar", "sigaa_sniper_config.json"); });
  $("#avancado-importar-arquivo").addEventListener("change", async (ev) => {
    const arquivo = ev.target.files[0];
    ev.target.value = "";
    if (!arquivo) return;
    if (arquivo.size > 1.5 * 1024 * 1024) { toast("Arquivo grande demais para ser uma configuração exportada pelo programa.", "aviso"); return; }
    const conteudo = await arquivo.text();
    const previa = await acao("POST", "/api/config/importar/previa", { conteudo });
    if (!previa) return;
    const linhas = [`Disciplinas válidas: ${previa.qtd_disciplinas}`];
    if (previa.disciplinas_ignoradas) linhas.push(`Disciplinas ignoradas (inválidas): ${previa.disciplinas_ignoradas}`);
    linhas.push(`Configurações: ${previa.tem_settings ? "sim, serão substituídas" : "não incluídas neste arquivo"}`);
    if (!(await confirmar("Confirmar importação", `Resumo do que será importado:\n\n${linhas.join("\n")}\n\nAplicar agora?`, "Aplicar"))) return;
    const r = await acao("POST", "/api/config/importar/aplicar", { conteudo });
    if (r) {
      toast(r.mensagem, "sucesso");
      $$("form").forEach(formularioSalvo); // importação substitui tudo: recarrega todos os campos
      try { preencherAvancado(await api("GET", "/api/avancado"), true); } catch (e2) { mostrarErro(e2); }
      recarregarTudo();
    }
  });
  CARREGADORES.avancado = carregarAvancado;

  // ── 🩺 Diagnóstico ───────────────────────────────────────────────────
  let relatorioDiag = "";
  async function rodarDiagnostico(caminho, botao) {
    const lista = limpar($("#diag-itens"));
    lista.append(h("li", {}, h("span", { class: "texto-suave" }, caminho.endsWith("camadas") ? "Testando cada camada (Internet → SIGAA → consulta pública → …)…" : "Rodando diagnóstico completo…")));
    const r = await acao("POST", caminho, {}, { botao });
    limpar(lista);
    if (!r) return;
    relatorioDiag = r.relatorio;
    r.itens.forEach((i) => lista.append(h("li", {},
      h("span", { "aria-hidden": "true" }, i.ok === true ? "✅" : i.ok === false ? "❌" : "⚪"),
      h("div", {}, h("div", { class: "nome" }, i.nome, h("span", { class: "visualmente-oculto" }, i.ok === true ? " — OK" : i.ok === false ? " — ERRO" : " — não testado")),
        h("div", { class: "detalhe" }, i.detalhe)))));
    $("#diag-bruto").textContent = relatorioDiag;
    $("#diag-bruto-bloco").hidden = false;
    $("#diag-exportar").disabled = $("#diag-copiar").disabled = false;
  }
  $("#diag-completo").addEventListener("click", (ev) => rodarDiagnostico("/api/diagnostico/completo", ev.currentTarget));
  $("#diag-camadas").addEventListener("click", (ev) => rodarDiagnostico("/api/diagnostico/camadas", ev.currentTarget));
  $("#diag-exportar").addEventListener("click", () => salvarBlob(new Blob([relatorioDiag], { type: "text/plain;charset=utf-8" }), "diagnostico_sigaa_sniper.txt"));
  $("#diag-copiar").addEventListener("click", async () => {
    if (!relatorioDiag) { toast("Rode um diagnóstico primeiro.", "info"); return; }
    // Mesma segunda camada de sanitização da GUI antes de copiar.
    if (["senha=", "password=", "token=", "cpf="].some((t) => relatorioDiag.toLowerCase().includes(t))) {
      dialogo({ titulo: "Bloqueado", texto: "O relatório parece conter um dado sensível — cópia cancelada por segurança." });
      return;
    }
    try { await navigator.clipboard.writeText(relatorioDiag); toast("Diagnóstico copiado para a área de transferência.", "sucesso"); }
    catch (e) { $("#diag-bruto-bloco").open = true; toast("Não foi possível copiar automaticamente — selecione o texto do relatório e copie.", "aviso"); }
  });

  // ── 🧪 Experimental ──────────────────────────────────────────────────
  async function carregarExperimental() {
    let r; try { r = await api("GET", "/api/experimental"); } catch (e) { mostrarErro(e); return; }
    const lista = limpar($("#exp-lista"));
    r.experimentos.forEach((exp) => {
      const saida = h("pre", { class: "bloco-codigo", hidden: true });
      lista.append(h("article", { class: "cartao" },
        h("div", { class: "cartao-cabecalho" }, h("h2", {}, exp.nome), h("span", { class: `selo ${exp.disponivel ? "selo-sucesso" : "selo-aviso"}` }, exp.status)),
        h("p", {}, exp.descricao),
        h("p", { class: "meta" }, `Origem: ${exp.origem}`),
        h("p", { class: "meta" }, `Dependências: ${exp.dependencias.length ? exp.dependencias.join(", ") : "nenhuma (usa o que o programa principal já tem)"}`),
        h("p", { class: "meta" }, `Riscos/limitações: ${exp.riscos}`),
        h("div", { class: "acoes acoes-compactas" },
          h("button", { type: "button", class: "botao botao-secundario", onclick: async (ev) => {
            saida.hidden = false; saida.textContent = "Executando…";
            const res = await acao("POST", "/api/experimental/executar", { id: exp.id }, { botao: ev.currentTarget, rotuloSim: "Executar" });
            if (res) saida.textContent = res.resultado; else saida.hidden = true;
          } }, "▶️ Executar"),
          h("button", { type: "button", class: "botao botao-fantasma", onclick: () => informar(`Guia — ${exp.nome}`, exp.guia) }, "📖 Ver guia")),
        saida));
    });
  }
  CARREGADORES.experimental = carregarExperimental;

  // ── ❓ Ajuda (Markdown simples → DOM, sem innerHTML) ─────────────────
  function inline(texto) {
    const frag = document.createDocumentFragment();
    const re = /(`[^`]+`|\*\*[^*]+\*\*|https?:\/\/[^\s)<>]+)/g;
    let ultimo = 0, m;
    while ((m = re.exec(texto))) {
      if (m.index > ultimo) frag.append(texto.slice(ultimo, m.index));
      const t = m[0];
      if (t.startsWith("`")) frag.append(h("code", {}, t.slice(1, -1)));
      else if (t.startsWith("**")) frag.append(h("strong", {}, t.slice(2, -2)));
      else frag.append(h("a", { href: t, target: "_blank", rel: "noopener noreferrer" }, t));
      ultimo = m.index + t.length;
    }
    if (ultimo < texto.length) frag.append(texto.slice(ultimo));
    return frag;
  }
  function markdown(texto) {
    const raiz = document.createDocumentFragment();
    const linhas = texto.replace(/\r/g, "").split("\n");
    let i = 0, lista = null, paragrafo = [];
    const fecharParagrafo = () => { if (paragrafo.length) { raiz.append(h("p", {}, inline(paragrafo.join(" ")))); paragrafo = []; } };
    const fecharLista = () => { lista = null; };
    while (i < linhas.length) {
      const l = linhas[i];
      if (l.startsWith("```")) {
        fecharParagrafo(); fecharLista();
        const bloco = []; i++;
        while (i < linhas.length && !linhas[i].startsWith("```")) bloco.push(linhas[i++]);
        raiz.append(h("pre", {}, bloco.join("\n"))); i++; continue;
      }
      const tit = /^(#{1,4})\s+(.*)$/.exec(l);
      if (tit) { fecharParagrafo(); fecharLista(); raiz.append(h(`h${Math.min(4, tit[1].length)}`, {}, inline(tit[2]))); i++; continue; }
      if (/^\s*\|.*\|\s*$/.test(l)) {
        fecharParagrafo(); fecharLista();
        const tabela = h("table", {}); let primeira = true;
        while (i < linhas.length && /^\s*\|.*\|\s*$/.test(linhas[i])) {
          const cels = linhas[i].trim().slice(1, -1).split("|").map((c) => c.trim());
          if (!cels.every((c) => /^:?-{2,}:?$/.test(c))) tabela.append(h("tr", {}, cels.map((c) => h(primeira ? "th" : "td", {}, inline(c)))));
          primeira = false; i++;
        }
        raiz.append(tabela); continue;
      }
      const item = /^\s*(?:[-*]|\d+\.)\s+(.*)$/.exec(l);
      if (item) {
        fecharParagrafo();
        if (!lista) { lista = h(/^\s*\d+\./.test(l) ? "ol" : "ul", {}); raiz.append(lista); }
        lista.append(h("li", {}, inline(item[1]))); i++; continue;
      }
      if (!l.trim()) { fecharParagrafo(); fecharLista(); i++; continue; }
      fecharLista(); paragrafo.push(l.trim()); i++;
    }
    fecharParagrafo();
    return raiz;
  }
  async function carregarAjuda() {
    if (estadoApp.carregado.ajuda) return;
    let r; try { r = await api("GET", "/api/ajuda"); } catch (e) { mostrarErro(e); return; }
    estadoApp.carregado.ajuda = true;
    const abas = limpar($("#ajuda-abas"));
    const mostrar = (idx) => {
      $$("button", abas).forEach((b, j) => b.setAttribute("aria-selected", String(j === idx)));
      limpar($("#ajuda-conteudo")).append(markdown(r.documentos[idx].conteudo));
    };
    r.documentos.forEach((d, idx) => abas.append(h("button", { type: "button", role: "tab", onclick: () => mostrar(idx) }, d.titulo)));
    mostrar(0);
  }
  CARREGADORES.ajuda = carregarAjuda;

  // ── ℹ️ Sobre ─────────────────────────────────────────────────────────
  let guiaManual = "";
  async function carregarSobre() {
    let s; try { s = await api("GET", "/api/sobre"); } catch (e) { mostrarErro(e); return; }
    $("#sobre-repo").href = s.repositorio; $("#sobre-repo").textContent = `🔗 ${s.repositorio}`;
    $("#sobre-versao").textContent = s.versao;
    guiaManual = s.guia_manual;
    if (!s.atalho_suportado) { $("#sobre-guia").hidden = false; $("#sobre-guia").textContent = s.guia_manual; }
  }
  $("#sobre-atalho").addEventListener("click", async (ev) => {
    const r = await acao("POST", "/api/sobre/atalho", {}, { botao: ev.currentTarget });
    if (r) toast(`✅ ${r.mensagem}`, "sucesso", 8000);
    else if (guiaManual) { $("#sobre-guia").hidden = false; $("#sobre-guia").textContent = guiaManual; }
  });
  CARREGADORES.sobre = carregarSobre;

  // ── Encerrar ─────────────────────────────────────────────────────────
  $("#botao-encerrar").addEventListener("click", async () => {
    if (!(await confirmar("Encerrar a Interface Web", "Encerrar a Interface Web e voltar ao menu do terminal? As credenciais serão apagadas da memória.", "Encerrar"))) return;
    const r = await acao("POST", "/api/encerrar", {}, { rotuloSim: "Parar e sair" });
    if (r) bloquear("👋 Interface Web encerrada", r.mensagem, "Para abrir de novo, escolha [0] 🌐 Interface Web no menu do programa.");
  });
  window.addEventListener("beforeunload", (ev) => {
    if (!estadoApp.encerrado && estadoApp.estado && estadoApp.estado.execucao && estadoApp.estado.execucao.em_execucao) {
      ev.preventDefault(); ev.returnValue = "";
    }
  });

  // ── Assistente de primeira execução ──────────────────────────────────
  const assistente = { etapa: 0, credenciais: {}, disciplinas: [], modo: "monitoramento" };
  const ETAPAS = ["Boas-vindas", "Credenciais", "Disciplina", "Modo", "Notificações", "Concluir"];
  function salvarEtapaAtual() {
    const c = $("#assistente-conteudo");
    if (assistente.etapa === 1) ["usuario", "senha", "cpf", "nascimento"].forEach((k) => { const i = $(`[name=a_${k}]`, c); if (i) assistente.credenciais[k] = i.value; });
    if (assistente.etapa === 3) { const r = $("input[name=a_modo]:checked", c); if (r) assistente.modo = r.value; }
  }
  function renderAssistente() {
    const c = limpar($("#assistente-conteudo"));
    $("#assistente-passos").textContent = `Etapa ${assistente.etapa + 1} de ${ETAPAS.length} · ${ETAPAS.join(" → ")}`;
    $("#assistente-voltar").disabled = assistente.etapa === 0;
    $("#assistente-proximo").textContent = assistente.etapa === ETAPAS.length - 1 ? "Finalizar" : "Próximo ▶";
    const cr = assistente.credenciais;
    const campo = (rot, nome, tipo = "text") => h("label", {}, rot, h("input", { name: `a_${nome}`, type: tipo, value: cr[nome] || "", autocomplete: tipo === "password" ? "new-password" : "off" }));
    switch (assistente.etapa) {
      case 0:
        c.append(h("h2", { id: "assistente-titulo" }, "Bem-vindo ao SIGAA Sniper"),
          h("p", {}, "Vamos configurar o essencial em algumas etapas rápidas — todas opcionais, você pode pular a qualquer momento e configurar tudo depois nas abas normais."),
          h("p", { class: "texto-suave" }, "Etapas: credenciais → disciplina → modo → notificações → concluir."));
        break;
      case 1:
        c.append(h("h2", { id: "assistente-titulo" }, "1. Credenciais do SIGAA"),
          h("p", { class: "texto-suave" }, "Nunca são salvas em disco — só ficam em memória nesta execução. Pode preencher agora ou pular e preencher na aba Credenciais."),
          campo("Matrícula", "usuario"), campo("Senha", "senha", "password"), campo("CPF", "cpf"), campo("Nascimento (DD/MM/AAAA)", "nascimento"));
        break;
      case 2: {
        const status = h("p", { class: "dica" }, `${estadoApp.estado.qtd_disciplinas + assistente.disciplinas.length} disciplina(s) já cadastrada(s).`);
        const codigo = h("input", { name: "a_codigo", autocomplete: "off" });
        const turma = h("input", { name: "a_turma", autocomplete: "off" });
        const depto = h("input", { name: "a_depto", autocomplete: "off", list: "a-deptos", placeholder: "nome ou código" });
        const datalist = h("datalist", { id: "a-deptos" });
        depto.addEventListener("input", async () => {
          let r; try { r = await api("GET", `/api/departamentos?q=${encodeURIComponent(depto.value)}`); } catch (e) { return; }
          limpar(datalist).append(...r.departamentos.slice(0, 20).map((d) => h("option", { value: `${d.codigo} — ${d.nome}` })));
        });
        c.append(h("h2", { id: "assistente-titulo" }, "2. Adicionar uma disciplina"),
          h("p", { class: "texto-suave" }, "Pode adicionar mais depois na aba Disciplinas. Digite o departamento para buscar."),
          h("label", {}, "Código (ex: FGA0211)", codigo), h("label", {}, "Turma (ex: 01)", turma),
          h("label", {}, "Departamento (nome ou código)", depto), datalist,
          h("button", { type: "button", class: "botao botao-secundario alinhar-inicio", onclick: () => {
            const m = /^(\d+)/.exec(depto.value.trim());
            const cod = codigo.value.trim().toUpperCase(), t = turma.value.trim(), d = m ? Number(m[1]) : 0;
            if (!cod || !t || !d) { status.textContent = "Preencha código, turma e departamento."; status.style.color = "var(--perigo)"; return; }
            assistente.disciplinas.push({ codigo: cod, turma: t, departamento: d });
            status.style.color = "var(--sucesso)";
            status.textContent = `${cod}-${t} adicionada! Total: ${estadoApp.estado.qtd_disciplinas + assistente.disciplinas.length}.`;
            codigo.value = ""; turma.value = "";
          } }, "➕ Adicionar disciplina"), status);
        break;
      }
      case 3:
        c.append(h("h2", { id: "assistente-titulo" }, "3. Modo de operação"),
          h("p", { class: "texto-suave" }, "Pode mudar isso a qualquer momento na aba Execução."),
          h("div", { class: "opcoes-modo" },
            h("label", { class: "opcao-modo" }, h("input", { type: "radio", name: "a_modo", value: "matricula", checked: assistente.modo === "matricula" }),
              h("span", { class: "opcao-conteudo" }, h("strong", {}, "Matrícula automática"), h("span", {}, "Tenta se matricular assim que achar vaga."))),
            h("label", { class: "opcao-modo" }, h("input", { type: "radio", name: "a_modo", value: "monitoramento", checked: assistente.modo === "monitoramento" }),
              h("span", { class: "opcao-conteudo" }, h("strong", {}, "Somente monitoramento"), h("span", {}, "Só avisa, nunca matricula sozinho.")))));
        break;
      case 4:
        c.append(h("h2", { id: "assistente-titulo" }, "4. Notificações (opcional)"),
          h("p", { class: "texto-suave" }, "Totalmente opcional — o programa funciona normalmente sem nenhuma. Configure em detalhes na aba Notificações depois, se quiser."),
          h("p", {}, "Disponíveis: Telegram, ntfy e alarme sonoro local."));
        break;
      default: {
        const preenchidas = ["usuario", "senha", "cpf", "nascimento"].every((k) => (cr[k] || "").trim()) || estadoApp.estado.credenciais_preenchidas;
        c.append(h("h2", { id: "assistente-titulo" }, "Tudo pronto!"),
          h("ul", {}, h("li", {}, `Credenciais: ${preenchidas ? "preenchidas" : "não preenchidas ainda"}`),
            h("li", {}, `Disciplinas cadastradas: ${estadoApp.estado.qtd_disciplinas + assistente.disciplinas.length}`),
            h("li", {}, `Modo: ${assistente.modo === "matricula" ? "Matrícula automática" : "Somente monitoramento"}`)),
          h("p", { class: "texto-suave" }, "Clique em Finalizar para começar a usar o programa."));
      }
    }
    const primeiro = $("input", c); if (primeiro) primeiro.focus();
  }
  async function finalizarAssistente() {
    salvarEtapaAtual();
    const r = await acao("POST", "/api/assistente/finalizar", { credenciais: assistente.credenciais, disciplinas: assistente.disciplinas, modo: assistente.modo });
    $("#dialogo-assistente").close();
    if (r) { recarregarTudo(); toast("Configuração inicial salva.", "sucesso"); }
  }
  function abrirAssistente() {
    assistente.modo = (estadoApp.estado && estadoApp.estado.modo) || "monitoramento";
    renderAssistente();
    const dlg = $("#dialogo-assistente");
    dlg.oncancel = (ev) => { ev.preventDefault(); finalizarAssistente(); };
    dlg.showModal();
  }
  $("#form-assistente").addEventListener("submit", (ev) => {
    ev.preventDefault();
    salvarEtapaAtual();
    if (assistente.etapa === ETAPAS.length - 1) { finalizarAssistente(); return; }
    assistente.etapa++; renderAssistente();
  });
  $("#assistente-voltar").addEventListener("click", () => { salvarEtapaAtual(); if (assistente.etapa > 0) { assistente.etapa--; renderAssistente(); } });
  $("#assistente-pular").addEventListener("click", finalizarAssistente);

  // ── Inicialização ────────────────────────────────────────────────────
  async function recarregarTudo() {
    await atualizarEstado();
    if (estadoApp.estado) preencherExecucao(estadoApp.estado);
    const t = estadoApp.telaAtual;
    if (t && CARREGADORES[t] && t !== "ajuda") CARREGADORES[t]();
  }

  function mostrarFaixaEncerramento(marcador) {
    const faixa = h("div", { class: "alerta alerta-aviso faixa", role: "alert" },
      h("div", {}, h("strong", {}, "⚠️ Execução anterior não finalizada normalmente"),
        h("p", {}, `A execução anterior do motor (iniciada em ${marcador.inicio || "?"}, modo: ${marcador.modo || "?"}) não foi encerrada de forma controlada — o programa pode ter sido fechado abruptamente ou travado.`),
        h("p", {}, "Isso NÃO significa que uma matrícula foi confirmada. Se tiver dúvida, verifique manualmente no SIGAA.")),
      h("span", { class: "espaco" }),
      h("button", { type: "button", class: "botao botao-secundario botao-pequeno", onclick: () => faixa.remove() }, "Entendi"));
    $("#faixas").append(faixa);
  }

  let aplicacaoIniciada = false;
  async function iniciarAplicacao() {
    if (aplicacaoIniciada) { await recarregarTudo(); return; }
    aplicacaoIniciada = true;
    $("#tela-bloqueio").hidden = true;
    $("#app").hidden = false;
    await atualizarEstado();
    const est = estadoApp.estado;
    preencherExecucao(est);
    if (est.encerramento_anterior) mostrarFaixaEncerramento(est.encerramento_anterior);
    irPara(location.hash.replace("#/", "") || "execucao");
    estadoApp.timers.push(setInterval(atualizarEstado, 2000));
    estadoApp.timers.push(setInterval(atualizarDashboard, 1000));
    estadoApp.timers.push(setInterval(() => atualizarLogs(false), 1500));
    if (est.primeira_execucao) abrirAssistente();
  }

  async function boot() {
    let est;
    try { est = await api("GET", "/api/estado"); } catch (e) { return; }
    estadoApp.estado = est;
    estadoApp.ajuda = est.ajuda || {};
    if (est.aviso_aceito) iniciarAplicacao();
    else exigirAviso();
  }
  boot();
})();
