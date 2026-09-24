"""
Experimento: sincronização de relógio via header HTTP do próprio SIGAA.

Origem: legacy/predecessores_http/BOT-SIGAA-HTTP-CAROL.py — usava o header
`Date` da resposta HTTP do SIGAA para descobrir o horário real do servidor e
agendar o início do ataque com mais precisão do que confiar só no relógio
local (que pode estar alguns segundos errado).

Por que é experimental e não foi incorporado ao motor principal: o
`AGENDAR_INICIO` da v4.0 já funciona (usa `datetime.now()` local) e trocar
esse mecanismo por padrão mudaria um comportamento que já funciona sem
necessidade clara — mas a diferença entre o relógio local e o do SIGAA pode
importar em disputas de poucos segundos por uma vaga concorrida, então fica
disponível aqui pra quem quiser usar/testar.

Sem dependências extra — usa só httpx, que já é dependência principal.
"""
from __future__ import annotations

import asyncio

from app.core.relogio import medir_offset_relogio  # promovido ao núcleo (sugestão 038): opção do agendamento
from app.experimental import Experimento, registrar


def _executar_sincrono() -> str:
    resultado = asyncio.run(medir_offset_relogio())
    sinal = "adiantado" if resultado["offset_segundos"] < 0 else "atrasado"
    return (
        f"Hora do servidor SIGAA: {resultado['hora_servidor']}\n"
        f"Hora deste computador: {resultado['hora_local']}\n"
        f"Diferença: este computador está {abs(resultado['offset_segundos']):.2f}s {sinal} "
        f"em relação ao SIGAA (medição com {resultado['latencia_ida_volta_segundos']*1000:.0f}ms de ida-e-volta).\n\n"
        f"Se essa diferença for grande (>1s), um agendamento baseado no relógio local pode disparar\n"
        f"cedo/tarde demais em disputas apertadas por vaga."
    )


registrar(Experimento(
    id="ntp_scheduler",
    nome="Sincronização de relógio com o SIGAA",
    descricao="Mede a diferença entre o relógio deste computador e o horário real do servidor do SIGAA, usando o header HTTP Date — sem precisar de NTP de verdade.",
    origem="legacy/predecessores_http/BOT-SIGAA-HTTP-CAROL.py",
    dependencias=[],
    riscos="Nenhum — só faz uma requisição HTTP de leitura ao SIGAA, não altera nada.",
    guia_instalacao="Nenhuma instalação necessária — usa a mesma biblioteca (httpx) do programa principal.",
    disponivel=lambda: True,
    executar=_executar_sincrono,
))
