"""Proteção de carga (Fase 4): limitador global (071), logins escalonados (073), disjuntor (039)."""
from __future__ import annotations

import asyncio
import time

from app.core import engine
from app.core.config import estimar_carga, validar_settings, carregar_settings
from app.core.protecao import Disjuntor, LimitadorTaxa
from tests.test_engine_fluxo import montar, rodar_ate, sigaa  # noqa: F401  (fixture)


def test_limitador_segura_o_ritmo():
    async def cenario():
        lim = LimitadorTaxa(10)
        inicio = time.monotonic()
        for _ in range(25):
            await lim.adquirir()
        return time.monotonic() - inicio, lim.esperas
    duracao, esperas = asyncio.run(cenario())
    # 10 de rajada + 15 a 10/s ≈ 1,5 s
    assert 1.2 <= duracao <= 2.5 and esperas > 0


def test_limitador_desligado_nao_espera():
    async def cenario():
        lim = LimitadorTaxa(0)
        inicio = time.monotonic()
        for _ in range(500):
            await lim.adquirir()
        return time.monotonic() - inicio
    assert asyncio.run(cenario()) < 0.2


def test_maquina_de_estados_do_disjuntor():
    mudancas = []
    d = Disjuntor(limiar_falhas=3, espera_inicial_seg=0.2, ao_mudar=lambda e, s: mudancas.append(e))
    d.registrar_falha(); d.registrar_falha()
    assert d.estado == "fechado"
    d.registrar_falha()
    assert d.estado == "aberto" and d.segundos_para_reabrir() > 0

    async def cenario():
        parado = lambda: False  # noqa: E731
        await d.liberar(1, parado)          # espera vencer → worker 1 vira a sonda
        assert d.estado == "meio_aberto" and d.sonda == 1
        outro = asyncio.create_task(d.liberar(2, parado))
        await asyncio.sleep(0.3)
        assert not outro.done()              # só a sonda passa no meio aberto
        d.registrar_falha()                  # sonda falhou → abre de novo com o dobro da espera
        assert d.estado == "aberto" and d.espera_atual == 0.4
        await outro                          # depois da espera, worker 2 vira sonda
        d.registrar_sucesso()
    asyncio.run(cenario())
    assert d.estado == "fechado" and d.espera_atual == 0.2
    assert mudancas == ["aberto", "meio_aberto", "aberto", "meio_aberto", "fechado"]


def test_disjuntor_desligado_nunca_abre():
    d = Disjuntor(limiar_falhas=1, ativo=False)
    for _ in range(10):
        d.registrar_falha()
    assert d.estado == "fechado"


def test_sigaa_sobrecarregado_abre_o_disjuntor_sem_relogar(sigaa, monkeypatch):  # noqa: F811
    sigaa.sobrecarga_nas_primeiras = 10_000
    motor, eventos = montar(dry_run=True)
    motor.disjuntor.limiar = 4
    motor.disjuntor.espera_atual = motor.disjuntor.espera_inicial = 30
    rodar_ate(motor, lambda m: m.disjuntor.estado == "aberto")
    buscas_ate_abrir = sigaa._buscas
    snap = motor.snapshot()
    assert buscas_ate_abrir == 4 and snap["telemetria"]["erros"]["sobrecarga"]["total"] == 4
    posts_cas = [r for r in sigaa.requisicoes if r[0] == "POST" and "sso-server" in r[1]]
    assert len(posts_cas) == 1, "HTTP 503 não deve provocar relogin"
    assert ("disjuntor_aberto", {"espera_seg": 30}) in eventos


def test_disjuntor_para_buscas_e_retoma_quando_o_sigaa_volta(sigaa):  # noqa: F811
    sigaa.sobrecarga_nas_primeiras = 3
    motor, eventos = montar(dry_run=True)
    motor.disjuntor.limiar = 3
    motor.disjuntor.espera_atual = motor.disjuntor.espera_inicial = 0.5
    rodar_ate(motor, lambda m: m.fim_ts is not None, timeout=20)  # termina sozinho: DRY RUN simula a matrícula
    tipos = [t for t, _ in eventos]
    assert tipos.index("disjuntor_aberto") < tipos.index("disjuntor_fechado") < tipos.index("matricula_sucesso")
    assert motor.resumo["totais"]["simuladas"] == 1


def test_logins_simultaneos_limitados(sigaa, monkeypatch):  # noqa: F811
    class Contador:
        agora = 0
        maximo = 0

    real_realizar = engine.SigaaWorker._realizar_login

    async def login_lento(self):
        Contador.agora += 1
        Contador.maximo = max(Contador.maximo, Contador.agora)
        try:
            await asyncio.sleep(0.1)
            return await real_realizar(self)
        finally:
            Contador.agora -= 1

    monkeypatch.setattr(engine.SigaaWorker, "_realizar_login", login_lento)
    motor, _ = montar(dry_run=True)
    motor.num_workers = 6
    motor.cfg_protecao["logins_simultaneos"] = 2
    rodar_ate(motor, lambda m: m.fim_ts is not None, timeout=20)
    assert Contador.maximo == 2


def test_configuracao_e_carga_estimada_com_teto(raiz_temporaria):
    s = carregar_settings()
    assert s["protecao"] == {"limite_req_por_seg": 20, "logins_simultaneos": 3, "disjuntor": True}
    assert validar_settings(s) == []
    s["protecao"]["limite_req_por_seg"] = 500
    assert any("buscas por segundo" in p for p in validar_settings(s))
    carga = estimar_carga(20, 0.3, 1, limite=10)
    assert carga["req_por_seg"] == 10 and carga["limitada"] and "teto" in carga["texto"]
    assert not estimar_carga(4, 1.5, 1, limite=10)["limitada"]
