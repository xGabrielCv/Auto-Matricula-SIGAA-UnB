"""
Assistente de solução de problemas e recomendações de configuração
(Fase 5 — sugestões 079 e 089).

O assistente conecta SINTOMAS a CAUSAS PROVÁVEIS usando o que o programa já
sabe: a execução atual (ou a última gravada), os erros por categoria, os alertas,
o resultado da verificação prévia, a classificação das respostas do SIGAA e o
detector de configurações inseguras. Cada achado traz a evidência ("visto:
12 logins recusados"), a causa e a ação — nunca um palpite sem evidência, a não
ser como "verificação sugerida" marcada como tal.

As recomendações olham as métricas de uma execução e sugerem ajustes que PASSAM
PELA VALIDAÇÃO NORMAL antes de serem salvos (quem aplica é a interface).
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional

SINTOMAS: Dict[str, str] = {
    "login": "O login não funciona / a execução para logo no início",
    "turma": "O programa não encontra minha disciplina ou turma",
    "vagas": "Nunca aparece vaga",
    "erros": "Muitos erros, lentidão ou o SIGAA parece fora do ar",
    "confirmacao": "Achou vaga, mas a matrícula não confirma",
    "parou": "O programa parou sozinho",
}


def _contexto(settings: Dict[str, Any], disciplinas: List[Any], credenciais: Any = None,
              snap: Optional[Dict[str, Any]] = None, ultima: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Normaliza a fonte: execução em andamento/recém-encerrada (snapshot) ou a última gravada (resumo)."""
    erros: Dict[str, int] = {}
    requisicoes, motivo_fim, alvos, alertas, tentativas = 0, None, [], [], []
    lat_media = None
    if snap:
        tel = snap.get("telemetria") or {}
        erros = {c: v.get("total", 0) for c, v in (tel.get("erros") or {}).items()}
        requisicoes = tel.get("requisicoes", 0)
        motivo_fim = snap.get("motivo_fim")
        alvos = snap.get("alvos") or []
        alertas = (snap.get("alertas") or {}).get("ativos", []) + (snap.get("alertas") or {}).get("historico", [])
        tentativas = snap.get("tentativas") or []
        lat_media = (tel.get("latencia") or {}).get("media")
        fonte = "a execução atual" if snap.get("fase") != "encerrado" else "a execução que acabou de terminar"
    elif ultima:
        erros = dict(ultima.get("erros") or {})
        requisicoes = (ultima.get("totais") or {}).get("requisicoes", 0)
        motivo_fim = ultima.get("motivo_fim")
        alvos = ultima.get("alvos") or []
        alertas = ultima.get("alertas") or []
        tentativas = ultima.get("tentativas") or []
        lat_media = (ultima.get("latencia_ms") or {}).get("media")
        fonte = f"a última execução ({ultima.get('inicio', '?')})"
    else:
        fonte = ""
    return {"settings": settings, "disciplinas": disciplinas, "credenciais": credenciais, "erros": erros,
            "requisicoes": requisicoes, "motivo_fim": motivo_fim, "alvos": alvos, "alertas": alertas,
            "tentativas": tentativas, "lat_media": lat_media, "fonte": fonte, "tem_dados": bool(snap or ultima)}


def _achado(causa: str, acao: str, evidencia: str = "", tela: str = "", certeza: str = "provavel") -> Dict[str, str]:
    return {"causa": causa, "acao": acao, "evidencia": evidencia, "tela": tela, "certeza": certeza}


def _credenciais(ctx) -> List[Dict[str, str]]:
    cred = ctx["credenciais"]
    if cred is None:
        return []
    if not cred.preenchida():
        return [_achado("As credenciais do SIGAA não estão preenchidas nesta sessão.",
                        "Preencha matrícula, senha, CPF e data de nascimento na tela Credenciais.", "credenciais vazias",
                        "credenciais", "certa")]
    return [_achado(p, "Corrija na tela Credenciais.", "conferência local", "credenciais", "certa") for p in cred.problemas()]


