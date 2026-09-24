"""
Gera version_info.txt (metadados do .exe para o PyInstaller) a partir de
app/versao.py — assim a versão só precisa ser alterada num lugar.

Uso: python tools/gerar_version_info.py   (chamado pelo tools/build_exe.bat)
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from app.versao import VERSAO_APP, versao_tupla  # noqa: E402

MODELO = """\
# Metadados de versão do executável (usado pelo PyInstaller via --version-file).
# GERADO AUTOMATICAMENTE por tools/gerar_version_info.py a partir de app/versao.py —
# altere a versão lá, não aqui.
# Gerado para reduzir a chance de falso positivo de antivírus: binários sem
# nenhuma informação de versão/editor tendem a ser tratados como "desconhecidos"
# por mecanismos de reputação. Nenhum campo aqui reivindica afiliação com a UnB
# (ver aviso legal no README e em docs/SEGURANCA.md).
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tupla},
    prodvers={tupla},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [
            StringStruct(u'CompanyName', u'Projeto independente / código aberto'),
            StringStruct(u'FileDescription', u'SIGAA Sniper - Automação e monitoramento de matrícula (projeto educacional, não afiliado à UnB)'),
            StringStruct(u'FileVersion', u'{texto}'),
            StringStruct(u'InternalName', u'SIGAA-Sniper'),
            StringStruct(u'LegalCopyright', u'Código aberto - uso educacional'),
            StringStruct(u'OriginalFilename', u'SIGAA-Sniper.exe'),
            StringStruct(u'ProductName', u'SIGAA Sniper'),
            StringStruct(u'ProductVersion', u'{texto}'),
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""


def conteudo() -> str:
    tupla = versao_tupla()
    return MODELO.format(tupla=repr(tupla), texto=".".join(str(n) for n in tupla))


def main() -> None:
    caminho = os.path.join(RAIZ, "version_info.txt")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo())
    print(f"version_info.txt gerado para a versão {VERSAO_APP}")


if __name__ == "__main__":
    main()
