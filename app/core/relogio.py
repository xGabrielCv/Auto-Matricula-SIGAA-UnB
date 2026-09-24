"""
Diferença entre o relógio deste computador e o do SIGAA (sugestão 038).

Promovido do experimento "Sincronização de relógio" (app/experimental/
ntp_scheduler.py, que agora reutiliza esta função): lê o cabeçalho HTTP
`Date` de uma página pública do SIGAA e compara com a hora local, descontando
metade do tempo de ida e volta. Com a opção ligada, o agendamento de início
usa o horário do SIGAA em vez do relógio do PC.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, Optional

import httpx

URL_PADRAO = "https://sigaa.unb.br/sigaa/public/"


async def medir_offset_relogio(url: str = URL_PADRAO, fabrica_cliente: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
    """offset_segundos > 0: o SIGAA está À FRENTE deste computador."""
    fabrica = fabrica_cliente or httpx.AsyncClient
    antes = datetime.now(timezone.utc)
    async with fabrica(timeout=10) as client:
        resp = await client.get(url)
    depois = datetime.now(timezone.utc)

    date_header = resp.headers.get("date")
    if not date_header:
        raise RuntimeError("O servidor não enviou o header 'Date' na resposta — não é possível medir o offset.")
    hora_servidor = parsedate_to_datetime(date_header)
    if hora_servidor.tzinfo is None:
        hora_servidor = hora_servidor.replace(tzinfo=timezone.utc)

    latencia = (depois - antes).total_seconds()
    meio = antes + (depois - antes) / 2
    return {
        "hora_servidor": hora_servidor.isoformat(),
        "hora_local": depois.isoformat(),
        "offset_segundos": round((hora_servidor - meio).total_seconds(), 2),
        "latencia_ida_volta_segundos": round(latencia, 3),
    }


def descrever_offset(offset_segundos: float) -> str:
    if abs(offset_segundos) < 0.5:
        return "o relógio deste computador está alinhado com o do SIGAA (diferença menor que 0,5 s)"
    lado = "atrasado" if offset_segundos > 0 else "adiantado"
    return f"o relógio deste computador está {abs(offset_segundos):.1f} s {lado} em relação ao SIGAA"
