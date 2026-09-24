"""
Trilha de auditoria das ações do usuário (Fase 6 — sugestões 062 e 063).

O log do motor conta o que o robô fez; esta trilha conta o que a PESSOA fez:
aceitou o aviso legal (com a versão/hash do texto aceito), iniciou/parou uma
execução (modo, DRY RUN), mudou configurações (quais chaves e, quando não é
sensível, de quanto para quanto), importou/restaurou configuração, aplicou um
perfil, salvou/apagou segredos de notificação, apagou histórico...

Regras:
  - NUNCA grava valores sensíveis: credenciais não passam por aqui, e para
    chaves que não estão em VALORES_SEGUROS só o NOME da chave é registrado;
  - o aceite do aviso legal é registrado a cada vez, mas nunca é "lembrado":
    o aviso continua aparecendo sempre (063);
  - falha ao gravar a trilha nunca interrompe a ação do usuário.

Arquivo: data/auditoria.jsonl (JSON Lines), com rotação simples por tamanho.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

TAMANHO_MAX = 2 * 1024 * 1024
_lock = threading.Lock()
_origem = "programa"

# Chaves de settings cujo valor pode aparecer na trilha (números, modos, liga/desliga).
VALORES_SEGUROS = {"modo", "dry_run", "num_workers", "intervalo_busca", "timeout_req", "agendar_inicio", "agendar_fim",
                   "verificacao_previa", "agendamento_relogio_sigaa", "abrir_dashboard_ao_iniciar"}

ROTULOS_ACOES = {
    "aviso_aceito": "Aceitou o aviso legal",
    "aviso_recusado": "Recusou o aviso legal",
    "execucao_iniciada": "Iniciou uma execução",
    "execucao_parada": "Pediu para parar a execução",
    "execucao_pausada": "Pausou a execução",
    "execucao_retomada": "Retomou a execução",
    "configuracao_alterada": "Alterou configurações",
    "disciplinas_alteradas": "Alterou as disciplinas",
    "configuracao_importada": "Importou uma configuração",
    "padroes_restaurados": "Restaurou configurações padrão",
    "versao_restaurada": "Desfez uma alteração (restaurou uma versão anterior)",
    "perfil_aplicado": "Aplicou um perfil",
    "perfil_salvo": "Salvou um perfil",
    "perfil_apagado": "Apagou um perfil",
    "segredos_salvos": "Salvou tokens de notificação neste computador",
    "segredos_apagados": "Apagou os tokens de notificação salvos",
    "credenciais_preenchidas": "Preencheu as credenciais do SIGAA (só em memória)",
    "credenciais_limpas": "Apagou as credenciais da memória",
    "historico_apagado": "Apagou o histórico de execuções",
    "departamentos_atualizados": "Atualizou a lista de departamentos",
    "recomendacao_aplicada": "Aplicou uma recomendação de configuração",
    "sessao_web_expirada": "Sessão da Interface Web expirou por inatividade",
    "configuracao_inicial": "Concluiu o assistente de configuração inicial",
}


def definir_origem(origem: str) -> None:
    """Cada interface diz quem ela é ao iniciar: 'web', 'interface grafica' ou 'terminal'."""
    global _origem
    _origem = origem


def _arquivo() -> str:
    from app.utils.paths import caminho
    return caminho("data", "auditoria.jsonl")


def registrar(acao: str, **detalhes: Any) -> None:
    registro = {"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "acao": acao, "origem": _origem}
    for chave, valor in detalhes.items():
        if isinstance(valor, (str, int, float, bool)) or valor is None:
            registro[chave] = valor
        elif isinstance(valor, (list, tuple)):
            registro[chave] = [v for v in valor if isinstance(v, (str, int, float, bool))][:50]
    _gravar(registro)


def _gravar(registro: Dict[str, Any]) -> None:
    try:
        with _lock:
            arquivo = _arquivo()
            if os.path.exists(arquivo) and os.path.getsize(arquivo) > TAMANHO_MAX:
                os.replace(arquivo, arquivo + ".1")
            with open(arquivo, "a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except OSError:
        pass  # a trilha é secundária: nunca impede a ação


def listar(limite: int = 200) -> List[Dict[str, Any]]:
    """Mais recentes primeiro, com o rótulo legível de cada ação."""
    arquivo = _arquivo()
    if not os.path.exists(arquivo):
        return []
    with open(arquivo, encoding="utf-8") as f:
        linhas = f.readlines()[-limite:]
    saida = []
    for linha in reversed(linhas):
        try:
            r = json.loads(linha)
        except ValueError:
            continue
        r["rotulo"] = ROTULOS_ACOES.get(r.get("acao"), r.get("acao"))
        r["descricao"] = descrever(r)
        saida.append(r)
    return saida


def descrever(r: Dict[str, Any]) -> str:
    acao = r.get("acao")
    if acao == "aviso_aceito":
        return f"versão do texto {r.get('hash_aviso', '?')} · programa {r.get('versao', '?')}"
    if acao == "execucao_iniciada":
        modo = "somente monitoramento" if r.get("modo") == "monitoramento" else (
            "matrícula em DRY RUN" if r.get("dry_run") else "MATRÍCULA REAL")
        if r.get("demo"):
            modo = "DEMONSTRAÇÃO (SIGAA simulado) · " + modo
        return f"{modo} · {r.get('disciplinas', '?')} disciplina(s) · {r.get('num_workers', '?')} worker(s)"
    if acao == "configuracao_alterada":
        partes = [f"{m['chave']}: {m['de']} → {m['para']}" if "de" in m else m["chave"] for m in r.get("mudancas_det", [])]
        return ", ".join(partes) or ", ".join(r.get("chaves", []))
    if acao == "disciplinas_alteradas":
        return f"{r.get('antes', '?')} → {r.get('depois', '?')} disciplina(s)"
    if acao in ("perfil_aplicado", "perfil_salvo", "perfil_apagado"):
        return str(r.get("perfil", ""))
    return str(r.get("detalhe", "") or "")


def mudancas_settings(antes: Dict[str, Any], depois: Dict[str, Any]) -> List[Dict[str, Any]]:
    mudancas = []
    for chave in sorted(set(antes) | set(depois)):
        if chave == "versao" or antes.get(chave) == depois.get(chave):
            continue
        if chave in VALORES_SEGUROS:
            mudancas.append({"chave": chave, "de": antes.get(chave), "para": depois.get(chave)})
        else:
            mudancas.append({"chave": chave})
    return mudancas


def registrar_mudancas_settings(antes: Dict[str, Any], depois: Dict[str, Any]) -> None:
    mudancas = mudancas_settings(antes, depois)
    if not mudancas:
        return
    # Detalhes aninhados não passam pelo filtro de tipos de registrar(); os valores
    # já vêm só das chaves seguras (mudancas_settings).
    detalhe = [{k: (str(v) if v is not None else "—") for k, v in m.items()} for m in mudancas]
    _gravar({"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "acao": "configuracao_alterada", "origem": _origem,
             "chaves": [m["chave"] for m in mudancas], "mudancas_det": detalhe})


def hash_aviso_legal() -> str:
    """Identifica a versão exata do texto aceito (texto completo + confirmações)."""
    from app.core.disclaimer import CONFIRMACOES, TEXTO_COMPLETO
    conteudo = TEXTO_COMPLETO + "\n" + "\n".join(f"{c}:{t}" for c, t in CONFIRMACOES)
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:12]


def registrar_aceite_aviso() -> None:
    from app.versao import VERSAO_APP
    registrar("aviso_aceito", hash_aviso=hash_aviso_legal(), versao=VERSAO_APP)


def registrar_inicio(settings: Dict[str, Any], qtd_disciplinas: int, execucao_id: Optional[str] = None) -> None:
    registrar("execucao_iniciada", modo=settings.get("modo"), dry_run=bool(settings.get("dry_run", True)),
              num_workers=settings.get("num_workers"), disciplinas=qtd_disciplinas, execucao_id=execucao_id)
