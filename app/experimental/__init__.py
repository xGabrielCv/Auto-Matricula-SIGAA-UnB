"""
Área Experimental — seções 26-31 do pedido de continuação.

Regra central: nada aqui faz parte do caminho principal validado (motor de
matrícula/monitoramento). Cada experimento é isolado, documentado, e uma
falha dele NUNCA pode derrubar o programa principal (seção 30) — por isso
todo `executar()` registrado aqui é chamado sempre dentro de um try/except
pelo chamador (ver app/gui/screens/experimental.py).

As dependências específicas de cada experimento (ex: Selenium) NÃO fazem
parte de requirements.txt e NUNCA são instaladas automaticamente pelo
run.bat/instalador principal (seção 31) — isso mantém a distribuição
principal pequena e estável. Quem quiser rodar um experimento que precise de
algo extra recebe um guia manual (seção 29), nunca uma instalação silenciosa.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class Experimento:
    id: str
    nome: str
    descricao: str
    origem: str                # de qual versão legada isso veio
    dependencias: List[str]    # pacotes extras necessários (fora do requirements.txt principal)
    riscos: str
    guia_instalacao: str = ""
    disponivel: Callable[[], bool] = field(default=lambda: True)
    executar: Optional[Callable[[], str]] = None  # roda algo rápido e síncrono, devolve texto de resultado
    parar: Optional[Callable[[], None]] = None

    @property
    def status(self) -> str:
        return "Pronto para executar" if self.disponivel() else "Requer instalação manual"


_REGISTRO: List[Experimento] = []


def registrar(exp: Experimento) -> Experimento:
    _REGISTRO.append(exp)
    return exp


def listar_experimentos() -> List[Experimento]:
    # Import tardio de cada módulo de experimento — só o necessário para popular o registro,
    # sem puxar dependências pesadas na importação deste pacote.
    from app.experimental import ntp_scheduler, backoff_retry, monitor_publico_selenium  # noqa: F401
    return list(_REGISTRO)
