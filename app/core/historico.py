"""
Histórico local de execuções (Fase 3 — sugestão 060).

Antes, toda análise morria com a sessão: os painéis zeravam ao reabrir o
programa e o log rotativo não permite consultas por período. Agora, ao fim de
cada execução, o motor grava aqui (SQLite da biblioteca padrão, em
data/historico.db):

  - execucoes       → uma linha por execução (o resumo da sugestão 048 + totais);
  - leituras_vagas  → mudanças na quantidade de vagas de cada disciplina;
  - series_minuto   → buscas, tempo de resposta e erros agregados por minuto.

É isso que alimenta a tela Histórico: dias/períodos (022/024), comparação
entre execuções (025), mapa de calor de quando vagas abrem (028) e exportação
(049).

Regras:
  - Só UMA gravação por execução, no encerramento — nada é escrito durante o
    laço de busca (sem custo no caminho quente). Se o programa cair no meio,
    aquela execução não entra no histórico (o marcador de encerramento anormal
    continua avisando).
  - Nunca guarda credenciais: só códigos de disciplina, contagens e tempos.
  - Retenção configurável (settings["historico"]["dias_retencao"]).
"""
from __future__ import annotations

import csv
import io
import logging
import json
import os
import sqlite3
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from app.utils.paths import pasta_data

ARQUIVO = "historico.db"
VERSAO_ESQUEMA = 1
_lock = threading.Lock()
# Os resumos antigos (data/relatorios/) são importados uma vez por sessão do
# programa — e nunca de novo depois de "Apagar histórico" na mesma sessão.
_importacao_feita = False

ESQUEMA = """
CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS execucoes (
    id TEXT PRIMARY KEY, inicio REAL NOT NULL, fim REAL, duracao_seg REAL, modo TEXT, dry_run INTEGER,
    motivo_fim TEXT, versao TEXT, num_workers INTEGER, intervalo_busca REAL, timeout_req INTEGER,
    requisicoes INTEGER, vagas_vistas INTEGER, tentativas INTEGER, matriculadas INTEGER, simuladas INTEGER,
    bloqueadas INTEGER, erros INTEGER, latencia_media REAL, latencia_min REAL, latencia_max REAL,
    disciplinas TEXT, resumo_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_execucoes_inicio ON execucoes(inicio);
CREATE TABLE IF NOT EXISTS leituras_vagas (
    execucao_id TEXT NOT NULL, chave TEXT NOT NULL, t REAL NOT NULL, vagas INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leituras_t ON leituras_vagas(t);
CREATE INDEX IF NOT EXISTS idx_leituras_exec ON leituras_vagas(execucao_id);
CREATE TABLE IF NOT EXISTS series_minuto (
    execucao_id TEXT NOT NULL, t REAL NOT NULL, req INTEGER, p50 REAL, p95 REAL, erros_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_series_exec ON series_minuto(execucao_id);
"""

DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def caminho_banco() -> str:
    return os.path.join(pasta_data(), ARQUIVO)


def _abrir() -> sqlite3.Connection:
    conexao = sqlite3.connect(caminho_banco(), timeout=10)
    conexao.row_factory = sqlite3.Row
    try:
        conexao.executescript(ESQUEMA)
        conexao.execute("INSERT OR IGNORE INTO meta (chave, valor) VALUES ('versao_esquema', ?)", (str(VERSAO_ESQUEMA),))
        conexao.commit()  # não deixa transação de escrita aberta (outra conexão ficaria "database is locked")
    except BaseException:
        conexao.close()
        raise
    return conexao


def _conectar() -> sqlite3.Connection:
    """Desde a 6.1.0: um banco corrompido (queda de energia, arquivo trocado) não derruba
    as telas. O arquivo danificado é guardado como historico.db.corrompido-<data>
    (nada é apagado) e um banco novo, vazio, é criado no lugar."""
    try:
        return _abrir()
    except sqlite3.DatabaseError as e:
        if "locked" in str(e).lower():
            raise
        destino = f"{caminho_banco()}.corrompido-{time.strftime('%Y%m%d_%H%M%S')}"
        try:
            os.replace(caminho_banco(), destino)
        except OSError:
            raise e
        logging.getLogger("sniper").warning(
            f"Histórico ilegível ({type(e).__name__}): guardado em {os.path.basename(destino)} e recriado vazio.")
        return _abrir()


@contextmanager
def _banco():
    """Conexão que sempre é FECHADA ao sair (o `with` do sqlite3 só confirma a
    transação — no Windows, uma conexão esquecida aberta impede apagar o arquivo)."""
    conexao = _conectar()
    try:
        with conexao:
            yield conexao
    finally:
        conexao.close()


