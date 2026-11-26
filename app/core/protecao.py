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
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
from typing import Callable, Optional

# Respostas HTTP que indicam sobrecarga/indisponibilidade do servidor (não sessão expirada).
STATUS_SOBRECARGA = {429, 502, 503, 504}


def parse_retry_after(valor: Optional[str], max_seg: float = 120.0) -> Optional[float]:
    """Interpreta o cabeçalho HTTP `Retry-After` (segundos ou data HTTP), limitado ao teto seguro."""
    if not valor:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        seg = float(texto)
    except ValueError:
        try:
            dt = parsedate_to_datetime(texto)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            seg = (dt - datetime.now(timezone.utc)).total_seconds()
        except Exception:
            return None
    if seg <= 0:
        return None
    return min(float(max_seg), max(1.0, seg))


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
        self._acordar: Optional[asyncio.Event] = None
        self._acordar_loop: Optional[asyncio.AbstractEventLoop] = None

    def _evento_acordar(self) -> asyncio.Event:
        loop = asyncio.get_running_loop()
        if self._acordar is None or self._acordar_loop is not loop:
            self._acordar = asyncio.Event()
            self._acordar_loop = loop
        return self._acordar

    def _notificar(self) -> None:
        ev = self._acordar
        if ev is not None:
            try:
                if self._acordar_loop is asyncio.get_running_loop():
                    ev.set()
            except RuntimeError:
                pass

    def registrar_sucesso(self) -> None:
        self.falhas_seguidas = 0
        if self.estado != "fechado":
            self.estado = "fechado"
            self.sonda = None
            self.espera_atual = self.espera_inicial
            self._notificar()
            self._ao_mudar("fechado", 0.0)

    def registrar_falha(self, retry_after: Optional[float] = None) -> None:
        if not self.ativo:
            return
        self.falhas_seguidas += 1
        espera_srv = min(self.espera_max, max(1.0, float(retry_after))) if retry_after and retry_after > 0 else None
        if self.estado == "meio_aberto":
            self.espera_atual = min(self.espera_max, self.espera_atual * 2)
            self._abrir(espera_srv)
        elif self.estado == "fechado" and self.falhas_seguidas >= self.limiar:
            self._abrir(espera_srv)
        elif self.estado == "aberto" and espera_srv is not None:
            self.reabre_em = max(self.reabre_em, time.monotonic() + espera_srv)

    def _abrir(self, espera_override: Optional[float] = None) -> None:
        self.estado = "aberto"
        self.sonda = None
        self.aberturas += 1
        espera = max(self.espera_atual, espera_override) if espera_override is not None else self.espera_atual
        self.reabre_em = time.monotonic() + espera
        self._ao_mudar("aberto", espera)

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
            ev = self._evento_acordar()
            ev.clear()
            if self.estado == "fechado":
                return
            pausa = min(0.25, max(0.01, self.segundos_para_reabrir())) if self.estado == "aberto" else 0.25
            try:
                await asyncio.wait_for(ev.wait(), timeout=pausa)
            except asyncio.TimeoutError:
                pass
