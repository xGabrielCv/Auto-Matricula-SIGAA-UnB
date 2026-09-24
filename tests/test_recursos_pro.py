"""
Fase 6 — recursos profissionais: versões anteriores da configuração (045),
perfis (042), trilha de auditoria e aceite do aviso legal (062/063) e lista de
departamentos atualizada pela página pública do SIGAA (046).
"""
from __future__ import annotations

import json
import os

import httpx
import pytest

from app.core import auditoria
from app.core.config import (Disciplina, aplicar_perfil, apagar_perfil, carregar_disciplinas, carregar_settings,
                             listar_perfis, listar_versoes_config, restaurar_versao_config, salvar_disciplinas,
                             salvar_perfil, salvar_settings)
from app.core import departamentos


# ── 045: versões anteriores ───────────────────────────────────────────────

def test_cada_alteracao_guarda_a_versao_anterior_e_restaura(raiz_temporaria):
    s = carregar_settings()
    salvar_settings(s)                      # 1º salvamento: nada anterior para guardar
    assert listar_versoes_config() == []
    salvar_settings({**s, "num_workers": 7})
    salvar_settings({**s, "num_workers": 9})
    salvar_settings({**s, "num_workers": 9})  # igual: não gera versão
    versoes = listar_versoes_config()
    assert [v["tipo"] for v in versoes] == ["settings", "settings"]
    assert "num_workers 7 (hoje 9)" in versoes[0]["resumo"]
    restaurar_versao_config(versoes[0]["id"])
    assert carregar_settings()["num_workers"] == 7
    assert len(listar_versoes_config()) == 3  # restaurar guardou a versão "9" — dá para desfazer o desfazer
    with pytest.raises(ValueError):
        restaurar_versao_config("../settings.json")


def test_versoes_de_disciplinas_e_limite(raiz_temporaria, monkeypatch):
    import app.core.config as cfg
    monkeypatch.setattr(cfg, "MAX_VERSOES_CONFIG", 3)
    for i in range(6):
        salvar_disciplinas([Disciplina("FGA0211", f"{i:02d}", 673)])
    versoes = [v for v in listar_versoes_config() if v["tipo"] == "disciplinas"]
    assert len(versoes) == 3 and "tinha FGA0211-04" in versoes[0]["resumo"]
    restaurar_versao_config(versoes[0]["id"])
    assert carregar_disciplinas()[0].turma == "04"


# ── 042: perfis ──────────────────────────────────────────────────────────

def test_perfil_salva_aplica_e_nunca_liga_matricula_real(raiz_temporaria):
    s = {**carregar_settings(), "modo": "matricula", "dry_run": False, "num_workers": 4, "intervalo_busca": 1.5}
    salvar_perfil("Semana de Matrícula!", s, [Disciplina("MAT0025", "02", 518)])
    perfis = listar_perfis()
    assert perfis[0]["arquivo"] == "semana-de-matricula.json" and perfis[0]["nome"] == "Semana de Matrícula!"
    assert "4 workers" in perfis[0]["resumo"] and "1 disciplina" in perfis[0]["resumo"]
    atuais = {**carregar_settings(), "dry_run": True}
    novos, disciplinas = aplicar_perfil("semana-de-matricula.json", atuais)
    assert novos["modo"] == "matricula" and novos["num_workers"] == 4
    assert novos["dry_run"] is True  # o perfil guardado tinha DRY RUN desligado — não importa
    assert disciplinas[0].chave() == "MAT0025-02"
    with pytest.raises(ValueError):
        aplicar_perfil("../settings.json", atuais)
    with pytest.raises(ValueError):
        salvar_perfil("!!!", s, [])
    apagar_perfil("semana-de-matricula.json")
    assert listar_perfis() == []


def test_perfil_invalido_nao_e_aplicado(raiz_temporaria):
    pasta = raiz_temporaria / "config" / "perfis"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "ruim.json").write_text(json.dumps({"nome": "Ruim", "settings": {"num_workers": 500}, "disciplinas": []}),
                                     encoding="utf-8")
    with pytest.raises(ValueError, match="validação"):
        aplicar_perfil("ruim.json", carregar_settings())


# ── 062 / 063: trilha de auditoria ───────────────────────────────────────

