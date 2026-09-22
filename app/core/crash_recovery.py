"""
Detecção de encerramento anormal — seção 54 do pedido de continuação.

Escreve um marcador quando o motor começa a rodar e apaga quando termina de
forma controlada (mesmo por erro tratado). Se o marcador ainda existir na
próxima vez que o programa checar, é porque a execução anterior foi
interrompida abruptamente (queda de energia, processo morto, crash).

IMPORTANTE: a presença do marcador NUNCA é interpretada como "a matrícula
aconteceu" — só como "não sabemos como aquela execução terminou". O usuário
é quem decide checar manualmente o SIGAA se precisar ter certeza.
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

from app.utils.paths import caminho as caminho_projeto

ARQUIVO_MARCADOR = "data/.execucao_em_andamento.json"


def marcar_execucao_iniciada(modo: str, execucao_id: str) -> None:
    caminho = caminho_projeto(*ARQUIVO_MARCADOR.split("/"))
    dados = {"inicio": time.strftime("%Y-%m-%d %H:%M:%S"), "pid": os.getpid(), "modo": modo, "execucao_id": execucao_id}
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False)
    except OSError:
        pass  # best-effort — nunca deve impedir o motor de rodar


def marcar_execucao_encerrada() -> None:
    caminho = caminho_projeto(*ARQUIVO_MARCADOR.split("/"))
    try:
        if os.path.exists(caminho):
            os.remove(caminho)
    except OSError:
        pass


def verificar_encerramento_anterior() -> Optional[dict]:
    """Devolve os dados do marcador se a última execução não terminou de forma
    controlada, ou None se terminou normalmente (ou nunca rodou)."""
    caminho = caminho_projeto(*ARQUIVO_MARCADOR.split("/"))
    if not os.path.exists(caminho):
        return None
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"inicio": "desconhecido", "pid": None, "modo": "desconhecido", "execucao_id": "desconhecido"}
