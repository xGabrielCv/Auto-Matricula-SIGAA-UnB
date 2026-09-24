"""Histórico local de execuções (Fase 3): SQLite, consultas, mapa de calor, comparação e exportação."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime

from app.core import historico
from app.core.relatorios import salvar_relatorio
from tests.test_engine_fluxo import montar, rodar, sigaa  # noqa: F401  (fixture)


def _resumo(eid: str, inicio: datetime, duracao: int = 600, vagas: int = 0, erros: int = 0, alvos=("FGA0211-01",),
            workers: int = 8) -> dict:
    fim = datetime.fromtimestamp(inicio.timestamp() + duracao)
    return {
        "execucao_id": eid, "versao": "t", "modo": "monitoramento", "dry_run": True,
        "inicio": inicio.strftime("%Y-%m-%d %H:%M:%S"), "fim": fim.strftime("%Y-%m-%d %H:%M:%S"),
        "duracao_seg": duracao, "motivo_fim": "interrompida",
        "configuracao": {"num_workers": workers, "intervalo_busca": 0.8, "timeout_req": 10, "agendar_inicio": None},
        "alvos": [{"chave": a, "codigo": a[:7], "turma": a[-2:], "departamento": 673, "estado": "sem_vagas",
                   "estado_rotulo": "Sem vagas", "vagas": 0, "buscas": 10, "vagas_vistas": vagas, "tentativas": 0} for a in alvos],
        "totais": {"requisicoes": 1200, "vagas_vistas": vagas, "tentativas": 0, "matriculadas": 0, "simuladas": 0,
                   "bloqueadas": 0, "erros": erros},
        "erros": {}, "latencia_ms": {"media": 200, "recente": 210, "min": 90, "max": 900}, "contadores": {},
    }


def test_execucao_real_entra_no_historico(sigaa, raiz_temporaria):  # noqa: F811
    motor, _ = montar(dry_run=True)
    rodar(motor)
    execucoes = historico.listar_execucoes()
    assert [e["id"] for e in execucoes] == [motor.execucao_id]
    e = execucoes[0]
    assert e["simuladas"] == 1 and e["disciplinas"] == ["FGA0211-01"] and e["dry_run"] is True
    detalhe = historico.obter_execucao(motor.execucao_id)
    assert detalhe["resumo"]["alvos"][0]["estado"] == "simulada"
    assert detalhe["vagas_series"]["FGA0211-01"][-1][1] == 2
    with open(historico.caminho_banco(), "rb") as f:
        assert b"s3nh@" not in f.read()  # nunca guarda credenciais


def test_historico_desativado_nao_grava(sigaa, raiz_temporaria):  # noqa: F811
    motor, _ = montar(dry_run=True)
    motor.cfg_historico["ativo"] = False
    rodar(motor)
    assert historico.listar_execucoes() == []


def test_mapa_de_calor_conta_aberturas_de_vaga(raiz_temporaria):
    segunda_9h = datetime(2026, 9, 21, 9, 0, 0)  # segunda-feira
    t = segunda_9h.timestamp()
    historico.registrar_execucao(_resumo("a", segunda_9h, vagas=2), {
        # abre às 9h05, fecha, reabre às 10h10; a série de MAT0025 abre às 9h30
        "vagas_series": {"FGA0211-01": [[t + 60, 0], [t + 300, 2], [t + 360, 3], [t + 400, 0], [t + 4200, 1]],
                         "MAT0025-02": [[t + 1800, 1]]},
        "pontos": [{"t": t + i, "req": 5, "p50": 100 + i, "p95": 300, "erros": {"timeout": 1} if i == 3 else {}} for i in range(120)],
    })
    mapa = historico.mapa_aberturas_de_vaga()
    assert mapa["total"] == 3 and mapa["matriz"][0][9] == 2 and mapa["matriz"][0][10] == 1
    assert historico.mapa_aberturas_de_vaga(disciplina="MAT0025-02")["total"] == 1
    detalhe = historico.obter_execucao("a")
    assert len(detalhe["series_minuto"]) == 2 and detalhe["series_minuto"][0]["req"] == 300
    assert detalhe["series_minuto"][0]["erros"] == {"timeout": 1}


def test_por_dia_filtros_e_comparacao(raiz_temporaria):
    hoje = datetime.now().replace(microsecond=0)
    antigo = datetime.fromtimestamp(time.time() - 40 * 86400).replace(microsecond=0)
    historico.registrar_execucao(_resumo("recente", hoje, duracao=3600, vagas=4, erros=10, workers=20))
    historico.registrar_execucao(_resumo("velha", antigo, duracao=1800, vagas=1, alvos=("MAT0025-02",), workers=4))
    assert {e["id"] for e in historico.listar_execucoes()} == {"recente", "velha"}
    assert [e["id"] for e in historico.listar_execucoes(dias=30)] == ["recente"]
    assert [e["id"] for e in historico.listar_execucoes(disciplina="MAT0025-02")] == ["velha"]
    dias = historico.resumo_por_dia()
    assert len(dias) == 2 and dias[-1]["horas"] == 1.0 and dias[-1]["vagas_vistas"] == 4
    comp = historico.comparar(["recente", "velha", "nao-existe"])
    assert [c["id"] for c in comp] == ["recente", "velha"]
    assert comp[0]["indicadores"]["num_workers"] == 20 and comp[1]["indicadores"]["taxa_erro"] == 0


def test_exportacao_csv_segura_e_json(raiz_temporaria):
    r = _resumo("x1", datetime(2026, 9, 21, 9, 0, 0), alvos=("=CMD()",))  # disciplina maliciosa num arquivo importado
    historico.registrar_execucao(r)
    csv_texto = historico.exportar_execucoes("csv")
    assert csv_texto.startswith("﻿") and "id;inicio_txt" in csv_texto
    assert "'=CMD()" in csv_texto  # fórmula neutralizada para Excel/Sheets
    dados = json.loads(historico.exportar_execucoes("json"))
    assert dados[0]["id"] == "x1"
    assert "execucao_id;disciplina;horario;vagas" in historico.exportar_leituras_vagas("csv")


def test_retencao_apagar_e_importar_relatorios(raiz_temporaria):
    antigo = datetime.fromtimestamp(time.time() - 400 * 86400).replace(microsecond=0)
    historico.registrar_execucao(_resumo("muito-antiga", antigo))
    historico.registrar_execucao(_resumo("nova", datetime.now().replace(microsecond=0)))
    assert historico.aplicar_retencao(180) == 1
    assert [e["id"] for e in historico.listar_execucoes()] == ["nova"]
    assert historico.aplicar_retencao(0) == 0  # 0 = guardar sempre
    historico.apagar_tudo()
    assert not os.path.exists(historico.caminho_banco())  # conexões fechadas: o arquivo pode ser apagado
    salvar_relatorio(_resumo("do-relatorio", datetime.now().replace(microsecond=0)))
    assert historico.importar_relatorios_antigos() == 0  # apagou nesta sessão: não traz de volta
    assert historico.importar_relatorios_antigos(forcar=True) == 1
    assert historico.importar_relatorios_antigos(forcar=True) == 0  # já está no banco
    assert historico.listar_execucoes()[0]["id"] == "do-relatorio"
