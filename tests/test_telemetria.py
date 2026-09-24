"""
Telemetria do motor (Fase 2): eventos estruturados no log (053), estado por
disciplina (019) e por worker (055), contadores (056), fase (086), séries e
histograma (026/030/031), relatório de encerramento (048).
"""
from __future__ import annotations

import json
import logging

from app.core import engine
from app.core.logging_setup import JsonFormatter
from app.core.relatorios import carregar_relatorio, listar_relatorios, texto_relatorio
from app.core.telemetria import Telemetria
from tests.test_engine_fluxo import montar, rodar, rodar_ate, sigaa  # noqa: F401  (fixture)


# ── Unidade ──────────────────────────────────────────────────────────────

def test_histograma_percentis_e_amostragem():
    t = Telemetria()
    for ms in (50, 120, 300, 700, 1500, 5000):
        t.registrar_requisicao(ms)
    t.registrar_requisicao(None)  # timeout: conta como requisição, sem latência
    t.registrar_erro("timeout", "W0")
    t.amostrar(agora=1000.0)
    s = t.snapshot()
    assert s["requisicoes"] == 7 and s["histograma"]["contagens"] == [1, 1, 1, 1, 1, 1]
    ponto = s["pontos"][-1]
    assert ponto["req"] == 7 and ponto["erros"] == {"timeout": 1}
    assert 300 < ponto["p50"] < 1500 and ponto["p95"] > ponto["p50"]
    assert s["latencia"]["min"] == 50 and s["latencia"]["max"] == 5000
    t.amostrar(agora=1001.0)
    assert s["pontos"][-1]["req"] == 7 and t.snapshot()["pontos"][-1]["req"] == 0  # segundo novo começa zerado
    assert s["erros"]["timeout"]["total"] == 1 and s["erros"]["timeout"]["ultimo_detalhe"] == "W0"


def test_serie_de_vagas_so_guarda_mudancas():
    t = Telemetria()
    for v in (0, 0, 0, 2, 2, 0):
        t.registrar_vagas("FGA0211-01", v)
    serie = t.snapshot()["vagas_series"]["FGA0211-01"]
    assert [v for _t, v in serie] == [0, 2, 0]
    assert t.snapshot()["vagas_vistas"] == 2 and t.snapshot()["ultima_vaga"]["vagas"] == 2


