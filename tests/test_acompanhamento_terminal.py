"""Acompanhamento da execução no terminal (sugestões 014/017): parada pela
tecla Q, alternância painel/log com D e modo sem teclado (entrada redirecionada)."""
from __future__ import annotations

import asyncio
import logging
import sys
import time

from app.terminal import acompanhamento


class MotorFalso:
    execucao_id = "teste-terminal"
    modo = "monitoramento"
    dry_run = True

    def __init__(self, dura_seg=None):
        self.log = logging.getLogger("teste_acompanhamento")
        self.dura_seg = dura_seg
        self.parado_por_pedido = False

    async def executar(self):
        inicio = time.time()
        while not self.parado_por_pedido:
            if self.dura_seg is not None and time.time() - inicio > self.dura_seg:
                return
            await asyncio.sleep(0.02)

    def parar(self):
        self.parado_por_pedido = True


class TeclasFalsas:
    """Substitui o leitor de teclado: devolve a sequência programada, uma tecla por leitura."""
    sequencia = []

    def __init__(self):
        self.disponivel = True
        self._fila = list(TeclasFalsas.sequencia)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def ler(self):
        return self._fila.pop(0) if self._fila else None


def test_sem_teclado_espera_o_motor_terminar(raiz_temporaria):
    motor = MotorFalso(dura_seg=0.3)
    saida = []
    assert acompanhamento.acompanhar_execucao(motor, entrada_interativa=False, imprimir=saida.append) is None
    assert not motor.parado_por_pedido
    assert any("Ctrl+C" in s for s in saida)


def test_tecla_q_no_painel_para_com_seguranca(raiz_temporaria, monkeypatch):
    TeclasFalsas.sequencia = [None, None, "q"]
    monkeypatch.setattr(acompanhamento, "LeitorTeclas", TeclasFalsas)
    motor = MotorFalso()
    inicio = time.time()
    acompanhamento.acompanhar_execucao(motor, imprimir=lambda _t: None)
    assert motor.parado_por_pedido and time.time() - inicio < 10


def test_tecla_d_alterna_para_linhas_de_log_e_q_para(raiz_temporaria, monkeypatch):
    TeclasFalsas.sequencia = [None, "d", None, "q"]
    monkeypatch.setattr(acompanhamento, "LeitorTeclas", TeclasFalsas)
    motor = MotorFalso()
    saida = []
    acompanhamento.acompanhar_execucao(motor, imprimir=saida.append)
    assert motor.parado_por_pedido
    assert any("Linhas de log" in s for s in saida) and any("Parando com segurança" in s for s in saida)


def test_console_volta_ao_normal_depois_do_painel(raiz_temporaria, monkeypatch):
    TeclasFalsas.sequencia = ["q"]
    monkeypatch.setattr(acompanhamento, "LeitorTeclas", TeclasFalsas)
    motor = MotorFalso()
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    motor.log.addHandler(handler)
    try:
        acompanhamento.acompanhar_execucao(motor, imprimir=lambda _t: None)
        assert handler.level == logging.INFO  # o painel silencia o console só enquanto está na tela
    finally:
        motor.log.removeHandler(handler)


def test_eventos_recentes_filtra(raiz_temporaria):
    import json
    pasta = raiz_temporaria / "data"
    pasta.mkdir(exist_ok=True)
    linhas = [
        {"timestamp": "2026-01-01 10:00:01", "level": "WARNING", "worker": "W0", "message": "[W0] ⏳ Timeout (Socket Preso). Ressuscitando worker..."},
        {"timestamp": "2026-01-01 10:00:02", "level": "WARNING", "worker": "W1", "message": "[W1] 🚨 VAGA DETECTADA (80ms) -> FGA0211-01 (1 vaga(s))!"},
        "linha corrompida",
    ]
    (pasta / "sigaa_sniper_audit.json").write_text(
        "".join((json.dumps(l, ensure_ascii=False) if isinstance(l, dict) else l) + "\n" for l in linhas), encoding="utf-8")
    assert len(acompanhamento.eventos_recentes()) == 2
    assert [e.categoria for e in acompanhamento.eventos_recentes(categoria="REDE")] == ["REDE"]
    assert acompanhamento.eventos_recentes(texto="fga0211")[0].worker == "W1"


