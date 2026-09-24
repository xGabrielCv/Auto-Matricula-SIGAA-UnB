"""
Webhook genérico — Discord, Slack ou JSON (Fase 6 — sugestão 081).

A URL do webhook funciona como uma senha (quem a tiver posta no seu canal),
por isso é tratada como segredo: fica só em memória ou no cofre (cofre.py).
Mesmas regras dos outros canais: levanta exceção na falha e o gerenciador
(manager.py) engole, para nunca derrubar o monitoramento.
"""
from __future__ import annotations

import httpx

FORMATOS = {"discord": "Discord", "slack": "Slack", "json": "JSON genérico"}


def montar_payload(formato: str, titulo: str, mensagem: str) -> dict:
    if formato == "discord":
        return {"content": f"**{titulo}**\n{mensagem}"[:1900], "username": "SIGAA Sniper"}
    if formato == "slack":
        return {"text": f"*{titulo}*\n{mensagem}"}
    return {"app": "SIGAA Sniper", "titulo": titulo, "mensagem": mensagem}


async def enviar_webhook(url: str, formato: str, titulo: str, mensagem: str, timeout: float = 15.0) -> None:
    if not url:
        raise ValueError("URL do webhook não configurada.")
    if not url.startswith("https://"):
        raise ValueError("A URL do webhook precisa começar com https://.")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=montar_payload(formato, titulo, mensagem))
        resp.raise_for_status()


async def testar_webhook(url: str, formato: str) -> str:
    await enviar_webhook(url, formato, "SIGAA Sniper", "✅ Notificação de teste do webhook funcionando!")
    return "Mensagem de teste enviada com sucesso."
