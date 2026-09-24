"""
Fonte única de versão e metadados do programa.

Tudo que mostra versão ou o endereço do repositório (terminal, GUI, Web,
diagnóstico) importa daqui. O `version_info.txt` usado pelo PyInstaller é
gerado a partir destes valores por tools/gerar_version_info.py (chamado pelo
tools/build_exe.bat) — tests/test_utilitarios.py garante que os dois batem.
"""
from __future__ import annotations

NOME_APP = "SIGAA Sniper"
VERSAO_APP = "6.1.0"
URL_REPOSITORIO = "https://github.com/xGabrielCv/Auto-Matricula-SIGAA-UnB"


def versao_tupla() -> tuple:
    """(maior, menor, correção, 0) — formato exigido pelo recurso de versão do Windows."""
    partes = [int(p) for p in VERSAO_APP.split(".")[:3]]
    return tuple(partes + [0] * (4 - len(partes)))