def _agregar_por_minuto(pontos: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pontos por segundo → um ponto por minuto (req somado, p50 médio, p95 máximo, erros somados)."""
    baldes: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for p in pontos:
        baldes[int(p["t"] // 60)].append(p)
    saida = []
    for minuto in sorted(baldes):
        grupo = baldes[minuto]
        p50 = [p["p50"] for p in grupo if p.get("p50") is not None]
        p95 = [p["p95"] for p in grupo if p.get("p95") is not None]
        erros: Dict[str, int] = defaultdict(int)
        for p in grupo:
            for cat, n in (p.get("erros") or {}).items():
                erros[cat] += n
        saida.append({"t": minuto * 60.0, "req": sum(p["req"] for p in grupo),
                      "p50": (sum(p50) / len(p50)) if p50 else None, "p95": max(p95) if p95 else None,
                      "erros": dict(erros)})
    return saida


def registrar_execucao(resumo: Dict[str, Any], telemetria: Optional[Dict[str, Any]] = None) -> bool:
    """Grava uma execução encerrada. Idempotente (regravar o mesmo id substitui)."""
    if not resumo or not resumo.get("execucao_id"):
        return False
    tel = telemetria or {}
    t = resumo.get("totais", {})
    lat = resumo.get("latencia_ms", {})
    cfg = resumo.get("configuracao", {})
    inicio = datetime.strptime(resumo["inicio"], "%Y-%m-%d %H:%M:%S").timestamp()
    fim = datetime.strptime(resumo["fim"], "%Y-%m-%d %H:%M:%S").timestamp() if resumo.get("fim") else None
    disciplinas = ",".join(a["chave"] for a in resumo.get("alvos", []))
    with _lock, _banco() as con:
        eid = resumo["execucao_id"]
        for tabela in ("leituras_vagas", "series_minuto"):
            con.execute(f"DELETE FROM {tabela} WHERE execucao_id = ?", (eid,))  # noqa: S608 — nome fixo
        con.execute(
            """INSERT OR REPLACE INTO execucoes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid, inicio, fim, resumo.get("duracao_seg"), resumo.get("modo"), int(bool(resumo.get("dry_run"))),
             resumo.get("motivo_fim"), resumo.get("versao"), cfg.get("num_workers"), cfg.get("intervalo_busca"),
             cfg.get("timeout_req"), t.get("requisicoes", 0), t.get("vagas_vistas", 0), t.get("tentativas", 0),
             t.get("matriculadas", 0), t.get("simuladas", 0), t.get("bloqueadas", 0), t.get("erros", 0),
             lat.get("media"), lat.get("min"), lat.get("max"), disciplinas, json.dumps(resumo, ensure_ascii=False)),
        )
        leituras = [(eid, chave, float(ts), int(v)) for chave, serie in (tel.get("vagas_series") or {}).items() for ts, v in serie]
        con.executemany("INSERT INTO leituras_vagas VALUES (?,?,?,?)", leituras)
        minutos = _agregar_por_minuto(tel.get("pontos") or [])
        con.executemany("INSERT INTO series_minuto VALUES (?,?,?,?,?,?)",
                        [(eid, m["t"], m["req"], m["p50"], m["p95"], json.dumps(m["erros"])) for m in minutos])
    return True


def aplicar_retencao(dias: int) -> int:
    """Apaga execuções mais antigas que `dias` (0 = nunca apaga). Devolve quantas saíram."""
    if not dias or dias <= 0:
        return 0
    limite = time.time() - dias * 86400
    with _lock, _banco() as con:
        ids = [r["id"] for r in con.execute("SELECT id FROM execucoes WHERE inicio < ?", (limite,))]
        for eid in ids:
            for tabela in ("leituras_vagas", "series_minuto", "execucoes"):
                coluna = "id" if tabela == "execucoes" else "execucao_id"
                con.execute(f"DELETE FROM {tabela} WHERE {coluna} = ?", (eid,))  # noqa: S608 — nomes fixos
    return len(ids)


def apagar_tudo() -> None:
    global _importacao_feita
    _importacao_feita = True
    with _lock:
        try:
            os.remove(caminho_banco())
        except FileNotFoundError:
            pass
    from app.core import auditoria
    auditoria.registrar("historico_apagado")


