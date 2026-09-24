"""
Pós-6.0.0 — correções do uso real: estado parado ≠ execução, carregar a última
execução, assistente inicial, validações, departamentos, persistência e ciclo
de vida (Web, GUI e núcleo).
"""
from __future__ import annotations

import json
import os
import threading
import time

import httpx
import pytest

from app.core import configuracao_inicial as ci
from app.core.config import carregar_disciplinas, carregar_settings, salvar_settings
from app.core.credentials import SessaoCredenciais
from app.core.validadores import (normalizar_cpf, problema_cpf, problema_email, problema_nascimento_texto,
                                  problema_url_webhook, problemas_email_cfg)
from app.dashboard.metrics import ColetorMetricas


# ── Validações centrais ─────────────────────────────────────────────────

@pytest.mark.parametrize("entrada", ["12345678909", "123.456.789-09", " 123 456 789 09 ", "123.456.78909"])
def test_cpf_formatos_aceitos(entrada):
    assert problema_cpf(entrada) is None and normalizar_cpf(entrada) == "123.456.789-09"


@pytest.mark.parametrize("entrada,trecho", [
    ("", "Informe"), ("123.456.789-0a", "só pode ter números"), ("1234567890", "11 dígitos — você digitou 10"),
    ("111.111.111-11", "todos os dígitos iguais"), ("123.456.789-00", "dígitos verificadores"),
])
def test_cpf_invalido_explica_o_problema(entrada, trecho):
    assert trecho in problema_cpf(entrada)


@pytest.mark.parametrize("entrada", ["01/02/2003", "1/2/2003", "01-02-2003", "01022003", "01.02.2003"])
def test_nascimento_formatos_aceitos(entrada):
    assert problema_nascimento_texto(entrada) is None


@pytest.mark.parametrize("entrada,trecho", [
    ("", "DD/MM/AAAA"), ("01/02/03", "incompleta"), ("31/13/2000", "Mês 13"), ("32/01/2000", "Dia 32"),
    ("31/02/2000", "que exista"), ("01/02/2999", "futuro"), ("ab/cd/efgh", "só pode ter números"), ("01/02/1850", "improvável"),
])
def test_nascimento_invalido_explica_o_problema(entrada, trecho):
    assert trecho in problema_nascimento_texto(entrada)


def test_email_e_webhook():
    assert problema_email("eu@gmail.com") is None and "não parece" in problema_email("eu@gmail")
    assert problema_url_webhook("https://discord.com/api/webhooks/1/x") is None
    for ruim, trecho in (("http://x.com", "https://"), ("https://", "incompleta"), ("https://a b.com", "espaços"), ("", "Informe")):
        assert trecho in problema_url_webhook(ruim)
    cfg = {"servidor": "http://smtp.gmail.com", "porta": 99999, "usuario": "x", "destinatario": "y@z.com", "seguranca": "tls"}
    problemas = " | ".join(problemas_email_cfg(cfg, ""))
    for trecho in ("sem http", "Porta", "STARTTLS", "Usuário do e-mail", "senha de app"):
        assert trecho in problemas


def test_credenciais_usam_as_mesmas_mensagens():
    s = SessaoCredenciais()
    s.sigaa.cpf, s.sigaa.nascimento = "123.456.789-0", "31/13/2000"
    problemas = s.sigaa.problemas()
    assert any("11 dígitos" in p for p in problemas) and any("Mês 13" in p for p in problemas)


# ── Assistente de configuração inicial ─────────────────────────────────

def _dados(**extra):
    base = {"credenciais": {}, "disciplinas": [{"codigo": "fga0211", "turma": "01", "departamento": "673", "grupo": "calc", "prioridade": "alta"}],
            "execucao": {"modo": "matricula", "dry_run": True, "preset": "moderado", "verificacao_previa": True},
            "notificacoes": {"windows_ativo": True}, "paineis": {"carregar_ultima_execucao": True}}
    base.update(extra)
    return base


