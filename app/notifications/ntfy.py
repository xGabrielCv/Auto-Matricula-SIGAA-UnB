"""
Notificação via ntfy.sh — recuperado de legacy/monitores_selenium/Monitorador_Com_Alarme_E_Notifi.py
e legacy/predecessores_http/BOT-SIGAA-HTTP-CAROL.py.

O tópico funciona como um "segredo" simples: quem souber o nome do tópico
recebe as notificações. Por isso ele é tratado como dado sensível e não é
salvo em disco por padrão (ver app/core/credentials.py).
"""
from __future__ import annotations

import httpx


async def enviar_ntfy(topic: str, titulo: str, mensagem: str, servidor: str = "https://ntfy.sh", timeout: float = 15.0) -> None:
    if not topic:
        raise ValueError("Tópico do ntfy não configurado.")
    url = f"{servidor.rstrip('/')}/{topic}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, data=mensagem.encode("utf-8"), headers={"Title": titulo})
        resp.raise_for_status()


async def testar_ntfy(topic: str, servidor: str = "https://ntfy.sh") -> str:
    await enviar_ntfy(topic, "SIGAA Sniper", "✅ Notificação de teste do ntfy funcionando!", servidor)
    return f"Notificação de teste enviada para o tópico '{topic}'."