def importar_relatorios_antigos(forcar: bool = False) -> int:
    """Traz para o banco os resumos JSON de data/relatorios/ que ainda não estão
    nele (execuções gravadas antes de o histórico existir). Sem séries por minuto.
    Só age na primeira chamada da sessão (`forcar=True` ignora isso)."""
    global _importacao_feita
    if _importacao_feita and not forcar:
        return 0
    _importacao_feita = True
    from app.core.relatorios import listar_relatorios
    with _banco() as con:
        existentes = {r["id"] for r in con.execute("SELECT id FROM execucoes")}
    novos = 0
    for resumo in listar_relatorios():
        if resumo.get("execucao_id") not in existentes:
            try:
                registrar_execucao(resumo)
                novos += 1
            except (KeyError, ValueError, sqlite3.Error):
                continue
    return novos


# ── Consultas ─────────────────────────────────────────────────────────────

def _filtro(dias: Optional[int], disciplina: Optional[str]) -> tuple:
    condicoes, parametros = [], []
    if dias:
        condicoes.append("inicio >= ?")
        parametros.append(time.time() - dias * 86400)
    if disciplina:
        condicoes.append("(',' || disciplinas || ',') LIKE ?")
        parametros.append(f"%,{disciplina},%")
    return (" WHERE " + " AND ".join(condicoes)) if condicoes else "", parametros


def listar_execucoes(dias: Optional[int] = None, disciplina: Optional[str] = None, limite: int = 500) -> List[Dict[str, Any]]:
    onde, parametros = _filtro(dias, disciplina)
    with _banco() as con:
        linhas = con.execute(f"SELECT * FROM execucoes{onde} ORDER BY inicio DESC LIMIT ?",  # noqa: S608 — só placeholders
                             (*parametros, limite)).fetchall()
    saida = []
    for r in linhas:
        item = {k: r[k] for k in r.keys() if k != "resumo_json"}
        item["dry_run"] = bool(item["dry_run"])
        item["disciplinas"] = [d for d in (item["disciplinas"] or "").split(",") if d]
        item["buscas_por_seg"] = (item["requisicoes"] / item["duracao_seg"]) if item["duracao_seg"] else None
        item["taxa_erro"] = (item["erros"] / item["requisicoes"]) if item["requisicoes"] else None
        saida.append(item)
    return saida


def obter_execucao(execucao_id: str) -> Optional[Dict[str, Any]]:
    with _banco() as con:
        r = con.execute("SELECT * FROM execucoes WHERE id = ?", (execucao_id,)).fetchone()
        if not r:
            return None
        series = [{"t": s["t"], "req": s["req"], "p50": s["p50"], "p95": s["p95"], "erros": json.loads(s["erros_json"] or "{}")}
                  for s in con.execute("SELECT * FROM series_minuto WHERE execucao_id = ? ORDER BY t", (execucao_id,))]
        vagas: Dict[str, List] = defaultdict(list)
        for lv in con.execute("SELECT chave, t, vagas FROM leituras_vagas WHERE execucao_id = ? ORDER BY t", (execucao_id,)):
            vagas[lv["chave"]].append([lv["t"], lv["vagas"]])
    return {"resumo": json.loads(r["resumo_json"]), "series_minuto": series, "vagas_series": dict(vagas),
            "inicio": r["inicio"], "fim": r["fim"]}


def resumo_por_dia(dias: Optional[int] = None, disciplina: Optional[str] = None) -> List[Dict[str, Any]]:
    """Totais por dia (sugestão 022): execuções, horas monitoradas, buscas, vagas, erros, matrículas."""
    por_dia: Dict[str, Dict[str, Any]] = {}
    for e in listar_execucoes(dias, disciplina, limite=100000):
        dia = datetime.fromtimestamp(e["inicio"]).strftime("%Y-%m-%d")
        d = por_dia.setdefault(dia, {"dia": dia, "execucoes": 0, "horas": 0.0, "buscas": 0, "vagas_vistas": 0,
                                     "erros": 0, "matriculadas": 0, "simuladas": 0})
        d["execucoes"] += 1
        d["horas"] += (e["duracao_seg"] or 0) / 3600
        d["buscas"] += e["requisicoes"] or 0
        d["vagas_vistas"] += e["vagas_vistas"] or 0
        d["erros"] += e["erros"] or 0
        d["matriculadas"] += e["matriculadas"] or 0
        d["simuladas"] += e["simuladas"] or 0
    return [dict(v, horas=round(v["horas"], 2)) for _k, v in sorted(por_dia.items())]