def test_assistente_aplica_tudo_e_nao_reaparece(raiz_temporaria):
    from app.gui.wizard_primeira_execucao import primeira_execucao
    s = carregar_settings()
    assert primeira_execucao(s, []) is True
    sessao = SessaoCredenciais()
    novos, disciplinas, problemas = ci.aplicar(_dados(credenciais={"usuario": "200012345", "senha": "x", "cpf": "12345678909",
                                                                   "nascimento": "1/2/2003"}), s, [], sessao)
    assert problemas == []
    salvo = carregar_settings()
    assert salvo["num_workers"] == 8 and salvo["modo"] == "matricula" and salvo["dry_run"] is True
    assert salvo["carregar_ultima_execucao"] is True and salvo["notificacoes"]["windows_ativo"] is True
    assert salvo["assistente_concluido"] is True and primeira_execucao(salvo, []) is False
    d = carregar_disciplinas()[0]
    assert (d.chave(), d.grupo, d.prioridade) == ("FGA0211-01", "calc", "alta")
    assert sessao.sigaa.cpf == "123.456.789-09" and sessao.sigaa.nascimento == "01/02/2003"
    assert "12345678909" not in open(raiz_temporaria / "config" / "settings.json", encoding="utf-8").read()


def test_assistente_invalido_nao_salva_nada(raiz_temporaria):
    s = carregar_settings()
    for ruim in (_dados(credenciais={"usuario": "u", "senha": "s", "cpf": "111", "nascimento": "01/02/2003"}),
                 _dados(disciplinas=[{"codigo": "FGA0211", "turma": "A", "departamento": "673"}]),
                 _dados(notificacoes={"webhook_ativo": True, "webhook_url": "http://x"}),
                 _dados(notificacoes={"email_ativo": True, "email": {"servidor": "smtp.gmail.com"}}),
                 _dados(execucao={"modo": "x", "preset": "leve"})):
        _novos, _disc, problemas = ci.aplicar(ruim, s, [], SessaoCredenciais())
        assert problemas
    assert not (raiz_temporaria / "config" / "settings.json").exists()


def test_assistente_etapas_e_dispensa(raiz_temporaria):
    assert ci.validar_etapa("credenciais", {}, [])["avisos"]  # em branco: pode seguir
    assert ci.validar_etapa("credenciais", {"usuario": "u"}, [])["problemas"]
    assert ci.validar_etapa("disciplina", {"codigo": "FGA0211", "turma": "01", "departamento": "abc"}, [])["problemas"]
    r = ci.validar_etapa("disciplina", {"codigo": "XYZ9", "turma": "1", "departamento": "99999"}, [])
    assert not r["problemas"] and len(r["avisos"]) >= 2
    s = ci.dispensar(carregar_settings())
    assert s["assistente_concluido"] and carregar_settings()["assistente_concluido"]
    assert "Disciplinas novas: 1" in "\n".join(ci.resumo(_dados()))


# ── Estado parado ≠ execução (o problema do uso real) ────────────────────

def _log_de_execucao_antiga(raiz):
    """Log de uma execução que terminou há 2 horas, com workers e erros."""
    os.makedirs(raiz / "data", exist_ok=True)
    inicio = time.time() - 7200
    linhas = []
    for i in range(60):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(inicio + i))
        linhas.append({"timestamp": ts, "level": "INFO", "worker": f"W{i % 3}", "message": "🔍 Buscando FGA0211-01...",
                       "evento": "busca", "codigo": "FGA0211", "turma": "01", "execucao_id": "antiga"})
        linhas.append({"timestamp": ts, "level": "WARNING", "worker": f"W{i % 3}", "message": "⏳ Timeout (Socket Preso). Ressuscitando worker...",
                       "evento": "timeout", "execucao_id": "antiga"})
    (raiz / "data" / "sigaa_sniper_audit.json").write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in linhas) + "\n",
                                                            encoding="utf-8")


