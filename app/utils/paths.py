"""
Resolução de caminhos portáteis.

Nada aqui pode depender do usuário/máquina de desenvolvimento. Tudo é relativo
à raiz do projeto, descoberta em tempo de execução — funciona em qualquer
pasta (Desktop, Downloads, pendrive, outro computador) e também quando
empacotado com PyInstaller (onde os arquivos ficam ao lado do .exe, não do
código-fonte extraído).
"""
from __future__ import annotations

import os
import sys


def raiz_projeto() -> str:
    """Diretório raiz do projeto (onde ficam config/, logs/, data/, docs/)."""
    if getattr(sys, "frozen", False):
        # Executável PyInstaller: usa a pasta onde o .exe está, não o _MEIPASS temporário.
        return os.path.dirname(sys.executable)
    # Execução via código-fonte: sobe de app/utils/ até a raiz do projeto.
    aqui = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(aqui))


def caminho(*partes: str) -> str:
    """Monta um caminho absoluto dentro da raiz do projeto, criando pastas pai se preciso."""
    p = os.path.join(raiz_projeto(), *partes)
    pai = os.path.dirname(p)
    if pai:
        os.makedirs(pai, exist_ok=True)
    return p


def pasta_config() -> str:
    d = os.path.join(raiz_projeto(), "config")
    os.makedirs(d, exist_ok=True)
    return d


def pasta_logs() -> str:
    d = os.path.join(raiz_projeto(), "logs")
    os.makedirs(d, exist_ok=True)
    return d


def pasta_data() -> str:
    d = os.path.join(raiz_projeto(), "data")
    os.makedirs(d, exist_ok=True)
    return d


def pasta_docs() -> str:
    return os.path.join(raiz_projeto(), "docs")
