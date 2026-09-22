"""
Criação de atalho do Windows — seção 94.5 do pedido.

Usa o truque clássico de gerar um script VBS temporário que chama
WScript.Shell para criar o .lnk, executado via `cscript` (já vem com
qualquer Windows) — evita adicionar pywin32/pyshortcuts como dependência só
para isso.

Correções desta versão (bugs reais):
  1. No pacote do executável não existe run.bat — o atalho sempre falhava com
     "run.bat não encontrado". Agora, rodando como .exe, o atalho aponta para o
     próprio SIGAA-Sniper.exe; rodando pelo código-fonte, continua apontando
     para run.bat (comportamento anterior preservado).
  2. O .vbs era gravado em UTF-8, mas o cscript lê scripts sem BOM na página
     de código ANSI — caminhos com acento (ex: C:\\Users\\João\\...) ficavam
     corrompidos e o atalho não era criado. Agora é gravado em UTF-16 (com BOM),
     que o cscript lê corretamente.
  3. A Área de Trabalho redirecionada para o OneDrive (padrão em muitos
     Windows 10/11) não fica em ~/Desktop. Agora a pasta real é consultada no
     Windows (SHGetFolderPathW) antes de cair no ~/Desktop.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from app.utils.paths import raiz_projeto


def suportado() -> bool:
    return sys.platform == "win32"


def _pasta_area_de_trabalho() -> str:
    if suportado():
        try:
            import ctypes
            from ctypes import wintypes

            CSIDL_DESKTOPDIRECTORY = 0x0010
            buffer = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_DESKTOPDIRECTORY, None, 0, buffer) == 0 and buffer.value:
                return buffer.value
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


def alvo_do_atalho() -> str:
    """O .exe quando empacotado; run.bat quando rodando pelo código-fonte."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.join(raiz_projeto(), "run.bat")


def criar_atalho_area_trabalho(nome: str = "SIGAA Sniper") -> str:
    """Cria um atalho na Área de Trabalho do usuário atual apontando para o
    programa. Devolve o caminho do atalho criado, ou lança uma exceção com uma
    mensagem clara."""
    if not suportado():
        raise RuntimeError("Criação automática de atalho só é suportada no Windows.")

    area_trabalho = _pasta_area_de_trabalho()
    if not os.path.isdir(area_trabalho):
        raise RuntimeError(f"Pasta da Área de Trabalho não encontrada em: {area_trabalho}")

    alvo = alvo_do_atalho()
    if not os.path.exists(alvo):
        raise RuntimeError(f"Arquivo do programa não encontrado em: {alvo}")

    caminho_atalho = os.path.join(area_trabalho, f"{nome}.lnk")

    def _vbs(texto: str) -> str:
        return texto.replace('"', '""')  # escape de aspas em string VBScript

    script_vbs = f"""\
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{_vbs(caminho_atalho)}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{_vbs(alvo)}"
oLink.WorkingDirectory = "{_vbs(raiz_projeto())}"
oLink.WindowStyle = 1
oLink.Description = "Abrir o SIGAA Sniper"
oLink.Save
"""

    # "utf-16" grava com BOM — o cscript reconhece e lê acentos corretamente.
    with tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False, encoding="utf-16") as f:
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

1. Clique com o botão direito em SIGAA-Sniper.exe (ou em run.bat, se estiver
   usando o código-fonte), dentro da pasta do programa.
2. Escolha "Enviar para" → "Área de trabalho (criar atalho)".
3. Um atalho vai aparecer na sua Área de Trabalho — pode renomear como quiser.

Pronto: dar duplo clique nesse atalho abre o programa normalmente.
"""