def test_coletor_sem_execucao_congela_tempo_e_nao_acusa_workers():
    c = ColetorMetricas()
    antigo = time.time() - 3600
    for i in range(3):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(antigo + i * 10))
        c.processar_linha(json.dumps({"timestamp": ts, "worker": "W1", "message": "🔍 Buscando X-01...", "evento": "busca"}), ao_vivo=False)
    parado = c.snapshot(execucao_ativa=False)
    assert parado["uptime_bot_seg"] == pytest.approx(20, abs=1) and parado["workers_com_alerta"] == []
    ativo = c.snapshot(execucao_ativa=True)
    assert ativo["uptime_bot_seg"] > 3000 and ativo["workers_com_alerta"]  # o comportamento antigo, só com execução ativa


from tests.test_web_api import H, aceitar, web  # noqa: E402,F401


def _instantaneo(c):
    d = c.get("/api/dashboard", headers=H).json()
    lg = c.get("/api/logs", headers=H).json()
    est = c.get("/api/estado", headers=H).json()
    return {"uptime": d["uptime"], "buscas": d["total_buscas"], "alertas": d["workers_com_alerta"], "saude": d["saude"],
            "tem_dados": d["tem_dados"], "recuperado": d["recuperado"], "ativa": d["execucao_ativa"], "painel": d["painel"],
            "workers": len(d["workers"]), "logs": len(lg["registros"]), "ultimo_log": lg["ultimo_seq"],
            "execucao": est["execucao"]["em_execucao"], "eventos": len(est["eventos"])}


def test_web_aberta_e_parada_nao_mostra_execucao_antiga_nem_muda(raiz_temporaria):
    _log_de_execucao_antiga(raiz_temporaria)
    from app.web.estado import EstadoWeb
    from app.web.server import criar_servidor
    e = EstadoWeb()
    s = criar_servidor(e, "127.0.0.1", 0)
    threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{s.porta}", timeout=10) as c:
            c.get(f"/?chave={s.chave}")
            aceitar(c)
            antes = _instantaneo(c)
            assert antes["tem_dados"] is False and antes["recuperado"] is False and antes["painel"] is None
            assert antes["alertas"] == [] and antes["logs"] == 0 and antes["ativa"] is False and antes["execucao"] is False
            assert antes["uptime"] == "sem dados" and antes["buscas"] == 0 and antes["workers"] == 0
            time.sleep(3)
            assert _instantaneo(c) == antes  # nada que dependa de execução se moveu
    finally:
        s.shutdown()
        s.server_close()
        e.finalizar()


def test_web_com_ultima_execucao_carregada_fica_congelada(raiz_temporaria):
    _log_de_execucao_antiga(raiz_temporaria)
    salvar_settings({**carregar_settings(), "carregar_ultima_execucao": True})
    from app.web.estado import EstadoWeb
    e = EstadoWeb()
    try:
        d1 = e.dashboard()
        assert d1["recuperado"] is True and d1["execucao_ativa"] is False and d1["total_buscas"] == 60
        assert d1["uptime"] == "0m 59s" and d1["workers_com_alerta"] == [] and d1["rps_atual"] == 0
        assert len(e.logs()["registros"]) == 120
        time.sleep(2.2)
        d2 = e.dashboard()
        assert d2["uptime"] == d1["uptime"] and d2["total_buscas"] == 60 and d2["saude"] == d1["saude"]
        # Histórico continua independente (nada foi apagado nem gravado ao abrir).
        from app.core import historico
        assert historico.listar_execucoes() == []
    finally:
        e.finalizar()


