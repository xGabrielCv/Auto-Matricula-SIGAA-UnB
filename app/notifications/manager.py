"""
Gerenciador de notificações — ponto único que o motor (app/core/engine.py) chama.

Regras de ouro (seção 39 do pedido):
  1. Notificação é sempre secundária. Uma falha de Telegram/ntfy/alarme jamais
     pode parar ou atrasar o monitoramento.
  2. Todo envio é disparado como uma task assíncrona "fire-and-forget" —
     o motor nunca espera (`await`) uma notificação terminar.
  3. Um limitador de taxa (recuperado dos legados: deque de timestamps, N
     alertas por janela de tempo) evita spam caso uma vaga fique piscando
     disponível/indisponível repetidamente. Desde a seção 42 do pedido de
     continuação, o limite é POR (tipo de evento, disciplina) em vez de
     global — assim uma disciplina "piscando" vaga não consome a cota de
     outra disciplina que teve uma vaga nova de verdade. Eventos sem
     disciplina associada (ex: erro_critico) usam uma chave própria.
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any, Dict, Optional

from app.core.credentials import CredenciaisNotificacao
from app.notifications.alarm import tocar_alarme
from app.notifications.ntfy import enviar_ntfy
from app.notifications.telegram import enviar_telegram

MENSAGENS = {
    "vaga_detectada": lambda d: f"🚨 Vaga detectada em {d.get('codigo')}-{d.get('turma')} ({d.get('vagas')} vaga(s))!",
    "matricula_sucesso": lambda d: (
        f"🎉 Matrícula confirmada em {d.get('codigo')}-{d.get('turma')}!"
        if not d.get("dry_run") else f"🧪 [TESTE] Matrícula simulada com sucesso em {d.get('codigo')}-{d.get('turma')}."
    ),
    "matricula_falha": lambda d: f"❌ Tentativa de matrícula em {d.get('codigo')}-{d.get('turma')} falhou (o robô vai tentar de novo).",
    "matricula_bloqueada": lambda d: f"🛑 {d.get('codigo')}-{d.get('turma')} bloqueada pelo SIGAA (pré-requisito/choque de horário). Parando de monitorar essa disciplina.",
    "erro_critico": lambda d: f"💥 Erro crítico no worker {d.get('worker')}: {d.get('erro')}",
}


class GerenciadorNotificacoes:
    def __init__(
        self,
        eventos_ativos: Dict[str, bool],
        canais_ativos: Dict[str, bool],
        credenciais: CredenciaisNotificacao,
        limite_janela: int = 5,
        janela_seg: int = 300,
        alarme_repeticoes: int = 3,
        alarme_duracao_seg: int = 20,
        logger: Optional[logging.Logger] = None,
    ):
        self.eventos_ativos = eventos_ativos
        self.canais_ativos = canais_ativos
        self.credenciais = credenciais
        self.limite_janela = limite_janela
        self.janela_seg = janela_seg
        self.alarme_repeticoes = alarme_repeticoes
        self.alarme_duracao_seg = alarme_duracao_seg
        self.log = logger or logging.getLogger("sniper")
        self._timestamps_por_chave: Dict[str, deque] = {}
        self._tarefas_em_voo: set = set()

    # erro_critico é raro e importante o suficiente pra nunca ser suprimido por
    # taxa — "eventos prioritários" (seção 42).
    EVENTOS_PRIORITARIOS = {"erro_critico"}

    def _chave_para(self, tipo: str, dados: Dict[str, Any]) -> str:
        codigo, turma = dados.get("codigo"), dados.get("turma")
        if codigo and turma:
            return f"{tipo}:{codigo}-{turma}"
        return f"{tipo}:geral"

    def _pode_notificar(self, chave: str) -> bool:
        import time
        agora = time.time()
        fila = self._timestamps_por_chave.setdefault(chave, deque())
        while fila and fila[0] < agora - self.janela_seg:
            fila.popleft()
        if len(fila) < self.limite_janela:
            fila.append(agora)
            return True
        return False

    def notificar_evento(self, tipo: str, dados: Dict[str, Any]) -> None:
        """Chamado de dentro do motor (síncrono, sem I/O). Agenda o envio real
        como uma task separada e retorna na hora."""
        if not self.eventos_ativos.get(tipo, False):
            return

        chave = self._chave_para(tipo, dados)
        if tipo not in self.EVENTOS_PRIORITARIOS and not self._pode_notificar(chave):
            self.log.info(f"🔕 Notificação de '{chave}' suprimida (limite de {self.limite_janela}/{self.janela_seg}s por disciplina/evento atingido).")
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self.log.warning("Gerenciador de notificações chamado fora de um loop assíncrono — ignorado.")
            return

        tarefa = loop.create_task(self._despachar(tipo, dados))
        self._tarefas_em_voo.add(tarefa)
        tarefa.add_done_callback(self._tarefas_em_voo.discard)

    async def _despachar(self, tipo: str, dados: Dict[str, Any]) -> None:
        gerador_msg = MENSAGENS.get(tipo)
        mensagem = gerador_msg(dados) if gerador_msg else f"Evento: {tipo} — {dados}"
        titulo = "SIGAA Sniper"

        if self.canais_ativos.get("telegram") and self.credenciais.telegram_configurado():
            await self._seguro("Telegram", enviar_telegram(self.credenciais.telegram_token, self.credenciais.telegram_chat_id, mensagem))

        if self.canais_ativos.get("ntfy") and self.credenciais.ntfy_configurado():
            await self._seguro("ntfy", enviar_ntfy(self.credenciais.ntfy_topic, titulo, mensagem, self.credenciais.ntfy_servidor))

        if self.canais_ativos.get("alarme") and tipo in ("vaga_detectada", "matricula_sucesso"):
            await self._seguro("Alarme", tocar_alarme(self.alarme_repeticoes, self.alarme_duracao_seg))

    async def _seguro(self, nome_canal: str, corrotina) -> None:
        """Envolve qualquer canal: loga a falha e segue em frente, nunca propaga."""
        try:
            await corrotina
        except Exception as e:
            self.log.warning(f"⚠️ Falha ao enviar notificação via {nome_canal} (monitoramento continua): {repr(e)}")
