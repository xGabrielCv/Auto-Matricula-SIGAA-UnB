"""
Integridade do executável e aviso de novas versões (Fase 7 — sugestões 069 e 099).

- `hash_executavel()`: SHA-256 do próprio .exe em execução, para comparar com o
  SHA256SUMS.txt publicado junto do pacote (o tamanho do arquivo, sozinho, não
  prova que o executável é o legítimo).
- `verificar_atualizacao()`: UMA consulta à API pública de versões do GitHub —
  só quando a pessoa pede ou ligou a opção. Nunca baixa nem instala nada:
  apenas avisa e mostra o link.
"""
from __future__ import annotations

import hashlib
import re
import sys
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

from app.versao import URL_REPOSITORIO, VERSAO_APP

_cache_hash: Optional[str] = None


def sha256_arquivo(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def hash_executavel() -> Optional[str]:
    """SHA-256 do executável (None quando rodando pelo código-fonte)."""
    global _cache_hash
    if not getattr(sys, "frozen", False):
        return None
    if _cache_hash is None:
        try:
            _cache_hash = sha256_arquivo(sys.executable)
        except OSError:
            return None
    return _cache_hash


def _versao_tupla(texto: str) -> tuple:
    numeros = re.findall(r"\d+", texto or "")[:3]
    return tuple(int(n) for n in numeros) + (0,) * (3 - len(numeros))


def url_api_ultima_versao() -> str:
    caminho = urlsplit(URL_REPOSITORIO).path.strip("/")
    return f"https://api.github.com/repos/{caminho}/releases/latest"


def verificar_atualizacao(cliente: Any = None, timeout: float = 8.0) -> Dict[str, Any]:
    import httpx
    proprio = cliente is None
    cliente = cliente or httpx.Client(timeout=timeout, follow_redirects=True,
                                      headers={"Accept": "application/vnd.github+json", "User-Agent": f"SIGAA-Sniper/{VERSAO_APP}"})
    base = {"atual": VERSAO_APP, "ultima": None, "nova": False, "url": f"{URL_REPOSITORIO}/releases"}
    try:
        resp = cliente.get(url_api_ultima_versao())
    except httpx.HTTPError as e:
        return {**base, "ok": False, "texto": f"Não foi possível consultar o GitHub agora ({type(e).__name__})."}
    finally:
        if proprio:
            cliente.close()
    if resp.status_code == 404:
        return {**base, "ok": True, "texto": "Ainda não há versões publicadas no GitHub para comparar."}
    if resp.status_code != 200:
        return {**base, "ok": False, "texto": f"O GitHub respondeu HTTP {resp.status_code}; tente mais tarde."}
    try:
        dados = resp.json()
    except ValueError:
        return {**base, "ok": False, "texto": "Resposta inesperada do GitHub."}
    ultima = str(dados.get("tag_name") or "").lstrip("vV")
    url = str(dados.get("html_url") or base["url"])
    if not url.startswith(URL_REPOSITORIO):
        url = base["url"]  # só aponta para o repositório oficial
    nova = bool(ultima) and _versao_tupla(ultima) > _versao_tupla(VERSAO_APP)
    texto = (f"Há uma versão nova: {ultima} (você usa {VERSAO_APP}). Baixe pelo repositório oficial." if nova
             else f"Você está com a versão mais recente ({VERSAO_APP}).")
    return {**base, "ok": True, "ultima": ultima or None, "nova": nova, "url": url, "texto": texto}
