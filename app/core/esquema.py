"""
Esquema único dos campos numéricos da configuração (Fase 7 — sugestão 044).

Antes, cada faixa estava escrita em até quatro lugares — validação, Spinbox da
interface gráfica, <input> da Web e terminal — e já tinha divergido (o tamanho
do log aceitava 1–1000 na validação e 1–500 na tela; o JSON de auditoria nem
era validado). Agora a faixa de cada campo mora aqui: `validar_settings` usa
este esquema, a interface gráfica pede a faixa com `faixa()` e a Web recebe o
esquema junto das configurações avançadas.
"""
from __future__ import annotations

from typing import Any, Dict, List, NamedTuple, Optional, Tuple


class Campo(NamedTuple):
    rotulo: str
    minimo: float
    maximo: float
    inteiro: bool = True
    unidade: str = ""
    padrao_ausente: Optional[float] = None  # valor assumido se a chave não existir (configs antigas)


ESQUEMA: Dict[str, Campo] = {
    "num_workers": Campo("Número de workers", 1, 100),
    "intervalo_busca": Campo("Intervalo de busca", 0.05, 60, inteiro=False, unidade=" segundos"),
    "timeout_req": Campo("Timeout de requisição", 1, 120, unidade=" segundos"),
    "logs.tamanho_max_mb": Campo("Tamanho máximo dos dumps de debug", 1, 500, unidade=" MB"),
    "logs.arquivos_mantidos": Campo("Dumps de debug mantidos", 0, 50, padrao_ausente=5),
    "json_audit.tamanho_max_mb": Campo("Tamanho máximo do log principal", 1, 500, unidade=" MB", padrao_ausente=20),
    "json_audit.arquivos_mantidos": Campo("Arquivos antigos do log principal", 0, 50, padrao_ausente=3),
    "historico.dias_retencao": Campo("Retenção do histórico", 0, 3650, unidade=" dias (0 = guardar sempre)", padrao_ausente=180),
    "protecao.limite_req_por_seg": Campo("Limite de buscas por segundo", 0, 200, inteiro=False, unidade=" (0 = sem limite)", padrao_ausente=20),
    "protecao.logins_simultaneos": Campo("Logins simultâneos", 1, 20, padrao_ausente=3),
    "web.porta": Campo("Porta da Interface Web", 1024, 65535, padrao_ausente=8765),
    "web.expirar_inatividade_min": Campo("Expiração da Interface Web", 0, 720, unidade=" minutos (0 = nunca)", padrao_ausente=0),
    "alertas.taxa_erro_pct": Campo("Limite da taxa de erro (%)", 5, 100, padrao_ausente=30),
    "alertas.taxa_erro_min": Campo("Minutos da taxa de erro", 1, 60, padrao_ausente=2),
    "alertas.sem_resposta_min": Campo("Minutos sem resposta do SIGAA", 1, 120, padrao_ausente=5),
    "alertas.sem_busca_min": Campo("Minutos sem nenhuma busca", 1, 120, padrao_ausente=2),
    "interface.escala_fonte": Campo("Tamanho da fonte da interface gráfica (%)", 80, 160, padrao_ausente=100),
    "notificacoes.resumo_intervalo_horas": Campo("Intervalo do resumo periódico", 0.5, 48, inteiro=False, unidade=" horas", padrao_ausente=6),
}


def faixa(chave: str) -> Tuple[float, float]:
    campo = ESQUEMA[chave]
    return campo.minimo, campo.maximo


def _obter(settings: Dict[str, Any], chave: str, padrao: Any) -> Any:
    atual: Any = settings
    for parte in chave.split("."):
        if not isinstance(atual, dict) or parte not in atual:
            return padrao
        atual = atual[parte]
    return atual


def _numero(valor: float) -> str:
    return str(int(valor)) if float(valor).is_integer() else str(valor).replace(".", ",")


def problemas_numericos(settings: Dict[str, Any]) -> List[str]:
    problemas = []
    for chave, campo in ESQUEMA.items():
        valor = _obter(settings, chave, campo.padrao_ausente if campo.padrao_ausente is not None else 0)
        tipo_ok = isinstance(valor, int) if campo.inteiro else isinstance(valor, (int, float))
        if not tipo_ok or isinstance(valor, bool) or not campo.minimo <= valor <= campo.maximo:
            problemas.append(f"{campo.rotulo} deve estar entre {_numero(campo.minimo)} e {_numero(campo.maximo)}{campo.unidade}.")
    return problemas


def esquema_para_web() -> Dict[str, Dict[str, Any]]:
    return {chave: {"min": c.minimo, "max": c.maximo, "inteiro": c.inteiro} for chave, c in ESQUEMA.items()}