def test_gui_aberta_e_parada(raiz_temporaria, monkeypatch):
    pytest.importorskip("tkinter")
    _log_de_execucao_antiga(raiz_temporaria)
    from tests.test_gui import _tk_disponivel
    if not _tk_disponivel():
        pytest.skip("sem ambiente gráfico")
    import app.gui.app as modulo

    class AvisoAceito:
        aceito = True

        def __init__(self, _p):
            pass

    monkeypatch.setattr(modulo, "DialogoAvisoLegal", AvisoAceito)
    monkeypatch.setattr(modulo.SniperApp, "wait_window", lambda self, w=None: None)
    monkeypatch.setattr(modulo.SniperApp, "_talvez_mostrar_assistente_primeira_execucao", lambda self: None)
    app = modulo.SniperApp()
    app.withdraw()
    try:
        dash = app._telas["dashboard"]
        dash._atualizar()
        textos = lambda: (dash.lbl_saude.cget("text"), dash.labels_cards["uptime"].cget("text"),  # noqa: E731
                          dash.labels_cards["total_buscas"].cget("text"), dash.lbl_alerta_workers.cget("text"), dash.lbl_fase.cget("text"))
        antes = textos()
        assert "Nenhuma execução em andamento" in antes[0] and antes[1] == "sem dados" and antes[2] == "0" and antes[3] == ""
        time.sleep(2)
        dash._atualizar()
        assert textos() == antes
        assert app._telas["logs"].buffer.__len__() == 0 if hasattr(app._telas["logs"], "buffer") else True
    finally:
        app.destroy()


# ── Persistência ─────────────────────────────────────────────────────────

def test_arquivos_corrompidos_nao_quebram(raiz_temporaria):
    from app.core import historico
    os.makedirs(raiz_temporaria / "data", exist_ok=True)
    (raiz_temporaria / "config").mkdir(exist_ok=True)
    (raiz_temporaria / "data" / "historico.db").write_bytes(b"lixo" * 500)
    (raiz_temporaria / "config" / "settings.json").write_text("{quebrado", encoding="utf-8")
    (raiz_temporaria / "config" / "disciplinas.json").write_text("[{\"codigo\": 1}]", encoding="utf-8")
    assert carregar_settings()["num_workers"] == 20 and carregar_disciplinas() == []
    assert historico.listar_execucoes() == []  # recuperou: guardou o danificado e recriou
    guardados = [n for n in os.listdir(raiz_temporaria / "data") if n.startswith("historico.db.corrompido-")]
    assert len(guardados) == 1
    from tests.test_historico import _resumo
    from datetime import datetime
    assert historico.registrar_execucao(_resumo("nova", datetime.now()), {})
    assert [x["id"] for x in historico.listar_execucoes()] == ["nova"]


# ── Ciclo de vida / reinicialização / concorrência ───────────────────────

def test_reabrir_a_interface_web_varias_vezes_nao_deixa_restos(raiz_temporaria):
    from app.web.estado import EstadoWeb
    from app.web.server import criar_servidor
    base = threading.active_count()
    for _ in range(5):
        e = EstadoWeb()
        s = criar_servidor(e, "127.0.0.1", 0)
        t = threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        t.start()
        with httpx.Client(base_url=f"http://127.0.0.1:{s.porta}", timeout=5) as c:
            assert c.get(f"/?chave={s.chave}").status_code in (200, 303)
        porta = s.porta
        s.shutdown()
        s.server_close()
        e.finalizar()
        t.join(5)
        with pytest.raises(httpx.HTTPError):
            httpx.get(f"http://127.0.0.1:{porta}/", timeout=1)
    time.sleep(0.3)
    assert threading.active_count() <= base + 1


