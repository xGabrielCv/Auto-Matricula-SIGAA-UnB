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
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

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
        },
        "alarme": {"repeticoes": 3, "duracao_seg": 20},
        "limite_notificacoes_janela": 5,
        "janela_notificacoes_seg": 300,
    },
    "logs": {"tamanho_max_mb": 10, "arquivos_mantidos": 5},
    "json_audit": {"tamanho_max_mb": 20, "arquivos_mantidos": 3},
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
    _escrever_json(caminho, settings)


# ─────────────────────────────────────────────────────────────────────────
# Restaurar padrões (seção 34) — tudo ou só uma seção, nunca mexe em credenciais
# (que já não ficam neste arquivo).
# ─────────────────────────────────────────────────────────────────────────

SECOES_RESTAURAVEIS = ["monitoramento", "dashboard", "notificacoes", "avancado", "urls"]

_CHAVES_POR_SECAO: Dict[str, List[str]] = {
    "monitoramento": ["modo", "dry_run", "agendar_inicio", "num_workers", "intervalo_busca", "timeout_req"],
    "dashboard": ["abrir_dashboard_ao_iniciar"],
    "notificacoes": ["notificacoes"],
    "avancado": ["logs", "json_audit", "debug"],
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
    problemas = []

    if not (1 <= settings.get("num_workers", 0) <= 100):
        problemas.append("Número de workers deve estar entre 1 e 100.")
    if not (0.05 <= settings.get("intervalo_busca", 0) <= 60):
        problemas.append("Intervalo de busca deve estar entre 0.05 e 60 segundos.")
    if not (1 <= settings.get("timeout_req", 0) <= 120):
        problemas.append("Timeout de requisição deve estar entre 1 e 120 segundos.")
    if settings.get("modo") not in ("matricula", "monitoramento"):
        problemas.append(f"Modo de execução inválido: {settings.get('modo')!r} (esperado 'matricula' ou 'monitoramento').")

    agendar = settings.get("agendar_inicio")
    if agendar:
        try:
            from datetime import datetime
            datetime.strptime(agendar, "%d/%m/%Y %H:%M:%S")
        except ValueError:
            problemas.append(f"Data de agendamento inválida: {agendar!r} (formato esperado: DD/MM/AAAA HH:MM:SS).")

    for chave_url, valor in settings.get("urls", {}).items():
        if not (isinstance(valor, str) and valor.startswith("https://")):
            problemas.append(f"URL '{chave_url}' inválida (precisa começar com https://): {valor!r}")

    logs_cfg = settings.get("logs", {})
    if not (1 <= logs_cfg.get("tamanho_max_mb", 0) <= 1000):
        problemas.append("Tamanho máximo de log deve estar entre 1 e 1000 MB.")

    return problemas


def validar_disciplinas(disciplinas: List["Disciplina"]) -> List[str]:
    problemas = []
    ativas = [d for d in disciplinas if d.ativa]
    if not ativas:
        problemas.append("Nenhuma disciplina ativa — adicione ou ative pelo menos uma antes de iniciar.")
    for d in ativas:
        if not d.codigo or not d.turma:
            problemas.append(f"Disciplina incompleta: código={d.codigo!r}, turma={d.turma!r}.")
        if not d.departamento or d.departamento <= 0:
            problemas.append(f"Disciplina {d.codigo}-{d.turma} está sem um departamento válido.")
    return problemas


@dataclass
class Disciplina:
    codigo: str
    turma: str
    departamento: int
    ativa: bool = True
    professor: str = ""

    def chave(self) -> str:
        return f"{self.codigo}-{self.turma}"

    def como_tupla(self):
        """Formato [codigo, turma, id_departamento] esperado pela engine (compatível com a v4.0)."""
        return [self.codigo, self.turma, self.departamento]


def carregar_disciplinas() -> List[Disciplina]:
    caminho = os.path.join(pasta_config(), ARQUIVO_DISCIPLINAS)
    bruto = _ler_json(caminho, [])
    disciplinas = []
    for item in bruto:
        try:
            disciplinas.append(Disciplina(
                codigo=str(item["codigo"]).strip().upper(),
                turma=str(item["turma"]).strip(),
                departamento=int(item["departamento"]),
                ativa=bool(item.get("ativa", True)),
                professor=str(item.get("professor", "")),
            ))
        except (KeyError, ValueError, TypeError):
            continue  # ignora entradas corrompidas em vez de travar o app
    return disciplinas


def salvar_disciplinas(disciplinas: List[Disciplina]) -> None:
    caminho = os.path.join(pasta_config(), ARQUIVO_DISCIPLINAS)
    _escrever_json(caminho, [asdict(d) for d in disciplinas])


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
    dado = _ler_json(caminho, None)
    return dado if isinstance(dado, dict) else None


def salvar_segredos_notificacao(telegram_token: str, telegram_chat_id: str, ntfy_topic: str) -> None:
    """
    Só deve ser chamada quando o usuário marcou explicitamente uma caixa do tipo
    "Salvar neste computador (arquivo não criptografado)" na GUI/terminal.
    Nunca é chamada automaticamente pelo app.
    """
    caminho = os.path.join(pasta_config(), ARQUIVO_SEGREDOS_NOTIFICACAO)
    _escrever_json(caminho, {
        "telegram_token": telegram_token,
        "telegram_chat_id": telegram_chat_id,
        "ntfy_topic": ntfy_topic,
    })


def apagar_segredos_notificacao() -> None:
    caminho = os.path.join(pasta_config(), ARQUIVO_SEGREDOS_NOTIFICACAO)
    if os.path.exists(caminho):
        os.remove(caminho)


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
                disciplinas_ok.append(Disciplina(
                    codigo=str(d["codigo"]).strip().upper(),
                    turma=str(d["turma"]).strip(),
                    departamento=int(d["departamento"]),
                    ativa=bool(d.get("ativa", True)),
                    professor=str(d.get("professor", "")),
                ))
            except (KeyError, ValueError, TypeError):
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

    return resumo
