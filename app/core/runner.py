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

    def iniciar(self) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("O motor já está em execução.")
        self._thread = threading.Thread(target=self._rodar, name="MotorMatricula", daemon=True)
        self._thread.start()

    def _rodar(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
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
        if self._loop and self._thread and self._thread.is_alive():
            self._loop.call_soon_threadsafe(self.motor.parar)

    def em_execucao(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def aguardar(self, timeout: Optional[float] = None) -> None:
        if self._thread:
            self._thread.join(timeout=timeout)
