"""
Teste ponta a ponta da Interface Web num navegador real (Playwright + Edge ou
Chrome já instalados no sistema), com o MOTOR REAL rodando contra o SIGAA
simulado de test_engine_fluxo.py — nenhuma requisição sai do computador.

Opcional: é pulado se o Playwright não estiver instalado (não é dependência
do programa). Para rodar:
    pip install playwright pytest
    python -m pytest tests/test_web_e2e.py
Screenshots vão para a pasta indicada em SIGAA_SNIPER_SCREENSHOTS (se definida).
"""
from __future__ import annotations

import os
import re
import threading

import httpx
import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from app.core import engine  # noqa: E402
from app.web import estado as estado_mod  # noqa: E402
from app.web.estado import EstadoWeb  # noqa: E402
from app.web.server import criar_servidor  # noqa: E402
from tests.test_engine_fluxo import SigaaSimulado  # noqa: E402

PASTA_FOTOS = os.environ.get("SIGAA_SNIPER_SCREENSHOTS")


def foto(pagina, nome):
    if PASTA_FOTOS:
        os.makedirs(PASTA_FOTOS, exist_ok=True)
        pagina.screenshot(path=os.path.join(PASTA_FOTOS, f"{nome}.png"), full_page=True)


@pytest.fixture
def servidor(monkeypatch):
    simulado = SigaaSimulado(vagas=3)
    original = httpx.AsyncClient
    monkeypatch.setattr(engine.httpx, "AsyncClient",
                        lambda *a, **k: original(*a, **{**k, "transport": httpx.MockTransport(simulado)}))

    from app.core.diagnostics import ResultadoChecagem

    async def conectividade_simulada():
        return ResultadoChecagem("Conectividade com o SIGAA", True, "HTTP 200 (simulado no teste)")

    monkeypatch.setattr(estado_mod, "checar_conectividade_sigaa", conectividade_simulada)

    e = EstadoWeb()
    s = criar_servidor(e, "127.0.0.1", 0)
    threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    yield e, s, simulado
    s.shutdown()
    s.server_close()
    e.finalizar()


@pytest.fixture
def navegador():
    with sync_api.sync_playwright() as pw:
        nav = None
        for canal in ("msedge", "chrome", None):
            try:
                nav = pw.chromium.launch(channel=canal, headless=True) if canal else pw.chromium.launch(headless=True)
                break
            except Exception:
                continue
        if nav is None:
            pytest.skip("nenhum navegador Chromium disponível")
        yield nav
        nav.close()


