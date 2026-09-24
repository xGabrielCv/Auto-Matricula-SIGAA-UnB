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
    registrarNotificacao(mensagem, tipo);
    const icone = { sucesso: "✅", aviso: "⚠️", erro: "❌", info: "ℹ️" }[tipo] || "ℹ️";
    const el = h("div", { class: `toast toast-${tipo}`, role: tipo === "erro" ? "alert" : "status" },
      h("span", { "aria-hidden": "true" }, icone), h("span", {}, mensagem),
      h("button", { type: "button", "aria-label": "Fechar aviso", onclick: () => el.remove() }, "×"));
    const pilha = $("#toasts");
    pilha.append(el);
    while (pilha.children.length > 4) pilha.firstElementChild.remove();
    if (ms) setTimeout(() => el.remove(), ms);
  }

  // ── Central de notificações (sugestão 088) ───────────────────────────
  // Histórico dos avisos desta sessão da página: toasts somem em segundos
  // (no máximo 4 na tela), e um aviso importante podia passar despercebido.
  const central = { itens: [], naoLidas: 0, ultimoSeqServidor: null };
  function registrarNotificacao(mensagem, tipo) {
    central.itens.unshift({ mensagem, tipo, hora: new Date().toLocaleTimeString("pt-BR"), lida: false });
    if (central.itens.length > 100) central.itens.length = 100;
    central.naoLidas = Math.min(central.naoLidas + 1, central.itens.length);
    atualizarSino();
    if ($("#dialogo-central").open) renderCentral();
  }
  function atualizarSino() {
    const cont = $("#sino-contador");
    cont.hidden = central.naoLidas === 0;
    cont.textContent = central.naoLidas > 9 ? "9+" : String(central.naoLidas);
    $("#botao-sino").setAttribute("aria-label", central.naoLidas ? `Central de notificações — ${central.naoLidas} não lida(s)` : "Central de notificações");
  }
  function renderCentral() {
    const ul = limpar($("#central-lista"));
    central.itens.forEach((n) => ul.append(h("li", { class: `nivel-${n.tipo}${n.lida ? "" : " nao-lida"}` },
      h("span", { class: "hora" }, n.hora), h("span", {}, n.mensagem))));
    $("#central-vazio").hidden = central.itens.length > 0;
  }
  function abrirCentral() {
    renderCentral();
    const dlg = $("#dialogo-central");
    if (!dlg.open) dlg.showModal();
    // Abrir a central conta como "ler": zera o contador (a lista ainda destaca o que era novo).
    central.itens.forEach((n) => { n.lida = true; });
    central.naoLidas = 0;
    atualizarSino();
  }
  $("#botao-sino").addEventListener("click", abrirCentral);
  $("#central-fechar").addEventListener("click", () => $("#dialogo-central").close());
  $("#central-limpar").addEventListener("click", () => { central.itens = []; central.naoLidas = 0; atualizarSino(); renderCentral(); });

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

  // Reconexão resiliente (sugestão 004): uma falha momentânea (PC sob carga,
  // antivírus inspecionando a conexão…) não bloqueia mais a página na hora.
  // Só depois de várias tentativas sem resposta a interface é dada como encerrada.
  const conexao = { reconectando: false };
  const ESPERAS_RECONEXAO_MS = [1000, 2000, 3000, 5000, 8000];
  const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

  function perdeuConexao() {
    if (estadoApp.encerrado || conexao.reconectando) return;
    conexao.reconectando = true;
    $("#faixa-conexao").hidden = false;
    tentarReconectar(0);
  }
  async function tentarReconectar(i) {
    if (estadoApp.encerrado || !conexao.reconectando) return;
    if (i >= ESPERAS_RECONEXAO_MS.length) {
      conexao.reconectando = false;
      $("#faixa-conexao").hidden = true;
      servidorIndisponivel();
      return;
    }
    $("#faixa-conexao-texto").textContent =
      `Sem resposta do SIGAA Sniper — reconectando (tentativa ${i + 1} de ${ESPERAS_RECONEXAO_MS.length})… A execução, se houver, continua no programa.`;
    await esperar(ESPERAS_RECONEXAO_MS[i]);
    if (!conexao.reconectando) return; // outra chamada já reconectou
    try {
      const r = await fetch("/api/estado", { cache: "no-store", credentials: "same-origin", headers: { "X-Requested-With": "SIGAA-Sniper" } });
      if (r.status === 401) { conexao.reconectando = false; $("#faixa-conexao").hidden = true; acessoNegado(); return; }
      conexaoRestabelecida();
    } catch (e) {
      tentarReconectar(i + 1);
    }
  }
  function conexaoRestabelecida() {
    if (!conexao.reconectando) return;
    conexao.reconectando = false;
    $("#faixa-conexao").hidden = true;
    toast("Conexão com o SIGAA Sniper restabelecida.", "sucesso");
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
      perdeuConexao();
      throw new ErroHttp(0, { erro: "Sem conexão com o SIGAA Sniper no momento — tentando reconectar." });
    }
    if (conexao.reconectando) conexaoRestabelecida();
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
      "Não há mais conexão com o SIGAA Sniper — a Interface Web foi encerrada no terminal ou o programa foi fechado (a página tentou reconectar por alguns segundos).",
      "Para usar de novo, abra o programa e escolha a opção [0] 🌐 Interface Web no menu.");
  }
  function acessoNegado() {
    bloquear("🔒 Acesso não autorizado",
      "Esta página não tem a chave de acesso desta execução (ela muda sempre que a Interface Web é aberta).",
      "Se você reabriu o programa, volte ao terminal do SIGAA Sniper e abra o NOVO link completo exibido lá.");
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
  // ── 087: preferências de exibição (só neste navegador) ─────────────
  const EXIBICAO_PADRAO = { densidade: "confortavel", fonte: 100 };
  function lerExibicao() {
    try { return { ...EXIBICAO_PADRAO, ...JSON.parse(localStorage.getItem("sniper-exibicao") || "{}") }; } catch (e) { return { ...EXIBICAO_PADRAO }; }
  }
  function aplicarExibicao(p) {
    document.documentElement.dataset.densidade = p.densidade;
    document.documentElement.style.setProperty("--escala-fonte", String((Number(p.fonte) || 100) / 100));
  }
  aplicarExibicao(lerExibicao());
  function abrirExibicao() {
    const p = lerExibicao();
    const opcoes = (nome, lista, atual) => h("div", { class: "segmentado", role: "group", "aria-label": nome },
      lista.map(([valor, rotulo]) => h("button", { type: "button", "aria-pressed": String(String(atual) === String(valor)), "data-valor": valor,
        onclick: (ev) => {
          ev.currentTarget.parentElement.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === ev.currentTarget)));
          p[nome === "Densidade" ? "densidade" : "fonte"] = valor;
          aplicarExibicao(p);
          try { localStorage.setItem("sniper-exibicao", JSON.stringify(p)); } catch (e2) { /* só nesta sessão */ }
        } }, rotulo)));
    dialogo({ titulo: "🔠 Exibição", nos: h("div", { class: "formulario" },
      h("p", { class: "texto-suave" }, "Vale só neste navegador. O tema claro/escuro fica no botão 🌓 Tema."),
      h("span", { class: "rotulo-visivel" }, "Densidade"),
      opcoes("Densidade", [["confortavel", "Confortável"], ["compacta", "Compacta (mais linhas por tela)"]], p.densidade),
      h("span", { class: "rotulo-visivel" }, "Tamanho do texto"),
      opcoes("Tamanho do texto", [[90, "90%"], [100, "100%"], [115, "115%"], [130, "130%"]], p.fonte)) });
  }
  $("#botao-exibicao").addEventListener("click", abrirExibicao);

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
      processarEventosServidor(est.eventos || []);
    } catch (e) { /* tratado em api() */ }
  }

  /** Eventos do motor (vaga, matrícula, fim da execução) chegam pelo /api/estado
   *  em qualquer tela — antes só o Dashboard mostrava vagas, e só se estivesse aberto. */
  function processarEventosServidor(eventos) {
    if (central.ultimoSeqServidor === null) {
      // Primeira leitura: o que aconteceu antes de a página abrir entra como histórico, sem alarde.
      eventos.forEach((ev) => central.itens.unshift({ mensagem: ev.texto, tipo: ev.nivel, hora: ev.hora, lida: true }));
      central.ultimoSeqServidor = eventos.length ? eventos[eventos.length - 1].seq : 0;
      return;
    }
    eventos.filter((ev) => ev.seq > central.ultimoSeqServidor).forEach((ev) => {
      central.ultimoSeqServidor = ev.seq;
      toast(ev.texto, ev.nivel, ev.tipo === "vaga_detectada" || ev.tipo === "matricula_sucesso" ? 12000 : 7000);
      // 084: o que exige atenção imediata também é anunciado na hora por leitores de tela.
      if (["vaga_detectada", "matricula_sucesso", "parada_seguranca"].includes(ev.tipo) || ev.nivel === "erro"
          || (ev.tipo === "alerta_limiar" && ev.nivel === "aviso")) $("#anuncio-urgente").textContent = ev.texto;
    });
  }

  function renderStatus(exec) {
    const caixa = $("#status-execucao");
    const estado = exec.em_execucao ? (exec.estado === "parando" ? "parando" : exec.pausado ? "pausado" : "executando") : (exec.estado === "erro" ? "erro" : "parado");
    caixa.dataset.estado = estado;
    const texto = { executando: exec.mensagem.replace("Em execução — ", "Em execução · "), parando: "Parando…", erro: "Encerrado com erro", parado: "Parado",
      pausado: exec.motivo_pausa === "janela" ? "Pausado · fora da janela" : "Pausado" }[estado];
    $(".status-texto", caixa).textContent = texto;
    caixa.title = exec.mensagem;
    const rodando = exec.em_execucao;
    $("#botao-iniciar").disabled = rodando;
    $("#botao-parar").disabled = !rodando || exec.estado === "parando";
    const botaoPausa = $("#botao-pausar");
    botaoPausa.disabled = !rodando || exec.estado === "parando" || exec.motivo_pausa === "janela";
    botaoPausa.textContent = exec.pausado ? "▶️ Retomar" : "⏸️ Pausar";
    botaoPausa.dataset.acao = exec.pausado ? "retomar" : "pausar";
    const dashPausa = $("#dash-pausar");
    dashPausa.hidden = !rodando || exec.motivo_pausa === "janela";
    dashPausa.textContent = exec.pausado ? "▶️ Retomar" : "⏸️ Pausar";
    dashPausa.dataset.acao = botaoPausa.dataset.acao;
    $$("#tela-execucao input").forEach((i) => { i.disabled = rodando; });
    $("#exec-agendar-limpar").disabled = rodando;
    $("#exec-fim-limpar").disabled = rodando;
    $("#selo-demo").hidden = !(exec.demo && rodando);
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
    const problemasCred = est.problemas_credenciais || [];
    if ($("#exec-demo").checked) item(null, "Demonstração: credenciais fictícias, SIGAA simulado e DRY RUN sempre ligado.", null, null);
    else if (est.credenciais_preenchidas && problemasCred.length) item(false, `Credenciais com problema: ${problemasCred.join(" ")}`, "credenciais", "Corrigir");
    else item(est.credenciais_preenchidas, est.credenciais_preenchidas ? "Credenciais do SIGAA preenchidas (só em memória)." : "Credenciais do SIGAA não preenchidas.", "credenciais", est.credenciais_preenchidas ? "Revisar" : "Preencher");
    item(est.qtd_disciplinas_ativas > 0, `${est.qtd_disciplinas_ativas} disciplina(s) ativa(s) de ${est.qtd_disciplinas} cadastrada(s).`, "disciplinas", "Gerenciar");
    if (est.carga && est.carga.req_por_seg !== null) {
      item(est.carga.nivel === "alta" ? false : null, est.carga.alerta || `Carga estimada: ${est.carga.texto}`, "avancado", "Ajustar");
    }
    (est.alertas_seguranca || []).forEach((a) => item(a.nivel === "risco" ? false : null, `${a.titulo}: ${a.acao}`,
      a.tela || "diagnostico", "Ver"));
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
    $("#exec-fim").value = paraDatetimeLocal(est.agendar_fim);
    const j = est.janela || {};
    $("#exec-janela-ativa").checked = !!j.ativa;
    $("#exec-janela-inicio").value = j.inicio || "07:00";
    $("#exec-janela-fim").value = j.fim || "23:00";
    const dias = limpar($("#exec-janela-dias"));
    dias.append(h("legend", { class: "rotulo-visivel" }, "Dias"));
    ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"].forEach((nome, i) => dias.append(h("label", {},
      h("input", { type: "checkbox", value: String(i), checked: (j.dias || []).includes(i) }), nome)));
    $("#exec-relogio").checked = !!est.agendamento_relogio_sigaa;
    $("#exec-verificacao").checked = est.verificacao_previa !== false;
    if (j.ativa || est.agendamento_relogio_sigaa || est.verificacao_previa === false) $("#exec-mais").open = true;
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
  $("#exec-fim-limpar").addEventListener("click", () => { $("#exec-fim").value = ""; });
  async function alternarPausa(botao) {
    const acaoPausa = botao.dataset.acao === "retomar" ? "retomar" : "pausar";
    // O aviso vem do próprio motor (central de notificações) quando a pausa de fato acontece.
    const r = await acao("POST", `/api/execucao/${acaoPausa}`, {}, { botao });
    if (r) atualizarEstado();
  }
  $("#botao-pausar").addEventListener("click", (ev) => alternarPausa(ev.currentTarget));
  $("#dash-pausar").addEventListener("click", (ev) => alternarPausa(ev.currentTarget));

  $("#exec-demo").addEventListener("change", () => { if (estadoApp.estado) renderChecklist(estadoApp.estado); });
  // Sugestão 070: só interação de verdade (clique/tecla/rolagem) conta como atividade —
  // as consultas automáticas de estado não mantêm a sessão viva sozinhas.
  let ultimaAtividadeEnviada = 0;
  ["pointerdown", "keydown", "wheel"].forEach((tipo) => document.addEventListener(tipo, () => {
    if (Date.now() - ultimaAtividadeEnviada < 60000 || estadoApp.encerrado) return;
    ultimaAtividadeEnviada = Date.now();
    api("POST", "/api/atividade", {}).catch(() => {});
  }, { passive: true }));

  $("#botao-iniciar").addEventListener("click", async () => {
    const corpo = {
      modo: modoSelecionado(), dry_run: $("#exec-dry-run").checked, agendar_inicio: deDatetimeLocal($("#exec-agendar").value),
      agendar_fim: deDatetimeLocal($("#exec-fim").value),
      janela: { ativa: $("#exec-janela-ativa").checked, inicio: $("#exec-janela-inicio").value, fim: $("#exec-janela-fim").value,
        dias: $$("#exec-janela-dias input:checked").map((c) => Number(c.value)) },
      agendamento_relogio_sigaa: $("#exec-relogio").checked, verificacao_previa: $("#exec-verificacao").checked,
      demo: $("#exec-demo").checked,
    };
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

  // ── 📊 Dashboard / Centro de Operações (Fase 2) ──────────────────────
  // Com uma execução nesta sessão, os dados vêm direto do motor (`painel`):
  // estado de cada disciplina e worker, saúde com causa provável, erros por
  // tipo e séries para os gráficos. Sem execução, continua valendo o painel
  // calculado a partir do arquivo de log (execuções anteriores).
  const fmt = (v, suf = "", casas = 1) => (v === null || v === undefined ? null : `${Number(v).toFixed(casas)}${suf}`);
  const fmtMs = (v) => (v === null || v === undefined ? null : `${Math.round(v)} ms`);
  const G = window.Graficos;
  let historicoVagas = {};
  const dash = { aba: "geral", janela: 300, ultimo: null };
  const lt = { execucao: "", periodo: 0, ocultas: new Set(), dados: null, carregadoEm: 0, carregando: false };
  const SELO_SAUDE = { aguardando: "selo-neutro", estavel: "selo-sucesso", atencao: "selo-aviso", critico: "selo-perigo" };
  const ICONE_SAUDE = { aguardando: "⏳", estavel: "✅", atencao: "⚠️", critico: "📛" };
  const SELO_ESTADO_ALVO = {
    aguardando: "selo-neutro", buscando: "selo-neutro", sem_vagas: "selo-neutro", vaga: "selo-sucesso", tentando: "selo-aviso",
    matriculada: "selo-sucesso", simulada: "selo-sucesso", bloqueada: "selo-perigo", falha: "selo-aviso", departamento_indisponivel: "selo-perigo",
  };
  const CATEGORIAS_ERRO = ["timeout", "rede", "sessao", "departamento", "login", "critico", "confirmacao", "sobrecarga"];
  const ROTULOS_ERRO = { timeout: "Tempo esgotado", rede: "Falha de rede", sessao: "Sessão expirada", departamento: "Departamento indisponível",
    login: "Falha de login", critico: "Erro inesperado", confirmacao: "Falha na confirmação", sobrecarga: "SIGAA sobrecarregado" };
  const corErro = (cat) => CATEGORIAS_ERRO.indexOf(cat) + 1; // cor fixa por tipo de erro, nunca pela posição

  function relativo(ts, agora) {
    if (!ts) return "—";
    const d = Math.max(0, Math.round(agora - ts));
    return d < 60 ? `há ${d}s` : d < 3600 ? `há ${Math.floor(d / 60)} min` : `há ${Math.floor(d / 3600)} h`;
  }
  function duracao(seg) {
    if (seg === null || seg === undefined) return null;
    const s = Math.max(0, Math.floor(seg)), hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
    return hh ? `${hh}h ${mm}m ${ss}s` : `${mm}m ${ss}s`;
  }

  async function atualizarDashboard() {
    if (estadoApp.telaAtual !== "dashboard" || estadoApp.encerrado) return;
    const comSeries = dash.aba === "graficos";
    let m;
    try { m = await api("GET", `/api/dashboard${comSeries ? `?series=1&janela=${dash.janela}` : ""}`); } catch (e) { return; }
    historicoVagas = m.historico_vagas || {};
    const p = m.painel;
    dash.ultimo = m;
    renderSeloSaude(m, p);
    renderFase(p, m.execucao);
    renderCards(m, p);
    renderAlvos(p);
    renderSaudeDetalhe(p);
    renderErrosGrupos(p);

    const alerta = $("#dash-alerta");
    const alertas = p ? p.workers.filter((w) => w.estado !== "encerrado" && w.ocioso_seg > 30).map((w) => `${w.id} sem progresso há ${Math.round(w.ocioso_seg)}s (${w.estado_rotulo})`)
      : m.workers_com_alerta;
    alerta.hidden = !alertas.length;
    alerta.textContent = alertas.length ? `⚠ Possível problema detectado: ${alertas.join(" | ")}` : "";

    const listar = (sel, linhas, vazio) => {
      const ul = limpar($(sel));
      if (!linhas.length) ul.append(h("li", { class: "vazio" }, vazio));
      linhas.forEach((l) => ul.append(h("li", {}, l)));
    };
    const ativa = m.execucao_ativa || (p && p.fase && p.fase.fase !== "encerrado");
    listar("#dash-vagas", m.registro_vagas, ativa ? "Aguardando o surgimento de vagas…" : "Nenhuma execução em andamento.");
    listar("#dash-erros", m.log_erros, ativa ? "Nenhum erro até agora." : "Nenhuma execução em andamento.");
    renderWorkers(m, p);
    renderAlertasLimiar(p);
    renderTentativas(p);
    if (dash.aba === "tempo" && (Date.now() - lt.carregadoEm > 5000) && (!lt.execucao || !lt.dados || lt.execucao === (lt.dados.execucoes || [])[0])) carregarLinhaTempo();
    if (dash.aba === "graficos") renderGraficos(p);
    if (dash.aba === "workers") renderGraficoWorkers(p);
    renderStatus(m.execucao);
    $("#dash-parar").hidden = !m.execucao.em_execucao;
    $("#dash-parar").disabled = m.execucao.estado === "parando";
    $("#dash-ver-resumo").hidden = !(p && p.resumo);
  }

  // Fase 5: alertas por limiar ativos (058/090) e tentativas de matrícula rastreadas (059).
  function renderAlertasLimiar(p) {
    const ul = limpar($("#dash-alertas-limiar"));
    const ativos = p && p.alertas ? p.alertas.ativos : [];
    ul.hidden = !ativos.length;
    ativos.forEach((a) => ul.append(h("li", { class: "alerta alerta-aviso" },
      h("strong", {}, `🔔 ${a.titulo}`), " — ", a.texto, h("span", { class: "texto-suave" }, ` (${relativo(a.desde, p.agora)})`))));
  }
  const ROTULO_RESULTADO = { SUCESSO: "Sucesso", ERRO_REGRA: "Bloqueada pelo SIGAA", FALHA: "Falhou", ERRO: "Interrompida" };
  function textoEtapas(t) {
    return (t.etapas || []).map((e) => `${e.rotulo} ${fmtMs(e.ms)}`).join(" → ") || "—";
  }
  function renderTentativas(p) {
    const lista = p && p.tentativas ? p.tentativas.slice().reverse().slice(0, 10) : [];
    $("#dash-tentativas-cartao").hidden = !lista.length;
    const corpo = limpar($("#dash-tentativas"));
    lista.forEach((t) => {
      const resultado = t.resultado ? (ROTULO_RESULTADO[t.resultado] || t.resultado) + (t.dry_run && t.resultado === "SUCESSO" ? " (DRY RUN)" : "") : "Em andamento…";
      corpo.append(h("tr", {},
        h("td", {}, new Date(t.inicio * 1000).toLocaleTimeString("pt-BR")), h("td", {}, t.chave), h("td", {}, t.worker),
        h("td", {}, h("span", { class: `selo ${t.resultado === "SUCESSO" ? "selo-sucesso" : t.resultado ? "selo-perigo" : "selo-neutro"}` }, resultado)),
        h("td", { class: "num" }, t.desde_vaga_ms === undefined ? "—" : fmtMs(t.desde_vaga_ms)),
        h("td", {}, textoEtapas(t), t.dump ? h("span", { class: "texto-suave" }, " · página capturada") : null)));
    });
  }

  // ── 🕒 Linha do tempo (054) ─────────────────────────────────────────
  const dataLog = (ts) => { const d = new Date(String(ts).replace(" ", "T")); return Number.isNaN(d.getTime()) ? null : d; };
  async function carregarLinhaTempo() {
    if (lt.carregando) return;
    lt.carregando = true;
    if (!lt.dados) { limpar($("#lt-itens")); $("#lt-resumo").textContent = "Carregando a linha do tempo…"; }
    try {
      lt.dados = await api("GET", `/api/linha-do-tempo${lt.execucao ? `?execucao=${encodeURIComponent(lt.execucao)}` : ""}`);
      lt.carregadoEm = Date.now();
      renderLinhaTempo();
    } catch (e) { $("#lt-resumo").textContent = "Não foi possível carregar a linha do tempo agora."; }
    finally { lt.carregando = false; }
  }
  function renderLinhaTempo() {
    const d = lt.dados;
    if (!d) return;
    const sel = $("#lt-execucao");
    const opcoes = d.execucoes.map((id, i) => `${id}${i === 0 ? " (mais recente)" : ""}`);
    if (sel.options.length !== opcoes.length || [...sel.options].some((o, i) => o.textContent !== opcoes[i])) {
      limpar(sel);
      d.execucoes.forEach((id, i) => sel.append(h("option", { value: id }, opcoes[i])));
    }
    sel.value = d.execucao_id || "";
    sel.disabled = !d.execucoes.length;
    const chips = limpar($("#lt-categorias"));
    d.categorias.forEach((c) => chips.append(h("button", {
      type: "button", class: "chip", "aria-pressed": String(!lt.ocultas.has(c.id)), "data-categoria": c.id,
      onclick: () => { if (lt.ocultas.has(c.id)) lt.ocultas.delete(c.id); else lt.ocultas.add(c.id); renderLinhaTempo(); },
    }, `${c.rotulo} `, h("span", { class: "chip-contagem" }, String(c.total)))));
    const ultimo = d.itens.length ? dataLog(d.itens[d.itens.length - 1].fim) : null;
    const itens = d.itens.filter((i) => !lt.ocultas.has(i.categoria)
      && (!lt.periodo || !ultimo || (dataLog(i.fim) || ultimo) >= new Date(ultimo.getTime() - lt.periodo * 1000)));
    const ol = limpar($("#lt-itens"));
    const vazio = $("#lt-vazio");
    vazio.hidden = !!itens.length;
    vazio.textContent = !d.itens.length
      ? "Nenhum evento marcante ainda. Inicie uma execução — início, logins, vagas, tentativas e erros aparecem aqui."
      : "Nenhum evento com os filtros escolhidos.";
    $("#lt-resumo").textContent = d.itens.length
      ? `${itens.length} de ${d.itens.length} evento(s) marcante(s) da execução ${d.execucao_id}. As buscas sem vaga ficam de fora.`
      : "";
    const tentativas = Object.fromEntries((d.tentativas || []).map((t) => [t.id, t]));
    let anterior = null;
    itens.forEach((i) => {
      const quando = dataLog(i.inicio);
      if (anterior && quando && quando - anterior > 5 * 60 * 1000) {
        ol.append(h("li", { class: "lt-intervalo", "aria-hidden": "true" }, `… ${duracao((quando - anterior) / 1000)} sem eventos marcantes …`));
      }
      anterior = dataLog(i.fim) || quando;
      const t = i.tentativa_id ? tentativas[i.tentativa_id] : null;
      ol.append(h("li", { class: `lt-item lt-${i.nivel} lt-cat-${i.categoria}` },
        h("span", { class: "lt-hora" }, i.hora, i.hora_fim ? h("span", { class: "texto-suave" }, `–${i.hora_fim}`) : null),
        h("span", { class: "lt-marca", "aria-hidden": "true" }),
        h("div", { class: "lt-corpo" },
          h("div", { class: "lt-titulo" }, i.titulo, i.quantidade > 1 ? h("span", { class: "selo selo-neutro selo-espacado" }, `×${i.quantidade}`) : null,
            i.nivel !== "info" ? h("span", { class: "visualmente-oculto" }, ` (${i.nivel})`) : null),
          h("div", { class: "lt-detalhe" }, i.detalhe),
          h("div", { class: "lt-meta" }, [i.worker && i.worker !== "MAIN" ? i.worker : null, i.tentativa_id ? `tentativa ${i.tentativa_id}` : null].filter(Boolean).join(" · ")),
          t && i.evento === "tentativa_concluida" ? h("button", { type: "button", class: "botao botao-fantasma botao-pequeno", onclick: () => mostrarTentativa(t) }, "Ver etapas") : null)));
    });
  }
  function mostrarTentativa(t) {
    let antes = 0;
    const linhas = (t.etapas || []).map((e) => { const passo = e.ms - antes; antes = e.ms; return h("tr", {}, h("td", {}, e.rotulo), h("td", { class: "num" }, fmtMs(e.ms)), h("td", { class: "num" }, `+${fmtMs(passo)}`)); });
    dialogo({ titulo: `Tentativa ${t.id} — ${t.chave}`, nos: h("div", {},
      h("p", {}, `Resultado: ${ROTULO_RESULTADO[t.resultado] || t.resultado || "em andamento"} · ${t.worker} · da vaga vista ao resultado: ${t.desde_vaga_ms === undefined ? "—" : fmtMs(t.desde_vaga_ms)}`),
      h("table", { class: "tabela" }, h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Etapa"), h("th", { scope: "col", class: "num" }, "Desde o início"), h("th", { scope: "col", class: "num" }, "Duração"))),
        h("tbody", {}, linhas)),
      t.dump ? h("p", { class: "dica" }, `Página capturada: ${t.dump} (veja em Diagnóstico → Páginas capturadas).`) : null) });
  }
  $("#lt-execucao").addEventListener("change", (ev) => { lt.execucao = ev.target.value; lt.dados = null; carregarLinhaTempo(); });
  $("#lt-atualizar").addEventListener("click", () => carregarLinhaTempo());
  $$("#lt-periodo button").forEach((b) => b.addEventListener("click", () => {
    lt.periodo = Number(b.dataset.periodo);
    $$("#lt-periodo button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    renderLinhaTempo();
  }));

  function renderSeloSaude(m, p) {
    const selo = $("#dash-saude");
    if (p) {
      const s = p.saude;
      selo.className = `selo ${SELO_SAUDE[s.nivel] || "selo-neutro"}`;
      selo.textContent = `${ICONE_SAUDE[s.nivel] || ""} ${s.titulo}`;
      selo.title = s.causa;
      return;
    }
    // Sem execução nesta sessão: nunca exibir "saúde" de uma execução que não está rodando.
    if (!m.execucao_ativa) {
      selo.className = "selo selo-neutro";
      selo.textContent = m.recuperado ? "📂 Última execução (recuperada)" : "⚪ Nenhuma execução em andamento";
      selo.title = "";
      return;
    }
    const legado = { aguardando_trafego: ["Aguardando tráfego", "selo-neutro"], estavel: ["✅ Sistema estável", "selo-sucesso"],
      degradado: ["⚠️ Degradado", "selo-aviso"], critico: ["📛 Crítico", "selo-perigo"] }[m.saude.status] || ["—", "selo-neutro"];
    selo.className = `selo ${legado[1]}`;
    selo.textContent = legado[0] + (m.saude.taxa_erro !== null && !["estavel", "aguardando_trafego"].includes(m.saude.status) ? ` (erros: ${Math.round(m.saude.taxa_erro * 100)}%)` : "");
    selo.title = "";
  }

  function renderFase(p, exec) {
    const fase = $("#dash-fase"), barra = $("#dash-progresso");
    if (!p) {
      barra.hidden = true;
      fase.textContent = exec.em_execucao ? "" : (dash.ultimo && dash.ultimo.recuperado
        ? "Mostrando dados recuperados da última execução (já encerrada). Nenhuma execução em andamento."
        : "Nenhuma execução em andamento. O painel começa a se mover quando você iniciar uma execução.");
      return;
    }
    let texto = p.fase.texto;
    if (p.fase.fase === "monitorando" && p.inicio) texto += ` Rodando há ${duracao(p.agora - p.inicio)}.`;
    if (p.fase.fase === "encerrado" && !exec.em_execucao) texto = "Última execução encerrada — veja o resumo.";
    fase.textContent = texto;
    barra.hidden = p.fase.progresso === null || p.fase.progresso === undefined;
    if (!barra.hidden) $("#dash-progresso-valor").style.width = `${Math.round(p.fase.progresso * 100)}%`;
  }

  function renderCards(m, p) {
    const grade = limpar($("#dash-cards"));
    const card = (rotulo, valor, spark, dica) => {
      const semDados = valor === null || valor === undefined;
      const tend = spark ? G.tendencia(spark.valores) : null;
      grade.append(h("div", { class: "card-metrica", title: dica || null },
        h("div", { class: "rotulo" }, rotulo),
        h("div", { class: "linha-valor" },
          h("div", { class: `valor${semDados ? " sem-dados" : ""}` }, semDados ? "sem dados" : valor),
          spark ? G.sparkline(spark.valores, spark.rotulo) : null),
        tend ? h("div", { class: "tendencia" }, { subindo: "↑ subindo no último minuto", caindo: "↓ caindo no último minuto", estavel: "→ estável no último minuto" }[tend]) : null));
    };
    if (p) {
      const ativos = p.workers.filter((w) => w.estado !== "encerrado").length;
      const erros = p.erros_agrupados.reduce((s, e) => s + e.total, 0);
      card("Buscas por segundo", fmt(p.rps_atual, "/s"), { valores: p.sparks.rps, rotulo: "Tendência de buscas por segundo" });
      card("Tempo de resposta", fmtMs(p.latencia.recente), { valores: p.sparks.p50, rotulo: "Tendência do tempo de resposta" }, "Média das últimas 100 respostas");
      card("Vagas vistas", String(p.vagas_vistas), null, "Leituras em que o SIGAA mostrou vaga");
      card("Total de buscas", String(p.requisicoes));
      card("Tempo rodando", p.inicio ? duracao((p.fim || p.agora) - p.inicio) : null);
      card("Mín / máx", p.latencia.min === null ? null : `${fmtMs(p.latencia.min)} / ${fmtMs(p.latencia.max)}`);
      card("Erros", String(erros));
      card("Workers ativos", `${ativos} de ${p.workers.length || "—"}`);
      return;
    }
    if (!m.execucao_ativa) {
      if (!m.recuperado) {
        grade.append(h("p", { class: "vazio" }, "Nenhuma execução em andamento — os números aparecem quando você iniciar uma. Execuções anteriores ficam na tela Histórico."));
        return;
      }
      [["Buscas (última execução)", String(m.total_buscas)], ["Vagas encontradas", String(m.vagas_encontradas)],
        ["Duração da última execução", m.uptime === "sem dados" ? null : m.uptime], ["Tempo médio de resposta", fmtMs(m.latencia_media_ms)],
        ["Erros", String(m.erros_totais)]].forEach(([r, v]) => card(r, v));
      return;
    }
    [["Requisições/s", fmt(m.rps_atual, " req/s")], ["Buscas/s", fmt(m.bps_atual, " bps")],
      ["Latência (últ. 100)", fmtMs(m.latencia_recente_ms)], ["Total de buscas", String(m.total_buscas)],
      ["Vagas encontradas", String(m.vagas_encontradas)], ["Tempo rodando", m.uptime === "sem dados" ? null : m.uptime],
      ["Média histórica", fmt(m.avg_rps, " req/s")],
      ["Latência mín / máx", m.latencia_min_ms === null ? null : `${fmtMs(m.latencia_min_ms)} / ${fmtMs(m.latencia_max_ms)}`],
      ["Total de requisições", `${m.total_reqs}${m.total_reqs_falha_rede ? ` (${m.total_reqs_falha_rede} c/ falha)` : ""}`],
    ].forEach(([r, v]) => card(r, v));
  }

  function renderAlvos(p) {
    const grade = limpar($("#dash-alvos"));
    $("#dash-alvos-vazio").hidden = !!(p && p.alvos.length);
    if (!p) return;
    p.alvos.forEach((a) => {
      const vagas = a.vagas === null || a.vagas === undefined ? "—" : String(a.vagas);
      grade.append(h("article", { class: `cartao-alvo estado-${a.estado}`, "aria-label": `${a.chave}: ${a.estado_rotulo}` },
        h("div", { class: "topo-alvo" }, h("span", { class: "codigo" }, a.chave),
          h("span", { class: `selo ${SELO_ESTADO_ALVO[a.estado] || "selo-neutro"}` }, a.estado_rotulo)),
        h("div", {}, h("span", { class: "vagas-grande" }, vagas), h("span", { class: "texto-suave" }, " vaga(s) na última leitura")),
        h("div", { class: "meta-alvo" }, `Última leitura ${a.ultima_leitura_txt} · ${a.buscas} busca(s) · vaga vista ${a.vagas_vistas}x`
          + (a.tentativas ? ` · ${a.tentativas} tentativa(s)` : "")),
        h("div", { class: "meta-alvo" }, `Neste estado ${a.desde_txt}`
          + (a.grupo ? ` · grupo ${a.grupo}` : "") + (a.prioridade && a.prioridade !== "normal" ? ` · prioridade ${a.prioridade}` : "")),
        a.verificacao ? h("div", { class: `verificacao-alvo${a.verificacao.resultado === "ok" ? "" : " problema"}` },
          `Verificação prévia: ${a.verificacao.texto}`) : null));
    });
  }

  function renderSaudeDetalhe(p) {
    const causa = $("#dash-saude-causa"), dl = limpar($("#dash-saude-indicadores"));
    if (!p) { causa.textContent = "Inicie uma execução para ver a saúde da conexão com o SIGAA."; return; }
    causa.textContent = p.saude.causa;
    const i = p.saude.indicadores;
    const taxa = i.taxa_erro === null || i.taxa_erro === undefined ? "—" : `${Math.round(i.taxa_erro * 100)}%`;
    [["Resposta agora", fmtMs(i.latencia_recente_ms) || "—"], ["Resposta típica", fmtMs(i.latencia_mediana_ms) || "—"],
      [`Taxa de erro (${i.janela_seg}s)`, taxa], ["Tempos esgotados", String(i.timeouts)], ["Sessões expiradas", String(i.sessoes_expiradas)],
      ["Novos logins", String(i.relogins)], ["Falhas de rede", String(i.falhas_rede)],
      ["Memória do programa", i.memoria_mb === null || i.memoria_mb === undefined ? "—" : `${Math.round(i.memoria_mb)} MB`],
    ].forEach(([rotulo, valor]) => dl.append(h("div", {}, h("dt", {}, rotulo), h("dd", {}, valor))));
  }

  function renderErrosGrupos(p) {
    const corpo = limpar($("#dash-erros-grupos"));
    const grupos = p ? p.erros_agrupados : [];
    $("#dash-erros-grupos-vazio").hidden = grupos.length > 0;
    grupos.forEach((g) => corpo.append(h("tr", {},
      h("td", {}, h("strong", {}, g.rotulo)), h("td", { class: "num" }, `${g.total} (${g.percentual}%)`),
      h("td", {}, relativo(g.ultima, p.agora)), h("td", { class: "texto-suave" }, g.acao))));
  }

  function renderWorkers(m, p) {
    const ordem = (id) => { const x = /^W(\d+)$/.exec(id); return x ? Number(x[1]) : 9999; };
    const corpo = limpar($("#dash-workers"));
    if (p) {
      [...p.workers].sort((a, b) => ordem(a.id) - ordem(b.id)).forEach((w) => {
        const c = w.contadores;
        const erros = (c.timeouts || 0) + (c.falhas_rede || 0) + (c.sessoes_expiradas || 0) + (c.erros_criticos || 0);
        corpo.append(h("tr", {}, h("td", {}, h("strong", {}, w.id)), h("td", {}, w.estado_rotulo), h("td", {}, w.alvo || "—"),
          h("td", { class: "num" }, String(c.buscas || 0)), h("td", { class: `num${erros ? " lat-vermelho" : ""}` }, String(erros)),
          h("td", { class: "num" }, String(c.relogins || 0)), h("td", { class: "num" }, w.latencia_ms !== null ? `${w.latencia_ms} ms` : "–"),
          h("td", { class: `num${w.estado !== "encerrado" && w.ocioso_seg > 30 ? " lat-vermelho" : ""}` }, w.estado === "encerrado" ? "—" : `${w.ocioso_seg.toFixed(1)}s`)));
      });
      $("#dash-workers-vazio").hidden = p.workers.length > 0;
      return;
    }
    m.workers.sort((a, b) => ordem(a.id) - ordem(b.id)).forEach((w) => corpo.append(h("tr", {},
      h("td", {}, h("strong", {}, w.id)), h("td", {}, "—"), h("td", {}, w.ultima_acao),
      h("td", { class: "num" }, String(w.buscas)), h("td", { class: `num${w.erros ? " lat-vermelho" : ""}` }, String(w.erros)),
      h("td", { class: "num" }, "—"), h("td", { class: `num lat-${w.cor_latencia || ""}` }, w.latencia ? `${w.latencia} ms` : "–"),
      h("td", { class: `num${w.ocioso_seg !== null && w.ocioso_seg > 5 ? " lat-vermelho" : ""}` },
        w.ocioso_seg === null ? "—" : `${w.ocioso_seg.toFixed(1)}s`))));
    $("#dash-workers-vazio").hidden = m.workers.length > 0;
  }

  function renderGraficos(p) {
    const figs = ["#graf-latencia", "#graf-rps", "#graf-vagas", "#graf-erros", "#graf-histograma"].map((s) => $(s));
    if (!p || !p.series) { figs.forEach((f) => G.vazio(f, "Os gráficos aparecem quando houver uma execução nesta sessão.")); $("#dash-graficos-nota").textContent = ""; return; }
    const s = p.series;
    $("#dash-graficos-nota").textContent = s.balde_seg > 1 ? `Cada ponto resume ${s.balde_seg} s.` : "";
    const inicio = dash.janela ? Math.max(p.inicio || 0, p.agora - dash.janela) : p.inicio;
    const fim = p.fim || p.agora;
    const pontos = (valores) => s.t.map((t, i) => [t, valores[i]]);
    G.serieTempo($("#graf-latencia"), { tipo: "linha", inicio, fim, formatar: (v) => `${Math.round(v)} ms`, vazio: "Ainda não há respostas neste período.",
      series: [{ nome: "Mediana (p50)", cor: 1, pontos: pontos(s.p50) }, { nome: "95º percentil (p95)", cor: 2, pontos: pontos(s.p95) }] });
    G.serieTempo($("#graf-rps"), { tipo: "linha", inicio, fim, formatar: (v) => `${G.numero(v, 1)}/s`, vazio: "Nenhuma busca neste período.",
      series: [{ nome: "Buscas por segundo", cor: 1, pontos: pontos(s.rps) }] });
    const seriesVagas = p.alvos.slice(0, 7).map((a, i) => ({ nome: a.chave, cor: i + 1, pontos: (p.vagas_series[a.chave] || []) }));
    G.serieTempo($("#graf-vagas"), { tipo: "degrau", inicio, fim, formatar: (v) => `${v} vaga(s)`, vazio: "Nenhuma leitura de vagas neste período.",
      series: seriesVagas });
    if (p.alvos.length > 7) $("#dash-graficos-nota").textContent += " O gráfico de vagas mostra as 7 primeiras disciplinas.";
    const categorias = CATEGORIAS_ERRO.filter((c) => s.erros[c].some((v) => v > 0));
    G.serieTempo($("#graf-erros"), { tipo: "empilhado", inicio, fim, formatar: (v) => `${v}`, vazio: "Nenhum erro neste período.",
      series: categorias.map((c) => ({ nome: ROTULOS_ERRO[c], cor: corErro(c), pontos: pontos(s.erros[c]) })) });
    const lim = p.histograma.limites_ms;
    const faixas = lim.map((l, i) => (i === 0 ? `<${l}` : `${lim[i - 1]}–${l}`)).concat([`≥${lim[lim.length - 1]}`]);
    G.barras($("#graf-histograma"), { categorias: faixas, tituloCategoria: "Faixa (ms)", vazio: "Ainda não há respostas medidas.",
      series: [{ nome: "Respostas", cor: 1, valores: p.histograma.contagens }], formatar: (v) => G.numero(v) });
  }

  function renderGraficoWorkers(p) {
    const fig = $("#graf-workers");
    if (!p || !p.workers.length) { G.vazio(fig, "Os workers aparecem quando houver uma execução nesta sessão."); return; }
    const ws = [...p.workers].sort((a, b) => Number(a.id.slice(1)) - Number(b.id.slice(1)));
    const tipos = [["timeouts", "timeout"], ["falhas_rede", "rede"], ["sessoes_expiradas", "sessao"], ["erros_criticos", "critico"], ["sobrecargas", "sobrecarga"]];
    G.barras(fig, { categorias: ws.map((w) => w.id), tituloCategoria: "Worker", vazio: "Nenhuma falha por worker nesta execução.",
      series: tipos.map(([campo, cat]) => ({ nome: ROTULOS_ERRO[cat], cor: corErro(cat), valores: ws.map((w) => w.contadores[campo] || 0) }))
        .filter((se) => se.valores.some((v) => v > 0)) });
  }

  function mostrarResumo() {
    const r = dash.ultimo && dash.ultimo.painel && dash.ultimo.painel.resumo;
    if (!r) return;
    const t = r.totais;
    const modo = r.modo === "monitoramento" ? "Somente monitoramento" : r.dry_run ? "Matrícula em DRY RUN (teste)" : "Matrícula REAL";
    const motivos = { concluida: "Todas as disciplinas foram processadas", interrompida: "Interrompida pelo usuário",
      sem_workers: "Nenhum worker conseguiu continuar (login recusado ou falhas seguidas)", erro: "Encerrada por um erro" };
    const nos = h("div", { class: "resumo-execucao" },
      h("p", {}, `${r.inicio} → ${r.fim} (${duracao(r.duracao_seg)}) · ${modo}`),
      h("p", {}, h("strong", {}, motivos[r.motivo_fim] || "Fim da execução")),
      h("dl", { class: "indicadores" }, [["Buscas", t.requisicoes], ["Vagas vistas", t.vagas_vistas], ["Tentativas", t.tentativas],
        ["Matriculadas", t.matriculadas], ["Simuladas (DRY RUN)", t.simuladas], ["Bloqueadas", t.bloqueadas], ["Erros", t.erros]]
        .map(([k, v]) => h("div", {}, h("dt", {}, k), h("dd", {}, String(v))))),
      h("h3", {}, "Disciplinas"),
      h("div", { class: "tabela-rolavel" }, h("table", { class: "tabela" },
        h("thead", {}, h("tr", {}, ["Disciplina", "Resultado", "Buscas", "Vagas vistas", "Tentativas"].map((c) => h("th", { scope: "col" }, c)))),
        h("tbody", {}, r.alvos.map((a) => h("tr", {}, h("td", {}, a.chave), h("td", {}, a.estado_rotulo), h("td", { class: "num" }, String(a.buscas)),
          h("td", { class: "num" }, String(a.vagas_vistas)), h("td", { class: "num" }, String(a.tentativas))))))),
      h("p", { class: "dica" }, `Execução ${r.execucao_id} · ${r.configuracao.num_workers} workers, intervalo ${r.configuracao.intervalo_busca}s. `
        + "Uma cópia deste resumo fica em data/relatorios/."));
    dialogo({ titulo: "📋 Resumo da execução", nos });
  }

  // Abas (padrão ARIA: setas trocam de aba)
  function trocarAba(aba) {
    dash.aba = aba;
    $$("#dash-abas [role=tab]").forEach((b) => { const ativa = b.dataset.aba === aba; b.setAttribute("aria-selected", String(ativa)); b.tabIndex = ativa ? 0 : -1; });
    ["geral", "graficos", "workers", "tempo"].forEach((a) => { $(`#painel-dash-${a}`).hidden = a !== aba; });
    if (aba === "tempo") carregarLinhaTempo();
    G.esconderTooltip();
    atualizarDashboard();
  }
  $$("#dash-abas [role=tab]").forEach((b) => {
    b.tabIndex = b.getAttribute("aria-selected") === "true" ? 0 : -1;
    b.addEventListener("click", () => trocarAba(b.dataset.aba));
    b.addEventListener("keydown", (ev) => {
      if (!["ArrowLeft", "ArrowRight"].includes(ev.key)) return;
      ev.preventDefault();
      const abas = $$("#dash-abas [role=tab]");
      const i = abas.indexOf(b) + (ev.key === "ArrowRight" ? 1 : -1);
      const alvo = abas[(i + abas.length) % abas.length];
      alvo.focus(); trocarAba(alvo.dataset.aba);
    });
  });
  $$("#dash-janela button").forEach((b) => b.addEventListener("click", () => {
    dash.janela = Number(b.dataset.janela);
    $$("#dash-janela button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    $$("#painel-dash-graficos .grafico-area").forEach((a) => a.classList.add("atualizando"));
    atualizarDashboard().finally(() => $$("#painel-dash-graficos .grafico-area").forEach((a) => a.classList.remove("atualizando")));
  }));
  let redimensionar = null;
  window.addEventListener("resize", () => {
    clearTimeout(redimensionar);
    redimensionar = setTimeout(() => {
      if (estadoApp.telaAtual !== "dashboard" || !dash.ultimo) return;
      if (dash.aba === "graficos") renderGraficos(dash.ultimo.painel);
      if (dash.aba === "workers") renderGraficoWorkers(dash.ultimo.painel);
    }, 150);
  });
  $("#dash-parar").addEventListener("click", async (ev) => {
    const r = await acao("POST", "/api/execucao/parar", {}, { botao: ev.currentTarget });
    if (r) { renderStatus(r.execucao); toast("Parando — aguardando os workers atuais encerrarem.", "info"); }
  });
  $("#dash-ver-resumo").addEventListener("click", mostrarResumo);

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
  $("#log-exportar-csv").addEventListener("click", () => exportarLogsCsv());
  $("#log-baixar").addEventListener("click", (ev) => { ev.preventDefault(); baixar("/api/logs/arquivo", "sigaa_sniper_audit.json"); });
  CARREGADORES.logs = () => atualizarLogs(true);

  // ── 🗂️ Histórico (Fase 3: 061, 022, 024, 025, 028, 049, 050) ─────────
  // Período e disciplina filtram TUDO nesta tela (cards, gráficos e lista),
  // para os números sempre concordarem entre si.
  const hist = { dias: 30, disciplina: "", dados: null, selecionadas: new Set() };
  const MOTIVOS_FIM = { concluida: "Concluída", interrompida: "Interrompida", sem_workers: "Sem workers", erro: "Erro" };
  const dataHora = (ts) => new Date(ts * 1000).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });
  const diaCurto = (iso) => { const [a, m, d] = iso.split("-"); return `${d}/${m}${a !== String(new Date().getFullYear()) ? `/${a.slice(2)}` : ""}`; };

  function consultaHistorico() {
    const q = new URLSearchParams();
    if (hist.dias) q.set("dias", String(hist.dias));
    if (hist.disciplina) q.set("disciplina", hist.disciplina);
    return q.toString();
  }

  async function carregarHistorico() {
    let r;
    $$("#tela-historico .grafico-area").forEach((a) => a.classList.add("atualizando"));
    try { r = await api("GET", `/api/historico?${consultaHistorico()}`); } catch (e) { mostrarErro(e); return; }
    finally { $$("#tela-historico .grafico-area").forEach((a) => a.classList.remove("atualizando")); }
    hist.dados = r;
    $("#hist-desativado").hidden = r.ativo;
    const sel = $("#hist-disciplina");
    const atual = sel.value;
    limpar(sel).append(h("option", { value: "" }, "Todas"), ...r.disciplinas.map((d) => h("option", { value: d }, d)));
    sel.value = r.disciplinas.includes(atual) ? atual : "";
    renderHistoricoCards(r.totais);
    renderHistoricoGraficos(r);
    renderHistoricoLista(r.execucoes);
    carregarJanelas();
  }

  function renderHistoricoCards(t) {
    const grade = limpar($("#hist-cards"));
    [["Execuções", G.numero(t.execucoes)], ["Horas monitoradas", G.numero(t.horas, 1)], ["Buscas", G.numero(t.buscas)],
      ["Vagas vistas", G.numero(t.vagas_vistas)], ["Matrículas", `${t.matriculadas}${t.simuladas ? ` (+${t.simuladas} simuladas)` : ""}`],
      ["Erros", G.numero(t.erros)]].forEach(([rotulo, valor]) => grade.append(h("div", { class: "card-metrica" },
      h("div", { class: "rotulo" }, rotulo), h("div", { class: "valor" }, valor))));
  }

  function renderHistoricoGraficos(r) {
    const dias = r.por_dia;
    G.barras($("#graf-hist-vagas"), { categorias: dias.map((d) => diaCurto(d.dia)), tituloCategoria: "Dia",
      series: [{ nome: "Vagas vistas", cor: 1, valores: dias.map((d) => d.vagas_vistas) }], vazio: "Nenhuma vaga vista no período." });
    G.barras($("#graf-hist-horas"), { categorias: dias.map((d) => diaCurto(d.dia)), tituloCategoria: "Dia",
      series: [{ nome: "Horas monitoradas", cor: 1, valores: dias.map((d) => d.horas) }], formatar: (v) => `${G.numero(v, 1)} h`,
      vazio: "Nenhuma execução no período." });
    G.mapaCalor($("#graf-hist-mapa"), { linhas: r.mapa.dias, colunas: r.mapa.horas, matriz: r.mapa.matriz,
      rotuloColuna: (c) => `${String(c).padStart(2, "0")}h`, nomeValor: "Vagas que abriram",
      formatar: (v) => `${v} abertura(s)`, vazio: "Nenhuma vaga abriu no período — o mapa aparece quando houver aberturas registradas." });
  }

  function renderHistoricoLista(execucoes) {
    const corpo = limpar($("#hist-linhas"));
    hist.selecionadas = new Set([...hist.selecionadas].filter((id) => execucoes.some((e) => e.id === id)));
    execucoes.forEach((e) => {
      const resultado = e.matriculadas ? `${e.matriculadas} matriculada(s)` : e.simuladas ? `${e.simuladas} simulada(s)`
        : e.bloqueadas ? `${e.bloqueadas} bloqueada(s)` : "—";
      const caixa = h("input", { type: "checkbox", "aria-label": `Selecionar execução de ${dataHora(e.inicio)} para comparar` });
      caixa.checked = hist.selecionadas.has(e.id);
      caixa.addEventListener("change", () => {
        if (caixa.checked) hist.selecionadas.add(e.id); else hist.selecionadas.delete(e.id);
        if (hist.selecionadas.size > 2) { hist.selecionadas.delete(e.id); caixa.checked = false; toast("Escolha no máximo duas execuções para comparar.", "aviso"); }
        linha.classList.toggle("selecionada", caixa.checked);
        $("#hist-comparar").disabled = hist.selecionadas.size !== 2;
      });
      const modo = e.modo === "monitoramento" ? "Monitoramento" : e.dry_run ? "Matrícula (DRY RUN)" : "Matrícula REAL";
      const linha = h("tr", { class: caixa.checked ? "selecionada" : "" },
        h("td", {}, caixa), h("td", {}, dataHora(e.inicio)), h("td", {}, duracao(e.duracao_seg) || "—"), h("td", {}, modo),
        h("td", {}, MOTIVOS_FIM[e.motivo_fim] || "—"), h("td", { class: "num" }, G.numero(e.requisicoes)),
        h("td", { class: "num" }, G.numero(e.vagas_vistas)), h("td", { class: "num" }, resultado), h("td", { class: "num" }, G.numero(e.erros)),
        h("td", {}, h("button", { type: "button", class: "botao botao-fantasma botao-pequeno", onclick: () => abrirDetalheHistorico(e.id) }, "Ver")));
      corpo.append(linha);
    });
    $("#hist-vazio").hidden = execucoes.length > 0;
    $("#hist-comparar").disabled = hist.selecionadas.size !== 2;
  }

  async function abrirDetalheHistorico(id) {
    let d;
    try { d = await api("GET", `/api/historico/execucao/${encodeURIComponent(id)}`); } catch (e) { mostrarErro(e); return; }
    const r = d.resumo, t = r.totais;
    const modo = r.modo === "monitoramento" ? "Somente monitoramento" : r.dry_run ? "Matrícula em DRY RUN (teste)" : "Matrícula REAL";
    $("#hist-detalhe-titulo").textContent = `Execução de ${dataHora(d.inicio)}`;
    limpar($("#hist-detalhe-conteudo")).append(h("div", {},
      h("p", {}, `${r.inicio} → ${r.fim} (${duracao(r.duracao_seg)}) · ${modo} · ${MOTIVOS_FIM[r.motivo_fim] || "fim"}`),
      h("dl", { class: "indicadores" }, [["Buscas", t.requisicoes], ["Vagas vistas", t.vagas_vistas], ["Tentativas", t.tentativas],
        ["Matriculadas", t.matriculadas], ["Simuladas", t.simuladas], ["Bloqueadas", t.bloqueadas], ["Erros", t.erros],
        ["Workers / intervalo", `${r.configuracao.num_workers} / ${r.configuracao.intervalo_busca}s`]]
        .map(([k, v]) => h("div", {}, h("dt", {}, k), h("dd", {}, String(v))))),
      h("h3", {}, "Disciplinas"),
      h("div", { class: "tabela-rolavel" }, h("table", { class: "tabela" },
        h("thead", {}, h("tr", {}, ["Disciplina", "Resultado", "Buscas", "Vagas vistas", "Tentativas"].map((c, i) => h("th", { scope: "col", class: i > 1 ? "num" : "" }, c)))),
        h("tbody", {}, r.alvos.map((a) => h("tr", {}, h("td", {}, a.chave), h("td", {}, a.estado_rotulo), h("td", { class: "num" }, String(a.buscas)),
          h("td", { class: "num" }, String(a.vagas_vistas)), h("td", { class: "num" }, String(a.tentativas))))))),
      Object.keys(r.erros || {}).length ? h("p", { class: "dica" }, `Erros por tipo: ${Object.entries(r.erros).map(([k, v]) => `${ROTULOS_ERRO[k] || k} ${v}`).join(", ")}`) : null,
      h("p", { class: "dica" }, `ID ${r.execucao_id} · versão ${r.versao}`)));
    $("#hist-detalhe").hidden = false;
    const s = d.series_minuto;
    G.serieTempo($("#graf-hist-det-latencia"), { tipo: "linha", formatar: (v) => `${Math.round(v)} ms`,
      vazio: "Sem série por minuto (execuções gravadas antes do histórico têm só o resumo).",
      series: [{ nome: "Mediana (p50)", cor: 1, pontos: s.map((p) => [p.t, p.p50]) }, { nome: "95º percentil (p95)", cor: 2, pontos: s.map((p) => [p.t, p.p95]) }] });
    G.serieTempo($("#graf-hist-det-vagas"), { tipo: "degrau", inicio: d.inicio, fim: d.fim, formatar: (v) => `${v} vaga(s)`,
      vazio: "Nenhuma leitura de vagas registrada.",
      series: r.alvos.slice(0, 7).map((a, i) => ({ nome: a.chave, cor: i + 1, pontos: d.vagas_series[a.chave] || [] })) });
    $("#hist-detalhe").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function compararHistorico() {
    let r;
    try { r = await api("GET", `/api/historico/comparar?ids=${[...hist.selecionadas].map(encodeURIComponent).join(",")}`); } catch (e) { mostrarErro(e); return; }
    const [a, b] = r.execucoes;
    if (!a || !b) return;
    const linhas = [
      ["Início", (x) => x.resumo.inicio], ["Duração", (x) => duracao(x.indicadores.duracao_seg)],
      ["Workers", (x) => x.indicadores.num_workers, "menor"], ["Intervalo entre buscas", (x) => `${x.indicadores.intervalo_busca}s`],
      ["Buscas por segundo", (x) => x.indicadores.buscas_por_seg, "num1"], ["Tempo de resposta médio", (x) => x.indicadores.latencia_media, "ms"],
      ["Taxa de erro", (x) => x.indicadores.taxa_erro, "pct"], ["Vagas vistas", (x) => x.indicadores.vagas_vistas],
      ["Tentativas", (x) => x.indicadores.tentativas], ["Erros", (x) => x.indicadores.erros],
    ];
    const fmtValor = (v, tipo) => (v === null || v === undefined ? "—" : tipo === "ms" ? `${Math.round(v)} ms` : tipo === "pct" ? `${G.numero(v * 100, 1)}%`
      : tipo === "num1" ? G.numero(v, 1) : String(v));
    const tabela = limpar($("#hist-comparacao-tabela"));
    tabela.append(h("thead", {}, h("tr", {}, h("th", { scope: "col" }, ""), h("th", { scope: "col" }, "Execução A"), h("th", { scope: "col" }, "Execução B"))),
      h("tbody", {}, linhas.map(([rotulo, f, tipo]) => h("tr", {}, h("th", { scope: "row" }, rotulo),
        h("td", {}, fmtValor(f(a), tipo)), h("td", {}, fmtValor(f(b), tipo))))));
    $("#hist-comparacao").hidden = false;
    G.serieTempo($("#graf-hist-comparacao"), { tipo: "linha", formatar: (v) => `${Math.round(v)} ms`, tituloX: "Minutos desde o início",
      formatarX: (m) => `${G.numero(m, 0)} min`, vazio: "Estas execuções não têm série por minuto.",
      series: [{ nome: "Execução A", cor: 1, pontos: a.latencia_por_minuto }, { nome: "Execução B", cor: 2, pontos: b.latencia_por_minuto }] });
    $("#hist-comparacao").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  $$("#hist-periodo button").forEach((b) => b.addEventListener("click", () => {
    hist.dias = Number(b.dataset.dias);
    $$("#hist-periodo button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    carregarHistorico();
  }));
  $("#hist-disciplina").addEventListener("change", (ev) => { hist.disciplina = ev.target.value; carregarHistorico(); });
  $("#hist-comparar").addEventListener("click", compararHistorico);
  $$("#tela-historico [data-fechar]").forEach((b) => b.addEventListener("click", () => { $(`#${b.dataset.fechar}`).hidden = true; }));
  $("#hist-apagar").addEventListener("click", async (ev) => {
    const r = await acao("POST", "/api/historico/apagar", {}, { botao: ev.currentTarget, rotuloSim: "Apagar tudo" });
    if (r) { toast(r.mensagem, "sucesso"); $("#hist-detalhe").hidden = $("#hist-comparacao").hidden = true; carregarHistorico(); }
  });
  $("#hist-exportar").addEventListener("click", (ev) => {
    const lista = $("#hist-exportar-lista");
    lista.hidden = !lista.hidden;
    ev.currentTarget.setAttribute("aria-expanded", String(!lista.hidden));
    if (!lista.hidden) $("button", lista).focus();
  });
  $$("#hist-exportar-lista button").forEach((b) => b.addEventListener("click", () => {
    $("#hist-exportar-lista").hidden = true;
    $("#hist-exportar").setAttribute("aria-expanded", "false");
    const q = new URLSearchParams(consultaHistorico());
    q.set("tipo", b.dataset.tipo); q.set("formato", b.dataset.formato);
    baixar(`/api/historico/exportar?${q}`, `sigaa_sniper_${b.dataset.tipo === "vagas" ? "vagas" : "historico"}.${b.dataset.formato}`);
  }));
  document.addEventListener("click", (ev) => {
    if (!ev.target.closest(".menu-exportar")) { $("#hist-exportar-lista").hidden = true; $("#hist-exportar").setAttribute("aria-expanded", "false"); }
  });
  async function carregarAuditoria() {
    let r; try { r = await api("GET", "/api/auditoria"); } catch (e) { return; }
    const corpo = limpar($("#auditoria-lista"));
    $("#auditoria-vazio").hidden = !!r.acoes.length;
    r.acoes.slice(0, 100).forEach((a) => corpo.append(h("tr", {},
      h("td", {}, a.quando), h("td", {}, a.rotulo), h("td", {}, a.descricao || "—"), h("td", {}, a.origem))));
  }
  // Sugestão 091: horários em que as vagas costumam surgir, com janela sugerida.
  const NOMES_DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
  function faixaHoras(item) {
    const max = Math.max(1, ...item.contagem_por_hora);
    return h("div", { class: "faixa-horas", role: "img", "aria-label": item.texto },
      item.contagem_por_hora.map((n, hora) => {
        const barra = h("span", { class: `hora${hora >= item.inicio_h && hora <= item.fim_h ? " na-janela" : ""}`, title: `${hora}h: ${n} abertura(s)` });
        barra.style.setProperty("--altura", `${Math.round((n / max) * 100)}%`);  // CSSOM: permitido pela CSP (atributo style não)
        return barra;
      }),
      h("span", { class: "eixo-horas", "aria-hidden": "true" }, h("span", {}, "0h"), h("span", {}, "6h"), h("span", {}, "12h"), h("span", {}, "18h"), h("span", {}, "23h")));
  }
  async function carregarJanelas() {
    const q = consultaHistorico();
    let r; try { r = await api("GET", `/api/historico/janelas${q ? `?${q}` : ""}`); } catch (e) { return; }
    const ul = limpar($("#janelas-lista"));
    $("#janelas-vazio").hidden = !!r.janelas.length;
    $("#janelas-legenda").textContent = `Por disciplina, nos últimos ${r.dias} dias.`;
    r.janelas.forEach((j) => ul.append(h("li", {},
      h("div", { class: "nome" }, j.disciplina, h("span", { class: "texto-suave" }, ` · ${j.aberturas} abertura(s) de vaga`)),
      h("p", { class: "detalhe" }, j.texto),
      j.suficiente ? faixaHoras(j) : null,
      j.suficiente ? h("div", { class: "legenda-janela texto-suave" }, h("span", { class: "amostra na-janela", "aria-hidden": "true" }), " faixa com a maior parte das aberturas · ",
        `sugestão: das ${j.sugestao.inicio} às ${j.sugestao.fim}, ${j.sugestao.dias.map((d) => NOMES_DIAS[d]).join(", ")}`) : null,
      j.suficiente ? h("button", { type: "button", class: "botao botao-secundario botao-pequeno", onclick: async (ev) => {
        const ok = await acao("POST", "/api/execucao/janela", { janela: j.sugestao }, { botao: ev.currentTarget, rotuloSim: "Usar janela" });
        if (ok) { toast(ok.mensagem, "sucesso"); atualizarEstado(); }
      } }, "Usar como janela diária") : null)));
  }
  CARREGADORES.historico = () => { carregarHistorico(); carregarAuditoria(); };

  // Impressão / Salvar como PDF (sugestão 050): imprime só o bloco escolhido.
  function imprimir(elemento) {
    document.body.classList.add("modo-impressao");
    elemento.classList.add("imprimir-alvo");
    const limparModo = () => { document.body.classList.remove("modo-impressao"); elemento.classList.remove("imprimir-alvo"); window.removeEventListener("afterprint", limparModo); };
    window.addEventListener("afterprint", limparModo);
    window.print();
    setTimeout(limparModo, 1500); // navegadores que não disparam afterprint
  }
  $("#hist-imprimir").addEventListener("click", () => imprimir($("#hist-detalhe")));

  // Exportar os eventos FILTRADOS da Central de Logs (sugestão 049).
  function celulaCsv(v) {
    let t = String(v === null || v === undefined ? "" : v);
    if (/^[=+\-@\t\r]/.test(t)) t = `'${t}`; // evita injeção de fórmula no Excel/Sheets
    return /[;"\n\r]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
  }
  function exportarLogsCsv() {
    const visiveis = logs.registros.filter(passaFiltro);
    if (!visiveis.length) { toast("Nenhum evento com os filtros atuais.", "info"); return; }
    const cab = ["data_hora", "worker", "categoria", "nivel", "evento", "explicacao", "mensagem_original"];
    const linhas = visiveis.map((r) => [r.timestamp, r.worker, r.categoria, r.nivel, r.titulo, r.corpo, r.bruto.message || ""].map(celulaCsv).join(";"));
    salvarBlob(new Blob(["﻿" + [cab.join(";"), ...linhas].join("\r\n")], { type: "text/csv;charset=utf-8" }), "sigaa_sniper_eventos.csv");
    toast(`${visiveis.length} evento(s) exportado(s).`, "sucesso");
  }

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
        h("td", {}, d.grupo || "—"),
        h("td", {}, { alta: "Alta", normal: "Normal", baixa: "Baixa" }[d.prioridade] || "Normal"),
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
  // Desde a 6.1.0: nada de lista pulando enquanto se digita. Ou a pessoa digita o
  // código, ou abre "Ver departamentos" (lista completa, pesquisável).
  async function nomeDoDepartamento(codigo) {
    try {
      const r = await api("GET", `/api/departamentos?q=${encodeURIComponent(String(codigo))}`);
      const d = r.departamentos.find((x) => x.codigo === Number(codigo));
      return d ? d.nome : "";
    } catch (e) { return null; }
  }
  async function definirDepto(codigo, nome) {
    deptoSelecionado = codigo || 0;
    $("#disc-depto-busca").value = codigo ? String(codigo) : "";
    const alvo = $("#disc-depto-selecionado");
    if (!codigo) { alvo.textContent = "Digite o código ou escolha na lista."; return; }
    if (nome === undefined) nome = await nomeDoDepartamento(codigo);
    alvo.textContent = nome ? `✔ ${codigo} — ${nome}`
      : nome === null ? `Código ${codigo} (não foi possível consultar a lista agora)`
        : `⚠ ${codigo} não está na lista de referência — confira o código (pode ser um departamento novo).`;
  }
  let buscaTimer = null;
  $("#disc-depto-busca").addEventListener("input", (ev) => {
    const texto = ev.target.value.trim();
    clearTimeout(buscaTimer);
    if (!/^\d+$/.test(texto)) {
      deptoSelecionado = 0;
      $("#disc-depto-selecionado").textContent = texto ? "O código do departamento é só o número. Para procurar pelo nome, use \"Ver departamentos\"." : "Digite o código ou escolha na lista.";
      return;
    }
    deptoSelecionado = Number(texto);
    buscaTimer = setTimeout(() => definirDepto(Number(texto)), 250);
  });

  function escolherDepartamento(termoInicial = "") {
    const dlg = $("#dialogo-departamentos");
    const busca = $("#deptos-busca"), lista = $("#deptos-lista"), status = $("#deptos-status");
    let todos = [];
    const render = () => {
      const t = busca.value.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
      const filtrados = todos.filter((d) => !t || String(d.codigo) === t || d.nome.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().includes(t));
      limpar(lista);
      status.textContent = !todos.length ? status.textContent : filtrados.length
        ? `${filtrados.length} de ${todos.length} departamento(s). Clique para escolher.` : "Nenhum departamento com esse nome ou código.";
      filtrados.slice(0, 300).forEach((d) => lista.append(h("li", {}, h("button", { type: "button", class: "item-depto",
        onclick: () => { dlg.close(); resolver({ codigo: d.codigo, nome: d.nome }); } },
      h("span", { class: "codigo-depto" }, String(d.codigo)), " ", d.nome))));
    };
    let resolver;
    const promessa = new Promise((r) => { resolver = r; });
    busca.value = termoInicial;
    limpar(lista);
    status.textContent = "Carregando a lista…";
    busca.oninput = render;
    $("#deptos-fechar").onclick = () => { dlg.close(); resolver(null); };
    dlg.oncancel = (ev) => { ev.preventDefault(); dlg.close(); resolver(null); };
    dlg.showModal();
    busca.focus();
    api("GET", "/api/departamentos?todos=1").then((r) => {
      todos = r.departamentos;
      status.textContent = r.info ? r.info.texto : "";
      if (!todos.length) { status.textContent = "A lista de departamentos está vazia — use \"Atualizar lista de departamentos\" na tela Disciplinas ou digite o código."; return; }
      render();
    }).catch(() => { status.textContent = "Não foi possível carregar a lista agora. Digite o código do departamento no campo."; });
    return promessa;
  }
  $("#disc-ver-deptos").addEventListener("click", async () => {
    const d = await escolherDepartamento("");
    if (d) definirDepto(d.codigo, d.nome);
    $("#disc-depto-busca").focus();
  });

  function abrirDisciplina(d) {
    const f = $("#form-disciplina");
    f.reset();
    edicao = d ? { indice: d.indice, chave: d.chave } : null;
    $("#disc-titulo").textContent = d ? `Editar ${d.chave}` : "Adicionar disciplina";
    if (d) { f.codigo.value = d.codigo; f.turma.value = d.turma; f.professor.value = d.professor; f.grupo.value = d.grupo || ""; f.prioridade.value = d.prioridade || "normal"; definirDepto(d.departamento, d.nome_departamento); } else definirDepto(0);
    limpar($("#disc-grupos")).append(...[...new Set(disciplinas.map((x) => x.grupo).filter(Boolean))].map((g) => h("option", { value: g })));
    $("#dialogo-disciplina").showModal();
    f.codigo.focus();
  }
  $("#disc-adicionar").addEventListener("click", () => abrirDisciplina(null));

  // Cadastro em lote (sugestão 005): colar → pré-visualizar → confirmar.
  // O servidor reinterpreta o texto ao aplicar; a prévia é só para o usuário revisar.
  function abrirLote() {
    $("#form-lote").reset();
    limpar($("#lote-linhas"));
    $("#lote-tabela-bloco").hidden = true;
    $("#lote-resumo").textContent = "";
    $("#lote-adicionar").disabled = true;
    $("#lote-adicionar").textContent = "Adicionar";
    $("#dialogo-lote").showModal();
    $("#lote-texto").focus();
  }
  $("#disc-lote").addEventListener("click", abrirLote);
  $("#lote-cancelar").addEventListener("click", () => $("#dialogo-lote").close());
  $("#lote-texto").addEventListener("input", () => {
    if ($("#lote-adicionar").disabled) return;
    $("#lote-adicionar").disabled = true;
    $("#lote-resumo").textContent = "O texto mudou — pré-visualize de novo antes de adicionar.";
  });
  $("#lote-previa").addEventListener("click", async (ev) => {
    const r = await acao("POST", "/api/disciplinas/lote/previa", { texto: $("#lote-texto").value }, { botao: ev.currentTarget });
    if (!r) return;
    const corpo = limpar($("#lote-linhas"));
    r.linhas.forEach((l) => {
      const [classe, rotulo, detalhe] = l.erros.length ? ["situacao-erro", "❌ Erro", l.erros[0]]
        : l.avisos.length ? ["situacao-aviso", "⚠️ Aviso", l.avisos[0]] : ["situacao-ok", "✅ OK", ""];
      corpo.append(h("tr", {}, h("td", { class: "num" }, String(l.linha)),
        h("td", {}, l.disciplina ? `${l.disciplina.codigo}-${l.disciplina.turma}` : l.texto),
        h("td", { class: classe }, rotulo), h("td", {}, detalhe)));
    });
    $("#lote-tabela-bloco").hidden = false;
    $("#lote-resumo").textContent = `${r.validas} válida(s)${r.com_aviso ? ` (${r.com_aviso} com aviso)` : ""} · ${r.invalidas} com erro (serão ignoradas).`;
    $("#lote-adicionar").disabled = r.validas === 0;
    $("#lote-adicionar").textContent = r.validas ? `Adicionar ${r.validas}` : "Adicionar";
  });
  $("#form-lote").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const r = await acao("POST", "/api/disciplinas/lote/aplicar", { texto: $("#lote-texto").value },
      { botao: $("#lote-adicionar"), rotuloSim: "Adicionar mesmo assim" });
    if (!r) return;
    $("#dialogo-lote").close();
    disciplinas = r.disciplinas; renderDisciplinas(); toast(r.mensagem, "sucesso"); atualizarEstado();
  });
  $("#disc-cancelar").addEventListener("click", () => $("#dialogo-disciplina").close());
  $("#form-disciplina").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.currentTarget;
    const corpo = { codigo: f.codigo.value, turma: f.turma.value, departamento: deptoSelecionado, professor: f.professor.value,
      grupo: f.grupo.value, prioridade: f.prioridade.value };
    let r;
    if (edicao) r = await acao("POST", `/api/disciplinas/${edicao.indice}/editar`, { ...corpo, chave_original: edicao.chave }, { botao: $("button[type=submit]", f), rotuloSim: "Salvar mesmo assim" });
    else r = await acao("POST", "/api/disciplinas", corpo, { botao: $("button[type=submit]", f), rotuloSim: "Salvar mesmo assim" });
    if (r) { $("#dialogo-disciplina").close(); disciplinas = r.disciplinas; renderDisciplinas(); toast(r.mensagem, "sucesso"); atualizarEstado(); }
  });
  CARREGADORES.disciplinas = () => { carregarDisciplinas(); carregarInfoDepartamentos(); };
  async function carregarInfoDepartamentos() {
    try { $("#depto-info").textContent = (await api("GET", "/api/departamentos?q=%23")).info.texto; } catch (e) { /* */ }
  }
  $("#depto-atualizar").addEventListener("click", async (ev) => {
    const r = await acao("POST", "/api/departamentos/atualizar", {}, { botao: ev.currentTarget });
    if (r) { toast(r.mensagem, "sucesso"); $("#depto-info").textContent = r.info.texto; }
  });

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
      eventos, lembrar: f.lembrar.checked, resumo_intervalo_horas: f.resumo_intervalo_horas.value,
      windows_ativo: f.windows_ativo.checked, webhook_ativo: f.webhook_ativo.checked, webhook_formato: f.webhook_formato.value,
      webhook_url: f.webhook_url.value, email_ativo: f.email_ativo.checked, email_senha: f.email_senha.value,
      manter_email_senha: !f.email_senha.value,
      email: { servidor: f["email.servidor"].value, porta: f["email.porta"].value, usuario: f["email.usuario"].value,
        destinatario: f["email.destinatario"].value, remetente: f["email.remetente"].value, seguranca: f["email.seguranca"].value },
    };
  }
  async function carregarNotificacoes() {
    let n; try { n = await api("GET", "/api/notificacoes"); } catch (e) { mostrarErro(e); return; }
    const f = $("#form-notificacoes");
    ["telegram_ativo", "ntfy_ativo", "alarme_ativo", "lembrar"].forEach((k) => definir(f[k], n[k]));
    ["telegram_token", "telegram_chat_id", "ntfy_topic", "ntfy_servidor"].forEach((k) => definir(f[k], n[k] || ""));
    definir(f.alarme_repeticoes, n.alarme_repeticoes); definir(f.alarme_duracao, n.alarme_duracao);
    definir(f.resumo_intervalo_horas, n.resumo_intervalo_horas);
    ["windows_ativo", "webhook_ativo", "email_ativo"].forEach((k) => definir(f[k], n[k]));
    definir(f.webhook_formato, n.webhook_formato); definir(f.webhook_url, n.webhook_url || "");
    ["servidor", "porta", "usuario", "destinatario", "remetente", "seguranca"].forEach((k) => definir(f[`email.${k}`], n.email[k] ?? ""));
    $("#notif-email-senha-dica").hidden = !n.tem_email_senha;
    $("#notif-cofre-texto").textContent = n.cofre_texto;
    if (!n.windows_disponivel) $("#notif-windows-dica").textContent = "Disponível só no Windows.";
    const caixa = $("#notif-eventos");
    if (!caixa.children.length) {
      Object.entries(n.rotulos_eventos || ROTULOS_EVENTOS).forEach(([chave, rotulo]) => caixa.append(
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
  // Perfis de carga (sugestão 043): a estimativa é recalculada ao vivo com os
  // MESMOS parâmetros do servidor (app/core/config.py: estimar_carga).
  const carga = { parametros: null, presets: {} };
  function estimarCarga(workers, intervalo) {
    const p = carga.parametros;
    if (!p || !(workers > 0) || !(intervalo >= 0)) return null;
    const alvos = Math.max(1, p.qtd_alvos);
    let rps = (workers * alvos) / (alvos * p.latencia_seg + intervalo);
    const teto = Number(String($("#form-avancado")["protecao.limite_req_por_seg"].value || p.teto || 0).replace(",", "."));
    const limitada = teto > 0 && teto < rps;
    if (limitada) rps = teto;
    const nivel = rps <= p.limite_baixa ? "baixa" : rps <= p.limite_moderada ? "moderada" : "alta";
    return { rps, nivel, limitada };
  }
  function presetCorrespondente(workers, intervalo) {
    return Object.keys(carga.presets).find((k) => carga.presets[k].num_workers === workers && Math.abs(carga.presets[k].intervalo_busca - intervalo) < 1e-9) || "";
  }
  function atualizarCargaAvancado() {
    const f = $("#form-avancado");
    const workers = Number(f.num_workers.value);
    const intervalo = Number(String(f.intervalo_busca.value).replace(",", "."));
    f.preset_carga.value = presetCorrespondente(workers, intervalo);
    const c = estimarCarga(workers, intervalo);
    const saida = $("#avancado-carga");
    if (!c) { saida.textContent = ""; saida.className = "carga-estimada"; return; }
    saida.className = `carga-estimada carga-${c.nivel}`;
    saida.textContent = `Carga estimada: ≈ ${c.rps.toFixed(1)} req/s (${c.nivel}) `
      + (c.limitada ? "— limitada pelo teto da proteção de carga." : `com ${Math.max(1, carga.parametros.qtd_alvos)} disciplina(s) ativa(s).`)
      + (c.nivel === "alta" ? " ⚠️ Considere o perfil Moderado ou Leve — o aviso legal pede uso responsável, e cargas altas aumentam o risco de bloqueio." : "");
  }

  function preencherAvancado(a, forcar = false) {
    const f = $("#form-avancado");
    if (forcar) formularioSalvo(f);
    const d = (campo, valor) => definir(f[campo], valor);
    carga.parametros = a.carga_parametros;
    // 044: as faixas dos campos numéricos vêm do mesmo esquema que valida no servidor.
    Object.entries(a.esquema || {}).forEach(([nome, e]) => {
      const campo = f.elements.namedItem(nome);
      if (campo && campo.type === "number") { campo.min = String(e.min); campo.max = String(e.max); }
    });
    carga.presets = a.presets_carga || {};
    const sel = f.preset_carga;
    if (!sel.children.length) {
      Object.entries(carga.presets).forEach(([k, p]) => sel.append(h("option", { value: k }, `${p.rotulo} — ${p.num_workers} workers, ${p.intervalo_busca}s`)));
      sel.append(h("option", { value: "" }, "Personalizado"));
    }
    d("num_workers", a.num_workers); d("intervalo_busca", a.intervalo_busca); d("timeout_req", a.timeout_req);
    d("abrir_dashboard_ao_iniciar", a.abrir_dashboard_ao_iniciar); d("carregar_ultima_execucao", a.carregar_ultima_execucao); d("nivel_log_console", a.nivel_log_console);
    d("logs.tamanho_max_mb", a.logs.tamanho_max_mb); d("logs.arquivos_mantidos", a.logs.arquivos_mantidos);
    d("json_audit.tamanho_max_mb", a.json_audit.tamanho_max_mb); d("json_audit.arquivos_mantidos", a.json_audit.arquivos_mantidos);
    d("web.host", a.web.host); d("web.porta", a.web.porta); d("web.abrir_navegador", a.web.abrir_navegador);
    d("web.modo_aplicativo", a.web.modo_aplicativo); d("web.expirar_inatividade_min", a.web.expirar_inatividade_min);
    d("historico.ativo", a.historico.ativo); d("historico.dias_retencao", a.historico.dias_retencao);
    d("protecao.limite_req_por_seg", a.protecao.limite_req_por_seg); d("protecao.logins_simultaneos", a.protecao.logins_simultaneos);
    d("protecao.disjuntor", a.protecao.disjuntor);
    ["ativo", "taxa_erro_pct", "taxa_erro_min", "sem_resposta_min", "sem_busca_min"].forEach((k) => d(`alertas.${k}`, a.alertas[k]));
    const urls = $("#avancado-urls");
    if (!urls.children.length) {
      Object.keys(a.urls).forEach((k) => urls.append(h("label", {}, ROTULOS_URLS[k] || k, h("input", { name: `url.${k}`, spellcheck: "false", autocomplete: "off" }))));
    }
    Object.keys(a.urls).forEach((k) => definir(f[`url.${k}`], a.urls[k]));
    $("#avancado-espaco").textContent = textoEspaco(a.espaco);
    atualizarCargaAvancado();
    const secoes = $("#avancado-secoes");
    if (!secoes.children.length) {
      a.secoes_restauraveis.forEach((s) => secoes.append(h("label", { class: "caixa" }, h("input", { type: "checkbox", value: s }), ROTULOS_SECOES[s] || s)));
    }
  }
  $("#avancado-preset").addEventListener("change", (ev) => {
    const p = carga.presets[ev.target.value];
    if (!p) return; // "Personalizado": mantém os números digitados
    const f = $("#form-avancado");
    f.num_workers.value = p.num_workers; f.intervalo_busca.value = p.intervalo_busca;
    f.num_workers.dataset.editado = "1"; f.intervalo_busca.dataset.editado = "1";
    atualizarCargaAvancado();
  });
  ["num_workers", "intervalo_busca", "protecao.limite_req_por_seg"].forEach((n) => $("#form-avancado")[n].addEventListener("input", atualizarCargaAvancado));

  async function carregarAvancado() {
    try { preencherAvancado(await api("GET", "/api/avancado")); } catch (e) { mostrarErro(e); }
    carregarPerfis(); carregarVersoes();
  }

  // ── Perfis (042) e versões anteriores (045) ─────────────────────────
  function renderPerfis(perfis) {
    const ul = limpar($("#perfis-lista"));
    if (!perfis.length) ul.append(h("li", {}, h("span", { "aria-hidden": "true" }, "ℹ️"), h("div", {}, h("div", { class: "nome" }, "Nenhum perfil ainda"),
      h("div", { class: "detalhe" }, "Configure tudo como quer e salve com um nome abaixo."))));
    perfis.forEach((p) => ul.append(h("li", {}, h("span", { "aria-hidden": "true" }, "🎛️"),
      h("div", { class: "expandir" }, h("div", { class: "nome" }, p.nome), h("div", { class: "detalhe" }, `${p.resumo} · salvo em ${p.criado}`)),
      h("div", { class: "acoes acoes-compactas" },
        h("button", { type: "button", class: "botao botao-secundario botao-pequeno", onclick: (ev) => aplicarPerfil(p.arquivo, ev.currentTarget) }, "Aplicar"),
        h("button", { type: "button", class: "botao botao-fantasma botao-pequeno", "aria-label": `Apagar o perfil ${p.nome}`,
          onclick: async (ev) => { const r = await acao("POST", "/api/perfis/apagar", { arquivo: p.arquivo }, { botao: ev.currentTarget, rotuloSim: "Apagar" });
            if (r) { toast(r.mensagem, "sucesso"); renderPerfis(r.perfis); atualizarEstado(); } } }, "Apagar")))));
  }
  async function carregarPerfis() {
    try { renderPerfis((await api("GET", "/api/perfis")).perfis); } catch (e) { /* cartão fica como está */ }
  }
  async function aplicarPerfil(arquivo, botao) {
    const r = await acao("POST", "/api/perfis/aplicar", { arquivo }, { botao, rotuloSim: "Aplicar perfil" });
    if (r) { toast(r.mensagem, "sucesso"); $$("form").forEach(formularioSalvo); recarregarTudo(); carregarVersoes(); }
  }
  $("#form-perfil").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.currentTarget;
    const r = await acao("POST", "/api/perfis", { nome: f.nome.value }, { botao: $("button[type=submit]", f), rotuloSim: "Substituir" });
    if (r) { toast(r.mensagem, "sucesso"); f.reset(); renderPerfis(r.perfis); atualizarEstado(); }
  });
  function renderVersoes(versoes) {
    const corpo = limpar($("#versoes-lista"));
    $("#versoes-vazio").hidden = !!versoes.length;
    versoes.forEach((v) => corpo.append(h("tr", {}, h("td", {}, v.quando), h("td", {}, v.tipo_rotulo), h("td", {}, v.resumo),
      h("td", {}, h("button", { type: "button", class: "botao botao-fantasma botao-pequeno", onclick: async (ev) => {
        const r = await acao("POST", "/api/config/versoes/restaurar", { id: v.id }, { botao: ev.currentTarget, rotuloSim: "Restaurar" });
        if (r) { toast(r.mensagem, "sucesso"); $$("form").forEach(formularioSalvo); renderVersoes(r.versoes); recarregarTudo(); }
      } }, "Restaurar")))));
  }
  async function carregarVersoes() {
    try { renderVersoes((await api("GET", "/api/config/versoes")).versoes); } catch (e) { /* idem */ }
  }
  $("#form-avancado").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.currentTarget;
    const urls = {};
    $$("#avancado-urls input").forEach((i) => { urls[i.name.slice(4)] = i.value; });
    const corpo = {
      num_workers: f.num_workers.value, intervalo_busca: f.intervalo_busca.value, timeout_req: f.timeout_req.value,
      abrir_dashboard_ao_iniciar: f.abrir_dashboard_ao_iniciar.checked, carregar_ultima_execucao: f.carregar_ultima_execucao.checked, nivel_log_console: f.nivel_log_console.value,
      logs: { tamanho_max_mb: f["logs.tamanho_max_mb"].value, arquivos_mantidos: f["logs.arquivos_mantidos"].value },
      json_audit: { tamanho_max_mb: f["json_audit.tamanho_max_mb"].value, arquivos_mantidos: f["json_audit.arquivos_mantidos"].value },
      web: { host: f["web.host"].value, porta: f["web.porta"].value, abrir_navegador: f["web.abrir_navegador"].checked,
        modo_aplicativo: f["web.modo_aplicativo"].checked, expirar_inatividade_min: f["web.expirar_inatividade_min"].value },
      historico: { ativo: f["historico.ativo"].checked, dias_retencao: f["historico.dias_retencao"].value },
      protecao: { limite_req_por_seg: f["protecao.limite_req_por_seg"].value, logins_simultaneos: f["protecao.logins_simultaneos"].value,
        disjuntor: f["protecao.disjuntor"].checked },
      alertas: { ativo: f["alertas.ativo"].checked, taxa_erro_pct: f["alertas.taxa_erro_pct"].value, taxa_erro_min: f["alertas.taxa_erro_min"].value,
        sem_resposta_min: f["alertas.sem_resposta_min"].value, sem_busca_min: f["alertas.sem_busca_min"].value },
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
  $("#avancado-testar-urls").addEventListener("click", async (ev) => {
    const urls = {};
    $$("#avancado-urls input").forEach((i) => { urls[i.name.slice(4)] = i.value; });
    const lista = limpar($("#avancado-urls-teste"));
    lista.append(h("li", {}, h("span", { class: "texto-suave" }, "Testando cada endereço…")));
    const r = await acao("POST", "/api/avancado/testar-urls", { urls }, { botao: ev.currentTarget });
    limpar(lista);
    if (!r) return;
    r.resultados.forEach((x) => lista.append(h("li", {},
      h("span", { "aria-hidden": "true" }, x.ok ? "✅" : x.status === null && !x.dominio_ok ? "⛔" : "❌"),
      h("div", {}, h("div", { class: "nome" }, ROTULOS_URLS[x.nome] || x.nome, h("span", { class: "visualmente-oculto" }, x.ok ? " — OK" : " — problema")),
        h("div", { class: "detalhe" }, x.texto)))));
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
    $("#diag-exportar").disabled = $("#diag-copiar").disabled = $("#diag-imprimir").disabled = false;
  }
  $("#diag-completo").addEventListener("click", (ev) => rodarDiagnostico("/api/diagnostico/completo", ev.currentTarget));
  $("#diag-camadas").addEventListener("click", (ev) => rodarDiagnostico("/api/diagnostico/camadas", ev.currentTarget));
  $("#diag-imprimir").addEventListener("click", () => imprimir($("#diag-cartao")));
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

  // Fase 5: segurança (067), assistente (079), recomendações (089), páginas (064), pacote (051).
  const CERTEZA = { certa: ["Confirmado", "selo-info"], provavel: ["Provável", "selo-aviso"], sugestao: ["Verifique", "selo-neutro"] };
  const NOME_TELA = { credenciais: "Credenciais", disciplinas: "Disciplinas", execucao: "Execução", dashboard: "Dashboard", avancado: "Config. Avançadas",
    notificacoes: "Notificações", diagnostico: "Diagnóstico", historico: "Histórico", logs: "Logs" };
  const botaoIr = (tela) => tela && tela !== estadoApp.telaAtual ? h("button", { type: "button", class: "botao botao-fantasma botao-pequeno", "data-ir-para": tela }, `Ir para ${NOME_TELA[tela] || tela}`) : null;
  async function carregarSeguranca() {
    const lista = limpar($("#seg-itens"));
    let r; try { r = await api("GET", "/api/diagnostico/seguranca"); } catch (e) { lista.append(h("li", {}, "Não foi possível conferir agora.")); return; }
    if (!r.alertas.length) { lista.append(h("li", {}, h("span", { "aria-hidden": "true" }, "✅"), h("div", {}, h("div", { class: "nome" }, "Nenhuma configuração insegura encontrada")))); return; }
    r.alertas.forEach((a) => lista.append(h("li", {},
      h("span", { "aria-hidden": "true" }, a.nivel === "risco" ? "❌" : "⚠️"),
      h("div", {}, h("div", { class: "nome" }, a.titulo, h("span", { class: "visualmente-oculto" }, a.nivel === "risco" ? " — risco" : " — atenção")),
        h("div", { class: "detalhe" }, a.detalhe), h("div", { class: "detalhe" }, h("strong", {}, "O que fazer: "), a.acao), botaoIr(a.tela)))));
  }
  async function carregarAssistente() {
    let r; try { r = await api("GET", "/api/assistente"); } catch (e) { return; }
    const grade = $("#assist-sintomas");
    if (!grade.children.length) {
      r.sintomas.forEach((s) => grade.append(h("button", { type: "button", class: "botao botao-secundario sintoma", "data-sintoma": s.id,
        "aria-pressed": "false", onclick: (ev) => diagnosticarSintoma(s.id, ev.currentTarget) }, s.texto)));
    }
    const lista = limpar($("#rec-itens"));
    if (!r.recomendacoes.length) {
      lista.append(h("li", {}, h("span", { "aria-hidden": "true" }, "ℹ️"), h("div", {}, h("div", { class: "nome" }, "Nenhuma recomendação agora"),
        h("div", { class: "detalhe" }, "Elas aparecem quando uma execução tem métricas suficientes (pelo menos 100 buscas) e algo pode ser melhor ajustado."))));
    }
    r.recomendacoes.forEach((x) => lista.append(h("li", {}, h("span", { "aria-hidden": "true" }, "💡"),
      h("div", {}, h("div", { class: "nome" }, x.texto), h("div", { class: "detalhe" }, x.motivo),
        h("button", { type: "button", class: "botao botao-secundario botao-pequeno", onclick: async (ev) => {
          const ok = await acao("POST", "/api/assistente/aplicar", { id: x.id }, { botao: ev.currentTarget });
          if (ok) { toast(ok.mensagem, "sucesso"); carregarAssistente(); recarregarTudo(); }
        } }, "Aplicar")))));
  }
  async function diagnosticarSintoma(id, botao) {
    $$("#assist-sintomas button").forEach((b) => b.setAttribute("aria-pressed", String(b === botao)));
    const caixa = limpar($("#assist-resultado"));
    caixa.append(h("p", { class: "texto-suave" }, "Analisando…"));
    const r = await acao("POST", "/api/assistente/diagnosticar", { sintoma: id }, { botao });
    limpar(caixa);
    if (!r) return;
    caixa.append(h("h3", {}, r.pergunta), h("p", { class: "texto-suave" }, r.fonte ? `Analisado com base em ${r.fonte} e na configuração atual.` : "Sem execução para analisar: só a configuração atual foi conferida."));
    caixa.append(h("ul", { class: "lista-diagnostico" }, r.achados.map((a) => h("li", {},
      h("span", { class: `selo ${CERTEZA[a.certeza][1]}` }, CERTEZA[a.certeza][0]),
      h("div", {}, h("div", { class: "nome" }, a.causa), a.evidencia ? h("div", { class: "detalhe" }, `Evidência: ${a.evidencia}`) : null,
        h("div", { class: "detalhe" }, h("strong", {}, "O que fazer: "), a.acao), botaoIr(a.tela))))));
  }
  async function carregarDumps() {
    const corpo = limpar($("#dumps-itens"));
    let r; try { r = await api("GET", "/api/suporte/dumps"); } catch (e) { return; }
    $("#dumps-vazio").hidden = !!r.dumps.length;
    r.dumps.slice(0, 30).forEach((d) => corpo.append(h("tr", {},
      h("td", {}, d.quando || "—"), h("td", {}, d.motivo_texto), h("td", {}, d.worker), h("td", { class: "num" }, `${d.tamanho_kb} KB`),
      h("td", {}, h("button", { type: "button", class: "botao botao-fantasma botao-pequeno", onclick: () => verDump(d.nome) }, "Ver")))));
  }
  async function verDump(nome) {
    let d; try { d = await api("GET", `/api/suporte/dumps/${encodeURIComponent(nome)}`); } catch (e) { mostrarErro(e); return; }
    dialogo({ titulo: `📄 ${d.motivo_texto}`, nos: h("div", {},
      h("p", { class: "dica" }, `${d.quando || ""} · ${d.worker} · dados pessoais mascarados com ***${d.cortado ? " · página longa: mostrando o começo" : ""}`),
      h("pre", { class: "bloco-codigo bloco-dump" }, d.texto || "(página sem texto visível)")) });
  }
  $("#dumps-atualizar").addEventListener("click", carregarDumps);
  $("#seg-atualizar").addEventListener("click", carregarSeguranca);
  $("#suporte-previa").addEventListener("click", async (ev) => {
    const botao = ev.currentTarget;
    botao.disabled = true;
    let r = null;
    try { r = await api("GET", "/api/suporte/pacote/previa"); } catch (e) { mostrarErro(e); } finally { botao.disabled = false; }
    const lista = limpar($("#suporte-itens"));
    if (!r) return;
    r.arquivos.forEach((a) => lista.append(h("li", {}, h("span", { "aria-hidden": "true" }, a.nome.endsWith("/") ? "📁" : "📄"),
      h("div", {}, h("div", { class: "nome" }, `${a.nome} `, h("span", { class: "texto-suave" }, `(${a.tamanho_kb} KB)`)), h("div", { class: "detalhe" }, a.descricao)))));
  });
  $("#suporte-baixar").addEventListener("click", () => baixar("/api/suporte/pacote", "sigaa_sniper_suporte.zip"));
  CARREGADORES.diagnostico = () => { carregarSeguranca(); carregarAssistente(); carregarDumps(); };

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
    $("#sobre-hash").textContent = s.sha256 || "rodando pelo código-fonte (sem executável para verificar)";
    $("#sobre-verificar-ao-abrir").checked = s.verificar_ao_abrir;
    guiaManual = s.guia_manual;
    if (!s.atalho_suportado) { $("#sobre-guia").hidden = false; $("#sobre-guia").textContent = s.guia_manual; }
  }
  $("#sobre-atalho").addEventListener("click", async (ev) => {
    const r = await acao("POST", "/api/sobre/atalho", {}, { botao: ev.currentTarget });
    if (r) toast(`✅ ${r.mensagem}`, "sucesso", 8000);
    else if (guiaManual) { $("#sobre-guia").hidden = false; $("#sobre-guia").textContent = guiaManual; }
  });
  $("#sobre-atualizacao").addEventListener("click", async (ev) => {
    const r = await acao("POST", "/api/sobre/atualizacao", {}, { botao: ev.currentTarget });
    if (!r) return;
    const caixa = limpar($("#sobre-atualizacao-resultado"));
    caixa.append(r.texto, r.nova ? h("span", {}, " ", h("a", { href: r.url, target: "_blank", rel: "noopener noreferrer" }, "Abrir a página da versão")) : "");
  });
  $("#sobre-verificar-ao-abrir").addEventListener("change", (ev) => acao("POST", "/api/sobre/preferencias", { verificar_ao_abrir: ev.target.checked }));
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

  // ── Paleta de ações e atalhos de teclado (sugestão 002) ──────────────
  // Reaproveita os mesmos botões/handlers da página: "Iniciar" pela paleta
  // passa pelas mesmas validações e confirmações (inclusive a da matrícula real).
  const normalizar = (t) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const ATALHOS_TELAS = { e: "execucao", d: "dashboard", l: "logs", i: "historico", c: "credenciais", m: "disciplinas", n: "notificacoes", a: "avancado", g: "diagnostico", h: "ajuda" };
  function acoesDisponiveis() {
    const letraDaTela = Object.fromEntries(Object.entries(ATALHOS_TELAS).map(([l, t]) => [t, l]));
    const telas = $$("#menu button").map((b) => ({
      rotulo: `Ir para ${b.textContent.trim()}`, grupo: "Tela", palavras: b.dataset.tela,
      atalho: letraDaTela[b.dataset.tela] ? `G ${letraDaTela[b.dataset.tela].toUpperCase()}` : "",
      fazer: () => irPara(b.dataset.tela),
    }));
    const clicar = (tela, sel) => () => { irPara(tela); const b = $(sel); if (b && !b.disabled) b.click(); };
    const acoes = [
      { rotulo: "▶️ Iniciar execução", grupo: "Execução", palavras: "start comecar rodar", fazer: clicar("execucao", "#botao-iniciar"), ativa: () => !$("#botao-iniciar").disabled },
      { rotulo: "⏯️ Pausar / retomar execução", grupo: "Execução", palavras: "pausa continuar", fazer: () => alternarPausa($("#botao-pausar")), ativa: () => !$("#botao-pausar").disabled },
      { rotulo: "⏹️ Parar execução", grupo: "Execução", palavras: "stop encerrar", fazer: clicar("execucao", "#botao-parar"), ativa: () => !$("#botao-parar").disabled },
      { rotulo: "➕ Adicionar disciplina", grupo: "Disciplinas", palavras: "materia turma nova", fazer: () => { irPara("disciplinas"); abrirDisciplina(null); } },
      { rotulo: "📋 Adicionar várias disciplinas (lote)", grupo: "Disciplinas", palavras: "colar planilha lista", fazer: () => { irPara("disciplinas"); abrirLote(); } },
      { rotulo: "🔔 Abrir central de notificações", grupo: "Geral", palavras: "avisos alertas historico", fazer: abrirCentral },
      { rotulo: "🩺 Rodar diagnóstico completo", grupo: "Diagnóstico", palavras: "testar conexao problema", fazer: clicar("diagnostico", "#diag-completo") },
      { rotulo: "🌐 Testar conectividade em camadas", grupo: "Diagnóstico", palavras: "internet sigaa rede", fazer: clicar("diagnostico", "#diag-camadas") },
      { rotulo: "🧭 Assistente de solução de problemas", grupo: "Diagnóstico", palavras: "ajuda erro nao funciona causa", fazer: () => { irPara("diagnostico"); $("#assist-cartao").scrollIntoView({ block: "start" }); } },
      { rotulo: "📦 Baixar pacote de suporte", grupo: "Diagnóstico", palavras: "zip ajuda suporte issue", fazer: () => baixar("/api/suporte/pacote", "sigaa_sniper_suporte.zip") },
      { rotulo: "🕒 Linha do tempo da execução", grupo: "Dashboard", palavras: "timeline eventos historia", fazer: () => { irPara("dashboard"); trocarAba("tempo"); } },
      { rotulo: "⬇️ Baixar arquivo de log", grupo: "Logs", palavras: "download auditoria json", fazer: () => baixar("/api/logs/arquivo", "sigaa_sniper_audit.json") },
      { rotulo: "📊 Exportar histórico de execuções (CSV)", grupo: "Histórico", palavras: "planilha excel relatorio", fazer: () => baixar("/api/historico/exportar?tipo=execucoes&formato=csv", "sigaa_sniper_historico.csv") },
      { rotulo: "📤 Exportar configuração (backup)", grupo: "Configuração", palavras: "backup salvar exportar", fazer: () => baixar("/api/config/exportar", "sigaa_sniper_config.json") },
      { rotulo: "🌓 Alternar tema claro/escuro", grupo: "Geral", palavras: "dark escuro claro", fazer: () => $("#botao-tema").click() },
      { rotulo: "🔠 Exibição (densidade e tamanho do texto)", grupo: "Geral", palavras: "fonte compacta letra tamanho", fazer: abrirExibicao },
      { rotulo: "🧰 Refazer a configuração inicial", grupo: "Geral", palavras: "assistente configurar primeira vez wizard", fazer: abrirAssistente },
      { rotulo: "🧭 Tour pela interface", grupo: "Geral", palavras: "ajuda tutorial guia primeira vez", fazer: iniciarTour },
      { rotulo: "⌨️ Mostrar atalhos de teclado", grupo: "Geral", palavras: "ajuda teclas", atalho: "?", fazer: mostrarAtalhos },
      { rotulo: "⏻ Encerrar a Interface Web", grupo: "Geral", palavras: "sair fechar", fazer: () => $("#botao-encerrar").click() },
    ];
    const perfis = (estadoApp.estado && estadoApp.estado.perfis || []).map((p) => ({
      rotulo: `🎛️ Aplicar perfil: ${p.nome}`, grupo: "Perfis", palavras: "perfil cenario trocar", fazer: () => { irPara("avancado"); aplicarPerfil(p.arquivo, null); },
    }));
    return [...acoes.filter((a) => !a.ativa || a.ativa()), ...perfis, ...telas];
  }
  const paleta = { itens: [], indice: 0 };
  function renderPaleta() {
    const termos = normalizar($("#paleta-busca").value.trim()).split(/\s+/).filter(Boolean);
    // Relevância: termo no próprio rótulo vale mais que no grupo/palavras-chave
    // (ex: "logs" deve trazer "Ir para Logs" antes de "Baixar arquivo de log").
    paleta.itens = acoesDisponiveis().map((a, ordem) => {
      const rotulo = normalizar(a.rotulo);
      const resto = normalizar(`${a.grupo} ${a.palavras || ""}`);
      let pontos = 0;
      for (const t of termos) {
        if (rotulo.includes(t)) pontos += 2;
        else if (resto.includes(t)) pontos += 1;
        else return null;
      }
      return { a, pontos, ordem };
    }).filter(Boolean).sort((x, y) => y.pontos - x.pontos || x.ordem - y.ordem).map((x) => x.a);
    paleta.indice = Math.min(paleta.indice, Math.max(0, paleta.itens.length - 1));
    const ul = limpar($("#paleta-lista"));
    if (!paleta.itens.length) { ul.append(h("li", { class: "vazio", role: "option", "aria-disabled": "true" }, "Nenhuma ação encontrada.")); return; }
    paleta.itens.forEach((a, i) => ul.append(h("li", {
      role: "option", id: `paleta-op-${i}`, "aria-selected": i === paleta.indice ? "true" : "false",
      onclick: () => executarDaPaleta(i), onmousemove: () => { if (paleta.indice !== i) { paleta.indice = i; marcarPaleta(); } },
    }, h("span", {}, a.rotulo), h("span", { class: "grupo" }, a.grupo), a.atalho ? h("kbd", {}, a.atalho) : null)));
    marcarPaleta();
  }
  function marcarPaleta() {
    $$("#paleta-lista li[role=option]").forEach((li, i) => li.setAttribute("aria-selected", i === paleta.indice ? "true" : "false"));
    const atual = $(`#paleta-op-${paleta.indice}`);
    $("#paleta-busca").setAttribute("aria-activedescendant", atual ? atual.id : "");
    if (atual) atual.scrollIntoView({ block: "nearest" });
  }
  function abrirPaleta() {
    if (estadoApp.encerrado || $("#app").hidden) return;
    $$("dialog[open]").forEach((d) => { if (d.id !== "dialogo-paleta" && d.id !== "dialogo-aviso") d.close(); });
    if ($("#dialogo-aviso").open) return; // o aviso legal nunca pode ser contornado
    $("#paleta-busca").value = "";
    paleta.indice = 0;
    renderPaleta();
    const dlg = $("#dialogo-paleta");
    if (!dlg.open) dlg.showModal();
    $("#paleta-busca").focus();
  }
  function executarDaPaleta(i) {
    const a = paleta.itens[i];
    if (!a) return;
    $("#dialogo-paleta").close();
    a.fazer();
  }
  $("#paleta-busca").addEventListener("input", () => { paleta.indice = 0; renderPaleta(); });
  $("#paleta-busca").addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowDown") { ev.preventDefault(); paleta.indice = Math.min(paleta.indice + 1, paleta.itens.length - 1); marcarPaleta(); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); paleta.indice = Math.max(paleta.indice - 1, 0); marcarPaleta(); }
    else if (ev.key === "Enter") { ev.preventDefault(); executarDaPaleta(paleta.indice); }
    else if (ev.key === "?" && !ev.target.value) { ev.preventDefault(); $("#dialogo-paleta").close(); mostrarAtalhos(); }
  });
  $("#dialogo-paleta").addEventListener("click", (ev) => { if (ev.target.id === "dialogo-paleta") ev.target.close(); }); // clique fora fecha
  $("#botao-paleta").addEventListener("click", abrirPaleta);

  function mostrarAtalhos() {
    const linhas = [["Ctrl + K", "Abrir a paleta de ações (buscar qualquer ação ou tela)"], ["?", "Mostrar esta lista de atalhos"],
      ...Object.entries(ATALHOS_TELAS).map(([l, t]) => [`G e depois ${l.toUpperCase()}`, `Ir para ${$(`#tela-${t}`).dataset.titulo}`]),
      ["Esc", "Fechar a janela/diálogo aberto"]];
    dialogo({ titulo: "⌨️ Atalhos de teclado", nos: h("table", { class: "tabela tabela-atalhos" },
      h("tbody", {}, linhas.map(([k, d]) => h("tr", {}, h("td", {}, h("kbd", {}, k)), h("td", {}, d))))) });
  }

  let esperandoG = null;
  document.addEventListener("keydown", (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && !ev.altKey && ev.key.toLowerCase() === "k") { ev.preventDefault(); abrirPaleta(); return; }
    if (ev.ctrlKey || ev.metaKey || ev.altKey || estadoApp.encerrado || $("#app").hidden) return;
    if ($$("dialog[open]").length) return;
    const alvo = ev.target;
    if (alvo && (alvo.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(alvo.tagName))) return;
    if (esperandoG) {
      clearTimeout(esperandoG); esperandoG = null;
      const tela = ATALHOS_TELAS[ev.key.toLowerCase()];
      if (tela) { ev.preventDefault(); irPara(tela); }
      return;
    }
    if (ev.key === "?") { ev.preventDefault(); mostrarAtalhos(); return; }
    if (ev.key.toLowerCase() === "g") { esperandoG = setTimeout(() => { esperandoG = null; }, 1200); }
  });

  // ── Assistente de configuração inicial (desde a 6.1.0) ───────────────────
  // Mesmas etapas e mesma validação da interface gráfica: a regra mora em
  // app/core/configuracao_inicial.py; aqui só se apresenta. Nada é salvo
  // antes de "Concluir" na revisão.
  const ETAPAS = ["Boas-vindas", "Credenciais", "Disciplinas", "Execução", "Notificações", "Painéis", "Revisão"];
  const assistente = { etapa: 0, dados: null, presets: null };
  function dadosIniciaisAssistente() {
    const est = estadoApp.estado || {};
    return {
      credenciais: { usuario: "", senha: "", cpf: "", nascimento: "" },
      disciplinas: [],
      execucao: { modo: est.modo || "monitoramento", dry_run: true, preset: "leve", verificacao_previa: true },
      notificacoes: { windows_ativo: false, webhook_ativo: false, webhook_formato: "discord", webhook_url: "",
        email_ativo: false, email: { servidor: "", porta: 587, seguranca: "starttls", usuario: "", destinatario: "", remetente: "" },
        email_senha: "", lembrar_segredos: false },
      paineis: { carregar_ultima_execucao: false, abrir_dashboard_ao_iniciar: true },
    };
  }
  function mostrarProblemas(problemas, avisos = []) {
    const caixa = limpar($("#assistente-erros"));
    caixa.hidden = !problemas.length && !avisos.length;
    if (problemas.length) caixa.append(h("div", { class: "alerta alerta-erro", role: "alert" }, h("strong", {}, "Corrija para continuar:"),
      h("ul", {}, problemas.map((p) => h("li", {}, p)))));
    if (avisos.length) caixa.append(h("div", { class: "alerta alerta-aviso" }, h("ul", {}, avisos.map((p) => h("li", {}, p)))));
  }
  const campoA = (rot, obj, chave, attrs = {}) => {
    const entrada = h("input", { value: obj[chave] ?? "", autocomplete: "off", ...attrs });
    entrada.addEventListener("input", () => { obj[chave] = attrs.type === "number" ? Number(entrada.value) : entrada.value; });
    return h("label", {}, rot, entrada);
  };
  const caixaA = (rot, obj, chave) => {
    const entrada = h("input", { type: "checkbox", checked: !!obj[chave] });
    entrada.addEventListener("change", () => { obj[chave] = entrada.checked; renderAssistente(); });
    return h("label", { class: "caixa" }, entrada, " ", rot);
  };
  function renderAssistente() {
    const c = limpar($("#assistente-conteudo"));
    const d = assistente.dados;
    const e = assistente.etapa;
    $("#assistente-passos").textContent = `Etapa ${e + 1} de ${ETAPAS.length} · ${ETAPAS.map((n, i) => (i === e ? `[${n}]` : n)).join(" → ")}`;
    $("#assistente-voltar").disabled = e === 0;
    $("#assistente-proximo").textContent = e === ETAPAS.length - 1 ? "✔ Concluir" : "Próximo ▶";
    switch (e) {
      case 0:
        c.append(h("h2", { id: "assistente-titulo" }, "Bem-vindo ao SIGAA Sniper"),
          h("p", {}, "Vamos configurar o essencial em 6 etapas curtas. Cada campo tem explicação, os dados são conferidos antes de avançar e nada é salvo até você revisar e concluir."),
          h("p", { class: "texto-suave" }, "Preferir fazer depois? \"Configurar depois\" fecha o assistente; ele pode ser reaberto em Config. Avançadas → Refazer a configuração inicial."));
        break;
      case 1: {
        const cr = d.credenciais;
        c.append(h("h2", { id: "assistente-titulo" }, "1. Credenciais do SIGAA"),
          h("p", { class: "texto-suave" }, "Ficam só na memória desta execução — nunca em disco. Pode deixar tudo em branco e preencher depois na tela Credenciais."),
          campoA("Matrícula (usuário do SIGAA)", cr, "usuario"), campoA("Senha", cr, "senha", { type: "password", autocomplete: "new-password" }),
          campoA("CPF — com ou sem pontos (ex: 123.456.789-09)", cr, "cpf", { inputmode: "numeric" }),
          campoA("Data de nascimento — DD/MM/AAAA (ex: 01/02/2003)", cr, "nascimento", { placeholder: "DD/MM/AAAA" }),
          h("p", { class: "dica" }, "O CPF e a data são os que o SIGAA pede na tela de confirmação da matrícula; eles são conferidos agora, antes de qualquer login."));
        break;
      }
      case 2: {
        const nova = { codigo: "", turma: "", departamento: "", grupo: "", prioridade: "normal" };
        const deptoInfo = h("p", { class: "dica", "aria-live": "polite" }, "Digite o código ou escolha na lista.");
        const deptoCampo = campoA("Código do departamento (ex: 673)", nova, "departamento", { inputmode: "numeric" });
        const prioridade = h("select", {}, ["alta", "normal", "baixa"].map((p) => h("option", { value: p, selected: p === "normal" },
          { alta: "Alta — consultada primeiro", normal: "Normal", baixa: "Baixa — a cada 3 rodadas" }[p])));
        prioridade.addEventListener("change", () => { nova.prioridade = prioridade.value; });
        const lista = h("ul", { class: "disciplinas-assistente" }, d.disciplinas.map((x, i) => h("li", {},
          h("span", {}, `${x.codigo.toUpperCase()}-${x.turma} · depto ${x.departamento}${x.grupo ? ` · grupo ${x.grupo}` : ""} · ${x.prioridade}`),
          h("button", { type: "button", class: "botao botao-fantasma botao-pequeno", "aria-label": `Remover ${x.codigo}-${x.turma}`,
            onclick: () => { d.disciplinas.splice(i, 1); renderAssistente(); } }, "Remover"))));
        c.append(h("h2", { id: "assistente-titulo" }, "2. Disciplinas"),
          h("p", { class: "texto-suave" }, `${(estadoApp.estado || {}).qtd_disciplinas || 0} já cadastrada(s). Adicione quantas quiser (ou nenhuma agora).`),
          campoA("Código da disciplina (ex: FGA0211)", nova, "codigo"), campoA("Turma — só números (ex: 01)", nova, "turma", { inputmode: "numeric" }),
          h("div", { class: "campo-com-botao" }, h("div", { class: "expandir" }, deptoCampo),
            h("button", { type: "button", class: "botao botao-secundario", onclick: async () => {
              const r = await escolherDepartamento("");
              if (r) { nova.departamento = String(r.codigo); $("input", deptoCampo).value = r.codigo; deptoInfo.textContent = `✔ ${r.codigo} — ${r.nome}`; }
            } }, "📋 Ver departamentos")), deptoInfo,
          h("div", { class: "grade-2 grade-compacta" },
            h("label", {}, h("span", { class: "rotulo-linha" }, "Grupo de alternativas (opcional) ", h("button", { type: "button", class: "ajuda-mini", "data-ajuda": "grupo", "aria-label": "Como funciona o grupo?" }, "?")),
              (() => { const i = h("input", { maxlength: "40", autocomplete: "off", placeholder: "ex: calculo1" }); i.addEventListener("input", () => { nova.grupo = i.value; }); return i; })()),
            h("label", {}, h("span", { class: "rotulo-linha" }, "Prioridade ", h("button", { type: "button", class: "ajuda-mini", "data-ajuda": "prioridade", "aria-label": "Como funciona a prioridade?" }, "?")), prioridade)),
          h("p", { class: "dica" }, "Mesmo grupo = alternativas (garantida uma, as outras saem da busca). Prioridade só define a ordem das consultas."),
          h("button", { type: "button", class: "botao botao-secundario alinhar-inicio", onclick: async () => {
            let r; try { r = await api("POST", "/api/configuracao-inicial/validar", { etapa: "disciplina", dados: nova, pendentes: d.disciplinas }); } catch (err) { mostrarErro(err); return; }
            mostrarProblemas(r.problemas, r.avisos);
            if (r.ok) { d.disciplinas.push({ ...nova, codigo: nova.codigo.trim().toUpperCase(), turma: nova.turma.trim() }); renderAssistente(); if (r.avisos.length) mostrarProblemas([], r.avisos); }
          } }, "➕ Adicionar esta disciplina"), lista);
        break;
      }
      case 3: {
        const ex = d.execucao;
        const radio = (valor, titulo, texto) => {
          const i = h("input", { type: "radio", name: "a_modo", value: valor, checked: ex.modo === valor });
          i.addEventListener("change", () => { ex.modo = valor; renderAssistente(); });
          return h("label", { class: "opcao-modo" }, i, h("span", { class: "opcao-conteudo" }, h("strong", {}, titulo), h("span", {}, texto)));
        };
        const preset = h("select", {}, Object.entries(assistente.presets || {}).map(([k, p]) => h("option", { value: k, selected: k === ex.preset },
          `${p.rotulo} — ${p.num_workers} workers, ${p.intervalo_busca}s`)));
        preset.addEventListener("change", () => { ex.preset = preset.value; });
        c.append(h("h2", { id: "assistente-titulo" }, "3. Execução"),
          h("div", { class: "opcoes-modo" }, radio("monitoramento", "👀 Somente monitoramento", "Avisa quando achar vaga, nunca matricula sozinho."),
            radio("matricula", "🎯 Matrícula automática", "Tenta se matricular assim que achar vaga.")),
          ex.modo === "matricula" ? caixaA("DRY RUN (recomendado para começar): simula tudo, mas não confirma a matrícula de verdade", ex, "dry_run") : null,
          ex.modo === "matricula" && !ex.dry_run ? h("p", { class: "alerta alerta-aviso" }, "⚠️ Sem DRY RUN, ao achar vaga o programa confirma a matrícula de verdade.") : null,
          h("label", {}, "Perfil de carga (quanto o programa consulta o SIGAA)", preset),
          h("p", { class: "dica" }, "Leve basta para acompanhar vagas e pesa menos no SIGAA. Pode ajustar depois em Config. Avançadas."),
          caixaA("Verificar login e disciplinas antes de começar (recomendado)", ex, "verificacao_previa"));
        break;
      }
      case 4: {
        const n = d.notificacoes;
        const formato = h("select", {}, [["discord", "Discord"], ["slack", "Slack"], ["json", "JSON genérico"]].map(([v, r]) => h("option", { value: v, selected: n.webhook_formato === v }, r)));
        formato.addEventListener("change", () => { n.webhook_formato = formato.value; });
        const seg = h("select", {}, [["starttls", "STARTTLS (porta 587)"], ["ssl", "SSL/TLS (porta 465)"]].map(([v, r]) => h("option", { value: v, selected: n.email.seguranca === v }, r)));
        seg.addEventListener("change", () => { n.email.seguranca = seg.value; n.email.porta = seg.value === "ssl" ? 465 : 587; renderAssistente(); });
        c.append(h("h2", { id: "assistente-titulo" }, "4. Notificações (opcional)"),
          h("p", { class: "texto-suave" }, "O programa funciona sem nenhuma. Telegram, ntfy e alarme sonoro ficam na tela Notificações."),
          caixaA("🪟 Aviso na área de notificações do Windows (não precisa configurar nada)", n, "windows_ativo"),
          h("div", { class: "linha-form" }, caixaA("🔗 Webhook (Discord, Slack…)", n, "webhook_ativo"),
            h("button", { type: "button", class: "botao botao-fantasma botao-pequeno", "data-ajuda": "webhook" }, "Como configurar?")),
          n.webhook_ativo ? h("div", { class: "grade-2 grade-compacta" }, h("label", {}, "Formato", formato),
            campoA("URL do webhook (https://…)", n, "webhook_url", { type: "password" })) : null,
          h("div", { class: "linha-form" }, caixaA("✉️ E-mail (SMTP)", n, "email_ativo"),
            h("button", { type: "button", class: "botao botao-fantasma botao-pequeno", "data-ajuda": "email" }, "Como configurar?")),
          n.email_ativo ? h("div", { class: "formulario" },
            h("div", { class: "grade-2 grade-compacta" }, campoA("Servidor SMTP (ex: smtp.gmail.com)", n.email, "servidor"), h("label", {}, "Segurança", seg)),
            h("div", { class: "grade-2 grade-compacta" }, campoA("Usuário (seu e-mail)", n.email, "usuario"), campoA("Senha (Gmail/Outlook: senha de app)", n, "email_senha", { type: "password", autocomplete: "new-password" })),
            h("div", { class: "grade-2 grade-compacta" }, campoA("Enviar para", n.email, "destinatario"), campoA("Remetente (opcional)", n.email, "remetente"))) : null,
          n.webhook_ativo || n.email_ativo ? caixaA("Guardar a URL/senha neste computador (cifradas com a sua conta do Windows)", n, "lembrar_segredos") : null);
        break;
      }
      case 5:
        c.append(h("h2", { id: "assistente-titulo" }, "5. Painéis"),
          caixaA("Carregar os dados da última execução ao abrir o programa", d.paineis, "carregar_ultima_execucao"),
          h("p", { class: "dica" }, "Desligado (recomendado): Dashboard e Logs começam vazios até você iniciar uma execução; as anteriores ficam na tela Histórico. Ligado: mostram a última execução marcada como recuperada — o tempo não corre e nada é iniciado."),
          caixaA("Abrir o Dashboard automaticamente ao iniciar uma execução", d.paineis, "abrir_dashboard_ao_iniciar"));
        break;
      default: {
        const lista = h("ul", { class: "lista-resumo" }, h("li", {}, "Montando o resumo…"));
        c.append(h("h2", { id: "assistente-titulo" }, "6. Revisão"),
          h("p", { class: "texto-suave" }, "Confira. \"◀ Voltar\" corrige qualquer etapa; \"✔ Concluir\" salva tudo (e confere tudo de novo antes)."), lista);
        api("POST", "/api/configuracao-inicial/resumo", d).then((r) => { limpar(lista).append(...r.linhas.map((l) => h("li", {}, l))); }).catch(() => {});
      }
    }
    const primeiro = $("input, select", c); if (primeiro) primeiro.focus();
  }
  const ETAPA_VALIDADA = { 1: ["credenciais", (d) => d.credenciais], 3: ["execucao", (d) => d.execucao], 4: ["notificacoes", (d) => d.notificacoes] };
  async function avancarAssistente() {
    const e = assistente.etapa;
    if (e === ETAPAS.length - 1) { await concluirAssistente(); return; }
    if (ETAPA_VALIDADA[e]) {
      const [nome, parte] = ETAPA_VALIDADA[e];
      let r; try { r = await api("POST", "/api/configuracao-inicial/validar", { etapa: nome, dados: parte(assistente.dados) }); } catch (err) { mostrarErro(err); return; }
      if (!r.ok) { mostrarProblemas(r.problemas, r.avisos); return; }
      mostrarProblemas([], r.avisos);
    } else mostrarProblemas([]);
    assistente.etapa++; renderAssistente();
  }
  async function concluirAssistente() {
    const botao = $("#assistente-proximo");
    botao.disabled = true;
    try {
      const r = await api("POST", "/api/assistente/finalizar", assistente.dados);
      $("#dialogo-assistente").close();
      toast(r.mensagem, "sucesso");
      recarregarTudo();
      let visto = false;
      try { visto = localStorage.getItem("sniper-tour-visto") === "1"; } catch (err) { /* */ }
      if (!visto) setTimeout(iniciarTour, 400);  // 007: mostra onde acompanhar tudo, uma vez só
    } catch (err) {
      if (err instanceof ErroHttp && err.dados && err.dados.problemas) mostrarProblemas(err.dados.problemas);
      else mostrarErro(err);
    } finally { botao.disabled = false; }
  }
  async function dispensarAssistente() {
    const r = await acao("POST", "/api/assistente/finalizar", { dispensar: true });
    $("#dialogo-assistente").close();
    if (r) { toast(r.mensagem, "info"); atualizarEstado(); }
  }
  async function abrirAssistente() {
    assistente.etapa = 0;
    assistente.dados = dadosIniciaisAssistente();
    if (!assistente.presets) { try { assistente.presets = (await api("GET", "/api/avancado")).presets_carga; } catch (err) { assistente.presets = {}; } }
    mostrarProblemas([]);
    renderAssistente();
    const dlg = $("#dialogo-assistente");
    dlg.oncancel = (ev) => { ev.preventDefault(); dispensarAssistente(); };
    dlg.showModal();
  }
  $("#form-assistente").addEventListener("submit", (ev) => { ev.preventDefault(); avancarAssistente(); });
  $("#assistente-voltar").addEventListener("click", () => { if (assistente.etapa > 0) { assistente.etapa--; mostrarProblemas([]); renderAssistente(); } });
  $("#assistente-pular").addEventListener("click", dispensarAssistente);
  $("#avancado-assistente").addEventListener("click", abrirAssistente);

  // ── 007: tour guiado pela interface ─────────────────────────────────
  const PASSOS_TOUR = [
    { alvo: "#status-execucao", titulo: "Estado da execução", texto: "Aqui você vê sempre se o programa está parado, rodando ou pausado — e em qual modo. Matrícula real aparece em vermelho." },
    { alvo: "#menu button[data-tela=execucao]", titulo: "Execução", texto: "Escolha o modo, agende início e fim, e inicie. A lista \"Pronto para iniciar?\" mostra o que falta. Para experimentar sem risco, use o Modo demonstração." },
    { alvo: "#menu button[data-tela=dashboard]", titulo: "Dashboard", texto: "Acompanhe cada disciplina, a saúde da conexão, gráficos, tentativas de matrícula e a linha do tempo da execução." },
    { alvo: "#menu button[data-tela=logs]", titulo: "Logs", texto: "Tudo o que o robô fez, em linguagem simples, com filtros e exportação." },
    { alvo: "#menu button[data-tela=diagnostico]", titulo: "Diagnóstico", texto: "Se algo não funcionar, o assistente de solução de problemas mostra a causa provável e o que fazer." },
    { alvo: "#botao-sino", titulo: "Avisos", texto: "Vagas, matrículas e alertas também ficam guardados aqui, mesmo que você esteja em outra tela." },
    { alvo: "#botao-paleta", titulo: "Ações rápidas", texto: "Ctrl+K abre a busca de ações: iniciar, pausar, ir para qualquer tela… Tecle ? para ver todos os atalhos." },
  ];
  let passoTour = -1;
  function fecharTour(lembrar) {
    passoTour = -1;
    $$(".tour-balao, .tour-destaque").forEach((el) => el.remove());
    if (lembrar) { try { localStorage.setItem("sniper-tour-visto", "1"); } catch (e) { /* */ } }
  }
  function mostrarPassoTour(i) {
    $$(".tour-balao, .tour-destaque").forEach((el) => el.remove());
    const passos = PASSOS_TOUR.filter((p) => { const el = $(p.alvo); return el && el.getClientRects().length; });
    if (i >= passos.length) { fecharTour(true); return; }
    passoTour = i;
    const passo = passos[i];
    const alvo = $(passo.alvo);
    alvo.scrollIntoView({ block: "nearest" });
    const r = alvo.getBoundingClientRect();
    const destaque = h("div", { class: "tour-destaque", "aria-hidden": "true" });
    Object.assign(destaque.style, { top: `${r.top - 4}px`, left: `${r.left - 4}px`, width: `${r.width + 8}px`, height: `${r.height + 8}px` });
    document.body.append(destaque);
    const balao = h("div", { class: "tour-balao", role: "dialog", "aria-modal": "false", "aria-labelledby": "tour-titulo" },
      h("p", { class: "texto-suave" }, `Passo ${i + 1} de ${passos.length}`),
      h("h2", { id: "tour-titulo" }, passo.titulo), h("p", {}, passo.texto),
      h("div", { class: "acoes acoes-compactas" },
        h("button", { type: "button", class: "botao botao-fantasma botao-pequeno", onclick: () => fecharTour(true) }, "Pular tour"),
        i > 0 ? h("button", { type: "button", class: "botao botao-secundario botao-pequeno", onclick: () => mostrarPassoTour(i - 1) }, "Voltar") : null,
        h("button", { type: "button", class: "botao botao-primario botao-pequeno", onclick: () => mostrarPassoTour(i + 1) },
          i === passos.length - 1 ? "Concluir" : "Próximo")));
    document.body.append(balao);
    const largura = Math.min(340, window.innerWidth - 24);
    const esquerda = Math.max(12, Math.min(r.left, window.innerWidth - largura - 12));
    const abaixo = r.bottom + 12 + balao.offsetHeight < window.innerHeight;
    Object.assign(balao.style, { left: `${esquerda}px`, width: `${largura}px`,
      top: `${abaixo ? r.bottom + 12 : Math.max(12, r.top - balao.offsetHeight - 12)}px` });
    $("button.botao-primario", balao).focus();
  }
  function iniciarTour() { fecharTour(false); mostrarPassoTour(0); }
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && passoTour >= 0) fecharTour(true); });
  window.addEventListener("resize", () => { if (passoTour >= 0) mostrarPassoTour(passoTour); });

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