def test_trilha_registra_acoes_sem_valores_sensiveis(raiz_temporaria):
    auditoria.definir_origem("teste")
    auditoria.registrar_aceite_aviso()
    s = carregar_settings()
    salvar_settings(s)
    salvar_settings({**s, "num_workers": 5, "urls": {**s["urls"], "cas_login": "https://autenticacao.unb.br/x"}})
    auditoria.registrar("credenciais_preenchidas", senha="NAO-DEVE-APARECER-EM-LUGAR-NENHUM" and None)
    acoes = auditoria.listar()
    assert [a["acao"] for a in acoes][:3] == ["credenciais_preenchidas", "configuracao_alterada", "aviso_aceito"]
    mudanca = acoes[1]
    assert "num_workers: 20 → 5" in mudanca["descricao"] and "urls" in mudanca["descricao"]
    assert "autenticacao.unb.br/x" not in json.dumps(mudanca)  # URL: só o nome da chave
    aceite = acoes[2]
    assert aceite["hash_aviso"] == auditoria.hash_aviso_legal() and len(aceite["hash_aviso"]) == 12
    assert aceite["origem"] == "teste" and aceite["rotulo"] == "Aceitou o aviso legal"
    bruto = open(raiz_temporaria / "data" / "auditoria.jsonl", encoding="utf-8").read()
    assert "NAO-DEVE-APARECER" not in bruto


def test_hash_do_aviso_muda_quando_o_texto_muda(monkeypatch):
    from app.core import disclaimer
    antes = auditoria.hash_aviso_legal()
    monkeypatch.setattr(disclaimer, "TEXTO_COMPLETO", disclaimer.TEXTO_COMPLETO + " (revisado)")
    assert auditoria.hash_aviso_legal() != antes


def test_inicio_parada_e_pausa_do_motor_entram_na_trilha(raiz_temporaria, monkeypatch):
    from app.core import engine
    from app.core.runner import ExecutorMotor
    from tests.test_engine_fluxo import SigaaSimulado
    simulado = SigaaSimulado(vagas=0)
    original = httpx.AsyncClient
    monkeypatch.setattr(engine.httpx, "AsyncClient", lambda *a, **k: original(*a, **{**k, "transport": httpx.MockTransport(simulado)}))
    from tests.test_observabilidade import novo_motor
    motor = novo_motor(modo="monitoramento")
    ex = ExecutorMotor(motor)
    ex.iniciar()
    import time
    limite = time.time() + 15
    while motor.fase != "monitorando" and time.time() < limite:
        time.sleep(0.05)
    ex.chamar(motor.pausar, "usuario")
    ex.chamar(motor.retomar, "usuario")
    ex.parar()
    ex.parar()  # segundo pedido não duplica
    ex.aguardar(15)
    acoes = [a["acao"] for a in auditoria.listar()]
    assert acoes.count("execucao_parada") == 1
    assert {"execucao_iniciada", "execucao_pausada", "execucao_retomada"} <= set(acoes)
    inicio = next(a for a in auditoria.listar() if a["acao"] == "execucao_iniciada")
    assert "somente monitoramento" in inicio["descricao"] and inicio["execucao_id"] == motor.execucao_id


# ── 046: departamentos ───────────────────────────────────────────────────

PAGINA_PUBLICA = """<html><form id="formTurma"><select name="formTurma:inputDepto" id="formTurma:inputDepto">
<option value="0">-- SELECIONE --</option>
<option value="673">CAMPUS UNB GAMA: FACULDADE DE CIÊNCIAS E TECNOLOGIAS EM ENGENHARIA - BRASÍLIA</option>
<option value="508">DEPTO CIÊNCIAS DA COMPUTAÇÃO - BRASÍLIA</option>
<option value="518">DEPARTAMENTO DE MATEMÁTICA - BRASÍLIA</option>
<option value="9999">INSTITUTO NOVO DE TESTES - BRASÍLIA</option>
<option value="327">DEPTO ADMINISTRAÇÃO - BRASÍLIA</option>
<option value="x">inválido</option>
</select></form></html>"""


