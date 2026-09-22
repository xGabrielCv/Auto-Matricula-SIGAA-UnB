"""LogTailer: leitura incremental e convivência com a rotação do log (Windows)."""
from __future__ import annotations

import json
import logging
import os
from logging.handlers import RotatingFileHandler

from app.dashboard.metrics import ColetorMetricas, LogTailer


class _HandlerQueRegistraErros(RotatingFileHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.erros = []

    def handleError(self, record):  # noqa: N802 — nome da API do logging
        import sys
        self.erros.append(sys.exc_info()[1])


def test_leitura_incremental_e_linha_parcial(tmp_path):
    arq = tmp_path / "log.json"
    arq.write_bytes(b'{"a": 1}\n{"b": 2')
    t = LogTailer(str(arq))
    assert t.read_new_lines() == ['{"a": 1}\n']
    with open(arq, "ab") as f:
        f.write(b'}\r\n{"c": 3}\n')
    assert t.read_new_lines() == ['{"b": 2}\n', '{"c": 3}\n']
    assert t.read_new_lines() == []


def test_arquivo_inexistente(tmp_path):
    assert LogTailer(str(tmp_path / "nao_existe.json")).read_new_lines() == []


def test_rotacao_nao_e_bloqueada_pelo_leitor(tmp_path):
    """Regressão: com a aba Dashboard/Logs aberta, a versão anterior mantinha o
    arquivo aberto e, no Windows, a rotação falhava (WinError 32) em TODA linha
    nova depois de atingir o tamanho máximo — o log parava de ser gravado."""
    caminho = str(tmp_path / "audit.json")
    handler = _HandlerQueRegistraErros(caminho, maxBytes=2000, backupCount=2, encoding="utf-8")
    logger = logging.getLogger("teste_rotacao")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    tailer = LogTailer(caminho)
    lidas = []
    for i in range(300):
        logger.info(json.dumps({"i": i, "message": "x" * 40}))
        if i % 5 == 0:
            lidas.extend(tailer.read_new_lines())
    lidas.extend(tailer.read_new_lines())
    handler.close()

    assert handler.erros == [], f"rotação falhou: {handler.erros[:1]}"
    assert os.path.exists(caminho + ".1")
    assert len(lidas) > 0


def test_coletor_marca_sem_dados_e_conta_vagas():
    c = ColetorMetricas()
    assert c.snapshot()["latencia_recente_ms"] is None
    for msg in ["SESSAO_INICIADA id=x", "[W0] 🔍 Buscando FGA0211-01...", "[W0] 📉 Sem vagas (120ms).",
                "[W0] 🚨 VAGA DETECTADA (90ms) -> FGA0211-01 (2 vaga(s))!"]:
        c.processar_linha(json.dumps({"timestamp": "2026-01-01 10:00:00", "level": "INFO", "worker": "W0", "message": msg}), ao_vivo=True)
    m = c.snapshot()
    assert m["vagas_encontradas"] == 1
    assert m["total_buscas"] == 1
    assert m["latencia_min_ms"] == 90 and m["latencia_max_ms"] == 120
    assert m["historico_vagas"]["FGA0211-01"][-1][1] == 2
