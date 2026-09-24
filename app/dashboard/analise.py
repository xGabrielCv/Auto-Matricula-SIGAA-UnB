"""
Análises sobre o snapshot do motor (Fase 2) — uma implementação, três telas
(Web, GUI e terminal):

  - avaliar_saude()   → sugestão 020: não só "estável/degradado", mas O PORQUÊ
                        (internet? SIGAA lento? login? departamento?);
  - agrupar_erros()   → sugestão 021: erros por tipo, com contagem, primeira/
                        última ocorrência e o que fazer;
  - descrever_fase()  → sugestão 086: "Agendado", "Fazendo login 3/8", "Monitorando"…;
  - series_grafico()  → sugestões 026/031/032: pontos por segundo reamostrados
                        para a janela pedida (o navegador nunca recebe milhares
                        de pontos a cada atualização).

Tudo aqui é leitura pura sobre dados já coletados — nada faz requisição.
"""
from __future__ import annotations

import time
from statistics import median
from typing import Any, Dict, List, Optional

from app.core.telemetria import ACOES_ERRO, CATEGORIAS_ERRO, ROTULOS_ERRO

JANELA_SAUDE_SEG = 30
LIMITE_TAXA_ERRO_ATENCAO = 0.05
LIMITE_TAXA_ERRO_CRITICO = 0.30
FATOR_LENTIDAO = 3.0  # latência recente X vezes acima da mediana da execução = "SIGAA ficou lento"


def _ultimos(pontos: List[Dict[str, Any]], segundos: int) -> List[Dict[str, Any]]:
    if not pontos:
        return []
    limite = pontos[-1]["t"] - segundos
    return [p for p in pontos if p["t"] > limite]


