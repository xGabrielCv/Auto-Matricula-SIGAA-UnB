"""
Acompanhamento de uma execução no terminal (sugestões 014, 017 e 016).

Antes, o terminal rodava `asyncio.run(motor.executar())` e mostrava só as
linhas de log rolando; parar exigia Ctrl+C, que interrompe o motor de forma
abrupta. Agora o motor roda pelo mesmo ExecutorMotor da GUI e da Web, e o
terminal mostra:

  - o painel ao vivo (`rich`) que já existia em app/dashboard/cli_dashboard.py
    mas não era acessível por nenhum menu — enquanto ele está na tela, o log
    continua sendo gravado no arquivo, só não é impresso no console;
  - teclas durante a execução: Q para parar com elegância (mesmo "Parar" da
    GUI/Web) e D para alternar entre o painel e as linhas de log.

Sem um terminal interativo (ex: entrada redirecionada), não há como ler
teclas: o comportamento volta ao anterior (linhas de log, Ctrl+C para parar).
"""
from __future__ import annotations

import logging
import os
import sys
import time
from typing import Callable, List, Optional

from app.core.runner import ExecutorMotor
from app.dashboard.log_humano import CATEGORIAS, traduzir
from app.dashboard.metrics import ColetorMetricas, LogTailer, ler_ultimos_registros
from app.utils.paths import caminho as caminho_projeto

ARQUIVO_LOG = ("data", "sigaa_sniper_audit.json")


# ── Teclado sem bloquear ─────────────────────────────────────────────────

class LeitorTeclas:
    """Lê uma tecla por vez sem esperar ENTER. No Windows usa msvcrt (mesma
    técnica do encerramento da Interface Web); em outros sistemas, termios."""

    def __init__(self):
        self.disponivel = bool(sys.stdin) and hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
        self._termios_original = None

    def __enter__(self):
        if self.disponivel and os.name != "nt":
            try:
                import termios
                import tty
                self._termios_original = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
            except Exception:
                self.disponivel = False
        return self

    def __exit__(self, *_):
        if self._termios_original is not None:
            import termios
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._termios_original)

    def ler(self) -> Optional[str]:
        if not self.disponivel:
            return None
        try:
            if os.name == "nt":
                import msvcrt
                if msvcrt.kbhit():
                    return msvcrt.getwch().lower()
                return None
            import select
            prontos, _, _ = select.select([sys.stdin], [], [], 0)
            return sys.stdin.read(1).lower() if prontos else None
        except Exception:
            return None


def _handler_console(logger: logging.Logger) -> Optional[logging.Handler]:
    for h in logger.handlers:
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            return h
    return None


# ── Painel ao vivo ───────────────────────────────────────────────────────

def _rodape(motor, parando: bool):
    from rich.panel import Panel
    if motor.modo == "monitoramento":
        modo = "[green]SOMENTE MONITORAMENTO[/] (nunca matricula)"
    elif motor.dry_run:
        modo = "[yellow]MATRÍCULA em DRY RUN[/] (teste — não confirma)"
    else:
        modo = "[bold white on red] MATRÍCULA REAL [/] confirma de verdade ao achar vaga"
    if getattr(motor, "demo", False):
        modo = "[bold black on cyan] DEMONSTRAÇÃO [/] SIGAA simulado · " + modo
    if parando:
        teclas = "[yellow]Parando… aguardando os workers atuais encerrarem[/]"
    elif getattr(motor, "pausado", False):
        teclas = "[yellow]PAUSADO[/] · [bold]P[/] retomar  ·  [bold]Q[/] parar  ·  [bold]D[/] ver linhas de log"
    else:
        teclas = "[bold]P[/] pausar  ·  [bold]Q[/] parar  ·  [bold]D[/] ver linhas de log"
    return Panel(f"{modo}   ·   execução {motor.execucao_id}   ·   {teclas}", style="dim")


