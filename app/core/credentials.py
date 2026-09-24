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
from datetime import date, datetime
from typing import List, Optional


def cpf_valido(cpf: str) -> bool:
    """Confere os dois dígitos verificadores do CPF (aceita com ou sem pontuação).

    Um CPF real sempre passa nesta conta — então recusar aqui nunca bloqueia
    um usuário legítimo, só erros de digitação. Sem isso, um CPF digitado
    errado só aparecia no pior momento: cada vaga encontrada virava uma
    confirmação recusada pelo SIGAA."""
    numeros = re.sub(r"\D", "", cpf or "")
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(numeros[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(numeros[tamanho]):
            return False
    return True


def normalizar_nascimento(texto: str) -> str:
    """Leva formas comuns de digitar a data ao formato DD/MM/AAAA que o SIGAA
    espera: "01022003" → "01/02/2003", "1/2/2003" → "01/02/2003",
    "01-02-2003" → "01/02/2003". Se não reconhecer, devolve o texto como veio
    (a validação é quem avisa)."""
    t = (texto or "").strip()
    if re.fullmatch(r"\d{8}", t):
        return f"{t[:2]}/{t[2:4]}/{t[4:]}"
    m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", t)
    if m:
        return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"
    return t


def problema_nascimento(texto: str, hoje: Optional[date] = None) -> Optional[str]:
    """Devolve a descrição do problema com a data (ou None se estiver ok)."""
    hoje = hoje or date.today()
    try:
        data = datetime.strptime(texto or "", "%d/%m/%Y").date()
    except ValueError:
        return "Data de nascimento inválida — use o formato DD/MM/AAAA com uma data que exista (ex: 01/02/2003)."
    if data >= hoje:
        return "Data de nascimento no futuro — confira o ano."
    if data.year < 1900:
        return "Data de nascimento com ano improvável — confira o ano."
    return None


@dataclass
class CredenciaisSigaa:
    """Credenciais de login do SIGAA. Vive só em memória, nunca em arquivo."""
    usuario: str = ""
    senha: str = ""
    cpf: str = ""
    nascimento: str = ""  # formato DD/MM/AAAA, como o SIGAA espera

    def preenchida(self) -> bool:
        return bool(self.usuario and self.senha and self.cpf and self.nascimento)

    def problemas(self) -> List[str]:
        """Problemas de formato que fariam a confirmação da matrícula ser recusada.
        Só olha campos preenchidos — campo vazio é tratado por preenchida()."""
        from app.core.validadores import problema_cpf, problema_nascimento_texto
        encontrados = []
        for valor, validar in ((self.cpf, problema_cpf), (self.nascimento, problema_nascimento_texto)):
            if valor:
                problema = validar(valor)
                if problema:
                    encontrados.append(problema)
        return encontrados

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
    # Fase 6: URL do webhook (081) e senha do e-mail (082) também são segredos.
    webhook_url: str = ""
    email_senha: str = ""

    def telegram_configurado(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)

    def ntfy_configurado(self) -> bool:
        return bool(self.ntfy_topic)

    def webhook_configurado(self) -> bool:
        return self.webhook_url.startswith("https://")

    def limpar(self) -> None:
        self.telegram_token = self.telegram_chat_id = self.ntfy_topic = ""
        self.webhook_url = self.email_senha = ""


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
