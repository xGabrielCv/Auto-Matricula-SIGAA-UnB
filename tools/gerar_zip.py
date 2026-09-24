"""
Gera o SIGAA-Sniper.zip de distribuição: só o que o usuário final precisa.

Conteúdo: SIGAA-Sniper.exe, README.md, docs/GUIA_DE_USO.md, docs/SEGURANCA.md e
SHA256SUMS.txt (impressão digital do executável). Nunca inclui config/, data/,
logs/, código de desenvolvimento ou documentos internos.
Uso: python tools/gerar_zip.py   (depois do build e do tools/gerar_hashes.py)
"""
from __future__ import annotations

import hashlib
import os
import sys
import zipfile

ARQUIVOS = [
    ("SIGAA-Sniper.exe", "SIGAA-Sniper/SIGAA-Sniper.exe"),
    ("README.md", "SIGAA-Sniper/README.md"),
    ("docs/GUIA_DE_USO.md", "SIGAA-Sniper/docs/GUIA_DE_USO.md"),
    ("docs/SEGURANCA.md", "SIGAA-Sniper/docs/SEGURANCA.md"),
    ("SHA256SUMS.txt", "SIGAA-Sniper/SHA256SUMS.txt"),
]


def main() -> int:
    faltando = [origem for origem, _ in ARQUIVOS if not os.path.isfile(origem)]
    if faltando:
        print(f"[erro] faltam: {', '.join(faltando)}")
        return 1
    with zipfile.ZipFile("SIGAA-Sniper.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for origem, destino in ARQUIVOS:
            z.write(origem, destino)
    problemas = verificar("SIGAA-Sniper.zip")
    if problemas:
        for p in problemas:
            print(f"[erro] {p}")
        return 1
    print("SIGAA-Sniper.zip gerado e conferido:")
    for info in zipfile.ZipFile("SIGAA-Sniper.zip").infolist():
        print(f"  {info.filename}  ({info.file_size} bytes)")
    return 0


def verificar(caminho_zip: str) -> list:
    """Confere o ZIP pronto: exatamente os arquivos esperados (nada de config/, data/,
    logs/, código ou documento interno) e o .exe igual à impressão digital publicada."""
    problemas = []
    with zipfile.ZipFile(caminho_zip) as z:
        nomes = sorted(i.filename for i in z.infolist())
        esperados = sorted(destino for _, destino in ARQUIVOS)
        if nomes != esperados:
            problemas.append(f"conteúdo diferente do esperado: sobrando {sorted(set(nomes) - set(esperados))}, "
                             f"faltando {sorted(set(esperados) - set(nomes))}")
        if z.testzip() is not None:
            problemas.append("arquivo corrompido dentro do ZIP")
        if "SIGAA-Sniper/SIGAA-Sniper.exe" in nomes and "SIGAA-Sniper/SHA256SUMS.txt" in nomes:
            publicado = z.read("SIGAA-Sniper/SHA256SUMS.txt").decode("utf-8").split()[0]
            real = hashlib.sha256(z.read("SIGAA-Sniper/SIGAA-Sniper.exe")).hexdigest()
            if publicado != real:
                problemas.append("o SHA256SUMS.txt não corresponde ao executável do ZIP")
    return problemas


if __name__ == "__main__":
    sys.exit(main())
