"""
Alertas por limiar, anomalias e resumo periódico (Fase 5 — sugestões 058, 090 e 052).

O motor chama `AvaliadorAlertas.avaliar(snapshot)` a cada poucos segundos. Cada
regra olha só a telemetria que o motor já coleta (nada de I/O aqui) e devolve
MUDANÇAS: um alerta é emitido uma vez quando a condição começa e uma vez quando
ela termina ("resolvido") — nunca uma notificação por avaliação.

Regras (limites configuráveis em settings["alertas"]):
  - taxa_erro:     % de buscas com erro nos últimos N minutos acima do limite;
  - sem_resposta:  nenhuma resposta do SIGAA há M minutos (com o motor buscando);
  - sem_busca:     nenhuma busca feita há K minutos (workers parados/travados);
  - lentidao (090): latência recente 5× acima da mediana da própria execução;
  - manutencao (090): páginas de manutenção/indisponibilidade detectadas.

Nenhuma regra dispara com a execução pausada, agendada, fora da janela ou com
a pausa automática da proteção de carga ativa — nesses casos o silêncio é
esperado e já tem aviso próprio.
"""
from __future__ import annotations

import time
from statistics import median
from typing import Any, Dict, List, Optional

PADROES_ALERTAS: Dict[str, Any] = {
    "ativo": True,
    "taxa_erro_pct": 30,       # % de buscas com erro...
    "taxa_erro_min": 2,        # ...sustentada por N minutos
    "sem_resposta_min": 5,
    "sem_busca_min": 2,
    "lentidao_fator": 5,
}
MIN_BUSCAS_TAXA = 20           # abaixo disso a taxa de erro não é confiável
MIN_AMOSTRAS_LENTIDAO = 120    # segundos com latência antes de comparar
JANELA_LENTIDAO_SEG = 30

TITULOS = {
    "taxa_erro": "Muitos erros nas buscas",
    "sem_resposta": "SIGAA sem responder",
    "sem_busca": "Nenhuma busca acontecendo",
    "lentidao": "SIGAA muito mais lento que o normal",
    "manutencao": "SIGAA parece estar em manutenção",
}


def _fase_ativa(snap: Dict[str, Any]) -> bool:
    return (snap.get("fase") == "monitorando" and not snap.get("pausado")
            and (snap.get("disjuntor") or {}).get("estado", "fechado") == "fechado")


