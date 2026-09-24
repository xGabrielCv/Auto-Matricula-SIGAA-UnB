"""
Configuração compartilhada dos testes.

Todo teste roda com os dados do programa (config/, data/, logs/) numa pasta
temporária — nunca toca na configuração real de quem roda os testes.
"""
from __future__ import annotations

import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


@pytest.fixture(autouse=True)
def raiz_temporaria(tmp_path, monkeypatch):
    import app.utils.paths as paths
    monkeypatch.setattr(paths, "raiz_projeto", lambda: str(tmp_path))
    # Sessão de credenciais é um singleton de processo — zera entre testes.
    from app.core import credentials, historico
    credentials.encerrar_sessao()
    monkeypatch.setattr(historico, "_importacao_feita", False)  # cada teste é uma "sessão" nova
    yield tmp_path
    credentials.encerrar_sessao()
