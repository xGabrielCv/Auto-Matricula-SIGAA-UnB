"""
Criação de atalho do Windows — seção 94.5 do pedido.

Usa o truque clássico de gerar um script VBS temporário que chama
WScript.Shell para criar o .lnk, executado via `cscript` (já vem com
qualquer Windows) — evita adicionar pywin32/pyshortcuts como dependência só
para isso.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from app.utils.paths import raiz_projeto


def suportado() -> bool:
    return sys.platform == "win32"


def criar_atalho_area_trabalho(nome: str = "SIGAA Sniper") -> str:
    """Cria um atalho na Área de Trabalho do usuário atual apontando para run.bat.
    Devolve o caminho do atalho criado, ou lança uma exceção com uma mensagem clara."""
    if not suportado():
        raise RuntimeError("Criação automática de atalho só é suportada no Windows.")

    area_trabalho = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(area_trabalho):
        raise RuntimeError(f"Pasta da Área de Trabalho não encontrada em: {area_trabalho}")

    alvo = os.path.join(raiz_projeto(), "run.bat")
    if not os.path.exists(alvo):
        raise RuntimeError(f"Arquivo run.bat não encontrado em: {alvo}")

    caminho_atalho = os.path.join(area_trabalho, f"{nome}.lnk")

    script_vbs = f"""\
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{caminho_atalho}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{alvo}"
oLink.WorkingDirectory = "{raiz_projeto()}"
oLink.WindowStyle = 1
oLink.Description = "Abrir o SIGAA Sniper"
oLink.Save
"""

    with tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False, encoding="utf-8") as f:
        f.write(script_vbs)
        caminho_vbs = f.name

    try:
        resultado = subprocess.run(
            ["cscript", "//nologo", caminho_vbs],
            capture_output=True, text=True, timeout=15,
        )
        if resultado.returncode != 0:
            raise RuntimeError(f"cscript retornou erro: {resultado.stderr.strip() or resultado.stdout.strip()}")
    finally:
        try:
            os.remove(caminho_vbs)
        except OSError:
            pass

    if not os.path.exists(caminho_atalho):
        raise RuntimeError("O script rodou, mas o atalho não apareceu na Área de Trabalho.")

    return caminho_atalho


GUIA_MANUAL = """\
Como criar um atalho manualmente (caso a criação automática não funcione):

1. Clique com o botão direito em run.bat, dentro da pasta do programa.
2. Escolha "Enviar para" → "Área de trabalho (criar atalho)".
3. Um atalho vai aparecer na sua Área de Trabalho — pode renomear como quiser.

Pronto: dar duplo clique nesse atalho abre o programa normalmente.
"""
