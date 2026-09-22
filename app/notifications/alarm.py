"""
Alarme sonoro local — recuperado de legacy/monitores_selenium/Monitorador_Com_Alarme.py.

A v4.0 e os legados de monitoramento usam `winsound` (só Windows). Como este
projeto roda em Windows (o ambiente de desenvolvimento e o público-alvo),
mantemos winsound como mecanismo principal, mas cai para um beep de terminal
(`\\a`) em qualquer outro sistema em vez de falhar — o alarme é sempre
best-effort e nunca pode derrubar o monitor.

Diferença importante em relação ao legado: aqui o alarme roda numa thread
separada (via asyncio.to_thread) para não bloquear o loop de eventos.
"""
from __future__ import annotations

import asyncio
import sys


def _tocar_sirene_bloqueante(repeticoes: int, duracao_seg: int) -> None:
    if sys.platform == "win32":
        import winsound
        import time
        t0 = time.time()
        while time.time() - t0 < duracao_seg:
            for _ in range(repeticoes):
                winsound.Beep(1500, 200)
                winsound.Beep(800, 200)
    else:
        for _ in range(repeticoes):
            sys.stdout.write("\a")
            sys.stdout.flush()


async def tocar_alarme(repeticoes: int = 3, duracao_seg: int = 20) -> None:
    """Não-bloqueante: delega o beep síncrono para uma thread do executor padrão."""
    await asyncio.to_thread(_tocar_sirene_bloqueante, repeticoes, duracao_seg)


async def testar_alarme(repeticoes: int = 2, duracao_seg: int = 3) -> str:
    await tocar_alarme(repeticoes=repeticoes, duracao_seg=duracao_seg)
    return "Alarme de teste tocado."
