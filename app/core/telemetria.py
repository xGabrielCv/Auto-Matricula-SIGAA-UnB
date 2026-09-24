"""
Telemetria do motor em memória (Fase 2: sugestões 019, 026, 027, 030, 031, 055, 056).

Antes, tudo o que os painéis mostravam era reconstruído lendo o TEXTO do log
(app/dashboard/metrics.py): mudar uma frase no motor quebrava o painel sem
erro, e o estado de cada disciplina/worker só podia ser adivinhado.

Agora o próprio motor registra aqui o que acontece, nos mesmos pontos em que
já escrevia o log. As interfaces (Web, GUI, terminal) leem um `snapshot()` —
cópia pronta para exibir, protegida por lock, porque o motor roda numa thread
e as telas em outra.

Nada aqui faz I/O nem guarda dados sensíveis: só contagens, tempos e códigos
de disciplina.
"""
from __future__ import annotations

import threading
import time
from collections import Counter, deque
from typing import Any, Deque, Dict, List, Optional

# Limites superiores (ms) das faixas do histograma de latência; a última faixa é "acima de 2000".
FAIXAS_LATENCIA_MS = [100, 250, 500, 1000, 2000]

# Categorias de erro — as mesmas usadas no painel de erros agrupados e no gráfico por categoria.
CATEGORIAS_ERRO = ["timeout", "rede", "sessao", "departamento", "login", "critico", "confirmacao", "sobrecarga"]

ROTULOS_ERRO = {
    "timeout": "Tempo esgotado", "rede": "Falha de rede", "sessao": "Sessão expirada",
    "departamento": "Departamento indisponível", "login": "Falha de login", "critico": "Erro inesperado",
    "confirmacao": "Falha na confirmação", "sobrecarga": "SIGAA sobrecarregado",
}

# O que fazer quando um tipo de erro domina (painel de erros agrupados).
ACOES_ERRO = {
    "timeout": "O SIGAA está demorando para responder. Se for constante, aumente o timeout ou use um perfil de carga mais leve.",
    "rede": "Confira sua conexão com a internet. Rode o Diagnóstico → Testar conectividade em camadas.",
    "sessao": "O SIGAA encerrou a sessão; o programa entra de novo sozinho. Muitas seguidas podem indicar excesso de workers.",
    "departamento": "A busca no departamento não abriu: fora do período de matrícula extraordinária ou código de departamento errado.",
    "login": "Confira matrícula e senha na aba Credenciais. Se estiverem certas, o SIGAA pode estar fora do ar.",
    "critico": "Erro não previsto. Veja os detalhes na Central de Logs e, se repetir, gere um diagnóstico.",
    "confirmacao": "A tela de confirmação do SIGAA não veio como esperado. Veja o dump de debug em logs/.",
    "sobrecarga": "O SIGAA respondeu que está sobrecarregado (HTTP 429/502/503/504). O programa reduz o ritmo sozinho; "
                  "se persistir, use um perfil de carga mais leve.",
}

# Estados possíveis de uma disciplina (sugestão 019), na ordem em que aparecem na vida de um alvo.
ESTADOS_ALVO = {
    "aguardando": "Aguardando login",
    "buscando": "Buscando",
    "sem_vagas": "Sem vagas",
    "vaga": "Vaga vista",
    "tentando": "Tentando matricular",
    "matriculada": "Matriculada",
    "simulada": "Matrícula simulada (DRY RUN)",
    "bloqueada": "Bloqueada pelo SIGAA",
    "falha": "Tentativa falhou (tentando de novo)",
    "departamento_indisponivel": "Departamento indisponível",
    "dispensada": "Dispensada (outra turma do grupo foi garantida)",
    "removida": "Removida durante a execução",
}
ESTADOS_FINAIS_ALVO = {"matriculada", "simulada", "bloqueada", "dispensada", "removida"}

# Estados possíveis de um worker (sugestão 055).
ESTADOS_WORKER = {
    "iniciando": "Iniciando", "logando": "Fazendo login", "logado": "Logado", "preparando": "Preparando busca",
    "buscando": "Buscando", "tentando": "Tentando matricular", "aguardando": "Aguardando após falha",
    "reiniciando": "Reiniciando conexão", "encerrado": "Encerrado", "contido": "Aguardando o SIGAA se recuperar",
    "pausado": "Pausado", "fila_login": "Na fila do login",
}


def _percentil(valores: List[float], p: float) -> Optional[float]:
    if not valores:
        return None
    ordenados = sorted(valores)
    k = (len(ordenados) - 1) * p
    baixo, alto = int(k), min(int(k) + 1, len(ordenados) - 1)
    return ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * (k - baixo)


