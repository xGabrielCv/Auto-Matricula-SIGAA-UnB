"""
Credenciais em memória — a regra mais importante de segurança do projeto.

NADA neste módulo grava em disco. As credenciais do SIGAA (e, por padrão,
também as de notificação) só existem enquanto o processo Python está rodando
e desaparecem quando o programa fecha. Isso é intencional e não deve ser
"melhorado" adicionando persistência automática no futuro.

Se um dia for necessário depurar por que uma credencial "sumiu" entre uma
execução e outra: não é bug, é a funcionalidade.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CredenciaisSigaa:
    """Credenciais de login do SIGAA. Vive só em memória, nunca em arquivo."""
    usuario: str = ""
    senha: str = ""
    cpf: str = ""
    nascimento: str = ""  # formato DD/MM/AAAA, como o SIGAA espera

    def preenchida(self) -> bool:
        return bool(self.usuario and self.senha and self.cpf and self.nascimento)

    def cpf_numeros(self) -> str:
        return re.sub(r"\D", "", self.cpf)

    def limpar(self) -> None:
        """Sobrescreve os campos antes de descartar o objeto (higiene de memória)."""
        self.usuario = self.senha = self.cpf = self.nascimento = ""


@dataclass
class CredenciaisNotificacao:
    """
    Credenciais dos canais de notificação (Telegram/ntfy).

    Por padrão também são somente-memória, pelo mesmo princípio aplicado às
    credenciais do SIGAA. A GUI pode oferecer "salvar neste computador" como
    opt-in explícito (ver app/core/config.py: salvar_segredos_notificacao),
    nunca como comportamento automático.
    """
    telegram_token: str = ""
    telegram_chat_id: str = ""
    ntfy_topic: str = ""
    ntfy_servidor: str = "https://ntfy.sh"

    def telegram_configurado(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)

    def ntfy_configurado(self) -> bool:
        return bool(self.ntfy_topic)

    def limpar(self) -> None:
        self.telegram_token = self.telegram_chat_id = self.ntfy_topic = ""


@dataclass
class SessaoCredenciais:
    """Agrupa tudo que é sensível numa única execução do programa."""
    sigaa: CredenciaisSigaa = field(default_factory=CredenciaisSigaa)
    notificacao: CredenciaisNotificacao = field(default_factory=CredenciaisNotificacao)

    def limpar_tudo(self) -> None:
        self.sigaa.limpar()
        self.notificacao.limpar()


_sessao_global: Optional[SessaoCredenciais] = None


def obter_sessao() -> SessaoCredenciais:
    """Singleton simples em memória de processo — não é salvo em nenhum lugar."""
    global _sessao_global
    if _sessao_global is None:
        _sessao_global = SessaoCredenciais()
    return _sessao_global


def encerrar_sessao() -> None:
    """Chame ao fechar o app (GUI/terminal) para apagar credenciais da memória."""
    global _sessao_global
    if _sessao_global is not None:
        _sessao_global.limpar_tudo()
    _sessao_global = None
