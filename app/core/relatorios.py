"""
Relatórios de encerramento de execução (sugestão 048).

Cada execução do motor termina gravando um resumo em
data/relatorios/<execucao_id>.json: duração, modo, resultado de cada
disciplina, buscas, vagas vistas, tentativas, erros por tipo e a configuração
usada. Não contém credenciais (o resumo só tem códigos de disciplina e contagens).
Guarda os mais recentes e apaga os antigos automaticamente.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from app.utils.paths import pasta_data

PASTA_RELATORIOS = "relatorios"
MAX_RELATORIOS = 50
_ID_VALIDO = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

MOTIVOS_FIM = {
    "concluida": "Todas as disciplinas foram processadas",
    "interrompida": "Interrompida pelo usuário",
    "sem_workers": "Encerrada: nenhum worker conseguiu continuar (login recusado ou falhas seguidas)",
    "erro": "Encerrada por um erro",
    "fim_agendado": "Encerrada no horário de término agendado",
    "login_recusado": "Encerrada antes de começar: o SIGAA recusou o login (confira matrícula e senha)",
    "dados_incorretos": "Parada por segurança: o SIGAA recusou os dados de confirmação (senha, CPF ou data de nascimento)",
    "periodo_encerrado": "Parada: o SIGAA informou que o período de matrícula não está aberto",
    None: "Motivo desconhecido",
}


def _pasta() -> str:
    pasta = os.path.join(pasta_data(), PASTA_RELATORIOS)
    os.makedirs(pasta, exist_ok=True)
    return pasta


def salvar_relatorio(resumo: Dict[str, Any]) -> Optional[str]:
    execucao_id = str(resumo.get("execucao_id", ""))
    if not _ID_VALIDO.match(execucao_id):
        return None
    caminho = os.path.join(_pasta(), f"{execucao_id}.json")
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)
    _aplicar_retencao()
    return caminho


def _aplicar_retencao() -> None:
    arquivos = sorted(
        (os.path.join(_pasta(), n) for n in os.listdir(_pasta()) if n.endswith(".json")),
        key=os.path.getmtime, reverse=True,
    )
    for antigo in arquivos[MAX_RELATORIOS:]:
        try:
            os.remove(antigo)
        except OSError:
            pass


def carregar_relatorio(execucao_id: str) -> Optional[Dict[str, Any]]:
    if not _ID_VALIDO.match(execucao_id or ""):
        return None  # nunca monta caminho com texto arbitrário
    caminho = os.path.join(_pasta(), f"{execucao_id}.json")
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def listar_relatorios(limite: int = MAX_RELATORIOS) -> List[Dict[str, Any]]:
    """Resumos mais recentes primeiro (arquivos corrompidos são ignorados)."""
    resultado = []
    nomes = sorted((n for n in os.listdir(_pasta()) if n.endswith(".json")),
                   key=lambda n: os.path.getmtime(os.path.join(_pasta(), n)), reverse=True)
    for nome in nomes[:limite]:
        dados = carregar_relatorio(nome[:-5])
        if dados:
            resultado.append(dados)
    return resultado


def texto_relatorio(resumo: Dict[str, Any]) -> str:
    """Versão em texto simples (terminal, GUI, cópia)."""
    t = resumo.get("totais", {})
    modo = "Somente monitoramento" if resumo.get("modo") == "monitoramento" else (
        "Matrícula em DRY RUN (teste)" if resumo.get("dry_run") else "Matrícula REAL")
    minutos, segundos = divmod(int(resumo.get("duracao_seg") or 0), 60)
    horas, minutos = divmod(minutos, 60)
    duracao = f"{horas}h {minutos}m {segundos}s" if horas else f"{minutos}m {segundos}s"
    linhas = [
        f"Resumo da execução {resumo.get('execucao_id', '?')}",
        f"  {resumo.get('inicio', '?')} → {resumo.get('fim', '?')} ({duracao}) · {modo}",
        f"  Fim: {MOTIVOS_FIM.get(resumo.get('motivo_fim'), resumo.get('motivo_fim'))}",
        f"  Buscas: {t.get('requisicoes', 0)} · vagas vistas: {t.get('vagas_vistas', 0)} · "
        f"tentativas: {t.get('tentativas', 0)} · erros: {t.get('erros', 0)}",
        "",
        "  Disciplinas:",
    ]
    for a in resumo.get("alvos", []):
        linhas.append(f"    {a['chave']:<14} {a['estado_rotulo']:<34} buscas {a['buscas']:>5} · vagas vistas {a['vagas_vistas']}")
    erros = resumo.get("erros") or {}
    if erros:
        linhas += ["", "  Erros por tipo: " + ", ".join(f"{k} {v}" for k, v in sorted(erros.items(), key=lambda x: -x[1]))]
    return "\n".join(linhas)
