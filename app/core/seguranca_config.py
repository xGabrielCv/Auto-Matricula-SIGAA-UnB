"""
Detector de configurações inseguras (Fase 5 — sugestão 067).

Junta num lugar só alertas que antes apareciam espalhados (ou não apareciam):
Interface Web exposta na rede, URLs fora da UnB, carga alta, proteção de carga
desligada, segredos de notificação salvos, pasta sincronizada com a nuvem e
matrícula real ligada. Nada aqui muda configuração — só explica e sugere.

Níveis: "risco" (pode expor dados ou prejudicar a conta) e "atencao"
(escolha legítima, mas vale confirmar que é intencional).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

HOSTS_LOCAIS = {"127.0.0.1", "localhost", "::1"}
PASTAS_NUVEM = ("onedrive", "dropbox", "google drive", "googledrive", "icloud", "meu drive", "my drive")


def _dominio_unb(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host == "unb.br" or host.endswith(".unb.br")


def alertas_de_configuracao(settings: Optional[Dict[str, Any]] = None, qtd_alvos: int = 1,
                            raiz: Optional[str] = None) -> List[Dict[str, str]]:
    from app.core.config import carregar_settings, estimar_carga, existe_segredos_notificacao_salvos
    from app.utils.paths import raiz_projeto
    s = settings if settings is not None else carregar_settings()
    alertas: List[Dict[str, str]] = []

    def alerta(id_, nivel, titulo, detalhe, acao, tela=""):
        alertas.append({"id": id_, "nivel": nivel, "titulo": titulo, "detalhe": detalhe, "acao": acao, "tela": tela})

    host = str((s.get("web") or {}).get("host", "127.0.0.1")).strip().lower()
    if host not in HOSTS_LOCAIS:
        alerta("web_exposta", "risco", "Interface Web acessível por outros aparelhos",
               f"O endereço configurado ({host}) permite que outros aparelhos da rede abram a Interface Web — "
               "protegida só pela chave de acesso do link.",
               "Use 127.0.0.1 em Configurações Avançadas → Interface Web, a não ser que precise mesmo do acesso pela rede.",
               "avancado")

    fora = sorted(nome for nome, url in (s.get("urls") or {}).items() if url and not _dominio_unb(str(url)))
    if fora:
        alerta("urls_fora_unb", "risco", "Endereços do SIGAA fora do domínio da UnB",
               f"{', '.join(fora)} não aponta(m) para unb.br. Suas credenciais seriam enviadas para esse endereço.",
               "Restaure os endereços padrão em Configurações Avançadas → URLs do SIGAA.", "avancado")

    protecao = s.get("protecao") or {}
    carga = estimar_carga(s.get("num_workers"), s.get("intervalo_busca"), qtd_alvos, protecao.get("limite_req_por_seg", 0))
    if carga.get("nivel") == "alta":
        alerta("carga_alta", "atencao", "Carga alta sobre o SIGAA", carga.get("alerta") or carga.get("texto", ""),
               "Escolha o perfil Moderado ou Leve em Configurações Avançadas.", "avancado")
    if not protecao.get("disjuntor", True) or not protecao.get("limite_req_por_seg"):
        alerta("protecao_desligada", "atencao", "Proteção de carga desligada",
               "Sem a pausa automática ou sem limite de buscas por segundo, o programa insiste mesmo com o SIGAA "
               "instável — mais carga no servidor e mais risco de bloqueio.",
               "Religue em Configurações Avançadas → Proteção de carga.", "avancado")

    from app.core.config import segredos_salvos_cifrados
    if existe_segredos_notificacao_salvos() and not segredos_salvos_cifrados():
        alerta("segredos_salvos", "atencao", "Tokens de notificação salvos neste computador",
               "Os tokens de notificação estão salvos em texto simples (a proteção de dados do Windows não estava "
               "disponível). Quem tiver acesso a esta pasta pode enviar mensagens pelo seu bot.",
               "Se o computador é compartilhado, apague os segredos salvos na tela Notificações.", "notificacoes")

    pasta = (raiz or raiz_projeto()).lower().replace("\\", "/")
    if any(seg.startswith(nome) for seg in pasta.split("/") for nome in PASTAS_NUVEM):
        alerta("pasta_nuvem", "atencao", "Programa numa pasta sincronizada com a nuvem",
               "Logs, histórico e páginas de diagnóstico desta pasta são enviados para a nuvem. Senha e CPF nunca "
               "são gravados, mas os logs mostram suas disciplinas e horários.",
               "Se preferir, mova a pasta do programa para fora do OneDrive/Dropbox/Google Drive.")

    if s.get("modo") == "matricula" and not s.get("dry_run", True):
        alerta("matricula_real", "atencao", "Matrícula real ligada",
               "O DRY RUN está desligado: ao achar vaga, o programa confirma a matrícula de verdade.",
               "Confirme que é isso mesmo. Para testar, ligue o DRY RUN na tela Execução.", "execucao")
    return alertas


def checar_configuracoes_inseguras(settings: Optional[Dict[str, Any]] = None) -> List[Any]:
    """Mesmos alertas no formato do Diagnóstico (❌ para risco, ⚪ para atenção)."""
    from app.core.diagnostics import ResultadoChecagem
    alertas = alertas_de_configuracao(settings)
    if not alertas:
        return [ResultadoChecagem("Configurações de segurança", True, "Nenhuma configuração insegura encontrada")]
    return [ResultadoChecagem(f"Segurança: {a['titulo']}", False if a["nivel"] == "risco" else None,
                              ("" if a["nivel"] == "risco" else "ATENÇÃO — ") + f"{a['detalhe']} → {a['acao']}") for a in alertas]


# ── Testar endereços do SIGAA (sugestão 047) ─────────────────────────────

def testar_urls(urls: Dict[str, str], cliente: Any = None, timeout: float = 6.0) -> List[Dict[str, Any]]:
    """GET sem credenciais em cada endereço configurado. Endereços fora da UnB
    NÃO são contatados (nada de testar um domínio desconhecido)."""
    import httpx
    proprio = cliente is None
    cliente = cliente or httpx.Client(timeout=timeout, follow_redirects=True,
                                      headers={"User-Agent": "Mozilla/5.0 (SIGAA Sniper - teste de endereco)"})
    resultados = []
    try:
        for nome, url in urls.items():
            item: Dict[str, Any] = {"nome": nome, "url": url, "dominio_ok": _dominio_unb(str(url)), "status": None,
                                    "pede_login": False, "ok": False}
            if not str(url).startswith("https://"):
                item["texto"] = "Não testado: o endereço precisa começar com https://."
            elif not item["dominio_ok"]:
                item["texto"] = "Não testado: fora do domínio unb.br (suas credenciais seriam enviadas para lá)."
            else:
                try:
                    resp = cliente.get(url)
                    final = str(resp.url).lower()
                    item["status"] = resp.status_code
                    item["pede_login"] = "autenticacao" in final or "login" in final or "sessão expirada" in resp.text.lower()
                    item["ok"] = resp.status_code < 500
                    if not item["ok"]:
                        item["texto"] = f"O SIGAA respondeu com erro (HTTP {resp.status_code}) — pode estar fora do ar."
                    elif item["pede_login"]:
                        item["texto"] = f"Responde (HTTP {resp.status_code}) e pede login — normal sem uma sessão aberta."
                    else:
                        item["texto"] = f"Responde (HTTP {resp.status_code})."
                except httpx.TimeoutException:
                    item["texto"] = "Sem resposta dentro do tempo limite."
                except httpx.HTTPError as e:
                    item["texto"] = f"Não foi possível conectar ({type(e).__name__})."
            resultados.append(item)
    finally:
        if proprio:
            cliente.close()
    return resultados
