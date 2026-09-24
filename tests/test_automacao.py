"""Automação avançada (Fase 4): pausa (036), janela e término (035), relógio do SIGAA (038),
verificação prévia (040), classificação com parada segura (092), grupos (033), prioridade (034)
e disciplinas alteradas com a execução em andamento (037)."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta

from app.core import engine
from app.core.config import Disciplina, analisar_disciplina, carregar_settings, validar_settings
from app.core.regras import classificar_resposta_confirmacao, dentro_da_janela, inspecionar_turma
from app.core.runner import ExecutorMotor
from tests.test_engine_fluxo import credenciais, montar, pagina_resultado, rodar, rodar_ate, sigaa  # noqa: F401


def _motor(alvos, **kw):
    eventos = []
    motor = engine.MotorMatricula(
        credenciais=credenciais(), disciplinas=alvos, num_workers=kw.pop("num_workers", 1), intervalo_busca=0.01,
        timeout_req=5, dry_run=kw.pop("dry_run", True), modo=kw.pop("modo", "matricula"),
        logger=logging.getLogger("teste_automacao"), on_evento=lambda t, d: eventos.append((t, d)), **kw)
    return motor, eventos


# ── Regras puras ─────────────────────────────────────────────────────────

def test_janela_de_execucao_inclusive_cruzando_meia_noite():
    j = {"ativa": True, "inicio": "07:00", "fim": "23:00", "dias": [0, 1, 2, 3, 4]}
    seg_8h, sab_8h, seg_23h30 = datetime(2026, 9, 21, 8), datetime(2026, 9, 26, 8), datetime(2026, 9, 21, 23, 30)
    assert dentro_da_janela(j, seg_8h) and not dentro_da_janela(j, sab_8h) and not dentro_da_janela(j, seg_23h30)
    noite = {"ativa": True, "inicio": "22:00", "fim": "02:00", "dias": [4]}  # sexta à noite
    assert dentro_da_janela(noite, datetime(2026, 9, 25, 23)) and dentro_da_janela(noite, datetime(2026, 9, 26, 1))
    assert not dentro_da_janela(noite, datetime(2026, 9, 26, 3)) and not dentro_da_janela(noite, datetime(2026, 9, 24, 23))
    assert dentro_da_janela({"ativa": False}, sab_8h)


def test_validacao_de_janela_termino_e_prioridade(raiz_temporaria):
    s = carregar_settings()
    assert validar_settings(s) == []
    s.update({"janela": {"ativa": True, "inicio": "25:00", "fim": "07:00", "dias": []},
              "agendar_inicio": "10/10/2026 10:00:00", "agendar_fim": "10/10/2026 09:00:00"})
    problemas = " ".join(validar_settings(s))
    assert "horário de inicio" in problemas and "dia da semana" in problemas and "término precisa ser depois" in problemas
    erros, _ = analisar_disciplina(Disciplina("FGA0211", "01", 673, prioridade="urgente"), [])
    assert erros and "Prioridade" in erros[0]
    # mesma disciplina em duas turmas no MESMO grupo: sem o aviso de "mais de uma turma"
    existentes = [Disciplina("FGA0211", "01", 673, grupo="calculo")]
    _, avisos = analisar_disciplina(Disciplina("FGA0211", "03", 673, grupo="calculo"), existentes)
    assert not any("mais de uma turma" in a for a in avisos)
    _, avisos = analisar_disciplina(Disciplina("FGA0211", "03", 673), existentes)
    assert any("GRUPO" in a for a in avisos)


def test_classificacao_usa_a_mensagem_de_erro_e_so_para_na_direcao_segura():
    assert classificar_resposta_confirmacao("Senha incorreta.")["decisao"] == "parar"
    assert classificar_resposta_confirmacao("Fora do período de matrícula extraordinária")["categoria"] == "periodo_encerrado"
    assert classificar_resposta_confirmacao("Não há vagas disponíveis")["decisao"] == "tentar_de_novo"
    assert classificar_resposta_confirmacao("Choque de horário com FGA0100")["categoria"] == "choque_horario"
    # rótulo de formulário não é erro: "Data de Nascimento" sozinho não dispara parada
    assert classificar_resposta_confirmacao("Data de Nascimento:")["categoria"] == "desconhecido"


def test_inspecao_de_turma_para_a_verificacao_previa():
    html = pagina_resultado(3)
    assert inspecionar_turma(html, "FGA0211", "01") == {"disciplina_encontrada": True, "turma_encontrada": True, "vagas": 3,
                                                          "turmas_vistas": ["01", "02"]}
    assert inspecionar_turma(html, "FGA0211", "09")["turma_encontrada"] is False
    assert inspecionar_turma(html, "MAT0025", "01")["disciplina_encontrada"] is False


# ── Motor contra o SIGAA simulado ────────────────────────────────────────

def test_pausar_e_retomar_mantem_a_sessao(sigaa):  # noqa: F811
    sigaa.vagas = 0
    motor, eventos = montar(modo="monitoramento")

    async def cenario():
        async def controlar():
            while motor.telemetria.requisicoes < 5:
                await asyncio.sleep(0.02)
            motor.pausar()
            await asyncio.sleep(0.1)
            congeladas = motor.telemetria.requisicoes
            await asyncio.sleep(0.6)
            assert motor.telemetria.requisicoes == congeladas  # nada de busca pausado
            assert motor.snapshot()["workers"][0]["estado"] == "pausado"
            motor.retomar()
            while motor.telemetria.requisicoes < congeladas + 5:
                await asyncio.sleep(0.02)
            motor.parar()
        await asyncio.gather(motor.executar(), controlar())

    asyncio.run(asyncio.wait_for(cenario(), 15))
    posts_cas = [r for r in sigaa.requisicoes if r[0] == "POST" and "sso-server" in r[1]]
    assert len(posts_cas) == 1  # retomar não faz novo login
    tipos = [t for t, _ in eventos]
    assert tipos.index("execucao_pausada") < tipos.index("execucao_retomada")


def test_pausa_pedida_de_outra_thread_pelo_executor(sigaa):  # noqa: F811
    sigaa.vagas = 0
    motor, _ = montar(modo="monitoramento")
    executor = ExecutorMotor(motor)
    executor.iniciar()
    try:
        limite = time.time() + 10
        while motor.telemetria.requisicoes < 3 and time.time() < limite:
            time.sleep(0.02)
        executor.chamar(motor.pausar)
        time.sleep(0.3)
        assert motor.pausado and motor.snapshot()["pausado"]
        executor.chamar(motor.retomar)
        time.sleep(0.2)
        assert not motor.pausado
    finally:
        executor.parar()
        executor.aguardar(10)


def test_fora_da_janela_pausa_sozinho_e_usuario_nao_fura(sigaa):  # noqa: F811
    sigaa.vagas = 0
    agora = datetime.now()
    fora = {"ativa": True, "inicio": (agora + timedelta(hours=2)).strftime("%H:%M"),
            "fim": (agora + timedelta(hours=3)).strftime("%H:%M"), "dias": list(range(7))}
    motor, eventos = _motor([["FGA0211", "01", 673]], modo="monitoramento", janela=fora)
    rodar_ate(motor, lambda m: m.pausado and m.motivo_pausa == "janela")
    assert ("execucao_pausada", {"motivo": "janela"}) in eventos
    assert motor.retomar() is False  # só a própria janela retoma


def test_horario_de_termino_encerra_a_execucao(sigaa):  # noqa: F811
    sigaa.vagas = 0
    fim = (datetime.now() + timedelta(seconds=2)).strftime("%d/%m/%Y %H:%M:%S")
    motor, _ = _motor([["FGA0211", "01", 673]], modo="monitoramento", agendar_fim=fim)
    rodar(motor, timeout=15)  # termina sozinha
    assert motor.motivo_fim == "fim_agendado" and motor.resumo["motivo_fim"] == "fim_agendado"


def test_agendamento_pelo_relogio_do_sigaa(sigaa, monkeypatch):  # noqa: F811
    async def offset_falso(*_a, **_k):
        return {"offset_segundos": 3.0, "hora_servidor": "", "hora_local": "", "latencia_ida_volta_segundos": 0.01}
    monkeypatch.setattr(engine, "medir_offset_relogio", offset_falso)
    alvo = datetime.now().replace(microsecond=0) + timedelta(seconds=4)
    motor, _ = _motor([["FGA0211", "01", 673]], agendar_inicio=alvo.strftime("%d/%m/%Y %H:%M:%S"), relogio_sigaa=True)
    inicio = time.time()
    rodar(motor, timeout=15)
    # O SIGAA está 3 s à frente: o disparo acontece ~3 s antes do horário no relógio local.
    assert motor.offset_relogio_seg == 3.0
    primeiro_login = next(i for i, r in enumerate(sigaa.requisicoes) if "sso-server" in r[1])
    assert primeiro_login == 0 and time.time() - inicio < 4


def test_verificacao_previa_aponta_turma_e_disciplina_inexistentes(sigaa):  # noqa: F811
    sigaa.vagas = 0
    motor, eventos = _motor([["FGA0211", "01", 673], ["FGA0211", "09", 673], ["MAT0025", "01", 673]],
                            modo="monitoramento", verificacao_previa=True)
    rodar_ate(motor, lambda m: m.fase == "monitorando")
    resultado = {a["chave"]: a.get("verificacao", {}).get("resultado") for a in motor.snapshot()["alvos"]}
    assert resultado == {"FGA0211-01": "ok", "FGA0211-09": "turma_nao_encontrada", "MAT0025-01": "disciplina_nao_encontrada"}
    evento = next(d for t, d in eventos if t == "verificacao_previa")
    assert evento["login"] == "ok" and len(evento["resultados"]) == 3


def test_verificacao_previa_com_login_recusado_nao_solta_os_workers(sigaa):  # noqa: F811
    sigaa.login_recusado = True
    motor, _ = _motor([["FGA0211", "01", 673]], verificacao_previa=True, num_workers=5)
    rodar(motor, timeout=10)
    posts_cas = [r for r in sigaa.requisicoes if r[0] == "POST" and "sso-server" in r[1]]
    assert len(posts_cas) == 1 and motor.motivo_fim == "login_recusado" and motor._workers == []


def test_dados_de_confirmacao_recusados_param_a_execucao(sigaa):  # noqa: F811
    sigaa.resposta_final = "<span class='erro'>Senha incorreta.</span>"
    motor, eventos = montar(dry_run=False)
    rodar(motor, timeout=15)  # para sozinho: nada de tentar de novo com senha errada
    assert len(sigaa.posts_confirmacao()) == 1
    assert motor.motivo_fim == "dados_incorretos"
    assert any(t == "parada_seguranca" and d["motivo"] == "dados_incorretos" for t, d in eventos)


def test_vaga_esgotada_continua_tentando(sigaa):  # noqa: F811
    sigaa.resposta_final = "<span class='erro'>Não há vagas disponíveis nesta turma.</span>"
    motor, _ = montar(dry_run=False)
    rodar_ate(motor, lambda m: len(sigaa.posts_confirmacao()) >= 2)  # decisão da v4.0 preservada: tenta de novo
    assert motor.motivo_forcado is None


def test_grupo_de_alternativas_dispensa_as_outras_turmas(sigaa):  # noqa: F811
    motor, eventos = _motor([["FGA0211", "01", 673, "calculo"], ["FGA0211", "02", 673, "calculo"]])
    rodar(motor)
    estados = {a["chave"]: a["estado"] for a in motor.snapshot()["alvos"]}
    assert estados == {"FGA0211-01": "simulada", "FGA0211-02": "dispensada"}
    assert len(sigaa.posts_selecao()) == 1 and motor.motivo_fim == "concluida"
    assert any(t == "grupo_dispensado" for t, _ in eventos)


def test_prioridade_baixa_e_consultada_menos(sigaa):  # noqa: F811
    sigaa.vagas = 0
    motor, _ = _motor([["FGA0211", "01", 673, "", "normal"], ["FGA0211", "03", 673, "", "baixa"]], modo="monitoramento")
    rodar_ate(motor, lambda m: m.estado_alvos["FGA0211-01"]["buscas"] >= 12)
    normal, baixa = motor.estado_alvos["FGA0211-01"]["buscas"], motor.estado_alvos["FGA0211-03"]["buscas"]
    assert 1 <= baixa <= normal / 2


def test_alterar_disciplinas_com_a_execucao_em_andamento(sigaa):  # noqa: F811
    sigaa.vagas = 0
    motor, _ = _motor([["FGA0211", "01", 673]], modo="monitoramento")

    async def cenario():
        async def mexer():
            while motor.estado_alvos["FGA0211-01"]["buscas"] < 3:
                await asyncio.sleep(0.02)
            motor.adicionar_alvo(["FGA0211", "02", 673, "", "normal"])
            motor.remover_alvo("FGA0211-01")
            while motor.estado_alvos["FGA0211-02"]["buscas"] < 3:
                await asyncio.sleep(0.02)
            motor.parar()
        await asyncio.gather(motor.executar(), mexer())

    asyncio.run(asyncio.wait_for(cenario(), 15))
    estados = {a["chave"]: a["estado"] for a in motor.snapshot()["alvos"]}
    assert estados["FGA0211-01"] == "removida" and motor.estado_alvos["FGA0211-02"]["buscas"] >= 3
