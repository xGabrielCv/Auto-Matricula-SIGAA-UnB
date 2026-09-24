"""
Gera SHA256SUMS.txt com o SHA-256 dos arquivos distribuídos (sugestão 069).

Uso: python tools/gerar_hashes.py SIGAA-Sniper.exe [SIGAA-Sniper.zip ...]
Chamado pelo tools/build_exe.bat depois do build. Quem baixa pode comparar
com o hash mostrado em "Sobre" ou com `certutil -hashfile SIGAA-Sniper.exe SHA256`.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.distribuicao import sha256_arquivo  # noqa: E402


def main(arquivos) -> int:
    linhas = []
    for caminho in arquivos:
        if not os.path.isfile(caminho):
            print(f"[aviso] {caminho} não existe — ignorado")
            continue
        linhas.append(f"{sha256_arquivo(caminho)}  {os.path.basename(caminho)}")
    if not linhas:
        return 1
    with open("SHA256SUMS.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(linhas) + "\n")
    print("\n".join(linhas))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["SIGAA-Sniper.exe"]))
