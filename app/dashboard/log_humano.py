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


# Fases 4 e 5: eventos com mensagem já escrita para pessoas (título, categoria).
_EVENTOS_TEXTO_PRONTO = {
    "sigaa_sobrecarregado": ("SIGAA sobrecarregado", "REDE"),
    "sigaa_manutencao": ("SIGAA em manutenção", "REDE"),
    "disjuntor_aberto": ("Buscas pausadas: SIGAA instável", "REDE"),
    "disjuntor_fechado": ("SIGAA respondendo de novo", "REDE"),
    "execucao_pausada": ("Execução pausada", "SISTEMA"),
    "execucao_retomada": ("Execução retomada", "SISTEMA"),
    "parada_seguranca": ("Execução parada por segurança", "ERRO"),
    "grupo_dispensado": ("Turmas alternativas dispensadas", "MATRICULA"),
    "verificacao_previa": ("Verificação prévia", "SISTEMA"),
    "classificacao_resposta": ("Resposta do SIGAA classificada", "MATRICULA"),
    "relogio_sigaa": ("Relógio do SIGAA", "SISTEMA"),
    "alvo_adicionado": ("Disciplina adicionada", "SISTEMA"),
    "alvo_removido": ("Disciplina removida", "SISTEMA"),
    "fim_agendado": ("Horário de término atingido", "SISTEMA"),
    "alerta_limiar": ("Alerta", "AVISO"),
    "worker_reiniciado": ("Worker travado recriado", "AVISO"),
    "resposta_erro_sigaa": ("O SIGAA respondeu com erro", "MATRICULA"),
    "confirmacao_nao_detectada": ("Tela de confirmação não veio", "MATRICULA"),
}


def _extrair(padrao: str, texto: str, grupo: int = 1) -> Optional[str]:
    m = re.search(padrao, texto)
    return m.group(grupo) if m else None


def traduzir(registro: dict) -> EventoHumano:
    msg = registro.get("message", "")
    worker = registro.get("worker", "MAIN")
    nivel = registro.get("level", "INFO")
    ts = registro.get("timestamp", "")

    titulo, corpo, categoria = _interpretar(msg, worker, registro)

    return EventoHumano(
        titulo=titulo, corpo=corpo, categoria=categoria,
        nivel=nivel, worker=worker, timestamp=ts, mensagem_original=msg,
    )


