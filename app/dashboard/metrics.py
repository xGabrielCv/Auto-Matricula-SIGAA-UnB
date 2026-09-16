"""
Motor de métricas do dashboard — usado tanto pelo painel de terminal (rich)
quanto pela aba de dashboard da GUI (Tkinter). Uma única implementação, dois
jeitos de exibir (seção 50 do pedido: não duplicar lógica).

Esta é uma reescrita auditada de legacy/base_v4.0/dashboard_sniper.py.
Problemas reais encontrados nessa versão e como foram corrigidos aqui:

  1. LATÊNCIA INCOMPLETA: o código antigo só extraía latência das linhas
     "📉 Sem vagas (Xms)". As linhas "🚨 VAGA DETECTADA (Xms)" também têm o
     tempo de resposta, mas eram ignoradas — a latência mostrada excluía
     sistematicamente as respostas mais "importantes" (quando havia vaga).
     CORRIGIDO: ambos os padrões alimentam a mesma estatística de latência.

  2. RPS SUBESTIMADO: requisições que terminaram em falha de rede
     ("🔌 Falha de rede") ou erro crítico não eram contadas como requisição
     alguma, então "Total Reqs"/RPS eram um PISO, não uma contagem real,
     sem isso ficar visível para quem lia o painel.
     CORRIGIDO: essas linhas agora contam para o total de requisições
     (sem latência associada, já que a requisição falhou).

  3. MÉDIA HISTÓRICA CONTAMINADA ENTRE EXECUÇÕES: como o arquivo de log é
     reaberto em modo "append", reiniciar o bot sem apagar o log fazia o
     "tempo decorrido" (e portanto RPS/BPS médios e uptime do bot) incluir
     minutos ou horas de uma execução anterior já encerrada.
     CORRIGIDO: o motor agora grava uma linha marcador "SESSAO_INICIADA"
     a cada chamada de MotorMatricula.executar(); o dashboard reseta as
     métricas de sessão sempre que vê um novo marcador.

  4. MÉTRICAS SEM DADOS SUFICIENTES: em vez de mostrar "0ms" ou "0.0 req/s"
     como se fossem valores reais quando não há dados, os campos ficam
     marcados como "sem dados" (ver `disponivel` nos dicts retornados).
"""
from __future__ import annotations

import os
import re
import time
from collections import deque
from datetime import datetime
from typing import Dict, Optional

MARCADOR_SESSAO = "SESSAO_INICIADA"


