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
    pagina.fill("[name=a_usuario]", "200012345")
    foto(pagina, "02_assistente")
    pagina.locator("#assistente-pular").click()
    expect(assistente).to_be_hidden()
    assert e.sessao.sigaa.usuario == "200012345"

    # ── Credenciais ──
    pagina.click("#menu button[data-tela=credenciais]")
    pagina.fill("#form-credenciais [name=senha]", "s3nh@")
    pagina.fill("#form-credenciais [name=cpf]", "12345678900")
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
    pagina.fill("#disc-depto-busca", "gama")
    pagina.locator("#disc-depto-lista li").first.click()
    expect(pagina.locator("#disc-depto-selecionado")).to_contain_text("673")
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
    expect(pagina.locator("#dash-workers tr").first).to_be_visible()
    foto(pagina, "05_dashboard")
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
