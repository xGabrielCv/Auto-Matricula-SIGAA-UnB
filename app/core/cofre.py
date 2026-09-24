"""
Cofre dos segredos de notificação (Fase 6 — sugestão 065).

Quando a pessoa escolhe "Salvar neste computador", os tokens de notificação
(Telegram, tópico do ntfy, URL de webhook, senha do e-mail) passam a ser
CIFRADOS com a DPAPI do Windows (CryptProtectData), atrelada à conta do
Windows: uma cópia do arquivo em outro computador ou em outra conta não
decifra. Sem biblioteca externa — só `ctypes`, como em resource_monitor.

Fora do Windows (ou se a DPAPI falhar) o comportamento anterior continua —
texto simples, com o aviso explícito na tela. As credenciais do SIGAA NUNCA
passam por aqui: continuam só em memória, por princípio do projeto.
"""
from __future__ import annotations

import base64
import json
import sys
from typing import Any, Dict, Optional

FORMATO_DPAPI = "dpapi-v1"
_ENTROPIA = b"SIGAA-Sniper/segredos-de-notificacao"


def dpapi_disponivel() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return hasattr(ctypes, "windll") and hasattr(ctypes.windll, "crypt32")
    except Exception:
        return False


def _blob(dados: bytes):
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(dados, len(dados))
    return DATA_BLOB(len(dados), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer, DATA_BLOB


def _chamar(funcao_nome: str, dados: bytes) -> bytes:
    import ctypes
    entrada, _buf_entrada, DATA_BLOB = _blob(dados)
    entropia, _buf_entropia, _ = _blob(_ENTROPIA)
    saida = DATA_BLOB()
    funcao = getattr(ctypes.windll.crypt32, funcao_nome)
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    if funcao_nome == "CryptProtectData":
        ok = funcao(ctypes.byref(entrada), "SIGAA Sniper", ctypes.byref(entropia), None, None,
                    CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(saida))
    else:
        ok = funcao(ctypes.byref(entrada), None, ctypes.byref(entropia), None, None,
                    CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(saida))
    if not ok:
        raise OSError(f"{funcao_nome} falhou (código {ctypes.GetLastError()})")
    try:
        return ctypes.string_at(saida.pbData, saida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(saida.pbData)


def cifrar(segredos: Dict[str, Any]) -> Dict[str, Any]:
    """Devolve o conteúdo a gravar no arquivo: cifrado (DPAPI) ou, sem DPAPI, o próprio dicionário."""
    if not dpapi_disponivel():
        return dict(segredos)
    try:
        bruto = json.dumps(segredos, ensure_ascii=False).encode("utf-8")
        return {"formato": FORMATO_DPAPI, "dados": base64.b64encode(_chamar("CryptProtectData", bruto)).decode("ascii")}
    except Exception:
        return dict(segredos)  # nunca perde o que a pessoa pediu para salvar


def decifrar(conteudo: Any) -> Optional[Dict[str, Any]]:
    """Aceita o formato cifrado e o antigo (texto simples). None se não der para ler."""
    if not isinstance(conteudo, dict):
        return None
    if conteudo.get("formato") != FORMATO_DPAPI:
        return conteudo  # arquivo antigo, em texto simples
    if not dpapi_disponivel():
        return None
    try:
        bruto = _chamar("CryptUnprotectData", base64.b64decode(conteudo.get("dados", "")))
        dados = json.loads(bruto.decode("utf-8"))
        return dados if isinstance(dados, dict) else None
    except Exception:
        return None  # outra conta/outro computador: não decifra


def esta_cifrado(conteudo: Any) -> bool:
    return isinstance(conteudo, dict) and conteudo.get("formato") == FORMATO_DPAPI


def descricao_armazenamento() -> str:
    if dpapi_disponivel():
        return ("cifrados com a proteção de dados do Windows (DPAPI), atrelada à sua conta do Windows — "
                "uma cópia do arquivo em outro computador ou outra conta não pode ser lida")
    return "gravados em texto simples (não criptografado) — a proteção de dados do Windows não está disponível aqui"