class LogTailer:
    """Leitura incremental do log JSON Lines, tolerante à rotação do arquivo
    (detecta troca de inode, como quando o RotatingFileHandler rotaciona)."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.f_obj = None
        self.inode = -1
        self.buffer = ""

    def read_new_lines(self):
        try:
            stat = os.stat(self.filepath)
            if stat.st_ino != self.inode:
                if self.f_obj:
                    self.f_obj.close()
                self.f_obj = open(self.filepath, "r", encoding="utf-8")
                self.inode = stat.st_ino
                self.buffer = ""
        except FileNotFoundError:
            return []

        if not self.f_obj:
            return []

        linhas_completas = []
        while True:
            pedaco = self.f_obj.readline()
            if not pedaco:
                break
            self.buffer += pedaco
            if self.buffer.endswith("\n"):
                linhas_completas.append(self.buffer)
                self.buffer = ""
        return linhas_completas


class ColetorMetricas:
    """Processa linhas de log e mantém o estado agregado do dashboard."""

    def __init__(self):
        self.stats = {
            "start_time_log": None,
            "last_time_log": None,
            "total_buscas": 0,
            "total_reqs": 0,
            "total_reqs_falha_rede": 0,
            "erros_totais": 0,
            "vagas_encontradas": 0,
            "soma_latencia": 0,
            "qtd_latencia": 0,
            "min_latencia": float("inf"),
            "max_latencia": 0,
            "latencias_recentes": deque(maxlen=100),
            "workers": {},
            "log_erros": deque(maxlen=7),
            "registro_vagas": deque(maxlen=10),
            "modo": None,
            "historico_vagas": {},  # seção 43: {"FGA0211-01": deque([(hora, vagas), ...], maxlen=30)}
        }
        self.rps_window: deque = deque()
        self.bps_window: deque = deque()
        self.health_req_window: deque = deque()
        self.health_err_window: deque = deque()
        self.dashboard_start = time.time()
        self._ultima_busca_por_worker: Dict[str, str] = {}  # seção 43: pra saber a que disciplina um "Sem vagas" pertence

    def _resetar_sessao(self):
        """Chamado quando um novo marcador de início de sessão é encontrado —
        evita misturar estatísticas de execuções diferentes do bot."""
        inicio_dashboard = self.dashboard_start
        self.__init__()
        self.dashboard_start = inicio_dashboard

    def processar_linha(self, linha: str, ao_vivo: bool) -> None:
        try:
            import json
            registro = json.loads(linha)
        except (json.JSONDecodeError, ValueError):
            return

        msg = registro.get("message", "")
        worker = registro.get("worker", "MAIN")
        nivel = registro.get("level", "INFO")
        log_time_str = registro.get("timestamp", "")

        if MARCADOR_SESSAO in msg:
            self._resetar_sessao()
            return

        agora_real = time.time()
        event_ts = agora_real
        try:
            if log_time_str:
                dt = datetime.strptime(log_time_str, "%Y-%m-%d %H:%M:%S")
                event_ts = dt.timestamp()
                if self.stats["start_time_log"] is None:
                    self.stats["start_time_log"] = event_ts
                self.stats["last_time_log"] = event_ts
        except ValueError:
            pass

        ts_fila = agora_real if ao_vivo else event_ts

        if worker != "MAIN" and worker not in self.stats["workers"]:
            self.stats["workers"][worker] = {
                "ultima_acao": "Aguardando...",
                "latencia": 0,
                "timestamp": event_ts,
                "buscas_feitas": 0,
                "erros_count": 0,
            }

        # 1. ERROS E ALERTAS
        if nivel in ("WARNING", "ERROR", "CRITICAL") and "VAGA DETECTADA" not in msg and "DRY RUN" not in msg:
            self.stats["erros_totais"] += 1
            if ao_vivo:
                self.health_err_window.append(ts_fila)
            if worker in self.stats["workers"]:
                self.stats["workers"][worker]["erros_count"] += 1
            if "Timeout" not in msg:
                self.stats["log_erros"].appendleft(f"[{log_time_str}] {worker}: {msg}")
            elif worker in self.stats["workers"]:
                self.stats["workers"][worker].update({"ultima_acao": "Timeout / Rede lenta", "timestamp": event_ts})

        # 2. CONTAGEM DE REQUISIÇÕES (RPS) — inclui falhas de rede/erro crítico (correção #2)
        eh_requisicao = ("Sem vagas" in msg) or ("VAGA DETECTADA" in msg) or ("Timeout" in msg)
        eh_falha_rede = ("Falha de rede" in msg) or ("Erro crítico inesperado" in msg)
        if eh_requisicao or eh_falha_rede:
            self.stats["total_reqs"] += 1
            if eh_falha_rede:
                self.stats["total_reqs_falha_rede"] += 1
            if ao_vivo:
                self.rps_window.append(ts_fila)
                self.health_req_window.append(ts_fila)

        # 3. BUSCAS (BPS)
        if "🔍 Buscando" in msg:
            self.stats["total_buscas"] += 1
            if ao_vivo:
                self.bps_window.append(ts_fila)
            alvo = re.search(r"Buscando ([A-Z0-9-]+)", msg)
            alvo_str = alvo.group(1) if alvo else "..."
            if worker in self.stats["workers"]:
                self.stats["workers"][worker].update({"ultima_acao": f"Buscando {alvo_str}", "timestamp": event_ts})
                self.stats["workers"][worker]["buscas_feitas"] += 1
            if alvo:
                self._ultima_busca_por_worker[worker] = alvo_str

        # 4. LATÊNCIA — agora captura "Sem vagas" E "VAGA DETECTADA" (correção #1)
        lat_val = None
        if "📉 Sem vagas" in msg or "🚨 VAGA DETECTADA" in msg:
            m = re.search(r"\((\d+)ms\)", msg)
            if m:
                lat_val = int(m.group(1))

        if lat_val is not None:
            self.stats["soma_latencia"] += lat_val
            self.stats["qtd_latencia"] += 1
            self.stats["min_latencia"] = min(self.stats["min_latencia"], lat_val)
            self.stats["max_latencia"] = max(self.stats["max_latencia"], lat_val)
            if ao_vivo:
                self.stats["latencias_recentes"].append(lat_val)
            if worker in self.stats["workers"]:
                cor = "verde" if lat_val <= 230 else "amarelo" if lat_val < 400 else "vermelho"
                if "📉 Sem vagas" in msg:
                    self.stats["workers"][worker].update({"ultima_acao": "Sem vagas", "timestamp": event_ts})
                self.stats["workers"][worker].update({"latencia": lat_val, "cor_lat": cor})

            if "📉 Sem vagas" in msg:
                disciplina = self._ultima_busca_por_worker.get(worker)
                if disciplina:
                    self._registrar_historico_vaga(disciplina, log_time_str, 0)

        # 5. VAGAS E SUCESSO
        if "🚨 VAGA DETECTADA" in msg:
            self.stats["vagas_encontradas"] += 1
            alvo = re.search(r"-> ([A-Z0-9-]+)", msg)
            alvo_str = alvo.group(1) if alvo else "Disciplina"
            vagas_qtd = re.search(r"\((\d+) vaga", msg)
            self._registrar_historico_vaga(alvo_str, log_time_str, int(vagas_qtd.group(1)) if vagas_qtd else 1)
            self.stats["registro_vagas"].appendleft(f"[{log_time_str}] {worker} VAGA DETECTADA: {alvo_str}")
            if worker in self.stats["workers"]:
                self.stats["workers"][worker].update({"ultima_acao": "🚨 ACHOU VAGA!", "timestamp": event_ts})
        elif "SUCESSO ABSOLUTO" in msg or "DRY RUN SUCESSO" in msg:
            self.stats["registro_vagas"].appendleft(f"[{log_time_str}] {worker} MATRICULADO COM SUCESSO!")
            if worker in self.stats["workers"]:
                self.stats["workers"][worker].update({"ultima_acao": "🎉 MATRICULADO!", "timestamp": event_ts})

    def _registrar_historico_vaga(self, disciplina: str, hora: str, vagas: int) -> None:
        """Seção 43: histórico por disciplina, limitado (30 entradas) pra nunca crescer sem parar."""
        if disciplina not in self.stats["historico_vagas"]:
            self.stats["historico_vagas"][disciplina] = deque(maxlen=30)
        historico = self.stats["historico_vagas"][disciplina]
        # Evita repetir a mesma leitura de novo (ex: "0 vagas" 50x seguidas) — só
        # registra quando o valor muda, como no exemplo do pedido (10:30/10:32/10:34).
        if not historico or historico[-1][1] != vagas:
            historico.append((hora, vagas))

    def _aparar_janela(self, janela: deque, segundos: int, agora: float):
        while janela and janela[0] < agora - segundos:
            janela.popleft()

    def snapshot(self) -> Dict:
        """Retorna todas as métricas prontas para exibição, já marcando quais
        não têm dados suficientes (`disponivel: False`) em vez de mostrar zero."""
        agora = time.time()
        self._aparar_janela(self.rps_window, 5, agora)
        self._aparar_janela(self.bps_window, 5, agora)
        self._aparar_janela(self.health_err_window, 30, agora)
        self._aparar_janela(self.health_req_window, 30, agora)

        s = self.stats
        tem_log = s["start_time_log"] is not None

        rps_atual = len(self.rps_window) / 5.0
        bps_atual = len(self.bps_window) / 5.0

        avg_rps = avg_bps = None
        if tem_log and s["last_time_log"] > s["start_time_log"]:
            decorrido = s["last_time_log"] - s["start_time_log"]
            avg_rps = s["total_reqs"] / decorrido
            avg_bps = s["total_buscas"] / decorrido

        avg_lat_100 = (sum(s["latencias_recentes"]) / len(s["latencias_recentes"])) if s["latencias_recentes"] else None
        avg_lat_total = (s["soma_latencia"] / s["qtd_latencia"]) if s["qtd_latencia"] > 0 else None
        min_lat = s["min_latencia"] if s["min_latencia"] != float("inf") else None
        max_lat = s["max_latencia"] if s["qtd_latencia"] > 0 else None

        saude = self._calcular_saude()

        return {
            "tem_dados": tem_log,
            "rps_atual": rps_atual,
            "bps_atual": bps_atual,
            "avg_rps": avg_rps,
            "avg_bps": avg_bps,
            "latencia_recente_ms": avg_lat_100,
            "latencia_media_ms": avg_lat_total,
            "latencia_min_ms": min_lat,
            "latencia_max_ms": max_lat,
            "saude": saude,
            "total_reqs": s["total_reqs"],
            "total_reqs_falha_rede": s["total_reqs_falha_rede"],
            "total_buscas": s["total_buscas"],
            "vagas_encontradas": s["vagas_encontradas"],
            "erros_totais": s["erros_totais"],
            "uptime_bot_seg": (agora - s["start_time_log"]) if tem_log else None,
            "uptime_dashboard_seg": agora - self.dashboard_start,
            "workers": dict(s["workers"]),
            "registro_vagas": list(s["registro_vagas"]),
            "log_erros": list(s["log_erros"]),
            "historico_vagas": {k: list(v) for k, v in s["historico_vagas"].items()},
            "workers_com_alerta": self._detectar_workers_parados(s["workers"], agora),
        }

    LIMIAR_WORKER_PARADO_SEG = 30  # seção 38: acima disso, um worker que não fez nada é anômalo

    def _detectar_workers_parados(self, workers: dict, agora: float) -> list:
        """Seção 38: detecção de degradação — worker sem nenhuma atividade
        recente pode estar travado. Não é uma garantia (pode só estar entre
        ciclos com poucas disciplinas), mas é um sinal honesto pra investigar."""
        alertas = []
        for w_id, w in workers.items():
            ocioso = agora - w["timestamp"]
            if ocioso > self.LIMIAR_WORKER_PARADO_SEG:
                alertas.append(f"{w_id} sem atividade há {ocioso:.0f}s (última ação: {w['ultima_acao']})")
        return alertas

    def _calcular_saude(self) -> Dict:
        req_recentes = len(self.health_req_window)
        if req_recentes == 0:
            return {"status": "aguardando_trafego", "taxa_erro": None}
        taxa_erro = len(self.health_err_window) / req_recentes
        if taxa_erro > 0.30:
            status = "critico"
        elif taxa_erro > 0.05:
            status = "degradado"
        else:
            status = "estavel"
        return {"status": status, "taxa_erro": taxa_erro}


def formatar_uptime(segundos: Optional[float]) -> str:
    if segundos is None or segundos < 0:
        return "sem dados"
    m, s = divmod(int(segundos), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"