def test_atualizar_departamentos_da_pagina_publica(raiz_temporaria):
    pedidos = []

    def transporte(req):
        pedidos.append(req)
        return httpx.Response(200, text=PAGINA_PUBLICA)

    assert departamentos.info_lista()["fonte"] == "embutida"
    assert not departamentos.codigo_conhecido(9999)
    with httpx.Client(transport=httpx.MockTransport(transporte)) as c:
        r = departamentos.atualizar_departamentos(c)
    assert r["quantidade"] == 5 and r["novos"] == 1 and r["removidos"] > 100
    assert len(pedidos) == 1 and pedidos[0].method == "GET" and "cookie" not in pedidos[0].headers
    assert departamentos.codigo_conhecido(9999) and departamentos.nome_do_departamento(9999).startswith("INSTITUTO NOVO")
    assert departamentos.info_lista()["fonte"] == "sigaa"
    assert [d.codigo for d in departamentos.buscar_departamentos("computacao")] == [508]
    assert auditoria.listar()[0]["acao"] == "departamentos_atualizados"


def test_pagina_publica_sem_lista_mantem_a_atual(raiz_temporaria):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>manutenção</html>"))) as c:
        with pytest.raises(ValueError, match="mantida"):
            departamentos.atualizar_departamentos(c)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as c:
        with pytest.raises(ValueError, match="503"):
            departamentos.atualizar_departamentos(c)
    assert departamentos.info_lista()["fonte"] == "embutida" and departamentos.codigo_conhecido(673)


# ── API Web ──────────────────────────────────────────────────────────────

from tests.test_web_api import H, aceitar, web  # noqa: E402,F401


def test_api_web_perfis_versoes_auditoria(web, raiz_temporaria):
    e, _, c, _ = web
    aceitar(c)
    assert c.get("/api/auditoria", headers=H).json()["acoes"][0]["acao"] == "aviso_aceito"
    r = c.post("/api/perfis", headers=H, json={"nome": "Calmo"})
    assert r.status_code == 200 and r.json()["perfis"][0]["nome"] == "Calmo"
    assert c.post("/api/perfis", headers=H, json={"nome": "calmo"}).status_code == 409  # já existe → confirmar
    assert c.post("/api/perfis", headers=H, json={"nome": "calmo", "confirmado": True}).status_code == 200
    assert c.get("/api/estado", headers=H).json()["perfis"] == [{"arquivo": "calmo.json", "nome": "calmo"}]
    av = c.get("/api/avancado", headers=H).json()
    c.post("/api/avancado", headers=H, json={**av, "num_workers": 6})
    assert c.post("/api/perfis/aplicar", headers=H, json={"arquivo": "calmo.json"}).status_code == 409  # confirmação
    assert c.post("/api/perfis/aplicar", headers=H, json={"arquivo": "calmo.json", "confirmado": True}).status_code == 200
    assert e.settings["num_workers"] == 20
    versoes = c.get("/api/config/versoes", headers=H).json()["versoes"]
    alvo = next(v for v in versoes if v["tipo"] == "settings" and "num_workers 6" in v["resumo"])
    r = c.post("/api/config/versoes/restaurar", headers=H, json={"id": alvo["id"], "confirmado": True})
    assert r.status_code == 200 and e.settings["num_workers"] == 6
    assert c.post("/api/config/versoes/restaurar", headers=H, json={"id": "x", "confirmado": True}).status_code == 404
    acoes = [a["acao"] for a in c.get("/api/auditoria", headers=H).json()["acoes"]]
    assert {"perfil_salvo", "perfil_aplicado", "versao_restaurada", "configuracao_alterada"} <= set(acoes)
    assert c.post("/api/perfis/apagar", headers=H, json={"arquivo": "calmo.json", "confirmado": True}).json()["perfis"] == []
    info = c.get("/api/departamentos?q=673", headers=H).json()
    assert info["departamentos"][0]["codigo"] == 673 and info["info"]["fonte"] == "embutida"


# ── 065: cofre dos segredos de notificação ───────────────────────────────

