"""
Estado e ações da Interface Web — equivalente web de app/gui/app.py + telas.

Cada método aqui reproduz a MESMA regra que a tela correspondente da GUI
(validações, confirmações, mensagens), chamando o mesmo núcleo (app/core,
app/dashboard, app/notifications). O servidor HTTP (app/web/server.py) só
traduz requisições JSON para estas chamadas.

Confirmações que na GUI são caixas "Sim/Não" viram aqui um erro 409 com
`precisa_confirmar: True`: a página mostra a pergunta e, se o usuário
confirmar, reenvia a mesma ação com `confirmado: true`. Assim nenhuma
confirmação existente pode ser pulada chamando a API diretamente.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
import time
from collections import deque
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from app.core.config import (
    LATENCIA_REFERENCIA_SEG, LIMITE_CARGA_BAIXA, LIMITE_CARGA_MODERADA, PADROES_SETTINGS, PRESETS_CARGA,
    SECOES_RESTAURAVEIS,
    Disciplina, analisar_disciplina, aplicar_segredos_notificacao_salvos, apagar_segredos_notificacao,
    carregar_disciplinas, carregar_settings, estimar_carga, existe_segredos_notificacao_salvos,
    exportar_configuracao, importar_configuracao, interpretar_lote, pre_visualizar_importacao, restaurar_padroes,
    salvar_disciplinas, salvar_segredos_notificacao, salvar_settings, validar_disciplinas, validar_settings,
    aplicar_perfil, apagar_perfil, listar_perfis, listar_versoes_config, restaurar_versao_config, salvar_perfil,
)
from app.core import auditoria
from app.core.credentials import encerrar_sessao, normalizar_nascimento, obter_sessao
from app.core.crash_recovery import verificar_encerramento_anterior
from app.core.departamentos import buscar_departamentos, codigo_conhecido, nome_do_departamento
from app.core.diagnostics import (
    VERSAO_APP, ResultadoChecagem, checar_conectividade_em_camadas, checar_conectividade_sigaa,
    checar_modo_execucao, checar_saude_sistema, gerar_relatorio_texto,
)
from app.core.disclaimer import CONFIRMACOES, RESUMOS_CURTOS, TEXTO_COMPLETO, TITULO
from app.core.cofre import descricao_armazenamento
from app.core.esquema import esquema_para_web
from app.core.textos import ROTULOS_EVENTOS_NOTIFICACAO, textos_ajuda
from app.notifications import windows as windows_notif
from app.core.factory import construir_motor
from app.core.runner import ExecutorMotor
from app.core import historico as historico_mod
from app.core.relatorios import MOTIVOS_FIM
from app.core.resource_monitor import medir_memoria_mb
from app.dashboard.analise import (
    agrupar_erros, avaliar_saude, descrever_fase, series_grafico, sparklines, tempo_relativo,
)
from app.dashboard.linha_do_tempo import linha_do_tempo
from app.dashboard.log_humano import CATEGORIAS, traduzir
from app.dashboard.metrics import ColetorMetricas, LogTailer, formatar_uptime
from app.utils.cleanup import limpar_debug_dumps, resumo_espaco_em_disco
from app.utils.paths import caminho as caminho_projeto
from app.utils.paths import pasta_config, pasta_docs
from app.versao import URL_REPOSITORIO

MAX_LOGS_MEMORIA = 1000  # mesmo limite da tela de Logs da GUI
MAX_EVENTOS_NOTIFICACAO = 50
INTERVALO_REPETIR_VAGA_SEG = 60

# Eventos do motor que viram aviso na Central de notificações da página
# (sugestão 088). Mesmos textos das notificações externas (Telegram/ntfy).
TEXTOS_EVENTOS = {
    "vaga_detectada": ("sucesso", lambda d: f"Vaga encontrada em {d.get('codigo')}-{d.get('turma')} ({d.get('vagas')} vaga(s))!"),
    "matricula_sucesso": ("sucesso", lambda d: (
        f"[TESTE] Matrícula simulada com sucesso em {d.get('codigo')}-{d.get('turma')} (DRY RUN — nada foi confirmado)."
        if d.get("dry_run") else f"Matrícula CONFIRMADA em {d.get('codigo')}-{d.get('turma')}!")),
    "matricula_bloqueada": ("aviso", lambda d: f"{d.get('codigo')}-{d.get('turma')} bloqueada pelo SIGAA (pré-requisito/choque) — deixou de ser monitorada."),
    "matricula_falha": ("aviso", lambda d: f"Tentativa de matrícula em {d.get('codigo')}-{d.get('turma')} falhou — o programa vai tentar de novo."),
    "erro_critico": ("erro", lambda d: f"Erro crítico no worker W{d.get('worker')}: {d.get('erro')}"),
    # Fase 4
    "execucao_pausada": ("info", lambda d: "Execução pausada — fora da janela de execução; volta sozinha no próximo horário."
                         if d.get("motivo") == "janela" else "Execução pausada. As sessões continuam abertas; clique em Retomar."),
    "execucao_retomada": ("info", lambda d: "Execução retomada."),
    "disjuntor_aberto": ("aviso", lambda d: f"SIGAA instável: buscas pausadas por {d.get('espera_seg', 0):.0f}s para não sobrecarregá-lo."),
    "disjuntor_fechado": ("sucesso", lambda d: "SIGAA respondendo de novo: buscas retomadas."),
    "parada_seguranca": ("erro", lambda d: f"Execução parada por segurança: {d.get('explicacao')}"),
    "grupo_dispensado": ("sucesso", lambda d: f"Grupo '{d.get('grupo')}': {d.get('garantida')} garantida — "
                         f"{', '.join(d.get('dispensadas', []))} saiu(ram) da busca."),
    "verificacao_previa": ("aviso", lambda d: _texto_verificacao(d)),
    # Fase 5
    "alerta_limiar": ("aviso", lambda d: f"{d.get('titulo')}: {d.get('texto')}" if d.get("estado") == "ativo"
                      else str(d.get("texto"))),
    "worker_reiniciado": ("aviso", lambda d: f"O worker W{d.get('worker')} ficou {d.get('parado_seg')}s sem progresso e foi recriado."),
}


def _texto_verificacao(d: Dict[str, Any]) -> str:
    if d.get("login") == "recusado":
        return "Verificação prévia: o SIGAA recusou o login — a execução não começou. Confira matrícula e senha."
    problemas = [r for r in d.get("resultados", []) if r.get("resultado") != "ok"]
    if not problemas:
        return f"Verificação prévia: login ok e {len(d.get('resultados', []))} disciplina(s) encontrada(s)."
    return "Verificação prévia: " + "; ".join(f"{r['chave']}: {r['texto']}" for r in problemas)


class ErroApi(Exception):
    """Erro de negócio que vira uma resposta JSON com status HTTP específico."""

    def __init__(self, status: int, mensagem: str, **extra: Any):
        super().__init__(mensagem)
        self.status = status
        self.mensagem = mensagem
        self.extra = extra


def _precisa_confirmar(mensagem: str, **extra: Any) -> ErroApi:
    return ErroApi(409, mensagem, precisa_confirmar=True, **extra)


def _bool(valor: Any) -> bool:
    return valor is True or (isinstance(valor, str) and valor.lower() in ("1", "true", "sim", "on"))


def _int(valor: Any, nome: str, minimo: int, maximo: int) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        raise ErroApi(400, f"{nome}: informe um número inteiro.")
    if not (minimo <= numero <= maximo):
        raise ErroApi(400, f"{nome}: deve estar entre {minimo} e {maximo}.")
    return numero


def _float(valor: Any, nome: str) -> float:
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        raise ErroApi(400, f"{nome}: informe um número.")


def _resultado_json(r: ResultadoChecagem) -> Dict[str, Any]:
    return {"nome": r.nome, "ok": r.ok, "detalhe": r.detalhe}


class EstadoWeb:
    def __init__(self):
        self.lock = threading.RLock()
        self.evento_encerrar = threading.Event()
        auditoria.definir_origem("web")
        self.ultima_atividade = time.time()  # Fase 6 (070): expiração por inatividade
        self._verificacao_versao_feita = False
        self.aviso_aceito = False  # nunca persistido: o aviso aparece em TODA execução

        # Mesma ordem de inicialização da GUI (app/gui/app.py).
        self.sessao = obter_sessao()
        self.settings = carregar_settings()
        self.disciplinas: List[Disciplina] = carregar_disciplinas()
        aplicar_segredos_notificacao_salvos(self.sessao.notificacao)
        self.primeira_execucao = (
            not self.settings.get("assistente_concluido") and not self.disciplinas
        )
        self.encerramento_anterior = verificar_encerramento_anterior()
        limpar_debug_dumps(manter=self.settings["logs"]["arquivos_mantidos"])

        self._executor: Optional[ExecutorMotor] = None
        self._motor = None  # última execução desta sessão (os painéis continuam mostrando depois que ela termina)
        self._historico_importado = False
        self._status: Dict[str, Any] = {"estado": "parado", "mensagem": "Parado.", "modo": None, "dry_run": None, "inicio": None}

        self._lock_metricas = threading.Lock()
        self._coletor = ColetorMetricas()
        # Desde a 6.1.0: o log de auditoria guarda TODAS as execuções. Por padrão o
        # Dashboard e a Central de Logs começam do fim dele (nada de execução
        # anterior aparecendo como se fosse a atual); com "carregar_ultima_execucao"
        # ligado, leem o que já existe e mostram marcado como recuperado.
        self.carregar_ultima = bool(self.settings.get("carregar_ultima_execucao"))
        caminho_log = caminho_projeto("data", "sigaa_sniper_audit.json")
        self._tailer_dashboard: Optional[LogTailer] = LogTailer(caminho_log)
        self._backlog_dashboard_lido = False

        self._lock_eventos = threading.Lock()
        self._eventos: deque = deque(maxlen=MAX_EVENTOS_NOTIFICACAO)
        self._seq_eventos = 0
        self._ultima_vaga_avisada: Dict[str, tuple] = {}  # chave → (vagas, instante)

        self._lock_logs = threading.Lock()
        self._logs: deque = deque(maxlen=MAX_LOGS_MEMORIA)
        self._seq_logs = 0
        self._tailer_logs: Optional[LogTailer] = LogTailer(caminho_log)
        if not self.carregar_ultima:
            self._tailer_dashboard.pular_para_o_fim()
            self._tailer_logs.pular_para_o_fim()

    # ── Estado geral ──────────────────────────────────────────────────────

    def estado(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "versao": VERSAO_APP,
                "aviso_aceito": self.aviso_aceito,
                "primeira_execucao": self.primeira_execucao,
                "encerramento_anterior": self.encerramento_anterior,
                "execucao": self.status_execucao(),
                "credenciais_preenchidas": self.sessao.sigaa.preenchida(),
                "problemas_credenciais": self.sessao.sigaa.problemas(),
                "carga": self._carga_estimada(),
                "alertas_seguranca": self._alertas_seguranca(),
                "perfis": [{"arquivo": p["arquivo"], "nome": p["nome"]} for p in listar_perfis()],
                "qtd_disciplinas": len(self.disciplinas),
                "qtd_disciplinas_ativas": sum(1 for d in self.disciplinas if d.ativa),
                "modo": self.settings["modo"],
                "dry_run": self.settings["dry_run"],
                "agendar_inicio": self.settings.get("agendar_inicio") or "",
                "agendar_fim": self.settings.get("agendar_fim") or "",
                "janela": {**PADROES_SETTINGS["janela"], **(self.settings.get("janela") or {})},
                "agendamento_relogio_sigaa": bool(self.settings.get("agendamento_relogio_sigaa")),
                "verificacao_previa": bool(self.settings.get("verificacao_previa", True)),
                "grupos": sorted({d.grupo for d in self.disciplinas if d.grupo}),
                "eventos": self.eventos_recentes(),
                "abrir_dashboard_ao_iniciar": self.settings.get("abrir_dashboard_ao_iniciar", True),
                "ajuda": textos_ajuda(),
            }

    def _alertas_seguranca(self) -> List[Dict[str, str]]:
        """Sugestão 067 — só os que não repetem a checklist (carga e matrícula real já aparecem nela)."""
        from app.core.seguranca_config import alertas_de_configuracao
        try:
            return [a for a in alertas_de_configuracao(self.settings, max(1, sum(1 for d in self.disciplinas if d.ativa)))
                    if a["id"] not in ("carga_alta", "matricula_real")]
        except Exception:
            return []

    def _carga_estimada(self, num_workers: Any = None, intervalo: Any = None) -> Dict[str, Any]:
        ativas = sum(1 for d in self.disciplinas if d.ativa)
        return estimar_carga(
            self.settings["num_workers"] if num_workers is None else num_workers,
            self.settings["intervalo_busca"] if intervalo is None else intervalo,
            ativas, self.settings.get("protecao", {}).get("limite_req_por_seg", 0),
        )

    # ── Central de notificações (sugestão 088) ───────────────────────────

    def _registrar_evento(self, tipo: str, texto: str, nivel: str) -> None:
        with self._lock_eventos:
            self._seq_eventos += 1
            self._eventos.append({"seq": self._seq_eventos, "tipo": tipo, "nivel": nivel,
                                  "texto": texto, "hora": time.strftime("%H:%M:%S")})

    def _ao_evento_motor(self, tipo: str, dados: dict) -> None:
        """Chamado pela thread do motor (via construir_motor). Só guarda texto —
        nunca faz I/O nem pode atrasar o monitoramento."""
        definicao = TEXTOS_EVENTOS.get(tipo)
        if tipo == "verificacao_previa" and dados.get("login") == "ok" and all(
                r.get("resultado") == "ok" for r in dados.get("resultados", [])):
            definicao = ("sucesso", TEXTOS_EVENTOS[tipo][1])
        if tipo == "vaga_detectada":
            # No modo monitoramento a mesma vaga é vista a cada ciclo; só avisa de novo
            # se a quantidade mudar ou depois de um tempo (evita dezenas de avisos iguais).
            chave = f"{dados.get('codigo')}-{dados.get('turma')}"
            agora = time.time()
            anterior = self._ultima_vaga_avisada.get(chave)
            if anterior and anterior[0] == dados.get("vagas") and agora - anterior[1] < INTERVALO_REPETIR_VAGA_SEG:
                return
            self._ultima_vaga_avisada[chave] = (dados.get("vagas"), agora)
        if tipo == "alerta_limiar" and dados.get("estado") != "ativo":
            definicao = ("sucesso", TEXTOS_EVENTOS[tipo][1])
        if definicao:
            nivel, gerar = definicao
            self._registrar_evento(tipo, gerar(dados), nivel)

    def eventos_recentes(self) -> List[Dict[str, Any]]:
        with self._lock_eventos:
            return list(self._eventos)

    # ── Aviso legal (seções 94.8-94.13) ─────────────────────────────────

    @staticmethod
    def aviso_legal() -> Dict[str, Any]:
        return {
            "titulo": TITULO,
            "texto": TEXTO_COMPLETO,
            "confirmacoes": [
                {"chave": chave, "texto": texto, "resumo": RESUMOS_CURTOS.get(chave, texto[:80])}
                for chave, texto in CONFIRMACOES
            ],
            "repositorio": URL_REPOSITORIO,
        }

    def aceitar_aviso(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        if not self._verificacao_versao_feita:
            self._verificacao_versao_feita = True
            self._verificar_ao_abrir()
        marcadas = dados.get("confirmacoes") or {}
        faltando = [chave for chave, _ in CONFIRMACOES if marcadas.get(chave) is not True]
        if faltando:
            raise ErroApi(400, "É preciso confirmar TODOS os pontos do aviso legal para continuar.", faltando=faltando)
        with self.lock:
            self.aviso_aceito = True
        auditoria.registrar_aceite_aviso()
        return {"ok": True}

    def recusar_aviso(self) -> Dict[str, Any]:
        # Mesmo efeito de "Recusar e sair" na GUI: encerra este modo.
        auditoria.registrar("aviso_recusado")
        self.evento_encerrar.set()
        return {"ok": True, "mensagem": "Você optou por não aceitar os termos. A Interface Web foi encerrada."}

    # ── Credenciais (só memória) ──────────────────────────────────────────

    def credenciais(self) -> Dict[str, Any]:
        cred = self.sessao.sigaa
        # A senha nunca volta para a página — só se ela existe.
        return {"usuario": cred.usuario, "cpf": cred.cpf, "nascimento": cred.nascimento,
                "tem_senha": bool(cred.senha), "preenchida": cred.preenchida()}

    def salvar_credenciais(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        cred = self.sessao.sigaa
        with self.lock:
            cred.usuario = str(dados.get("usuario", "")).strip()
            senha = str(dados.get("senha", ""))
            if senha or not _bool(dados.get("manter_senha")):
                cred.senha = senha
            cred.cpf = str(dados.get("cpf", "")).strip()
            cred.nascimento = normalizar_nascimento(str(dados.get("nascimento", "")))
        if not cred.preenchida():
            raise ErroApi(400, "Preencha matrícula, senha, CPF e data de nascimento.", credenciais=self.credenciais())
        problemas = cred.problemas()
        if problemas:
            # Os valores ficam em memória (como na GUI) para o usuário só corrigir o campo errado,
            # mas a execução não inicia enquanto houver problema (ver iniciar()).
            raise ErroApi(400, "Confira os dados — com eles a confirmação da matrícula seria recusada pelo SIGAA:",
                          problemas=problemas, credenciais=self.credenciais())
        auditoria.registrar("credenciais_preenchidas")
        return {"ok": True, "mensagem": "Credenciais mantidas em memória para esta execução (nada foi salvo em disco).",
                "credenciais": self.credenciais()}

    def limpar_credenciais(self) -> Dict[str, Any]:
        self.sessao.sigaa.limpar()
        auditoria.registrar("credenciais_limpas")
        return {"ok": True, "mensagem": "Campos apagados da tela e da memória.", "credenciais": self.credenciais()}

    # ── Disciplinas ───────────────────────────────────────────────────────

    def listar_disciplinas(self) -> Dict[str, Any]:
        with self.lock:
            return {"disciplinas": [
                {**asdict(d), "indice": i, "chave": d.chave(), "nome_departamento": nome_do_departamento(d.departamento),
                 "departamento_conhecido": codigo_conhecido(d.departamento)}
                for i, d in enumerate(self.disciplinas)
            ]}

    @staticmethod
    def buscar_departamentos(termo: str, todos: bool = False) -> Dict[str, Any]:
        from app.core.departamentos import info_lista
        encontrados = buscar_departamentos(termo or "")
        return {"departamentos": [{"codigo": d.codigo, "nome": d.nome} for d in (encontrados if todos else encontrados[:25])],
                "total": len(encontrados), "info": info_lista()}

    @staticmethod
    def atualizar_departamentos() -> Dict[str, Any]:
        """Sugestão 046: uma leitura da página pública do SIGAA (sem login)."""
        from app.core.departamentos import atualizar_departamentos, info_lista
        try:
            r = atualizar_departamentos()
        except ValueError as e:
            raise ErroApi(502, str(e))
        extra = []
        if r["novos"]:
            extra.append(f"{r['novos']} nova(s)")
        if r["removidos"]:
            extra.append(f"{r['removidos']} que não existem mais")
        return {"ok": True, "mensagem": f"Lista atualizada: {r['quantidade']} unidades" + (f" ({', '.join(extra)})." if extra else "."),
                "info": info_lista()}

    def _disciplina_do_formulario(self, dados: Dict[str, Any], ignorar_indice: Optional[int] = None) -> Disciplina:
        codigo = str(dados.get("codigo", "")).strip().upper()
        turma = str(dados.get("turma", "")).strip()
        try:
            depto = int(str(dados.get("departamento", "")).strip() or 0)
        except ValueError:
            depto = 0
        prioridade = str(dados.get("prioridade", "normal") or "normal").strip().lower()
        nova = Disciplina(codigo=codigo, turma=turma, departamento=depto, professor=str(dados.get("professor", "")).strip(),
                          grupo=str(dados.get("grupo", "") or "").strip()[:40], prioridade=prioridade)
        # Mesma regra da GUI e do terminal (app/core/config.py: analisar_disciplina).
        erros, avisos = analisar_disciplina(nova, self.disciplinas, ignorar_indice)
        if erros:
            raise ErroApi(400, erros[0] if len(erros) == 1 else "Corrija antes de salvar:",
                          problemas=erros if len(erros) > 1 else [])
        if avisos and not _bool(dados.get("confirmado")):
            so_departamento = len(avisos) == 1 and "departamento" in avisos[0]
            raise _precisa_confirmar(
                "\n\n".join(avisos) + "\n\nSalvar mesmo assim?",
                titulo="Código não reconhecido" if so_departamento else "Confira antes de salvar",
            )
        return nova

    def _indice_valido(self, indice: int, chave_esperada: Optional[str]) -> int:
        if not (0 <= indice < len(self.disciplinas)):
            raise ErroApi(404, "Disciplina não encontrada — a lista foi atualizada.")
        # Proteção contra lista desatualizada na página: nunca age sobre uma
        # disciplina diferente da que o usuário estava vendo.
        if chave_esperada is not None and self.disciplinas[indice].chave() != chave_esperada:
            raise ErroApi(409, "A lista de disciplinas mudou desde que a página foi carregada. Atualize e tente de novo.")
        return indice

    def adicionar_disciplina(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:  # validação de duplicata e inclusão no mesmo lock
            nova = self._disciplina_do_formulario(dados)
            self.disciplinas.append(nova)
            salvar_disciplinas(self.disciplinas)
            extra = self._aplicar_na_execucao(adicionar=[nova])
        return {"ok": True, "mensagem": f"{nova.chave()} adicionada.{extra}", **self.listar_disciplinas()}

    def editar_disciplina(self, indice: int, dados: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            i = self._indice_valido(indice, dados.get("chave_original"))
            nova = self._disciplina_do_formulario(dados, ignorar_indice=i)
            nova.ativa = self.disciplinas[i].ativa  # editar nunca reativa/desativa por tabela
            antiga = self.disciplinas[i]
            self.disciplinas[i] = nova
            salvar_disciplinas(self.disciplinas)
            extra = self._aplicar_na_execucao(adicionar=[nova], remover=[antiga.chave()] if antiga.chave() != nova.chave() else [])
        return {"ok": True, "mensagem": f"{nova.chave()} atualizada.{extra}", **self.listar_disciplinas()}

    def previa_lote(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        texto = dados.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            raise ErroApi(400, "Cole pelo menos uma linha no formato CÓDIGO TURMA DEPARTAMENTO.")
        if len(texto) > 50_000:
            raise ErroApi(413, "Texto grande demais para um cadastro em lote.")
        with self.lock:
            itens = interpretar_lote(texto, self.disciplinas)
        linhas = [{
            "linha": it["linha"], "texto": it["texto"], "erros": it["erros"], "avisos": it["avisos"],
            "disciplina": asdict(it["disciplina"]) if it["disciplina"] else None,
        } for it in itens]
        validas = [it for it in itens if it["disciplina"] and not it["erros"]]
        return {"linhas": linhas, "validas": len(validas),
                "com_aviso": sum(1 for it in validas if it["avisos"]),
                "invalidas": sum(1 for it in itens if it["erros"])}

    def aplicar_lote(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        """Reinterpreta o texto no servidor (nunca confia na prévia da página) e
        adiciona só as linhas sem erro. Linhas com aviso exigem confirmação."""
        texto = dados.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            raise ErroApi(400, "Nada para adicionar.")
        if len(texto) > 50_000:
            raise ErroApi(413, "Texto grande demais para um cadastro em lote.")
        with self.lock:
            itens = [it for it in interpretar_lote(texto, self.disciplinas) if it["disciplina"] and not it["erros"]]
            if not itens:
                raise ErroApi(400, "Nenhuma linha válida para adicionar — confira a pré-visualização.")
            com_aviso = [it for it in itens if it["avisos"]]
            if com_aviso and not _bool(dados.get("confirmado")):
                raise _precisa_confirmar(
                    f"{len(com_aviso)} linha(s) têm avisos (ex.: linha {com_aviso[0]['linha']}: {com_aviso[0]['avisos'][0]})"
                    f"\n\nAdicionar as {len(itens)} disciplina(s) válidas mesmo assim?",
                    titulo="Confirmar cadastro em lote",
                )
            self.disciplinas.extend(it["disciplina"] for it in itens)
            salvar_disciplinas(self.disciplinas)
            self._aplicar_na_execucao(adicionar=[it["disciplina"] for it in itens])
        return {"ok": True, "mensagem": f"{len(itens)} disciplina(s) adicionada(s).", **self.listar_disciplinas()}

    def remover_disciplina(self, indice: int, dados: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            i = self._indice_valido(indice, dados.get("chave"))
            d = self.disciplinas[i]
            if not _bool(dados.get("confirmado")):
                raise _precisa_confirmar(f"Remover {d.codigo}-{d.turma} da lista?", titulo="Remover")
            self.disciplinas.pop(i)
            salvar_disciplinas(self.disciplinas)
            extra = self._aplicar_na_execucao(remover=[d.chave()])
        return {"ok": True, "mensagem": f"{d.chave()} removida.{extra}", **self.listar_disciplinas()}

    def alternar_disciplina(self, indice: int, dados: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            i = self._indice_valido(indice, dados.get("chave"))
            self.disciplinas[i].ativa = not self.disciplinas[i].ativa
            salvar_disciplinas(self.disciplinas)
            d = self.disciplinas[i]
            extra = self._aplicar_na_execucao(adicionar=[d] if d.ativa else [], remover=[] if d.ativa else [d.chave()])
        return {"ok": True, "mensagem": f"{d.chave()} {'ativada' if d.ativa else 'desativada'}.{extra}", **self.listar_disciplinas()}

    # ── Execução ──────────────────────────────────────────────────────────

    # ── Fase 6 (070): expiração da sessão por inatividade ─────────────────

    def registrar_atividade(self, _dados: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.ultima_atividade = time.time()
        return {"ok": True}

    def expirou_por_inatividade(self, agora: Optional[float] = None) -> bool:
        """True (uma vez) quando passou o limite sem interação E sem execução ativa.
        Nesse caso apaga as credenciais da memória; o servidor troca a chave de acesso."""
        agora = agora or time.time()
        limite = int((self.settings.get("web") or {}).get("expirar_inatividade_min") or 0)
        if limite <= 0:
            return False
        if self._executor and self._executor.em_execucao():
            self.ultima_atividade = agora  # nunca interrompe um monitoramento; o relógio recomeça no fim
            return False
        if agora - self.ultima_atividade < limite * 60:
            return False
        self.sessao.sigaa.limpar()
        self.sessao.notificacao.limpar()
        self.aviso_aceito = False
        self.ultima_atividade = agora
        auditoria.registrar("sessao_web_expirada", detalhe=f"{limite} min sem uso")
        return True

    def status_execucao(self) -> Dict[str, Any]:
        status = dict(self._status)
        status["em_execucao"] = bool(self._executor and self._executor.em_execucao())
        status["demo"] = bool(getattr(self._motor, "demo", False))
        motor = self._motor
        status["pausado"] = bool(status["em_execucao"] and getattr(motor, "pausado", False))
        status["motivo_pausa"] = getattr(motor, "motivo_pausa", None) if status["pausado"] else None
        return status

    def pausar(self) -> Dict[str, Any]:
        with self.lock:
            if not (self._executor and self._executor.em_execucao() and hasattr(self._motor, "pausar")):
                raise ErroApi(409, "Não há execução em andamento para pausar.")
            self._executor.chamar(self._motor.pausar, "usuario")
        return {"ok": True, "mensagem": "Pausando — as buscas param e as sessões continuam abertas."}

    def retomar(self) -> Dict[str, Any]:
        with self.lock:
            if not (self._executor and self._executor.em_execucao() and hasattr(self._motor, "retomar")):
                raise ErroApi(409, "Não há execução em andamento.")
            if getattr(self._motor, "motivo_pausa", None) == "janela":
                raise ErroApi(409, "A execução está fora da janela de execução e volta sozinha no próximo horário "
                                   "(altere a janela na tela Execução, com o motor parado, se precisar).")
            self._executor.chamar(self._motor.retomar, "usuario")
        return {"ok": True, "mensagem": "Retomando as buscas."}

    def _aplicar_na_execucao(self, adicionar: List[Disciplina] = (), remover: List[str] = ()) -> str:
        """Sugestão 037: mudanças de disciplina valem na hora para a execução em andamento."""
        if not (self._executor and self._executor.em_execucao() and hasattr(self._motor, "adicionar_alvo")):
            return ""
        for chave in remover:
            self._executor.chamar(self._motor.remover_alvo, chave)
        for d in adicionar:
            if d.ativa:
                self._executor.chamar(self._motor.adicionar_alvo, d.como_alvo())
        return " Aplicado também à execução em andamento."

    def iniciar(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if self._executor and self._executor.em_execucao():
                raise ErroApi(409, "O motor já está em execução. Pare antes de iniciar de novo.")

            modo = dados.get("modo", self.settings["modo"])
            if modo not in ("matricula", "monitoramento"):
                raise ErroApi(400, "Modo de execução inválido.")
            demo = _bool(dados.get("demo"))  # Fase 6 (077): SIGAA simulado, sempre em DRY RUN
            dry_run = True if demo else _bool(dados.get("dry_run", self.settings["dry_run"]))
            agendar = str(dados.get("agendar_inicio") or "").strip() or None
            agendar_fim = str(dados.get("agendar_fim") or "").strip() or None

            novos = dict(self.settings)
            novos.update({"modo": modo, "dry_run": dry_run, "agendar_inicio": agendar, "agendar_fim": agendar_fim})
            if "janela" in dados and isinstance(dados["janela"], dict):
                j = dados["janela"]
                try:
                    dias = sorted({int(x) for x in (j.get("dias") or []) if 0 <= int(x) <= 6})
                except (TypeError, ValueError):
                    dias = []
                novos["janela"] = {"ativa": _bool(j.get("ativa")), "inicio": str(j.get("inicio", "")).strip()[:5],
                                   "fim": str(j.get("fim", "")).strip()[:5], "dias": dias}
            if "agendamento_relogio_sigaa" in dados:
                novos["agendamento_relogio_sigaa"] = _bool(dados["agendamento_relogio_sigaa"])
            if "verificacao_previa" in dados:
                novos["verificacao_previa"] = _bool(dados["verificacao_previa"])

            # Mesmas validações de TelaExecucao._validar_pronto (GUI). Na demonstração as
            # credenciais são fictícias e, sem disciplinas, entram disciplinas de exemplo.
            if not demo and not self.sessao.sigaa.preenchida():
                raise ErroApi(400, "Preencha suas credenciais do SIGAA na aba Credenciais antes de iniciar.", ir_para="credenciais")
            problemas_cred = [] if demo else self.sessao.sigaa.problemas()
            if problemas_cred:
                raise ErroApi(400, "Corrija suas credenciais antes de iniciar:", problemas=problemas_cred, ir_para="credenciais")
            problemas = validar_settings(novos) + ([] if demo and not any(d.ativa for d in self.disciplinas)
                                                   else validar_disciplinas(self.disciplinas))
            if problemas:
                raise ErroApi(400, "Antes de iniciar, corrija:", problemas=problemas)

            # Confirmação extra (só na Web): matrícula REAL, com DRY RUN desligado.
            if modo == "matricula" and not dry_run and not _bool(dados.get("confirmado")):
                raise _precisa_confirmar(
                    "O DRY RUN está DESLIGADO: quando encontrar vaga, o programa vai CONFIRMAR A MATRÍCULA DE "
                    "VERDADE no SIGAA.\n\nTem certeza de que quer iniciar a matrícula real?",
                    titulo="Confirmar matrícula real",
                )

            if not demo:  # a demonstração não mexe no DRY RUN salvo
                self.settings = novos
                salvar_settings(self.settings)

            motor = construir_motor(novos if demo else self.settings, self.sessao, self.disciplinas,
                                    on_evento_extra=self._ao_evento_motor, demo=demo)
            self._motor = motor
            self._executor = ExecutorMotor(motor, ao_finalizar=self._ao_finalizar)
            self._executor.iniciar()
            modo_txt = "Matrícula automática" if modo == "matricula" else "Somente monitoramento"
            if modo == "matricula":
                modo_txt += " (DRY RUN — teste)" if dry_run else " (REAL)"
            if demo:
                modo_txt = "DEMONSTRAÇÃO (SIGAA simulado) · " + modo_txt
            self._status = {"estado": "executando", "mensagem": f"Em execução — {modo_txt}",
                            "modo": modo, "dry_run": dry_run, "inicio": time.time(), "execucao_id": motor.execucao_id}
        return {"ok": True, "execucao": self.status_execucao(),
                "abrir_dashboard": bool(self.settings.get("abrir_dashboard_ao_iniciar"))}

    def _ao_finalizar(self, erro: Optional[Exception]) -> None:
        with self.lock:
            if erro:
                self._status = {**self._status, "estado": "erro", "mensagem": f"Encerrado com erro: {erro}"}
            else:
                self._status = {**self._status, "estado": "parado", "mensagem": "Parado."}
        resumo = getattr(self._motor, "resumo", None)
        if erro:
            self._registrar_evento("execucao_encerrada", f"A execução terminou com erro: {erro}", "erro")
        elif resumo:
            t = resumo["totais"]
            self._registrar_evento("execucao_encerrada", (
                f"Execução encerrada — {MOTIVOS_FIM.get(resumo.get('motivo_fim'), 'fim')}. "
                f"{t['requisicoes']} busca(s), {t['vagas_vistas']} vaga(s) vista(s), {t['tentativas']} tentativa(s), "
                f"{t['erros']} erro(s). O resumo completo está no Dashboard."), "info")
        else:
            self._registrar_evento("execucao_encerrada", "A execução terminou. Veja os detalhes no Dashboard e na Central de Logs.", "info")

    def parar(self) -> Dict[str, Any]:
        with self.lock:
            if self._executor and self._executor.em_execucao():
                self._executor.parar()
                self._status = {**self._status, "estado": "parando", "mensagem": "Parando... (aguardando workers atuais encerrarem)"}
        return {"ok": True, "execucao": self.status_execucao()}

    # ── Dashboard ─────────────────────────────────────────────────────────

    def painel_motor(self, janela_seg: Optional[int] = None, com_series: bool = False) -> Optional[Dict[str, Any]]:
        """Dados da execução vindos direto do motor (Fase 2) — estado de cada
        disciplina e worker, saúde, erros agrupados, séries para os gráficos."""
        motor = self._motor
        if motor is None or not hasattr(motor, "snapshot"):
            return None
        snap = motor.snapshot()
        tel = snap["telemetria"]
        # Execução encerrada: o painel fica congelado no instante do fim — nada de
        # "há X s", fase ou memória mudando com o relógio depois da parada.
        agora = snap["fim"] or time.time()
        alvos = [{**a, "ultima_leitura_txt": tempo_relativo(a["ultima_leitura"], agora),
                  "desde_txt": tempo_relativo(a["desde"], agora)} for a in snap["alvos"]]
        painel = {
            "execucao_id": snap["execucao_id"], "modo": snap["modo"], "dry_run": snap["dry_run"],
            "fase": descrever_fase(snap, agora), "inicio": snap["inicio"], "fim": snap["fim"],
            "alvos": alvos, "workers": snap["workers"], "contadores": snap["contadores"],
            "saude": avaliar_saude(snap, None if snap["fim"] else medir_memoria_mb()), "erros_agrupados": agrupar_erros(snap),
            "histograma": tel["histograma"], "latencia": tel["latencia"], "rps_atual": tel["rps_atual"],
            "requisicoes": tel["requisicoes"], "vagas_vistas": tel["vagas_vistas"], "ultima_vaga": tel["ultima_vaga"],
            "sparks": sparklines(tel["pontos"]), "resumo": getattr(motor, "resumo", None), "agora": agora,
            "tentativas": snap.get("tentativas", []), "alertas": snap.get("alertas", {"ativos": [], "historico": []}),
            "reinicios_workers": snap.get("reinicios_workers", 0),
        }
        if com_series:
            painel["series"] = series_grafico(tel["pontos"], janela_seg)
            limite = (agora - janela_seg) if janela_seg else 0
            # Série em degraus: o último valor ANTES da janela entra para o degrau começar certo.
            vagas = {}
            for chave, mudancas in tel["vagas_series"].items():
                dentro = [m for m in mudancas if m[0] >= limite]
                antes = [m for m in mudancas if m[0] < limite]
                vagas[chave] = ([[limite, antes[-1][1]]] if antes and janela_seg else []) + [list(m) for m in dentro]
            painel["vagas_series"] = vagas
        return painel

    def dashboard(self, janela_seg: Optional[int] = None, com_series: bool = False) -> Dict[str, Any]:
        ativa = bool(self._executor and self._executor.em_execucao())
        with self._lock_metricas:
            # A primeira leitura (o que já estava no arquivo) é passado: entra com o
            # horário original, não como tráfego "agora".
            for linha in self._tailer_dashboard.read_new_lines():
                self._coletor.processar_linha(linha, ao_vivo=self._backlog_dashboard_lido)
            self._backlog_dashboard_lido = True
            m = self._coletor.snapshot(execucao_ativa=ativa)

        agora = time.time()
        workers = []
        for w_id, w in m["workers"].items():
            workers.append({
                "id": w_id, "erros": w["erros_count"], "buscas": w["buscas_feitas"], "ultima_acao": w["ultima_acao"],
                "latencia": w["latencia"] or None, "cor_latencia": w.get("cor_lat"),
                "ocioso_seg": round(agora - w["timestamp"], 1) if ativa else None,
            })
        return {
            "saude": m["saude"], "rps_atual": m["rps_atual"], "bps_atual": m["bps_atual"],
            "avg_rps": m["avg_rps"], "avg_bps": m["avg_bps"],
            "latencia_recente_ms": m["latencia_recente_ms"], "latencia_media_ms": m["latencia_media_ms"],
            "latencia_min_ms": m["latencia_min_ms"], "latencia_max_ms": m["latencia_max_ms"],
            "total_reqs": m["total_reqs"], "total_reqs_falha_rede": m["total_reqs_falha_rede"],
            "total_buscas": m["total_buscas"], "vagas_encontradas": m["vagas_encontradas"], "erros_totais": m["erros_totais"],
            "uptime": formatar_uptime(m["uptime_bot_seg"]), "tem_dados": m["tem_dados"],
            "workers": workers, "registro_vagas": m["registro_vagas"], "log_erros": m["log_erros"],
            "historico_vagas": m["historico_vagas"], "workers_com_alerta": m["workers_com_alerta"],
            "execucao": self.status_execucao(),
            "painel": self.painel_motor(janela_seg, com_series),
            "execucao_ativa": ativa,
            # Dados de uma execução anterior carregados ao abrir (nunca a execução atual).
            "recuperado": bool(self.carregar_ultima and self._motor is None and m["tem_dados"]),
        }

    # ── Histórico de execuções (Fase 3: 060, 061, 022, 024, 025, 028, 049) ──

    def historico(self, dias: Optional[int] = None, disciplina: str = "") -> Dict[str, Any]:
        if not self._historico_importado:
            # Resumos gravados antes de o banco existir (data/relatorios/) entram uma vez.
            try:
                historico_mod.importar_relatorios_antigos()
            except Exception:
                pass
            self._historico_importado = True
        disciplina = disciplina.strip() or None
        execucoes = historico_mod.listar_execucoes(dias, disciplina)
        por_dia = historico_mod.resumo_por_dia(dias, disciplina)
        totais = {
            "execucoes": len(execucoes),
            "horas": round(sum((e["duracao_seg"] or 0) for e in execucoes) / 3600, 1),
            "buscas": sum(e["requisicoes"] or 0 for e in execucoes),
            "vagas_vistas": sum(e["vagas_vistas"] or 0 for e in execucoes),
            "matriculadas": sum(e["matriculadas"] or 0 for e in execucoes),
            "simuladas": sum(e["simuladas"] or 0 for e in execucoes),
            "erros": sum(e["erros"] or 0 for e in execucoes),
        }
        return {"execucoes": execucoes, "por_dia": por_dia, "totais": totais,
                "mapa": historico_mod.mapa_aberturas_de_vaga(dias, disciplina),
                "disciplinas": historico_mod.disciplinas_no_historico(),
                "ativo": self.settings.get("historico", {}).get("ativo", True),
                "dias_retencao": self.settings.get("historico", {}).get("dias_retencao", 180)}

    @staticmethod
    def detalhe_historico(execucao_id: str) -> Dict[str, Any]:
        detalhe = historico_mod.obter_execucao(execucao_id)
        if not detalhe:
            raise ErroApi(404, "Execução não encontrada no histórico.")
        return detalhe

    @staticmethod
    def comparar_historico(ids_texto: str) -> Dict[str, Any]:
        ids = [i for i in (ids_texto or "").split(",") if i][:2]
        if len(ids) != 2:
            raise ErroApi(400, "Escolha exatamente duas execuções para comparar.")
        return {"execucoes": historico_mod.comparar(ids)}

    @staticmethod
    def exportar_historico(tipo: str, formato: str, dias: Optional[int], disciplina: str) -> tuple:
        if formato not in ("csv", "json") or tipo not in ("execucoes", "vagas"):
            raise ErroApi(400, "Exportação inválida.")
        funcao = historico_mod.exportar_execucoes if tipo == "execucoes" else historico_mod.exportar_leituras_vagas
        conteudo = funcao(formato, dias, disciplina.strip() or None)
        nome = f"sigaa_sniper_{'historico' if tipo == 'execucoes' else 'vagas'}.{formato}"
        tipo_mime = "text/csv; charset=utf-8" if formato == "csv" else "application/json; charset=utf-8"
        return conteudo.encode("utf-8"), tipo_mime, nome

    def apagar_historico(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        if not _bool(dados.get("confirmado")):
            raise _precisa_confirmar(
                "Apagar TODO o histórico de execuções (data/historico.db)? Os resumos em data/relatorios/ não são afetados. "
                "Isso não pode ser desfeito.", titulo="Apagar histórico")
        historico_mod.apagar_tudo()
        self._historico_importado = True  # não reimporta os relatórios que a pessoa acabou de mandar apagar
        return {"ok": True, "mensagem": "Histórico apagado."}

    # ── Central de Logs ──────────────────────────────────────────────────

    def logs(self, desde: int = 0) -> Dict[str, Any]:
        with self._lock_logs:
            if self._tailer_logs:
                for linha in self._tailer_logs.read_new_lines():
                    try:
                        registro = json.loads(linha)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if not isinstance(registro, dict):
                        continue
                    self._seq_logs += 1
                    self._logs.append((self._seq_logs, registro))
            itens = [(s, r) for s, r in self._logs if s > desde]
            ultimo = self._seq_logs

        saida = []
        for seq, registro in itens:
            ev = traduzir(registro)
            saida.append({
                "seq": seq, "hora": str(registro.get("timestamp", ""))[-8:], "timestamp": registro.get("timestamp", ""),
                "worker": ev.worker, "categoria": ev.categoria, "nivel": ev.nivel,
                "titulo": ev.titulo, "corpo": ev.corpo, "bruto": registro,
            })
        return {"registros": saida, "ultimo_seq": ultimo, "categorias": CATEGORIAS}

    @staticmethod
    def caminho_log() -> str:
        return caminho_projeto("data", "sigaa_sniper_audit.json")

    def abrir_arquivo_log(self) -> Dict[str, Any]:
        caminho_log = self.caminho_log()
        if not os.path.exists(caminho_log):
            raise ErroApi(404, "O arquivo de log ainda não existe (nenhuma execução foi feita).")
        import subprocess
        import sys
        try:
            if sys.platform == "win32":
                os.startfile(caminho_log)  # noqa: S606 — caminho fixo do próprio programa
            elif sys.platform == "darwin":
                subprocess.run(["open", caminho_log], check=False)
            else:
                subprocess.run(["xdg-open", caminho_log], check=False)
        except Exception as e:
            raise ErroApi(500, f"Não foi possível abrir o arquivo automaticamente ({e}). Ele está em: {caminho_log}")
        return {"ok": True, "mensagem": f"Arquivo aberto: {caminho_log}"}

    # ── Notificações ──────────────────────────────────────────────────────

    def notificacoes(self) -> Dict[str, Any]:
        cfg = self.settings["notificacoes"]
        n = self.sessao.notificacao
        return {
            "telegram_ativo": cfg["telegram_ativo"], "ntfy_ativo": cfg["ntfy_ativo"], "alarme_ativo": cfg["alarme_ativo"],
            "alarme_repeticoes": cfg["alarme"]["repeticoes"], "alarme_duracao": cfg["alarme"]["duracao_seg"],
            "eventos": dict(cfg["eventos"]), "rotulos_eventos": ROTULOS_EVENTOS_NOTIFICACAO,
            "windows_ativo": cfg.get("windows_ativo", False), "windows_disponivel": windows_notif.disponivel(),
            "webhook_ativo": cfg.get("webhook_ativo", False), "webhook_formato": cfg.get("webhook_formato", "discord"),
            "webhook_url": n.webhook_url,
            "email_ativo": cfg.get("email_ativo", False), "email": dict(cfg.get("email") or {}), "tem_email_senha": bool(n.email_senha),
            "cofre_texto": descricao_armazenamento(),
            "resumo_intervalo_horas": cfg.get("resumo_intervalo_horas", 6),
            "telegram_token": n.telegram_token, "telegram_chat_id": n.telegram_chat_id,
            "ntfy_topic": n.ntfy_topic, "ntfy_servidor": n.ntfy_servidor,
            "lembrar": existe_segredos_notificacao_salvos(),
        }

    def salvar_notificacoes(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        repeticoes = _int(dados.get("alarme_repeticoes", 3), "Repetições do alarme", 1, 20)
        duracao = _int(dados.get("alarme_duracao", 20), "Duração do alarme", 1, 120)
        try:
            horas_resumo = float(str(dados.get("resumo_intervalo_horas", self.settings["notificacoes"].get("resumo_intervalo_horas", 6))).replace(",", "."))
        except ValueError:
            horas_resumo = -1
        if not 0.5 <= horas_resumo <= 48:
            raise ErroApi(400, "Intervalo do resumo periódico deve estar entre 0,5 e 48 horas.")
        # Desde a 6.1.0: webhook e e-mail são conferidos ANTES de qualquer alteração.
        from app.core.validadores import problema_url_webhook, problemas_email_cfg
        url = str(dados.get("webhook_url", "")).strip()
        if (url or _bool(dados.get("webhook_ativo"))) and problema_url_webhook(url):
            raise ErroApi(400, problema_url_webhook(url))
        senha_email = str(dados.get("email_senha", ""))
        senha_final = senha_email if (senha_email or not _bool(dados.get("manter_email_senha"))) else self.sessao.notificacao.email_senha
        if _bool(dados.get("email_ativo")):
            email_candidato = dict(dados.get("email") if isinstance(dados.get("email"), dict) else {})
            try:
                email_candidato["porta"] = int(str(email_candidato.get("porta", 587)).strip() or 587)
            except ValueError:
                email_candidato["porta"] = -1
            problemas = problemas_email_cfg(email_candidato, senha_final)
            if problemas:
                raise ErroApi(400, "Revise a configuração de e-mail:", problemas=problemas)
        with self.lock:
            cfg = self.settings["notificacoes"]
            cfg["telegram_ativo"] = _bool(dados.get("telegram_ativo"))
            cfg["ntfy_ativo"] = _bool(dados.get("ntfy_ativo"))
            cfg["alarme_ativo"] = _bool(dados.get("alarme_ativo"))
            cfg["alarme"]["repeticoes"] = repeticoes
            cfg["alarme"]["duracao_seg"] = duracao
            cfg["resumo_intervalo_horas"] = horas_resumo
            cfg["windows_ativo"] = _bool(dados.get("windows_ativo"))
            cfg["webhook_ativo"] = _bool(dados.get("webhook_ativo"))
            formato = str(dados.get("webhook_formato", "discord"))
            cfg["webhook_formato"] = formato if formato in ("discord", "slack", "json") else "discord"
            cfg["email_ativo"] = _bool(dados.get("email_ativo"))
            email = dados.get("email") if isinstance(dados.get("email"), dict) else {}
            cfg["email"] = {"servidor": str(email.get("servidor", "")).strip()[:120],
                            "porta": _int(email.get("porta", 587) or 587, "Porta do e-mail", 1, 65535),
                            "usuario": str(email.get("usuario", "")).strip()[:120],
                            "destinatario": str(email.get("destinatario", "")).strip()[:200],
                            "remetente": str(email.get("remetente", "") or "").strip()[:200],
                            "seguranca": "ssl" if email.get("seguranca") == "ssl" else "starttls"}
            eventos = dados.get("eventos") or {}
            for chave in cfg["eventos"]:
                if chave in eventos:
                    cfg["eventos"][chave] = _bool(eventos[chave])
            salvar_settings(self.settings)

            n = self.sessao.notificacao
            n.telegram_token = str(dados.get("telegram_token", "")).strip()
            n.telegram_chat_id = str(dados.get("telegram_chat_id", "")).strip()
            n.ntfy_topic = str(dados.get("ntfy_topic", "")).strip()
            n.ntfy_servidor = str(dados.get("ntfy_servidor", "")).strip() or "https://ntfy.sh"
            n.webhook_url = url
            n.email_senha = senha_final

            if _bool(dados.get("lembrar")):
                salvar_segredos_notificacao(n.telegram_token, n.telegram_chat_id, n.ntfy_topic, n.ntfy_servidor,
                                            n.webhook_url, n.email_senha)
                msg = f"Configuração salva (segredos de notificação {descricao_armazenamento().split(' — ')[0]})."
            else:
                msg = "Configuração salva (segredos de notificação só em memória)."
        return {"ok": True, "mensagem": msg, "notificacoes": self.notificacoes()}

    def alterar_persistencia_notificacoes(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        """Desmarcar "Salvar neste computador" apaga o arquivo na hora — igual à GUI."""
        if not _bool(dados.get("lembrar")):
            apagar_segredos_notificacao()
            return {"ok": True, "mensagem": "Segredos de notificação salvos anteriormente foram apagados do disco."}
        return {"ok": True, "mensagem": "Clique em \"Salvar configuração de notificações\" para gravar os segredos em disco."}

    @staticmethod
    def testar_notificacoes(dados: Dict[str, Any]) -> Dict[str, Any]:
        from app.notifications.alarm import testar_alarme
        from app.notifications.ntfy import testar_ntfy
        from app.notifications.telegram import testar_telegram
        from app.notifications.email import configurado as email_ok, testar_email
        from app.notifications.webhook import testar_webhook

        canal = dados.get("canal")
        webhook_url = str(dados.get("webhook_url", "")).strip()
        formato = str(dados.get("webhook_formato", "discord"))
        email_cfg = dados.get("email") if isinstance(dados.get("email"), dict) else {}
        email_cfg = {**email_cfg, "porta": _int(email_cfg.get("porta", 587) or 587, "Porta do e-mail", 1, 65535)}
        email_senha = str(dados.get("email_senha", "")) or obter_sessao().notificacao.email_senha
        token, chat = str(dados.get("telegram_token", "")).strip(), str(dados.get("telegram_chat_id", "")).strip()
        topic = str(dados.get("ntfy_topic", "")).strip()
        servidor = str(dados.get("ntfy_servidor", "")).strip() or "https://ntfy.sh"
        repeticoes = _int(dados.get("alarme_repeticoes", 2), "Repetições do alarme", 1, 20)
        duracao = min(3, _int(dados.get("alarme_duracao", 3), "Duração do alarme", 1, 120))

        tarefas = []
        if canal in ("telegram", "todos") and (canal == "telegram" or _bool(dados.get("telegram_ativo"))):
            if not token or not chat:
                if canal == "telegram":
                    raise ErroApi(400, "Preencha o token e o chat ID antes de testar.")
            else:
                tarefas.append(("Telegram", lambda: testar_telegram(token, chat)))
        if canal in ("ntfy", "todos") and (canal == "ntfy" or _bool(dados.get("ntfy_ativo"))):
            if not topic:
                if canal == "ntfy":
                    raise ErroApi(400, "Preencha o tópico antes de testar.")
            else:
                tarefas.append(("ntfy", lambda: testar_ntfy(topic, servidor)))
        if canal in ("alarme", "todos") and (canal == "alarme" or _bool(dados.get("alarme_ativo"))):
            tarefas.append(("Alarme", lambda: testar_alarme(repeticoes, duracao)))
        if canal in ("windows", "todos") and (canal == "windows" or _bool(dados.get("windows_ativo"))):
            if not windows_notif.disponivel():
                if canal == "windows":
                    raise ErroApi(400, "A notificação do Windows só funciona no Windows.")
            else:
                tarefas.append(("Windows", windows_notif.testar_windows))
        if canal in ("webhook", "todos") and (canal == "webhook" or _bool(dados.get("webhook_ativo"))):
            if not webhook_url.startswith("https://"):
                if canal == "webhook":
                    raise ErroApi(400, "Preencha a URL do webhook (https://…) antes de testar.")
            else:
                tarefas.append(("Webhook", lambda: testar_webhook(webhook_url, formato)))
        if canal in ("email", "todos") and (canal == "email" or _bool(dados.get("email_ativo"))):
            from app.core.validadores import problemas_email_cfg
            problemas_email = problemas_email_cfg(email_cfg, email_senha)
            if problemas_email:
                if canal == "email":
                    raise ErroApi(400, "Revise a configuração de e-mail antes de testar:", problemas=problemas_email)
            else:
                tarefas.append(("E-mail", lambda: testar_email(email_cfg, email_senha)))

        if not tarefas:
            raise ErroApi(400, "Nenhum canal de notificação está ativado e preenchido.")

        async def rodar_tudo():
            linhas, todos_ok = [], True
            for nome, fabrica in tarefas:
                try:
                    await fabrica()
                    linhas.append({"canal": nome, "ok": True, "mensagem": "OK"})
                except Exception as e:
                    todos_ok = False
                    linhas.append({"canal": nome, "ok": False, "mensagem": f"falhou ({e})"})
            return linhas, todos_ok

        linhas, todos_ok = asyncio.run(rodar_tudo())
        return {"ok": todos_ok, "resultados": linhas}

    # ── Configurações avançadas ──────────────────────────────────────────

    def avancado(self) -> Dict[str, Any]:
        s = self.settings
        return {
            "num_workers": s["num_workers"], "intervalo_busca": s["intervalo_busca"], "timeout_req": s["timeout_req"],
            "abrir_dashboard_ao_iniciar": s["abrir_dashboard_ao_iniciar"],
            "carregar_ultima_execucao": bool(s.get("carregar_ultima_execucao")),
            "nivel_log_console": s.get("debug", {}).get("nivel_log_console", "INFO"),
            "logs": dict(s["logs"]), "json_audit": dict(s["json_audit"]), "urls": dict(s.get("urls", {})),
            "historico": {**PADROES_SETTINGS["historico"], **s.get("historico", {})},
            "protecao": {**PADROES_SETTINGS["protecao"], **s.get("protecao", {})},
            "alertas": {**PADROES_SETTINGS["alertas"], **s.get("alertas", {})},
            "web": {**PADROES_SETTINGS["web"], **s.get("web", {})}, "espaco": resumo_espaco_em_disco(),
            "secoes_restauraveis": SECOES_RESTAURAVEIS, "esquema": esquema_para_web(),
            "presets_carga": PRESETS_CARGA, "carga": self._carga_estimada(),
            # Parâmetros da estimativa, para a página recalcular ao vivo com a MESMA conta do servidor.
            "carga_parametros": {"latencia_seg": LATENCIA_REFERENCIA_SEG, "limite_baixa": LIMITE_CARGA_BAIXA,
                                 "limite_moderada": LIMITE_CARGA_MODERADA,
                                 "teto": self.settings.get("protecao", {}).get("limite_req_por_seg", 0),
                                 "qtd_alvos": max(1, sum(1 for d in self.disciplinas if d.ativa))},
        }

    def salvar_avancado(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            novos = dict(self.settings)
            novos["num_workers"] = _int(dados.get("num_workers"), "Quantidade de workers", -10**9, 10**9)
            novos["intervalo_busca"] = round(_float(dados.get("intervalo_busca"), "Intervalo entre buscas"), 2)
            novos["timeout_req"] = _int(dados.get("timeout_req"), "Timeout de requisição", -10**9, 10**9)
            novos["abrir_dashboard_ao_iniciar"] = _bool(dados.get("abrir_dashboard_ao_iniciar"))
            novos["carregar_ultima_execucao"] = _bool(dados.get("carregar_ultima_execucao"))
            nivel = dados.get("nivel_log_console", "INFO")
            novos["debug"] = {"nivel_log_console": nivel if nivel in ("INFO", "DEBUG") else "INFO"}
            logs, audit = dados.get("logs") or {}, dados.get("json_audit") or {}
            novos["logs"] = {"tamanho_max_mb": _int(logs.get("tamanho_max_mb"), "Tamanho máximo dos logs", 0, 10**6),
                             "arquivos_mantidos": _int(logs.get("arquivos_mantidos"), "Arquivos de log mantidos", 0, 50)}
            novos["json_audit"] = {"tamanho_max_mb": _int(audit.get("tamanho_max_mb"), "Tamanho máximo do JSON", 1, 500),
                                   "arquivos_mantidos": _int(audit.get("arquivos_mantidos"), "Arquivos JSON mantidos", 0, 50)}
            prot = dados.get("protecao") or {}
            novos["protecao"] = {
                "limite_req_por_seg": round(_float(prot.get("limite_req_por_seg", 20), "Limite de buscas por segundo"), 1),
                "logins_simultaneos": _int(prot.get("logins_simultaneos", 3), "Logins simultâneos", -10**6, 10**6),
                "disjuntor": _bool(prot.get("disjuntor", True)),
            }
            alertas = dados.get("alertas") or {}
            atuais = {**PADROES_SETTINGS["alertas"], **self.settings.get("alertas", {})}
            novos["alertas"] = {
                "ativo": _bool(alertas.get("ativo", atuais["ativo"])),
                "taxa_erro_pct": _int(alertas.get("taxa_erro_pct", atuais["taxa_erro_pct"]), "Limite da taxa de erro", -10**6, 10**6),
                "taxa_erro_min": _int(alertas.get("taxa_erro_min", atuais["taxa_erro_min"]), "Minutos da taxa de erro", -10**6, 10**6),
                "sem_resposta_min": _int(alertas.get("sem_resposta_min", atuais["sem_resposta_min"]), "Minutos sem resposta", -10**6, 10**6),
                "sem_busca_min": _int(alertas.get("sem_busca_min", atuais["sem_busca_min"]), "Minutos sem busca", -10**6, 10**6),
            }
            hist = dados.get("historico") or {}
            novos["historico"] = {"ativo": _bool(hist.get("ativo", True)),
                                  "dias_retencao": _int(hist.get("dias_retencao", 180), "Retenção do histórico (dias)", -10**6, 10**6)}
            urls = dados.get("urls") or {}
            novos["urls"] = {chave: str(urls.get(chave, "")).strip() for chave in self.settings.get("urls", {})}
            web = dados.get("web") or {}
            novos["web"] = {
                "host": str(web.get("host", "127.0.0.1")).strip() or "127.0.0.1",
                "porta": _int(web.get("porta", 8765), "Porta da Interface Web", 0, 10**6),
                "abrir_navegador": _bool(web.get("abrir_navegador", True)),
                "modo_aplicativo": _bool(web.get("modo_aplicativo", True)),
                "expirar_inatividade_min": _int(web.get("expirar_inatividade_min", 0) or 0, "Expiração por inatividade", -10**6, 10**6),
            }

            problemas = validar_settings(novos)
            if problemas:
                raise ErroApi(400, "Corrija antes de salvar:", problemas=problemas)

            if novos["urls"] != self.settings.get("urls", {}) and not _bool(dados.get("confirmado")):
                raise _precisa_confirmar(
                    "Você alterou as URLs do SIGAA. Um valor incorreto pode impedir o programa de funcionar "
                    "completamente.\n\nTem certeza que quer salvar assim mesmo?",
                    titulo="Confirmar alteração de URLs",
                )

            web_mudou = novos["web"] != self.settings.get("web")
            self.settings = novos
            salvar_settings(self.settings)
        msg = "Configurações avançadas salvas."
        if web_mudou:
            msg += " A nova porta/endereço da Interface Web vale a partir da próxima vez que ela for aberta."
        return {"ok": True, "mensagem": msg, "avancado": self.avancado()}

    def restaurar(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        todas = _bool(dados.get("todas"))
        secoes = [s for s in (dados.get("secoes") or []) if s in SECOES_RESTAURAVEIS]
        if not todas and not secoes:
            raise ErroApi(400, "Marque pelo menos uma seção para restaurar.")
        if not _bool(dados.get("confirmado")):
            texto = ("Restaurar TODAS as configurações avançadas para o padrão? (credenciais nunca são afetadas)"
                     if todas else f"Restaurar os valores padrão de: {', '.join(secoes)}?")
            raise _precisa_confirmar(texto, titulo="Confirmar")
        with self.lock:
            self.settings = restaurar_padroes(self.settings, None if todas else secoes)
            salvar_settings(self.settings)
        return {"ok": True, "mensagem": "Configurações restauradas — os campos já mostram os novos valores.", "avancado": self.avancado()}

    def limpar_dumps(self) -> Dict[str, Any]:
        removidos = limpar_debug_dumps(manter=self.settings["logs"]["arquivos_mantidos"])
        return {"ok": True, "mensagem": f"{removidos} arquivo(s) de debug antigo removido(s).", "espaco": resumo_espaco_em_disco()}

    @staticmethod
    def exportar_configuracao() -> bytes:
        """Mesmo conteúdo de exportar_configuracao() (nunca inclui credenciais)."""
        pasta = tempfile.mkdtemp(prefix="sniper_export_")
        caminho = os.path.join(pasta, "sigaa_sniper_config.json")
        try:
            exportar_configuracao(caminho)
            with open(caminho, "rb") as f:
                return f.read()
        finally:
            try:
                os.remove(caminho)
            except OSError:
                pass
            try:
                os.rmdir(pasta)
            except OSError:
                pass

    @staticmethod
    def _com_arquivo_temporario(conteudo: str, funcao):
        pasta = tempfile.mkdtemp(prefix="sniper_import_")
        caminho = os.path.join(pasta, "importacao.json")
        try:
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(conteudo)
            return funcao(caminho)
        finally:
            try:
                os.remove(caminho)
            except OSError:
                pass
            try:
                os.rmdir(pasta)
            except OSError:
                pass

    def previa_importacao(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        conteudo = dados.get("conteudo")
        if not isinstance(conteudo, str) or not conteudo.strip():
            raise ErroApi(400, "Escolha um arquivo JSON exportado pelo programa.")
        try:
            resumo = self._com_arquivo_temporario(conteudo, pre_visualizar_importacao)
        except Exception as e:
            raise ErroApi(400, f"Arquivo rejeitado: {e}")
        if resumo["problemas_settings"]:
            raise ErroApi(400, "O arquivo tem problemas e não será importado:", problemas=resumo["problemas_settings"])
        return {"ok": True, "qtd_disciplinas": resumo["qtd_disciplinas"],
                "disciplinas_ignoradas": len(resumo["problemas_disciplinas"]), "tem_settings": resumo["tem_settings"]}

    def aplicar_importacao(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        self.previa_importacao(dados)  # revalida antes de aplicar
        with self.lock:
            try:
                self._com_arquivo_temporario(dados["conteudo"], importar_configuracao)
            except Exception as e:
                raise ErroApi(400, f"Erro ao importar: {e}")
            self.settings = carregar_settings()
            self.disciplinas = carregar_disciplinas()
        return {"ok": True, "mensagem": "Configurações importadas — as telas já mostram os novos valores."}

    # ── Diagnóstico ───────────────────────────────────────────────────────

    @staticmethod
    def diagnostico_completo() -> Dict[str, Any]:
        from app.core.seguranca_config import checar_configuracoes_inseguras
        resultados = [*checar_saude_sistema(), checar_modo_execucao(), *checar_configuracoes_inseguras()]
        try:
            resultados.append(asyncio.run(checar_conectividade_sigaa()))
        except Exception as e:
            resultados.append(ResultadoChecagem("Conectividade com o SIGAA", False, str(e)))
        return {"relatorio": gerar_relatorio_texto(resultados), "itens": [_resultado_json(r) for r in resultados]}

    @staticmethod
    def diagnostico_camadas() -> Dict[str, Any]:
        resultados = asyncio.run(checar_conectividade_em_camadas())
        return {"relatorio": gerar_relatorio_texto(resultados), "itens": [_resultado_json(r) for r in resultados]}

    # ── Fase 6: perfis (042), versões anteriores (045), trilha de auditoria (062/063) ──

    @staticmethod
    def perfis() -> Dict[str, Any]:
        return {"perfis": listar_perfis()}

    def salvar_perfil(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        nome = str(dados.get("nome", "")).strip()
        try:
            from app.core.config import _arquivo_perfil
            arquivo = _arquivo_perfil(nome)
        except ValueError as e:
            raise ErroApi(400, str(e))
        if any(p["arquivo"] == arquivo for p in listar_perfis()) and not _bool(dados.get("confirmado")):
            raise _precisa_confirmar(f"Já existe um perfil chamado \"{nome}\". Substituir pelo que está configurado agora?",
                                     titulo="Substituir perfil")
        with self.lock:
            salvar_perfil(nome, self.settings, self.disciplinas)
        return {"ok": True, "mensagem": f"Perfil \"{nome}\" salvo com a configuração e as disciplinas atuais.", **self.perfis()}

    def aplicar_perfil(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        if self._executor and self._executor.em_execucao():
            raise ErroApi(409, "Pare a execução antes de trocar de perfil.")
        arquivo = str(dados.get("arquivo", ""))
        perfil = next((p for p in listar_perfis() if p["arquivo"] == arquivo), None)
        if perfil is None:
            raise ErroApi(404, "Perfil não encontrado.")
        if not _bool(dados.get("confirmado")):
            raise _precisa_confirmar(
                f"Aplicar o perfil \"{perfil['nome']}\"?\n\n{perfil['resumo']}.\n\nSubstitui o modo, o desempenho, a proteção, "
                "a janela, os alertas, as notificações e as disciplinas. O DRY RUN continua como está agora "
                "(um perfil nunca liga a matrícula real sozinho). Dá para desfazer em \"Versões anteriores\".",
                titulo="Aplicar perfil")
        with self.lock:
            try:
                novos, disciplinas = aplicar_perfil(arquivo, self.settings)
            except ValueError as e:
                raise ErroApi(400, str(e))
            self.settings, self.disciplinas = novos, disciplinas
            salvar_settings(self.settings)
            salvar_disciplinas(self.disciplinas)
        return {"ok": True, "mensagem": f"Perfil \"{perfil['nome']}\" aplicado."}

    def apagar_perfil(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        arquivo = str(dados.get("arquivo", ""))
        perfil = next((p for p in listar_perfis() if p["arquivo"] == arquivo), None)
        if perfil is None:
            raise ErroApi(404, "Perfil não encontrado.")
        if not _bool(dados.get("confirmado")):
            raise _precisa_confirmar(f"Apagar o perfil \"{perfil['nome']}\"? A configuração atual não muda.", titulo="Apagar perfil")
        apagar_perfil(arquivo)
        return {"ok": True, "mensagem": f"Perfil \"{perfil['nome']}\" apagado.", **self.perfis()}

    @staticmethod
    def versoes_config() -> Dict[str, Any]:
        return {"versoes": listar_versoes_config()}

    def restaurar_versao(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        versao = str(dados.get("id", ""))
        item = next((v for v in listar_versoes_config() if v["id"] == versao), None)
        if item is None:
            raise ErroApi(404, "Versão não encontrada.")
        if item["tipo"] == "disciplinas" and self._executor and self._executor.em_execucao():
            raise ErroApi(409, "Pare a execução antes de restaurar as disciplinas.")
        if not _bool(dados.get("confirmado")):
            raise _precisa_confirmar(f"Voltar {item['tipo_rotulo'].lower()} para a versão de {item['quando']}?\n\n{item['resumo']}\n\n"
                                     "A versão atual também fica guardada, então dá para desfazer.", titulo="Restaurar versão")
        with self.lock:
            try:
                r = restaurar_versao_config(versao)
            except ValueError as e:
                raise ErroApi(400, str(e))
            if r["tipo"] == "settings":
                self.settings = r["settings"]
            else:
                self.disciplinas = r["disciplinas"]
        return {"ok": True, "mensagem": f"{item['tipo_rotulo']} restauradas para {item['quando']}.", **self.versoes_config()}

    @staticmethod
    def auditoria() -> Dict[str, Any]:
        return {"acoes": auditoria.listar(200)}

    # ── Fase 6 (091): janelas prováveis de vaga ─────────────────────────────

    @staticmethod
    def janelas_provaveis(dias: Optional[int], disciplina: str) -> Dict[str, Any]:
        return {"dias": dias or 14, "janelas": historico_mod.janelas_provaveis(dias or 14, disciplina)}

    def aplicar_janela(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        """Usa uma janela sugerida pelo histórico como janela diária da execução (035)."""
        from app.core.regras import descrever_janela, problemas_janela
        j = dados.get("janela") if isinstance(dados.get("janela"), dict) else {}
        try:
            dias = sorted({int(x) for x in (j.get("dias") or []) if 0 <= int(x) <= 6})
        except (TypeError, ValueError):
            dias = []
        janela = {"ativa": True, "inicio": str(j.get("inicio", ""))[:5], "fim": str(j.get("fim", ""))[:5], "dias": dias}
        problemas = problemas_janela(janela)
        if problemas:
            raise ErroApi(400, "Janela inválida:", problemas=problemas)
        if not _bool(dados.get("confirmado")):
            raise _precisa_confirmar(f"Usar a janela diária {descrever_janela(janela)} nas próximas execuções?\n\n"
                                     "Fora dela as buscas ficam pausadas. É estatística do seu histórico — vagas "
                                     "podem surgir em outros horários.", titulo="Usar janela sugerida")
        with self.lock:
            self.settings["janela"] = janela
            salvar_settings(self.settings)
        return {"ok": True, "mensagem": f"Janela diária definida: {descrever_janela(janela)}. Vale a partir da próxima execução."}

    # ── Fase 5: segurança, URLs, dumps, pacote de suporte, assistente, linha do tempo ──

    def alertas_seguranca(self) -> Dict[str, Any]:
        from app.core.seguranca_config import alertas_de_configuracao
        return {"alertas": alertas_de_configuracao(self.settings, max(1, sum(1 for d in self.disciplinas if d.ativa)))}

    def testar_urls(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        """Sugestão 047: testa os endereços do formulário (ainda não salvos) ou os salvos."""
        from app.core.seguranca_config import testar_urls
        urls = dados.get("urls") if isinstance(dados.get("urls"), dict) else self.settings.get("urls", {})
        urls = {str(k)[:40]: str(v).strip()[:500] for k, v in list(urls.items())[:10]}
        return {"resultados": testar_urls(urls)}

    @staticmethod
    def listar_dumps() -> Dict[str, Any]:
        from app.core.suporte import listar_dumps
        return {"dumps": listar_dumps()}

    def ler_dump(self, nome: str) -> Dict[str, Any]:
        from app.core.suporte import ler_dump
        lido = ler_dump(nome, self.sessao.sigaa)
        if not lido:
            raise ErroApi(404, "Página não encontrada (pode ter sido apagada pela limpeza automática).")
        lido.pop("html", None)  # a interface só mostra o texto; o HTML (mascarado) vai no pacote de suporte
        return lido

    def previa_pacote_suporte(self) -> Dict[str, Any]:
        from app.core.suporte import conteudo_pacote_suporte
        return {"arquivos": conteudo_pacote_suporte(self.sessao.sigaa)}

    def gerar_pacote_suporte(self) -> tuple:
        from app.core.suporte import gerar_pacote_suporte, nome_pacote_suporte
        return gerar_pacote_suporte(self.sessao.sigaa), nome_pacote_suporte()

    def _contexto_assistente(self) -> Dict[str, Any]:
        from app.core.relatorios import listar_relatorios
        snap = None
        motor = self._motor
        if motor is not None and hasattr(motor, "snapshot"):
            try:
                snap = motor.snapshot()
            except Exception:
                snap = None
        ultima = None
        if snap is None:
            lista = listar_relatorios(1)
            ultima = lista[0] if lista else None
        return {"snap": snap, "ultima": ultima}

    def assistente(self) -> Dict[str, Any]:
        from app.core.assistente import SINTOMAS, recomendar_configuracao
        ctx = self._contexto_assistente()
        return {"sintomas": [{"id": k, "texto": v} for k, v in SINTOMAS.items()],
                "recomendacoes": recomendar_configuracao(self.settings, ctx["snap"], ctx["ultima"])}

    def diagnosticar_sintoma(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        from app.core.assistente import diagnosticar
        try:
            return diagnosticar(str(dados.get("sintoma", "")), self.settings, self.disciplinas, self.sessao.sigaa,
                                **self._contexto_assistente())
        except ValueError as e:
            raise ErroApi(400, str(e))

    def aplicar_recomendacao(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        from app.core.assistente import aplicar_recomendacao, recomendar_configuracao
        ctx = self._contexto_assistente()
        with self.lock:
            rec = next((r for r in recomendar_configuracao(self.settings, ctx["snap"], ctx["ultima"])
                        if r["id"] == dados.get("id")), None)
            if rec is None:
                raise ErroApi(409, "Essa recomendação não vale mais (as métricas ou a configuração mudaram).")
            novos = dict(self.settings)
            problemas = aplicar_recomendacao(novos, rec)
            if problemas:
                raise ErroApi(400, "A recomendação não passou na validação:", problemas=problemas)
            self.settings = novos
            salvar_settings(self.settings)
        extra = " Vale a partir da próxima execução." if self._executor and self._executor.em_execucao() else ""
        return {"ok": True, "mensagem": f"Aplicado: {rec['texto']}{extra}"}

    def linha_do_tempo(self, execucao_id: str = "") -> Dict[str, Any]:
        dados = linha_do_tempo(self.caminho_log(), execucao_id or None)
        motor = self._motor
        if motor is not None and dados["execucao_id"] == getattr(motor, "execucao_id", None):
            dados["tentativas"] = motor.tentativas_publicas() if hasattr(motor, "tentativas_publicas") else []
        else:
            from app.core.relatorios import carregar_relatorio
            resumo = carregar_relatorio(dados["execucao_id"]) if dados["execucao_id"] else None
            dados["tentativas"] = (resumo or {}).get("tentativas", [])
        return dados

    # ── Experimental ──────────────────────────────────────────────────────

    @staticmethod
    def experimentos() -> Dict[str, Any]:
        from app.experimental import listar_experimentos
        return {"experimentos": [{
            "id": e.id, "nome": e.nome, "descricao": e.descricao, "origem": e.origem, "status": e.status,
            "disponivel": e.disponivel(), "dependencias": e.dependencias, "riscos": e.riscos,
            "guia": e.guia_instalacao or "Nenhuma instalação adicional necessária para este experimento.",
        } for e in listar_experimentos()]}

    @staticmethod
    def executar_experimento(dados: Dict[str, Any]) -> Dict[str, Any]:
        from app.experimental import listar_experimentos
        exp = next((e for e in listar_experimentos() if e.id == dados.get("id")), None)
        if exp is None or exp.executar is None:
            raise ErroApi(404, "Experimento não encontrado.")
        if not _bool(dados.get("confirmado")):
            raise _precisa_confirmar(
                f"Você está prestes a executar o recurso experimental:\n\n\"{exp.nome}\"\n\n"
                "Isso usa uma implementação alternativa, não validada como o caminho principal, "
                "e pode se comportar de forma inesperada.\n\nDeseja continuar?",
                titulo="Confirmar execução experimental",
            )
        try:
            resultado = exp.executar()
        except Exception as e:  # uma falha experimental NUNCA derruba o programa principal
            resultado = f"❌ O experimento falhou (isso é esperado às vezes — é experimental): {type(e).__name__}: {e}"
        return {"ok": True, "resultado": resultado}

    # ── Ajuda / Sobre ─────────────────────────────────────────────────────

    @staticmethod
    def ajuda() -> Dict[str, Any]:
        documentos = []
        for nome_arquivo, titulo in [("GUIA_DE_USO.md", "Guia de uso"), ("SEGURANCA.md", "Segurança e privacidade")]:
            caminho = os.path.join(pasta_docs(), nome_arquivo)
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    conteudo = f.read()
            except OSError:
                conteudo = "Arquivo de ajuda não encontrado."
            documentos.append({"titulo": titulo, "arquivo": nome_arquivo, "conteudo": conteudo})
        return {"documentos": documentos}

    @staticmethod
    def sobre() -> Dict[str, Any]:
        from app.core.shortcut import GUIA_MANUAL, suportado
        from app.core.distribuicao import hash_executavel
        return {"versao": VERSAO_APP, "repositorio": URL_REPOSITORIO, "atalho_suportado": suportado(), "guia_manual": GUIA_MANUAL,
                "sha256": hash_executavel(), "verificar_ao_abrir": bool(carregar_settings().get("atualizacoes", {}).get("verificar_ao_abrir"))}

    def verificar_atualizacao(self) -> Dict[str, Any]:
        """Sugestão 099: uma consulta ao GitHub, só quando pedida (ou com a opção ligada)."""
        from app.core.distribuicao import verificar_atualizacao
        r = verificar_atualizacao()
        if r.get("nova"):
            self._registrar_evento("versao_nova", r["texto"], "info")
        return r

    def preferencia_atualizacao(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            self.settings["atualizacoes"] = {"verificar_ao_abrir": _bool(dados.get("verificar_ao_abrir"))}
            salvar_settings(self.settings)
        return {"ok": True}

    def _verificar_ao_abrir(self) -> None:
        if not (self.settings.get("atualizacoes") or {}).get("verificar_ao_abrir"):
            return
        threading.Thread(target=lambda: self.verificar_atualizacao(), name="VerificaVersao", daemon=True).start()

    @staticmethod
    def criar_atalho() -> Dict[str, Any]:
        from app.core.shortcut import GUIA_MANUAL, criar_atalho_area_trabalho
        try:
            caminho = criar_atalho_area_trabalho()
        except Exception as e:
            raise ErroApi(500, f"Não foi possível criar automaticamente ({e}).", guia_manual=GUIA_MANUAL)
        return {"ok": True, "mensagem": f"Atalho criado em: {caminho}"}

    # ── Assistente de primeira execução (seção 74) ───────────────────────

    def finalizar_assistente(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        """Conclui (valida tudo e salva) ou dispensa ("configurar depois") o assistente inicial."""
        from app.core import configuracao_inicial as ci
        with self.lock:
            if _bool(dados.get("dispensar")):
                self.settings = ci.dispensar(self.settings)
                self.primeira_execucao = False
                return {"ok": True, "mensagem": "Tudo bem — reabra o assistente quando quiser em Config. Avançadas."}
            settings, disciplinas, problemas = ci.aplicar(dados, self.settings, self.disciplinas, self.sessao)
            if problemas:
                raise ErroApi(400, "Revise antes de concluir:", problemas=problemas)
            self.settings, self.disciplinas = settings, disciplinas
            self.primeira_execucao = False
        return {"ok": True, "mensagem": "Configuração inicial salva."}

    def validar_etapa_assistente(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        from app.core import configuracao_inicial as ci
        etapa = str(dados.get("etapa", ""))
        pendentes = [ci.disciplina_de_dados(d)[0] for d in (dados.get("pendentes") or []) if isinstance(d, dict)]
        r = ci.validar_etapa(etapa, dados.get("dados") or {}, self.disciplinas + pendentes)
        return {"ok": not r["problemas"], **r}

    def resumo_assistente(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        from app.core import configuracao_inicial as ci
        return {"linhas": ci.resumo(dados)}

    # ── Encerramento ─────────────────────────────────────────────────────

    def encerrar(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        if self._executor and self._executor.em_execucao() and not _bool(dados.get("confirmado")):
            raise _precisa_confirmar("O monitor ainda está em execução. Parar e sair mesmo assim?", titulo="Sair")
        self.evento_encerrar.set()
        return {"ok": True, "mensagem": "Interface Web encerrada. Pode fechar esta aba."}

    def finalizar(self) -> None:
        """Chamado quando o servidor para: mesmo cuidado do _ao_fechar da GUI."""
        if self._executor and self._executor.em_execucao():
            self._executor.parar()
            self._executor.aguardar(timeout=5)
        encerrar_sessao()  # apaga credenciais da memória
