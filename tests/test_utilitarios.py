"""Atalho da Área de Trabalho, Telegram, caminhos e departamentos."""
from __future__ import annotations

import asyncio
import os
import sys

import httpx
import pytest

from app.core import shortcut


def test_alvo_do_atalho_codigo_fonte_e_exe(monkeypatch):
    assert shortcut.alvo_do_atalho().endswith("run.bat")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Programas\SIGAA-Sniper.exe")
    assert shortcut.alvo_do_atalho() == r"C:\Programas\SIGAA-Sniper.exe"


@pytest.mark.skipif(sys.platform != "win32", reason="atalho .lnk só existe no Windows")
def test_atalho_em_pasta_com_acentos(tmp_path, monkeypatch, raiz_temporaria):
    """Regressão: o .vbs em UTF-8 corrompia caminhos com acento no cscript."""
    area = tmp_path / "Área de Trabalho do João"
    area.mkdir()
    (raiz_temporaria / "run.bat").write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setattr(shortcut, "_pasta_area_de_trabalho", lambda: str(area))
    caminho = shortcut.criar_atalho_area_trabalho(nome="Teste Sniper Ção")
    assert os.path.exists(caminho) and caminho.endswith("Teste Sniper Ção.lnk")


@pytest.mark.skipif(sys.platform != "win32", reason="consulta de pasta especial do Windows")
def test_pasta_area_de_trabalho_real_existe():
    assert os.path.isdir(shortcut._pasta_area_de_trabalho())


def test_telegram_sem_parse_mode(monkeypatch):
    """Regressão: parse_mode=Markdown fazia o Telegram recusar mensagens com '_'."""
    from app.notifications import telegram
    enviados = []

    def handler(request):
        enviados.append(request)
        return httpx.Response(200, json={"ok": True})

    original = httpx.AsyncClient
    monkeypatch.setattr(telegram.httpx, "AsyncClient", lambda *a, **k: original(*a, transport=httpx.MockTransport(handler), **k))
    asyncio.run(telegram.enviar_telegram("TOKEN", "42", "💥 Erro crítico: KeyError('form_menu_discente')"))
    import json
    corpo = json.loads(enviados[0].content)
    assert "parse_mode" not in corpo and corpo["text"].endswith("discente')")


def test_pasta_docs_cai_para_recursos_embutidos(raiz_temporaria):
    from app.utils.paths import pasta_docs
    # a pasta temporária não tem docs/ → usa a cópia que acompanha o programa
    assert os.path.exists(os.path.join(pasta_docs(), "GUIA_DE_USO.md"))


def test_busca_de_departamento():
    from app.core.departamentos import buscar_departamentos, codigo_conhecido
    assert buscar_departamentos("gama")[0].codigo == 673
    assert buscar_departamentos("673")[0].codigo == 673
    assert codigo_conhecido(508) and not codigo_conhecido(123456)