def mapa_aberturas_de_vaga(dias: Optional[int] = None, disciplina: Optional[str] = None) -> Dict[str, Any]:
    """Sugestão 028: quantas vezes uma vaga ABRIU (0 → >0, ou primeira leitura já
    com vaga) em cada dia da semana × hora. Uma vaga que fica aberta por horas
    conta uma vez — o que interessa é quando elas surgem."""
    condicoes, parametros = [], []
    if dias:
        condicoes.append("t >= ?")
        parametros.append(time.time() - dias * 86400)
    if disciplina:
        condicoes.append("chave = ?")
        parametros.append(disciplina)
    onde = (" WHERE " + " AND ".join(condicoes)) if condicoes else ""
    matriz = [[0] * 24 for _ in range(7)]
    total = 0
    with _banco() as con:
        anterior: Dict[tuple, int] = {}
        for lv in con.execute(f"SELECT execucao_id, chave, t, vagas FROM leituras_vagas{onde} ORDER BY execucao_id, chave, t",  # noqa: S608
                              parametros):
            chave = (lv["execucao_id"], lv["chave"])
            antes = anterior.get(chave, 0)
            if lv["vagas"] > 0 and antes <= 0:
                quando = datetime.fromtimestamp(lv["t"])
                matriz[quando.weekday()][quando.hour] += 1
                total += 1
            anterior[chave] = lv["vagas"]
    return {"dias": DIAS_SEMANA, "horas": list(range(24)), "matriz": matriz, "total": total}


def comparar(ids: List[str]) -> List[Dict[str, Any]]:
    """Sugestão 025: execuções lado a lado, com a série por minuto em "minutos desde o início"."""
    saida = []
    for eid in ids:
        detalhe = obter_execucao(eid)
        if not detalhe:
            continue
        resumo = detalhe["resumo"]
        inicio = detalhe["inicio"]
        linha = next((e for e in listar_execucoes(limite=100000) if e["id"] == eid), {})
        saida.append({
            "id": eid, "resumo": resumo, "indicadores": {
                "duracao_seg": resumo.get("duracao_seg"), "num_workers": resumo["configuracao"].get("num_workers"),
                "intervalo_busca": resumo["configuracao"].get("intervalo_busca"),
                "buscas_por_seg": linha.get("buscas_por_seg"), "latencia_media": linha.get("latencia_media"),
                "taxa_erro": linha.get("taxa_erro"), "vagas_vistas": resumo["totais"].get("vagas_vistas"),
                "tentativas": resumo["totais"].get("tentativas"), "erros": resumo["totais"].get("erros"),
            },
            # O balde do 1º minuto começa antes do início exato: nunca "minutos negativos".
            "latencia_por_minuto": [[round(max(0.0, (s["t"] - inicio) / 60), 2), s["p50"]] for s in detalhe["series_minuto"]],
        })
    return saida


# ── Exportação (sugestão 049) ─────────────────────────────────────────────

def _celula_segura(valor: Any) -> Any:
    """Evita injeção de fórmula ao abrir o CSV no Excel/Sheets."""
    if isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + valor
    return valor


def para_csv(linhas: List[Dict[str, Any]], colunas: List[str]) -> str:
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")  # ";" abre direto no Excel em português
    escritor.writerow(colunas)
    for linha in linhas:
        escritor.writerow([_celula_segura(linha.get(c)) for c in colunas])
    return "﻿" + saida.getvalue()  # BOM: acentos corretos no Excel


COLUNAS_EXECUCOES = ["id", "inicio_txt", "duracao_seg", "modo", "dry_run", "motivo_fim", "num_workers", "intervalo_busca",
                     "requisicoes", "vagas_vistas", "tentativas", "matriculadas", "simuladas", "bloqueadas", "erros",
                     "latencia_media", "disciplinas_txt"]


def exportar_execucoes(formato: str, dias: Optional[int] = None, disciplina: Optional[str] = None) -> str:
    execucoes = listar_execucoes(dias, disciplina, limite=100000)
    for e in execucoes:
        e["inicio_txt"] = datetime.fromtimestamp(e["inicio"]).strftime("%Y-%m-%d %H:%M:%S")
        e["disciplinas_txt"] = " ".join(e["disciplinas"])
    if formato == "json":
        return json.dumps(execucoes, ensure_ascii=False, indent=2)
    return para_csv(execucoes, COLUNAS_EXECUCOES)


