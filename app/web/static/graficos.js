/* SIGAA Sniper — gráficos da Interface Web (Fase 2).
 *
 * SVG gerado aqui mesmo, sem biblioteca e sem CDN: a página funciona offline
 * e a Content-Security-Policy continua bloqueando qualquer script externo.
 *
 * Regras (método de visualização adotado no projeto):
 *  - cores por PAPEL (--serie-1..7), fixas por entidade — nunca pela posição
 *    no ranking; validadas para daltonismo nos dois temas;
 *  - um eixo Y só; linhas de 2px; barras de no máximo 24px com ponta
 *    arredondada; 2px de "vão" na cor da superfície entre segmentos;
 *  - grade discreta; legenda sempre que houver 2+ séries;
 *  - hover E teclado (setas) mostram a leitura; a mesma informação está na
 *    tabela "Ver dados em tabela" — o tooltip nunca é o único caminho;
 *  - todo texto vindo de dados entra com textContent.
 */
"use strict";

window.Graficos = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const ALTURA = 220;
  const MARGEM = { topo: 12, direita: 16, baixo: 26, esquerda: 48 };

  function svg(tag, attrs = {}) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) el.setAttribute(k, v);
    return el;
  }
  function html(tag, attrs = {}, ...filhos) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") el.className = v; else if (k === "text") el.textContent = v; else el.setAttribute(k, v);
    }
    filhos.flat().forEach((f) => { if (f !== null && f !== undefined) el.append(f instanceof Node ? f : document.createTextNode(String(f))); });
    return el;
  }
  const hora = (t) => new Date(t * 1000).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const horaCurta = (t, intervalo) => new Date(t * 1000).toLocaleTimeString("pt-BR",
    intervalo > 600 ? { hour: "2-digit", minute: "2-digit" } : { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const numero = (v, casas = 0) => (v === null || v === undefined || Number.isNaN(v) ? "—"
    : Number(v).toLocaleString("pt-BR", { maximumFractionDigits: casas, minimumFractionDigits: 0 }));

  /** Passo "limpo" (1, 2, 5 × 10^n) para ~4 marcas no eixo. */
  function escalaLimpa(max, marcas = 4) {
    if (!(max > 0)) return { max: 1, passo: 1 };
    const bruto = max / marcas;
    const pot = 10 ** Math.floor(Math.log10(bruto));
    const passo = [1, 2, 5, 10].map((m) => m * pot).find((p) => p >= bruto);
    return { max: Math.ceil(max / passo) * passo, passo };
  }

  // ── Estrutura comum: área do gráfico, legenda, tabela ─────────────────
  function estrutura(fig) {
    let area = fig.querySelector(".grafico-area");
    if (!area) {
      area = html("div", { class: "grafico-area" });
      const legenda = html("ul", { class: "grafico-legenda", "aria-label": "Legenda" });
      const tabela = html("details", { class: "grafico-tabela" }, html("summary", {}, "Ver dados em tabela"), html("div", { class: "tabela-rolavel" }));
      fig.append(area, legenda, tabela);
    }
    return { area, legenda: fig.querySelector(".grafico-legenda"), tabela: fig.querySelector(".grafico-tabela .tabela-rolavel") };
  }
  function largura(area) { return Math.max(280, Math.floor(area.clientWidth || area.parentElement.clientWidth || 480)); }

  function vazio(fig, texto) {
    const { area, legenda, tabela } = estrutura(fig);
    area.replaceChildren(html("p", { class: "grafico-vazio" }, texto));
    legenda.replaceChildren();
    tabela.replaceChildren(html("p", { class: "texto-suave" }, "Sem dados."));
  }

  function renderLegenda(legenda, series, forma) {
    legenda.replaceChildren();
    if (series.length < 2) return; // uma série só: o título já diz o que é
    series.forEach((s) => legenda.append(html("li", {},
      html("span", { class: `chave chave-${forma} serie-${s.cor}`, "aria-hidden": "true" }), s.nome)));
  }

  function renderTabela(destino, cabecalho, linhas) {
    const tabela = html("table", { class: "tabela" },
      html("thead", {}, html("tr", {}, cabecalho.map((c, i) => html("th", { scope: "col", class: i ? "num" : "" }, c)))),
      html("tbody", {}, linhas.map((l) => html("tr", {}, l.map((c, i) => html("td", { class: i ? "num" : "" }, c))))));
    destino.replaceChildren(tabela);
  }

  // ── Tooltip único (reposicionado) ────────────────────────────────────
  function tooltip() { return document.getElementById("grafico-tooltip"); }
  function mostrarTooltip(ancora, x, y, titulo, linhas) {
    const tt = tooltip();
    tt.replaceChildren(html("div", { class: "tt-titulo" }, titulo),
      ...linhas.map((l) => html("div", { class: "tt-linha" },
        html("span", { class: `chave chave-${l.forma || "linha"} serie-${l.cor}`, "aria-hidden": "true" }),
        html("strong", {}, l.valor), html("span", { class: "tt-nome" }, l.nome))));
    tt.hidden = false;
    const r = ancora.getBoundingClientRect();
    const larguraTt = tt.offsetWidth;
    let esquerda = r.left + x + 14;
    if (esquerda + larguraTt > window.innerWidth - 8) esquerda = r.left + x - larguraTt - 14;
    tt.style.left = `${Math.max(8, esquerda)}px`;
    tt.style.top = `${Math.max(8, r.top + y - 10)}px`;
  }
  function esconderTooltip() { const tt = tooltip(); if (tt) tt.hidden = true; }
  document.addEventListener("scroll", esconderTooltip, true);

  function eixos(g, w, h, escala, formatarY) {
    for (let v = 0; v <= escala.max + 1e-9; v += escala.passo) {
      const y = MARGEM.topo + h - (v / escala.max) * h;
      g.append(svg("line", { class: v === 0 ? "eixo-base" : "grade", x1: MARGEM.esquerda, x2: MARGEM.esquerda + w, y1: y, y2: y }));
      const rotulo = svg("text", { class: "rotulo-eixo", x: MARGEM.esquerda - 8, y: y + 4, "text-anchor": "end" });
      rotulo.textContent = formatarY(v);
      g.append(rotulo);
    }
  }

  /**
   * Série temporal: linhas, degraus ou áreas empilhadas.
   * cfg = { series: [{ nome, cor, pontos: [[t, v], ...] }], tipo: "linha"|"degrau"|"empilhado",
   *         inicio, fim, formatar(v), unidade, vazio }
   * Para "empilhado", todas as séries devem ter os mesmos t (alinhados).
   */
  function serieTempo(fig, cfg) {
    const series = cfg.series.filter((s) => s.pontos.length);
    const comValor = series.some((s) => s.pontos.some((p) => p[1] !== null && p[1] !== undefined && (cfg.tipo !== "empilhado" || p[1] > 0)));
    if (!series.length || !comValor) { vazio(fig, cfg.vazio || "Sem dados neste período."); return; }
    const { area, legenda, tabela } = estrutura(fig);
    const W = largura(area), w = W - MARGEM.esquerda - MARGEM.direita, h = ALTURA - MARGEM.topo - MARGEM.baixo;
    const todosT = series.flatMap((s) => s.pontos.map((p) => p[0]));
    // O eixo cobre o período pedido E todos os dados (nenhuma linha sai da área do gráfico).
    const t0 = Math.min(cfg.inicio ?? Infinity, ...todosT), t1 = Math.max(cfg.fim ?? 0, ...todosT);
    const escalaX = (t) => MARGEM.esquerda + (t1 > t0 ? ((t - t0) / (t1 - t0)) * w : w / 2);
    const formatar = cfg.formatar || ((v) => numero(v));
    const rotuloX = cfg.formatarX ? (t) => cfg.formatarX(t) : (t) => horaCurta(t, t1 - t0);
    const tituloX = cfg.formatarX || hora;

    // Empilhamento: acumula por índice (t alinhados).
    const empilhado = cfg.tipo === "empilhado";
    const tempos = empilhado ? series[0].pontos.map((p) => p[0]) : null;
    const acumulado = empilhado ? series.map((_s, i) => tempos.map((_t, j) => series.slice(0, i + 1).reduce((soma, s) => soma + (s.pontos[j][1] || 0), 0))) : null;
    const maxY = empilhado ? Math.max(...acumulado[acumulado.length - 1]) : Math.max(...series.flatMap((s) => s.pontos.map((p) => p[1] || 0)));
    const escala = escalaLimpa(maxY * 1.05);
    const escalaY = (v) => MARGEM.topo + h - (v / escala.max) * h;

    const raiz = svg("svg", { class: "grafico-svg", width: W, height: ALTURA, viewBox: `0 0 ${W} ${ALTURA}`, role: "img",
      tabindex: "0", "aria-label": `${fig.dataset.titulo}. Use as setas para ler cada ponto; os mesmos dados estão na tabela abaixo.` });
    const g = svg("g");
    raiz.append(g);
    eixos(g, w, h, escala, (v) => numero(v, escala.passo < 1 ? 1 : 0));
    // Marcas de tempo no eixo X (4 a 5)
    const qtdX = Math.min(5, Math.max(2, Math.floor(w / 110)));
    for (let i = 0; i < qtdX; i++) {
      const t = t0 + ((t1 - t0) * i) / (qtdX - 1 || 1);
      const rotulo = svg("text", { class: "rotulo-eixo", x: escalaX(t), y: ALTURA - 6, "text-anchor": i === 0 ? "start" : i === qtdX - 1 ? "end" : "middle" });
      rotulo.textContent = rotuloX(t);
      g.append(rotulo);
    }

    if (empilhado) {
      // Da série de cima para a de baixo, cada camada é desenhada até sua soma acumulada.
      for (let i = series.length - 1; i >= 0; i--) {
        const topo = acumulado[i].map((v, j) => `${escalaX(tempos[j])},${escalaY(v)}`);
        const base = (i > 0 ? acumulado[i - 1] : tempos.map(() => 0)).map((v, j) => `${escalaX(tempos[j])},${escalaY(v)}`).reverse();
        g.append(svg("polygon", { class: `area-empilhada serie-${series[i].cor}`, points: [...topo, ...base].join(" ") }));
      }
    } else {
      series.forEach((s) => {
        let d = "";
        let caneta = false;
        s.pontos.forEach(([t, v], j) => {
          if (v === null || v === undefined) { caneta = false; return; }
          const x = escalaX(t), y = escalaY(v);
          if (!caneta) { d += `M${x},${y}`; caneta = true; return; }
          if (cfg.tipo === "degrau") d += `H${x}V${y}`; else d += `L${x},${y}`;
          if (cfg.tipo === "degrau" && j === s.pontos.length - 1 && cfg.fim && t < cfg.fim) d += `H${escalaX(cfg.fim)}`;
        });
        if (cfg.tipo === "degrau" && s.pontos.length === 1 && cfg.fim) {
          const [t, v] = s.pontos[0];
          d = `M${escalaX(t)},${escalaY(v)}H${escalaX(cfg.fim)}`;
        }
        g.append(svg("path", { class: `linha serie-${s.cor}`, d }));
      });
    }

    // Camada de leitura: cruz vertical + pontos + tooltip; teclado com setas.
    const cruz = svg("line", { class: "cruz", y1: MARGEM.topo, y2: MARGEM.topo + h, visibility: "hidden" });
    const marcadores = svg("g", { class: "marcadores" });
    const alvoHover = svg("rect", { class: "alvo-hover", x: MARGEM.esquerda, y: MARGEM.topo, width: w, height: h });
    g.append(cruz, marcadores, alvoHover);
    const temposLeitura = [...new Set(todosT)].sort((a, b) => a - b);
    const valorEm = (s, t, idx) => {
      if (empilhado) return s.pontos[idx] ? s.pontos[idx][1] : null;
      if (cfg.tipo === "degrau") { let v = null; for (const p of s.pontos) { if (p[0] <= t) v = p[1]; else break; } return v; }
      const p = s.pontos.find((q) => q[0] === t);
      return p ? p[1] : null;
    };
    let indice = temposLeitura.length - 1;
    function ler(i) {
      indice = Math.max(0, Math.min(temposLeitura.length - 1, i));
      const t = temposLeitura[indice];
      const idxAlinhado = empilhado ? tempos.indexOf(t) : -1;
      const x = escalaX(t);
      cruz.setAttribute("x1", x); cruz.setAttribute("x2", x); cruz.setAttribute("visibility", "visible");
      marcadores.replaceChildren();
      const linhas = [];
      series.forEach((s, si) => {
        const v = valorEm(s, t, idxAlinhado);
        linhas.push({ nome: s.nome, valor: v === null || v === undefined ? "—" : formatar(v), cor: s.cor, forma: empilhado ? "area" : "linha" });
        if (v === null || v === undefined) return;
        const yv = empilhado ? acumulado[si][idxAlinhado] : v;
        marcadores.append(svg("circle", { class: `marcador serie-${s.cor}`, cx: x, cy: escalaY(yv), r: 4 }));
      });
      if (empilhado) linhas.reverse(); // na ordem visual: de cima para baixo
      mostrarTooltip(raiz, x, MARGEM.topo + 8, tituloX(t), linhas);
    }
    function soltar() { cruz.setAttribute("visibility", "hidden"); marcadores.replaceChildren(); esconderTooltip(); }
    alvoHover.addEventListener("pointermove", (ev) => {
      const r = raiz.getBoundingClientRect();
      const tAlvo = t0 + ((ev.clientX - r.left - MARGEM.esquerda) / w) * (t1 - t0);
      let melhor = 0;
      temposLeitura.forEach((t, i) => { if (Math.abs(t - tAlvo) < Math.abs(temposLeitura[melhor] - tAlvo)) melhor = i; });
      ler(melhor);
    });
    alvoHover.addEventListener("pointerleave", soltar);
    raiz.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowLeft") { ev.preventDefault(); ler(indice - 1); }
      else if (ev.key === "ArrowRight") { ev.preventDefault(); ler(indice + 1); }
      else if (ev.key === "Home") { ev.preventDefault(); ler(0); }
      else if (ev.key === "End") { ev.preventDefault(); ler(temposLeitura.length - 1); }
      else if (ev.key === "Escape") soltar();
    });
    raiz.addEventListener("focus", () => ler(indice));
    raiz.addEventListener("blur", soltar);

    area.replaceChildren(raiz);
    renderLegenda(legenda, series, empilhado ? "area" : "linha");
    const linhasTabela = temposLeitura.slice(-120).reverse().map((t) => {
      const idx = empilhado ? tempos.indexOf(t) : -1;
      return [tituloX(t), ...series.map((s) => { const v = valorEm(s, t, idx); return v === null || v === undefined ? "—" : formatar(v); })];
    });
    renderTabela(tabela, [cfg.tituloX || "Horário", ...series.map((s) => s.nome)], linhasTabela);
  }

  /**
   * Barras verticais — simples (uma série) ou empilhadas (várias).
   * cfg = { categorias: [...], series: [{ nome, cor, valores: [...] }], formatar, vazio, rotuloCategoria }
   */
  function barras(fig, cfg) {
    const series = cfg.series;
    const totais = cfg.categorias.map((_c, i) => series.reduce((s, se) => s + (se.valores[i] || 0), 0));
    if (!cfg.categorias.length || !totais.some((v) => v > 0)) { vazio(fig, cfg.vazio || "Sem dados."); return; }
    const { area, legenda, tabela } = estrutura(fig);
    const W = largura(area), w = W - MARGEM.esquerda - MARGEM.direita, h = ALTURA - MARGEM.topo - MARGEM.baixo;
    const escala = escalaLimpa(Math.max(...totais) * 1.1);
    const escalaY = (v) => (v / escala.max) * h;
    const formatar = cfg.formatar || ((v) => numero(v));
    const faixa = w / cfg.categorias.length;
    const espessura = Math.max(4, Math.min(24, faixa * 0.6)); // nunca mais que 24px: o resto da faixa é respiro
    const raiz = svg("svg", { class: "grafico-svg", width: W, height: ALTURA, viewBox: `0 0 ${W} ${ALTURA}`, role: "img",
      "aria-label": `${fig.dataset.titulo}. Os valores estão na tabela abaixo; passe o mouse ou use Tab em cada barra.` });
    const g = svg("g");
    raiz.append(g);
    eixos(g, w, h, escala, (v) => numero(v, escala.passo < 1 ? 1 : 0));
    // Rótulos do eixo X: pula categorias quando o texto mais largo não cabe na faixa (sem colisão).
    const textoRotulo = (c) => (cfg.rotuloCategoria ? cfg.rotuloCategoria(c) : String(c));
    const larguraRotulo = Math.max(...cfg.categorias.map((c) => textoRotulo(c).length)) * 6.4 + 10;
    const passoRotulo = Math.max(1, Math.ceil(larguraRotulo / faixa));
    const indiceMaior = totais.indexOf(Math.max(...totais));

    cfg.categorias.forEach((cat, i) => {
      const x = MARGEM.esquerda + faixa * i + (faixa - espessura) / 2;
      let base = MARGEM.topo + h;
      const grupo = svg("g", { class: "barra", tabindex: "0", role: "img" });
      const partes = [];
      series.forEach((s, si) => {
        const v = s.valores[i] || 0;
        partes.push({ nome: s.nome, valor: formatar(v), cor: s.cor, forma: "area" });
        if (!v) return;
        const altura = escalaY(v);
        const eTopo = series.slice(si + 1).every((o) => !(o.valores[i] > 0));
        // Ponta arredondada só no topo da pilha; vão de 2px (cor da superfície) entre segmentos.
        const vao = si > 0 && base < MARGEM.topo + h ? 2 : 0;
        const y = base - altura;
        const alturaVisivel = Math.max(1, altura - vao);
        grupo.append(svg("path", { class: `segmento serie-${s.cor}`, d: retangulo(x, y, espessura, alturaVisivel, eTopo ? Math.min(4, alturaVisivel) : 0) }));
        base = y;
      });
      grupo.setAttribute("aria-label", `${cat}: ${partes.map((p) => `${p.nome} ${p.valor}`).join(", ")}`);
      // Área de toque maior que a barra (a faixa inteira).
      grupo.prepend(svg("rect", { class: "alvo-barra", x: MARGEM.esquerda + faixa * i, y: MARGEM.topo, width: faixa, height: h }));
      const linhasTooltip = series.length > 1 ? [...partes].reverse() : partes; // de cima para baixo, como na pilha
      const topoBarra = base;
      const mostrar = () => { grupo.classList.add("ativa"); mostrarTooltip(raiz, x + espessura, topoBarra - MARGEM.topo, cat, linhasTooltip); };
      const esconder = () => { grupo.classList.remove("ativa"); esconderTooltip(); };
      grupo.addEventListener("pointerenter", mostrar); grupo.addEventListener("pointerleave", esconder);
      grupo.addEventListener("focus", mostrar); grupo.addEventListener("blur", esconder);
      g.append(grupo);
      if (i % passoRotulo === 0) {
        const r = svg("text", { class: "rotulo-eixo", x: x + espessura / 2, y: ALTURA - 6, "text-anchor": "middle" });
        r.textContent = textoRotulo(cat);
        g.append(r);
      }
      if (i === indiceMaior && series.length === 1) { // rótulo direto só no maior valor
        const r = svg("text", { class: "rotulo-valor", x: x + espessura / 2, y: base - 6, "text-anchor": "middle" });
        r.textContent = formatar(totais[i]);
        g.append(r);
      }
    });
    area.replaceChildren(raiz);
    renderLegenda(legenda, series, "area");
    renderTabela(tabela, [cfg.tituloCategoria || "Categoria", ...series.map((s) => s.nome), ...(series.length > 1 ? ["Total"] : [])],
      cfg.categorias.map((c, i) => [c, ...series.map((s) => formatar(s.valores[i] || 0)), ...(series.length > 1 ? [formatar(totais[i])] : [])]));
  }

  function retangulo(x, y, larg, alt, raio) {
    if (!raio) return `M${x},${y}h${larg}v${alt}h${-larg}Z`;
    return `M${x},${y + alt}V${y + raio}Q${x},${y} ${x + raio},${y}H${x + larg - raio}Q${x + larg},${y} ${x + larg},${y + raio}V${y + alt}Z`;
  }

  /**
   * Mapa de calor linhas × colunas (ex: dia da semana × hora) com rampa
   * sequencial de um só tom em 5 degraus; zero fica na cor neutra da superfície.
   * cfg = { linhas: [...], colunas: [...], matriz: [[...]], formatar(v), rotuloColuna(c), vazio }
   */
  function mapaCalor(fig, cfg) {
    const valores = cfg.matriz.flat();
    const max = Math.max(0, ...valores);
    if (!max) { vazio(fig, cfg.vazio || "Sem dados neste período."); return; }
    const { area, legenda, tabela } = estrutura(fig);
    const W = largura(area);
    const esq = 44, topo = 6, baixo = 22;
    const larguraCel = Math.max(10, (W - esq - 8) / cfg.colunas.length);
    const alturaCel = 22;
    const H = topo + alturaCel * cfg.linhas.length + baixo;
    const degrau = (v) => (v <= 0 ? 0 : Math.min(5, Math.ceil((v / max) * 5)));
    const formatar = cfg.formatar || ((v) => numero(v));
    const rotCol = cfg.rotuloColuna || ((c) => String(c));
    const raiz = svg("svg", { class: "grafico-svg", width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", tabindex: "0",
      "aria-label": `${fig.dataset.titulo}. Use as setas para percorrer as células; os valores estão na tabela abaixo.` });
    const celulas = [];
    cfg.linhas.forEach((linha, i) => {
      const r = svg("text", { class: "rotulo-eixo", x: esq - 8, y: topo + i * alturaCel + alturaCel / 2 + 4, "text-anchor": "end" });
      r.textContent = linha;
      raiz.append(r);
      cfg.colunas.forEach((col, j) => {
        const v = cfg.matriz[i][j];
        const x = esq + j * larguraCel, y = topo + i * alturaCel;
        const cel = svg("rect", { class: `celula-calor calor-${degrau(v)}`, x: x + 1, y: y + 1, width: larguraCel - 2, height: alturaCel - 2, rx: 3 });
        const mostrar = () => { marcar(i, j); mostrarTooltip(raiz, x + larguraCel, y, `${linha}, ${rotCol(col)}`, [{ nome: cfg.nomeValor || "", valor: formatar(v), cor: 1, forma: "area" }]); };
        cel.addEventListener("pointerenter", mostrar);
        cel.addEventListener("pointerleave", () => { cel.classList.remove("ativa"); esconderTooltip(); });
        raiz.append(cel);
        celulas.push({ cel, i, j, mostrar });
      });
    });
    const passo = Math.ceil(28 / larguraCel);
    cfg.colunas.forEach((col, j) => {
      if (j % passo) return;
      const r = svg("text", { class: "rotulo-eixo", x: esq + j * larguraCel + larguraCel / 2, y: H - 6, "text-anchor": "middle" });
      r.textContent = rotCol(col);
      raiz.append(r);
    });
    let atual = { i: 0, j: 0 };
    function marcar(i, j) { celulas.forEach((c) => c.cel.classList.toggle("ativa", c.i === i && c.j === j)); atual = { i, j }; }
    raiz.addEventListener("keydown", (ev) => {
      const d = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] }[ev.key];
      if (ev.key === "Escape") { esconderTooltip(); return; }
      if (!d) return;
      ev.preventDefault();
      const i = Math.max(0, Math.min(cfg.linhas.length - 1, atual.i + d[0]));
      const j = Math.max(0, Math.min(cfg.colunas.length - 1, atual.j + d[1]));
      celulas.find((c) => c.i === i && c.j === j).mostrar();
    });
    raiz.addEventListener("focus", () => celulas.find((c) => c.i === atual.i && c.j === atual.j).mostrar());
    raiz.addEventListener("blur", () => { celulas.forEach((c) => c.cel.classList.remove("ativa")); esconderTooltip(); });
    area.replaceChildren(raiz);
    // Legenda da escala (sequencial): faixas de valor por degrau.
    legenda.replaceChildren(html("li", { class: "escala-titulo" }, cfg.nomeValor || "Quantidade"),
      ...[0, 1, 2, 3, 4, 5].map((k) => {
        const de = Math.floor(((k - 1) / 5) * max) + 1, ate = Math.ceil((k / 5) * max);
        const texto = k === 0 ? "0" : de >= ate ? String(ate) : `${de}–${ate}`;
        return html("li", {}, html("span", { class: `chave chave-area celula-legenda calor-${k}`, "aria-hidden": "true" }), texto);
      }).filter((_li, k, arr) => k === 0 || arr[k].textContent !== arr[k - 1].textContent));
    renderTabela(tabela, ["", ...cfg.colunas.map(rotCol)], cfg.linhas.map((l, i) => [l, ...cfg.matriz[i].map((v) => formatar(v))]));
  }

  /** Mini gráfico de tendência para os cards (sem eixos; o card traz o número). */
  function sparkline(valores, rotulo) {
    const vals = valores.map((v) => (v === null || v === undefined ? null : v));
    const validos = vals.filter((v) => v !== null);
    const W = 88, H = 24;
    const raiz = svg("svg", { class: "sparkline", width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": rotulo });
    if (validos.length < 2) return raiz;
    const max = Math.max(...validos), min = Math.min(...validos);
    const x = (i) => 2 + (i / (vals.length - 1)) * (W - 8);
    const y = (v) => H - 3 - (max > min ? ((v - min) / (max - min)) * (H - 6) : (H - 6) / 2);
    let d = "", caneta = false, ultimo = null;
    vals.forEach((v, i) => { if (v === null) { caneta = false; return; } d += `${caneta ? "L" : "M"}${x(i)},${y(v)}`; caneta = true; ultimo = [x(i), y(v)]; });
    raiz.append(svg("path", { class: "sparkline-linha", d }));
    if (ultimo) raiz.append(svg("circle", { class: "sparkline-ponto", cx: ultimo[0], cy: ultimo[1], r: 3 }));
    return raiz;
  }

  /** Seta de tendência comparando a média do último terço com a do primeiro. */
  function tendencia(valores) {
    const v = valores.filter((x) => x !== null && x !== undefined);
    if (v.length < 6) return null;
    const terco = Math.floor(v.length / 3);
    const media = (a) => a.reduce((s, x) => s + x, 0) / a.length;
    const inicio = media(v.slice(0, terco)), fim = media(v.slice(-terco));
    if (!inicio && !fim) return "estavel";
    const variacao = (fim - inicio) / (Math.abs(inicio) || 1);
    return variacao > 0.15 ? "subindo" : variacao < -0.15 ? "caindo" : "estavel";
  }

  return { serieTempo, barras, mapaCalor, sparkline, tendencia, vazio, esconderTooltip, numero, hora };
})();
