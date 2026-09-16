"""
Experimento: backoff exponencial com jitter para respostas HTTP retriáveis
(429/502/503/504).

Origem: legacy/predecessores_http/BOT-SIGAA-HTTP-CAROL.py — tinha um
decorator de retry mais refinado que a v4.0 (que já trata timeout/erro de
rede, mas não distingue por código de status HTTP retriável específico).

Por que é experimental: a v4.0 já tem uma estratégia de recuperação
funcional (resetar_cliente + relogin em qualquer falha) — trocar isso por
padrão mudaria um comportamento que já funciona. Esta função fica disponível
como uma ferramenta isolada para quem quiser usá-la em cima do motor
principal sem alterar o comportamento validado por padrão.

Sem dependências extra.
"""
from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, TypeVar

import httpx

from app.experimental import Experimento, registrar

T = TypeVar("T")

STATUS_RETRIAVEIS = {429, 502, 503, 504}


async def com_retry_e_backoff(
    chamada: Callable[[], Awaitable[httpx.Response]],
    tentativas_max: int = 5,
    espera_base_seg: float = 0.5,
    espera_max_seg: float = 8.0,
) -> httpx.Response:
    """Executa `chamada()` de novo com backoff exponencial + jitter se a resposta
    vier com um status HTTP retriável. Propaga a exceção/resposta na última tentativa."""
    ultima_resposta = None
    for tentativa in range(1, tentativas_max + 1):
        resposta = await chamada()
        if resposta.status_code not in STATUS_RETRIAVEIS:
            return resposta
        ultima_resposta = resposta
        if tentativa == tentativas_max:
            break
        espera = min(espera_max_seg, espera_base_seg * (2 ** (tentativa - 1)))
        espera_com_jitter = espera * (0.5 + random.random())  # 50%-150% do valor calculado
        await asyncio.sleep(espera_com_jitter)
    return ultima_resposta


async def _autoteste() -> str:
    """Simula um servidor que responde 503 duas vezes e depois 200, usando
    httpx.MockTransport — não faz nenhuma requisição real, é 100% offline."""
    chamadas = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        if chamadas["n"] < 3:
            return httpx.Response(503, text="Serviço temporariamente indisponível")
        return httpx.Response(200, text="ok")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        async def chamar():
            return await client.get("https://exemplo.invalido/teste")

        resp = await com_retry_e_backoff(chamar, tentativas_max=5, espera_base_seg=0.01, espera_max_seg=0.05)

    ok = resp.status_code == 200 and chamadas["n"] == 3
    return (
        f"Autoteste (offline, sem tocar no SIGAA de verdade):\n"
        f"Simulei um servidor respondendo 503 duas vezes e depois 200.\n"
        f"Chamadas feitas: {chamadas['n']} — resultado final: HTTP {resp.status_code}\n"
        f"{'✅ Backoff funcionou como esperado (tentou 3x e usou a resposta boa).' if ok else '❌ Resultado inesperado.'}"
    )


def _executar_sincrono() -> str:
    return asyncio.run(_autoteste())


registrar(Experimento(
    id="backoff_retry",
    nome="Retry com backoff exponencial (429/502/503/504)",
    descricao="Função utilitária isolada que tenta de novo automaticamente, com espera crescente e aleatória, quando o SIGAA responde com um status HTTP de sobrecarga/indisponibilidade temporária. Não é usada pelo motor principal por padrão.",
    origem="legacy/predecessores_http/BOT-SIGAA-HTTP-CAROL.py",
    dependencias=[],
    riscos="Nenhum ao rodar o autoteste (100% offline/simulado). Se usado com o SIGAA de verdade, retries mal configurados podem aumentar a carga na sua conexão — use os valores padrão.",
    guia_instalacao="Nenhuma instalação necessária.",
    disponivel=lambda: True,
    executar=_executar_sincrono,
))
