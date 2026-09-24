"""
Assistente de configuração inicial — regra única para a Web e a interface gráfica.

As duas interfaces mostram as mesmas etapas e pedem a validação daqui antes de
avançar; a aplicação final também passa por aqui (e de novo pela validação).
Etapas (todas podem ser deixadas como estão, exceto quando algo foi preenchido
de forma inválida):

  1. credenciais   — matrícula, senha, CPF, nascimento (só em memória);
  2. disciplinas   — código, turma, departamento, grupo e prioridade;
  3. execucao      — modo, DRY RUN, perfil de carga, verificação prévia;
  4. notificacoes  — notificação do Windows, webhook, e-mail;
  5. paineis       — carregar a última execução ao abrir, abrir o dashboard ao iniciar;
  6. revisao       — resumo; só aqui algo é salvo.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple

from app.core.config import (
    PRESETS_CARGA, PRIORIDADES, Disciplina, analisar_disciplina, salvar_disciplinas, salvar_segredos_notificacao,
    salvar_settings, validar_settings,
)
from app.core.validadores import (
    normalizar_cpf, problema_cpf, problema_nascimento_texto, problema_url_webhook, problemas_email_cfg,
)

ETAPAS = [
    ("boas_vindas", "Boas-vindas"), ("credenciais", "Credenciais"), ("disciplinas", "Disciplinas"),
    ("execucao", "Execução"), ("notificacoes", "Notificações"), ("paineis", "Painéis"), ("revisao", "Revisão"),
]


def _bool(v: Any) -> bool:
    return v is True or (isinstance(v, str) and v.lower() in ("1", "true", "sim", "on"))


def validar_credenciais(c: Dict[str, Any]) -> List[str]:
    campos = {k: str(c.get(k, "") or "").strip() for k in ("usuario", "senha", "cpf", "nascimento")}
    if not any(campos.values()):
        return []  # pode deixar para depois
    problemas = []
    if not campos["usuario"]:
        problemas.append("Informe a matrícula (usuário do SIGAA).")
    if not campos["senha"]:
        problemas.append("Informe a senha do SIGAA.")
    for validar in ((problema_cpf, campos["cpf"]), (problema_nascimento_texto, campos["nascimento"])):
        p = validar[0](validar[1])
        if p:
            problemas.append(p)
    return problemas


def disciplina_de_dados(d: Dict[str, Any]) -> Tuple[Disciplina, List[str]]:
    try:
        depto = int(str(d.get("departamento", "")).strip() or 0)
    except ValueError:
        return Disciplina("", "", 0), ["O departamento deve ser o número (código) do departamento — use \"Ver departamentos\" para escolher."]
    prioridade = str(d.get("prioridade") or "normal").strip().lower()
    nova = Disciplina(codigo=str(d.get("codigo", "")).strip().upper(), turma=str(d.get("turma", "")).strip(),
                      departamento=depto, grupo=str(d.get("grupo", "") or "").strip()[:40], prioridade=prioridade)
    return nova, []


def validar_disciplina(d: Dict[str, Any], existentes: List[Disciplina]) -> Tuple[List[str], List[str]]:
    nova, problemas = disciplina_de_dados(d)
    if problemas:
        return problemas, []
    return analisar_disciplina(nova, existentes)


def validar_execucao(e: Dict[str, Any]) -> List[str]:
    problemas = []
    if e.get("modo", "monitoramento") not in ("matricula", "monitoramento"):
        problemas.append("Escolha um modo de operação.")
    if e.get("preset", "leve") not in PRESETS_CARGA:
        problemas.append("Escolha um perfil de carga.")
    return problemas


def validar_notificacoes(n: Dict[str, Any]) -> List[str]:
    problemas = []
    if _bool(n.get("webhook_ativo")):
        p = problema_url_webhook(str(n.get("webhook_url", "")))
        if p:
            problemas.append(p)
    if _bool(n.get("email_ativo")):
        cfg = dict(n.get("email") or {})
        try:
            cfg["porta"] = int(str(cfg.get("porta", 587)).strip() or 587)
        except ValueError:
            cfg["porta"] = -1
        problemas.extend(problemas_email_cfg(cfg, str(n.get("email_senha", ""))))
    return problemas


def validar_etapa(etapa: str, dados: Dict[str, Any], existentes: List[Disciplina]) -> Dict[str, Any]:
    """{"problemas": [...], "avisos": [...]} — vazio = pode avançar."""
    avisos: List[str] = []
    if etapa == "credenciais":
        problemas = validar_credenciais(dados)
        if not problemas and not any(str(v or "").strip() for v in dados.values()):
            avisos.append("Credenciais em branco: tudo bem, preencha depois na tela Credenciais (elas nunca são salvas em disco).")
    elif etapa == "disciplina":
        problemas, avisos = validar_disciplina(dados, existentes)
    elif etapa == "execucao":
        problemas = validar_execucao(dados)
    elif etapa == "notificacoes":
        problemas = validar_notificacoes(dados)
    else:
        problemas = []
    return {"problemas": problemas, "avisos": avisos}


def aplicar(dados: Dict[str, Any], settings: Dict[str, Any], disciplinas: List[Disciplina], sessao: Any
            ) -> Tuple[Dict[str, Any], List[Disciplina], List[str]]:
    """Valida TUDO de novo e aplica. Devolve (settings, disciplinas, problemas);
    com problemas, nada é salvo."""
    problemas: List[str] = []
    cred = dados.get("credenciais") or {}
    problemas += validar_credenciais(cred)
    novas = list(disciplinas)
    for d in dados.get("disciplinas") or []:
        erros, _ = validar_disciplina(d, novas)
        if erros:
            problemas += [f"{str(d.get('codigo', '')).upper()}-{d.get('turma', '')}: {e}" for e in erros]
            continue
        novas.append(disciplina_de_dados(d)[0])
    execucao = dados.get("execucao") or {}
    problemas += validar_execucao(execucao)
    notif = dados.get("notificacoes") or {}
    problemas += validar_notificacoes(notif)
    if problemas:
        return settings, disciplinas, problemas

    s = copy.deepcopy(settings)
    s["modo"] = execucao.get("modo", s.get("modo", "monitoramento"))
    s["dry_run"] = True if s["modo"] == "monitoramento" else _bool(execucao.get("dry_run", True))
    preset = PRESETS_CARGA[execucao.get("preset", "leve")]
    s["num_workers"], s["intervalo_busca"] = preset["num_workers"], preset["intervalo_busca"]
    s["verificacao_previa"] = _bool(execucao.get("verificacao_previa", True))
    cfg_n = s["notificacoes"]
    cfg_n["windows_ativo"] = _bool(notif.get("windows_ativo"))
    cfg_n["webhook_ativo"] = _bool(notif.get("webhook_ativo"))
    if notif.get("webhook_formato") in ("discord", "slack", "json"):
        cfg_n["webhook_formato"] = notif["webhook_formato"]
    cfg_n["email_ativo"] = _bool(notif.get("email_ativo"))
    if cfg_n["email_ativo"]:
        e = notif.get("email") or {}
        cfg_n["email"] = {"servidor": str(e.get("servidor", "")).strip(), "porta": int(str(e.get("porta", 587)) or 587),
                          "usuario": str(e.get("usuario", "")).strip(), "destinatario": str(e.get("destinatario", "")).strip(),
                          "remetente": str(e.get("remetente", "") or "").strip(),
                          "seguranca": "ssl" if e.get("seguranca") == "ssl" else "starttls"}
    paineis = dados.get("paineis") or {}
    s["carregar_ultima_execucao"] = _bool(paineis.get("carregar_ultima_execucao"))
    s["abrir_dashboard_ao_iniciar"] = _bool(paineis.get("abrir_dashboard_ao_iniciar", True))
    s["assistente_concluido"] = True
    problemas = validar_settings(s)
    if problemas:
        return settings, disciplinas, problemas

    if any(str(v or "").strip() for v in cred.values()):
        sessao.sigaa.usuario = str(cred.get("usuario", "")).strip()
        sessao.sigaa.senha = str(cred.get("senha", ""))
        sessao.sigaa.cpf = normalizar_cpf(str(cred.get("cpf", "")))
        from app.core.credentials import normalizar_nascimento
        sessao.sigaa.nascimento = normalizar_nascimento(str(cred.get("nascimento", "")))
    if cfg_n["webhook_ativo"]:
        sessao.notificacao.webhook_url = str(notif.get("webhook_url", "")).strip()
    if cfg_n["email_ativo"]:
        sessao.notificacao.email_senha = str(notif.get("email_senha", ""))
    salvar_settings(s)
    salvar_disciplinas(novas)
    if _bool(notif.get("lembrar_segredos")) and (cfg_n["webhook_ativo"] or cfg_n["email_ativo"]):
        n = sessao.notificacao
        salvar_segredos_notificacao(n.telegram_token, n.telegram_chat_id, n.ntfy_topic, n.ntfy_servidor, n.webhook_url, n.email_senha)
    from app.core import auditoria
    auditoria.registrar("configuracao_inicial", disciplinas=len(novas) - len(disciplinas))
    return s, novas, []


def dispensar(settings: Dict[str, Any]) -> Dict[str, Any]:
    """"Configurar depois": o assistente não volta a abrir sozinho (reabre em Config. Avançadas)."""
    s = copy.deepcopy(settings)
    s["assistente_concluido"] = True
    salvar_settings(s)
    return s


def resumo(dados: Dict[str, Any]) -> List[str]:
    cred = dados.get("credenciais") or {}
    e = dados.get("execucao") or {}
    n = dados.get("notificacoes") or {}
    p = dados.get("paineis") or {}
    modo = "Somente monitoramento" if e.get("modo", "monitoramento") == "monitoramento" else (
        "Matrícula automática em DRY RUN (teste)" if _bool(e.get("dry_run", True)) else "Matrícula automática REAL")
    canais = [nome for nome, ativo in (("Windows", n.get("windows_ativo")), ("webhook", n.get("webhook_ativo")),
                                        ("e-mail", n.get("email_ativo"))) if _bool(ativo)]
    linhas = [
        f"Credenciais: {'preenchidas (só em memória)' if any(str(v or '').strip() for v in cred.values()) else 'preencher depois'}",
        f"Disciplinas novas: {len(dados.get('disciplinas') or [])}"
        + "".join(f"\n  • {str(d.get('codigo', '')).upper()}-{d.get('turma', '')} (depto {d.get('departamento')}"
                  + (f", grupo {d.get('grupo')}" if d.get("grupo") else "") + f", prioridade {d.get('prioridade') or 'normal'})"
                  for d in dados.get("disciplinas") or []),
        f"Modo: {modo} · perfil de carga {PRESETS_CARGA.get(e.get('preset', 'leve'), PRESETS_CARGA['leve'])['rotulo']}"
        + (" · verificação prévia" if _bool(e.get("verificacao_previa", True)) else ""),
        f"Notificações: {', '.join(canais) if canais else 'nenhuma (pode ativar depois)'}",
        f"Ao abrir: {'carregar dados da última execução' if _bool(p.get('carregar_ultima_execucao')) else 'painéis começam vazios'}",
    ]
    return linhas


PRIORIDADES_VALIDAS = PRIORIDADES
