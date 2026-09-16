"""
Tradutor de eventos de log para linguagem humana — seções 18-22 do pedido de
continuação.

Pega um registro cru do log JSON Lines (o mesmo formato que app/core/engine.py
grava) e devolve uma explicação em português simples, sem jargão técnico,
mais uma categoria para filtragem. Os detalhes técnicos (worker, timestamp,
mensagem original) continuam disponíveis à parte para quem quiser — nunca é
apagado, só reorganizado em dois níveis (seção 22).

Regra de segurança: as mensagens que o motor já gera NUNCA incluem o valor de
senha/CPF/data de nascimento — só o nome do campo do formulário (ex: "Senha
mapeada: j_id123:senha"). Por isso este tradutor não precisa (e não tenta)
redigir segredos depois do fato — a garantia já vem de onde o log é gerado
(app/core/engine.py). Ver docs/SEGURANCA.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

CATEGORIAS = [
    "SISTEMA", "REDE", "SEGURANCA", "MATRICULA", "MONITORAMENTO",
    "NOTIFICACAO", "SUCESSO", "AVISO", "ERRO", "DEBUG",
]


@dataclass
class EventoHumano:
    titulo: str
    corpo: str
    categoria: str
    nivel: str  # INFO/WARNING/ERROR/CRITICAL — vem direto do log original
    worker: str
    timestamp: str
    mensagem_original: str


def _extrair(padrao: str, texto: str, grupo: int = 1) -> Optional[str]:
    m = re.search(padrao, texto)
    return m.group(grupo) if m else None


def traduzir(registro: dict) -> EventoHumano:
    msg = registro.get("message", "")
    worker = registro.get("worker", "MAIN")
    nivel = registro.get("level", "INFO")
    ts = registro.get("timestamp", "")

    titulo, corpo, categoria = _interpretar(msg, worker)

    return EventoHumano(
        titulo=titulo, corpo=corpo, categoria=categoria,
        nivel=nivel, worker=worker, timestamp=ts, mensagem_original=msg,
    )


def _interpretar(msg: str, worker: str) -> tuple:
    """Retorna (titulo, corpo, categoria). Cai num fallback genérico e honesto
    quando a mensagem não bate com nenhum padrão conhecido — nunca inventa
    uma explicação que a mensagem não sustenta."""

    if "SESSAO_INICIADA" in msg:
        m = re.search(r"id=(\S+)", msg)
        return ("Nova execução iniciada", f"O programa começou uma nova execução{f' (ID: {m.group(1)})' if m else ''}.", "SISTEMA")

    if "🔍 Buscando" in msg:
        alvo = _extrair(r"Buscando ([A-Z0-9-]+)", msg) or "uma disciplina"
        return (f"Consultando {alvo}", f"{worker} está verificando se há vagas disponíveis em {alvo} agora.", "MONITORAMENTO")

    if "📉 Sem vagas" in msg:
        ms = _extrair(r"\((\d+)ms\)", msg)
        tempo = f" (resposta em {ms} milissegundos)" if ms else ""
        return ("Sem vagas no momento", f"O SIGAA respondeu normalmente{tempo}. Nenhuma vaga disponível nesta consulta — o programa vai verificar de novo em breve.", "MONITORAMENTO")

    if "🚨 VAGA DETECTADA" in msg:
        alvo = _extrair(r"-> ([A-Z0-9-]+)", msg) or "uma disciplina"
        vagas = _extrair(r"\((\d+) vaga", msg)
        return (f"Vaga encontrada em {alvo}!", f"O SIGAA indicou {vagas or 'pelo menos uma'} vaga disponível em {alvo}. O programa vai agir de acordo com o modo configurado (matrícula automática ou apenas monitoramento).", "SUCESSO")

    if "🎯 ASSUMINDO O TIRO" in msg:
        alvo = _extrair(r"PARA ([A-Z0-9-]+)", msg) or ""
        return (f"Tentando garantir a vaga em {alvo}", f"{worker} foi o primeiro a chegar nesta vaga e está tentando confirmar a matrícula antes que ela desapareça.", "MATRICULA")

    if "🔒 Outro worker já está atirando" in msg:
        return ("Outro atirador já está nessa vaga", f"{worker} viu a mesma vaga, mas outro worker já está tentando confirmá-la — para evitar conflito, {worker} deixa esse pra ele e segue procurando outras.", "MATRICULA")

    if "🔒 DRY RUN ATIVO" in msg or "DRY RUN" in msg and "Abortando" in msg:
        return ("DRY RUN: matrícula NÃO confirmada", "O modo de teste está ativo. O programa preparou tudo até o passo final, mas não enviou a confirmação de verdade — nada mudou na sua grade.", "SISTEMA")

    if "🎉 SUCESSO ABSOLUTO" in msg:
        alvo = _extrair(r"em ([A-Z0-9-]+)", msg) or ""
        return (f"Matrícula confirmada em {alvo}!", "O SIGAA confirmou a matrícula de verdade. Essa disciplina não será mais monitorada.", "SUCESSO")

    if "🧪 DRY RUN SUCESSO" in msg:
        alvo = _extrair(r"em ([A-Z0-9-]+)", msg) or ""
        return (f"[TESTE] Matrícula simulada em {alvo}", "Em modo DRY RUN, todo o processo funcionou até o fim — se fosse a execução real, a matrícula teria sido confirmada agora.", "SISTEMA")

    if "🛑 REMOVIDO" in msg:
        alvo = _extrair(r"REMOVIDO: A UnB bloqueou ([A-Z0-9-]+)", msg) or ""
        return (f"{alvo} bloqueada pelo SIGAA", "O SIGAA recusou a matrícula por um motivo definitivo (pré-requisito não cumprido, choque de horário, ou limite de créditos). O programa parou de tentar essa disciplina específica — as outras continuam sendo monitoradas.", "AVISO")

    if "❌ Falha técnica" in msg:
        return ("Tentativa não deu certo, tentando de novo", "Algo deu errado ao tentar confirmar a matrícula, mas não foi um bloqueio definitivo. O programa vai continuar procurando e tentará de novo automaticamente.", "AVISO")

    if "⏳ Timeout" in msg:
        return ("Conexão demorou demais", f"{worker} esperou a resposta do SIGAA por tempo demais e desistiu dessa tentativa. Ação: o programa está reiniciando a conexão e vai tentar de novo automaticamente.", "REDE")

    if "🔌 Falha de rede" in msg:
        tipo = _extrair(r"\(([A-Za-z]+)\)", msg) or ""
        return ("Problema de conexão com a internet/SIGAA", f"{worker} não conseguiu se comunicar com o SIGAA ({tipo or 'erro de rede'}). Ação: o programa está reconectando automaticamente.", "REDE")

    if "⚠️ Sessão corrompida" in msg:
        return ("Sessão expirada, entrando de novo", f"{worker} percebeu que a sessão de login expirou ou foi encerrada pelo SIGAA. Ação: fazendo login novamente automaticamente.", "SEGURANCA")

    if "✅ Login concluído" in msg:
        return ("Login realizado com sucesso", f"{worker} entrou no SIGAA normalmente e está pronto para monitorar.", "SISTEMA")

    if "💥" in msg:
        return ("Erro inesperado", f"{worker} encontrou um problema que não era esperado. Ação: o programa está se recuperando automaticamente (reiniciando a conexão) e vai continuar funcionando.", "ERRO")

    if any(campo in msg for campo in ("Senha mapeada", "CPF injetado", "Data de Nascimento injetada", "Campo desconhecido preenchido")):
        return ("Preenchendo dados de confirmação", "O programa está preenchendo o formulário de confirmação de matrícula com seus dados (nenhum valor sensível aparece neste log — só o nome do campo do formulário).", "SEGURANCA")

    if "Falha ao enviar notificação" in msg or "Notificação de" in msg:
        return ("Aviso sobre notificações", "Houve um problema ao tentar enviar uma notificação (Telegram/ntfy/alarme). Isso NÃO afeta o monitoramento — ele continua funcionando normalmente.", "NOTIFICACAO")

    if "Teleportando" in msg:
        return ("Preparando busca no departamento", f"{worker} está acessando a página de busca de turmas do departamento configurado.", "MONITORAMENTO")

    # Fallback honesto: não finge entender o que não reconhece.
    return ("Evento do sistema", msg, "DEBUG")
