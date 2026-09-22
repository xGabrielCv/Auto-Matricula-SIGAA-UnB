"""Configuração: padrões, migração, validação, segredos opt-in, importação."""
from __future__ import annotations

import json
import os

from app.core import config
from app.core.credentials import CredenciaisNotificacao
from app.core.engine import URLS_PADRAO


def test_urls_padrao_iguais_no_motor_e_na_config():
    assert config.URLS_SIGAA_PADRAO == URLS_PADRAO


def test_padroes_seguros():
    s = config.carregar_settings()
    assert s["modo"] == "monitoramento"
    assert s["dry_run"] is True
    assert s["web"] == {"host": "127.0.0.1", "porta": 8765, "abrir_navegador": True}
    assert config.validar_settings(s) == []


def test_config_antiga_sem_web_recebe_padrao(raiz_temporaria):
    pasta = os.path.join(raiz_temporaria, "config")
    os.makedirs(pasta, exist_ok=True)
    antiga = {"versao": 3, "modo": "matricula", "num_workers": 7}
    with open(os.path.join(pasta, "settings.json"), "w", encoding="utf-8") as f:
        json.dump(antiga, f)
    s = config.carregar_settings()
    assert s["modo"] == "matricula" and s["num_workers"] == 7
    assert s["web"]["porta"] == 8765


def test_migracao_de_versao_faz_backup(raiz_temporaria):
    pasta = os.path.join(raiz_temporaria, "config")
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"versao": 2, "headless": True}, f)
    config.carregar_settings()
    assert os.path.exists(os.path.join(pasta, "settings.v2.backup.json"))


def test_config_corrompida_volta_ao_padrao(raiz_temporaria):
    pasta = os.path.join(raiz_temporaria, "config")
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, "settings.json"), "w", encoding="utf-8") as f:
        f.write("{isto não é json")
    assert config.carregar_settings()["modo"] == "monitoramento"


def test_validacao_web():
    s = config.carregar_settings()
    s["web"]["porta"] = 80
    assert any("Porta" in p for p in config.validar_settings(s))
    s["web"]["porta"] = True  # bool não é porta
    assert any("Porta" in p for p in config.validar_settings(s))
    s["web"] = {"host": "  ", "porta": 9000}
    assert any("host" in p for p in config.validar_settings(s))


def test_validacao_geral():
    s = config.carregar_settings()
    s.update({"num_workers": 0, "intervalo_busca": 0, "timeout_req": 500, "modo": "x", "agendar_inicio": "amanhã"})
    s["urls"]["cas_login"] = "http://inseguro"
    problemas = " ".join(config.validar_settings(s))
    for trecho in ("workers", "Intervalo", "Timeout", "Modo", "agendamento", "https"):
        assert trecho in problemas


def test_restaurar_avancado_inclui_web():
    s = config.carregar_settings()
    s["web"]["porta"] = 9999
    s["num_workers"] = 3
    r = config.restaurar_padroes(s, ["avancado"])
    assert r["web"]["porta"] == 8765
    assert r["num_workers"] == 3  # outras seções intocadas


def test_disciplinas_roundtrip_e_itens_corrompidos(raiz_temporaria):
    config.salvar_disciplinas([config.Disciplina("fga0211", "01", 673)])
    caminho = os.path.join(raiz_temporaria, "config", "disciplinas.json")
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    dados.append({"codigo": "SEMTURMA"})
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f)
    lidas = config.carregar_disciplinas()
    assert len(lidas) == 1 and lidas[0].codigo == "FGA0211"


def test_segredos_incluem_servidor_ntfy(raiz_temporaria):
    config.salvar_segredos_notificacao("tok", "123", "topico", "https://meu.ntfy")
    n = CredenciaisNotificacao()
    assert config.aplicar_segredos_notificacao_salvos(n) is True
    assert (n.telegram_token, n.telegram_chat_id, n.ntfy_topic, n.ntfy_servidor) == ("tok", "123", "topico", "https://meu.ntfy")
    config.apagar_segredos_notificacao()
    assert not config.existe_segredos_notificacao_salvos()
    assert config.aplicar_segredos_notificacao_salvos(CredenciaisNotificacao()) is False


def test_segredos_antigos_sem_servidor_mantem_padrao(raiz_temporaria):
    config.salvar_segredos_notificacao("tok", "123", "topico")
    n = CredenciaisNotificacao()
    config.aplicar_segredos_notificacao_salvos(n)
    assert n.ntfy_servidor == "https://ntfy.sh"


def test_exportacao_nunca_inclui_credenciais(raiz_temporaria, tmp_path):
    config.salvar_segredos_notificacao("TOKEN_SECRETO", "123", "topico")
    destino = tmp_path / "export.json"
    config.exportar_configuracao(str(destino))
    texto = destino.read_text(encoding="utf-8")
    assert "TOKEN_SECRETO" not in texto


def test_importacao_recusa_credencial_escondida(tmp_path):
    arq = tmp_path / "malicioso.json"
    arq.write_text(json.dumps({"settings": {"senha": "123"}, "disciplinas": []}), encoding="utf-8")
    try:
        config.pre_visualizar_importacao(str(arq))
    except ValueError as e:
        assert "sensíveis" in str(e)
    else:
        raise AssertionError("deveria ter recusado")
