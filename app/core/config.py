"""
Configuração NÃO-sensível — a única coisa que o programa persiste sozinho.

Tudo aqui é seguro de ficar em disco e de ser exportado/compartilhado:
disciplinas, desempenho (workers/intervalos/timeout), preferências de
execução, quais eventos disparam notificação, limites de log/JSON.

Credenciais (SIGAA, Telegram, ntfy) NUNCA entram neste arquivo — isso é
responsabilidade de app/core/credentials.py, que é só-memória por padrão.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.utils.paths import pasta_config

ARQUIVO_SETTINGS = "settings.json"
ARQUIVO_DISCIPLINAS = "disciplinas.json"
ARQUIVO_SEGREDOS_NOTIFICACAO = "notificacoes.secrets.json"  # opt-in, ver salvar_segredos_notificacao()

VERSAO_CONFIG = 3  # v1->v2: adiciona "urls" e "debug". v2->v3: remove "headless" (nunca era lido em lugar nenhum — seção 33)

# Mesmos valores padrão hardcoded em app/core/engine.py (URLS_PADRAO) — duplicados aqui de
# propósito para settings.json não depender de importar o módulo do motor só por isso.
# tests/test_configuracao_avancada.py garante que os dois conjuntos continuam idênticos.
URLS_SIGAA_PADRAO: Dict[str, str] = {
    "cas_login": "https://autenticacao.unb.br/sso-server/login?service=https%3A%2F%2Fsig.unb.br%2Fsigaa%2Flogin%2Fcas",
    "portal_discente": "https://sigaa.unb.br/sigaa/portais/discente/discente.jsf",
    "matricula_extra": "https://sigaa.unb.br/sigaa/graduacao/matricula/extraordinaria/matricula_extraordinaria.jsf",
    "confirmacao": "https://sigaa.unb.br/sigaa/graduacao/matricula/extraordinaria/confirmacao.jsf",
    "sigaa_base": "https://sigaa.unb.br",
}

PADROES_SETTINGS: Dict[str, Any] = {
    "versao": VERSAO_CONFIG,
    "modo": "monitoramento",          # "matricula" | "monitoramento"
    "num_workers": 20,
    "intervalo_busca": 0.3,
    "timeout_req": 10,
    "dry_run": True,                   # começa seguro por padrão; o usuário desliga conscientemente
    "agendar_inicio": None,            # "DD/MM/AAAA HH:MM:SS" ou None
    # Fase 4 — automação avançada:
    "agendar_fim": None,               # "DD/MM/AAAA HH:MM:SS" ou None — encerra sozinho nesse horário (035)
    "janela": {"ativa": False, "inicio": "07:00", "fim": "23:00", "dias": [0, 1, 2, 3, 4, 5, 6]},  # fora dela, pausa (035)
    "agendamento_relogio_sigaa": False,  # agenda pelo horário do servidor do SIGAA, não do PC (038)
    "verificacao_previa": True,        # confere login e disciplinas antes de soltar os workers (040)
    "abrir_dashboard_ao_iniciar": True,
    "urls": dict(URLS_SIGAA_PADRAO),
    "debug": {"nivel_log_console": "INFO"},  # "INFO" | "DEBUG" — só afeta o console, nunca o arquivo
    "notificacoes": {
        "telegram_ativo": False,
        "ntfy_ativo": False,
        "alarme_ativo": False,
        "eventos": {
            "vaga_detectada": True,
            "matricula_sucesso": True,
            "matricula_falha": False,
            "matricula_bloqueada": True,
            "erro_critico": False,
            # Fase 5: alertas de degradação (058/090), worker recriado (057) e resumos (052).
            "alerta_limiar": True,
            "worker_reiniciado": False,
            "resumo_periodico": False,
            "execucao_encerrada": False,
        },
        "resumo_intervalo_horas": 6,
        # Fase 6: notificação do Windows (080), webhook (081) e e-mail (082).
        "windows_ativo": False,
        "webhook_ativo": False,
        "webhook_formato": "discord",
        "email_ativo": False,
        "email": {"servidor": "", "porta": 587, "usuario": "", "destinatario": "", "remetente": "", "seguranca": "starttls"},
        "alarme": {"repeticoes": 3, "duracao_seg": 20},
        "limite_notificacoes_janela": 5,
        "janela_notificacoes_seg": 300,
    },
    "logs": {"tamanho_max_mb": 10, "arquivos_mantidos": 5},
    # Histórico local de execuções (data/historico.db). dias_retencao=0 guarda para sempre.
    "historico": {"ativo": True, "dias_retencao": 180},
    # Proteção de carga (Fase 4): teto de buscas/s do programa inteiro (0 = sem teto),
    # logins simultâneos no CAS e disjuntor que pausa as buscas quando o SIGAA fica instável.
    "protecao": {"limite_req_por_seg": 20, "logins_simultaneos": 3, "disjuntor": True},
    # Desde a 6.1.0: ao abrir, o Dashboard e a Central de Logs começam vazios (nenhuma execução
    # em andamento). Ligado, mostram os dados da última execução, marcados como recuperados.
    "carregar_ultima_execucao": False,
    # Assistente de configuração inicial concluído ou dispensado (reabre em Config. Avançadas).
    "assistente_concluido": False,
    # Aviso de versão nova (Fase 7, 099): desligado por padrão — nenhuma consulta sem a pessoa pedir.
    "atualizacoes": {"verificar_ao_abrir": False},
    # Aparência da interface gráfica (Fase 6, 010): "claro", "escuro" ou "sistema"; escala em %.
    "interface": {"tema": "claro", "escala_fonte": 100},
    # Alertas por limiar (Fase 5): taxa de erro sustentada, SIGAA sem responder, nenhuma busca.
    "alertas": {"ativo": True, "taxa_erro_pct": 30, "taxa_erro_min": 2, "sem_resposta_min": 5, "sem_busca_min": 2},
    "json_audit": {"tamanho_max_mb": 20, "arquivos_mantidos": 3},
    # Interface Web local (modo recomendado). Por segurança o padrão é só
    # 127.0.0.1 — acessível apenas por este computador. Chave nova: configs
    # antigas recebem estes valores automaticamente via _merge_padroes.
    # modo_aplicativo: abre a interface numa janela própria do Edge/Chrome, sem
    # barra de endereço (sugestão 003); se nenhum for encontrado, usa o navegador padrão.
    "web": {"host": "127.0.0.1", "porta": 8765, "abrir_navegador": True, "modo_aplicativo": True,
            # Fase 6 (070): minutos sem interação (e sem execução) até apagar as credenciais
            # da memória e exigir o link de novo. 0 = nunca expira.
            "expirar_inatividade_min": 0},
}


def _merge_padroes(base: Dict[str, Any], padrao: Dict[str, Any]) -> Dict[str, Any]:
    """Preenche chaves ausentes com o padrão, recursivamente — tolera config antiga/incompleta."""
    resultado = copy.deepcopy(padrao)
    for chave, valor in base.items():
        if isinstance(valor, dict) and isinstance(resultado.get(chave), dict):
            resultado[chave] = _merge_padroes(valor, resultado[chave])
        else:
            resultado[chave] = valor
    return resultado


def _ler_json(caminho: str, padrao: Any) -> Any:
    if not os.path.exists(caminho):
        return copy.deepcopy(padrao)
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Arquivo corrompido/ilegível: não derruba o app, volta ao padrão.
        return copy.deepcopy(padrao)


def _escrever_json(caminho: str, dados: Any) -> None:
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)  # escrita atômica: nunca deixa o arquivo pela metade


def carregar_settings() -> Dict[str, Any]:
    """
    Seções 51-52 do pedido de continuação: migração de configuração entre
    versões, sem o usuário perder o que já tinha configurado. Se o arquivo
    existente for de uma versão anterior, faz backup do original ANTES de
    mesclar com os novos padrões, e salva a versão já migrada.
    """
    caminho = os.path.join(pasta_config(), ARQUIVO_SETTINGS)
    bruto = _ler_json(caminho, PADROES_SETTINGS)

    versao_encontrada = bruto.get("versao") if isinstance(bruto, dict) else None
    migrado = _merge_padroes(bruto, PADROES_SETTINGS)

    if os.path.exists(caminho) and versao_encontrada is not None and versao_encontrada != VERSAO_CONFIG:
        caminho_backup = os.path.join(pasta_config(), f"settings.v{versao_encontrada}.backup.json")
        try:
            if not os.path.exists(caminho_backup):  # não sobrescreve um backup já feito antes
                _escrever_json(caminho_backup, bruto)
            salvar_settings(migrado)
            logging.getLogger("sniper").info(
                f"Configuração migrada da versão {versao_encontrada} para {VERSAO_CONFIG} "
                f"(backup do original salvo em {os.path.basename(caminho_backup)}).",
                extra={"worker_id": "MAIN"},
            )
        except OSError:
            pass  # migração é best-effort; nunca impede o programa de continuar com os valores mesclados em memória

    return migrado


def salvar_settings(settings: Dict[str, Any]) -> None:
    caminho = os.path.join(pasta_config(), ARQUIVO_SETTINGS)
    settings = dict(settings)
    settings["versao"] = VERSAO_CONFIG
    anterior = _guardar_versao(caminho, settings)  # Fase 6 (045): dá para desfazer
    _escrever_json(caminho, settings)
    if isinstance(anterior, dict):
        from app.core import auditoria
        auditoria.registrar_mudancas_settings(anterior, settings)


# ─────────────────────────────────────────────────────────────────────────
# Restaurar padrões (seção 34) — tudo ou só uma seção, nunca mexe em credenciais
# (que já não ficam neste arquivo).
# ─────────────────────────────────────────────────────────────────────────

SECOES_RESTAURAVEIS = ["monitoramento", "dashboard", "notificacoes", "avancado", "urls"]

_CHAVES_POR_SECAO: Dict[str, List[str]] = {
    "monitoramento": ["modo", "dry_run", "agendar_inicio", "num_workers", "intervalo_busca", "timeout_req",
                      "agendar_fim", "janela", "agendamento_relogio_sigaa", "verificacao_previa"],
    "dashboard": ["abrir_dashboard_ao_iniciar", "carregar_ultima_execucao"],
    "notificacoes": ["notificacoes"],
    "avancado": ["logs", "json_audit", "debug", "web", "historico", "protecao", "alertas", "interface", "atualizacoes"],
    "urls": ["urls"],
}


def restaurar_padroes(settings: Dict[str, Any], secoes: Optional[List[str]] = None) -> Dict[str, Any]:
    """Restaura os valores padrão. Sem `secoes`, restaura tudo. Nunca toca em
    credenciais (elas não vivem neste arquivo)."""
    resultado = dict(settings)
    alvo_chaves = secoes if secoes else list(_CHAVES_POR_SECAO.keys())
    for secao in alvo_chaves:
        for chave in _CHAVES_POR_SECAO.get(secao, []):
            resultado[chave] = copy.deepcopy(PADROES_SETTINGS[chave])
    return resultado


# ─────────────────────────────────────────────────────────────────────────
# Validação antes de iniciar (seção 35)
# ─────────────────────────────────────────────────────────────────────────

def validar_settings(settings: Dict[str, Any]) -> List[str]:
    """Devolve uma lista de problemas encontrados (vazia = tudo certo). Nunca
    lança exceção — o chamador decide se bloqueia o início ou só avisa."""
    # Fase 7 (044): as faixas de todos os campos numéricos vêm de um esquema único,
    # o mesmo que a interface gráfica e a Web usam nos seus campos.
    from app.core.esquema import problemas_numericos
    problemas = problemas_numericos(settings)

    if settings.get("modo") not in ("matricula", "monitoramento"):
        problemas.append(f"Modo de execução inválido: {settings.get('modo')!r} (esperado 'matricula' ou 'monitoramento').")

    agendar = settings.get("agendar_inicio")
    if agendar:
        try:
            from datetime import datetime
            datetime.strptime(agendar, "%d/%m/%Y %H:%M:%S")
        except ValueError:
            problemas.append(f"Data de agendamento inválida: {agendar!r} (formato esperado: DD/MM/AAAA HH:MM:SS).")

    fim = settings.get("agendar_fim")
    if fim:
        from datetime import datetime
        try:
            fim_dt = datetime.strptime(fim, "%d/%m/%Y %H:%M:%S")
            if agendar:
                try:
                    if fim_dt <= datetime.strptime(agendar, "%d/%m/%Y %H:%M:%S"):
                        problemas.append("O horário de término precisa ser depois do horário de início agendado.")
                except ValueError:
                    pass
        except ValueError:
            problemas.append(f"Horário de término inválido: {fim!r} (formato esperado: DD/MM/AAAA HH:MM:SS).")
    from app.core.regras import problemas_janela
    problemas.extend(problemas_janela(settings.get("janela") or {}))

    for chave_url, valor in settings.get("urls", {}).items():
        if not (isinstance(valor, str) and valor.startswith("https://")):
            problemas.append(f"URL '{chave_url}' inválida (precisa começar com https://): {valor!r}")

    interface = settings.get("interface", {})
    if interface.get("tema", "claro") not in ("claro", "escuro", "sistema"):
        problemas.append("Tema da interface gráfica inválido (claro, escuro ou sistema).")
    notif = settings.get("notificacoes", {})
    if notif.get("webhook_formato", "discord") not in ("discord", "slack", "json"):
        problemas.append("Formato do webhook inválido (use discord, slack ou json).")
    email = notif.get("email") or {}
    porta_email = email.get("porta", 587)
    if not (isinstance(porta_email, int) and not isinstance(porta_email, bool) and 1 <= porta_email <= 65535):
        problemas.append("Porta do servidor de e-mail inválida.")
    if email.get("seguranca", "starttls") not in ("starttls", "ssl"):
        problemas.append("Segurança do e-mail deve ser STARTTLS ou SSL.")
    web = settings.get("web", {})
    host = web.get("host", "127.0.0.1")
    if not (isinstance(host, str) and host.strip()):
        problemas.append("Endereço (host) da Interface Web não pode ficar vazio.")

    return problemas


def validar_disciplinas(disciplinas: List["Disciplina"]) -> List[str]:
    problemas = []
    ativas = [d for d in disciplinas if d.ativa]
    if not ativas:
        problemas.append("Nenhuma disciplina ativa — adicione ou ative pelo menos uma antes de iniciar.")
    for d in ativas:
        if not d.codigo or not d.turma:
            problemas.append(f"Disciplina incompleta: código={d.codigo!r}, turma={d.turma!r}.")
        elif not d.turma.isdigit():
            problemas.append(f"Disciplina {d.codigo}-{d.turma}: a turma deve ter só números (ex: 01) — do jeito atual ela nunca seria encontrada.")
        if not d.departamento or d.departamento <= 0:
            problemas.append(f"Disciplina {d.codigo}-{d.turma} está sem um departamento válido.")
    return problemas


PRIORIDADES = ("alta", "normal", "baixa")


@dataclass
class Disciplina:
    codigo: str
    turma: str
    departamento: int
    ativa: bool = True
    professor: str = ""
    # Fase 4: grupo de turmas alternativas (033) — garantida uma, as outras do mesmo
    # grupo saem da busca — e prioridade (034): "baixa" é consultada a cada 3 ciclos.
    grupo: str = ""
    prioridade: str = "normal"

    def chave(self) -> str:
        return f"{self.codigo}-{self.turma}"

    def como_tupla(self):
        """Formato [codigo, turma, id_departamento] esperado pela engine (compatível com a v4.0)."""
        return [self.codigo, self.turma, self.departamento]

    def como_alvo(self):
        """Formato do motor desde a Fase 4: os 3 campos da v4.0 + grupo + prioridade."""
        return [self.codigo, self.turma, self.departamento, self.grupo, self.prioridade]


def _disciplina_de_dict(item: Dict[str, Any]) -> "Disciplina":
    prioridade = str(item.get("prioridade", "normal") or "normal").strip().lower()
    return Disciplina(
        codigo=str(item["codigo"]).strip().upper(), turma=str(item["turma"]).strip(),
        departamento=int(item["departamento"]), ativa=bool(item.get("ativa", True)),
        professor=str(item.get("professor", "")), grupo=str(item.get("grupo", "") or "").strip()[:40],
        prioridade=prioridade if prioridade in PRIORIDADES else "normal",
    )


# ─────────────────────────────────────────────────────────────────────────
# Validação ao cadastrar disciplinas — mesma regra para GUI, Web e terminal.
# Erros impedem salvar; avisos pedem "salvar mesmo assim".
# ─────────────────────────────────────────────────────────────────────────

RE_CODIGO_DISCIPLINA = re.compile(r"^[A-Z]{3}\d{4}$")


def analisar_disciplina(
    nova: Disciplina, existentes: List[Disciplina], ignorar_indice: Optional[int] = None,
) -> Tuple[List[str], List[str]]:
    """Devolve (erros, avisos) para uma disciplina prestes a ser salva.

    A regra da turma vem do parser do motor (engine.parse_hot_path, lógica da
    v4.0): ele pega o PRIMEIRO número da célula de turma do SIGAA e compara
    com a turma cadastrada por igualdade exata. Uma turma com letras nunca
    pode ser encontrada — antes ela era aceita e ficava "sem vagas" para sempre."""
    from app.core.departamentos import codigo_conhecido

    erros: List[str] = []
    avisos: List[str] = []
    if not nova.codigo or not nova.turma or not nova.departamento or nova.departamento <= 0:
        erros.append("Preencha código da disciplina, turma, e selecione (ou digite) um departamento válido.")
        return erros, avisos

    if not nova.turma.isdigit():
        erros.append(
            f"Turma {nova.turma!r} inválida: use só os números da turma, como aparecem na lista do SIGAA "
            "(ex: 01). O programa localiza a turma pelo número, então letras fariam ela nunca ser encontrada."
        )
    elif len(nova.turma) == 1:
        avisos.append(
            f"A turma {nova.turma!r} tem um só dígito; no SIGAA as turmas costumam aparecer com dois (ex: 01). "
            "O número é comparado exatamente — confira como aparece na lista de turmas."
        )
    if not RE_CODIGO_DISCIPLINA.match(nova.codigo):
        avisos.append(f"O código {nova.codigo!r} não tem o formato usual do SIGAA (3 letras + 4 números, ex: FGA0211).")
    if nova.prioridade not in PRIORIDADES:
        erros.append(f"Prioridade inválida: {nova.prioridade!r} (use alta, normal ou baixa).")
    if not codigo_conhecido(nova.departamento):
        avisos.append(
            f"O código de departamento {nova.departamento} não está na lista de referência conhecida. "
            "Isso pode ser normal (departamento novo, ou a lista está desatualizada) — confira com "
            "\"Como encontrar?\" se não tiver certeza."
        )

    for i, d in enumerate(existentes):
        if i == ignorar_indice:
            continue
        if d.chave() == nova.chave():
            erros.append(f"{nova.chave()} já está cadastrada.")
        elif d.codigo == nova.codigo and not (nova.grupo and d.grupo == nova.grupo):
            avisos.append(
                f"{nova.codigo} já está cadastrada com a turma {d.turma}. Com duas turmas da mesma disciplina, "
                "o SIGAA recusa a segunda depois que a primeira for confirmada (\"mais de uma turma do componente\"). "
                "Dica: coloque as duas no mesmo GRUPO de alternativas — garantida uma, a outra sai da busca."
            )
    return erros, avisos


def interpretar_lote(texto: str, existentes: List[Disciplina]) -> List[Dict[str, Any]]:
    """Interpreta várias disciplinas coladas de uma vez (uma por linha:
    CÓDIGO TURMA DEPARTAMENTO [professor]) sem salvar nada. Cada linha volta
    com a disciplina interpretada (ou None) e seus erros/avisos, para a tela
    mostrar uma pré-visualização antes de confirmar. Duplicatas dentro do
    próprio lote também são detectadas."""
    resultado: List[Dict[str, Any]] = []
    aceitas: List[Disciplina] = []
    for numero, bruta in enumerate((texto or "").splitlines(), start=1):
        linha = bruta.strip()
        if not linha or linha.startswith("#"):
            continue
        partes = [p for p in re.split(r"[;,\t ]+", linha) if p]
        item: Dict[str, Any] = {"linha": numero, "texto": linha, "disciplina": None, "erros": [], "avisos": []}
        if len(partes) < 3:
            item["erros"].append("Formato esperado: CÓDIGO TURMA DEPARTAMENTO (ex: FGA0211 01 673).")
        elif not partes[2].isdigit():
            item["erros"].append(f"Departamento {partes[2]!r} deve ser o número (código) do departamento.")
        else:
            nova = Disciplina(codigo=partes[0].upper(), turma=partes[1], departamento=int(partes[2]),
                              professor=" ".join(partes[3:]))
            item["disciplina"] = nova
            item["erros"], item["avisos"] = analisar_disciplina(nova, list(existentes) + aceitas)
            if not item["erros"]:
                aceitas.append(nova)
        resultado.append(item)
    return resultado


# ─────────────────────────────────────────────────────────────────────────
# Presets de carga responsável (sugestão 043): em vez de adivinhar workers e
# intervalo, o usuário escolhe um perfil e vê a carga estimada.
# ─────────────────────────────────────────────────────────────────────────

PRESETS_CARGA: Dict[str, Dict[str, Any]] = {
    "leve": {"rotulo": "Leve", "num_workers": 4, "intervalo_busca": 1.5,
             "descricao": "Acompanhar vagas com calma. Menor carga e menor risco de bloqueio."},
    "moderado": {"rotulo": "Moderado", "num_workers": 8, "intervalo_busca": 0.8,
                 "descricao": "Equilíbrio entre tempo de reação e carga."},
    "padrao": {"rotulo": "Intenso (padrão original)", "num_workers": 20, "intervalo_busca": 0.3,
               "descricao": "Valores originais do projeto. Reação mais rápida, carga bem mais alta."},
}

# Para a estimativa: cada worker faz uma busca por disciplina ativa e dorme o
# intervalo; ~250 ms é uma resposta típica do SIGAA. É uma ESTIMATIVA — o
# painel mostra o valor medido durante a execução.
LATENCIA_REFERENCIA_SEG = 0.25
LIMITE_CARGA_BAIXA = 5.0     # req/s — até aqui: baixa
LIMITE_CARGA_MODERADA = 15.0  # acima disso: alta (mostra alerta)


def preset_correspondente(num_workers: Any, intervalo_busca: Any) -> Optional[str]:
    for chave, p in PRESETS_CARGA.items():
        try:
            if int(num_workers) == p["num_workers"] and abs(float(intervalo_busca) - p["intervalo_busca"]) < 1e-9:
                return chave
        except (TypeError, ValueError):
            return None
    return None


def estimar_carga(num_workers: Any, intervalo_busca: Any, qtd_alvos: int = 1, limite: Any = 0) -> Dict[str, Any]:
    """Requisições por segundo estimadas para a configuração, com nível e texto
    prontos para exibir. Valores inválidos devolvem nível 'desconhecida'."""
    try:
        workers, intervalo = int(num_workers), float(intervalo_busca)
    except (TypeError, ValueError):
        return {"req_por_seg": None, "nivel": "desconhecida", "texto": "Carga estimada indisponível (valores inválidos).",
                "preset": None, "alerta": None}
    alvos = max(1, int(qtd_alvos or 1))
    if workers <= 0 or intervalo < 0:
        return {"req_por_seg": None, "nivel": "desconhecida", "texto": "Carga estimada indisponível (valores inválidos).",
                "preset": None, "alerta": None}
    rps = workers * alvos / (alvos * LATENCIA_REFERENCIA_SEG + intervalo)
    try:
        teto = float(limite or 0)
    except (TypeError, ValueError):
        teto = 0.0
    limitado = 0 < teto < rps
    if limitado:
        rps = teto  # o limitador global (proteção de carga) não deixa passar disso
    nivel = "baixa" if rps <= LIMITE_CARGA_BAIXA else "moderada" if rps <= LIMITE_CARGA_MODERADA else "alta"
    alerta = None
    if nivel == "alta":
        alerta = (f"Carga alta: cerca de {rps:.0f} requisições por segundo. Considere o perfil Moderado ou Leve — "
                  "o aviso legal pede uso responsável, e cargas altas aumentam o risco de bloqueio.")
    return {
        "req_por_seg": round(rps, 1), "nivel": nivel, "preset": preset_correspondente(workers, intervalo),
        "texto": (f"≈ {rps:.1f} req/s ({nivel}) — limitada pelo teto de {teto:g} buscas/s da proteção de carga."
                  if limitado else
                  f"≈ {rps:.1f} req/s ({nivel}) — estimativa com {workers} worker(s), {alvos} disciplina(s) "
                  f"e ~{int(LATENCIA_REFERENCIA_SEG * 1000)} ms por resposta."),
        "limitada": limitado,
        "alerta": alerta,
    }


def carregar_disciplinas() -> List[Disciplina]:
    caminho = os.path.join(pasta_config(), ARQUIVO_DISCIPLINAS)
    bruto = _ler_json(caminho, [])
    disciplinas = []
    for item in bruto:
        try:
            disciplinas.append(_disciplina_de_dict(item))
        except (KeyError, ValueError, TypeError, AttributeError):
            continue  # ignora entradas corrompidas em vez de travar o app
    return disciplinas


def salvar_disciplinas(disciplinas: List[Disciplina]) -> None:
    caminho = os.path.join(pasta_config(), ARQUIVO_DISCIPLINAS)
    novas = [asdict(d) for d in disciplinas]
    anterior = _guardar_versao(caminho, novas)
    _escrever_json(caminho, novas)
    if isinstance(anterior, list) and anterior != novas:
        from app.core import auditoria
        auditoria.registrar("disciplinas_alteradas", antes=len(anterior), depois=len(novas))


# ─────────────────────────────────────────────────────────────────────────
# Segredos de notificação — opt-in explícito, NUNCA automático.
# As credenciais do SIGAA em si (app/core/credentials.py) não têm equivalente
# aqui de propósito: aquelas são sempre pedidas de novo a cada execução.
# ─────────────────────────────────────────────────────────────────────────

def existe_segredos_notificacao_salvos() -> bool:
    caminho = os.path.join(pasta_config(), ARQUIVO_SEGREDOS_NOTIFICACAO)
    return os.path.exists(caminho)


def carregar_segredos_notificacao() -> Optional[Dict[str, str]]:
    caminho = os.path.join(pasta_config(), ARQUIVO_SEGREDOS_NOTIFICACAO)
    if not os.path.exists(caminho):
        return None
    from app.core.cofre import decifrar
    return decifrar(_ler_json(caminho, None))  # aceita o formato cifrado e o antigo, em texto simples


def salvar_segredos_notificacao(telegram_token: str, telegram_chat_id: str, ntfy_topic: str, ntfy_servidor: str = "",
                                webhook_url: str = "", email_senha: str = "") -> None:
    """
    Só deve ser chamada quando o usuário marcou explicitamente uma caixa do tipo
    "Salvar neste computador (arquivo não criptografado)" na GUI/terminal/Web.
    Nunca é chamada automaticamente pelo app.

    `ntfy_servidor` passou a ser salvo junto (antes um servidor ntfy próprio
    era esquecido a cada reinício e as notificações iam para ntfy.sh).
    """
    caminho = os.path.join(pasta_config(), ARQUIVO_SEGREDOS_NOTIFICACAO)
    dados = {
        "telegram_token": telegram_token,
        "telegram_chat_id": telegram_chat_id,
        "ntfy_topic": ntfy_topic,
    }
    if ntfy_servidor:
        dados["ntfy_servidor"] = ntfy_servidor
    if webhook_url:
        dados["webhook_url"] = webhook_url
    if email_senha:
        dados["email_senha"] = email_senha
    from app.core.cofre import cifrar
    _escrever_json(caminho, cifrar(dados))  # Fase 6 (065): cifrado com a DPAPI quando disponível
    from app.core import auditoria
    auditoria.registrar("segredos_salvos")


def aplicar_segredos_notificacao_salvos(notificacao) -> bool:
    """Carrega os segredos de notificação salvos (opt-in) para a sessão em
    memória. Usado pelos três modos (GUI, terminal e Web) — antes só a GUI
    fazia isso, e o terminal ignorava os segredos salvos silenciosamente
    (Telegram/ntfy "ativos", mas sem token/tópico, nunca notificavam)."""
    segredos = carregar_segredos_notificacao()
    if not segredos:
        return False
    notificacao.telegram_token = segredos.get("telegram_token", "")
    notificacao.telegram_chat_id = segredos.get("telegram_chat_id", "")
    notificacao.ntfy_topic = segredos.get("ntfy_topic", "")
    if segredos.get("ntfy_servidor"):
        notificacao.ntfy_servidor = segredos["ntfy_servidor"]
    notificacao.webhook_url = segredos.get("webhook_url", "")
    notificacao.email_senha = segredos.get("email_senha", "")
    return True


def segredos_salvos_cifrados() -> bool:
    caminho = os.path.join(pasta_config(), ARQUIVO_SEGREDOS_NOTIFICACAO)
    from app.core.cofre import esta_cifrado
    return esta_cifrado(_ler_json(caminho, None))


def apagar_segredos_notificacao() -> None:
    caminho = os.path.join(pasta_config(), ARQUIVO_SEGREDOS_NOTIFICACAO)
    if os.path.exists(caminho):
        os.remove(caminho)
        from app.core import auditoria
        auditoria.registrar("segredos_apagados")


# ─────────────────────────────────────────────────────────────────────────
# Exportar/Importar configuração (não-sensível) — seção "Configurações Exportáveis"
# ─────────────────────────────────────────────────────────────────────────

def exportar_configuracao(caminho_destino: str) -> None:
    """Exporta settings + disciplinas. Nunca inclui credenciais nem segredos de notificação."""
    pacote = {
        "settings": carregar_settings(),
        "disciplinas": [asdict(d) for d in carregar_disciplinas()],
    }
    _escrever_json(caminho_destino, pacote)


CHAVES_CREDENCIAL_PROIBIDAS = ("senha", "password", "cpf", "token", "chat_id", "nascimento", "api_key")


def _procurar_credenciais_escondidas(obj: Any, caminho: str = "") -> List[str]:
    """Seção 48: nunca aceitar um arquivo de importação que tenha uma credencial
    escondida em um campo inesperado (o formato normal de exportação nunca inclui
    isso — se aparecer, é suspeito)."""
    achados = []
    if isinstance(obj, dict):
        for chave, valor in obj.items():
            caminho_atual = f"{caminho}.{chave}" if caminho else str(chave)
            chave_lower = str(chave).lower()
            if any(padrao in chave_lower for padrao in CHAVES_CREDENCIAL_PROIBIDAS) and isinstance(valor, str) and valor:
                achados.append(caminho_atual)
            achados.extend(_procurar_credenciais_escondidas(valor, caminho_atual))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            achados.extend(_procurar_credenciais_escondidas(item, f"{caminho}[{i}]"))
    return achados


def pre_visualizar_importacao(caminho_origem: str) -> Dict[str, Any]:
    """Lê e valida o arquivo SEM aplicar nada — para a GUI/terminal mostrarem um
    resumo antes de confirmar (seção 48: 'mostrar resumo antes de aplicar')."""
    with open(caminho_origem, "r", encoding="utf-8") as f:
        pacote = json.load(f)

    if not isinstance(pacote, dict):
        raise ValueError("Formato inválido: o arquivo não contém um objeto JSON no formato esperado.")

    credenciais_encontradas = _procurar_credenciais_escondidas(pacote)
    if credenciais_encontradas:
        raise ValueError(
            "Este arquivo parece conter dados sensíveis em campos inesperados "
            f"({', '.join(credenciais_encontradas[:5])}) — importação recusada por segurança. "
            "O formato normal de exportação deste programa nunca inclui isso."
        )

    resumo = {"tem_settings": "settings" in pacote, "problemas_settings": [], "qtd_disciplinas": 0, "problemas_disciplinas": []}

    if "settings" in pacote:
        if not isinstance(pacote["settings"], dict):
            raise ValueError("Campo 'settings' malformado (deveria ser um objeto).")
        settings_migrado = _merge_padroes(pacote["settings"], PADROES_SETTINGS)
        resumo["problemas_settings"] = validar_settings(settings_migrado)
        resumo["settings_migrado"] = settings_migrado

    if "disciplinas" in pacote:
        if not isinstance(pacote["disciplinas"], list):
            raise ValueError("Campo 'disciplinas' malformado (deveria ser uma lista).")
        disciplinas_ok = []
        for i, d in enumerate(pacote["disciplinas"]):
            try:
                disciplinas_ok.append(_disciplina_de_dict(d))
            except (KeyError, ValueError, TypeError, AttributeError):
                resumo["problemas_disciplinas"].append(f"Item {i} inválido/incompleto, foi ignorado.")
        resumo["qtd_disciplinas"] = len(disciplinas_ok)
        resumo["disciplinas_validas"] = disciplinas_ok

    return resumo


def importar_configuracao(caminho_origem: str) -> Dict[str, Any]:
    """Valida (via pre_visualizar_importacao) e só então aplica. Rejeita (lança
    ValueError) se as configurações resultantes forem inválidas — nunca aplica
    parcialmente um estado ruim."""
    resumo = pre_visualizar_importacao(caminho_origem)

    if resumo["problemas_settings"]:
        raise ValueError("Configurações inválidas no arquivo importado:\n" + "\n".join(resumo["problemas_settings"]))

    if resumo.get("tem_settings"):
        salvar_settings(resumo["settings_migrado"])
    if "disciplinas_validas" in resumo:
        salvar_disciplinas(resumo["disciplinas_validas"])
    from app.core import auditoria
    auditoria.registrar("configuracao_importada", disciplinas=resumo.get("qtd_disciplinas", 0),
                        com_configuracoes=bool(resumo.get("tem_settings")))
    return resumo


# ─────────────────────────────────────────────────────────────────────────
# Fase 6 — histórico de alterações (045) e perfis de configuração (042)
# ─────────────────────────────────────────────────────────────────────────

MAX_VERSOES_CONFIG = 20
_RE_VERSAO = re.compile(r"^(settings|disciplinas)__(\d{8})_(\d{6})_(\d{6})\.json$")


def _pasta_versoes() -> str:
    d = os.path.join(pasta_config(), "historico")
    os.makedirs(d, exist_ok=True)
    return d


def _guardar_versao(caminho: str, novos: Any) -> Any:
    """Antes de sobrescrever settings/disciplinas, guarda o conteúdo atual em
    config/historico/ (só se mudou). Devolve o conteúdo anterior (ou None).
    Nunca impede o salvamento: um problema aqui só faz perder o "desfazer"."""
    if not os.path.exists(caminho):
        return None
    try:
        with open(caminho, encoding="utf-8") as f:
            anterior = json.load(f)
    except (OSError, ValueError):
        return None
    if anterior == novos:
        return anterior
    try:
        from datetime import datetime
        base = os.path.splitext(os.path.basename(caminho))[0]
        pasta = _pasta_versoes()
        nome = f"{base}__{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
        _escrever_json(os.path.join(pasta, nome), anterior)
        versoes = sorted(n for n in os.listdir(pasta) if n.startswith(base + "__") and n.endswith(".json"))
        for antiga in versoes[:-MAX_VERSOES_CONFIG]:
            os.remove(os.path.join(pasta, antiga))
    except OSError:
        pass
    return anterior


def _resumo_versao(tipo: str, dados: Any) -> str:
    if tipo == "settings" and isinstance(dados, dict):
        from app.core.auditoria import mudancas_settings
        atual = carregar_settings()
        mudancas = mudancas_settings(atual, _merge_padroes(dados, PADROES_SETTINGS))
        if not mudancas:
            return "igual à configuração atual"
        partes = [f"{m['chave']} {m['para']} (hoje {m['de']})" if "de" in m else m["chave"] for m in mudancas[:6]]
        return "Diferenças para a atual: " + ", ".join(partes) + ("…" if len(mudancas) > 6 else "")
    if tipo == "disciplinas" and isinstance(dados, list):
        chaves = {f"{d.get('codigo')}-{d.get('turma')}" for d in dados if isinstance(d, dict)}
        atuais = {d.chave() for d in carregar_disciplinas()}
        extra = []
        if chaves - atuais:
            extra.append("tinha " + ", ".join(sorted(chaves - atuais)[:4]))
        if atuais - chaves:
            extra.append("não tinha " + ", ".join(sorted(atuais - chaves)[:4]))
        return f"{len(dados)} disciplina(s)" + (f" — {'; '.join(extra)}" if extra else " — mesmas disciplinas de hoje")
    return ""


def listar_versoes_config() -> List[Dict[str, Any]]:
    """Versões anteriores guardadas, mais recentes primeiro, com um resumo do que muda se restaurar."""
    pasta = _pasta_versoes()
    saida = []
    for nome in sorted(os.listdir(pasta), reverse=True):
        m = _RE_VERSAO.match(nome)
        if not m:
            continue
        tipo, dia, hora = m.group(1), m.group(2), m.group(3)
        dados = _ler_json(os.path.join(pasta, nome), None)
        saida.append({"id": nome, "tipo": tipo, "tipo_rotulo": "Configurações" if tipo == "settings" else "Disciplinas",
                      "quando": f"{dia[6:8]}/{dia[4:6]}/{dia[:4]} {hora[:2]}:{hora[2:4]}:{hora[4:6]}",
                      "resumo": _resumo_versao(tipo, dados)})
    return saida


def restaurar_versao_config(versao_id: str) -> Dict[str, Any]:
    """Volta settings ou disciplinas para uma versão guardada. A versão atual
    também é guardada antes — dá para desfazer o desfazer. Lança ValueError se
    a versão não existir ou não passar na validação."""
    m = _RE_VERSAO.match(str(versao_id or ""))
    caminho = os.path.join(_pasta_versoes(), str(versao_id)) if m else ""
    if not m or not os.path.isfile(caminho):
        raise ValueError("Versão não encontrada.")
    dados = _ler_json(caminho, None)
    from app.core import auditoria
    if m.group(1) == "settings":
        if not isinstance(dados, dict):
            raise ValueError("Versão ilegível.")
        novos = _merge_padroes(dados, PADROES_SETTINGS)
        problemas = validar_settings(novos)
        if problemas:
            raise ValueError("A versão guardada não passa na validação atual:\n" + "\n".join(problemas))
        salvar_settings(novos)
        auditoria.registrar("versao_restaurada", detalhe=f"configurações de {versao_id[10:25]}")
        return {"tipo": "settings", "settings": novos}
    if not isinstance(dados, list):
        raise ValueError("Versão ilegível.")
    disciplinas = []
    for item in dados:
        try:
            disciplinas.append(_disciplina_de_dict(item))
        except (KeyError, TypeError, ValueError):
            continue
    salvar_disciplinas(disciplinas)
    auditoria.registrar("versao_restaurada", detalhe=f"disciplinas de {versao_id[13:28]}")
    return {"tipo": "disciplinas", "disciplinas": disciplinas}


# Perfis (042): o "cenário" — modo, desempenho, proteção, janela, alertas,
# notificações (sem segredos) e disciplinas. O DRY RUN NUNCA vem do perfil:
# aplicar um perfil não pode ligar a matrícula real sem o usuário ver.
CHAVES_PERFIL = ["modo", "num_workers", "intervalo_busca", "timeout_req", "protecao", "janela", "verificacao_previa",
                 "agendamento_relogio_sigaa", "alertas", "notificacoes"]


def _pasta_perfis() -> str:
    d = os.path.join(pasta_config(), "perfis")
    os.makedirs(d, exist_ok=True)
    return d


def _arquivo_perfil(nome: str) -> str:
    import unicodedata
    base = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:40]
    if not base:
        raise ValueError("Dê um nome ao perfil (letras ou números).")
    return base + ".json"


def salvar_perfil(nome: str, settings: Dict[str, Any], disciplinas: List["Disciplina"]) -> Dict[str, Any]:
    nome = str(nome or "").strip()[:60]
    arquivo = _arquivo_perfil(nome)
    from datetime import datetime
    perfil = {"nome": nome, "criado": datetime.now().strftime("%d/%m/%Y %H:%M"),
              "settings": {k: copy.deepcopy(settings[k]) for k in CHAVES_PERFIL if k in settings},
              "disciplinas": [asdict(d) for d in disciplinas]}
    _escrever_json(os.path.join(_pasta_perfis(), arquivo), perfil)
    from app.core import auditoria
    auditoria.registrar("perfil_salvo", perfil=nome)
    return {"arquivo": arquivo, **perfil}


def listar_perfis() -> List[Dict[str, Any]]:
    saida = []
    for arquivo in sorted(os.listdir(_pasta_perfis())):
        if not arquivo.endswith(".json"):
            continue
        dados = _ler_json(os.path.join(_pasta_perfis(), arquivo), None)
        if not isinstance(dados, dict) or not isinstance(dados.get("settings"), dict):
            continue
        s = dados["settings"]
        modo = "somente monitoramento" if s.get("modo") == "monitoramento" else "matrícula automática"
        saida.append({"arquivo": arquivo, "nome": dados.get("nome") or arquivo[:-5], "criado": dados.get("criado", ""),
                      "resumo": f"{modo} · {s.get('num_workers', '?')} workers, {s.get('intervalo_busca', '?')} s · "
                                f"{len(dados.get('disciplinas') or [])} disciplina(s)"})
    return saida


def aplicar_perfil(arquivo: str, settings_atuais: Dict[str, Any]) -> Tuple[Dict[str, Any], List["Disciplina"]]:
    """Monta settings + disciplinas do perfil sobre a configuração atual, VALIDA e
    devolve (o chamador salva). Mantém o DRY RUN atual. Lança ValueError."""
    if not re.fullmatch(r"[a-z0-9-]{1,40}\.json", str(arquivo or "")):
        raise ValueError("Perfil não encontrado.")
    dados = _ler_json(os.path.join(_pasta_perfis(), arquivo), None)
    if not isinstance(dados, dict) or not isinstance(dados.get("settings"), dict):
        raise ValueError("Perfil não encontrado.")
    novos = copy.deepcopy(settings_atuais)
    for chave in CHAVES_PERFIL:
        if chave in dados["settings"]:
            valor = dados["settings"][chave]
            novos[chave] = _merge_padroes(valor, PADROES_SETTINGS[chave]) if isinstance(PADROES_SETTINGS.get(chave), dict) and isinstance(valor, dict) else valor
    novos["dry_run"] = settings_atuais.get("dry_run", True)
    disciplinas = []
    for item in dados.get("disciplinas") or []:
        try:
            disciplinas.append(_disciplina_de_dict(item))
        except (KeyError, TypeError, ValueError):
            continue
    problemas = validar_settings(novos)
    if problemas:
        raise ValueError("O perfil não passa na validação:\n" + "\n".join(problemas))
    from app.core import auditoria
    auditoria.registrar("perfil_aplicado", perfil=dados.get("nome") or arquivo)
    return novos, disciplinas


def apagar_perfil(arquivo: str) -> None:
    if not re.fullmatch(r"[a-z0-9-]{1,40}\.json", str(arquivo or "")):
        raise ValueError("Perfil não encontrado.")
    caminho = os.path.join(_pasta_perfis(), arquivo)
    if not os.path.isfile(caminho):
        raise ValueError("Perfil não encontrado.")
    nome = (_ler_json(caminho, {}) or {}).get("nome") or arquivo
    os.remove(caminho)
    from app.core import auditoria
    auditoria.registrar("perfil_apagado", perfil=nome)