def exportar_leituras_vagas(formato: str, dias: Optional[int] = None, disciplina: Optional[str] = None) -> str:
    condicoes, parametros = [], []
    if dias:
        condicoes.append("t >= ?")
        parametros.append(time.time() - dias * 86400)
    if disciplina:
        condicoes.append("chave = ?")
        parametros.append(disciplina)
    onde = (" WHERE " + " AND ".join(condicoes)) if condicoes else ""
    with _banco() as con:
        linhas = [{"execucao_id": r["execucao_id"], "disciplina": r["chave"],
                   "horario": datetime.fromtimestamp(r["t"]).strftime("%Y-%m-%d %H:%M:%S"), "vagas": r["vagas"]}
                  for r in con.execute(f"SELECT * FROM leituras_vagas{onde} ORDER BY t", parametros)]  # noqa: S608
    if formato == "json":
        return json.dumps(linhas, ensure_ascii=False, indent=2)
    return para_csv(linhas, ["execucao_id", "disciplina", "horario", "vagas"])


def disciplinas_no_historico() -> List[str]:
    with _banco() as con:
        com_leituras = [r["chave"] for r in con.execute("SELECT DISTINCT chave FROM leituras_vagas")]
    cadastradas = {d for e in listar_execucoes(limite=100000) for d in e["disciplinas"]}
    return sorted(set(com_leituras) | cadastradas)


# ── Janelas prováveis de vaga (Fase 6 — sugestão 091) ─────────────────────

MIN_ABERTURAS_JANELA = 5
COBERTURA_JANELA = 0.7


def _aberturas(dias: Optional[int], disciplina: Optional[str]) -> Dict[str, List[datetime]]:
    """Momentos em que uma vaga surgiu (0 → >0), por disciplina."""
    condicoes, parametros = [], []
    if dias:
        condicoes.append("t >= ?")
        parametros.append(time.time() - dias * 86400)
    if disciplina:
        condicoes.append("chave = ?")
        parametros.append(disciplina)
    onde = (" WHERE " + " AND ".join(condicoes)) if condicoes else ""
    saida: Dict[str, List[datetime]] = {}
    with _banco() as con:
        anterior: Dict[tuple, int] = {}
        for lv in con.execute(f"SELECT execucao_id, chave, t, vagas FROM leituras_vagas{onde} ORDER BY execucao_id, chave, t",  # noqa: S608
                              parametros):
            chave = (lv["execucao_id"], lv["chave"])
            if lv["vagas"] > 0 and anterior.get(chave, 0) <= 0:
                saida.setdefault(lv["chave"], []).append(datetime.fromtimestamp(lv["t"]))
            anterior[chave] = lv["vagas"]
    return saida


def _menor_faixa(contagem: List[int], alvo: float) -> tuple:
    """Menor faixa de horas contíguas (sem dar a volta na meia-noite) com pelo menos `alvo` aberturas."""
    melhor = (0, 23)
    for inicio in range(24):
        soma = 0
        for fim in range(inicio, 24):
            soma += contagem[fim]
            if soma >= alvo:
                if fim - inicio < melhor[1] - melhor[0]:
                    melhor = (inicio, fim)
                break
    return melhor


def janelas_provaveis(dias: int = 14, disciplina: str = "") -> List[Dict[str, Any]]:
    """Por disciplina: a menor faixa de horário que concentrou ~70% das vagas que
    surgiram no período, com uma sugestão de janela diária (035). É estatística do
    próprio histórico, nunca garantia de vaga."""
    resultado = []
    for chave, momentos in sorted(_aberturas(dias, disciplina or None).items()):
        total = len(momentos)
        item: Dict[str, Any] = {"disciplina": chave, "aberturas": total}
        if total < MIN_ABERTURAS_JANELA:
            item.update(suficiente=False, texto=f"{chave}: só {total} abertura(s) de vaga nos últimos {dias} dias — "
                                                "poucos dados para apontar um horário.")
            resultado.append(item)
            continue
        contagem = [0] * 24
        for m in momentos:
            contagem[m.hour] += 1
        inicio, fim = _menor_faixa(contagem, COBERTURA_JANELA * total)
        dentro = sum(contagem[inicio:fim + 1])
        pct = round(100 * dentro / total)
        dias_semana = sorted({m.weekday() for m in momentos if inicio <= m.hour <= fim})
        janela_inicio = f"{max(0, inicio - 1):02d}:30" if inicio > 0 else "00:00"
        janela_fim = f"{fim + 1:02d}:30" if fim < 23 else "23:59"
        item.update(
            suficiente=True, inicio_h=inicio, fim_h=fim, porcentagem=pct, contagem_por_hora=contagem,
            texto=(f"Nos últimos {dias} dias, {pct}% das vagas de {chave} surgiram entre {inicio}h e {fim + 1}h "
                   f"({dentro} de {total})."),
            sugestao={"ativa": True, "inicio": janela_inicio, "fim": janela_fim, "dias": dias_semana},
        )
        resultado.append(item)
    return resultado