class Telemetria:
    """Agregados da execução, amostrados a cada segundo em pontos de série temporal."""

    def __init__(self, max_pontos: int = 3600, max_mudancas_vagas: int = 500):
        self._lock = threading.Lock()
        self.inicio = time.time()
        # Acumuladores do segundo corrente (viram um ponto em amostrar()).
        self._lat_seg: List[float] = []
        self._req_seg = 0
        self._erros_seg: Counter = Counter()
        self.pontos: Deque[Dict[str, Any]] = deque(maxlen=max_pontos)
        # Totais da execução.
        self.requisicoes = 0
        self.histograma = [0] * (len(FAIXAS_LATENCIA_MS) + 1)
        self._lat_soma = 0.0
        self._lat_qtd = 0
        self._lat_min: Optional[float] = None
        self._lat_max: Optional[float] = None
        self._lat_recentes: Deque[float] = deque(maxlen=100)
        self.erros: Counter = Counter()
        self.erros_detalhe: Dict[str, Dict[str, Any]] = {}
        self.vagas_vistas = 0
        self.ultima_vaga: Optional[Dict[str, Any]] = None
        # Mudanças de quantidade de vagas por disciplina: {chave: deque[(t, vagas)]}.
        self._max_mudancas = max_mudancas_vagas
        self.vagas_series: Dict[str, Deque] = {}

    # ── registro (chamado pelo motor) ─────────────────────────────────────

    def registrar_requisicao(self, latencia_ms: Optional[float] = None) -> None:
        with self._lock:
            self.requisicoes += 1
            self._req_seg += 1
            if latencia_ms is None:
                return
            self._lat_seg.append(latencia_ms)
            self._lat_recentes.append(latencia_ms)
            self._lat_soma += latencia_ms
            self._lat_qtd += 1
            self._lat_min = latencia_ms if self._lat_min is None else min(self._lat_min, latencia_ms)
            self._lat_max = latencia_ms if self._lat_max is None else max(self._lat_max, latencia_ms)
            for i, limite in enumerate(FAIXAS_LATENCIA_MS):
                if latencia_ms < limite:
                    self.histograma[i] += 1
                    break
            else:
                self.histograma[-1] += 1

    def registrar_erro(self, categoria: str, detalhe: str = "") -> None:
        agora = time.time()
        with self._lock:
            self.erros[categoria] += 1
            self._erros_seg[categoria] += 1
            info = self.erros_detalhe.setdefault(categoria, {"primeira": agora, "ultima": agora, "ultimo_detalhe": ""})
            info["ultima"] = agora
            if detalhe:
                info["ultimo_detalhe"] = detalhe[:300]

    def registrar_vagas(self, chave: str, vagas: int) -> None:
        agora = time.time()
        with self._lock:
            serie = self.vagas_series.setdefault(chave, deque(maxlen=self._max_mudancas))
            if not serie or serie[-1][1] != vagas:
                serie.append((agora, vagas))
            if vagas > 0:
                self.vagas_vistas += 1
                self.ultima_vaga = {"chave": chave, "vagas": vagas, "quando": agora}

    def amostrar(self, agora: Optional[float] = None) -> None:
        """Fecha o segundo corrente num ponto da série (chamado pelo motor a cada ~1 s)."""
        agora = agora or time.time()
        with self._lock:
            self.pontos.append({
                "t": round(agora, 3), "req": self._req_seg,
                "p50": _percentil(self._lat_seg, 0.5), "p95": _percentil(self._lat_seg, 0.95),
                "erros": dict(self._erros_seg),
            })
            self._lat_seg = []
            self._req_seg = 0
            self._erros_seg = Counter()

    # ── leitura (chamado pelas interfaces) ────────────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            pontos = list(self.pontos)
            ultimos = pontos[-5:]
            return {
                "inicio": self.inicio,
                "requisicoes": self.requisicoes,
                "rps_atual": (sum(p["req"] for p in ultimos) / len(ultimos)) if ultimos else None,
                "latencia": {
                    "media": (self._lat_soma / self._lat_qtd) if self._lat_qtd else None,
                    "recente": (sum(self._lat_recentes) / len(self._lat_recentes)) if self._lat_recentes else None,
                    "min": self._lat_min, "max": self._lat_max, "amostras": self._lat_qtd,
                },
                "histograma": {"limites_ms": list(FAIXAS_LATENCIA_MS), "contagens": list(self.histograma)},
                "erros": {c: {"total": self.erros[c], **self.erros_detalhe.get(c, {})} for c in self.erros},
                "vagas_vistas": self.vagas_vistas,
                "ultima_vaga": dict(self.ultima_vaga) if self.ultima_vaga else None,
                "vagas_series": {k: list(v) for k, v in self.vagas_series.items()},
                "pontos": pontos,
            }
