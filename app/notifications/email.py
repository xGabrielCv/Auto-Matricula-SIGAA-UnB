"""
Notificação por e-mail (SMTP) — Fase 6, sugestão 082.

Usa o `smtplib` da biblioteca padrão numa thread separada (o motor nunca
espera o envio). A senha do e-mail é segredo: só em memória ou no cofre
(cofre.py). Para Gmail/Outlook, normalmente é preciso uma "senha de app".
"""
from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from typing import Dict

SEGURANCAS = {"starttls": "STARTTLS (porta 587)", "ssl": "SSL/TLS (porta 465)"}


def configurado(cfg: Dict, senha: str) -> bool:
    return bool(cfg.get("servidor") and cfg.get("usuario") and cfg.get("destinatario") and senha)


def _enviar(cfg: Dict, senha: str, assunto: str, mensagem: str, timeout: float) -> None:
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = (cfg.get("remetente") or "").strip() or cfg["usuario"]
    msg["To"] = cfg["destinatario"]
    msg.set_content(mensagem)
    contexto = ssl.create_default_context()
    porta = int(cfg.get("porta") or (465 if cfg.get("seguranca") == "ssl" else 587))
    if cfg.get("seguranca") == "ssl":
        with smtplib.SMTP_SSL(cfg["servidor"], porta, timeout=timeout, context=contexto) as smtp:
            smtp.login(cfg["usuario"], senha)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(cfg["servidor"], porta, timeout=timeout) as smtp:
            smtp.starttls(context=contexto)  # nunca envia a senha sem criptografia
            smtp.login(cfg["usuario"], senha)
            smtp.send_message(msg)


async def enviar_email(cfg: Dict, senha: str, assunto: str, mensagem: str, timeout: float = 20.0) -> None:
    if not configurado(cfg, senha):
        raise ValueError("Preencha servidor, usuário, destinatário e senha do e-mail.")
    await asyncio.to_thread(_enviar, cfg, senha, assunto, mensagem, timeout)


async def testar_email(cfg: Dict, senha: str) -> str:
    await enviar_email(cfg, senha, "SIGAA Sniper — teste", "✅ Notificação de teste por e-mail funcionando!")
    return "E-mail de teste enviado."