class AvaliadorAlertas:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.cfg = {**PADROES_ALERTAS, **(config or {})}
        self.ativos: Dict[str, Dict[str, Any]] = {}
        self.historico: List[Dict[str, Any]] = []
        self._ultima_resposta: Optional[float] = None
        self._ultima_busca_total = 0
        self._ultima_busca_ts: Optional[float] = None
        self._manutencao_ts: Optional[float] = None
        self._ultimo_ponto = 0.0

    def registrar_manutencao(self, agora: Optional[float] = None) -> None:
        self._manutencao_ts = agora or time.time()

    # ── regras ────────────────────────────────────────────────────────────

    def _condicoes(self, snap: Dict[str, Any], agora: float) -> Dict[str, Optional[str]]:
        tel = snap.get("telemetria") or {}
        pontos = tel.get("pontos") or []
        cfg = self.cfg
        cond: Dict[str, Optional[str]] = {}

        total_buscas = int((snap.get("contadores") or {}).get("buscas", 0))
        if total_buscas != self._ultima_busca_total or self._ultima_busca_ts is None:
            self._ultima_busca_total, self._ultima_busca_ts = total_buscas, agora
        novos = [p for p in pontos if p["t"] > self._ultimo_ponto]
        if pontos:
            self._ultimo_ponto = pontos[-1]["t"]
        if any(p.get("p50") is not None for p in novos):
            self._ultima_resposta = agora
        elif self._ultima_resposta is None:
            self._ultima_resposta = agora  # conta a partir do início do monitoramento

        # Taxa de erro sustentada.
        janela = [p for p in pontos if p["t"] >= agora - cfg["taxa_erro_min"] * 60]
        req = sum(p.get("req", 0) for p in janela)
        erros = sum(sum((p.get("erros") or {}).values()) for p in janela)
        cobertura = (janela[-1]["t"] - janela[0]["t"]) if len(janela) > 1 else 0
        if req >= MIN_BUSCAS_TAXA and cobertura >= cfg["taxa_erro_min"] * 60 * 0.9:
            pct = 100 * erros / max(1, req)
            cond["taxa_erro"] = (f"{pct:.0f}% das buscas dos últimos {cfg['taxa_erro_min']} min tiveram erro "
                                 f"(limite: {cfg['taxa_erro_pct']}%).") if pct > cfg["taxa_erro_pct"] else None
        else:
            cond["taxa_erro"] = None

        seg = agora - self._ultima_resposta
        cond["sem_resposta"] = (f"Nenhuma resposta do SIGAA há {seg / 60:.0f} min."
                                if seg >= cfg["sem_resposta_min"] * 60 else None)
        seg = agora - self._ultima_busca_ts
        ativos = [a for a in snap.get("alvos", []) if a.get("ativo")]
        sem_depto = bool(ativos) and all(a.get("estado") == "departamento_indisponivel" for a in ativos)
        cond["sem_busca"] = None
        if seg >= cfg["sem_busca_min"] * 60:
            cond["sem_busca"] = (f"Nenhuma busca feita há {seg / 60:.0f} min: a página de busca dos departamentos não abre "
                                 "(fora do período de matrícula extraordinária?)." if sem_depto else
                                 f"Nenhuma busca feita há {seg / 60:.0f} min — os workers podem estar travados.")

        # Lentidão anormal (090): mediana recente contra a mediana da execução inteira.
        com_lat = [p["p50"] for p in pontos if p.get("p50") is not None]
        recentes = [p["p50"] for p in pontos if p.get("p50") is not None and p["t"] >= agora - JANELA_LENTIDAO_SEG]
        cond["lentidao"] = None
        if len(com_lat) >= MIN_AMOSTRAS_LENTIDAO and len(recentes) >= 5:
            base, atual = median(com_lat[:-len(recentes)] or com_lat), median(recentes)
            if base > 0 and atual >= cfg["lentidao_fator"] * base and atual >= 1000:
                cond["lentidao"] = (f"Respostas levando ~{atual / 1000:.1f} s, contra ~{base / 1000:.1f} s no início "
                                    "desta execução. O problema provavelmente é o SIGAA, não o programa.")

        cond["manutencao"] = ("O SIGAA respondeu com uma página de manutenção/indisponibilidade. As buscas seguem "
                              "em ritmo reduzido até ele voltar."
                              if self._manutencao_ts and agora - self._manutencao_ts < 120 else None)
        return cond

    def avaliar(self, snap: Dict[str, Any], agora: Optional[float] = None) -> List[Dict[str, Any]]:
        """Devolve as mudanças desde a última avaliação: [{regra, estado: 'ativo'|'resolvido', texto}]."""
        if not self.cfg.get("ativo"):
            return []
        agora = agora or time.time()
        if _fase_ativa(snap):
            condicoes = self._condicoes(snap, agora)
        elif snap.get("fase") == "monitorando" and not snap.get("pausado"):
            # Pausa automática da proteção de carga: só a manutenção continua valendo
            # (é justamente o que costuma abrir o disjuntor).
            self._ultima_resposta = self._ultima_busca_ts = None
            condicoes = {"manutencao": self._condicoes(snap, agora)["manutencao"]}
            self._ultima_resposta = self._ultima_busca_ts = None
        else:
            # Pausado/agendado: relógios recomeçam na volta, para o silêncio
            # esperado não virar "sem resposta" na retomada.
            self._ultima_resposta = self._ultima_busca_ts = None
            return []
        mudancas = []
        for regra, texto in condicoes.items():
            if texto and regra not in self.ativos:
                self.ativos[regra] = {"regra": regra, "titulo": TITULOS[regra], "texto": texto, "desde": agora}
                mudancas.append({"regra": regra, "estado": "ativo", "titulo": TITULOS[regra], "texto": texto})
            elif not texto and regra in self.ativos:
                inicio = self.ativos.pop(regra)["desde"]
                mudancas.append({"regra": regra, "estado": "resolvido", "titulo": TITULOS[regra],
                                 "texto": f"{TITULOS[regra]}: normalizado após {max(1, round((agora - inicio) / 60))} min."})
            elif texto:
                self.ativos[regra]["texto"] = texto
        for m in mudancas:
            self.historico.append({**m, "quando": agora})
        del self.historico[:-100]
        return mudancas

    def snapshot(self) -> Dict[str, Any]:
        return {"ativos": [dict(a) for a in self.ativos.values()], "historico": [dict(h) for h in self.historico[-20:]]}


def texto_resumo_periodico(snap: Dict[str, Any], final: bool = False) -> str:
    """Resumo curto para Telegram/ntfy (052): diz se está tudo bem, sem jargão."""
    tel = snap.get("telemetria") or {}
    cont = snap.get("contadores") or {}
    inicio = snap.get("inicio") or time.time()
    horas = max(0.0, ((snap.get("fim") or time.time()) - inicio) / 3600)
    erros = sum(v.get("total", 0) for v in (tel.get("erros") or {}).values())
    alertas = [a["titulo"] for a in (snap.get("alertas") or {}).get("ativos", [])]
    ativos = sum(1 for a in snap.get("alvos", []) if a.get("ativo"))
    lat = (tel.get("latencia") or {}).get("recente")
    estado = "⚠️ Atenção: " + "; ".join(alertas) if alertas else ("⏸️ Pausado" if snap.get("pausado") else "✅ Tudo ok")
    cabecalho = "📋 Execução encerrada" if final else "📋 Resumo periódico"
    return (f"{cabecalho} ({horas:.1f} h): {estado}. {tel.get('requisicoes', 0)} buscas, "
            f"{tel.get('vagas_vistas', 0)} vaga(s) vista(s), {cont.get('tentativas', 0)} tentativa(s), {erros} erro(s)"
            + (f", resposta média {lat / 1000:.1f} s" if lat else "") + f". Disciplinas ativas: {ativos}.")