def _regras_login(ctx) -> List[Dict[str, str]]:
    achados = _credenciais(ctx)
    motivo = ctx["motivo_fim"]
    if motivo == "login_recusado" or ctx["erros"].get("login", 0) and motivo == "sem_workers":
        achados.append(_achado("O SIGAA recusou o login.", "Confira matrícula e senha (entre no SIGAA pelo navegador para "
                               "testar). O programa não insiste para não bloquear a sua conta.",
                               f"{ctx['fonte']} terminou com login recusado", "credenciais", "certa"))
    elif ctx["erros"].get("login"):
        achados.append(_achado("Falhas de login durante a execução.", "Se foram poucas, o SIGAA oscilou e o programa "
                               "entrou de novo sozinho. Se forem muitas, confira a senha e rode o teste de conectividade.",
                               f"{ctx['erros']['login']} falha(s) de login em {ctx['fonte']}", "diagnostico"))
    if ctx["erros"].get("rede") or ctx["erros"].get("timeout"):
        achados.append(_achado("Problemas de conexão até o SIGAA.", "Rode Diagnóstico → Testar conectividade em camadas.",
                               f"{ctx['erros'].get('rede', 0)} falha(s) de rede e {ctx['erros'].get('timeout', 0)} "
                               f"tempo(s) esgotado(s)", "diagnostico"))
    return achados


def _regras_turma(ctx) -> List[Dict[str, str]]:
    achados = []
    for a in ctx["alvos"]:
        v = a.get("verificacao") or {}
        if v.get("resultado") and v["resultado"] != "ok":
            achados.append(_achado(f"{a['chave']}: {v.get('texto')}.", "Confira código, turma e departamento na tela "
                                   "Disciplinas (a turma é o número, ex: 01).", "verificação prévia", "disciplinas", "certa"))
        elif a.get("estado") == "departamento_indisponivel":
            achados.append(_achado(f"{a['chave']}: a busca no departamento {a.get('departamento')} não abriu.",
                                   "Fora do período de matrícula extraordinária, ou o código do departamento está errado.",
                                   "estado da disciplina", "disciplinas"))
    ativas = [d for d in ctx["disciplinas"] if getattr(d, "ativa", True)]
    if not ativas:
        achados.append(_achado("Nenhuma disciplina ativa.", "Adicione ou ative disciplinas na tela Disciplinas.",
                               "lista de disciplinas", "disciplinas", "certa"))
    if not achados:
        achados.append(_achado("Verificação sugerida: deixe a verificação prévia ligada e inicie uma execução.",
                               "Ela confere, antes de começar, se cada disciplina e turma aparece na lista do departamento.",
                               "", "execucao", "sugestao"))
    return achados


def _regras_vagas(ctx) -> List[Dict[str, str]]:
    achados = _regras_turma(ctx) if any((a.get("verificacao") or {}).get("resultado", "ok") != "ok" for a in ctx["alvos"]) else []
    buscas = sum(a.get("buscas", 0) for a in ctx["alvos"])
    if ctx["tem_dados"] and buscas and not any(a.get("vagas_vistas") for a in ctx["alvos"]):
        achados.append(_achado("As buscas estão funcionando, mas nenhuma vaga abriu até agora.",
                               "É o cenário normal na maior parte do tempo. Veja no Histórico o mapa de horários em que "
                               "vagas costumam abrir.", f"{buscas} leitura(s) sem vaga em {ctx['fonte']}", "historico"))
    if not achados:
        achados.append(_achado("Ainda não há execução para analisar.", "Inicie uma execução (de preferência com DRY RUN) e "
                               "volte aqui depois de alguns minutos.", "", "execucao", "sugestao"))
    return achados


def _regras_erros(ctx) -> List[Dict[str, str]]:
    from app.core.telemetria import ACOES_ERRO, ROTULOS_ERRO
    achados = []
    total = max(1, ctx["requisicoes"])
    for cat, qtd in sorted(ctx["erros"].items(), key=lambda x: -x[1]):
        if qtd and (qtd / total >= 0.05 or qtd >= 20):
            achados.append(_achado(f"{ROTULOS_ERRO.get(cat, cat)}: {qtd} ocorrência(s) ({100 * qtd / total:.0f}% das buscas).",
                                   ACOES_ERRO.get(cat, "Veja os detalhes na Central de Logs."), ctx["fonte"], "dashboard"))
    for a in ctx["alertas"]:
        if a.get("estado", "ativo") == "ativo":
            achados.append(_achado(f"{a.get('titulo')}: {a.get('texto')}", "Veja o gráfico de erros e de tempo de resposta "
                                   "no Dashboard.", "alerta registrado", "dashboard"))
    for r in recomendar_configuracao(ctx):
        achados.append(_achado(r["texto"], r["motivo"], "métricas da execução", "avancado"))
    if not achados:
        achados.append(_achado("Nenhum erro relevante registrado." if ctx["tem_dados"] else "Ainda não há execução para analisar.",
                               "Rode o Diagnóstico completo e o teste de conectividade em camadas.", ctx["fonte"],
                               "diagnostico", "sugestao"))
    return achados


