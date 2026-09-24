"""
Proteção de carga do motor (Fase 4 — sugestões 071, 073 e 039).

  - LimitadorTaxa  → teto de buscas por segundo para o PROGRAMA INTEIRO (token
    bucket), qualquer que seja o número de workers. As etapas de matrícula
    (seleção/confirmação) NÃO passam por ele: uma vaga encontrada nunca espera.
  - Semáforo de logins (073) → no máximo N logins ao mesmo tempo no CAS (em
    vez de 20 workers entrando todos no mesmo instante).
  - Disjuntor (039) → quando o SIGAA dá sinais de sobrecarga ou queda (tempo
    esgotado, falha de rede, HTTP 429/502/503/504 seguidos), TODOS os workers
    param de buscar; depois de uma espera, só um worker faz uma busca de teste
    ("meio aberto"). Deu certo → volta ao normal. Falhou → espera o dobro.
    Antes, cada falha levava a um relogin imediato: com o SIGAA fora do ar,
    20 workers ficavam tentando login em laço.

As primitivas asyncio são criadas só dentro do loop do motor (nunca no
__init__), evitando o problema de "event loop diferente" em Python 3.9.
"""
from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional

# Respostas HTTP que indicam sobrecarga/indisponibilidade do servidor (não sessão expirada).
STATUS_SOBRECARGA = {429, 502, 503, 504}


class LimitadorTaxa:
    """Token bucket: no máximo `por_segundo` aquisições por segundo, com
    pequena rajada de até 1 segundo de tokens. `por_segundo <= 0` desliga."""

    def __init__(self, por_segundo: float):
        self.por_segundo = float(por_segundo or 0)
        self._tokens = max(1.0, self.por_segundo)
        self._ultimo = time.monotonic()
        self._lock: Optional[asyncio.Lock] = None
        self.esperas = 0  # quantas vezes alguém precisou esperar (telemetria)

    @property
    def ativo(self) -> bool:
        return self.por_segundo > 0

    def _repor(self) -> None:
        agora = time.monotonic()
        self._tokens = min(max(1.0, self.por_segundo), self._tokens + (agora - self._ultimo) * self.por_segundo)
        self._ultimo = agora

    async def adquirir(self) -> None:
        if not self.ativo:
            return
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            self._repor()
            if self._tokens < 1:
                self.esperas += 1
                await asyncio.sleep((1 - self._tokens) / self.por_segundo)
                self._repor()
            self._tokens -= 1


class Disjuntor:
    """Fechado (normal) → aberto (ninguém busca) → meio aberto (uma busca de teste)."""

    def __init__(self, limiar_falhas: int = 8, espera_inicial_seg: float = 15.0, espera_max_seg: float = 120.0,
                 ativo: bool = True, ao_mudar: Optional[Callable[[str, float], None]] = None):
        self.ativo = ativo
        self.limiar = limiar_falhas
        self.espera_inicial = espera_inicial_seg
        self.espera_max = espera_max_seg
        self.estado = "fechado"
        self.falhas_seguidas = 0
        self.espera_atual = espera_inicial_seg
        self.reabre_em = 0.0
        self.sonda: Optional[int] = None
        self.sonda_desde = 0.0
        self.prazo_sonda_seg = 30.0  # sonda que não responde nesse prazo é substituída por outro worker
        self.aberturas = 0
        self._ao_mudar = ao_mudar or (lambda _estado, _espera: None)

    def registrar_sucesso(self) -> None:
        self.falhas_seguidas = 0
        if self.estado != "fechado":
            self.estado = "fechado"
            self.sonda = None
            self.espera_atual = self.espera_inicial
            self._ao_mudar("fechado", 0.0)

    def registrar_falha(self) -> None:
        if not self.ativo:
            return
        self.falhas_seguidas += 1
        if self.estado == "meio_aberto":
            self.espera_atual = min(self.espera_max, self.espera_atual * 2)
            self._abrir()
        elif self.estado == "fechado" and self.falhas_seguidas >= self.limiar:
            self._abrir()

    def _abrir(self) -> None:
        self.estado = "aberto"
        self.sonda = None
        self.aberturas += 1
        self.reabre_em = time.monotonic() + self.espera_atual
        self._ao_mudar("aberto", self.espera_atual)

    def segundos_para_reabrir(self) -> float:
        return max(0.0, self.reabre_em - time.monotonic()) if self.estado == "aberto" else 0.0

    async def liberar(self, worker_id: int, parado: Callable[[], bool]) -> None:
        """Espera até este worker poder buscar. No estado aberto ninguém passa;
        quando a espera vence, o primeiro worker vira a "sonda" (meio aberto)."""
        while self.ativo and not parado():
            if self.estado == "fechado":
                return
            agora = time.monotonic()
            if self.estado == "aberto" and agora >= self.reabre_em:
                self.estado = "meio_aberto"
                self.sonda, self.sonda_desde = worker_id, agora
                self._ao_mudar("meio_aberto", 0.0)
                return
            if self.estado == "meio_aberto":
                if self.sonda == worker_id:
                    return
                if agora - self.sonda_desde > self.prazo_sonda_seg:  # sonda travada em outro ponto
                    self.sonda, self.sonda_desde = worker_id, agora
                    return
            await asyncio.sleep(0.25)