def test_parar_durante_o_login_encerra_com_seguranca(monkeypatch):
    import asyncio
    from app.core import engine
    from app.core.runner import ExecutorMotor
    from tests.test_observabilidade import novo_motor

    async def lento(request):
        await asyncio.sleep(30)  # CAS que não responde
        return httpx.Response(200, text="")

    original = httpx.AsyncClient
    monkeypatch.setattr(engine.httpx, "AsyncClient", lambda *a, **k: original(*a, **{**k, "transport": httpx.MockTransport(lento)}))
    motor = novo_motor(modo="monitoramento", num_workers=4, verificacao_previa=False, timeout_req=60)
    ex = ExecutorMotor(motor)
    ex.iniciar()
    limite = time.time() + 10
    while motor.fase != "logando" and time.time() < limite:
        time.sleep(0.05)
    assert motor.fase == "logando"
    t0 = time.time()
    ex.parar()
    ex.aguardar(15)
    assert not ex.em_execucao() and time.time() - t0 < 10
    assert motor.fase == "encerrado" and motor.motivo_fim == "interrompida"
    assert not any(t.name == "MotorMatricula" and t.is_alive() for t in threading.enumerate())


def test_nova_execucao_depois_de_ultima_carregada_nao_mistura(raiz_temporaria):
    _log_de_execucao_antiga(raiz_temporaria)
    c = ColetorMetricas()
    for linha in open(raiz_temporaria / "data" / "sigaa_sniper_audit.json", encoding="utf-8"):
        c.processar_linha(linha, ao_vivo=False)
    assert c.snapshot(False)["total_buscas"] == 60
    c.processar_linha(json.dumps({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "worker": "MAIN",
                                  "message": "SESSAO_INICIADA id=nova", "evento": "sessao_iniciada"}), ao_vivo=True)
    assert c.snapshot(True)["total_buscas"] == 0  # a nova execução começa do zero


def test_web_depois_de_parar_uma_execucao_o_dashboard_inteiro_congela(raiz_temporaria):
    """Achado no teste do .exe: depois de Parar, o tempo ocioso dos workers, os "há X s" e a
    memória continuavam mudando. Agora o painel inteiro fica igual enquanto nada roda."""
    from app.web.estado import EstadoWeb
    from app.web.server import criar_servidor
    e = EstadoWeb()
    s = criar_servidor(e, "127.0.0.1", 0)
    threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{s.porta}", timeout=15) as c:
            c.get(f"/?chave={s.chave}")
            aceitar(c)
            r = c.post("/api/execucao/iniciar", headers=H, json={"modo": "monitoramento", "demo": True})
            assert r.status_code == 200, r.text
            limite = time.time() + 20
            while c.get("/api/dashboard", headers=H).json()["painel"]["requisicoes"] < 3 and time.time() < limite:
                time.sleep(0.3)
            assert c.get("/api/dashboard", headers=H).json()["painel"]["requisicoes"] >= 3
            c.post("/api/execucao/parar", headers=H)
            limite = time.time() + 20
            while c.get("/api/estado", headers=H).json()["execucao"]["em_execucao"] and time.time() < limite:
                time.sleep(0.2)
            time.sleep(1.5)  # últimas linhas do log gravadas
            d1 = c.get("/api/dashboard?series=1", headers=H).json()
            assert d1["execucao_ativa"] is False and d1["workers_com_alerta"] == []
            assert all(w["ocioso_seg"] is None for w in d1["painel"]["workers"])
            assert all(w["ocioso_seg"] is None for w in d1["workers"])
            time.sleep(2.5)
            d2 = c.get("/api/dashboard?series=1", headers=H).json()
            dif = sorted(k for k in set(d1) | set(d2) if d1.get(k) != d2.get(k))
            dif_painel = sorted(k for k in set(d1["painel"]) | set(d2["painel"]) if d1["painel"].get(k) != d2["painel"].get(k))
            assert not dif and not dif_painel, (dif, dif_painel)
    finally:
        s.shutdown()
        s.server_close()
        e.finalizar()


# ── Terminal: as mesmas regras, com ajuda e lista completa ───────────────

def _digitar(monkeypatch, respostas):
    fila = iter(respostas)
    monkeypatch.setattr("builtins.input", lambda _p="": next(fila))
    return fila


