"""
Modo terminal (e entrada do modo Web pelo menu) — processo real, stdin/stdout.

Roda uma CÓPIA do programa numa pasta temporária (nunca a configuração real).
Por padrão testa o código-fonte (`python main.py`). Com a variável de
ambiente SIGAA_SNIPER_EXE apontando para o executável, os MESMOS testes rodam
contra o .exe (usado para validar o pacote final).
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

import httpx
import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.environ.get("SIGAA_SNIPER_EXE")


class Programa:
    def __init__(self, pasta, env_extra=None):
        if EXE and os.path.isdir(os.path.join(os.path.dirname(EXE), "_internal")):
            # Build "em pasta" (sugestão 100): copia a pasta inteira do programa.
            shutil.copytree(os.path.dirname(EXE), pasta, dirs_exist_ok=True)
            comando = [os.path.join(pasta, os.path.basename(EXE))]
        elif EXE:
            destino = os.path.join(pasta, os.path.basename(EXE))
            shutil.copy2(EXE, destino)
            comando = [destino]
        else:
            for item in ("main.py", "app", "docs"):
                origem = os.path.join(RAIZ, item)
                if os.path.isdir(origem):
                    shutil.copytree(origem, os.path.join(pasta, item), ignore=shutil.ignore_patterns("__pycache__"))
                else:
                    shutil.copy2(origem, pasta)
            comando = [sys.executable, "main.py"]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", **(env_extra or {})}
        self.proc = subprocess.Popen(comando, cwd=pasta, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, env=env)
        self.saida = []
        self._fila = queue.Queue()
        threading.Thread(target=self._ler, daemon=True).start()

    def _ler(self):
        for linha in iter(self.proc.stdout.readline, b""):
            texto = linha.decode("utf-8", errors="replace")
            self.saida.append(texto)
            self._fila.put(texto)

    def enviar(self, texto):
        self.proc.stdin.write(texto.encode("utf-8"))
        self.proc.stdin.flush()

    def esperar(self, padrao, timeout=60):
        limite = time.time() + timeout
        regex = re.compile(padrao)
        while time.time() < limite:
            for linha in self.saida:
                m = regex.search(linha)
                if m:
                    return m
            time.sleep(0.1)
        raise AssertionError(f"'{padrao}' não apareceu. Saída:\n{''.join(self.saida)[-3000:]}")

    def texto(self):
        return "".join(self.saida)

    def finalizar(self, timeout=30):
        try:
            return self.proc.wait(timeout=timeout)
        finally:
            if self.proc.poll() is None:
                self.proc.kill()


def test_recusar_aviso_legal_encerra(tmp_path):
    p = Programa(str(tmp_path))
    p.esperar(r"Aceito todos os termos")
    p.enviar("3\n")
    assert p.finalizar() == 0
    assert "não aceitar os termos" in p.texto()


def test_aceitar_e_sair_mostra_os_tres_modos(tmp_path):
    p = Programa(str(tmp_path))
    p.esperar(r"Aceito todos os termos")
    p.enviar("1\n")
    p.esperar(r"\[6\] Sair")
    p.enviar("6\n")
    assert p.finalizar() == 0
    texto = p.texto()
    assert "[0] 🌐 Interface Web" in texto and "RECOMENDADO" in texto
    assert "[1] Interface gráfica" in texto and "[2] Matrícula automática" in texto
    assert "Credenciais apagadas da memória" in texto


def test_texto_completo_do_disclaimer(tmp_path):
    p = Programa(str(tmp_path))
    p.esperar(r"Aceito todos os termos")
    p.enviar("2\n")
    p.esperar(r"Modalidade Segura")
    p.enviar("\n3\n")
    assert p.finalizar() == 0


def test_configuracoes_avancadas_pelo_terminal(tmp_path):
    p = Programa(str(tmp_path))
    p.esperar(r"Aceito todos os termos")
    # aceitar → Configurações → Avançadas → workers=5, intervalo=0.5, timeout=ENTER → voltar → sair
    p.enviar("1\n4\n4\n5\n0.5\n\n\n7\n6\n")
    assert p.finalizar() == 0
    with open(tmp_path / "config" / "settings.json", encoding="utf-8") as f:
        s = json.load(f)
    assert s["num_workers"] == 5 and s["intervalo_busca"] == 0.5 and s["timeout_req"] == 10


def test_interface_web_pelo_menu(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.json").write_text(json.dumps(
        {"versao": 3, "web": {"host": "127.0.0.1", "porta": 0, "abrir_navegador": False}}), encoding="utf-8")
    p = Programa(str(tmp_path))
    p.esperar(r"Aceito todos os termos")
    p.enviar("1\n0\n")
    m = p.esperar(r"(http://127\.0\.0\.1:\d+)/\?chave=(\S+)")
    base, chave = m.group(1), m.group(2)
    with httpx.Client(base_url=base, follow_redirects=True, timeout=15) as c:
        pagina = c.get(f"/?chave={chave}")
        assert pagina.status_code == 200 and "SIGAA Sniper" in pagina.text
        for estatico in ("/static/app.js", "/static/graficos.js", "/static/app.css"):
            assert c.get(estatico).status_code == 200, estatico  # tudo embutido (inclusive no .exe)
        est = c.get("/api/estado", headers={"X-Requested-With": "SIGAA-Sniper"}).json()
        assert est["aviso_aceito"] is False  # a Web exige o aviso de novo, como a GUI
    p.enviar("\n")  # ENTER encerra a Interface Web e volta ao menu
    p.esperar(r"Interface Web encerrada")
    p.esperar(r"\[6\] Sair")
    p.enviar("6\n")
    assert p.finalizar() == 0
    with pytest.raises(httpx.HTTPError):
        httpx.get(base, timeout=2)


def test_porta_ocupada_informa_e_usa_outra(tmp_path):
    import socket
    ocupado = socket.socket()
    ocupado.bind(("127.0.0.1", 0))
    ocupado.listen(1)
    porta = ocupado.getsockname()[1]
    try:
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "settings.json").write_text(json.dumps(
            {"versao": 3, "web": {"host": "127.0.0.1", "porta": porta, "abrir_navegador": False}}), encoding="utf-8")
        p = Programa(str(tmp_path))
        p.esperar(r"Aceito todos os termos")
        p.enviar("1\n0\n")
        p.esperar(rf"a porta {porta} estava ocupada")
        p.enviar("\n")
        p.esperar(r"Interface Web encerrada")
        p.enviar("6\n")
        assert p.finalizar() == 0
    finally:
        ocupado.close()


# ── Fase 1 ───────────────────────────────────────────────────────────────

def _settings(tmp_path):
    with open(tmp_path / "config" / "settings.json", encoding="utf-8") as f:
        return json.load(f)


def test_preset_de_carga_pelo_terminal(tmp_path):
    p = Programa(str(tmp_path))
    p.esperar(r"Aceito todos os termos")
    # aceitar → Configurações → Avançadas → perfil Leve (L) → timeout ENTER → pausa → voltar → sair
    p.enviar("1\n4\n4\nL\n\n\n7\n6\n")
    assert p.finalizar() == 0
    s = _settings(tmp_path)
    assert s["num_workers"] == 4 and s["intervalo_busca"] == 1.5
    assert "Carga estimada" in p.texto() and "(baixa)" in p.texto()


def test_terminal_nao_salva_configuracao_invalida(tmp_path):
    p = Programa(str(tmp_path))
    p.esperar(r"Aceito todos os termos")
    p.enviar("1\n4\n4\n500\n\n\n\n7\n6\n")
    assert p.finalizar() == 0
    assert "Não salvo" in p.texto()
    assert not (tmp_path / "config" / "settings.json").exists() or _settings(tmp_path)["num_workers"] != 500


def test_disciplinas_em_lote_pelo_terminal(tmp_path):
    p = Programa(str(tmp_path))
    p.esperar(r"Aceito todos os termos")
    # Configurações → Disciplinas → [5] lote (lista vazia) → 3 linhas (1 inválida) → linha vazia → confirmar
    # → [6] Continuar (agora com 2 disciplinas) → voltar → sair
    p.enviar("1\n4\n2\n5\nFGA0211 01 673\nMAT0025;02;518\nXYZ A 1\n\ns\n6\n7\n6\n")
    assert p.finalizar() == 0
    with open(tmp_path / "config" / "disciplinas.json", encoding="utf-8") as f:
        salvas = json.load(f)
    assert [(d["codigo"], d["turma"]) for d in salvas] == [("FGA0211", "01"), ("MAT0025", "02")]
    assert "só os números" in p.texto()


def test_eventos_recentes_em_linguagem_simples(tmp_path):
    (tmp_path / "data").mkdir()
    linhas = [
        {"timestamp": "2026-01-01 10:00:00", "level": "INFO", "worker": "MAIN", "message": "SESSAO_INICIADA id=x"},
        {"timestamp": "2026-01-01 10:00:01", "level": "WARNING", "worker": "W0", "message": "[W0] 🚨 VAGA DETECTADA (80ms) -> FGA0211-01 (1 vaga(s))!"},
    ]
    (tmp_path / "data" / "sigaa_sniper_audit.json").write_text(
        "".join(json.dumps(l, ensure_ascii=False) + "\n" for l in linhas), encoding="utf-8")
    p = Programa(str(tmp_path), env_extra={"COLUMNS": "140"})
    p.esperar(r"Aceito todos os termos")
    p.enviar("1\n5\n3\n")
    p.esperar(r"Vaga encontrada em FGA0211-01")
    p.enviar("5\n5\n6\n")  # voltar dos eventos → [5] Voltar do Diagnóstico (desde a Fase 3) → sair
    assert p.finalizar() == 0
    assert "Nova execução iniciada" in p.texto()


def test_historico_pelo_terminal(tmp_path):
    """Fase 3: a execução gravada aparece no histórico do terminal, com relatório e exportação CSV."""
    (tmp_path / "data" / "relatorios").mkdir(parents=True)
    resumo = {
        "execucao_id": "2026-09-24-abc123", "versao": "t", "modo": "monitoramento", "dry_run": True,
        "inicio": "2026-09-24 10:00:00", "fim": "2026-09-24 11:30:00", "duracao_seg": 5400, "motivo_fim": "interrompida",
        "configuracao": {"num_workers": 8, "intervalo_busca": 0.8, "timeout_req": 10, "agendar_inicio": None},
        "alvos": [{"chave": "FGA0211-01", "codigo": "FGA0211", "turma": "01", "departamento": 673, "estado": "sem_vagas",
                   "estado_rotulo": "Sem vagas", "vagas": 0, "buscas": 900, "vagas_vistas": 2, "tentativas": 0}],
        "totais": {"requisicoes": 900, "vagas_vistas": 2, "tentativas": 0, "matriculadas": 0, "simuladas": 0, "bloqueadas": 0, "erros": 3},
        "erros": {"timeout": 3}, "latencia_ms": {"media": 200, "min": 90, "max": 900}, "contadores": {},
    }
    (tmp_path / "data" / "relatorios" / "2026-09-24-abc123.json").write_text(json.dumps(resumo), encoding="utf-8")
    p = Programa(str(tmp_path))
    p.esperar(r"Aceito todos os termos")
    # aceitar → Diagnóstico → Histórico → ver [1] → pausa → exportar → pausa → voltar → voltar → sair
    p.enviar("1\n5\n4\n1\n\ne\n\nv\n5\n6\n")
    assert p.finalizar() == 0
    texto = p.texto()
    assert "24/09/2026 10:00" in texto and "Resumo da execução 2026-09-24-abc123" in texto
    exportados = list((tmp_path / "data" / "exportacoes").glob("historico_*.csv"))
    assert len(exportados) == 1 and "2026-09-24-abc123" in exportados[0].read_text(encoding="utf-8-sig")


def test_termino_e_janela_pelo_terminal(tmp_path):
    p = Programa(str(tmp_path))
    p.esperar(r"Aceito todos os termos")
    # Configurações → [8] → término, janela sim 08:00–18:00 seg-sex, relógio sim, verificação ENTER → pausa → voltar → sair
    p.enviar("1\n4\n8\n31/12/2030 23:00:00\ns\n08:00\n18:00\nseg,ter,qua,qui,sex\ns\n\n\n7\n6\n")
    assert p.finalizar() == 0
    s = _settings(tmp_path)
    assert s["agendar_fim"] == "31/12/2030 23:00:00" and s["agendamento_relogio_sigaa"] is True
    assert s["janela"] == {"ativa": True, "inicio": "08:00", "fim": "18:00", "dias": [0, 1, 2, 3, 4]}
    assert "das 08:00 às 18:00" in p.texto()


def test_assistente_e_pacote_de_suporte_pelo_terminal(tmp_path):
    p = Programa(str(tmp_path))
    p.esperar(r"Aceito todos os termos")
    # Diagnóstico → [6] assistente → sintoma 3 → pausa → voltar → [8] pacote (s) → pausa → [5] voltar → sair
    p.enviar("1\n5\n6\n3\n\nv\n8\ns\n\n5\n6\n")
    assert p.finalizar() == 0
    texto = p.texto()
    assert "Nunca aparece vaga" in texto and "Ainda não há execução para analisar" in texto
    assert "LEIA-ME.txt" in texto and "Pacote salvo em" in texto
    pacotes = os.listdir(tmp_path / "data" / "exportacoes")
    assert len(pacotes) == 1 and pacotes[0].startswith("sigaa_sniper_suporte_") and pacotes[0].endswith(".zip")


def test_perfis_e_acoes_registradas_pelo_terminal(tmp_path):
    p = Programa(str(tmp_path))
    p.esperar(r"Aceito todos os termos")
    # Configurações → [9] perfis → S (nome) → pausa → V → [7] voltar → Diagnóstico → [4] histórico → A → pausa → V → [5] → sair
    p.enviar("1\n4\n9\ns\nSemana\n\nv\n7\n5\n4\na\n\nv\n5\n6\n")
    assert p.finalizar() == 0
    assert (tmp_path / "config" / "perfis" / "semana.json").exists()
    texto = p.texto()
    assert "Perfil \"Semana\" salvo" in texto and "Aceitou o aviso legal" in texto and "Salvou um perfil" in texto


def test_demonstracao_pelo_terminal(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.json").write_text(json.dumps({"versao": 3, "num_workers": 4, "intervalo_busca": 0.1}),
                                                        encoding="utf-8")
    p = Programa(str(tmp_path))
    p.esperar(r"Aceito todos os termos")
    # aceitar → [7] demonstração → modo 1 (ENTER) → ENTER inicia → ... termina sozinha → pausa → sair
    p.enviar("1\n7\n\n\n")
    p.esperar(r"Demonstração encerrada", timeout=120)
    p.enviar("\n6\n")
    assert p.finalizar() == 0
    texto = p.texto()
    assert "DEMONSTRAÇÃO" in texto and "não foi guardado no histórico" in texto
    assert not (tmp_path / "data" / "historico.db").exists()


def test_paridade_do_terminal_editar_exportar_web(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "disciplinas.json").write_text(json.dumps(
        [{"codigo": "FGA0211", "turma": "01", "departamento": 673, "ativa": True}]), encoding="utf-8")
    p = Programa(str(tmp_path))
    p.esperar(r"Aceito todos os termos")
    # Configurações → Disciplinas → [7] editar a 1 (turma 02, resto ENTER) → pausa → [5] continuar
    # → [13] Web/logs (porta 9001, resto ENTER) → pausa → [11] exportar [1] → pausa → [7] voltar → sair
    p.enviar("1\n4\n2\n7\n1\n\n02\n\n\n\n\n5\n13\n\n9001\n\n\n\n\n\n\n11\n1\n\n7\n6\n")
    assert p.finalizar() == 0
    assert json.loads((tmp_path / "config" / "disciplinas.json").read_text(encoding="utf-8"))[0]["turma"] == "02"
    assert _settings(tmp_path)["web"]["porta"] == 9001
    assert any(n.startswith("sigaa_sniper_config_") for n in os.listdir(tmp_path / "data" / "exportacoes"))


def test_saida_redirecionada_sem_utf8_nao_quebra(tmp_path):
    p = Programa(str(tmp_path), env_extra={"PYTHONIOENCODING": "cp1252"})
    p.esperar(r"Aceito todos os termos")
    p.enviar("1\n6\n")
    assert p.finalizar() == 0
    assert "Traceback" not in p.texto() and "Logging error" not in p.texto()
