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
        if EXE:
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