def test_fluxo_completo_no_navegador(servidor, navegador):
    e, s, simulado = servidor
    ctx = navegador.new_context(viewport={"width": 1366, "height": 900}, locale="pt-BR")
    pagina = ctx.new_page()
    erros_console = []
    # 400/409 são respostas esperadas (validação/confirmação); o navegador as
    # registra como "Failed to load resource" — isso não é erro de JavaScript.
    pagina.on("console", lambda m: erros_console.append(m.text)
              if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
    pagina.on("pageerror", lambda ex: erros_console.append(str(ex)))
    expect = sync_api.expect

    pagina.goto(f"http://127.0.0.1:{s.porta}/?chave={s.chave}")
    assert "chave=" not in pagina.url  # a chave some da barra de endereço

    # ── Aviso legal: 5 confirmações obrigatórias ──
    aviso = pagina.locator("#dialogo-aviso")
    expect(aviso).to_be_visible()
    pagina.set_viewport_size({"width": 1366, "height": 900})
    foto(pagina, "01_aviso_legal")
    aceitar = pagina.locator("#aviso-aceitar")
    caixas = pagina.locator("#aviso-itens input[type=checkbox]")
    assert caixas.count() == 5
    pagina.locator("#aviso-itens summary").first.click()  # clicar no texto NÃO marca a caixa
    assert not caixas.first.is_checked()
    pagina.keyboard.press("Escape")  # Esc não fecha o aviso
    expect(aviso).to_be_visible()
    for i in range(4):
        caixas.nth(i).check()
    expect(aceitar).to_be_disabled()
    caixas.nth(4).check()
    expect(aceitar).to_be_enabled()
    aceitar.click()
    expect(aviso).to_be_hidden()

    # ── Assistente de primeira execução ──
    assistente = pagina.locator("#dialogo-assistente")
    expect(assistente).to_be_visible()
    pagina.locator("#assistente-proximo").click()
    pagina.locator("#assistente-conteudo input").first.fill("200012345")
    foto(pagina, "02_assistente")
    pagina.locator("#assistente-pular").click()
    expect(assistente).to_be_hidden()
    assert e.sessao.sigaa.usuario == ""  # pós-6.0.0: "Configurar depois" não salva nada pela metade

    # ── Credenciais ──
    pagina.click("#menu button[data-tela=credenciais]")
    pagina.fill("#form-credenciais [name=usuario]", "200012345")
    pagina.fill("#form-credenciais [name=senha]", "s3nh@")
    pagina.fill("#form-credenciais [name=cpf]", "12345678909")
    pagina.fill("#form-credenciais [name=nascimento]", "01/02/2003")
    pagina.click("#form-credenciais button[type=submit]")
    expect(pagina.locator(".toast-sucesso", has_text="memória")).to_be_visible()
    assert e.sessao.sigaa.preenchida()
    expect(pagina.locator("#cred-senha-dica")).to_be_visible()

    # ── Disciplinas: busca de departamento e confirmação de código desconhecido ──
    pagina.click("#menu button[data-tela=disciplinas]")
    pagina.click("#disc-adicionar")
    pagina.fill("#form-disciplina [name=codigo]", "fga0211")
    pagina.fill("#form-disciplina [name=turma]", "01")
    # Pós-6.0.0: digitar não abre lista; "Ver departamentos" mostra a lista completa pesquisável.
    pagina.fill("#disc-depto-busca", "gama")
    expect(pagina.locator("#disc-depto-selecionado")).to_contain_text("só o número")
    pagina.click("#disc-ver-deptos")
    expect(pagina.locator("#deptos-lista li").first).to_be_visible()
    assert pagina.locator("#deptos-lista li").count() > 100
    pagina.fill("#deptos-busca", "gama")
    pagina.locator("#deptos-lista .item-depto").first.click()
    expect(pagina.locator("#dialogo-departamentos")).to_be_hidden()
    expect(pagina.locator("#disc-depto-selecionado")).to_contain_text("673 — CAMPUS UNB GAMA")
    pagina.click("#form-disciplina button[type=submit]")
    expect(pagina.locator("#disc-linhas tr")).to_have_count(1)

    pagina.click("#disc-adicionar")
    pagina.fill("#form-disciplina [name=codigo]", "XYZ0001")
    pagina.fill("#form-disciplina [name=turma]", "09")
    pagina.fill("#disc-depto-busca", "99999")
    pagina.click("#form-disciplina button[type=submit]")
    expect(pagina.locator("#dialogo")).to_be_visible()
    expect(pagina.locator("#dialogo-titulo")).to_have_text("Código não reconhecido")
    pagina.locator("#dialogo-botoes button", has_text="Salvar mesmo assim").click()
    expect(pagina.locator("#disc-linhas tr")).to_have_count(2)
    # desativa a segunda para o motor só buscar FGA0211-01
    pagina.locator("#disc-linhas tr").nth(1).get_by_role("button", name=re.compile("Desativar")).click()
    expect(pagina.locator("#disc-linhas tr").nth(1)).to_contain_text("Não")
    foto(pagina, "03_disciplinas")

    # ── Execução real do motor (monitoramento) contra o SIGAA simulado ──
    pagina.click("#menu button[data-tela=execucao]")
    pagina.locator("input[name=modo][value=monitoramento]").check()
    expect(pagina.locator("#bloco-dry-run")).to_be_hidden()
    foto(pagina, "04_execucao")
    pagina.click("#botao-iniciar")
    expect(pagina.locator("#titulo-tela")).to_have_text("Dashboard")  # abre o dashboard ao iniciar
    expect(pagina.locator("#status-execucao")).to_have_attribute("data-estado", "executando")
    expect(pagina.locator("#dash-vagas li").first).to_contain_text("VAGA DETECTADA", timeout=20000)
    foto(pagina, "05_dashboard")
    pagina.click("#aba-dash-workers")  # a tabela de workers fica na aba "Workers" desde a Fase 2
    expect(pagina.locator("#dash-workers tr").first).to_be_visible()
    pagina.click("#aba-dash-geral")
    assert simulado.posts_selecao() == []  # monitoramento nunca seleciona turma

    # ── Logs ──
    pagina.click("#menu button[data-tela=logs]")
    expect(pagina.locator("#log-linhas tr").first).to_be_visible()
    pagina.select_option("#log-categoria", "SUCESSO")
    expect(pagina.locator("#log-linhas tr").first).to_contain_text("Vaga encontrada")
    pagina.locator("#log-linhas tr").first.click()
    expect(pagina.locator("#log-detalhe-corpo")).to_contain_text("vaga")
    pagina.locator("label:has(#log-tecnico)").click()
    expect(pagina.locator("#log-detalhe-tecnico")).to_contain_text("VAGA DETECTADA")
    foto(pagina, "06_logs")

    # ── Parar ──
    pagina.click("#menu button[data-tela=execucao]")
    pagina.click("#botao-parar")
    expect(pagina.locator("#status-execucao")).to_have_attribute("data-estado", "parado", timeout=20000)

    # ── Configurações avançadas: validação e confirmação de URL ──
    pagina.click("#menu button[data-tela=avancado]")
    expect(pagina.locator("#form-avancado [name=num_workers]")).to_have_value("20")  # formulário carregado
    pagina.fill("#form-avancado [name=num_workers]", "500")
    pagina.click("#form-avancado button[type=submit]")
    expect(pagina.locator("#dialogo")).to_be_visible()
    expect(pagina.locator("#dialogo-conteudo")).to_contain_text("workers")
    pagina.locator("#dialogo-botoes button").click()
    pagina.fill("#form-avancado [name=num_workers]", "4")
    pagina.fill("#form-avancado [name='url.sigaa_base']", "https://sigaa.exemplo")
    pagina.click("#form-avancado button[type=submit]")
    expect(pagina.locator("#dialogo-titulo")).to_have_text("Confirmar alteração de URLs")
    pagina.locator("#dialogo-botoes button", has_text="Cancelar").click()
    assert e.settings["num_workers"] == 20  # cancelou: nada salvo
    foto(pagina, "07_avancado")

    # ── Notificações sem canal: aviso claro ──
    pagina.click("#menu button[data-tela=notificacoes]")
    pagina.click("button[data-testar=todos]")
    expect(pagina.locator(".toast-aviso", has_text="Nenhum canal")).to_be_visible()
    foto(pagina, "08_notificacoes")

    # ── Diagnóstico, Experimental, Ajuda, Sobre ──
    pagina.click("#menu button[data-tela=diagnostico]")
    pagina.click("#diag-completo")
    expect(pagina.locator("#diag-itens li").first).to_be_visible(timeout=30000)
    expect(pagina.locator("#diag-itens")).to_contain_text("Modo configurado")
    foto(pagina, "09_diagnostico")
    pagina.click("#menu button[data-tela=experimental]")
    expect(pagina.locator("#exp-lista article")).to_have_count(3)
    pagina.click("#menu button[data-tela=ajuda]")
    expect(pagina.locator("#ajuda-conteudo h1")).to_contain_text("Guia de Uso")
    foto(pagina, "10_ajuda")
    pagina.click("#menu button[data-tela=sobre]")
    expect(pagina.locator("#sobre-repo")).to_contain_text("github.com")

    # ── Tema escuro e layout de celular ──
    pagina.click("#botao-tema")
    pagina.click("#menu button[data-tela=execucao]")
    foto(pagina, "11_execucao_escuro")
    pagina.set_viewport_size({"width": 390, "height": 844})
    expect(pagina.locator("#botao-menu")).to_be_visible()
    pagina.wait_for_timeout(400)  # fim da animação da barra lateral
    foto(pagina, "12_celular")
    pagina.click("#botao-menu")
    expect(pagina.locator("#barra-lateral")).to_have_class(re.compile("aberta"))
    pagina.click("#menu button[data-tela=dashboard]")
    expect(pagina.locator("#barra-lateral")).not_to_have_class(re.compile("aberta"))
    pagina.set_viewport_size({"width": 1366, "height": 900})

    # ── Encerrar ──
    pagina.click("#botao-encerrar")
    pagina.locator("#dialogo-botoes button", has_text="Encerrar").click()
    expect(pagina.locator("#tela-bloqueio")).to_be_visible()
    assert e.evento_encerrar.is_set()

    assert not erros_console, f"erros no console do navegador: {erros_console}"
    ctx.close()


def test_sem_chave_mostra_instrucao(servidor, navegador):
    _, s, _ = servidor
    pagina = navegador.new_page()
    resp = pagina.goto(f"http://127.0.0.1:{s.porta}/")
    assert resp.status == 403
    sync_api.expect(pagina.locator("h1")).to_contain_text("Link de acesso")
    pagina.close()


def _entrar(pagina, s):
    """Abre a página, aceita as 5 confirmações do aviso legal e pula o assistente."""
    expect = sync_api.expect
    pagina.goto(f"http://127.0.0.1:{s.porta}/?chave={s.chave}")
    caixas = pagina.locator("#aviso-itens input[type=checkbox]")
    expect(caixas).to_have_count(5)
    for i in range(5):
        caixas.nth(i).check()
    pagina.click("#aviso-aceitar")
    expect(pagina.locator("#dialogo-assistente")).to_be_visible()
    pagina.locator("#assistente-pular").click()
    expect(pagina.locator("#dialogo-assistente")).to_be_hidden()


def test_recursos_da_fase_1_no_navegador(servidor, navegador):
    e, s, _simulado = servidor
    expect = sync_api.expect
    ctx = navegador.new_context(viewport={"width": 1366, "height": 900}, locale="pt-BR")
    pagina = ctx.new_page()
    erros_console = []
    pagina.on("console", lambda m: erros_console.append(m.text)
              if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
    pagina.on("pageerror", lambda ex: erros_console.append(str(ex)))
    _entrar(pagina, s)

    # ── 002: paleta de ações (Ctrl+K) e atalhos G+letra / ? ──
    pagina.keyboard.press("Control+k")
    expect(pagina.locator("#dialogo-paleta")).to_be_visible()
    pagina.keyboard.type("logs")
    foto(pagina, "f1_01_paleta")
    pagina.keyboard.press("Enter")
    expect(pagina.locator("#dialogo-paleta")).to_be_hidden()
    expect(pagina.locator("#titulo-tela")).to_have_text("Logs")
    pagina.locator("#conteudo").focus()
    pagina.keyboard.press("g")
    pagina.keyboard.press("m")
    expect(pagina.locator("#titulo-tela")).to_have_text("Disciplinas")
    pagina.keyboard.press("?")
    expect(pagina.locator("#dialogo-titulo")).to_contain_text("Atalhos")
    pagina.keyboard.press("Escape")

    # ── 068: CPF inválido é apontado ──
    pagina.keyboard.press("g")
    pagina.keyboard.press("c")
    pagina.fill("#form-credenciais [name=usuario]", "200012345")
    pagina.fill("#form-credenciais [name=senha]", "s3nh@")
    pagina.fill("#form-credenciais [name=cpf]", "12345678900")
    pagina.fill("#form-credenciais [name=nascimento]", "01022003")
    pagina.click("#form-credenciais button[type=submit]")
    expect(pagina.locator("#dialogo-conteudo")).to_contain_text("CPF inválido")
    pagina.locator("#dialogo-botoes button").click()
    pagina.fill("#form-credenciais [name=cpf]", "12345678909")
    pagina.click("#form-credenciais button[type=submit]")
    expect(pagina.locator(".toast-sucesso", has_text="memória")).to_be_visible()
    assert e.sessao.sigaa.nascimento == "01/02/2003"

    # ── 005: cadastro em lote com pré-visualização ──
    pagina.click("#menu button[data-tela=disciplinas]")
    pagina.click("#disc-lote")
    pagina.fill("#lote-texto", "FGA0211 01 673\nMAT0025;02;518\nXYZ A 1")
    expect(pagina.locator("#lote-adicionar")).to_be_disabled()
    pagina.click("#lote-previa")
    expect(pagina.locator("#lote-linhas tr")).to_have_count(3)
    expect(pagina.locator("#lote-linhas")).to_contain_text("só os números")
    expect(pagina.locator("#lote-adicionar")).to_have_text("Adicionar 2")
    foto(pagina, "f1_02_lote")
    pagina.click("#lote-adicionar")
    expect(pagina.locator("#dialogo-lote")).to_be_hidden()
    expect(pagina.locator("#disc-linhas tr")).to_have_count(2)
    # desativa MAT0025 para o motor só buscar FGA0211-01 (a única que o SIGAA simulado conhece)
    pagina.locator("#disc-linhas tr").nth(1).get_by_role("button", name=re.compile("Desativar")).click()
    expect(pagina.locator("#disc-linhas tr").nth(1)).to_contain_text("Não")

    # ── 043: perfil de carga com estimativa ao vivo ──
    pagina.click("#menu button[data-tela=avancado]")
    expect(pagina.locator("#avancado-carga")).to_contain_text("(alta)")
    pagina.select_option("#avancado-preset", "leve")
    expect(pagina.locator("#form-avancado [name=num_workers]")).to_have_value("4")
    expect(pagina.locator("#avancado-carga")).to_contain_text("(baixa)")
    pagina.fill("#form-avancado [name=num_workers]", "7")
    expect(pagina.locator("#avancado-preset")).to_have_value("")
    pagina.select_option("#avancado-preset", "leve")
    foto(pagina, "f1_03_carga")
    pagina.click("#form-avancado button[type=submit]")
    expect(pagina.locator(".toast-sucesso", has_text="salvas")).to_be_visible()
    assert e.settings["num_workers"] == 4 and e.settings["intervalo_busca"] == 1.5
    pagina.click("#menu button[data-tela=execucao]")
    expect(pagina.locator("#checklist")).to_contain_text("Carga estimada")

    # ── 088: evento real do motor vira aviso em qualquer tela + central ──
    e.settings["abrir_dashboard_ao_iniciar"] = False
    e.settings["intervalo_busca"] = 0.2
    pagina.locator("input[name=modo][value=monitoramento]").check()
    pagina.click("#botao-iniciar")
    expect(pagina.locator("#status-execucao")).to_have_attribute("data-estado", "executando")
    pagina.click("#menu button[data-tela=credenciais]")
    expect(pagina.locator(".toast", has_text="Vaga encontrada em FGA0211-01")).to_be_visible(timeout=20000)
    expect(pagina.locator("#sino-contador")).to_be_visible()
    pagina.click("#botao-sino")
    expect(pagina.locator("#central-lista li", has_text="Vaga encontrada").first).to_be_visible()
    foto(pagina, "f1_04_central")
    pagina.click("#central-fechar")
    expect(pagina.locator("#sino-contador")).to_be_hidden()
    pagina.click("#menu button[data-tela=execucao]")
    pagina.click("#botao-parar")
    expect(pagina.locator("#status-execucao")).to_have_attribute("data-estado", "parado", timeout=20000)

    # ── 004: queda momentânea não derruba a página ──
    pagina.route("**/api/**", lambda rota: rota.abort())
    expect(pagina.locator("#faixa-conexao")).to_be_visible(timeout=10000)
    foto(pagina, "f1_05_reconectando")
    expect(pagina.locator("#tela-bloqueio")).to_be_hidden()
    pagina.unroute("**/api/**")
    expect(pagina.locator("#faixa-conexao")).to_be_hidden(timeout=15000)
    expect(pagina.locator(".toast", has_text="restabelecida")).to_be_visible()
    expect(pagina.locator("#app")).to_be_visible()

    assert not erros_console, f"erros no console do navegador: {erros_console}"
    ctx.close()


def test_queda_prolongada_bloqueia_a_pagina(servidor, navegador):
    _e, s, _ = servidor
    expect = sync_api.expect
    pagina = navegador.new_page()
    _entrar(pagina, s)
    pagina.route("**/api/**", lambda rota: rota.abort())
    expect(pagina.locator("#faixa-conexao")).to_be_visible(timeout=10000)
    # 5 tentativas (1+2+3+5+8 s) sem resposta → a página admite que a interface foi encerrada
    expect(pagina.locator("#tela-bloqueio")).to_be_visible(timeout=40000)
    expect(pagina.locator("#tela-bloqueio")).to_contain_text("encerrada")
    pagina.close()


def test_centro_de_operacoes_e_graficos(servidor, navegador):
    """Fase 2: estado por disciplina, saúde, gráficos com hover/teclado/tabela e resumo da execução."""
    e, s, simulado = servidor
    expect = sync_api.expect
    simulado.falhar_busca_a_cada = 4  # gera "sessão expirada" para os gráficos de erros
    ctx = navegador.new_context(viewport={"width": 1366, "height": 900}, locale="pt-BR")
    pagina = ctx.new_page()
    erros_console = []
    pagina.on("console", lambda m: erros_console.append(m.text)
              if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
    pagina.on("pageerror", lambda ex: erros_console.append(str(ex)))
    _entrar(pagina, s)
    e.sessao.sigaa.usuario, e.sessao.sigaa.senha = "200012345", "s3nh@"
    e.sessao.sigaa.cpf, e.sessao.sigaa.nascimento = "12345678909", "01/02/2003"
    e.adicionar_disciplina({"codigo": "FGA0211", "turma": "01", "departamento": 673})
    e.settings.update({"num_workers": 2, "intervalo_busca": 0.2})

    # Monitoramento: roda até pararmos, dando tempo de gerar séries.
    pagina.click("#menu button[data-tela=execucao]")
    pagina.locator("input[name=modo][value=monitoramento]").check()
    pagina.click("#botao-iniciar")
    expect(pagina.locator("#titulo-tela")).to_have_text("Dashboard")
    alvo = pagina.locator("#dash-alvos .cartao-alvo").first
    expect(alvo).to_contain_text("FGA0211-01")
    expect(alvo).to_contain_text("Vaga vista", timeout=20000)
    expect(pagina.locator("#dash-saude-indicadores")).to_contain_text("Resposta agora")
    expect(pagina.locator("#dash-erros-grupos")).to_contain_text("Sessão expirada", timeout=15000)
    expect(pagina.locator("#dash-cards svg.sparkline").first).to_be_attached()
    pagina.wait_for_timeout(3500)  # alguns segundos de série temporal
    foto(pagina, "f2_01_visao_geral")

    pagina.click("#aba-dash-graficos")
    expect(pagina.locator("#graf-latencia svg.grafico-svg")).to_be_visible(timeout=10000)
    expect(pagina.locator("#graf-rps path.linha")).to_have_count(1)
    expect(pagina.locator("#graf-vagas path.linha")).to_have_count(1)
    expect(pagina.locator("#graf-histograma .barra").first).to_be_attached()
    expect(pagina.locator("#graf-latencia .grafico-legenda li")).to_have_count(2)  # 2 séries → legenda
    expect(pagina.locator("#graf-rps .grafico-legenda li")).to_have_count(0)       # 1 série → sem legenda
    # Hover: cruz + tooltip com o valor
    # hover() espera e repete sozinho: o gráfico é redesenhado a cada segundo (evita corrida com o elemento antigo)
    pagina.locator("#graf-rps .alvo-hover").hover()
    expect(pagina.locator("#grafico-tooltip")).to_be_visible()
    expect(pagina.locator("#grafico-tooltip")).to_contain_text("/s")
    foto(pagina, "f2_02_graficos")
    # Teclado: foco no gráfico mostra a leitura; setas navegam
    pagina.locator("#graf-latencia svg.grafico-svg").focus()
    pagina.keyboard.press("ArrowLeft")
    expect(pagina.locator("#grafico-tooltip")).to_contain_text("Mediana")
    # Tabela de dados (a informação nunca depende só de cor/hover)
    pagina.locator("#graf-latencia .grafico-tabela summary").click()
    expect(pagina.locator("#graf-latencia .grafico-tabela tbody tr").first).to_be_visible()
    expect(pagina.locator("#graf-erros polygon.area-empilhada").first).to_be_attached()
    expect(pagina.locator("#graf-erros")).not_to_contain_text("Nenhum erro")
    # Período
    pagina.click("#dash-janela button[data-janela='0']")
    expect(pagina.locator("#dash-janela button[data-janela='0']")).to_have_attribute("aria-pressed", "true")

    pagina.click("#aba-dash-workers")
    expect(pagina.locator("#dash-workers tr")).to_have_count(2)
    expect(pagina.locator("#graf-workers .segmento").first).to_be_attached()
    foto(pagina, "f2_05_workers")

    pagina.click("#dash-parar")
    expect(pagina.locator("#status-execucao")).to_have_attribute("data-estado", "parado", timeout=20000)
    expect(pagina.locator("#dash-ver-resumo")).to_be_visible(timeout=10000)
    pagina.click("#aba-dash-geral")
    pagina.click("#dash-ver-resumo")
    expect(pagina.locator("#dialogo-conteudo")).to_contain_text("Interrompida pelo usuário")
    expect(pagina.locator("#dialogo-conteudo")).to_contain_text("FGA0211-01")
    foto(pagina, "f2_03_resumo")
    pagina.keyboard.press("Escape")

    # Tema escuro nos gráficos
    pagina.click("#botao-tema")
    pagina.click("#aba-dash-graficos")
    expect(pagina.locator("#graf-latencia svg.grafico-svg")).to_be_visible()
    pagina.wait_for_timeout(300)
    foto(pagina, "f2_04_graficos_escuro")
    assert not erros_console, f"erros no console do navegador: {erros_console}"
    ctx.close()


def test_historico_no_navegador(servidor, navegador, tmp_path):
    """Fase 3: filtros, mapa de calor, comparação, detalhe, impressão e exportação."""
    import time as _time
    from datetime import datetime
    from app.core import historico
    from tests.test_historico import _resumo
    e, s, _ = servidor
    expect = sync_api.expect
    agora = datetime.now().replace(microsecond=0, second=0)
    t = agora.timestamp()
    historico.registrar_execucao(_resumo("exec-hoje", agora, duracao=3600, vagas=3, erros=5, workers=20), {
        "vagas_series": {"FGA0211-01": [[t - 600, 0], [t, 2], [t + 300, 0]]},
        "pontos": [{"t": t + i, "req": 6, "p50": 150 + (i % 60), "p95": 400, "erros": {}} for i in range(0, 600, 5)]})
    antigo = datetime.fromtimestamp(_time.time() - 45 * 86400).replace(microsecond=0)
    historico.registrar_execucao(_resumo("exec-antiga", antigo, duracao=1800, vagas=1, workers=4), {
        "vagas_series": {"FGA0211-01": [[antigo.timestamp() + 60, 1]]},
        "pontos": [{"t": antigo.timestamp() + i, "req": 2, "p50": 300, "p95": 700, "erros": {}} for i in range(0, 600, 5)]})
    ctx = navegador.new_context(viewport={"width": 1366, "height": 900}, locale="pt-BR", accept_downloads=True)
    pagina = ctx.new_page()
    erros_console = []
    pagina.on("console", lambda m: erros_console.append(m.text)
              if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
    pagina.on("pageerror", lambda ex: erros_console.append(str(ex)))
    _entrar(pagina, s)

    pagina.click("#menu button[data-tela=historico]")
    expect(pagina.locator("#hist-linhas tr")).to_have_count(1)  # padrão: últimos 30 dias
    pagina.click("#hist-periodo button[data-dias='0']")
    expect(pagina.locator("#hist-linhas tr")).to_have_count(2)
    expect(pagina.locator("#hist-cards")).to_contain_text("Horas monitoradas")
    expect(pagina.locator("#graf-hist-mapa rect.celula-calor")).to_have_count(7 * 24)
    expect(pagina.locator("#graf-hist-mapa rect.calor-5")).to_have_count(2)  # uma abertura em cada execução (máximo = 1)
    expect(pagina.locator("#graf-hist-vagas .barra")).to_have_count(2)
    foto(pagina, "f3_01_historico")

    pagina.select_option("#hist-disciplina", "FGA0211-01")
    expect(pagina.locator("#hist-linhas tr")).to_have_count(2)

    # Comparação (duas execuções)
    caixas = pagina.locator("#hist-linhas input[type=checkbox]")
    caixas.nth(0).check()
    expect(pagina.locator("#hist-comparar")).to_be_disabled()
    caixas.nth(1).check()
    pagina.click("#hist-comparar")
    expect(pagina.locator("#hist-comparacao")).to_be_visible()
    expect(pagina.locator("#hist-comparacao-tabela")).to_contain_text("Workers")
    expect(pagina.locator("#graf-hist-comparacao path.linha")).to_have_count(2)
    foto(pagina, "f3_02_comparacao")

    # Detalhe + impressão
    pagina.locator("#hist-linhas tr").first.get_by_role("button", name="Ver").click()
    expect(pagina.locator("#hist-detalhe")).to_be_visible()
    expect(pagina.locator("#hist-detalhe-conteudo")).to_contain_text("FGA0211-01")
    expect(pagina.locator("#graf-hist-det-latencia path.linha")).to_have_count(2)
    pagina.evaluate("window.print = () => { window.__classesNaImpressao = document.body.className + '|' + document.querySelector('#hist-detalhe').className; }")
    pagina.click("#hist-imprimir")
    assert "modo-impressao" in pagina.evaluate("window.__classesNaImpressao") and "imprimir-alvo" in pagina.evaluate("window.__classesNaImpressao")
    pagina.emulate_media(media="print")
    foto(pagina, "f3_03_impressao")
    pagina.emulate_media(media="screen")

    # Exportações (download de arquivo)
    pagina.click("#hist-exportar")
    with pagina.expect_download() as info:
        pagina.click("#hist-exportar-lista button[data-tipo=execucoes][data-formato=csv]")
    caminho = tmp_path / "hist.csv"
    info.value.save_as(caminho)
    conteudo = caminho.read_text(encoding="utf-8-sig")
    assert "exec-hoje" in conteudo and "exec-antiga" in conteudo and conteudo.startswith("id;")

    pagina.click("#menu button[data-tela=logs]")
    pagina.wait_for_timeout(300)
    pagina.click("#log-exportar-csv")  # sem eventos: avisa em vez de baixar arquivo vazio
    expect(pagina.locator(".toast", has_text="Nenhum evento")).to_be_visible()

    # Apagar (pede confirmação)
    pagina.click("#menu button[data-tela=historico]")
    pagina.click("#hist-apagar")
    expect(pagina.locator("#dialogo-titulo")).to_have_text("Apagar histórico")
    pagina.locator("#dialogo-botoes button", has_text="Apagar tudo").click()
    expect(pagina.locator("#hist-vazio")).to_be_visible()
    assert not erros_console, f"erros no console do navegador: {erros_console}"
    ctx.close()


def test_automacao_avancada_no_navegador(servidor, navegador):
    """Fase 4: verificação prévia, pausar/retomar, grupo de alternativas e opções de execução."""
    e, s, simulado = servidor
    expect = sync_api.expect
    simulado.vagas = 0
    ctx = navegador.new_context(viewport={"width": 1366, "height": 900}, locale="pt-BR")
    pagina = ctx.new_page()
    erros_console = []
    pagina.on("console", lambda m: erros_console.append(m.text)
              if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
    pagina.on("pageerror", lambda ex: erros_console.append(str(ex)))
    _entrar(pagina, s)
    e.sessao.sigaa.usuario, e.sessao.sigaa.senha = "200012345", "s3nh@"
    e.sessao.sigaa.cpf, e.sessao.sigaa.nascimento = "12345678909", "01/02/2003"
    e.settings.update({"num_workers": 1, "intervalo_busca": 0.1})

    # Disciplinas com grupo e prioridade pelo formulário
    pagina.click("#menu button[data-tela=disciplinas]")
    for turma in ("01", "09"):
        pagina.click("#disc-adicionar")
        pagina.fill("#form-disciplina [name=codigo]", "FGA0211")
        pagina.fill("#form-disciplina [name=turma]", turma)
        pagina.fill("#disc-depto-busca", "673")
        pagina.fill("#form-disciplina [name=grupo]", "calculo")
        pagina.select_option("#form-disciplina [name=prioridade]", "alta" if turma == "01" else "baixa")
        pagina.click("#form-disciplina button[type=submit]")
        expect(pagina.locator("#dialogo-disciplina")).to_be_hidden()
    expect(pagina.locator("#disc-linhas")).to_contain_text("calculo")
    expect(pagina.locator("#disc-linhas tr").nth(1)).to_contain_text("Baixa")

    # Opções de execução + verificação prévia
    pagina.click("#menu button[data-tela=execucao]")
    pagina.locator("input[name=modo][value=monitoramento]").check()
    pagina.locator("#exec-mais summary").click()
    expect(pagina.locator("#exec-verificacao")).to_be_checked()
    expect(pagina.locator("#exec-janela-dias input")).to_have_count(7)
    foto(pagina, "f4_01_opcoes_execucao")
    pagina.click("#botao-iniciar")
    expect(pagina.locator("#titulo-tela")).to_have_text("Dashboard")
    expect(pagina.locator("#dash-alvos .cartao-alvo").nth(1)).to_contain_text("Verificação prévia", timeout=20000)
    expect(pagina.locator("#dash-alvos .cartao-alvo").nth(1)).to_contain_text("turma 09 não")
    expect(pagina.locator(".toast", has_text="Verificação prévia")).to_be_visible()

    # Pausar e retomar
    expect(pagina.locator("#dash-pausar")).to_be_visible()
    pagina.click("#dash-pausar")
    expect(pagina.locator("#status-execucao")).to_have_attribute("data-estado", "pausado", timeout=10000)
    expect(pagina.locator("#dash-fase")).to_contain_text("Pausado pelo usuário")
    foto(pagina, "f4_02_pausado")
    pagina.click("#dash-pausar")
    expect(pagina.locator("#status-execucao")).to_have_attribute("data-estado", "executando", timeout=10000)

    # Uma vaga aparece: a turma 01 é simulada (DRY RUN não se aplica ao monitoramento → só vaga vista)
    pagina.click("#dash-parar")
    expect(pagina.locator("#status-execucao")).to_have_attribute("data-estado", "parado", timeout=20000)
    assert not erros_console, f"erros no console do navegador: {erros_console}"
    ctx.close()


def test_observabilidade_no_navegador(servidor, navegador, raiz_temporaria):
    """Fase 5: tentativas, linha do tempo, assistente, segurança, páginas capturadas, pacote e teste de URLs."""
    import time as _time

    from app.core.config import Disciplina, salvar_disciplinas
    e, s, simulado = servidor
    expect = sync_api.expect
    ctx = navegador.new_context(viewport={"width": 1366, "height": 900}, locale="pt-BR")
    pagina = ctx.new_page()
    erros_console = []
    pagina.on("console", lambda m: erros_console.append(m.text)
              if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
    pagina.on("pageerror", lambda ex: erros_console.append(str(ex)))
    _entrar(pagina, s)
    e.sessao.sigaa.usuario, e.sessao.sigaa.senha = "200012345", "s3nh@"
    e.sessao.sigaa.cpf, e.sessao.sigaa.nascimento = "12345678909", "01/02/2003"
    e.settings.update({"num_workers": 1, "intervalo_busca": 0.1})
    e.disciplinas = [Disciplina("FGA0211", "01", 673)]
    salvar_disciplinas(e.disciplinas)

    # DRY RUN com vaga: a tentativa aparece com as etapas e os tempos.
    pagina.click("#menu button[data-tela=execucao]")
    pagina.locator("input[name=modo][value=matricula]").check()
    expect(pagina.locator("#exec-dry-run")).to_be_checked()
    pagina.click("#botao-iniciar")
    expect(pagina.locator("#titulo-tela")).to_have_text("Dashboard")
    expect(pagina.locator("#dash-tentativas")).to_contain_text("Sucesso (DRY RUN)", timeout=20000)
    expect(pagina.locator("#dash-tentativas")).to_contain_text("turma selecionada")
    expect(pagina.locator("#status-execucao")).to_have_attribute("data-estado", "parado", timeout=20000)
    foto(pagina, "f5_01_tentativas")

    # Linha do tempo: eventos marcantes, filtro por tipo e detalhe da tentativa.
    pagina.click("#aba-dash-tempo")
    itens = pagina.locator("#lt-itens .lt-item")
    expect(itens.first).to_contain_text("Nova execução iniciada", timeout=10000)
    expect(pagina.locator("#lt-itens")).to_contain_text("Tentando garantir a vaga")
    expect(pagina.locator("#lt-itens")).not_to_contain_text("Sem vagas no momento")
    total = itens.count()
    pagina.locator("#lt-categorias .chip", has_text="Login").click()
    expect(pagina.locator("#lt-categorias .chip", has_text="Login")).to_have_attribute("aria-pressed", "false")
    assert itens.count() < total
    foto(pagina, "f5_02_linha_do_tempo")
    pagina.locator("#lt-itens button", has_text="Ver etapas").first.click()
    expect(pagina.locator("#dialogo-conteudo")).to_contain_text("tela de confirmação recebida")
    pagina.keyboard.press("Escape")

    # Diagnóstico: assistente, segurança, recomendações, páginas capturadas e pacote de suporte.
    os.makedirs(raiz_temporaria / "logs", exist_ok=True)
    (raiz_temporaria / "logs" / f"debug_W0_selecao_falha_FGA0211_{int(_time.time())}.html").write_text(
        "<html><div id='info-usuario'>JOAO DA SILVA</div><p>Turma lotada, tente outra.</p></html>", encoding="utf-8")
    pagina.click("#menu button[data-tela=diagnostico]")
    expect(pagina.locator("#assist-sintomas button")).to_have_count(6)
    pagina.locator("#assist-sintomas button", has_text="matrícula não confirma").click()
    expect(pagina.locator("#assist-resultado")).to_contain_text("DRY RUN está ligado")
    expect(pagina.locator("#assist-resultado")).to_contain_text("Confirmado")
    expect(pagina.locator("#seg-itens")).to_contain_text("Nenhuma configuração insegura")
    expect(pagina.locator("#rec-itens")).to_contain_text("Nenhuma recomendação agora")
    expect(pagina.locator("#dumps-itens tr")).to_have_count(1)
    pagina.locator("#dumps-itens button", has_text="Ver").click()
    expect(pagina.locator("#dialogo-conteudo pre")).to_contain_text("Turma lotada")
    expect(pagina.locator("#dialogo-conteudo pre")).not_to_contain_text("JOAO")
    foto(pagina, "f5_03_pagina_capturada")
    pagina.keyboard.press("Escape")
    pagina.click("#suporte-previa")
    expect(pagina.locator("#suporte-itens")).to_contain_text("LEIA-ME.txt")
    expect(pagina.locator("#suporte-itens")).to_contain_text("paginas/")
    with pagina.expect_download() as baixado:
        pagina.click("#suporte-baixar")
    assert baixado.value.suggested_filename.endswith(".zip")
    foto(pagina, "f5_04_diagnostico")

    # Testar endereços: nada fora de unb.br é acessado.
    pagina.click("#menu button[data-tela=avancado]")
    campos = pagina.locator("#avancado-urls input")
    expect(campos.first).to_be_visible()
    for i in range(campos.count()):
        campos.nth(i).fill("https://exemplo.invalid/x")
    pagina.click("#avancado-testar-urls")
    expect(pagina.locator("#avancado-urls-teste li")).to_have_count(campos.count())
    expect(pagina.locator("#avancado-urls-teste")).to_contain_text("Não testado: fora do domínio unb.br")
    assert not erros_console, f"erros no console do navegador: {erros_console}"
    ctx.close()


def test_recursos_pro_no_navegador(servidor, navegador, raiz_temporaria):
    """Fase 6: demonstração, perfis, versões, ações registradas, janelas de vaga, novos canais, exibição e tour."""
    from tests.test_recursos_pro import _historico_com_aberturas
    e, s, _simulado = servidor
    expect = sync_api.expect
    ctx = navegador.new_context(viewport={"width": 1366, "height": 900}, locale="pt-BR")
    pagina = ctx.new_page()
    erros_console = []
    pagina.on("console", lambda m: erros_console.append(m.text)
              if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
    pagina.on("pageerror", lambda ex: erros_console.append(str(ex)))
    _entrar(pagina, s)
    e.settings.update({"num_workers": 2, "intervalo_busca": 0.1})

    # 077: demonstração sem credenciais e sem disciplinas (usa as de exemplo)
    pagina.click("#menu button[data-tela=execucao]")
    pagina.locator("label.bloco-demo").click()  # o interruptor é clicado pelo rótulo, como faz uma pessoa
    expect(pagina.locator("#exec-demo")).to_be_checked()
    expect(pagina.locator("#checklist")).to_contain_text("Demonstração: credenciais fictícias")
    pagina.click("#botao-iniciar")
    expect(pagina.locator("#selo-demo")).to_be_visible(timeout=10000)
    expect(pagina.locator("#status-execucao")).to_contain_text("DEMONSTRAÇÃO")
    foto(pagina, "f6_01_demonstracao")
    pagina.click("#menu button[data-tela=execucao]")
    pagina.click("#botao-parar")
    expect(pagina.locator("#status-execucao")).to_have_attribute("data-estado", "parado", timeout=20000)

    # 042 / 045: perfil salvo e aplicado; versão anterior restaurada
    pagina.click("#menu button[data-tela=avancado]")
    pagina.fill("#form-perfil [name=nome]", "Calmo")
    pagina.click("#form-perfil button[type=submit]")
    expect(pagina.locator("#perfis-lista")).to_contain_text("Calmo")
    campo_workers = pagina.locator("#form-avancado [name=num_workers]")
    campo_workers.fill("6")
    pagina.click("#form-avancado button[type=submit]")
    expect(pagina.locator(".toast", has_text="Configurações avançadas salvas")).to_be_visible()
    pagina.locator("#perfis-lista button", has_text="Aplicar").click()
    pagina.locator("#dialogo-botoes button", has_text="Aplicar perfil").click()
    expect(pagina.locator(".toast", has_text="aplicado")).to_be_visible()
    expect(campo_workers).to_have_value("2")
    expect(pagina.locator("#versoes-lista tr").first).to_be_visible()
    foto(pagina, "f6_02_perfis_versoes")

    # 062/063: ações registradas no Histórico; 091: janelas prováveis
    _historico_com_aberturas([8, 8, 9, 9, 9, 8])
    pagina.click("#menu button[data-tela=historico]")
    expect(pagina.locator("#auditoria-lista")).to_contain_text("Aceitou o aviso legal")
    expect(pagina.locator("#auditoria-lista")).to_contain_text("Aplicou um perfil")
    expect(pagina.locator("#janelas-lista")).to_contain_text("surgiram entre 8h e 10h")
    expect(pagina.locator("#janelas-lista .faixa-horas .hora")).to_have_count(24)
    pagina.locator("#janelas-lista button", has_text="Usar como janela diária").click()
    pagina.locator("#dialogo-botoes button", has_text="Usar janela").click()
    expect(pagina.locator(".toast", has_text="Janela diária definida")).to_be_visible()
    assert e.settings["janela"]["ativa"] is True
    foto(pagina, "f6_03_historico_janelas")

    # 080-082 / 065: novos canais e texto do cofre
    pagina.click("#menu button[data-tela=notificacoes]")
    expect(pagina.locator("[name=webhook_formato]")).to_be_visible()
    expect(pagina.locator("#notif-cofre-texto")).not_to_be_empty()
    pagina.fill("[name='email.servidor']", "smtp.exemplo.com")
    pagina.select_option("[name=webhook_formato]", "slack")
    pagina.click("#form-notificacoes button[type=submit]")
    expect(pagina.locator(".toast", has_text="Configuração salva")).to_be_visible()
    assert e.settings["notificacoes"]["email"]["servidor"] == "smtp.exemplo.com"

    # 087: exibição compacta e texto maior
    pagina.click("#botao-exibicao")
    pagina.locator("#dialogo-conteudo button", has_text="Compacta").click()
    pagina.locator("#dialogo-conteudo button", has_text="115%").click()
    assert pagina.evaluate("document.documentElement.dataset.densidade") == "compacta"
    assert pagina.evaluate("getComputedStyle(document.body).fontSize") == "17.25px"
    pagina.keyboard.press("Escape")

    # 007: tour pela paleta de ações
    pagina.keyboard.press("Control+k")
    pagina.keyboard.type("tour")
    pagina.keyboard.press("Enter")
    expect(pagina.locator(".tour-balao")).to_contain_text("Passo 1 de")
    pagina.locator(".tour-balao button", has_text="Próximo").click()
    expect(pagina.locator(".tour-balao h2")).to_have_text("Execução")
    foto(pagina, "f6_04_tour")
    pagina.keyboard.press("Escape")
    expect(pagina.locator(".tour-balao")).to_have_count(0)
    assert not erros_console, f"erros no console do navegador: {erros_console}"
    ctx.close()


def test_assistente_inicial_e_dashboard_parado_no_navegador(servidor, navegador, raiz_temporaria):
    """Pós-6.0.0: assistente completo (validação, voltar, revisão) e Dashboard sem execução fantasma."""
    import json as _json
    import time as _time
    e, s, _simulado = servidor
    expect = sync_api.expect
    # Log de uma execução antiga, com erros — não pode aparecer como execução atual.
    os.makedirs(raiz_temporaria / "data", exist_ok=True)
    antigo = _time.time() - 7200
    linhas = [_json.dumps({"timestamp": _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(antigo + i)), "level": "WARNING",
                           "worker": "W1", "message": "⏳ Timeout (Socket Preso). Ressuscitando worker...", "evento": "timeout"})
              for i in range(30)]
    (raiz_temporaria / "data" / "sigaa_sniper_audit.json").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    e._tailer_dashboard.pular_para_o_fim()
    e._tailer_logs.pular_para_o_fim()

    ctx = navegador.new_context(viewport={"width": 1366, "height": 900}, locale="pt-BR")
    pagina = ctx.new_page()
    erros_console = []
    pagina.on("console", lambda m: erros_console.append(m.text)
              if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
    pagina.on("pageerror", lambda ex: erros_console.append(str(ex)))
    pagina.goto(f"http://127.0.0.1:{s.porta}/?chave={s.chave}")
    caixas = pagina.locator("#aviso-itens input[type=checkbox]")
    expect(caixas).to_have_count(5)
    for i in range(5):
        caixas.nth(i).check()
    pagina.click("#aviso-aceitar")
    assistente = pagina.locator("#dialogo-assistente")
    expect(assistente).to_be_visible()
    proximo = pagina.locator("#assistente-proximo")
    proximo.click()
    expect(pagina.locator("#assistente-passos")).to_contain_text("[Credenciais]")
    campos = pagina.locator("#assistente-conteudo input")
    campos.nth(0).fill("200012345")
    campos.nth(1).fill("s3nh@")
    campos.nth(2).fill("123.456.789-0")
    campos.nth(3).fill("31/13/2003")
    proximo.click()
    expect(pagina.locator("#assistente-erros")).to_contain_text("11 dígitos")
    expect(pagina.locator("#assistente-erros")).to_contain_text("Mês 13")
    foto(pagina, "p6_01_assistente_erros")
    campos.nth(2).fill("12345678909")
    campos.nth(3).fill("01/02/2003")
    proximo.click()
    expect(pagina.locator("#assistente-passos")).to_contain_text("[Disciplinas]")
    campos = pagina.locator("#assistente-conteudo input")
    campos.nth(0).fill("fga0211")
    campos.nth(1).fill("01")
    pagina.locator("#assistente-conteudo button", has_text="Ver departamentos").click()
    pagina.fill("#deptos-busca", "gama")
    pagina.locator("#deptos-lista .item-depto").first.click()
    expect(pagina.locator("#assistente-conteudo")).to_contain_text("673 — CAMPUS UNB GAMA")
    pagina.locator("#assistente-conteudo button", has_text="Adicionar esta disciplina").click()
    expect(pagina.locator(".disciplinas-assistente li")).to_have_count(1)
    proximo.click()
    expect(pagina.locator("#assistente-passos")).to_contain_text("[Execução]")
    proximo.click()
    expect(pagina.locator("#assistente-passos")).to_contain_text("[Notificações]")
    pagina.locator("#assistente-conteudo label.caixa", has_text="Webhook (Discord").click()
    pagina.locator("#assistente-conteudo input[type=password]").fill("http://inseguro")
    proximo.click()
    expect(pagina.locator("#assistente-erros")).to_contain_text("https://")
    pagina.locator("#assistente-conteudo label.caixa", has_text="Webhook (Discord").click()  # desliga
    proximo.click()
    expect(pagina.locator("#assistente-passos")).to_contain_text("[Painéis]")
    pagina.click("#assistente-voltar")
    expect(pagina.locator("#assistente-passos")).to_contain_text("[Notificações]")
    proximo.click()
    proximo.click()
    expect(pagina.locator("#assistente-passos")).to_contain_text("[Revisão]")
    expect(pagina.locator(".lista-resumo")).to_contain_text("FGA0211-01")
    foto(pagina, "p6_02_revisao")
    proximo.click()
    expect(assistente).to_be_hidden()
    expect(pagina.locator(".toast", has_text="Configuração inicial salva")).to_be_visible()
    pagina.keyboard.press("Escape")  # fecha o tour, se abrir
    assert e.disciplinas[0].chave() == "FGA0211-01" and e.sessao.sigaa.cpf == "123.456.789-09"

    # Dashboard sem execução: nada da execução antiga, nada correndo.
    pagina.click("#menu button[data-tela=dashboard]")
    expect(pagina.locator("#dash-saude")).to_have_text("⚪ Nenhuma execução em andamento")
    expect(pagina.locator("#dash-cards")).to_contain_text("Nenhuma execução em andamento")
    expect(pagina.locator("#dash-alerta")).to_be_hidden()
    antes = pagina.locator("#dash-cards").inner_text()
    pagina.wait_for_timeout(2500)
    assert pagina.locator("#dash-cards").inner_text() == antes
    foto(pagina, "p6_03_dashboard_parado")
    pagina.click("#menu button[data-tela=logs]")
    expect(pagina.locator("#log-vazio")).to_be_visible()
    assert not erros_console, f"erros no console do navegador: {erros_console}"
    ctx.close()