def avaliar_saude(snap: Optional[Dict[str, Any]], memoria_mb: Optional[float] = None) -> Dict[str, Any]:
    """Nível (aguardando/estavel/atencao/critico), um título curto, a causa
    provável em linguagem simples e os indicadores que sustentam a conclusão."""
    if not snap:
        return {"nivel": "aguardando", "titulo": "Sem execução", "causa": "Inicie uma execução para ver a saúde da conexão.",
                "indicadores": {}}
    tel = snap["telemetria"]
    recentes = _ultimos(tel["pontos"], JANELA_SAUDE_SEG)
    reqs = sum(p["req"] for p in recentes)
    erros_recentes: Dict[str, int] = {}
    for p in recentes:
        for cat, n in p["erros"].items():
            erros_recentes[cat] = erros_recentes.get(cat, 0) + n
    total_erros = sum(erros_recentes.values())
    taxa = (total_erros / reqs) if reqs else None
    p50s = [p["p50"] for p in tel["pontos"] if p["p50"] is not None]
    lat_recente = median([p["p50"] for p in recentes if p["p50"] is not None]) if any(p["p50"] is not None for p in recentes) else None
    lat_base = median(p50s) if p50s else None
    contadores = snap.get("contadores", {})
    workers_ativos = sum(1 for w in snap["workers"] if w["estado"] not in ("encerrado",))
    indicadores = {
        "latencia_recente_ms": round(lat_recente) if lat_recente is not None else None,
        "latencia_mediana_ms": round(lat_base) if lat_base is not None else None,
        "taxa_erro": round(taxa, 3) if taxa is not None else None,
        "requisicoes_janela": reqs, "erros_janela": total_erros,
        "timeouts": contadores.get("timeouts", 0), "sessoes_expiradas": contadores.get("sessoes_expiradas", 0),
        "relogins": contadores.get("relogins", 0), "falhas_rede": contadores.get("falhas_rede", 0),
        "workers_ativos": workers_ativos, "workers_total": snap.get("num_workers"), "memoria_mb": memoria_mb,
        "janela_seg": JANELA_SAUDE_SEG,
    }

    disjuntor = snap.get("disjuntor") or {}
    if disjuntor.get("estado") in ("aberto", "meio_aberto") and snap.get("fase") != "encerrado":
        espera = disjuntor.get("reabre_em_seg") or 0
        return {"nivel": "critico", "titulo": "SIGAA instável",
                "causa": ("Muitas falhas seguidas (tempo esgotado, rede ou SIGAA sobrecarregado): as buscas foram pausadas "
                          "automaticamente para não sobrecarregar o SIGAA. "
                          + (f"Nova busca de teste em {espera}s." if disjuntor.get("estado") == "aberto" else "Fazendo uma busca de teste agora.")),
                "indicadores": indicadores}
    if snap.get("pausado") and snap.get("fase") != "encerrado":
        return {"nivel": "aguardando", "titulo": "Pausado",
                "causa": "Sem buscas enquanto a execução está pausada — não há tráfego para avaliar.", "indicadores": indicadores}
    if snap.get("fase") == "encerrado":
        return {"nivel": "aguardando", "titulo": "Execução encerrada", "causa": "Não há tráfego agora — veja o resumo da última execução.",
                "indicadores": indicadores}
    if snap.get("fase") in ("preparando", "agendado"):
        return {"nivel": "aguardando", "titulo": "Aguardando início", "causa": "Ainda não há buscas para avaliar.", "indicadores": indicadores}
    if not reqs and not total_erros:
        causa = "Fazendo login e preparando a busca." if snap.get("fase") == "logando" else "Nenhuma busca nos últimos 30 segundos."
        if erros_recentes.get("departamento") or tel["erros"].get("departamento"):
            causa = ACOES_ERRO["departamento"]
        return {"nivel": "aguardando", "titulo": "Aguardando tráfego", "causa": causa, "indicadores": indicadores}

    dominante = max(erros_recentes, key=erros_recentes.get) if erros_recentes else None
    if taxa is not None and taxa > LIMITE_TAXA_ERRO_CRITICO:
        nivel, titulo = "critico", "Muitas falhas"
    elif (taxa is not None and taxa > LIMITE_TAXA_ERRO_ATENCAO) or (
            lat_recente and lat_base and len(p50s) > 30 and lat_recente > FATOR_LENTIDAO * lat_base):
        nivel, titulo = "atencao", "Instável"
    else:
        nivel, titulo = "estavel", "Estável"

    if dominante and nivel != "estavel":
        causa = f"A maioria das falhas recentes é \"{ROTULOS_ERRO.get(dominante, dominante)}\". {ACOES_ERRO.get(dominante, '')}"
    elif lat_recente and lat_base and len(p50s) > 30 and lat_recente > FATOR_LENTIDAO * lat_base:
        causa = (f"O SIGAA está respondendo mais devagar que o normal desta execução "
                 f"({round(lat_recente)} ms agora, contra {round(lat_base)} ms típicos). Costuma ser o próprio SIGAA sob carga.")
    else:
        causa = "Respostas normais do SIGAA e poucas falhas."
    return {"nivel": nivel, "titulo": titulo, "causa": causa, "indicadores": indicadores}


