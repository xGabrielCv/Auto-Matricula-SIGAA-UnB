"""
Notificação via Telegram — recuperado de legacy/monitores_selenium/Monitorador_Com_Telegram.py.

A chamada HTTP é exatamente a mesma (POST JSON em .../bot{token}/sendMessage),
só trocamos `requests` (síncrono) por `httpx.AsyncClient` (assíncrono) para
não bloquear o loop de eventos do motor de matrícula.
"""
from __future__ import annotations

import httpx

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


async def enviar_telegram(token: str, chat_id: str, mensagem: str, timeout: float = 15.0) -> None:
    """Levanta exceção em caso de falha — quem chama decide como tratar (ver manager.py,
    que sempre engole a exceção para não derrubar o monitor)."""
    if not token or not chat_id:
        raise ValueError("Token ou chat_id do Telegram não configurados.")
    url = TELEGRAM_API.format(token=token)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json={"chat_id": chat_id, "text": mensagem, "parse_mode": "Markdown"})
        resp.raise_for_status()


async def testar_telegram(token: str, chat_id: str) -> str:
    """Usado pelo botão 'Enviar notificação de teste' da GUI/terminal."""
    await enviar_telegram(token, chat_id, "✅ SIGAA Sniper: notificação de teste do Telegram funcionando!")
    return "Mensagem de teste enviada com sucesso."
