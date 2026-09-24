"""
Executor em thread separada do MotorMatricula (asyncio) — usado pela GUI e
pelo terminal para nunca bloquear a interface (seção 37 do pedido:
"arquitetura responsiva").

Tkinter e o menu de terminal rodam num loop síncrono; o motor é assíncrono.
Este módulo é a ponte: roda `asyncio.run(motor.executar())` numa thread
dedicada e oferece um `parar()` thread-safe (via call_soon_threadsafe, a
forma correta de sinalizar um asyncio.Event a partir de outra thread).
"""
from __future__ import annotations

import asyncio
import threading
from typing import Callable, Optional

from app.core.engine import MotorMatricula


class ExecutorMotor:
    def __init__(self, motor: MotorMatricula, ao_finalizar: Optional[Callable[[Optional[Exception]], None]] = None):
        self.motor = motor
        self.ao_finalizar = ao_finalizar
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._erro: Optional[Exception] = None
        self._parada_pedida = False

    def iniciar(self) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("O motor já está em execução.")
        self._thread = threading.Thread(target=self._rodar, name="MotorMatricula", daemon=True)
        self._thread.start()
        from app.core import auditoria  # trilha de ações do usuário (062)
        m = self.motor
        if getattr(m, "demo", False):
            auditoria.registrar("execucao_iniciada", modo=getattr(m, "modo", None), dry_run=True, demo=True,
                                num_workers=getattr(m, "num_workers", None), disciplinas=len(getattr(m, "alvos_ativos", {}) or {}),
                                execucao_id=getattr(m, "execucao_id", None), detalhe="demonstração")
        else:
            auditoria.registrar_inicio({"modo": getattr(m, "modo", None), "dry_run": getattr(m, "dry_run", True),
                                        "num_workers": getattr(m, "num_workers", None)},
                                       len(getattr(m, "alvos_ativos", {}) or {}), getattr(m, "execucao_id", None))

    def _rodar(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            if self._parada_pedida:
                # "Parar" chegou antes de o loop existir (ex: Q/Parar logo após
                # Iniciar) — antes esse pedido era perdido e o motor seguia rodando.
                self._loop.call_soon(self.motor.parar)
            self._loop.run_until_complete(self.motor.executar())
        except Exception as e:  # nunca deixa uma exceção matar a thread silenciosamente
            self._erro = e
        finally:
            try:
                self._loop.close()
            except Exception:
                pass
            if self.ao_finalizar:
                self.ao_finalizar(self._erro)

    def parar(self) -> None:
        """Seguro para chamar da thread principal (GUI/terminal) enquanto o
        motor roda na thread de fundo."""
        if not self._parada_pedida and self._thread and self._thread.is_alive():
            from app.core import auditoria
            auditoria.registrar("execucao_parada", execucao_id=getattr(self.motor, "execucao_id", None))
        self._parada_pedida = True
        if self._loop and self._thread and self._thread.is_alive():
            self._loop.call_soon_threadsafe(self.motor.parar)

    def chamar(self, funcao, *args) -> None:
        """Executa `funcao(*args)` dentro do loop do motor (thread-safe), para
        pausar/retomar e mudar disciplinas com a execução em andamento. Antes
        de o loop existir, chama direto (o motor só guarda a intenção)."""
        if self._loop and self._thread and self._thread.is_alive() and self._loop.is_running():
            self._loop.call_soon_threadsafe(funcao, *args)
        else:
            funcao(*args)

    def em_execucao(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def aguardar(self, timeout: Optional[float] = None) -> None:
        if self._thread:
            self._thread.join(timeout=timeout)