@pytest.mark.skipif(os.name != "nt", reason="DPAPI só existe no Windows")
def test_segredos_salvos_cifrados_e_arquivo_antigo_continua_legivel(raiz_temporaria):
    from app.core import cofre
    from app.core.config import (aplicar_segredos_notificacao_salvos, carregar_segredos_notificacao,
                                 salvar_segredos_notificacao, segredos_salvos_cifrados)
    from app.core.credentials import CredenciaisNotificacao
    from app.core.seguranca_config import alertas_de_configuracao
    salvar_segredos_notificacao("123:TOKEN", "42", "topico-secreto", "", "https://discord.com/api/webhooks/x/y", "senha-email")
    bruto = (raiz_temporaria / "config" / "notificacoes.secrets.json").read_text(encoding="utf-8")
    assert "TOKEN" not in bruto and "topico-secreto" not in bruto and "senha-email" not in bruto
    assert segredos_salvos_cifrados()
    n = CredenciaisNotificacao()
    assert aplicar_segredos_notificacao_salvos(n)
    assert (n.telegram_token, n.ntfy_topic, n.webhook_url, n.email_senha) == (
        "123:TOKEN", "topico-secreto", "https://discord.com/api/webhooks/x/y", "senha-email")
    assert "segredos_salvos" not in [a["id"] for a in alertas_de_configuracao(carregar_settings())]
    # Arquivo antigo (texto simples) continua sendo lido — e aí o alerta aparece.
    (raiz_temporaria / "config" / "notificacoes.secrets.json").write_text(json.dumps({"telegram_token": "VELHO"}), encoding="utf-8")
    assert carregar_segredos_notificacao()["telegram_token"] == "VELHO" and not segredos_salvos_cifrados()
    assert "segredos_salvos" in [a["id"] for a in alertas_de_configuracao(carregar_settings())]
    # Conteúdo cifrado adulterado (ou de outra conta do Windows): não decifra, não quebra.
    assert cofre.decifrar({"formato": "dpapi-v1", "dados": "QUJD"}) is None


# ── 080 / 081 / 082: novos canais ────────────────────────────────────────

def test_webhook_formatos_e_envio(monkeypatch):
    import asyncio
    from app.notifications import webhook
    enviados = []
    original = httpx.AsyncClient

    def transporte(req):
        enviados.append((str(req.url), json.loads(req.content)))
        return httpx.Response(204)

    monkeypatch.setattr(webhook.httpx, "AsyncClient", lambda *a, **k: original(*a, **{**k, "transport": httpx.MockTransport(transporte)}))
    asyncio.run(webhook.enviar_webhook("https://discord.com/api/webhooks/1/abc", "discord", "SIGAA Sniper", "Vaga!"))
    asyncio.run(webhook.enviar_webhook("https://hooks.slack.com/x", "slack", "SIGAA Sniper", "Vaga!"))
    asyncio.run(webhook.enviar_webhook("https://exemplo.dev/hook", "json", "SIGAA Sniper", "Vaga!"))
    assert enviados[0][1]["content"] == "**SIGAA Sniper**\nVaga!" and enviados[1][1] == {"text": "*SIGAA Sniper*\nVaga!"}
    assert enviados[2][1] == {"app": "SIGAA Sniper", "titulo": "SIGAA Sniper", "mensagem": "Vaga!"}
    with pytest.raises(ValueError):
        asyncio.run(webhook.enviar_webhook("http://inseguro/x", "json", "t", "m"))


def test_email_usa_starttls_ou_ssl(monkeypatch):
    import asyncio
    from app.notifications import email as email_mod
    passos = []

    class SMTPFalso:
        def __init__(self, servidor, porta, timeout=None, context=None):
            passos.append(("conecta", servidor, porta, type(self).__name__))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            passos.append(("starttls",))

        def login(self, usuario, senha):
            passos.append(("login", usuario, senha))

        def send_message(self, msg):
            passos.append(("envia", msg["To"], msg["Subject"]))

    class SMTPSSLFalso(SMTPFalso):
        pass

    monkeypatch.setattr(email_mod.smtplib, "SMTP", SMTPFalso)
    monkeypatch.setattr(email_mod.smtplib, "SMTP_SSL", SMTPSSLFalso)
    cfg = {"servidor": "smtp.exemplo.com", "porta": 587, "usuario": "eu@exemplo.com", "destinatario": "eu@exemplo.com",
           "seguranca": "starttls"}
    asyncio.run(email_mod.enviar_email(cfg, "s3nh4", "Assunto", "Corpo"))
    assert [p[0] for p in passos] == ["conecta", "starttls", "login", "envia"]  # senha só depois do STARTTLS
    passos.clear()
    asyncio.run(email_mod.enviar_email({**cfg, "seguranca": "ssl", "porta": 465}, "s3nh4", "A", "B"))
    assert passos[0] == ("conecta", "smtp.exemplo.com", 465, "SMTPSSLFalso") and ("starttls",) not in passos
    with pytest.raises(ValueError):
        asyncio.run(email_mod.enviar_email({**cfg, "servidor": ""}, "s3nh4", "A", "B"))


