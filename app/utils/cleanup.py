"""
Limpeza automática — evita que a pasta do projeto cresça indefinidamente.

A v4.0 original salvava um debug_W{id}_{nome}_{timestamp}.html a cada falha
de parsing e nunca apagava nenhum. Esse era o único ponto de crescimento sem
limite do projeto (logs/JSON já rotacionam via RotatingFileHandler). Este
módulo cobre a peça que faltava: dumps de debug e temporários velhos.
"""
from __future__ import annotations

import glob
import os
import time
from typing import List

from app.utils.paths import raiz_projeto


def listar_debug_dumps() -> List[str]:
    padrao = os.path.join(raiz_projeto(), "logs", "debug_*.html")
    return sorted(glob.glob(padrao), key=os.path.getmtime, reverse=True)


def limpar_debug_dumps(manter: int = 20, dias_max: int = 7) -> int:
    """Mantém só os `manter` dumps mais recentes E remove qualquer um com mais de `dias_max` dias."""
    arquivos = listar_debug_dumps()
    agora = time.time()
    removidos = 0

    for caminho in arquivos[manter:]:
        try:
            os.remove(caminho)
            removidos += 1
        except OSError:
            pass

    for caminho in arquivos[:manter]:
        try:
            if agora - os.path.getmtime(caminho) > dias_max * 86400:
                os.remove(caminho)
                removidos += 1
        except OSError:
            pass

    return removidos


def tamanho_pasta_mb(pasta: str) -> float:
    total = 0
    for raiz, _dirs, arquivos in os.walk(pasta):
        for nome in arquivos:
            try:
                total += os.path.getsize(os.path.join(raiz, nome))
            except OSError:
                pass
    return total / (1024 * 1024)


def resumo_espaco_em_disco() -> dict:
    base = raiz_projeto()
    return {
        "logs_mb": round(tamanho_pasta_mb(os.path.join(base, "logs")), 2),
        "data_mb": round(tamanho_pasta_mb(os.path.join(base, "data")), 2),
        "config_mb": round(tamanho_pasta_mb(os.path.join(base, "config")), 2),
    }
