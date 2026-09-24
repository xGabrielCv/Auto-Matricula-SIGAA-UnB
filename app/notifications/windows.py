"""
Notificação nativa do Windows — balão na área de notificações (Fase 6, 080).

Sem biblioteca: um PowerShell curto usa a API de notificações do Windows
(WinRT) para mostrar o aviso. Título e mensagem vão por VARIÁVEIS DE AMBIENTE
e são escapados como XML dentro do próprio PowerShell — nunca são colados no
texto do comando (nada do texto da mensagem pode virar código).

Limite conhecido: sem um atalho registrado do programa, clicar no balão não
abre a interface (fica registrado como sugestão futura).
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys

# ID de aplicativo do próprio PowerShell: já registrado em todo Windows 10/11,
# é o que permite mostrar o balão sem instalar nada.
_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

_SCRIPT = (
    "$ErrorActionPreference='Stop';"
    "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;"
    "[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]|Out-Null;"
    "$t=[Security.SecurityElement]::Escape($env:SNIPER_TITULO);"
    "$m=[Security.SecurityElement]::Escape($env:SNIPER_MENSAGEM);"
    "$x=New-Object Windows.Data.Xml.Dom.XmlDocument;"
    "$x.LoadXml(\"<toast><visual><binding template='ToastGeneric'><text>$t</text><text>$m</text></binding></visual></toast>\");"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:SNIPER_APPID).Show("
    "[Windows.UI.Notifications.ToastNotification]::new($x))"
)


def disponivel() -> bool:
    return sys.platform == "win32"


async def enviar_windows(titulo: str, mensagem: str, timeout: float = 15.0) -> None:
    if not disponivel():
        raise RuntimeError("Notificação do Windows só funciona no Windows.")
    env = {**os.environ, "SNIPER_TITULO": titulo[:120], "SNIPER_MENSAGEM": mensagem[:400], "SNIPER_APPID": _APP_ID}
    processo = await asyncio.create_subprocess_exec(
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _SCRIPT,
        env=env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        _saida, erro = await asyncio.wait_for(processo.communicate(), timeout)
    except asyncio.TimeoutError:
        processo.kill()
        raise RuntimeError("O Windows não respondeu a tempo ao pedido de notificação.")
    if processo.returncode != 0:
        detalhe = (erro or b"").decode("utf-8", errors="replace").strip().splitlines()
        raise RuntimeError(f"O Windows recusou a notificação ({detalhe[-1][:160] if detalhe else processo.returncode}).")


async def testar_windows() -> str:
    await enviar_windows("SIGAA Sniper", "✅ Notificação de teste do Windows funcionando!")
    return "Notificação de teste mostrada."
