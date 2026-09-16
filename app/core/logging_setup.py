"""
Sistema de logs — preserva o formato JSON Lines da v4.0 (um objeto JSON por
linha, consumível por tail) mas com limites configuráveis em vez do valor
fixo de 50MB/2 backups hardcoded na v4.0 original.

Por que manter JSON Lines: é o formato que o dashboard (terminal e GUI) lê
via leitura incremental (tail), então mudar o formato quebraria os dois
consumidores. Só a política de rotação ficou configurável.
"""
from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Dict

from app.utils.paths import caminho as caminho_projeto


class JsonFormatter(logging.Formatter):
    """Formata cada registro de log como uma linha JSON válida (JSON Lines)."""

    def format(self, record: logging.LogRecord) -> str:
        worker_id = getattr(record, "worker_id", "MAIN")
        log_record: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "worker": worker_id,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record, ensure_ascii=False)


def configurar_logging(
    nome_logger: str = "sniper",
    arquivo_json: str = "data/sigaa_sniper_audit.json",
    tamanho_max_mb: int = 20,
    arquivos_mantidos: int = 3,
    nivel_console: int = logging.INFO,
) -> logging.Logger:
    """
    Configura (ou reconfigura) o logger principal. Chamar de novo com limites
    diferentes substitui os handlers antigos — útil quando o usuário muda o
    limite de log nas Configurações Avançadas sem reiniciar o programa.
    """
    logger = logging.getLogger(nome_logger)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    json_formatter = JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S")
    caminho_log = caminho_projeto(*arquivo_json.split("/"))

    file_handler = RotatingFileHandler(
        caminho_log,
        maxBytes=max(1, tamanho_max_mb) * 1024 * 1024,
        backupCount=max(0, arquivos_mantidos),
        encoding="utf-8",
    )
    file_handler.setFormatter(json_formatter)
    logger.addHandler(file_handler)

    console_formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(nivel_console)
    logger.addHandler(console_handler)

    logger.propagate = False
    return logger


def caminho_log_json(arquivo_json: str = "data/sigaa_sniper_audit.json") -> str:
    return caminho_projeto(*arquivo_json.split("/"))
