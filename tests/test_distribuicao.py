"""Fase 7: esquema único de campos (044), integridade do executável (069) e aviso de versão nova (099)."""
from __future__ import annotations

import copy
import sys

import httpx

from app.core import distribuicao
from app.core.config import PADROES_SETTINGS, validar_settings
from app.core.esquema import ESQUEMA, _obter, faixa


def test_esquema_cobre_os_padroes_e_os_padroes_sao_validos():
    for chave, campo in ESQUEMA.items():
        valor = _obter(PADROES_SETTINGS, chave, None)
        assert valor is not None, f"{chave} não existe nos padrões"
        assert campo.minimo <= valor <= campo.maximo, chave
    assert validar_settings(copy.deepcopy(PADROES_SETTINGS)) == []


def test_mesma_faixa_na_validacao_e_nas_telas():
    s = copy.deepcopy(PADROES_SETTINGS)
    s["logs"]["tamanho_max_mb"] = faixa("logs.tamanho_max_mb")[1] + 1  # antes a tela parava em 500 e a validação em 1000
    s["json_audit"]["arquivos_mantidos"] = 99                            # antes nem era validado
    problemas = validar_settings(s)
    assert any("dumps de debug" in p for p in problemas) and any("log principal" in p for p in problemas)
    s = copy.deepcopy(PADROES_SETTINGS)
    s["num_workers"] = 5.5
    assert any("Número de workers deve estar entre 1 e 100." == p for p in validar_settings(s))


def test_hash_do_executavel(monkeypatch, tmp_path):
    assert distribuicao.hash_executavel() is None  # pelo código-fonte
    exe = tmp_path / "SIGAA-Sniper.exe"
    exe.write_bytes(b"conteudo")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(distribuicao, "_cache_hash", None)
    import hashlib
    assert distribuicao.hash_executavel() == hashlib.sha256(b"conteudo").hexdigest()


def _cliente(status, corpo=None):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=corpo or {})))


def test_verificador_de_versao(monkeypatch):
    monkeypatch.setattr(distribuicao, "VERSAO_APP", "5.1.0")
    repo = distribuicao.URL_REPOSITORIO
    r = distribuicao.verificar_atualizacao(_cliente(200, {"tag_name": "v5.2.0", "html_url": f"{repo}/releases/tag/v5.2.0"}))
    assert r["nova"] and r["ultima"] == "5.2.0" and "5.2.0" in r["texto"] and r["url"].endswith("v5.2.0")
    assert not distribuicao.verificar_atualizacao(_cliente(200, {"tag_name": "v5.1.0"}))["nova"]
    assert not distribuicao.verificar_atualizacao(_cliente(200, {"tag_name": "v5.0.9"}))["nova"]
    falsa = distribuicao.verificar_atualizacao(_cliente(200, {"tag_name": "v9.0.0", "html_url": "https://golpe.exemplo/baixe"}))
    assert falsa["url"].startswith(repo)  # só aponta para o repositório oficial
    assert "Ainda não há versões" in distribuicao.verificar_atualizacao(_cliente(404))["texto"]
    assert distribuicao.verificar_atualizacao(_cliente(500))["ok"] is False


def test_verificacao_desligada_por_padrao():
    assert PADROES_SETTINGS["atualizacoes"]["verificar_ao_abrir"] is False