def test_formatador_so_grava_campos_permitidos():
    registro = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    registro.worker_id = "W0"
    registro.campos = {"evento": "busca", "codigo": "FGA0211", "senha": "s3nh@", "cpf": "123", "latencia_ms": 80}
    linha = json.loads(JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S").format(registro))
    assert linha["evento"] == "busca" and linha["latencia_ms"] == 80
    assert "senha" not in linha and "cpf" not in linha


# ── Motor real contra o SIGAA simulado ──────────────────────────────────

class _ArquivoJson(logging.Handler):
    def __init__(self):
        super().__init__()
        self.setFormatter(JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S"))
        self.linhas = []

    def emit(self, record):
        self.linhas.append(json.loads(self.format(record)))


def test_execucao_dry_run_registra_estado_e_resumo(sigaa, raiz_temporaria):  # noqa: F811
    motor, _ = montar(dry_run=True)
    arquivo = _ArquivoJson()
    motor.log.addHandler(arquivo)
    motor.log.setLevel(logging.INFO)
    try:
        rodar(motor)
    finally:
        motor.log.removeHandler(arquivo)

    snap = motor.snapshot()
    alvo = snap["alvos"][0]
    assert alvo["estado"] == "simulada" and alvo["vagas_vistas"] >= 1 and alvo["tentativas"] == 1
    assert snap["fase"] == "encerrado" and snap["motivo_fim"] == "concluida"
    assert snap["workers"][0]["estado"] == "encerrado"
    assert snap["contadores"]["buscas"] >= 1 and snap["contadores"]["tentativas"] == 1
    assert snap["telemetria"]["requisicoes"] >= 1 and snap["telemetria"]["pontos"]

    eventos = [l.get("evento") for l in arquivo.linhas]
    for esperado in ("sessao_iniciada", "login_ok", "busca", "vaga_detectada", "tentativa_iniciada",
                     "matricula_sucesso", "execucao_resumo"):
        assert esperado in eventos, esperado
    vaga = next(l for l in arquivo.linhas if l.get("evento") == "vaga_detectada")
    assert vaga["codigo"] == "FGA0211" and vaga["turma"] == "01" and vaga["vagas"] == 2 and "latencia_ms" in vaga
    assert all(l.get("execucao_id") == motor.execucao_id for l in arquivo.linhas if "evento" in l)
    texto_log = json.dumps(arquivo.linhas, ensure_ascii=False)
    assert "s3nh@" not in texto_log and "123.456.789-00" not in texto_log and "01/02/2003" not in texto_log

    resumo = carregar_relatorio(motor.execucao_id)
    assert resumo and resumo["totais"]["simuladas"] == 1 and resumo["motivo_fim"] == "concluida"
    assert resumo["alvos"][0]["estado"] == "simulada"
    assert listar_relatorios()[0]["execucao_id"] == motor.execucao_id
    assert "FGA0211-01" in texto_relatorio(resumo) and "DRY RUN" in texto_relatorio(resumo)
    assert "s3nh@" not in json.dumps(resumo)


def test_monitoramento_mantem_estado_vaga_e_para_por_usuario(sigaa, raiz_temporaria):  # noqa: F811
    motor, _ = montar(modo="monitoramento", parar_em="vaga_detectada")
    rodar(motor)
    alvo = motor.snapshot()["alvos"][0]
    assert alvo["estado"] == "vaga" and alvo["vagas"] == 2 and alvo["tentativas"] == 0
    assert motor.resumo["motivo_fim"] == "interrompida"


def test_bloqueio_e_estado_final_nao_e_sobrescrito(sigaa, raiz_temporaria):  # noqa: F811
    sigaa.resposta_final = "Erro: pré-requisito não cumprido"
    motor, _ = montar(dry_run=False)
    rodar(motor)
    motor.atualizar_alvo("FGA0211-01", "buscando")  # nada muda depois de um estado final
    assert motor.snapshot()["alvos"][0]["estado"] == "bloqueada"
    assert motor.resumo["totais"]["bloqueadas"] == 1


def test_departamento_indisponivel_aparece_no_estado(sigaa, monkeypatch, raiz_temporaria):  # noqa: F811
    monkeypatch.setattr(engine.SigaaWorker, "ESPERA_FALHA_BASE_SEG", 5)
    sigaa.portal_sem_menu = True
    motor, _ = montar(dry_run=True)
    rodar_ate(motor, lambda m: m.telemetria.erros["departamento"] >= 1)
    snap = motor.snapshot()
    assert snap["alvos"][0]["estado"] == "departamento_indisponivel"
    assert snap["telemetria"]["erros"]["departamento"]["total"] >= 1
    assert snap["contadores"]["falhas_departamento"] >= 1


# ── 053: consumidores usam o campo `evento` (texto só como fallback) ─────

def test_painel_e_traducao_nao_dependem_mais_do_texto():
    from app.dashboard.log_humano import traduzir
    from app.dashboard.metrics import ColetorMetricas, classificar
    # Mesmo que a frase do motor mude no futuro, o evento estruturado continua valendo.
    novo = {"timestamp": "2026-01-01 10:00:01", "level": "WARNING", "worker": "W0", "message": "frase reescrita",
            "evento": "vaga_detectada", "codigo": "FGA0211", "turma": "01", "vagas": 3, "latencia_ms": 90}
    assert classificar(novo) == "vaga"
    ev = traduzir(novo)
    assert ev.titulo == "Vaga encontrada em FGA0211-01!" and "3 vaga" in ev.corpo and ev.categoria == "SUCESSO"
    coletor = ColetorMetricas()
    coletor.processar_linha(json.dumps({**novo, "evento": "sessao_iniciada", "message": "x"}), ao_vivo=False)
    coletor.processar_linha(json.dumps(novo), ao_vivo=False)
    snap = coletor.snapshot()
    assert snap["vagas_encontradas"] == 1 and snap["latencia_max_ms"] == 90
    assert snap["historico_vagas"]["FGA0211-01"][-1][1] == 3
    # Log antigo (sem `evento`) continua sendo entendido pelo texto.
    antigo = {"timestamp": "2026-01-01 10:00:02", "level": "WARNING", "worker": "W1",
              "message": "[W1] 🚨 VAGA DETECTADA (80ms) -> MAT0025-02 (1 vaga(s))!"}
    assert classificar(antigo) == "vaga" and traduzir(antigo).titulo == "Vaga encontrada em MAT0025-02!"
    # Sucesso real x simulado pelo campo dry_run
    base = {"worker": "W0", "message": "x", "evento": "matricula_sucesso", "codigo": "FGA0211", "turma": "01"}
    assert traduzir({**base, "dry_run": False}).titulo.startswith("Matrícula confirmada")
    assert traduzir({**base, "dry_run": True}).titulo.startswith("[TESTE]")


def test_ao_encerrar_nao_sobra_estado_transitorio(sigaa, raiz_temporaria):  # noqa: F811
    """Parada logo após uma busca com falha deixava a disciplina "Buscando" para sempre."""
    sigaa.vagas = 0
    sigaa.falhar_busca_a_cada = 2
    motor, _ = montar(dry_run=True)
    # para logo depois de uma busca que falhou (a disciplina estava "Buscando" nesse instante)
    rodar_ate(motor, lambda m: m.telemetria.erros["sessao"] >= 2)
    assert motor.snapshot()["alvos"][0]["estado"] == "sem_vagas"
    assert motor.resumo["alvos"][0]["estado"] == "sem_vagas"
