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
from typing import Dict, List, Optional

MARCADOR_SESSAO = "SESSAO_INICIADA"

# Evento estruturado do log (sugestão 053) → tipo usado pelo coletor.
_TIPO_POR_EVENTO = {
    "sessao_iniciada": "sessao", "busca": "busca", "sem_vagas": "sem_vagas", "vaga_detectada": "vaga",
    "timeout": "timeout", "falha_rede": "falha_rede", "erro_critico": "falha_rede",
    "matricula_sucesso": "sucesso", "dry_run_interrompido": "dry_run",
}


def classificar(registro: dict) -> Optional[str]:
    """Tipo do evento: pelo campo `evento` quando existe (logs novos) ou pelo
    texto da mensagem (logs gravados antes da sugestão 053) — assim mudar uma
    frase no motor não quebra mais o painel, e logs antigos continuam legíveis."""
    evento = registro.get("evento")
    if evento:
        return _TIPO_POR_EVENTO.get(evento, "outro")
    msg = registro.get("message", "")
    if MARCADOR_SESSAO in msg:
        return "sessao"
    if "🔍 Buscando" in msg:
        return "busca"
    if "📉 Sem vagas" in msg:
        return "sem_vagas"
    if "🚨 VAGA DETECTADA" in msg:
        return "vaga"
    if "Timeout" in msg:
        return "timeout"
    if "Falha de rede" in msg or "Erro crítico inesperado" in msg:
        return "falha_rede"
    if "SUCESSO ABSOLUTO" in msg or "DRY RUN SUCESSO" in msg:
        return "sucesso"
    if "DRY RUN" in msg:
        return "dry_run"
    return None


def _alvo(registro: dict, padrao: Optional[str] = None) -> Optional[str]:
    if registro.get("codigo") and registro.get("turma"):
        return f"{registro['codigo']}-{registro['turma']}"
    if padrao is None:
        return None
    m = re.search(padrao, registro.get("message", ""))
    return m.group(1) if m else None


def _latencia(registro: dict) -> Optional[int]:
    if isinstance(registro.get("latencia_ms"), (int, float)):
        return int(registro["latencia_ms"])
    m = re.search(r"\((\d+)ms\)", registro.get("message", ""))
    return int(m.group(1)) if m else None