def _interpretar(msg: str, worker: str, registro: Optional[dict] = None) -> tuple:
    """Retorna (titulo, corpo, categoria). Cai num fallback genérico e honesto
    quando a mensagem não bate com nenhum padrão conhecido — nunca inventa
    uma explicação que a mensagem não sustenta.

    Linhas gravadas desde a sugestão 053 trazem o campo `evento` e os valores
    em campos próprios (`codigo`, `turma`, `vagas`, `latencia_ms`...): eles
    têm prioridade. Sem eles (logs antigos), vale o texto da mensagem."""
    registro = registro or {}
    evento = registro.get("evento")

    def eh(nome_evento: str, *marcadores: str) -> bool:
        if evento:
            return evento == nome_evento
        return any(m in msg for m in marcadores)

    def alvo_de(padrao: str, padrao_vazio: str = "") -> str:
        if registro.get("codigo") and registro.get("turma"):
            return f"{registro['codigo']}-{registro['turma']}"
        return _extrair(padrao, msg) or padrao_vazio

    def campo(nome: str, padrao: str) -> Optional[str]:
        valor = registro.get(nome)
        if valor is not None:
            return str(int(valor)) if isinstance(valor, float) else str(valor)
        return _extrair(padrao, msg)

    if eh("sessao_iniciada", "SESSAO_INICIADA"):
        execucao = registro.get("execucao_id") or _extrair(r"id=(\S+)", msg)
        return ("Nova execução iniciada", f"O programa começou uma nova execução{f' (ID: {execucao})' if execucao else ''}.", "SISTEMA")

    if eh("busca", "🔍 Buscando"):
        alvo = alvo_de(r"Buscando ([A-Z0-9-]+)", "uma disciplina")
        return (f"Consultando {alvo}", f"{worker} está verificando se há vagas disponíveis em {alvo} agora.", "MONITORAMENTO")

    if eh("sem_vagas", "📉 Sem vagas"):
        ms = campo("latencia_ms", r"\((\d+)ms\)")
        tempo = f" (resposta em {ms} milissegundos)" if ms else ""
        return ("Sem vagas no momento", f"O SIGAA respondeu normalmente{tempo}. Nenhuma vaga disponível nesta consulta — o programa vai verificar de novo em breve.", "MONITORAMENTO")

    if eh("vaga_detectada", "🚨 VAGA DETECTADA"):
        alvo = alvo_de(r"-> ([A-Z0-9-]+)", "uma disciplina")
        vagas = campo("vagas", r"\((\d+) vaga")
        return (f"Vaga encontrada em {alvo}!", f"O SIGAA indicou {vagas or 'pelo menos uma'} vaga disponível em {alvo}. O programa vai agir de acordo com o modo configurado (matrícula automática ou apenas monitoramento).", "SUCESSO")

    if eh("tentativa_iniciada", "🎯 ASSUMINDO O TIRO"):
        alvo = alvo_de(r"PARA ([A-Z0-9-]+)")
        return (f"Tentando garantir a vaga em {alvo}", f"{worker} foi o primeiro a chegar nesta vaga e está tentando confirmar a matrícula antes que ela desapareça.", "MATRICULA")

    if eh("tiro_duplicado", "🔒 Outro worker já está atirando"):
        return ("Outro atirador já está nessa vaga", f"{worker} viu a mesma vaga, mas outro worker já está tentando confirmá-la — para evitar conflito, {worker} deixa esse pra ele e segue procurando outras.", "MATRICULA")

    if not evento and ("🔒 DRY RUN ATIVO" in msg or "DRY RUN" in msg and "Abortando" in msg):
        return ("DRY RUN: matrícula NÃO confirmada", "O modo de teste está ativo. O programa preparou tudo até o passo final, mas não enviou a confirmação de verdade — nada mudou na sua grade.", "SISTEMA")

    real = eh("matricula_sucesso", "🎉 SUCESSO ABSOLUTO") and (registro.get("dry_run") is False if evento else True)
    if real:
        alvo = alvo_de(r"em ([A-Z0-9-]+)")
        return (f"Matrícula confirmada em {alvo}!", "O SIGAA confirmou a matrícula de verdade. Essa disciplina não será mais monitorada.", "SUCESSO")

    if eh("matricula_sucesso", "🧪 DRY RUN SUCESSO"):
        alvo = alvo_de(r"em ([A-Z0-9-]+)")
        return (f"[TESTE] Matrícula simulada em {alvo}", "Em modo DRY RUN, todo o processo funcionou até o fim — se fosse a execução real, a matrícula teria sido confirmada agora.", "SISTEMA")

    if eh("matricula_bloqueada", "🛑 REMOVIDO"):
        alvo = alvo_de(r"REMOVIDO: A UnB bloqueou ([A-Z0-9-]+)")
        return (f"{alvo} bloqueada pelo SIGAA", "O SIGAA recusou a matrícula por um motivo definitivo (pré-requisito não cumprido, choque de horário, ou limite de créditos). O programa parou de tentar essa disciplina específica — as outras continuam sendo monitoradas.", "AVISO")

    if eh("matricula_falha", "❌ Falha técnica"):
        return ("Tentativa não deu certo, tentando de novo", "Algo deu errado ao tentar confirmar a matrícula, mas não foi um bloqueio definitivo. O programa vai continuar procurando e tentará de novo automaticamente.", "AVISO")

    if eh("timeout", "⏳ Timeout"):
        return ("Conexão demorou demais", f"{worker} esperou a resposta do SIGAA por tempo demais e desistiu dessa tentativa. Ação: o programa está reiniciando a conexão e vai tentar de novo automaticamente.", "REDE")

    if eh("falha_rede", "🔌 Falha de rede"):
        tipo = campo("motivo", r"\(([A-Za-z]+)\)") or ""
        return ("Problema de conexão com a internet/SIGAA", f"{worker} não conseguiu se comunicar com o SIGAA ({tipo or 'erro de rede'}). Ação: o programa está reconectando automaticamente.", "REDE")

    if eh("sessao_expirada", "⚠️ Sessão corrompida"):
        return ("Sessão expirada, entrando de novo", f"{worker} percebeu que a sessão de login expirou ou foi encerrada pelo SIGAA. Ação: fazendo login novamente automaticamente.", "SEGURANCA")

    if eh("login_ok", "✅ Login concluído"):
        return ("Login realizado com sucesso", f"{worker} entrou no SIGAA normalmente e está pronto para monitorar.", "SISTEMA")

    if eh("erro_critico", "💥") or eh("login_erro", "💥"):
        return ("Erro inesperado", f"{worker} encontrou um problema que não era esperado. Ação: o programa está se recuperando automaticamente (reiniciando a conexão) e vai continuar funcionando.", "ERRO")

    if any(c in msg for c in ("Senha mapeada", "CPF injetado", "Data de Nascimento injetada", "Campo desconhecido preenchido")):
        return ("Preenchendo dados de confirmação", "O programa está preenchendo o formulário de confirmação de matrícula com seus dados (nenhum valor sensível aparece neste log — só o nome do campo do formulário).", "SEGURANCA")

    if "Falha ao enviar notificação" in msg or "Notificação de" in msg:
        return ("Aviso sobre notificações", "Houve um problema ao tentar enviar uma notificação (Telegram/ntfy/alarme). Isso NÃO afeta o monitoramento — ele continua funcionando normalmente.", "NOTIFICACAO")

    if eh("espera_falha", "⏸️ Aguardando") or eh("departamento_adiado", "⏸️ Aguardando"):
        segundos = campo("espera_seg", r"Aguardando (\d+)s")
        depto = campo("departamento", r"departamento (\d+)")
        alvo = f"o departamento {depto}" if depto else "o login"
        return ("Pausa antes de tentar de novo", f"{worker} teve falhas seguidas com {alvo} e vai esperar {segundos or 'alguns'} segundo(s) antes de tentar outra vez — para não sobrecarregar o SIGAA. A espera aumenta a cada falha seguida (até 30 s) e volta ao normal no primeiro sucesso.", "REDE")

    if "Nenhum worker conseguiu continuar" in msg:
        return ("Execução encerrada: nenhum worker ativo", "Todos os workers pararam — geralmente porque o SIGAA recusou o login (confira matrícula e senha) ou por falhas seguidas de conexão. Rode o Diagnóstico e revise as Credenciais antes de iniciar de novo.", "ERRO")

    if eh("execucao_resumo", "📋 Resumo da execução"):
        return ("Resumo da execução", msg.replace("📋 ", "") + " O relatório completo fica no Dashboard e em data/relatorios/.", "SISTEMA")

    if eh("preparando_departamento", "Teleportando"):
        return ("Preparando busca no departamento", f"{worker} está acessando a página de busca de turmas do departamento configurado.", "MONITORAMENTO")

    if eh("tentativa_etapa", "⏱️ Tentativa"):
        ms = campo("duracao_ms", r"\((\d+) ms\)")
        etapa = _extrair(r"Tentativa \w+: (.+?) \(", msg) or registro.get("etapa", "etapa")
        tid = registro.get("tentativa_id") or ""
        return (f"Tentativa {tid}: {etapa}".replace("  ", " "),
                f"{worker} chegou a esta etapa {ms or '?'} ms depois de começar a tentativa de matrícula.", "MATRICULA")

    if eh("tentativa_concluida", "🏁 Tentativa"):
        tid = registro.get("tentativa_id") or ""
        resultado = {"SUCESSO": "sucesso", "ERRO_REGRA": "bloqueada pelo SIGAA", "FALHA": "não deu certo",
                     "ERRO": "interrompida"}.get(str(registro.get("motivo", "")), str(registro.get("motivo", "")))
        return (f"Tentativa {tid} concluída: {resultado}".replace("  ", " ").strip(),
                msg.replace("🏁 ", "") + " Cada etapa e o tempo dela aparecem na Linha do tempo.", "MATRICULA")

    if eh("dump_salvo", "📄 Debug salvo"):
        return ("Página salva para diagnóstico", "O programa guardou a página do SIGAA que não veio como esperado — com "
                "matrícula, CPF, nome e campos de formulário mascarados. Veja em Diagnóstico → Páginas capturadas.", "SISTEMA")

    # Eventos cujo texto no log já está em linguagem simples: só ganham título e categoria.
    if evento in _EVENTOS_TEXTO_PRONTO:
        titulo, categoria = _EVENTOS_TEXTO_PRONTO[evento]
        return (titulo, re.sub(r"^\W+\s*", "", msg), categoria)

    # Fallback honesto: não finge entender o que não reconhece.
    return ("Evento do sistema", msg, "DEBUG")
