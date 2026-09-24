"""
Fase 5 — observabilidade, privacidade e suporte:
redação de dumps (066), visualizador (064), pacote de suporte (051),
configurações inseguras (067), teste de URLs (047), rastreamento de tentativas
(059), linha do tempo (054), supervisor de workers (057), alertas por limiar
(058), anomalias/manutenção (090), resumo periódico (052), assistente (079)
e recomendações (089).
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import time
import zipfile

import httpx
import pytest

from app.core import engine
from app.core.alertas import AvaliadorAlertas, texto_resumo_periodico
from app.core.assistente import aplicar_recomendacao, diagnosticar, recomendar_configuracao
from app.core.config import PADROES_SETTINGS, Disciplina, carregar_settings
from app.core.credentials import CredenciaisSigaa
from app.core.logging_setup import configurar_logging
from app.core.seguranca_config import alertas_de_configuracao
from app.core.seguranca_config import testar_urls as _testar_urls
from app.core.suporte import (conteudo_pacote_suporte, gerar_pacote_suporte, ler_dump, listar_dumps, redigir_html,
                              redigir_texto)
from app.dashboard.linha_do_tempo import linha_do_tempo, montar_linha_do_tempo
from tests.test_engine_fluxo import SigaaSimulado, pagina_resultado, rodar_ate

CRED = CredenciaisSigaa(usuario="200012345", senha="s3nh@Forte", cpf="123.456.789-09", nascimento="01/02/2003")


@pytest.fixture
def sigaa(monkeypatch):
    simulado = SigaaSimulado()
    original = httpx.AsyncClient

    def cliente(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(simulado)
        return original(*args, **kwargs)

    monkeypatch.setattr(engine.httpx, "AsyncClient", cliente)
    return simulado


def novo_motor(**extra):
    parametros = dict(credenciais=CRED, disciplinas=[["FGA0211", "01", 673]], num_workers=1, intervalo_busca=0.05,
                      timeout_req=5, dry_run=True, modo="matricula")
    parametros.update(extra)
    return engine.MotorMatricula(**parametros)


# ── 066: redação ──────────────────────────────────────────────────────────

PAGINA_PESSOAL = """<html><body><div id="info-usuario"><span>JOAO DA SILVA</span> 200012345</div>
<form id="j_id_jsp_9" action="/sigaa/x.jsf">
<input type="hidden" name="javax.faces.ViewState" value="H4sIAAAAsegredo">
<input type="text" name="j_id_jsp_9:cpf" value="12345678909">
<input type="password" name="j_id_jsp_9:senha" value="s3nh@Forte">
<input type="submit" name="j_id_jsp_9:btnConfirmar" value="Confirmar Matrícula">
<textarea name="obs">texto livre</textarea>
</form><p>Contato: joao@aluno.unb.br · CPF 123.456.789-09 · Matrícula 20/0012345 · nascido em 01/02/2003</p>
<p>Período letivo 2026.2 — turma 01</p></body></html>"""


def test_redigir_html_mascara_dados_pessoais_e_preserva_estrutura():
    r = redigir_html(PAGINA_PESSOAL, CRED)
    for segredo in ("JOAO DA SILVA", "200012345", "H4sIAAAAsegredo", "12345678909", "s3nh@Forte", "texto livre",
                    "joao@aluno.unb.br", "123.456.789-09", "20/0012345", "01/02/2003"):
        assert segredo not in r, segredo
    # O que importa para o diagnóstico continua: nomes de campos, botão e textos da página.
    assert 'name="j_id_jsp_9:btnConfirmar" value="Confirmar Matrícula"' in r
    assert 'id="j_id_jsp_9"' in r and "Período letivo 2026.2 — turma 01" in r


def test_redigir_texto_sem_credenciais_usa_padroes():
    t = redigir_texto('{"message": "CPF 111.444.777-35 e 11144477735, mat 190012345, x@y.com", "latencia_ms": 230}')
    assert "111.444.777-35" not in t and "11144477735" not in t and "190012345" not in t and "x@y.com" not in t
    assert '"latencia_ms": 230' in t


def test_bloco_grande_com_classe_discente_nao_apaga_a_pagina():
    html = "<div class='portal-discente'>" + "<p>Tabela de turmas</p>" * 40 + "</div>"
    assert "Tabela de turmas" in redigir_html(html)


def test_dump_do_motor_ja_vai_mascarado(sigaa, raiz_temporaria):
    sigaa.resposta_final = "Aluno JOAO 200012345 · CPF 123.456.789-09 · resposta estranha"
    motor = novo_motor(dry_run=False)
    rodar_ate(motor, lambda m: m.snapshot()["contadores"].get("dumps", 0) >= 1)
    dumps = listar_dumps()
    assert dumps and dumps[0]["motivo"].startswith("confirmacao_inconclusiva")
    assert "sem mensagem de sucesso" in dumps[0]["motivo_texto"]
    with open(os.path.join(raiz_temporaria, "logs", dumps[0]["nome"]), encoding="utf-8") as f:
        conteudo = f.read()
    assert "200012345" not in conteudo and "123.456.789-09" not in conteudo and "resposta estranha" in conteudo
    # A tentativa guarda o nome da página capturada.
    assert motor.tentativas_publicas()[0]["dump"] == dumps[0]["nome"]


# ── 064: visualizador ─────────────────────────────────────────────────────

def test_ler_dump_so_aceita_nomes_de_dump(raiz_temporaria):
    os.makedirs(raiz_temporaria / "logs", exist_ok=True)
    nome = f"debug_W1_selecao_falha_FGA0211_{int(time.time())}.html"
    (raiz_temporaria / "logs" / nome).write_text(PAGINA_PESSOAL, encoding="utf-8")
    (raiz_temporaria / "segredo.html").write_text("NAO", encoding="utf-8")
    lido = ler_dump(nome, CRED)
    assert lido and "Tela de confirmação não detectada" in lido["motivo_texto"] and lido["disciplina"] == "FGA0211"
    assert "JOAO DA SILVA" not in lido["texto"] and "Período letivo" in lido["texto"] and "<" not in lido["texto"]
    for invalido in ("../segredo.html", "..\\segredo.html", str(raiz_temporaria / "segredo.html"), "debug_x.txt", "", None):
        assert ler_dump(invalido) is None


# ── 051: pacote de suporte ────────────────────────────────────────────────

def test_pacote_de_suporte_sem_dados_pessoais(raiz_temporaria):
    os.makedirs(raiz_temporaria / "logs", exist_ok=True)
    os.makedirs(raiz_temporaria / "data", exist_ok=True)
    (raiz_temporaria / "logs" / f"debug_W2_confirmacao_inconclusiva_FGA0211_{int(time.time())}.html").write_text(
        PAGINA_PESSOAL, encoding="utf-8")
    (raiz_temporaria / "data" / "sigaa_sniper_audit.json").write_text(
        json.dumps({"timestamp": "2026-09-24 10:00:00", "message": "login de 200012345 com cpf 123.456.789-09"}) + "\n",
        encoding="utf-8")
    previa = conteudo_pacote_suporte(CRED)
    nomes = [a["nome"] for a in previa]
    assert nomes[0] == "LEIA-ME.txt" and "diagnostico.txt" in nomes and "configuracao.json" in nomes
    assert "eventos_recentes.jsonl" in nomes and any(n.startswith("paginas/") for n in nomes)
    z = zipfile.ZipFile(io.BytesIO(gerar_pacote_suporte(CRED)))
    assert sorted(z.namelist()) == sorted(nomes)
    tudo = "".join(z.read(n).decode("utf-8") for n in z.namelist())
    for segredo in ("200012345", "123.456.789-09", "s3nh@Forte", "JOAO DA SILVA", "01/02/2003"):
        assert segredo not in tudo, segredo
    assert "Segurança: Carga alta" in z.read("diagnostico.txt").decode("utf-8")


# ── 067 / 047 ─────────────────────────────────────────────────────────────

def test_configuracoes_inseguras():
    s = json.loads(json.dumps(PADROES_SETTINGS))
    # Com os padrões, só a carga do perfil Intenso (o mesmo aviso da checklist de Execução).
    assert [a["id"] for a in alertas_de_configuracao(s, raiz="C:/Programas/Sniper")] == ["carga_alta"]
    s["num_workers"], s["intervalo_busca"] = 4, 1.5
    assert alertas_de_configuracao(s, raiz="C:/Programas/Sniper") == []
    s["web"]["host"] = "0.0.0.0"
    s["urls"] = {**s["urls"], "cas_login": "https://sigaa-falso.com/login"}
    s["protecao"]["disjuntor"] = False
    s["modo"], s["dry_run"] = "matricula", False
    ids = {a["id"]: a["nivel"] for a in alertas_de_configuracao(s, raiz="C:/Users/x/OneDrive - UnB/Sniper")}
    assert ids == {"web_exposta": "risco", "urls_fora_unb": "risco", "protecao_desligada": "atencao",
                   "pasta_nuvem": "atencao", "matricula_real": "atencao"}


def test_testar_urls_nunca_contata_dominio_de_fora():
    vistos = []

    def transporte(req):
        vistos.append(str(req.url))
        if req.url.host == "autenticacao.unb.br":
            return httpx.Response(200, text="<html>login</html>")
        return httpx.Response(302, headers={"Location": "https://autenticacao.unb.br/sso-server/login"})

    with httpx.Client(transport=httpx.MockTransport(transporte), follow_redirects=True) as c:
        r = {x["nome"]: x for x in _testar_urls({"portal": "https://sigaa.unb.br/portal", "falsa": "https://golpe.com/x",
                                                "http": "http://sigaa.unb.br/x"}, cliente=c)}
    assert r["portal"]["ok"] and r["portal"]["pede_login"] and "pede login" in r["portal"]["texto"]
    assert not r["falsa"]["ok"] and "Não testado" in r["falsa"]["texto"] and not r["http"]["ok"]
    assert not any("golpe.com" in v for v in vistos) and not any(v.startswith("http://") for v in vistos)


# ── 059: tentativas ───────────────────────────────────────────────────────

def test_tentativa_rastreada_com_etapas_e_tempos(sigaa, raiz_temporaria):
    motor = novo_motor(logger=configurar_logging())
    rodar_ate(motor, lambda m: not m.alvos_ativos)
    t = motor.tentativas_publicas()
    assert len(t) == 1 and t[0]["resultado"] == "SUCESSO" and t[0]["chave"] == "FGA0211-01"
    assert [e["etapa"] for e in t[0]["etapas"]] == ["selecao_enviada", "tela_confirmacao", "formulario_preenchido",
                                                   "dry_run_parado"]
    assert t[0]["total_ms"] >= t[0]["etapas"][-1]["ms"] >= 0 and t[0]["desde_vaga_ms"] >= t[0]["total_ms"]
    assert not any(k.startswith("_") for k in t[0])
    # As linhas do log carregam o mesmo tentativa_id em todas as etapas.
    linhas = [json.loads(l) for l in open(raiz_temporaria / "data" / "sigaa_sniper_audit.json", encoding="utf-8")]
    ids = {l.get("tentativa_id") for l in linhas if l.get("evento") in ("tentativa_iniciada", "tentativa_etapa", "tentativa_concluida")}
    assert ids == {t[0]["id"]}
    # E a linha do tempo conta a história sem as buscas "sem vagas".
    lt = linha_do_tempo(str(raiz_temporaria / "data" / "sigaa_sniper_audit.json"))
    eventos = [i["evento"] for i in lt["itens"]]
    assert eventos[0] == "sessao_iniciada" and "tentativa_etapa" in eventos and "matricula_sucesso" in eventos
    assert "busca" not in eventos and "sem_vagas" not in eventos and lt["execucao_id"] == motor.execucao_id
    assert motor.resumo["tentativas"][0]["id"] == t[0]["id"]


def test_linha_do_tempo_agrupa_e_filtra_por_execucao():
    def r(ts, evento, eid="A", **k):
        return {"timestamp": f"2026-09-24 10:{ts}", "evento": evento, "execucao_id": eid, "message": evento, "level": "INFO", **k}
    registros = [r("00:00", "sessao_iniciada"), r("00:05", "login_ok", worker="W0"), r("00:06", "login_ok", worker="W1"),
                 r("00:20", "login_ok"), r("02:00", "login_ok"), r("03:00", "vaga_detectada", codigo="X", turma="01"),
                 r("03:01", "vaga_detectada", codigo="Y", turma="01"), r("04:00", "sessao_iniciada", eid="B")]
    lt = montar_linha_do_tempo(registros, "A")
    assert lt["execucoes"] == ["B", "A"]
    assert [(i["evento"], i["quantidade"]) for i in lt["itens"]] == [
        ("sessao_iniciada", 1), ("login_ok", 3), ("login_ok", 1), ("vaga_detectada", 1), ("vaga_detectada", 1)]
    assert lt["itens"][1]["hora_fim"] == "10:00:20"
    assert montar_linha_do_tempo(registros)["execucao_id"] == "B"


# ── 057: supervisor ───────────────────────────────────────────────────────

def test_supervisor_recria_worker_travado(sigaa, monkeypatch):
    original = engine.SigaaWorker.teleportar_departamento
    chamadas = {"n": 0}

    async def trava_na_primeira(self, id_depto):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            self.mudar_estado("preparando")
            await asyncio.sleep(3600)  # "socket preso" sem timeout
        return await original(self, id_depto)

    monkeypatch.setattr(engine.SigaaWorker, "teleportar_departamento", trava_na_primeira)
    sigaa.vagas = 0
    motor = novo_motor(modo="monitoramento", supervisor_seg=0.6)
    motor.intervalo_supervisor = 0.2
    rodar_ate(motor, lambda m: m.snapshot()["contadores"].get("buscas", 0) >= 2, timeout=20)
    assert motor.reinicios_workers[0] == 1
    assert [w["id"] for w in motor.snapshot()["workers"]] == ["W0"]  # sem o worker antigo duplicado


def test_supervisor_nunca_mexe_em_tentativa_nem_em_pausa():
    motor = novo_motor(supervisor_seg=1)
    w = engine.SigaaWorker(0, motor)
    w.ultimo_batimento = w.ultimo_progresso = time.time() - 100
    for estado in ("tentando", "pausado", "contido", "aguardando", "fila_login", "iniciando"):
        w.estado = estado
        assert not motor._worker_travado(w, time.time())
    w.estado = "buscando"
    assert motor._worker_travado(w, time.time())
    w.tentativa = {"id": "x"}
    assert not motor._worker_travado(w, time.time())


# ── 058 / 090 / 052: alertas, anomalias, resumo ───────────────────────────

def _snap(pontos, **extra):
    base = {"fase": "monitorando", "pausado": False, "disjuntor": {"estado": "fechado"}, "contadores": {"buscas": 0},
            "alvos": [], "telemetria": {"pontos": pontos}}
    base.update(extra)
    return base


def test_alerta_de_taxa_de_erro_dispara_uma_vez_e_resolve():
    av = AvaliadorAlertas({"taxa_erro_min": 1, "sem_busca_min": 60, "sem_resposta_min": 60})
    t0 = 1_000_000.0
    ruins = [{"t": t0 + i, "req": 2, "p50": 300, "erros": {"timeout": 1}} for i in range(61)]
    m = av.avaliar(_snap(ruins, contadores={"buscas": 1}), t0 + 61)
    assert [(x["regra"], x["estado"]) for x in m] == [("taxa_erro", "ativo")] and "50%" in m[0]["texto"]
    assert av.avaliar(_snap(ruins, contadores={"buscas": 2}), t0 + 62) == []  # não repete
    bons = ruins + [{"t": t0 + 61 + i, "req": 2, "p50": 300, "erros": {}} for i in range(1, 62)]
    m = av.avaliar(_snap(bons, contadores={"buscas": 3}), t0 + 123)
    assert [(x["regra"], x["estado"]) for x in m] == [("taxa_erro", "resolvido")]


def test_alertas_nao_disparam_pausado_e_sem_busca_explica_departamento():
    av = AvaliadorAlertas({"sem_busca_min": 1, "sem_resposta_min": 60})
    t0 = 2_000_000.0
    assert av.avaliar(_snap([], pausado=True), t0) == []
    assert av.avaliar(_snap([], pausado=True), t0 + 500) == []
    alvos = [{"ativo": True, "estado": "departamento_indisponivel"}]
    assert av.avaliar(_snap([], alvos=alvos), t0 + 501) == []
    m = av.avaliar(_snap([], alvos=alvos), t0 + 562)
    assert m and m[0]["regra"] == "sem_busca" and "departamentos não abre" in m[0]["texto"]


def test_lentidao_anormal():
    av = AvaliadorAlertas({"sem_busca_min": 60, "sem_resposta_min": 60})
    t0 = 3_000_000.0
    pontos = [{"t": t0 + i, "req": 1, "p50": 200, "erros": {}} for i in range(200)]
    pontos += [{"t": t0 + 200 + i, "req": 1, "p50": 2500, "erros": {}} for i in range(20)]
    assert AvaliadorAlertas().avaliar(_snap(pontos[:205], contadores={"buscas": 5}), t0 + 205) == []  # pico curto não conta
    m = av.avaliar(_snap(pontos, contadores={"buscas": 5}), t0 + 220)
    assert any(x["regra"] == "lentidao" for x in m)


def test_pagina_de_manutencao_nao_vira_sem_vagas(sigaa, monkeypatch):
    chamada = {"n": 0}
    original = sigaa.__class__.__call__

    def com_manutencao(self, request):
        resp = original(self, request)
        if request.method == "POST" and "form%3Abuscar" in request.content.decode():
            chamada["n"] += 1
            if chamada["n"] <= 2:
                return httpx.Response(200, text="<html><h1>Sistema em manutenção</h1><p>Volte mais tarde.</p></html>")
        return resp

    monkeypatch.setattr(sigaa.__class__, "__call__", com_manutencao)
    sigaa.vagas = 0
    motor = novo_motor(modo="monitoramento")
    rodar_ate(motor, lambda m: m.snapshot()["contadores"].get("buscas", 0) >= 3)
    snap = motor.snapshot()
    assert snap["contadores"]["manutencao"] == 2
    assert snap["telemetria"]["erros"]["sobrecarga"]["ultimo_detalhe"] == "página de manutenção do SIGAA"
    assert motor.alertas._manutencao_ts is not None


def test_texto_parecido_na_pagina_normal_nao_e_manutencao(sigaa, monkeypatch):
    monkeypatch.setattr("tests.test_engine_fluxo.pagina_resultado",
                        lambda v: pagina_resultado(v).replace("</table>", "</table><p>Sistema em manutenção amanhã</p>"))
    sigaa.vagas = 0
    motor = novo_motor(modo="monitoramento")
    rodar_ate(motor, lambda m: m.snapshot()["contadores"].get("buscas", 0) >= 3)
    assert motor.snapshot()["contadores"].get("manutencao", 0) == 0


def test_resumo_periodico_e_final(sigaa):
    enviados = []
    sigaa.vagas = 0
    motor = novo_motor(modo="monitoramento", resumo_intervalo_horas=0.0001,
                       on_evento=lambda tipo, dados: enviados.append((tipo, dados)))
    motor.intervalo_supervisor = 0.1
    motor.inicio_ts = None
    rodar_ate(motor, lambda m: any(t == "resumo_periodico" for t, _ in enviados), timeout=20)
    texto = next(d["texto"] for t, d in enviados if t == "resumo_periodico")
    assert texto.startswith("📋 Resumo periódico") and "buscas" in texto and "✅ Tudo ok" in texto
    snap = {"inicio": time.time() - 7200, "fim": time.time(), "telemetria": {"requisicoes": 10, "vagas_vistas": 1,
            "erros": {}, "latencia": {}}, "contadores": {}, "alvos": [], "alertas": {"ativos": [{"titulo": "SIGAA sem responder"}]}}
    assert "Execução encerrada (2.0 h): ⚠️ Atenção: SIGAA sem responder" in texto_resumo_periodico(snap, final=True)


# ── 079 / 089: assistente e recomendações ─────────────────────────────────

def test_assistente_login_recusado_e_credenciais():
    ultima = {"motivo_fim": "login_recusado", "erros": {"login": 1}, "totais": {"requisicoes": 0}, "inicio": "2026-09-24 10:00:00"}
    r = diagnosticar("login", carregar_settings(), [Disciplina("FGA0211", "01", 673)], CRED, ultima=ultima)
    assert r["achados"][0]["certeza"] == "certa" and "recusou o login" in r["achados"][0]["causa"]
    vazias = diagnosticar("login", carregar_settings(), [], CredenciaisSigaa())
    assert "não estão preenchidas" in vazias["achados"][0]["causa"]
    with pytest.raises(ValueError):
        diagnosticar("inexistente", carregar_settings(), [])


def test_assistente_confirmacao_aponta_a_etapa_que_falhou():
    tentativa = {"id": "ab12", "chave": "FGA0211-01", "resultado": "FALHA", "total_ms": 900,
                 "etapas": [{"etapa": "selecao_enviada", "ms": 300}]}
    s = {**carregar_settings(), "modo": "matricula", "dry_run": False}
    r = diagnosticar("confirmacao", s, [], CRED, ultima={"tentativas": [tentativa], "erros": {}, "totais": {}})
    assert any("tela de confirmação não veio" in a["causa"] for a in r["achados"])
    mon = diagnosticar("confirmacao", carregar_settings(), [], CRED)
    assert any("SOMENTE MONITORAMENTO" in a["causa"] for a in mon["achados"])


def test_recomendacoes_e_aplicacao_validada():
    s = carregar_settings()
    ultima = {"erros": {"timeout": 300}, "totais": {"requisicoes": 1000}, "latencia_ms": {"media": 100}}
    recs = {r["id"]: r for r in recomendar_configuracao(s, ultima=ultima)}
    assert recs["timeout"]["ajuste"] == {"timeout_req": 15}
    assert "workers_sem_ganho" in recs and recs["workers_sem_ganho"]["ajuste"]["num_workers"] < s["num_workers"]
    assert recomendar_configuracao(s, ultima={"erros": {"timeout": 50}, "totais": {"requisicoes": 60}}) == []
    copia = dict(s)
    assert aplicar_recomendacao(copia, recs["timeout"]) == [] and copia["timeout_req"] == 15
    ruim = dict(s)
    assert aplicar_recomendacao(ruim, {"ajuste": {"num_workers": 0}}) and ruim["num_workers"] == s["num_workers"]


# ── API Web da Fase 5 ─────────────────────────────────────────────────────

from tests.test_web_api import H, aceitar, web  # noqa: E402,F401 (fixture reaproveitada)


def test_api_web_fase5(web, raiz_temporaria):
    _, _, c, _ = web
    assert c.get("/api/assistente", headers=H).status_code == 403  # aviso legal primeiro
    aceitar(c)
    a = c.get("/api/assistente", headers=H).json()
    assert {s["id"] for s in a["sintomas"]} == {"login", "turma", "vagas", "erros", "confirmacao", "parou"}
    r = c.post("/api/assistente/diagnosticar", headers=H, json={"sintoma": "login"}).json()
    assert "não estão preenchidas" in r["achados"][0]["causa"]
    assert c.post("/api/assistente/diagnosticar", headers=H, json={"sintoma": "x"}).status_code == 400
    assert c.post("/api/assistente/aplicar", headers=H, json={"id": "timeout"}).status_code == 409
    seg = c.get("/api/diagnostico/seguranca", headers=H).json()["alertas"]
    assert [x["id"] for x in seg] == ["carga_alta"]
    assert all(x["id"] != "carga_alta" for x in c.get("/api/estado", headers=H).json()["alertas_seguranca"])
    # URLs: fora da UnB nunca é acessada (o teste nem tem rede para isso).
    t = c.post("/api/avancado/testar-urls", headers=H, json={"urls": {"x": "https://golpe.exemplo/login"}}).json()
    assert t["resultados"][0]["ok"] is False and "Não testado" in t["resultados"][0]["texto"]
    # Páginas capturadas: lista, leitura mascarada e bloqueio de caminhos.
    os.makedirs(raiz_temporaria / "logs", exist_ok=True)
    nome = f"debug_W1_selecao_falha_FGA0211_{int(time.time())}.html"
    (raiz_temporaria / "logs" / nome).write_text(PAGINA_PESSOAL, encoding="utf-8")
    assert c.get("/api/suporte/dumps", headers=H).json()["dumps"][0]["nome"] == nome
    lido = c.get(f"/api/suporte/dumps/{nome}", headers=H).json()
    assert "html" not in lido and "JOAO DA SILVA" not in lido["texto"] and "Período letivo" in lido["texto"]
    assert c.get("/api/suporte/dumps/debug_nao_existe.html", headers=H).status_code == 404
    assert c.get("/api/suporte/dumps/..%2Fsettings.json", headers=H).status_code == 404
    previa = c.get("/api/suporte/pacote/previa", headers=H).json()["arquivos"]
    assert previa[0]["nome"] == "LEIA-ME.txt"
    z = c.get("/api/suporte/pacote", headers=H)
    assert z.status_code == 200 and z.content[:2] == b"PK" and "attachment" in z.headers["content-disposition"]
    assert c.get("/api/linha-do-tempo", headers=H).json()["itens"] == []
    # Alertas nas Configurações Avançadas: salvos e validados.
    av = c.get("/api/avancado", headers=H).json()
    corpo = {**av, "urls": av["urls"], "alertas": {**av["alertas"], "taxa_erro_pct": 2}}
    assert c.post("/api/avancado", headers=H, json=corpo).status_code == 400
    corpo["alertas"]["taxa_erro_pct"] = 40
    assert c.post("/api/avancado", headers=H, json=corpo).status_code == 200
    assert carregar_settings()["alertas"]["taxa_erro_pct"] == 40
    n = c.get("/api/notificacoes", headers=H).json()
    assert "alerta_limiar" in n["rotulos_eventos"] and n["resumo_intervalo_horas"] == 6