def test_notificacao_windows_nunca_poe_o_texto_no_comando(monkeypatch):
    import asyncio
    from app.notifications import windows
    capturado = {}

    class ProcessoFalso:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def criar(*args, env=None, **kwargs):
        capturado["args"], capturado["env"] = args, env
        return ProcessoFalso()

    monkeypatch.setattr(windows.sys, "platform", "win32")
    monkeypatch.setattr(windows.asyncio, "create_subprocess_exec", criar)
    hostil = "Vaga'; Remove-Item C:\\ -Recurse; $(calc) <toast>&"
    asyncio.run(windows.enviar_windows("SIGAA Sniper", hostil))
    assert all(hostil not in str(a) for a in capturado["args"])
    assert capturado["env"]["SNIPER_MENSAGEM"] == hostil and "Escape($env:SNIPER_MENSAGEM)" in capturado["args"][-1]


def test_gerenciador_despacha_para_os_novos_canais(monkeypatch):
    import asyncio
    from app.core.credentials import CredenciaisNotificacao
    from app.notifications import manager
    chamados = []

    async def registrar(nome):
        chamados.append(nome)

    monkeypatch.setattr(manager, "enviar_windows", lambda *a: registrar("windows"))
    monkeypatch.setattr(manager, "enviar_webhook", lambda *a: registrar("webhook"))
    monkeypatch.setattr(manager, "enviar_email", lambda *a: registrar("email"))
    cred = CredenciaisNotificacao(webhook_url="https://exemplo.dev/h", email_senha="x")
    g = manager.GerenciadorNotificacoes({"vaga_detectada": True}, {"windows": True, "webhook": True, "email": True}, cred,
                                        email_cfg={"servidor": "s", "usuario": "u", "destinatario": "d"})

    async def cenario():
        g.notificar_evento("vaga_detectada", {"codigo": "FGA0211", "turma": "01", "vagas": 1})
        await asyncio.sleep(0)
        await g.aguardar_pendentes(5)

    asyncio.run(cenario())
    assert chamados == ["windows", "webhook", "email"]


def test_api_web_novos_canais(web, raiz_temporaria):
    e, _, c, _ = web
    aceitar(c)
    n = c.get("/api/notificacoes", headers=H).json()
    assert n["windows_ativo"] is False and n["webhook_formato"] == "discord" and n["email"]["porta"] == 587
    assert "cofre_texto" in n
    base = {"alarme_repeticoes": 3, "alarme_duracao": 20, "eventos": {}, "webhook_ativo": True, "webhook_formato": "slack",
            "webhook_url": "http://inseguro"}
    assert c.post("/api/notificacoes", headers=H, json=base).status_code == 400
    base.update(webhook_url="https://hooks.slack.com/x", email_ativo=True,
                email={"servidor": "smtp.exemplo.com", "porta": 465, "usuario": "a@b.com", "destinatario": "a@b.com", "seguranca": "ssl"},
                email_senha="pw")
    assert c.post("/api/notificacoes", headers=H, json=base).status_code == 200
    cfg = e.settings["notificacoes"]
    assert cfg["webhook_formato"] == "slack" and cfg["email"]["seguranca"] == "ssl" and cfg["email"]["porta"] == 465
    assert e.sessao.notificacao.webhook_url == "https://hooks.slack.com/x" and e.sessao.notificacao.email_senha == "pw"
    assert "https://hooks.slack.com/x" not in json.dumps(carregar_settings())  # a URL é segredo: não vai para settings
    r = c.post("/api/notificacoes/testar", headers=H, json={"canal": "webhook", "webhook_url": "ftp://x"})
    assert r.status_code == 400 and "https" in r.json()["erro"]


# ── 077: modo demonstração ───────────────────────────────────────────────