def agrupar_erros(snap: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Erros por tipo, do mais frequente ao menos, com o que fazer."""
    if not snap:
        return []
    erros = snap["telemetria"]["erros"]
    total = sum(v["total"] for v in erros.values()) or 1
    grupos = [{
        "categoria": cat, "rotulo": ROTULOS_ERRO.get(cat, cat), "total": v["total"],
        "percentual": round(100 * v["total"] / total), "primeira": v.get("primeira"), "ultima": v.get("ultima"),
        "ultimo_detalhe": v.get("ultimo_detalhe", ""), "acao": ACOES_ERRO.get(cat, ""),
    } for cat, v in erros.items()]
    return sorted(grupos, key=lambda g: -g["total"])


def descrever_fase(snap: Optional[Dict[str, Any]], agora: Optional[float] = None) -> Dict[str, Any]:
    """Etapa atual da execução com texto pronto e progresso (0–1) quando fizer sentido."""
    if not snap:
        return {"fase": "parado", "texto": "Nenhuma execução nesta sessão.", "progresso": None}
    fase = snap["fase"]
    if fase == "verificando":
        return {"fase": fase, "texto": "Verificando login e disciplinas antes de começar…", "progresso": None}
    if snap.get("pausado") and fase not in ("encerrado",):
        if snap.get("motivo_pausa") == "janela":
            return {"fase": fase, "texto": f"Fora da janela de execução ({snap.get('janela')}) — volta sozinho no próximo horário.",
                    "progresso": None}
        return {"fase": fase, "texto": "Pausado pelo usuário — sessões mantidas, nenhuma busca até retomar.", "progresso": None}
    if fase == "agendado":
        return {"fase": fase, "texto": f"Agendado para {snap.get('agendado_para')} — aguardando o horário.", "progresso": None}
    if fase == "logando":
        p = snap["progresso_login"]
        return {"fase": fase, "texto": f"Fazendo login: {p['logados']} de {p['total']} worker(s) prontos.",
                "progresso": (p["logados"] / p["total"]) if p["total"] else None}
    disjuntor = snap.get("disjuntor") or {}
    if fase in ("monitorando", "logando") and disjuntor.get("estado") == "aberto":
        return {"fase": fase, "texto": f"Pausado automaticamente: SIGAA instável — nova busca de teste em {disjuntor.get('reabre_em_seg', 0)}s.",
                "progresso": None}
    if fase == "monitorando":
        ativos = sum(1 for a in snap["alvos"] if a["ativo"])
        return {"fase": fase, "texto": f"Monitorando {ativos} disciplina(s) com {snap['num_workers']} worker(s).", "progresso": None}
    if fase == "encerrado":
        return {"fase": fase, "texto": "Execução encerrada.", "progresso": None}
    return {"fase": fase, "texto": "Preparando a execução…", "progresso": None}


def series_grafico(pontos: List[Dict[str, Any]], janela_seg: Optional[int] = None, max_pontos: int = 240) -> Dict[str, Any]:
    """Recorta a janela e reamostra em até `max_pontos` baldes: requisições/s
    (média), p50 (média), p95 (máximo — não esconder picos) e erros por
    categoria (soma)."""
    selecionados = _ultimos(pontos, janela_seg) if janela_seg else list(pontos)
    if not selecionados:
        return {"t": [], "rps": [], "p50": [], "p95": [], "erros": {c: [] for c in CATEGORIAS_ERRO}, "balde_seg": 1}
    tamanho = max(1, -(-len(selecionados) // max_pontos))  # divisão arredondada para cima
    saida = {"t": [], "rps": [], "p50": [], "p95": [], "erros": {c: [] for c in CATEGORIAS_ERRO}, "balde_seg": tamanho}
    for i in range(0, len(selecionados), tamanho):
        balde = selecionados[i:i + tamanho]
        saida["t"].append(balde[-1]["t"])
        saida["rps"].append(round(sum(p["req"] for p in balde) / len(balde), 2))
        p50 = [p["p50"] for p in balde if p["p50"] is not None]
        p95 = [p["p95"] for p in balde if p["p95"] is not None]
        saida["p50"].append(round(sum(p50) / len(p50)) if p50 else None)
        saida["p95"].append(round(max(p95)) if p95 else None)
        for c in CATEGORIAS_ERRO:
            saida["erros"][c].append(sum(p["erros"].get(c, 0) for p in balde))
    return saida


def sparklines(pontos: List[Dict[str, Any]], n: int = 60) -> Dict[str, List]:
    """Últimos n segundos para os mini gráficos dos cards (sugestão 032)."""
    ultimos = list(pontos)[-n:]
    return {"rps": [p["req"] for p in ultimos], "p50": [p["p50"] for p in ultimos]}


def tempo_relativo(ts: Optional[float], agora: Optional[float] = None) -> str:
    if not ts:
        return "—"
    delta = max(0, int((agora or time.time()) - ts))
    if delta < 60:
        return f"há {delta}s"
    if delta < 3600:
        return f"há {delta // 60} min"
    return f"há {delta // 3600} h {delta % 3600 // 60} min"