def test_executor_nao_perde_pedido_de_parada_antes_do_loop_existir():
    """Regressão: ExecutorMotor.parar() chamado antes de a thread criar o event
    loop era ignorado e o motor continuava rodando."""
    from app.core.runner import ExecutorMotor
    motor = MotorFalso()
    executor = ExecutorMotor(motor)
    executor.parar()
    executor.iniciar()
    executor.aguardar(timeout=5)
    assert not executor.em_execucao() and motor.parado_por_pedido


def test_painel_do_terminal_mostra_disciplinas_do_motor(raiz_temporaria, monkeypatch):
    """Com um motor real (SIGAA simulado), o painel inclui a tabela de disciplinas."""
    import httpx
    from rich.console import Console
    from app.core import engine
    from app.dashboard.cli_dashboard import gerar_painel_alvos, montar_layout
    from tests.test_engine_fluxo import SigaaSimulado, montar
    simulado = SigaaSimulado()
    original = httpx.AsyncClient
    monkeypatch.setattr(engine.httpx, "AsyncClient", lambda *a, **k: original(*a, **{**k, "transport": httpx.MockTransport(simulado)}))
    motor, _ = montar(dry_run=True)
    asyncio.run(asyncio.wait_for(motor.executar(), 15))
    console = Console(record=True, width=120, legacy_windows=False)
    console.print(gerar_painel_alvos(motor.snapshot()))
    texto = console.export_text()
    assert "FGA0211-01" in texto and "DRY RUN" in texto and "Execução encerrada" in texto
    assert montar_layout(com_rodape=True, qtd_alvos=1)["alvos"] is not None


def test_fluxo_completo_do_terminal_ate_o_resumo(raiz_temporaria, monkeypatch, capsys):
    """Menu [2] em DRY RUN, de ponta a ponta no mesmo processo: credenciais validadas,
    disciplina, execução real do motor (SIGAA simulado) e resumo impresso no fim."""
    import builtins
    import httpx
    from app.core import engine
    from app.core.config import Disciplina, salvar_disciplinas
    from app.terminal import menu
    from tests.test_engine_fluxo import SigaaSimulado
    simulado = SigaaSimulado()
    original = httpx.AsyncClient
    monkeypatch.setattr(engine.httpx, "AsyncClient", lambda *a, **k: original(*a, **{**k, "transport": httpx.MockTransport(simulado)}))
    monkeypatch.setattr(menu, "limpar_tela", lambda: None)
    salvar_disciplinas([Disciplina("FGA0211", "01", 673)])
    respostas = iter([
        "200012345",          # matrícula
        "123.456.789-00",     # CPF inválido → programa pede de novo
        "01022003",           # nascimento (normalizado)
        "",                   # "Digitar CPF e data de novo?" → sim (padrão)
        "12345678909", "01/02/2003",
        "5",                  # menu de disciplinas: [5] Continuar (1 disciplina cadastrada)
        "",                   # DRY RUN? [S/n] → sim
        "",                   # ENTER para iniciar
        "",                   # pausa final
    ])
    monkeypatch.setattr(builtins, "input", lambda _p="": next(respostas))
    monkeypatch.setattr(menu.getpass, "getpass", lambda _p="": "s3nh@")
    menu.fluxo_execucao("matricula")
    saida = capsys.readouterr().out
    assert "CPF inválido" in saida
    assert "Resumo da execução" in saida and "Matrícula simulada (DRY RUN)" in saida
    assert simulado.posts_confirmacao() == []  # DRY RUN nunca confirma


def test_tecla_p_pausa_e_retoma(raiz_temporaria, monkeypatch):
    class MotorPausavel(MotorFalso):
        pausado = False
        motivo_pausa = None
        historico = []

        def pausar(self, motivo):
            self.pausado = True
            MotorPausavel.historico.append("pausar")

        def retomar(self, motivo):
            self.pausado = False
            MotorPausavel.historico.append("retomar")

    TeclasFalsas.sequencia = [None, "p", None, "p", None, "q"]
    monkeypatch.setattr(acompanhamento, "LeitorTeclas", TeclasFalsas)
    motor = MotorPausavel()
    acompanhamento.acompanhar_execucao(motor, imprimir=lambda _t: None)
    assert MotorPausavel.historico == ["pausar", "retomar"] and motor.parado_por_pedido