def test_demonstracao_nao_toca_a_rede_e_nao_grava_historico(raiz_temporaria, monkeypatch):
    import asyncio
    from app.core import engine
    from app.core.credentials import SessaoCredenciais
    from app.core.factory import construir_motor
    from tests.test_engine_fluxo import rodar_ate

    def proibido(*a, **k):
        raise AssertionError("a demonstração tentou usar a rede de verdade")

    # Qualquer transporte real seria usado só se o motor ignorasse o transporte simulado.
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", proibido)
    enviados = []
    s = {**carregar_settings(), "num_workers": 2, "intervalo_busca": 0.05, "modo": "matricula", "dry_run": False}
    sessao = SessaoCredenciais()
    motor = construir_motor(s, sessao, [], demo=True, on_evento_extra=lambda t, d: enviados.append((t, d)))
    assert motor.demo and motor.dry_run is True and list(motor.alvos_ativos) == ["FGA0211-01", "MAT0025-02"]
    assert sessao.sigaa.usuario == ""  # credenciais fictícias ficam só no motor
    transporte = motor.opcoes_cliente["transport"]
    transporte.handler.prob_abrir = 1.0  # vagas garantidas para o teste não depender da sorte
    rodar_ate(motor, lambda m: not m.alvos_ativos, timeout=30)
    assert {a["estado"] for a in motor.snapshot()["alvos"]} == {"simulada"}
    assert motor.resumo["demo"] is True
    assert not (raiz_temporaria / "data" / "historico.db").exists()
    assert not (raiz_temporaria / "data" / "relatorios").exists() or not os.listdir(raiz_temporaria / "data" / "relatorios")
    assert any(t == "matricula_sucesso" and d.get("dry_run") for t, d in enviados)


def test_mensagens_da_demonstracao_sao_marcadas(monkeypatch):
    import asyncio
    from app.core.credentials import CredenciaisNotificacao
    from app.notifications import manager
    mensagens = []

    async def telegram(_t, _c, msg):
        mensagens.append(msg)

    monkeypatch.setattr(manager, "enviar_telegram", telegram)
    g = manager.GerenciadorNotificacoes({"vaga_detectada": True}, {"telegram": True},
                                        CredenciaisNotificacao(telegram_token="t", telegram_chat_id="c"))

    async def cenario():
        g.notificar_evento("vaga_detectada", {"codigo": "FGA0211", "turma": "01", "vagas": 2, "demo": True})
        await asyncio.sleep(0)
        await g.aguardar_pendentes(5)

    asyncio.run(cenario())
    assert mensagens and mensagens[0].startswith("[DEMONSTRAÇÃO] ")


def test_api_web_demonstracao_sem_credenciais(web, raiz_temporaria):
    e, _, c, _ = web
    aceitar(c)
    e.settings.update({"num_workers": 1, "intervalo_busca": 0.1})
    r = c.post("/api/execucao/iniciar", headers=H, json={"modo": "matricula", "dry_run": False, "demo": True})
    assert r.status_code == 200 and r.json()["execucao"]["demo"] is True
    assert "DEMONSTRAÇÃO" in r.json()["execucao"]["mensagem"]
    assert e.settings["dry_run"] is True  # o DRY RUN salvo não foi mexido pela demonstração
    c.post("/api/execucao/parar", headers=H)
    e._executor.aguardar(15)
    acao = next(a for a in c.get("/api/auditoria", headers=H).json()["acoes"] if a["acao"] == "execucao_iniciada")
    assert "DEMONSTRAÇÃO" in acao["descricao"]


# ── 070: expiração da sessão Web por inatividade ─────────────────────────

def test_sessao_web_expira_por_inatividade(web):
    e, s, c, anonimo = web
    aceitar(c)
    e.sessao.sigaa.usuario, e.sessao.sigaa.senha = "200012345", "s3nh@"
    assert not s.checar_inatividade()  # desligado por padrão
    e.settings["web"]["expirar_inatividade_min"] = 30
    assert not s.checar_inatividade()
    e.ultima_atividade -= 31 * 60
    avisos = []
    s.ao_expirar = lambda srv: avisos.append(srv.chave)
    chave_antiga = s.chave
    assert s.checar_inatividade() and avisos == [s.chave] and s.chave != chave_antiga
    assert e.sessao.sigaa.usuario == "" and e.sessao.sigaa.senha == "" and e.aviso_aceito is False
    assert c.get("/api/estado", headers=H).status_code == 401  # cookie antigo não vale mais
    assert anonimo.get(f"/?chave={chave_antiga}").status_code == 403
    assert anonimo.get(f"/?chave={s.chave}").status_code == 303  # o novo link funciona
    assert any(a["acao"] == "sessao_web_expirada" for a in auditoria.listar())


