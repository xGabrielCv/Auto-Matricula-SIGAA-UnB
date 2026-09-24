"""
Linha do tempo da execução (Fase 5 — sugestão 054).

Lê o final do log de auditoria (JSON Lines) e devolve só os eventos que contam
a história de uma execução — início, verificação, logins, vagas, tentativas e
cada etapa delas, resultados, pausas, proteção de carga, alertas, erros
relevantes e o fim — sem as milhares de linhas de "sem vagas". Eventos iguais
e seguidos (ex: 20 logins em sequência) viram um único item "×20".
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.dashboard.log_humano import traduzir

MAX_BYTES = 8 * 1024 * 1024
JUNTAR_SEG = 30

# evento → categoria da linha do tempo
MARCANTES = {
    "sessao_iniciada": "execucao", "verificacao_previa": "execucao", "relogio_sigaa": "execucao",
    "execucao_pausada": "execucao", "execucao_retomada": "execucao", "fim_agendado": "execucao",
    "execucao_resumo": "execucao", "parada_seguranca": "execucao", "alvo_adicionado": "execucao",
    "alvo_removido": "execucao",
    "login_ok": "login", "login_erro": "login", "sessao_expirada": "login",
    "vaga_detectada": "vagas", "grupo_dispensado": "vagas",
    "tentativa_iniciada": "tentativas", "tentativa_etapa": "tentativas", "tentativa_concluida": "tentativas",
    "matricula_sucesso": "tentativas", "matricula_bloqueada": "tentativas", "matricula_falha": "tentativas",
    "classificacao_resposta": "tentativas", "resposta_erro_sigaa": "tentativas",
    "confirmacao_nao_detectada": "tentativas", "dump_salvo": "tentativas",
    "disjuntor_aberto": "protecao", "disjuntor_fechado": "protecao", "sigaa_sobrecarregado": "protecao",
    "sigaa_manutencao": "protecao", "alerta_limiar": "protecao", "worker_reiniciado": "protecao",
    "timeout": "erros", "falha_rede": "erros", "erro_critico": "erros", "departamento_adiado": "erros",
}
CATEGORIAS_LINHA = {
    "execucao": "Execução", "login": "Login", "vagas": "Vagas", "tentativas": "Tentativas de matrícula",
    "protecao": "Proteção e alertas", "erros": "Erros",
}
# Eventos que se repetem muito e fazem sentido agrupados quando seguidos.
AGRUPAVEIS = {"login_ok", "login_erro", "sessao_expirada", "vaga_detectada", "sigaa_sobrecarregado", "sigaa_manutencao",
              "timeout", "falha_rede", "departamento_adiado"}
NIVEL = {"WARNING": "aviso", "ERROR": "erro", "CRITICAL": "destaque"}


def _ler_final(caminho: str, max_bytes: int) -> List[str]:
    if not os.path.exists(caminho):
        return []
    with open(caminho, "rb") as f:
        f.seek(0, os.SEEK_END)
        tamanho = f.tell()
        f.seek(max(0, tamanho - max_bytes))
        dados = f.read()
    linhas = dados.decode("utf-8", errors="replace").splitlines()
    return linhas[1:] if tamanho > max_bytes else linhas  # a 1ª pode estar cortada


def _registros(linhas: List[str]) -> List[Dict[str, Any]]:
    saida = []
    for linha in linhas:
        if '"evento"' not in linha:
            continue  # filtro barato antes do json.loads
        try:
            r = json.loads(linha)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("evento") in MARCANTES:
            saida.append(r)
    return saida


def _segundos(ts: str) -> float:
    try:
        return datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return 0.0


def montar_linha_do_tempo(registros: List[Dict[str, Any]], execucao_id: Optional[str] = None) -> Dict[str, Any]:
    execucoes: List[str] = []
    for r in registros:
        eid = r.get("execucao_id")
        if eid and eid not in execucoes:
            execucoes.append(eid)
    execucoes.reverse()  # mais recente primeiro
    escolhida = execucao_id if execucao_id in execucoes else (execucoes[0] if execucoes else None)

    itens: List[Dict[str, Any]] = []
    grupos: List[tuple] = []
    for r in registros:
        if escolhida and r.get("execucao_id") != escolhida:
            continue
        evento = r["evento"]
        ts = str(r.get("timestamp", ""))
        grupo = (evento, r.get("codigo"), r.get("turma"))
        if (itens and evento in AGRUPAVEIS and grupos[-1] == grupo
                and _segundos(ts) - _segundos(itens[-1]["fim"]) <= JUNTAR_SEG):
            itens[-1]["quantidade"] += 1
            itens[-1]["fim"] = ts
            continue
        ev = traduzir(r)
        grupos.append(grupo)
        itens.append({
            "evento": evento, "categoria": MARCANTES[evento], "inicio": ts, "fim": ts,
            "hora": ts[11:19] if len(ts) >= 19 else ts, "quantidade": 1,
            "titulo": ev.titulo, "detalhe": ev.corpo, "nivel": NIVEL.get(str(r.get("level")), "info"),
            "worker": r.get("worker", "MAIN"), "tentativa_id": r.get("tentativa_id"),
            "codigo": r.get("codigo"), "turma": r.get("turma"),
        })
    contagem: Dict[str, int] = {}
    for item in itens:
        item["hora_fim"] = item["fim"][11:19] if item["quantidade"] > 1 else None
        contagem[item["categoria"]] = contagem.get(item["categoria"], 0) + 1
    return {"execucao_id": escolhida, "execucoes": execucoes[:30], "itens": itens,
            "categorias": [{"id": c, "rotulo": rot, "total": contagem.get(c, 0)} for c, rot in CATEGORIAS_LINHA.items()]}


def linha_do_tempo(caminho_log: str, execucao_id: Optional[str] = None, max_bytes: int = MAX_BYTES) -> Dict[str, Any]:
    return montar_linha_do_tempo(_registros(_ler_final(caminho_log, max_bytes)), execucao_id)
