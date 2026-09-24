#!/usr/bin/env python3
"""
Ponto de entrada único do SIGAA Sniper.

Sem GUI/terminal escolhidos por linha de comando (seção 23 do pedido: nada
de `python main.py --worker 20`). Rodar `python main.py` (ou o .exe
empacotado) sempre cai no menu numerado; a opção [1] abre a GUI.
"""
from __future__ import annotations

import sys

# Alguns terminais Windows (cp1252) derrubam o programa com UnicodeEncodeError
# ao tentar imprimir emojis usados nas mensagens (✅, 🚨, etc.). errors="replace"
# faz esses caracteres virarem "?" em vez de travar o programa inteiro — achado
# e corrigido durante os testes deste projeto (ver docs/ARQUITETURA.md).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _checar_dependencias_essenciais() -> list:
    faltando = []
    for modulo, pacote_pip in [("httpx", "httpx"), ("bs4", "beautifulsoup4"), ("rich", "rich")]:
        try:
            __import__(modulo)
        except ImportError:
            faltando.append(pacote_pip)
    return faltando


def _saida_tolerante() -> None:
    """Saída redirecionada numa codificação sem emoji (ex: cp1252) não pode derrubar
    o menu: o caractere impossível vira um escape em vez de erro."""
    for fluxo in (sys.stdout, sys.stderr):
        try:
            if (getattr(fluxo, "encoding", "") or "").lower().replace("-", "") != "utf8":
                fluxo.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass


def main():
    _saida_tolerante()
    faltando = _checar_dependencias_essenciais()
    if faltando:
        print("=" * 50)
        print("Dependências ausentes detectadas:")
        for pacote in faltando:
            print(f"  - {pacote}")
        print("\nInstale com:")
        print(f"    pip install {' '.join(faltando)}")
        print("\n(No Windows, dando duplo clique em run.bat isso é feito automaticamente.)")
        print("=" * 50)
        sys.exit(1)

    from app.core.credentials import encerrar_sessao
    from app.terminal.menu import menu_principal
    try:
        menu_principal()
    except (EOFError, KeyboardInterrupt):
        # stdin fechado (Ctrl+D/Z) ou interrupção manual — encerra graciosamente
        # em vez de mostrar um traceback pro usuário (bug real encontrado em teste).
        print("\n\nEncerrando. Credenciais apagadas da memória. Até mais!")
        encerrar_sessao()
        sys.exit(0)


if __name__ == "__main__":
    main()