def test_terminal_credenciais_explicam_e_normalizam(monkeypatch, capsys):
    from app.core.credentials import encerrar_sessao, obter_sessao
    from app.terminal import menu
    monkeypatch.setattr(menu.getpass, "getpass", lambda _p="": "s3nh@")
    _digitar(monkeypatch, ["200012345", "123.456.789-0", "31/13/2003", "s", "12345678909", "01022003"])
    try:
        menu.pedir_credenciais()
        saida = capsys.readouterr().out
        assert "11 dígitos" in saida and "Mês 13" in saida
        s = obter_sessao().sigaa
        assert s.cpf == "123.456.789-09" and s.nascimento == "01/02/2003" and "s3nh@" not in saida
    finally:
        encerrar_sessao()


def test_terminal_departamento_pela_lista_completa(monkeypatch, capsys):
    from app.core.departamentos import listar_departamentos
    from app.terminal import menu
    todos = listar_departamentos()
    assert len(todos) > 25
    _digitar(monkeypatch, ["L", "", "25"])  # lista, próxima página, escolhe o 25º
    assert menu.pedir_departamento() == todos[24].codigo
    saida = capsys.readouterr().out
    assert f"[  1] {todos[0].codigo:>5}" in saida and f"[ 21] {todos[20].codigo:>5}" in saida


def test_terminal_grupo_e_prioridade_com_ajuda(monkeypatch, capsys):
    from app.core.textos import TEXTO_AJUDA_GRUPO, TEXTO_AJUDA_PRIORIDADE
    from app.terminal import menu
    _digitar(monkeypatch, ["?", "calculo", "?", "a"])
    assert menu._pedir_grupo_e_prioridade() == ("calculo", "alta")
    saida = capsys.readouterr().out
    assert TEXTO_AJUDA_GRUPO.splitlines()[0] in saida and TEXTO_AJUDA_PRIORIDADE.splitlines()[0] in saida
    _digitar(monkeypatch, ["", ""])  # ENTER mantém o que já estava
    assert menu._pedir_grupo_e_prioridade("calculo", "baixa") == ("calculo", "baixa")
    _digitar(monkeypatch, ["-", "n"])
    assert menu._pedir_grupo_e_prioridade("calculo", "baixa") == ("", "normal")


def test_terminal_webhook_e_email_conferidos_antes_de_ativar(monkeypatch, capsys, raiz_temporaria):
    from app.core.credentials import encerrar_sessao, obter_sessao
    from app.core.textos import TEXTO_AJUDA_WEBHOOK
    from app.terminal import menu
    monkeypatch.setattr(menu, "cabecalho", lambda *_a, **_k: None)
    senhas = iter(["", "senha-de-app"])
    monkeypatch.setattr(menu.getpass, "getpass", lambda _p="": next(senhas))
    _digitar(monkeypatch, [
        "8", "", "?", "http://inseguro.exemplo", "",          # webhook: ajuda, URL sem https → recusado
        "9", "smtp.exemplo.com", "1", "eu-sem-arroba", "", "", "",  # e-mail inválido, sem senha → recusado
        "9", "smtp.exemplo.com", "1", "eu@exemplo.com", "", "aviso@exemplo.com",  # válido
        "5",
    ])
    try:
        menu.menu_notificacoes()
        saida = capsys.readouterr().out
        assert TEXTO_AJUDA_WEBHOOK.splitlines()[0] in saida and "https://" in saida
        assert "E-mail não ativado" in saida and "senha-de-app" not in saida
        cfg = carregar_settings()["notificacoes"]
        assert cfg["webhook_ativo"] is False and obter_sessao().notificacao.webhook_url == ""
        assert cfg["email_ativo"] is True and cfg["email"]["remetente"] == "aviso@exemplo.com"
        assert cfg["email"]["usuario"] == "eu@exemplo.com" and "senha" not in json.dumps(cfg["email"]).lower()
        assert obter_sessao().notificacao.email_senha == "senha-de-app"
    finally:
        encerrar_sessao()
