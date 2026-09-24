"""
Monta um MotorMatricula pronto para rodar a partir de settings + credenciais
+ disciplinas — ponto único usado pela GUI e pelo terminal para não duplicar
a lógica de "como montar o motor" em dois lugares (seção 50 do pedido).
"""
from __future__ import annotations

import logging
from typing import Callable, List, Optional

from app.core.config import Disciplina
from app.core.credentials import SessaoCredenciais
from app.core.engine import MotorMatricula
from app.core.logging_setup import configurar_logging
from app.notifications.manager import GerenciadorNotificacoes


def construir_motor(
    settings: dict,
    sessao: SessaoCredenciais,
    disciplinas: List[Disciplina],
    on_evento_extra: Optional[Callable[[str, dict], None]] = None,
    demo: bool = False,
) -> MotorMatricula:
    if demo:
        # Modo demonstração (077): SIGAA simulado, credenciais fictícias, DRY RUN
        # sempre ligado e sem relógio do SIGAA (não há SIGAA de verdade para medir).
        from app.core.credentials import SessaoCredenciais
        from app.core.demo import CREDENCIAIS_DEMO, DISCIPLINAS_EXEMPLO
        settings = {**settings, "dry_run": True, "agendamento_relogio_sigaa": False}
        sessao = SessaoCredenciais(sigaa=CREDENCIAIS_DEMO, notificacao=sessao.notificacao)
        if not any(d.ativa for d in disciplinas):
            disciplinas = [Disciplina(c, t, d) for c, t, d in DISCIPLINAS_EXEMPLO]
    nivel_console = logging.DEBUG if settings.get("debug", {}).get("nivel_log_console") == "DEBUG" else logging.INFO
    logger = configurar_logging(
        tamanho_max_mb=settings["json_audit"]["tamanho_max_mb"],
        arquivos_mantidos=settings["json_audit"]["arquivos_mantidos"],
        nivel_console=nivel_console,
    )

    disciplinas_ativas = [d.como_alvo() for d in disciplinas if d.ativa]

    cfg_notif = settings["notificacoes"]
    gerenciador = GerenciadorNotificacoes(
        eventos_ativos=cfg_notif["eventos"],
        canais_ativos={
            "telegram": cfg_notif["telegram_ativo"],
            "ntfy": cfg_notif["ntfy_ativo"],
            "alarme": cfg_notif["alarme_ativo"],
            "windows": cfg_notif.get("windows_ativo", False),
            "webhook": cfg_notif.get("webhook_ativo", False),
            "email": cfg_notif.get("email_ativo", False),
        },
        webhook_formato=cfg_notif.get("webhook_formato", "discord"),
        email_cfg=cfg_notif.get("email"),
        credenciais=sessao.notificacao,
        limite_janela=cfg_notif["limite_notificacoes_janela"],
        janela_seg=cfg_notif["janela_notificacoes_seg"],
        alarme_repeticoes=cfg_notif["alarme"]["repeticoes"],
        alarme_duracao_seg=cfg_notif["alarme"]["duracao_seg"],
        logger=logger,
    )

    def on_evento(tipo: str, dados: dict) -> None:
        gerenciador.notificar_evento(tipo, {**dados, "demo": True} if demo else dados)
        if on_evento_extra:
            on_evento_extra(tipo, dados)

    transporte = None
    if demo:
        from app.core.demo import transporte_demo
        from app.core.engine import URLS_PADRAO
        transporte = transporte_demo(disciplinas_ativas, {**URLS_PADRAO, **(settings.get("urls") or {})})
    motor = MotorMatricula(
        credenciais=sessao.sigaa,
        disciplinas=disciplinas_ativas,
        num_workers=settings["num_workers"],
        intervalo_busca=settings["intervalo_busca"],
        timeout_req=settings["timeout_req"],
        dry_run=settings["dry_run"],
        agendar_inicio=settings["agendar_inicio"],
        modo=settings["modo"],
        urls=settings.get("urls"),
        logger=logger,
        on_evento=on_evento,
        historico=settings.get("historico"),
        protecao=settings.get("protecao"),
        agendar_fim=settings.get("agendar_fim"),
        janela=settings.get("janela"),
        relogio_sigaa=bool(settings.get("agendamento_relogio_sigaa")),
        verificacao_previa=bool(settings.get("verificacao_previa", True)),
        alertas=settings.get("alertas"),
        transporte=transporte,
        demo=demo,
        resumo_intervalo_horas=(cfg_notif.get("resumo_intervalo_horas", 6)
                                if cfg_notif["eventos"].get("resumo_periodico") else 0),
    )
    motor.aguardar_notificacoes = gerenciador.aguardar_pendentes
    return motor