def acompanhar_execucao(motor, entrada_interativa: Optional[bool] = None,
                        imprimir: Callable[[str], None] = print) -> Optional[Exception]:
    """Inicia o motor numa thread e acompanha até ele terminar. Devolve o erro
    do motor, se houve. Nunca deixa uma exceção de tela derrubar a execução."""
    erro_motor: List[Optional[Exception]] = [None]
    executor = ExecutorMotor(motor, ao_finalizar=lambda e: erro_motor.__setitem__(0, e))

    caminho_log = caminho_projeto(*ARQUIVO_LOG)
    tailer = LogTailer(caminho_log)
    tailer.pular_para_o_fim()  # o painel mostra só esta execução
    coletor = ColetorMetricas()
    console_handler = _handler_console(motor.log)
    nivel_original = console_handler.level if console_handler else None

    def silenciar_console(silenciar: bool):
        if console_handler is not None:
            console_handler.setLevel(logging.CRITICAL + 1 if silenciar else nivel_original)

    with LeitorTeclas() as teclas:
        interativo = teclas.disponivel if entrada_interativa is None else entrada_interativa
        modo_painel = interativo
        parando = False
        executor.iniciar()
        if not interativo:
            imprimir("\nIniciando... pressione Ctrl+C para parar.\n")
        try:
            while executor.em_execucao():
                if modo_painel:
                    modo_painel = _loop_painel(motor, executor, tailer, coletor, teclas, silenciar_console,
                                               lambda: parando)
                    if not executor.em_execucao():
                        break
                    if modo_painel is None:  # Q pressionado dentro do painel
                        parando = True
                        executor.parar()
                        modo_painel = True
                        continue
                    imprimir("\n— Linhas de log (D volta ao painel, Q para parar) —\n")
                    continue
                # Modo linhas de log
                for linha in tailer.read_new_lines():
                    coletor.processar_linha(linha, ao_vivo=True)
                tecla = teclas.ler() if interativo else None
                if tecla == "q" and not parando:
                    parando = True
                    imprimir("\nParando com segurança — aguardando os workers atuais encerrarem...\n")
                    executor.parar()
                elif tecla == "d":
                    modo_painel = True
                elif tecla == "p" and not parando:
                    imprimir(alternar_pausa(motor, executor))
                time.sleep(0.1)
        except KeyboardInterrupt:
            imprimir("\nParando (Ctrl+C) — aguardando os workers atuais encerrarem...")
            executor.parar()
        finally:
            silenciar_console(False)
            executor.aguardar(timeout=15)
    return erro_motor[0]


def alternar_pausa(motor, executor) -> str:
    """Tecla P (sugestões 017/036): pausa ou retoma sem perder as sessões."""
    if not hasattr(motor, "pausar"):
        return ""
    if getattr(motor, "pausado", False):
        if getattr(motor, "motivo_pausa", None) == "janela":
            return "\nFora da janela de execução — a execução volta sozinha no próximo horário.\n"
        executor.chamar(motor.retomar, "usuario")
        return "\n▶️ Retomando as buscas.\n"
    executor.chamar(motor.pausar, "usuario")
    return "\n⏸️ Pausado (P retoma). As sessões continuam abertas.\n"


def _loop_painel(motor, executor, tailer, coletor, teclas, silenciar_console, esta_parando) -> Optional[bool]:
    """Mostra o painel até: o motor terminar (True), D (False = ir para linhas
    de log) ou Q (None = pedir parada)."""
    from rich.live import Live

    from app.dashboard.cli_dashboard import atualizar_layout, criar_console, montar_layout

    console = criar_console()
    tem_snapshot = hasattr(motor, "snapshot")
    layout = montar_layout(com_rodape=True, qtd_alvos=len(motor.snapshot()["alvos"]) if tem_snapshot else 0)
    silenciar_console(True)
    try:
        with Live(layout, console=console, refresh_per_second=4, screen=False):
            while executor.em_execucao():
                for linha in tailer.read_new_lines():
                    coletor.processar_linha(linha, ao_vivo=True)
                atualizar_layout(layout, coletor, _rodape(motor, esta_parando()), motor.snapshot() if tem_snapshot else None)
                tecla = teclas.ler()
                if tecla == "p":
                    alternar_pausa(motor, executor)
                if tecla == "d":
                    return False
                if tecla == "q" and not esta_parando():
                    return None
                time.sleep(0.2)
    finally:
        silenciar_console(False)
    return True


# ── Leitor de eventos (016) ──────────────────────────────────────────────

def eventos_recentes(limite: int = 30, texto: str = "", categoria: str = "") -> List:
    """Últimos eventos do log em linguagem simples, com filtro opcional."""
    registros = ler_ultimos_registros(caminho_projeto(*ARQUIVO_LOG), limite=2000)
    eventos = [traduzir(r) for r in registros]
    texto = (texto or "").strip().lower()
    if categoria:
        eventos = [e for e in eventos if e.categoria == categoria]
    if texto:
        eventos = [e for e in eventos if texto in f"{e.titulo} {e.corpo} {e.mensagem_original} {e.worker}".lower()]
    return eventos[-limite:]


def imprimir_eventos(eventos) -> None:
    from rich.table import Table

    from app.dashboard.cli_dashboard import criar_console

    cores = {"SUCESSO": "green", "ERRO": "red", "AVISO": "yellow", "REDE": "yellow", "MATRICULA": "magenta",
             "SEGURANCA": "cyan", "MONITORAMENTO": "blue", "NOTIFICACAO": "cyan"}
    tabela = Table(expand=True, show_lines=False, header_style="bold")
    tabela.add_column("Hora", width=8, no_wrap=True)
    tabela.add_column("Worker", width=6, no_wrap=True)
    tabela.add_column("Categoria", width=13, no_wrap=True)
    tabela.add_column("Evento")
    for e in eventos:
        cor = cores.get(e.categoria, "white")
        tabela.add_row(str(e.timestamp)[-8:], e.worker, f"[{cor}]{e.categoria}[/]", f"[b]{e.titulo}[/]\n[dim]{e.corpo}[/]")
    criar_console().print(tabela)


__all__ = ["acompanhar_execucao", "eventos_recentes", "imprimir_eventos", "CATEGORIAS"]
