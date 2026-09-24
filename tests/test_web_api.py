"""
Interface Web: segurança do servidor local, aviso legal obrigatório,
confirmações (409) e equivalência com as regras da GUI — contra um servidor
HTTP real em porta efêmera.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time

import httpx
import pytest

from app.core.disclaimer import CONFIRMACOES
from app.web import estado as estado_mod
from app.web.estado import EstadoWeb
from app.web.server import criar_servidor

H = {"X-Requested-With": "SIGAA-Sniper"}
TODAS = {chave: True for chave, _ in CONFIRMACOES}
CRED = {"usuario": "200012345", "senha": "s3nh@", "cpf": "12345678909", "nascimento": "01/02/2003"}


@pytest.fixture
def web():
    e = EstadoWeb()
    s = criar_servidor(e, "127.0.0.1", 0)
    threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    base = f"http://127.0.0.1:{s.porta}"
    anonimo = httpx.Client(base_url=base, follow_redirects=False, timeout=10)
    cliente = httpx.Client(base_url=base, follow_redirects=False, timeout=30)
    assert cliente.get(f"/?chave={s.chave}").status_code == 303
    yield e, s, cliente, anonimo
    anonimo.close()
    cliente.close()
    s.shutdown()
    s.server_close()
    e.finalizar()


def aceitar(c):
    assert c.post("/api/aviso-legal/aceitar", headers=H, json={"confirmacoes": TODAS}).status_code == 200


# ── Segurança do servidor ────────────────────────────────────────────────

def test_pagina_exige_chave(web):
    _, s, cliente, anonimo = web
    assert anonimo.get("/").status_code == 403
    assert anonimo.get("/?chave=errada").status_code == 403
    r = cliente.get("/")
    assert r.status_code == 200 and "SIGAA Sniper" in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert "HttpOnly" in anonimo.get(f"/?chave={s.chave}").headers["set-cookie"]


def test_api_exige_cookie_e_cabecalho(web):
    _, _, cliente, anonimo = web
    assert anonimo.get("/api/estado", headers=H).status_code == 401
    assert cliente.get("/api/estado").status_code == 403  # sem X-Requested-With (proteção CSRF)
    assert cliente.get("/api/estado", headers=H).status_code == 200


def test_host_diferente_recusado(web):
    _, _, cliente, _ = web
    r = cliente.get("/api/estado", headers={**H, "Host": "atacante.exemplo:80"})
    assert r.status_code == 421


def test_limites_de_corpo(web):
    _, _, c, _ = web
    aceitar(c)
    r = c.post("/api/credenciais", headers={**H, "Content-Type": "text/plain"}, content=b"x=1")
    assert r.status_code == 415
    r = c.post("/api/credenciais", headers={**H, "Content-Type": "application/json"}, content=b"[1,2]")
    assert r.status_code == 400
    grande = json.dumps({"conteudo": "x" * (3 * 1024 * 1024)})
    r = c.post("/api/config/importar/previa", headers={**H, "Content-Type": "application/json"}, content=grande)
    assert r.status_code == 413


def test_arquivos_estaticos_sem_traversal(web):
    _, _, c, anonimo = web
    for caminho in ("/static/app.js", "/static/app.css", "/static/icone.svg"):
        assert anonimo.get(caminho).status_code == 200
    assert anonimo.get("/static/../server.py").status_code == 404
    assert anonimo.get("/static/%2e%2e/estado.py").status_code == 404


def test_porta_ocupada_usa_a_seguinte():
    e = EstadoWeb()
    s1 = criar_servidor(e, "127.0.0.1", 0)
    try:
        s2 = criar_servidor(e, "127.0.0.1", s1.porta, tentativas=5)
        assert s2.porta != s1.porta
        s2.server_close()
    finally:
        s1.server_close()


# ── Aviso legal ──────────────────────────────────────────────────────────

def test_aviso_legal_obrigatorio_e_completo(web):
    e, _, c, _ = web
    aviso = c.get("/api/aviso-legal", headers=H).json()
    assert len(aviso["confirmacoes"]) == 5 and "Isenção" in aviso["titulo"]
    r = c.get("/api/credenciais", headers=H)
    assert r.status_code == 403 and r.json()["aviso_pendente"]
    parcial = dict(TODAS)
    parcial["uso_responsavel"] = False
    r = c.post("/api/aviso-legal/aceitar", headers=H, json={"confirmacoes": parcial})
    assert r.status_code == 400 and r.json()["faltando"] == ["uso_responsavel"]
    assert c.get("/api/estado", headers=H).json()["aviso_aceito"] is False
    aceitar(c)
    assert c.get("/api/credenciais", headers=H).status_code == 200


def test_recusar_aviso_encerra(web):
    e, _, c, _ = web
    assert c.post("/api/aviso-legal/recusar", headers=H).status_code == 200
    assert e.evento_encerrar.is_set()


# ── Credenciais ──────────────────────────────────────────────────────────

def test_credenciais_so_em_memoria(web, raiz_temporaria):
    e, _, c, _ = web
    aceitar(c)
    r = c.post("/api/credenciais", headers=H, json={**CRED, "cpf": ""})
    assert r.status_code == 400
    r = c.post("/api/credenciais", headers=H, json=CRED)
    assert r.status_code == 200
    dados = c.get("/api/credenciais", headers=H).json()
    assert "senha" not in dados and dados["tem_senha"] and dados["preenchida"]
    # senha em branco + manter_senha preserva a senha anterior
    c.post("/api/credenciais", headers=H, json={**CRED, "senha": "", "manter_senha": True})
    assert e.sessao.sigaa.senha == "s3nh@"
    # nada sensível em disco
    for raiz, _dirs, arquivos in os.walk(raiz_temporaria):
        for nome in arquivos:
            with open(os.path.join(raiz, nome), "rb") as f:
                assert b"s3nh@" not in f.read()
    c.post("/api/credenciais/limpar", headers=H)
    assert not e.sessao.sigaa.preenchida()


# ── Disciplinas ──────────────────────────────────────────────────────────

def test_disciplinas_crud_e_confirmacoes(web):
    e, _, c, _ = web
    aceitar(c)
    r = c.post("/api/disciplinas", headers=H, json={"codigo": "fga0211", "turma": "01", "departamento": 673})
    assert r.status_code == 200 and r.json()["disciplinas"][0]["codigo"] == "FGA0211"

    r = c.post("/api/disciplinas", headers=H, json={"codigo": "XYZ1", "turma": "02", "departamento": 99999})
    assert r.status_code == 409 and r.json()["precisa_confirmar"]
    r = c.post("/api/disciplinas", headers=H, json={"codigo": "XYZ1", "turma": "02", "departamento": 99999, "confirmado": True})
    assert r.status_code == 200 and len(r.json()["disciplinas"]) == 2

    assert c.post("/api/disciplinas", headers=H, json={"codigo": "", "turma": "01", "departamento": 673}).status_code == 400

    # desativar, editar (não pode reativar), remover (pede confirmação)
    c.post("/api/disciplinas/0/alternar", headers=H, json={"chave": "FGA0211-01"})
    r = c.post("/api/disciplinas/0/editar", headers=H, json={"codigo": "FGA0211", "turma": "03", "departamento": 673, "chave_original": "FGA0211-01"})
    assert r.json()["disciplinas"][0]["ativa"] is False and r.json()["disciplinas"][0]["turma"] == "03"

    r = c.post("/api/disciplinas/0/remover", headers=H, json={"chave": "FGA0211-01"})
    assert r.status_code == 409 and "mudou" in r.json()["erro"]  # chave desatualizada é recusada
    r = c.post("/api/disciplinas/0/remover", headers=H, json={"chave": "FGA0211-03"})
    assert r.status_code == 409 and r.json()["precisa_confirmar"]
    r = c.post("/api/disciplinas/0/remover", headers=H, json={"chave": "FGA0211-03", "confirmado": True})
    assert [d["codigo"] for d in r.json()["disciplinas"]] == ["XYZ1"]
    assert c.post("/api/disciplinas/9/alternar", headers=H, json={}).status_code == 404


def test_busca_departamento_sem_acento(web):
    _, _, c, _ = web
    aceitar(c)
    r = c.get("/api/departamentos?q=computacao", headers=H).json()
    assert any(d["codigo"] == 508 for d in r["departamentos"])


# ── Execução ─────────────────────────────────────────────────────────────

class MotorFalso:
    execucao_id = "teste"

    def __init__(self):
        self._parar = None

    async def executar(self):
        self._parar = asyncio.Event()
        while not self._parar.is_set():
            await asyncio.sleep(0.05)

    def parar(self):
        if self._parar:
            self._parar.set()


def test_execucao_valida_confirma_e_para(web, monkeypatch):
    e, _, c, _ = web
    aceitar(c)
    monkeypatch.setattr(estado_mod, "construir_motor", lambda *a, **k: MotorFalso())

    r = c.post("/api/execucao/iniciar", headers=H, json={"modo": "monitoramento"})
    assert r.status_code == 400 and r.json()["ir_para"] == "credenciais"
    c.post("/api/credenciais", headers=H, json=CRED)
    r = c.post("/api/execucao/iniciar", headers=H, json={"modo": "monitoramento"})
    assert r.status_code == 400 and r.json()["problemas"]  # sem disciplinas ativas

    c.post("/api/disciplinas", headers=H, json={"codigo": "FGA0211", "turma": "01", "departamento": 673})
    r = c.post("/api/execucao/iniciar", headers=H, json={"modo": "matricula", "dry_run": True, "agendar_inicio": "31/02/2026 10:00:00"})
    assert r.status_code == 400 and any("agendamento" in p for p in r.json()["problemas"])

    r = c.post("/api/execucao/iniciar", headers=H, json={"modo": "matricula", "dry_run": False})
    assert r.status_code == 409 and "DE VERDADE" in r.json()["erro"]  # confirmação extra da matrícula real
    assert not e.status_execucao()["em_execucao"]

    r = c.post("/api/execucao/iniciar", headers=H, json={"modo": "monitoramento"})
    assert r.status_code == 200 and r.json()["execucao"]["em_execucao"]
    assert c.post("/api/execucao/iniciar", headers=H, json={"modo": "monitoramento"}).status_code == 409

    r = c.post("/api/encerrar", headers=H, json={})
    assert r.status_code == 409  # pede confirmação com o motor rodando
    assert not e.evento_encerrar.is_set()

    c.post("/api/execucao/parar", headers=H)
    for _ in range(50):
        if not e.status_execucao()["em_execucao"]:
            break
        time.sleep(0.05)
    assert e.status_execucao()["estado"] == "parado"
    assert c.post("/api/encerrar", headers=H, json={}).status_code == 200
    assert e.evento_encerrar.is_set()


# ── Dashboard e logs ─────────────────────────────────────────────────────

def test_dashboard_e_logs_leem_o_audit(web, raiz_temporaria):
    _, _, c, _ = web
    aceitar(c)
    pasta = raiz_temporaria / "data"
    pasta.mkdir(exist_ok=True)
    linhas = [
        {"timestamp": "2026-01-01 10:00:00", "level": "INFO", "worker": "MAIN", "message": "SESSAO_INICIADA id=x"},
        {"timestamp": "2026-01-01 10:00:01", "level": "INFO", "worker": "W0", "message": "[W0] 🔍 Buscando FGA0211-01..."},
        {"timestamp": "2026-01-01 10:00:01", "level": "WARNING", "worker": "W0", "message": "[W0] 🚨 VAGA DETECTADA (80ms) -> FGA0211-01 (1 vaga(s))!"},
        {"timestamp": "2026-01-01 10:00:02", "level": "ERROR", "worker": "W0", "message": "<script>alert(1)</script>"},
    ]
    (pasta / "sigaa_sniper_audit.json").write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in linhas), encoding="utf-8")
    d = c.get("/api/dashboard", headers=H).json()
    assert d["vagas_encontradas"] == 1 and d["workers"][0]["id"] == "W0"
    r = c.get("/api/logs?desde=0", headers=H).json()
    assert r["ultimo_seq"] == 4 and r["registros"][2]["categoria"] == "SUCESSO"
    assert c.get("/api/logs?desde=4", headers=H).json()["registros"] == []
    download = c.get("/api/logs/arquivo", headers=H)
    assert download.status_code == 200 and "attachment" in download.headers["content-disposition"]


# ── Notificações ─────────────────────────────────────────────────────────

def test_notificacoes_persistencia_opt_in(web, raiz_temporaria):
    e, _, c, _ = web
    aceitar(c)
    base = {"telegram_ativo": True, "ntfy_ativo": True, "alarme_ativo": False, "alarme_repeticoes": 3, "alarme_duracao": 20,
            "telegram_token": "TOK", "telegram_chat_id": "1", "ntfy_topic": "top", "ntfy_servidor": "https://x.ntfy",
            "eventos": {"erro_critico": True}}
    assert c.post("/api/notificacoes", headers=H, json={**base, "alarme_repeticoes": 99}).status_code == 400
    r = c.post("/api/notificacoes", headers=H, json={**base, "lembrar": False})
    assert r.status_code == 200 and not (raiz_temporaria / "config" / "notificacoes.secrets.json").exists()
    assert e.settings["notificacoes"]["eventos"]["erro_critico"] is True
    c.post("/api/notificacoes", headers=H, json={**base, "lembrar": True})
    # Fase 6 (065): no Windows o arquivo é cifrado com a DPAPI — o token não aparece no disco.
    from app.core.config import carregar_segredos_notificacao
    bruto = (raiz_temporaria / "config" / "notificacoes.secrets.json").read_text(encoding="utf-8")
    assert carregar_segredos_notificacao()["ntfy_servidor"] == "https://x.ntfy"
    if os.name == "nt":
        assert "TOK" not in bruto and json.loads(bruto)["formato"] == "dpapi-v1"
    c.post("/api/notificacoes/persistencia", headers=H, json={"lembrar": False})
    assert not (raiz_temporaria / "config" / "notificacoes.secrets.json").exists()
    r = c.post("/api/notificacoes/testar", headers=H, json={"canal": "todos"})
    assert r.status_code == 400
    r = c.post("/api/notificacoes/testar", headers=H, json={"canal": "telegram"})
    assert r.status_code == 400 and "token" in r.json()["erro"]


# ── Configurações avançadas, restaurar, exportar/importar ───────────────

def _avancado(c):
    a = c.get("/api/avancado", headers=H).json()
    return {k: a[k] for k in ("num_workers", "intervalo_busca", "timeout_req", "abrir_dashboard_ao_iniciar",
                                "nivel_log_console", "logs", "json_audit", "urls", "web")}


def test_avancado_valida_e_confirma_urls(web):
    e, _, c, _ = web
    aceitar(c)
    corpo = _avancado(c)
    assert c.post("/api/avancado", headers=H, json={**corpo, "num_workers": 500}).status_code == 400
    assert c.post("/api/avancado", headers=H, json={**corpo, "web": {**corpo["web"], "porta": 22}}).status_code == 400
    urls = {**corpo["urls"], "sigaa_base": "https://outro.exemplo"}
    r = c.post("/api/avancado", headers=H, json={**corpo, "urls": urls})
    assert r.status_code == 409
    r = c.post("/api/avancado", headers=H, json={**corpo, "urls": urls, "confirmado": True, "num_workers": 5})
    assert r.status_code == 200 and e.settings["num_workers"] == 5
    r = c.post("/api/avancado", headers=H, json={**_avancado(c), "web": {"host": "127.0.0.1", "porta": 9001, "abrir_navegador": False}})
    assert "próxima vez" in r.json()["mensagem"]

    assert c.post("/api/avancado/restaurar", headers=H, json={}).status_code == 400
    assert c.post("/api/avancado/restaurar", headers=H, json={"todas": True}).status_code == 409
    r = c.post("/api/avancado/restaurar", headers=H, json={"todas": True, "confirmado": True})
    assert r.json()["avancado"]["num_workers"] == 20 and r.json()["avancado"]["web"]["porta"] == 8765


def test_exportar_importar(web):
    e, _, c, _ = web
    aceitar(c)
    c.post("/api/disciplinas", headers=H, json={"codigo": "FGA0211", "turma": "01", "departamento": 673})
    c.post("/api/credenciais", headers=H, json=CRED)
    exportado = c.get("/api/config/exportar", headers=H)
    assert exportado.status_code == 200 and b"s3nh@" not in exportado.content
    pacote = exportado.json()
    pacote["disciplinas"].append({"codigo": "MAT0025", "turma": "02", "departamento": 518})

    malicioso = json.dumps({"settings": {"token": "abc"}})
    assert c.post("/api/config/importar/previa", headers=H, json={"conteudo": malicioso}).status_code == 400
    assert c.post("/api/config/importar/previa", headers=H, json={"conteudo": "{nao json"}).status_code == 400

    conteudo = json.dumps(pacote)
    previa = c.post("/api/config/importar/previa", headers=H, json={"conteudo": conteudo}).json()
    assert previa["qtd_disciplinas"] == 2 and previa["tem_settings"]
    assert c.post("/api/config/importar/aplicar", headers=H, json={"conteudo": conteudo}).status_code == 200
    assert [d.codigo for d in e.disciplinas] == ["FGA0211", "MAT0025"]


# ── Diagnóstico, experimental, ajuda, sobre, assistente ─────────────────

def test_diagnostico_sem_rede(web, monkeypatch):
    _, _, c, _ = web
    aceitar(c)
    from app.core.diagnostics import ResultadoChecagem

    async def falso():
        return ResultadoChecagem("Conectividade com o SIGAA", True, "HTTP 200 (simulado)")

    monkeypatch.setattr(estado_mod, "checar_conectividade_sigaa", falso)
    r = c.post("/api/diagnostico/completo", headers=H).json()
    assert "não contém credenciais" in r["relatorio"]
    assert any(i["nome"] == "Modo configurado" for i in r["itens"])


def test_experimental_pede_confirmacao(web):
    _, _, c, _ = web
    aceitar(c)
    ids = [x["id"] for x in c.get("/api/experimental", headers=H).json()["experimentos"]]
    assert "backoff_retry" in ids
    assert c.post("/api/experimental/executar", headers=H, json={"id": "backoff_retry"}).status_code == 409
    r = c.post("/api/experimental/executar", headers=H, json={"id": "backoff_retry", "confirmado": True})
    assert "Backoff funcionou" in r.json()["resultado"]


def test_ajuda_sobre_e_assistente(web, raiz_temporaria):
    e, _, c, _ = web
    aceitar(c)
    docs = c.get("/api/ajuda", headers=H).json()["documentos"]
    assert "Guia de Uso" in docs[0]["conteudo"]
    assert c.get("/api/sobre", headers=H).json()["repositorio"].startswith("https://github.com/")
    assert c.get("/api/estado", headers=H).json()["primeira_execucao"] is True
    # Pós-6.0.0: o assistente valida tudo antes de salvar (credencial pela metade ou disciplina inválida → 400).
    ruim = c.post("/api/assistente/finalizar", headers=H, json={
        "credenciais": {"usuario": "u", "senha": "", "cpf": "", "nascimento": ""},
        "disciplinas": [{"codigo": "fga0211", "turma": "01", "departamento": 673}, {"codigo": "", "turma": "x", "departamento": 1}],
        "execucao": {"modo": "matricula", "preset": "leve"}})
    assert ruim.status_code == 400 and not (raiz_temporaria / "config" / "settings.json").exists()
    r = c.post("/api/assistente/finalizar", headers=H, json={
        "credenciais": {}, "disciplinas": [{"codigo": "fga0211", "turma": "01", "departamento": 673}],
        "execucao": {"modo": "matricula", "preset": "leve", "dry_run": True}})
    assert r.status_code == 200
    est = c.get("/api/estado", headers=H).json()
    assert est["primeira_execucao"] is False and est["qtd_disciplinas"] == 1 and est["modo"] == "matricula"
    assert (raiz_temporaria / "config" / "settings.json").exists()


# ── Fase 1: validações, lote e carga estimada ───────────────────────────

def test_credenciais_invalidas_sao_apontadas_e_bloqueiam_inicio(web, monkeypatch):
    e, _, c, _ = web
    aceitar(c)
    monkeypatch.setattr(estado_mod, "construir_motor", lambda *a, **k: MotorFalso())
    r = c.post("/api/credenciais", headers=H, json={**CRED, "cpf": "12345678900", "nascimento": "01022003"})
    assert r.status_code == 400 and any("CPF inválido" in p for p in r.json()["problemas"])
    assert e.sessao.sigaa.nascimento == "01/02/2003"  # normalizada mesmo com o CPF errado
    c.post("/api/disciplinas", headers=H, json={"codigo": "FGA0211", "turma": "01", "departamento": 673})
    r = c.post("/api/execucao/iniciar", headers=H, json={"modo": "monitoramento"})
    assert r.status_code == 400 and r.json()["ir_para"] == "credenciais"
    assert not e.status_execucao()["em_execucao"]
    est = c.get("/api/estado", headers=H).json()
    assert est["problemas_credenciais"] and est["carga"]["nivel"] in ("baixa", "moderada", "alta")


def test_disciplina_duplicada_e_turma_com_letra_recusadas(web):
    _, _, c, _ = web
    aceitar(c)
    assert c.post("/api/disciplinas", headers=H, json={"codigo": "FGA0211", "turma": "01", "departamento": 673}).status_code == 200
    r = c.post("/api/disciplinas", headers=H, json={"codigo": "FGA0211", "turma": "01", "departamento": 673, "confirmado": True})
    assert r.status_code == 400 and "já está cadastrada" in r.json()["erro"]
    r = c.post("/api/disciplinas", headers=H, json={"codigo": "FGA0212", "turma": "A", "departamento": 673, "confirmado": True})
    assert r.status_code == 400
    r = c.post("/api/disciplinas", headers=H, json={"codigo": "FGA0211", "turma": "02", "departamento": 673})
    assert r.status_code == 409 and "mais de uma turma" in r.json()["erro"]


def test_cadastro_em_lote(web):
    e, _, c, _ = web
    aceitar(c)
    texto = "FGA0211 01 673\nMAT0025;02;518\nFGA0211 01 673\nlixo"
    previa = c.post("/api/disciplinas/lote/previa", headers=H, json={"texto": texto}).json()
    assert previa["validas"] == 2 and previa["invalidas"] == 2 and e.disciplinas == []  # prévia não salva nada
    r = c.post("/api/disciplinas/lote/aplicar", headers=H, json={"texto": texto})
    assert r.status_code == 200 and [d["chave"] for d in r.json()["disciplinas"]] == ["FGA0211-01", "MAT0025-02"]
    # linha com aviso (departamento desconhecido) exige confirmação
    r = c.post("/api/disciplinas/lote/aplicar", headers=H, json={"texto": "CIC0004 01 99999"})
    assert r.status_code == 409 and r.json()["precisa_confirmar"]
    r = c.post("/api/disciplinas/lote/aplicar", headers=H, json={"texto": "CIC0004 01 99999", "confirmado": True})
    assert r.status_code == 200 and len(e.disciplinas) == 3
    assert c.post("/api/disciplinas/lote/aplicar", headers=H, json={"texto": "FGA0211 01 673"}).status_code == 400
    assert c.post("/api/disciplinas/lote/previa", headers=H, json={"texto": "  "}).status_code == 400


def test_avancado_informa_presets_e_carga(web):
    _, _, c, _ = web
    aceitar(c)
    a = c.get("/api/avancado", headers=H).json()
    assert set(a["presets_carga"]) == {"leve", "moderado", "padrao"}
    assert a["carga"]["preset"] == "padrao" and a["carga"]["nivel"] == "alta"
    assert a["carga_parametros"]["latencia_seg"] > 0


def test_central_nao_repete_a_mesma_vaga(web):
    e, _, c, _ = web
    aceitar(c)
    for _ in range(5):
        e._ao_evento_motor("vaga_detectada", {"codigo": "FGA0211", "turma": "01", "vagas": 2})
    e._ao_evento_motor("vaga_detectada", {"codigo": "FGA0211", "turma": "01", "vagas": 3})  # mudou: avisa
    e._ao_evento_motor("matricula_bloqueada", {"codigo": "FGA0211", "turma": "01"})
    e._ao_evento_motor("evento_desconhecido", {})
    eventos = c.get("/api/estado", headers=H).json()["eventos"]
    assert [ev["tipo"] for ev in eventos] == ["vaga_detectada", "vaga_detectada", "matricula_bloqueada"]
    assert eventos[1]["texto"].startswith("Vaga encontrada em FGA0211-01 (3")


# ── Fase 3: histórico ────────────────────────────────────────────────────

def test_historico_api_filtros_detalhe_comparacao_exportacao(web, raiz_temporaria):
    from datetime import datetime
    from app.core import historico
    from tests.test_historico import _resumo
    e, _, c, anonimo = web
    aceitar(c)
    agora = datetime.now().replace(microsecond=0)
    historico.registrar_execucao(_resumo("exec-a", agora, vagas=3), {"vagas_series": {"FGA0211-01": [[agora.timestamp(), 2]]}, "pontos": []})
    historico.registrar_execucao(_resumo("exec-b", agora, alvos=("MAT0025-02",)))
    h = c.get("/api/historico?dias=30", headers=H).json()
    assert h["totais"]["execucoes"] == 2 and h["mapa"]["total"] == 1 and "FGA0211-01" in h["disciplinas"]
    assert [x["id"] for x in c.get("/api/historico?disciplina=MAT0025-02", headers=H).json()["execucoes"]] == ["exec-b"]
    assert c.get("/api/historico/execucao/exec-a", headers=H).json()["resumo"]["execucao_id"] == "exec-a"
    assert c.get("/api/historico/execucao/nada", headers=H).status_code == 404
    assert c.get("/api/historico/execucao/..%2F..%2Fx", headers=H).status_code == 404  # id fora do padrão nem casa a rota
    comp = c.get("/api/historico/comparar?ids=exec-a,exec-b", headers=H).json()
    assert len(comp["execucoes"]) == 2
    assert c.get("/api/historico/comparar?ids=exec-a", headers=H).status_code == 400
    csv_resp = c.get("/api/historico/exportar?tipo=execucoes&formato=csv", headers=H)
    assert csv_resp.status_code == 200 and "attachment" in csv_resp.headers["content-disposition"] and "exec-a" in csv_resp.text
    assert c.get("/api/historico/exportar?tipo=vagas&formato=json", headers=H).json()[0]["vagas"] == 2
    assert c.get("/api/historico/exportar?tipo=x&formato=csv", headers=H).status_code == 400
    assert anonimo.get("/api/historico/exportar?tipo=execucoes&formato=csv", headers=H).status_code == 401
    assert c.post("/api/historico/apagar", headers=H, json={}).status_code == 409
    assert c.post("/api/historico/apagar", headers=H, json={"confirmado": True}).status_code == 200
    assert c.get("/api/historico", headers=H).json()["totais"]["execucoes"] == 0


def test_historico_nas_configuracoes_avancadas(web):
    e, _, c, _ = web
    aceitar(c)
    corpo = _avancado(c)
    assert c.get("/api/avancado", headers=H).json()["historico"] == {"ativo": True, "dias_retencao": 180}
    assert c.post("/api/avancado", headers=H, json={**corpo, "historico": {"ativo": True, "dias_retencao": 99999}}).status_code == 400
    r = c.post("/api/avancado", headers=H, json={**corpo, "historico": {"ativo": False, "dias_retencao": 30}})
    assert r.status_code == 200 and e.settings["historico"] == {"ativo": False, "dias_retencao": 30}


# ── Fase 4: automação avançada pela Web ──────────────────────────────────

def test_pausar_retomar_janela_e_disciplinas_em_execucao(web, monkeypatch):
    from app.core import engine
    from tests.test_engine_fluxo import SigaaSimulado
    simulado = SigaaSimulado(vagas=0)
    original = httpx.AsyncClient
    monkeypatch.setattr(engine.httpx, "AsyncClient", lambda *a, **k: original(*a, **{**k, "transport": httpx.MockTransport(simulado)}))
    e, _, c, _ = web
    aceitar(c)
    c.post("/api/credenciais", headers=H, json=CRED)
    r = c.post("/api/disciplinas", headers=H, json={"codigo": "FGA0211", "turma": "01", "departamento": 673,
                                                    "grupo": "calculo", "prioridade": "alta"})
    assert r.json()["disciplinas"][0]["grupo"] == "calculo" and r.json()["disciplinas"][0]["prioridade"] == "alta"
    e.settings.update({"num_workers": 1, "intervalo_busca": 0.05})
    janela_ruim = {"ativa": True, "inicio": "99:00", "fim": "07:00", "dias": [0]}
    r = c.post("/api/execucao/iniciar", headers=H, json={"modo": "monitoramento", "janela": janela_ruim})
    assert r.status_code == 400 and any("Janela" in p for p in r.json()["problemas"])
    assert c.post("/api/execucao/pausar", headers=H).status_code == 409  # nada rodando

    r = c.post("/api/execucao/iniciar", headers=H, json={"modo": "monitoramento", "janela": {"ativa": False, "inicio": "07:00",
                                                                                              "fim": "23:00", "dias": [0]}})
    assert r.status_code == 200
    try:
        for _ in range(200):
            if e._motor.fase == "monitorando":
                break
            time.sleep(0.05)
        assert c.post("/api/execucao/pausar", headers=H).status_code == 200
        for _ in range(40):
            if c.get("/api/estado", headers=H).json()["execucao"]["pausado"]:
                break
            time.sleep(0.05)
        assert c.get("/api/estado", headers=H).json()["execucao"]["pausado"] is True
        assert c.post("/api/execucao/retomar", headers=H).status_code == 200
        r = c.post("/api/disciplinas", headers=H, json={"codigo": "FGA0211", "turma": "02", "departamento": 673, "grupo": "calculo"})
        assert "execução em andamento" in r.json()["mensagem"]
        for _ in range(100):
            if "FGA0211-02" in e._motor.alvos_ativos:
                break
            time.sleep(0.05)
        assert "FGA0211-02" in e._motor.alvos_ativos and e._motor.meta_alvos["FGA0211-02"]["grupo"] == "calculo"
        c.post("/api/disciplinas/1/alternar", headers=H, json={"chave": "FGA0211-02"})  # desativar = sair da busca
        for _ in range(100):
            if "FGA0211-02" not in e._motor.alvos_ativos:
                break
            time.sleep(0.05)
        assert "FGA0211-02" not in e._motor.alvos_ativos
    finally:
        c.post("/api/execucao/parar", headers=H)
        for _ in range(200):
            if not e.status_execucao()["em_execucao"]:
                break
            time.sleep(0.05)
    assert e.settings["verificacao_previa"] is True  # padrão: verifica antes de começar
    est = c.get("/api/estado", headers=H).json()
    assert est["grupos"] == ["calculo"] and est["janela"]["inicio"] == "07:00"
