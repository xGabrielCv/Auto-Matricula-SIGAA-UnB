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


# Campos estruturados aceitos no log (sugestão 053). Lista FECHADA de
# propósito: qualquer outro nome passado pelo motor é descartado, então um
# descuido futuro nunca grava credenciais no arquivo.
CAMPOS_ESTRUTURADOS = (
    "evento", "execucao_id", "codigo", "turma", "vagas", "latencia_ms", "http_status",
    "dry_run", "motivo", "espera_seg", "departamento",
    # Fase 5: rastreamento de tentativas de matrícula (059).
    "tentativa_id", "etapa", "duracao_ms",
)


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
        campos = getattr(record, "campos", None)
        if isinstance(campos, dict):
            for nome in CAMPOS_ESTRUTURADOS:
                valor = campos.get(nome)
                if isinstance(valor, (str, int, float, bool)) and valor is not None:
                    log_record[nome] = valor
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
    # Com a saída redirecionada para arquivo/pipe numa codificação que não tem
    # emoji (ex: cp1252 no Windows), cada linha com "🔍" gerava um traceback
    # "Logging error". O caractere impossível vira um escape; o log JSON (UTF-8)
    # continua com o texto completo.
    try:
        if (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "") != "utf8":
            sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(nivel_console)
    logger.addHandler(console_handler)

    logger.propagate = False
    return logger


def caminho_log_json(arquivo_json: str = "data/sigaa_sniper_audit.json") -> str:
    return caminho_projeto(*arquivo_json.split("/"))