def _regras_confirmacao(ctx) -> List[Dict[str, str]]:
    achados = _credenciais(ctx)
    falhas = [t for t in ctx["tentativas"] if t.get("resultado") not in ("SUCESSO", None)]
    for t in falhas[-3:]:
        etapas = [e.get("etapa") for e in t.get("etapas", [])]
        if "selecao_enviada" in etapas and "tela_confirmacao" not in etapas:
            causa = "Depois de selecionar a turma, a tela de confirmação não veio."
            acao = "A vaga pode ter acabado no meio do caminho. A página capturada (mascarada) está em Diagnóstico → Páginas."
        elif "confirmacao_enviada" in etapas:
            causa = "O SIGAA recebeu a confirmação e recusou."
            acao = "Veja a mensagem do SIGAA na Central de Logs (evento 'Resposta do SIGAA classificada')."
        else:
            causa = "A tentativa parou antes de enviar a confirmação."
            acao = "Veja a página capturada em Diagnóstico → Páginas capturadas."
        achados.append(_achado(f"Tentativa {t.get('id')} em {t.get('chave')}: {causa}", acao,
                               f"etapas: {', '.join(etapas) or 'nenhuma'} · {t.get('total_ms')} ms", "diagnostico", "certa"))
    if ctx["motivo_fim"] in ("dados_incorretos",):
        achados.append(_achado("O SIGAA disse que os dados da confirmação estão incorretos.",
                               "Confira CPF e data de nascimento na tela Credenciais.", "motivo de encerramento",
                               "credenciais", "certa"))
    if ctx["erros"].get("confirmacao"):
        achados.append(_achado(f"{ctx['erros']['confirmacao']} falha(s) na confirmação.",
                               "Veja as páginas capturadas (mascaradas) em Diagnóstico.", ctx["fonte"], "diagnostico"))
    if ctx["settings"].get("modo") == "monitoramento":
        achados.append(_achado("O modo é SOMENTE MONITORAMENTO.", "Nesse modo o programa avisa, mas nunca se matricula. "
                               "Troque o modo na tela Execução se quiser a matrícula automática.", "configuração",
                               "execucao", "certa"))
    elif ctx["settings"].get("dry_run", True):
        achados.append(_achado("O DRY RUN está ligado: a matrícula é simulada de propósito.",
                               "Desligue o DRY RUN na tela Execução quando quiser a matrícula real.", "configuração",
                               "execucao", "certa"))
    if not achados:
        achados.append(_achado("Nenhuma tentativa de matrícula registrada ainda.", "Quando houver, cada etapa e o tempo dela "
                               "aparecem aqui e na Linha do tempo.", "", "dashboard", "sugestao"))
    return achados


def _regras_parou(ctx) -> List[Dict[str, str]]:
    from app.core.relatorios import MOTIVOS_FIM
    motivo = ctx["motivo_fim"]
    if not motivo:
        return [_achado("Não há execução encerrada para analisar.", "Veja o Histórico para execuções anteriores.", "",
                        "historico", "sugestao")]
    texto = MOTIVOS_FIM.get(motivo, motivo)
    acoes = {
        "login_recusado": ("Confira matrícula e senha.", "credenciais"),
        "sem_workers": ("Nenhum worker conseguiu continuar. Confira as credenciais e rode o teste de conectividade.", "diagnostico"),
        "dados_incorretos": ("Confira CPF e data de nascimento.", "credenciais"),
        "periodo_encerrado": ("O período de matrícula terminou; não há o que fazer até o próximo.", ""),
        "fim_agendado": ("Terminou no horário de término configurado — comportamento esperado.", "execucao"),
        "concluida": ("Todas as disciplinas foram processadas — comportamento esperado.", "dashboard"),
        "interrompida": ("Parada pedida pelo usuário.", ""),
        "erro": ("Erro inesperado. Gere o pacote de suporte em Diagnóstico.", "diagnostico"),
    }
    acao, tela = acoes.get(motivo, ("Veja a Central de Logs.", "logs"))
    return [_achado(f"Motivo registrado: {texto}.", acao, ctx["fonte"], tela, "certa")]


REGRAS: Dict[str, Callable[[Dict[str, Any]], List[Dict[str, str]]]] = {
    "login": _regras_login, "turma": _regras_turma, "vagas": _regras_vagas,
    "erros": _regras_erros, "confirmacao": _regras_confirmacao, "parou": _regras_parou,
}


