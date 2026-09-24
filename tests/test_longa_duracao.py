"""
Teste de longa duração (Fase 7 — sugestão 078). Fora da suíte padrão.

Roda o motor real contra o SIGAA simulado do modo demonstração por vários
minutos (monitoramento, 4 workers, vagas abrindo e fechando) e mede o que
costuma dar problema em execuções noturnas: memória do processo, handles/
arquivos abertos, filas internas que deveriam ser limitadas e o log.

Para rodar:  SIGAA_SNIPER_LONGO=30 python -m pytest tests/test_longa_duracao.py -s
(o número é a duração em minutos)
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest

MINUTOS = float(os.environ.get("SIGAA_SNIPER_LONGO", "0") or 0)


def _handles() -> int:
    if sys.platform != "win32":
        return len(os.listdir("/proc/self/fd")) if os.path.isdir("/proc/self/fd") else 0
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = wintypes.HANDLE  # sem isso o pseudo-handle -1 é truncado em 64 bits
    k32.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    contagem = wintypes.DWORD()
    if not k32.GetProcessHandleCount(k32.GetCurrentProcess(), ctypes.byref(contagem)):
        raise OSError("GetProcessHandleCount falhou")
    return contagem.value


@pytest.mark.skipif(MINUTOS <= 0, reason="teste longo: defina SIGAA_SNIPER_LONGO=<minutos> para rodar")
def test_execucao_longa_sem_vazamentos(raiz_temporaria):
    from app.core.config import carregar_settings
    from app.core.credentials import SessaoCredenciais
    from app.core.factory import construir_motor
    from app.core.resource_monitor import medir_memoria_mb

    settings = {**carregar_settings(), "num_workers": 4, "intervalo_busca": 0.2, "modo": "monitoramento",
                "json_audit": {"tamanho_max_mb": 1, "arquivos_mantidos": 2}}
    motor = construir_motor(settings, SessaoCredenciais(), [], demo=True)
    motor.opcoes_cliente["transport"].handler.prob_abrir = 0.02
    amostras = []

    async def vigiar():
        inicio = time.time()
        while time.time() - inicio < MINUTOS * 60:
            await asyncio.sleep(10)
            amostras.append((time.time() - inicio, medir_memoria_mb(), _handles(), motor.telemetria.requisicoes))
        motor.parar()

    async def cenario():
        await asyncio.gather(motor.executar(), vigiar())

    asyncio.run(cenario())
    aquecido = [a for a in amostras if a[0] >= 60] or amostras
    memoria = [a[1] for a in aquecido if a[1] is not None]
    handles = [a[2] for a in aquecido]
    relatorio = (f"{MINUTOS:g} min · {motor.telemetria.requisicoes} buscas · memória {memoria[0]:.0f} -> {memoria[-1]:.0f} MB "
                 f"(máx {max(memoria):.0f}) · handles {handles[0]} -> {handles[-1]} (máx {max(handles)})")
    print("\n" + relatorio)
    assert motor.telemetria.requisicoes > MINUTOS * 60  # continuou buscando o tempo todo
    assert memoria[-1] - memoria[0] < 60, relatorio      # sem crescimento contínuo de memória
    assert handles[0] > 0, relatorio                     # a medição funcionou
    assert handles[-1] - handles[0] < 150, relatorio     # sem vazamento de conexões/arquivos
    snap = motor.snapshot()
    assert len(snap["telemetria"]["pontos"]) <= 3600 and len(snap["tentativas"]) <= 50
    assert sum(len(v) for v in snap["telemetria"]["vagas_series"].values()) <= 500 * max(1, len(snap["alvos"]))
    logs = [n for n in os.listdir(raiz_temporaria / "data") if n.startswith("sigaa_sniper_audit.json")]
    assert len(logs) <= 3, logs  # rotação respeita "arquivos_mantidos"


MINUTOS_PARADO = float(os.environ.get("SIGAA_SNIPER_LONGO_PARADO", "0") or 0)


@pytest.mark.skipif(MINUTOS_PARADO <= 0, reason="teste longo: defina SIGAA_SNIPER_LONGO_PARADO=<minutos> para rodar")
def test_interface_aberta_e_parada_por_muito_tempo(raiz_temporaria):
    """Pós-6.0.0: a Interface Web aberta, sendo consultada como a página faz
    (estado a cada 2 s, dashboard, logs), sem nenhuma execução. Nada que dependa
    de execução pode mudar, nenhum arquivo pode crescer e nada pode vazar."""
    import threading
    import httpx
    from app.core.disclaimer import CONFIRMACOES
    from app.core.resource_monitor import medir_memoria_mb
    from app.web.estado import EstadoWeb
    from app.web.server import criar_servidor

    e = EstadoWeb()
    s = criar_servidor(e, "127.0.0.1", 0)
    threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True).start()
    H = {"X-Requested-With": "SIGAA-Sniper"}

    def arquivos():
        saida = {}
        for pasta in ("data", "logs", "config"):
            caminho = raiz_temporaria / pasta
            if caminho.exists():
                for nome in os.listdir(caminho):
                    alvo = caminho / nome
                    if alvo.is_file():
                        saida[f"{pasta}/{nome}"] = alvo.stat().st_size
        return saida

    with httpx.Client(base_url=f"http://127.0.0.1:{s.porta}", timeout=10) as c:
        c.get(f"/?chave={s.chave}")
        c.post("/api/aviso-legal/aceitar", headers=H, json={"confirmacoes": {k: True for k, _ in CONFIRMACOES}})

        def foto():
            d = c.get("/api/dashboard", headers=H).json()
            lg = c.get("/api/logs", headers=H).json()
            est = c.get("/api/estado", headers=H).json()
            return {k: d[k] for k in ("uptime", "total_buscas", "total_reqs", "workers_com_alerta", "saude", "tem_dados",
                                       "recuperado", "execucao_ativa", "painel", "vagas_encontradas", "erros_totais")} | {
                "logs": lg["ultimo_seq"], "em_execucao": est["execucao"]["em_execucao"], "eventos": len(est["eventos"])}

        inicial, arquivos_ini = foto(), arquivos()
        mem_ini, threads_ini, handles_ini = medir_memoria_mb(), threading.active_count(), _handles()
        fim = time.time() + MINUTOS_PARADO * 60
        consultas = 0
        while time.time() < fim:
            assert foto() == inicial, "algo que depende de execução mudou com o programa parado"
            consultas += 1
            time.sleep(2)
        mem_fim, threads_fim, handles_fim = medir_memoria_mb(), threading.active_count(), _handles()
    s.shutdown()
    s.server_close()
    e.finalizar()
    relatorio = (f"{MINUTOS_PARADO:g} min parado · {consultas} consultas · memória {mem_ini:.0f} -> {mem_fim:.0f} MB · "
                 f"threads {threads_ini} -> {threads_fim} · handles {handles_ini} -> {handles_fim}")
    print("\n" + relatorio)
    assert arquivos() == arquivos_ini, "arquivos mudaram com o programa parado"
    assert mem_fim - mem_ini < 30 and threads_fim <= threads_ini + 2 and handles_fim - handles_ini < 100, relatorio
