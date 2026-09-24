"""
Validadores de entrada compartilhados pelas três interfaces (Web, GUI e terminal).

Uma regra, várias apresentações: cada interface só mostra a mensagem que vem
daqui. Nada disso faz rede — tudo roda antes de qualquer tentativa de login.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

_CARACTERES_CPF = re.compile(r"^[\d.\-\s]*$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_HOST = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")


def so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def normalizar_cpf(texto: str) -> str:
    """"123 456 789-09", "123.456.78909", "12345678909" → "123.456.789-09".
    Se não tiver 11 dígitos, devolve o texto limpo de espaços (a validação avisa)."""
    numeros = so_digitos(texto)
    if len(numeros) != 11:
        return (texto or "").strip()
    return f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"


def problema_cpf(texto: str) -> Optional[str]:
    """Descrição específica do problema com o CPF (None = válido)."""
    from app.core.credentials import cpf_valido
    t = (texto or "").strip()
    if not t:
        return "Informe o CPF."
    if not _CARACTERES_CPF.match(t):
        return "O CPF só pode ter números (pontos, traço e espaços são aceitos) — tire letras e outros símbolos."
    numeros = so_digitos(t)
    if len(numeros) != 11:
        return f"O CPF precisa ter 11 dígitos — você digitou {len(numeros)}."
    if numeros == numeros[0] * 11:
        return "CPF inválido — todos os dígitos iguais não formam um CPF."
    if not cpf_valido(numeros):
        return "CPF inválido — os dígitos verificadores não conferem. Confira se não há erro de digitação."
    return None


def problema_nascimento_texto(texto: str) -> Optional[str]:
    """Mesma regra da confirmação do SIGAA: DD/MM/AAAA. Aceita formas comuns
    (01022003, 1/2/2003, 01-02-2003) e diz exatamente o que está errado."""
    from app.core.credentials import normalizar_nascimento, problema_nascimento
    t = (texto or "").strip()
    if not t:
        return "Informe a data de nascimento no formato DD/MM/AAAA (ex: 01/02/2003)."
    if re.search(r"[^\d/.\-\s]", t):
        return "A data de nascimento só pode ter números e barras — use DD/MM/AAAA (ex: 01/02/2003)."
    normalizada = normalizar_nascimento(t)
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", normalizada)
    if not m:
        return "Data de nascimento incompleta — use DD/MM/AAAA, com o ano de 4 dígitos (ex: 01/02/2003)."
    dia, mes = int(m.group(1)), int(m.group(2))
    if not 1 <= mes <= 12:
        return f"Mês {mes:02d} não existe — use DD/MM/AAAA (o mês vem no meio)."
    if not 1 <= dia <= 31:
        return f"Dia {dia:02d} não existe — use DD/MM/AAAA."
    return problema_nascimento(normalizada)


def problema_email(endereco: str, rotulo: str = "E-mail") -> Optional[str]:
    t = (endereco or "").strip()
    if not t:
        return f"{rotulo}: informe um endereço."
    if not _EMAIL.match(t) or len(t) > 254:
        return f"{rotulo}: \"{t}\" não parece um endereço de e-mail válido (ex: nome@gmail.com)."
    return None


def problema_url_webhook(url: str) -> Optional[str]:
    t = (url or "").strip()
    if not t:
        return "Informe a URL do webhook."
    if " " in t:
        return "A URL do webhook não pode ter espaços."
    partes = urlsplit(t)
    if partes.scheme != "https":
        return "A URL do webhook precisa começar com https:// (conexão criptografada)."
    if not partes.hostname or "." not in partes.hostname:
        return "A URL do webhook está incompleta — copie o endereço inteiro gerado pelo Discord/Slack."
    return None


def problemas_email_cfg(cfg: Dict[str, Any], senha: str) -> List[str]:
    """Configuração completa do envio por e-mail (usada ao ativar e ao testar)."""
    problemas = []
    servidor = str(cfg.get("servidor", "")).strip()
    if not servidor:
        problemas.append("Informe o servidor SMTP (ex: smtp.gmail.com).")
    elif not _HOST.match(servidor) or "." not in servidor:
        problemas.append(f"Servidor SMTP \"{servidor}\" inválido — use só o nome do servidor, sem http:// (ex: smtp.gmail.com).")
    porta = cfg.get("porta", 587)
    if not (isinstance(porta, int) and not isinstance(porta, bool) and 1 <= porta <= 65535):
        problemas.append("Porta do e-mail inválida (normalmente 587 com STARTTLS ou 465 com SSL).")
    if cfg.get("seguranca", "starttls") not in ("starttls", "ssl"):
        problemas.append("Segurança do e-mail deve ser STARTTLS ou SSL.")
    for chave, rotulo in (("usuario", "Usuário do e-mail"), ("destinatario", "Destinatário")):
        p = problema_email(str(cfg.get(chave, "")), rotulo)
        if p:
            problemas.append(p)
    if str(cfg.get("remetente", "")).strip():
        p = problema_email(str(cfg.get("remetente")), "Remetente")
        if p:
            problemas.append(p)
    if not senha:
        problemas.append("Informe a senha do e-mail (Gmail/Outlook: use uma \"senha de app\").")
    return problemas