def diagnosticar(sintoma: str, settings: Dict[str, Any], disciplinas: List[Any], credenciais: Any = None,
                 snap: Optional[Dict[str, Any]] = None, ultima: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if sintoma not in REGRAS:
        raise ValueError("Sintoma desconhecido.")
    from app.core.seguranca_config import alertas_de_configuracao
    ctx = _contexto(settings, disciplinas, credenciais, snap, ultima)
    achados = REGRAS[sintoma](ctx)
    if sintoma in ("login", "erros"):
        for a in alertas_de_configuracao(settings, max(1, len(disciplinas))):
            if a["id"] in ("urls_fora_unb", "carga_alta", "protecao_desligada"):
                achados.append(_achado(a["titulo"] + ".", a["acao"], "configuração", a["tela"], "certa"))
    ordem = {"certa": 0, "provavel": 1, "sugestao": 2}
    achados.sort(key=lambda x: ordem.get(x["certeza"], 1))
    return {"sintoma": sintoma, "pergunta": SINTOMAS[sintoma], "fonte": ctx["fonte"], "achados": achados}


# ── Recomendações de configuração (089) ──────────────────────────────────

def recomendar_configuracao(ctx_ou_settings: Dict[str, Any], snap: Optional[Dict[str, Any]] = None,
                            ultima: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Cada recomendação: {id, texto, motivo, ajuste: {chave: valor}}. Aceita um
    contexto pronto (uso interno) ou settings + snapshot/resumo."""
    ctx = ctx_ou_settings if "erros" in ctx_ou_settings and "settings" in ctx_ou_settings else \
        _contexto(ctx_ou_settings, [], None, snap, ultima)
    s = ctx["settings"]
    req = ctx["requisicoes"]
    if req < 100:
        return []  # pouca amostra: melhor não recomendar nada
    erros = ctx["erros"]
    recs: List[Dict[str, Any]] = []
    workers, timeout = int(s.get("num_workers", 20)), int(s.get("timeout_req", 10))

    if erros.get("timeout", 0) / req >= 0.25 and timeout < 30:
        novo = min(30, timeout + 5)
        recs.append({"id": "timeout", "texto": f"Aumentar o timeout de {timeout} s para {novo} s.",
                     "motivo": f"{100 * erros['timeout'] / req:.0f}% das buscas esgotaram o tempo: o SIGAA está respondendo "
                               "devagar, e desistir cedo demais só gera nova tentativa.",
                     "ajuste": {"timeout_req": novo}})
    carga_ruim = (erros.get("sobrecarga", 0) + erros.get("sessao", 0)) / req
    if carga_ruim >= 0.05 and workers > 4:
        novo = max(4, workers // 2)
        recs.append({"id": "menos_workers_sobrecarga", "texto": f"Reduzir os workers de {workers} para {novo}.",
                     "motivo": f"{100 * carga_ruim:.0f}% das buscas terminaram em sobrecarga ou sessão encerrada pelo SIGAA — "
                               "sinal de carga alta demais.", "ajuste": {"num_workers": novo}})
    elif ctx["lat_media"] and workers > 4:
        # Workers necessários para o ritmo observado: ritmo × (tempo de resposta + intervalo).
        lat_s = ctx["lat_media"] / 1000
        limite = float((s.get("protecao") or {}).get("limite_req_por_seg") or 0)
        if limite > 0:
            necessarios = math.ceil(limite * (lat_s + float(s.get("intervalo_busca", 0.3)))) + 1
            if workers >= 1.5 * necessarios and workers - necessarios >= 3:
                recs.append({"id": "workers_sem_ganho", "texto": f"Usar {necessarios} workers em vez de {workers}.",
                             "motivo": f"Com respostas de ~{ctx['lat_media']:.0f} ms e o teto de {limite:g} buscas/s, "
                                       f"{necessarios} workers já alcançam o ritmo máximo; os outros só ficam esperando "
                                       "e fazem logins a mais.", "ajuste": {"num_workers": necessarios}})
    if s.get("modo") == "monitoramento" and workers > 8:
        recs.append({"id": "monitoramento_leve", "texto": "Usar o perfil Leve para só monitorar.",
                     "motivo": "No modo somente monitoramento a velocidade não decide nada; o perfil Leve dá o mesmo "
                               "resultado com bem menos carga no SIGAA.", "ajuste": {"num_workers": 4, "intervalo_busca": 1.5}})
    return recs


def aplicar_recomendacao(settings: Dict[str, Any], recomendacao: Dict[str, Any]) -> List[str]:
    """Aplica o ajuste numa CÓPIA, valida e só então copia para `settings`. Devolve os problemas (vazio = aplicado)."""
    from app.core.config import validar_settings
    copia = dict(settings)
    copia.update(recomendacao.get("ajuste") or {})
    problemas = validar_settings(copia)
    if not problemas:
        settings.update(recomendacao.get("ajuste") or {})
        from app.core import auditoria
        auditoria.registrar("recomendacao_aplicada", detalhe=str(recomendacao.get("texto", "")))
    return problemas