class LogTailer:
    """Leitura incremental do log JSON Lines, tolerante à rotação do arquivo
    (detecta troca de inode ou arquivo menor que a posição já lida, como quando
    o RotatingFileHandler rotaciona).

    BUG REAL CORRIGIDO (Windows): a versão anterior mantinha o arquivo aberto
    entre uma leitura e outra. No Windows, um arquivo aberto por outro handle
    não pode ser renomeado — então, com a aba Dashboard/Logs aberta, o
    RotatingFileHandler falhava ao rotacionar (PermissionError/WinError 32) a
    cada nova linha assim que o log atingia o tamanho máximo: o log parava de
    ser gravado e o console era inundado de tracebacks "--- Logging error ---".
    Agora o arquivo é aberto, lido a partir da última posição e fechado a cada
    chamada — nunca fica um handle pendurado impedindo a rotação.
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.inode = -1
        self.posicao = 0
        self.buffer = b""

    def pular_para_o_fim(self) -> None:
        """Ignora o que já está no arquivo (execuções anteriores) — a leitura
        passa a devolver só as linhas escritas daqui em diante."""
        try:
            stat = os.stat(self.filepath)
        except FileNotFoundError:
            return
        self.inode = stat.st_ino
        self.posicao = stat.st_size
        self.buffer = b""

    def read_new_lines(self):
        try:
            stat = os.stat(self.filepath)
        except FileNotFoundError:
            return []

        if stat.st_ino != self.inode or stat.st_size < self.posicao:
            # Arquivo novo (primeira leitura ou rotação): recomeça do início.
            self.inode = stat.st_ino
            self.posicao = 0
            self.buffer = b""

        if stat.st_size == self.posicao:
            return []

        try:
            with open(self.filepath, "rb") as f:
                f.seek(self.posicao)
                dados = f.read()
                self.posicao = f.tell()
        except OSError:
            return []

        self.buffer += dados
        *completas, self.buffer = self.buffer.split(b"\n")
        # rstrip(b"\r"): no Windows o log é gravado em modo texto ("\r\n"); a
        # versão antiga lia em modo texto e já recebia só "\n" — mantém igual.
        return [linha.rstrip(b"\r").decode("utf-8", errors="replace") + "\n" for linha in completas]


def ler_ultimos_registros(caminho: str, limite: int = 500, bloco: int = 1024 * 1024) -> List[dict]:
    """Os últimos `limite` registros do log JSON Lines, lendo só o final do
    arquivo (o log pode ter dezenas de MB). Linhas inválidas são ignoradas."""
    import json
    try:
        with open(caminho, "rb") as f:
            f.seek(0, os.SEEK_END)
            tamanho = f.tell()
            f.seek(max(0, tamanho - bloco))
            dados = f.read()
    except OSError:
        return []
    linhas = dados.split(b"\n")
    if tamanho > bloco:
        linhas = linhas[1:]  # a primeira linha do bloco pode ter vindo cortada
    registros = []
    for linha in linhas[-(limite * 2):]:
        try:
            registro = json.loads(linha.rstrip(b"\r").decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(registro, dict):
            registros.append(registro)
    return registros[-limite:]


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

        tipo = classificar(registro)
        if tipo == "sessao":
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
        if nivel in ("WARNING", "ERROR", "CRITICAL") and tipo not in ("vaga", "sucesso", "dry_run"):
            self.stats["erros_totais"] += 1
            if ao_vivo:
                self.health_err_window.append(ts_fila)
            if worker in self.stats["workers"]:
                self.stats["workers"][worker]["erros_count"] += 1
            if tipo != "timeout":
                self.stats["log_erros"].appendleft(f"[{log_time_str}] {worker}: {msg}")
            elif worker in self.stats["workers"]:
                self.stats["workers"][worker].update({"ultima_acao": "Timeout / Rede lenta", "timestamp": event_ts})

        # 2. CONTAGEM DE REQUISIÇÕES (RPS) — inclui falhas de rede/erro crítico (correção #2)
        eh_requisicao = tipo in ("sem_vagas", "vaga", "timeout")
        eh_falha_rede = tipo == "falha_rede"
        if eh_requisicao or eh_falha_rede:
            self.stats["total_reqs"] += 1
            if eh_falha_rede:
                self.stats["total_reqs_falha_rede"] += 1
            if ao_vivo:
                self.rps_window.append(ts_fila)
                self.health_req_window.append(ts_fila)

        # 3. BUSCAS (BPS)
        if tipo == "busca":
            self.stats["total_buscas"] += 1
            if ao_vivo:
                self.bps_window.append(ts_fila)
            alvo = _alvo(registro, r"Buscando ([A-Z0-9-]+)")
            alvo_str = alvo or "..."
            if worker in self.stats["workers"]:
                self.stats["workers"][worker].update({"ultima_acao": f"Buscando {alvo_str}", "timestamp": event_ts})
                self.stats["workers"][worker]["buscas_feitas"] += 1
            if alvo:
                self._ultima_busca_por_worker[worker] = alvo_str

        # 4. LATÊNCIA — agora captura "Sem vagas" E "VAGA DETECTADA" (correção #1)
        lat_val = _latencia(registro) if tipo in ("sem_vagas", "vaga") else None

        if lat_val is not None:
            self.stats["soma_latencia"] += lat_val
            self.stats["qtd_latencia"] += 1
            self.stats["min_latencia"] = min(self.stats["min_latencia"], lat_val)
            self.stats["max_latencia"] = max(self.stats["max_latencia"], lat_val)
            if ao_vivo:
                self.stats["latencias_recentes"].append(lat_val)
            if worker in self.stats["workers"]:
                cor = "verde" if lat_val <= 230 else "amarelo" if lat_val < 400 else "vermelho"
                if tipo == "sem_vagas":
                    self.stats["workers"][worker].update({"ultima_acao": "Sem vagas", "timestamp": event_ts})
                self.stats["workers"][worker].update({"latencia": lat_val, "cor_lat": cor})

            if tipo == "sem_vagas":
                disciplina = _alvo(registro) or self._ultima_busca_por_worker.get(worker)
                if disciplina:
                    self._registrar_historico_vaga(disciplina, log_time_str, 0)

        # 5. VAGAS E SUCESSO
        if tipo == "vaga":
            self.stats["vagas_encontradas"] += 1
            alvo_str = _alvo(registro, r"-> ([A-Z0-9-]+)") or "Disciplina"
            if isinstance(registro.get("vagas"), int):
                qtd = registro["vagas"]
            else:
                m_qtd = re.search(r"\((\d+) vaga", msg)
                qtd = int(m_qtd.group(1)) if m_qtd else 1
            self._registrar_historico_vaga(alvo_str, log_time_str, qtd)
            self.stats["registro_vagas"].appendleft(f"[{log_time_str}] {worker} VAGA DETECTADA: {alvo_str}")
            if worker in self.stats["workers"]:
                self.stats["workers"][worker].update({"ultima_acao": "🚨 ACHOU VAGA!", "timestamp": event_ts})
        elif tipo == "sucesso":
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

    def snapshot(self, execucao_ativa: bool = True) -> Dict:
        """Retorna todas as métricas prontas para exibição, já marcando quais
        não têm dados suficientes (`disponivel: False`) em vez de mostrar zero.

        Sem execução ativa (`execucao_ativa=False`), os dados são de uma execução
        ENCERRADA: o tempo fica congelado na duração dela e não há alerta de
        worker "sem atividade" — antes o tempo seguia contando a partir do início
        do log e a tela acusava workers parados de uma execução que nem existia."""
        agora = time.time()
        self._aparar_janela(self.rps_window, 5, agora)
        self._aparar_janela(self.bps_window, 5, agora)
        self._aparar_janela(self.health_err_window, 30, agora)
        self._aparar_janela(self.health_req_window, 30, agora)

        s = self.stats
        tem_log = s["start_time_log"] is not None

        # Sem execução ativa não existe tráfego "agora": zero fixo, em vez de um valor
        # que vai caindo sozinho nos segundos seguintes à parada.
        rps_atual = len(self.rps_window) / 5.0 if execucao_ativa else 0.0
        bps_atual = len(self.bps_window) / 5.0 if execucao_ativa else 0.0

        avg_rps = avg_bps = None
        if tem_log and s["last_time_log"] > s["start_time_log"]:
            decorrido = s["last_time_log"] - s["start_time_log"]
            avg_rps = s["total_reqs"] / decorrido
            avg_bps = s["total_buscas"] / decorrido

        avg_lat_100 = (sum(s["latencias_recentes"]) / len(s["latencias_recentes"])) if s["latencias_recentes"] else None
        avg_lat_total = (s["soma_latencia"] / s["qtd_latencia"]) if s["qtd_latencia"] > 0 else None
        min_lat = s["min_latencia"] if s["min_latencia"] != float("inf") else None
        max_lat = s["max_latencia"] if s["qtd_latencia"] > 0 else None

        saude = self._calcular_saude() if execucao_ativa else {"status": "aguardando_trafego", "taxa_erro": None}

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
            "uptime_bot_seg": (((agora if execucao_ativa else (s["last_time_log"] or s["start_time_log"])) - s["start_time_log"])
                               if tem_log else None),
            "uptime_dashboard_seg": agora - self.dashboard_start,
            "workers": dict(s["workers"]),
            "registro_vagas": list(s["registro_vagas"]),
            "log_erros": list(s["log_erros"]),
            "historico_vagas": {k: list(v) for k, v in s["historico_vagas"].items()},
            "workers_com_alerta": self._detectar_workers_parados(s["workers"], agora) if execucao_ativa else [],
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


def criar_tailer_da_sessao(caminho_log: str, carregar_ultima: bool) -> "LogTailer":
    """Leitor do log de auditoria para os painéis da interface aberta agora.
    Por padrão começa do FIM (só o que acontecer nesta sessão); com
    `carregar_ultima` lê também o que já existe (dados de execuções anteriores,
    que os painéis mostram como recuperados)."""
    tailer = LogTailer(caminho_log)
    if not carregar_ultima:
        tailer.pular_para_o_fim()
    return tailer


def formatar_uptime(segundos: Optional[float]) -> str:
    if segundos is None or segundos < 0:
        return "sem dados"
    m, s = divmod(int(segundos), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"