def test_sessao_nao_expira_com_execucao_ativa(web):
    e, s, _, _ = web

    class ExecutorFalso:
        def em_execucao(self):
            return True

    e.settings["web"]["expirar_inatividade_min"] = 1
    e.ultima_atividade -= 3600
    e._executor = ExecutorFalso()
    assert not s.checar_inatividade()
    e._executor = None
    assert not s.checar_inatividade()  # o relógio recomeçou quando a execução terminou


def test_acao_do_usuario_conta_como_atividade(web):
    e, _, c, _ = web
    aceitar(c)
    e.ultima_atividade -= 500
    c.get("/api/estado", headers=H)
    assert time_desde(e.ultima_atividade) >= 499  # consultas automáticas não contam
    c.post("/api/atividade", headers=H, json={})
    assert time_desde(e.ultima_atividade) < 5


def time_desde(ts):
    import time
    return time.time() - ts


# ── 091: janelas prováveis de vaga ───────────────────────────────────────

def _historico_com_aberturas(horas_fga, horas_mat=()):
    from datetime import datetime, timedelta
    from app.core import historico
    from tests.test_historico import _resumo
    base = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=3)
    serie_fga, serie_mat = [], []
    for i, hora in enumerate(horas_fga):
        t = (base.replace(hour=hora) + timedelta(minutes=10 + i)).timestamp()
        serie_fga += [[t, 1], [t + 60, 0]]
    for hora in horas_mat:
        t = (base.replace(hour=hora) + timedelta(minutes=5)).timestamp()
        serie_mat += [[t, 1], [t + 60, 0]]
    historico.registrar_execucao(_resumo("jan", base, alvos=("FGA0211-01", "MAT0025-02")),
                                 {"vagas_series": {"FGA0211-01": serie_fga, "MAT0025-02": serie_mat}, "pontos": []})
    return base


def test_janelas_provaveis_mostram_a_faixa_que_concentra_as_vagas(raiz_temporaria):
    from app.core import historico
    base = _historico_com_aberturas([8, 8, 9, 9, 9, 8, 15, 21], horas_mat=[10, 11])
    janelas = {j["disciplina"]: j for j in historico.janelas_provaveis(14)}
    fga = janelas["FGA0211-01"]
    assert fga["suficiente"] and (fga["inicio_h"], fga["fim_h"]) == (8, 9) and fga["porcentagem"] == 75
    assert "75% das vagas de FGA0211-01 surgiram entre 8h e 10h" in fga["texto"]
    assert fga["sugestao"] == {"ativa": True, "inicio": "07:30", "fim": "10:30", "dias": [base.weekday()]}
    assert sum(fga["contagem_por_hora"]) == 8
    assert janelas["MAT0025-02"]["suficiente"] is False and "poucos dados" in janelas["MAT0025-02"]["texto"]


def test_api_web_janelas_e_aplicar(web, raiz_temporaria):
    e, _, c, _ = web
    aceitar(c)
    _historico_com_aberturas([8, 8, 9, 9, 9, 8])
    r = c.get("/api/historico/janelas?dias=30", headers=H).json()
    sugestao = r["janelas"][0]["sugestao"]
    assert r["dias"] == 30 and r["janelas"][0]["porcentagem"] == 100
    assert c.post("/api/execucao/janela", headers=H, json={"janela": sugestao}).status_code == 409  # confirmação
    ok = c.post("/api/execucao/janela", headers=H, json={"janela": sugestao, "confirmado": True})
    assert ok.status_code == 200 and e.settings["janela"]["ativa"] is True and e.settings["janela"]["inicio"] == "07:30"
    ruim = c.post("/api/execucao/janela", headers=H, json={"janela": {"inicio": "25:00", "fim": "10:00", "dias": [0]}, "confirmado": True})
    assert ruim.status_code == 400
