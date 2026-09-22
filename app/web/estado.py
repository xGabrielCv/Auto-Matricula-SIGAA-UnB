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
    SECOES_RESTAURAVEIS, Disciplina, aplicar_segredos_notificacao_salvos, apagar_segredos_notificacao,
    carregar_disciplinas, carregar_settings, existe_segredos_notificacao_salvos, exportar_configuracao,
    importar_configuracao, pre_visualizar_importacao, restaurar_padroes, salvar_disciplinas,
    salvar_segredos_notificacao, salvar_settings, validar_disciplinas, validar_settings,
)
from app.core.credentials import encerrar_sessao, obter_sessao
from app.core.crash_recovery import verificar_encerramento_anterior
from app.core.departamentos import buscar_departamentos, codigo_conhecido, nome_do_departamento
from app.core.diagnostics import (
    VERSAO_APP, ResultadoChecagem, checar_conectividade_em_camadas, checar_conectividade_sigaa,
    checar_modo_execucao, checar_saude_sistema, gerar_relatorio_texto,
)
from app.core.disclaimer import CONFIRMACOES, RESUMOS_CURTOS, TEXTO_COMPLETO, TITULO
from app.core.factory import construir_motor
from app.core.runner import ExecutorMotor
from app.dashboard.log_humano import CATEGORIAS, traduzir
from app.dashboard.metrics import ColetorMetricas, LogTailer, formatar_uptime
from app.utils.cleanup import limpar_debug_dumps, resumo_espaco_em_disco
from app.utils.paths import caminho as caminho_projeto
from app.utils.paths import pasta_config, pasta_docs

URL_REPOSITORIO = "https://github.com/xGabrielCv/Auto-Matricula-SIGAA-UnB"
MAX_LOGS_MEMORIA = 1000  # mesmo limite da tela de Logs da GUI

# Textos de ajuda — os mesmos da GUI, importados de lá quando possível para
# não haver duas versões divergentes (tkinter não é necessário para ler as
# constantes, mas o import do módulo da tela exige tkinter; por isso a cópia
# fica isolada em _textos_ajuda()).


def _textos_ajuda() -> Dict[str, str]:
    try:
        from app.gui.screens.avancado import AJUDA
        from app.gui.screens.disciplinas import TEXTO_AJUDA_DEPARTAMENTO
        from app.gui.screens.notificacoes import TEXTO_AJUDA_ALARME, TEXTO_AJUDA_NTFY, TEXTO_AJUDA_TELEGRAM
        textos = {f"avancado_{k}": v for k, v in AJUDA.items()}
        textos.update({
            "departamento": TEXTO_AJUDA_DEPARTAMENTO, "telegram": TEXTO_AJUDA_TELEGRAM,
            "ntfy": TEXTO_AJUDA_NTFY, "alarme": TEXTO_AJUDA_ALARME,
        })
        return textos
    except Exception:
        return {}


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
        self.aviso_aceito = False  # nunca persistido: o aviso aparece em TODA execução

        # Mesma ordem de inicialização da GUI (app/gui/app.py).
        self.sessao = obter_sessao()
        self.settings = carregar_settings()
        self.disciplinas: List[Disciplina] = carregar_disciplinas()
        aplicar_segredos_notificacao_salvos(self.sessao.notificacao)
        self.primeira_execucao = (
            not os.path.exists(os.path.join(pasta_config(), "settings.json")) and not self.disciplinas
        )
        self.encerramento_anterior = verificar_encerramento_anterior()
        limpar_debug_dumps(manter=self.settings["logs"]["arquivos_mantidos"])

        self._executor: Optional[ExecutorMotor] = None
        self._status: Dict[str, Any] = {"estado": "parado", "mensagem": "Parado.", "modo": None, "dry_run": None, "inicio": None}

        self._lock_metricas = threading.Lock()
        self._coletor = ColetorMetricas()
        self._tailer_dashboard: Optional[LogTailer] = None

        self._lock_logs = threading.Lock()
        self._logs: deque = deque(maxlen=MAX_LOGS_MEMORIA)
        self._seq_logs = 0
        self._tailer_logs: Optional[LogTailer] = None

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
                "qtd_disciplinas": len(self.disciplinas),
                "qtd_disciplinas_ativas": sum(1 for d in self.disciplinas if d.ativa),
                "modo": self.settings["modo"],
                "dry_run": self.settings["dry_run"],
                "agendar_inicio": self.settings.get("agendar_inicio") or "",
                "abrir_dashboard_ao_iniciar": self.settings.get("abrir_dashboard_ao_iniciar", True),
                "ajuda": _textos_ajuda(),
            }

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
        marcadas = dados.get("confirmacoes") or {}
        faltando = [chave for chave, _ in CONFIRMACOES if marcadas.get(chave) is not True]
        if faltando:
            raise ErroApi(400, "É preciso confirmar TODOS os pontos do aviso legal para continuar.", faltando=faltando)
        with self.lock:
            self.aviso_aceito = True
        return {"ok": True}

    def recusar_aviso(self) -> Dict[str, Any]:
        # Mesmo efeito de "Recusar e sair" na GUI: encerra este modo.
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
            cred.nascimento = str(dados.get("nascimento", "")).strip()
        if not cred.preenchida():
            raise ErroApi(400, "Preencha matrícula, senha, CPF e data de nascimento.", credenciais=self.credenciais())
        return {"ok": True, "mensagem": "Credenciais mantidas em memória para esta execução (nada foi salvo em disco).",
                "credenciais": self.credenciais()}

    def limpar_credenciais(self) -> Dict[str, Any]:
        self.sessao.sigaa.limpar()
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
    def buscar_departamentos(termo: str) -> Dict[str, Any]:
        return {"departamentos": [{"codigo": d.codigo, "nome": d.nome} for d in buscar_departamentos(termo or "")[:25]]}

    def _disciplina_do_formulario(self, dados: Dict[str, Any]) -> Disciplina:
        codigo = str(dados.get("codigo", "")).strip().upper()
        turma = str(dados.get("turma", "")).strip()
        try:
            depto = int(str(dados.get("departamento", "")).strip() or 0)
        except ValueError:
            depto = 0
        if not codigo or not turma or depto <= 0:
            raise ErroApi(400, "Preencha código da disciplina, turma, e selecione (ou digite) um departamento válido.")
        if not codigo_conhecido(depto) and not _bool(dados.get("confirmado")):
            raise _precisa_confirmar(
                f"O código de departamento {depto} não está na lista de referência conhecida.\n\n"
                "Isso pode ser normal (departamento novo, ou a lista está desatualizada) — mas confira "
                "com \"Como encontrar?\" se não tiver certeza.\n\nSalvar mesmo assim?",
                titulo="Código não reconhecido",
            )
        return Disciplina(codigo=codigo, turma=turma, departamento=depto, professor=str(dados.get("professor", "")).strip())

    def _indice_valido(self, indice: int, chave_esperada: Optional[str]) -> int:
        if not (0 <= indice < len(self.disciplinas)):
            raise ErroApi(404, "Disciplina não encontrada — a lista foi atualizada.")
        # Proteção contra lista desatualizada na página: nunca age sobre uma
        # disciplina diferente da que o usuário estava vendo.
        if chave_esperada is not None and self.disciplinas[indice].chave() != chave_esperada:
            raise ErroApi(409, "A lista de disciplinas mudou desde que a página foi carregada. Atualize e tente de novo.")
        return indice

    def adicionar_disciplina(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        nova = self._disciplina_do_formulario(dados)
        with self.lock:
            self.disciplinas.append(nova)
            salvar_disciplinas(self.disciplinas)
        return {"ok": True, "mensagem": f"{nova.chave()} adicionada.", **self.listar_disciplinas()}

    def editar_disciplina(self, indice: int, dados: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            i = self._indice_valido(indice, dados.get("chave_original"))
            nova = self._disciplina_do_formulario(dados)
            nova.ativa = self.disciplinas[i].ativa  # editar nunca reativa/desativa por tabela
            self.disciplinas[i] = nova
            salvar_disciplinas(self.disciplinas)
        return {"ok": True, "mensagem": f"{nova.chave()} atualizada.", **self.listar_disciplinas()}

    def remover_disciplina(self, indice: int, dados: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            i = self._indice_valido(indice, dados.get("chave"))
            d = self.disciplinas[i]
            if not _bool(dados.get("confirmado")):
                raise _precisa_confirmar(f"Remover {d.codigo}-{d.turma} da lista?", titulo="Remover")
            self.disciplinas.pop(i)
            salvar_disciplinas(self.disciplinas)
        return {"ok": True, "mensagem": f"{d.chave()} removida.", **self.listar_disciplinas()}

    def alternar_disciplina(self, indice: int, dados: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            i = self._indice_valido(indice, dados.get("chave"))
            self.disciplinas[i].ativa = not self.disciplinas[i].ativa
            salvar_disciplinas(self.disciplinas)
            d = self.disciplinas[i]
        return {"ok": True, "mensagem": f"{d.chave()} {'ativada' if d.ativa else 'desativada'}.", **self.listar_disciplinas()}

    # ── Execução ──────────────────────────────────────────────────────────

    def status_execucao(self) -> Dict[str, Any]:
        status = dict(self._status)
        status["em_execucao"] = bool(self._executor and self._executor.em_execucao())
        return status

    def iniciar(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if self._executor and self._executor.em_execucao():
                raise ErroApi(409, "O motor já está em execução. Pare antes de iniciar de novo.")

            modo = dados.get("modo", self.settings["modo"])
            if modo not in ("matricula", "monitoramento"):
                raise ErroApi(400, "Modo de execução inválido.")
            dry_run = _bool(dados.get("dry_run", self.settings["dry_run"]))
            agendar = str(dados.get("agendar_inicio") or "").strip() or None

            novos = dict(self.settings)
            novos.update({"modo": modo, "dry_run": dry_run, "agendar_inicio": agendar})

            # Mesmas validações de TelaExecucao._validar_pronto (GUI).
            if not self.sessao.sigaa.preenchida():
                raise ErroApi(400, "Preencha suas credenciais do SIGAA na aba Credenciais antes de iniciar.", ir_para="credenciais")
            problemas = validar_settings(novos) + validar_disciplinas(self.disciplinas)
            if problemas:
                raise ErroApi(400, "Antes de iniciar, corrija:", problemas=problemas)

            # Confirmação extra (só na Web): matrícula REAL, com DRY RUN desligado.
            if modo == "matricula" and not dry_run and not _bool(dados.get("confirmado")):
                raise _precisa_confirmar(
                    "O DRY RUN está DESLIGADO: quando encontrar vaga, o programa vai CONFIRMAR A MATRÍCULA DE "
                    "VERDADE no SIGAA.\n\nTem certeza de que quer iniciar a matrícula real?",
                    titulo="Confirmar matrícula real",
                )

            self.settings = novos
            salvar_settings(self.settings)

            motor = construir_motor(self.settings, self.sessao, self.disciplinas)
            self._executor = ExecutorMotor(motor, ao_finalizar=self._ao_finalizar)
            self._executor.iniciar()
            modo_txt = "Matrícula automática" if modo == "matricula" else "Somente monitoramento"
            if modo == "matricula":
                modo_txt += " (DRY RUN — teste)" if dry_run else " (REAL)"
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

    def parar(self) -> Dict[str, Any]:
        with self.lock:
            if self._executor and self._executor.em_execucao():
                self._executor.parar()
                self._status = {**self._status, "estado": "parando", "mensagem": "Parando... (aguardando workers atuais encerrarem)"}
        return {"ok": True, "execucao": self.status_execucao()}

    # ── Dashboard ─────────────────────────────────────────────────────────

    def dashboard(self) -> Dict[str, Any]:
        with self._lock_metricas:
            if self._tailer_dashboard is None:
                caminho_log = caminho_projeto("data", "sigaa_sniper_audit.json")
                if os.path.exists(caminho_log):
                    self._tailer_dashboard = LogTailer(caminho_log)
            if self._tailer_dashboard:
                for linha in self._tailer_dashboard.read_new_lines():
                    self._coletor.processar_linha(linha, ao_vivo=True)
            m = self._coletor.snapshot()

        agora = time.time()
        workers = []
        for w_id, w in m["workers"].items():
            workers.append({
                "id": w_id, "erros": w["erros_count"], "buscas": w["buscas_feitas"], "ultima_acao": w["ultima_acao"],
                "latencia": w["latencia"] or None, "cor_latencia": w.get("cor_lat"), "ocioso_seg": round(agora - w["timestamp"], 1),
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
        }

    # ── Central de Logs ──────────────────────────────────────────────────

    def logs(self, desde: int = 0) -> Dict[str, Any]:
        with self._lock_logs:
            if self._tailer_logs is None:
                caminho_log = caminho_projeto("data", "sigaa_sniper_audit.json")
                if os.path.exists(caminho_log):
                    self._tailer_logs = LogTailer(caminho_log)
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
            "eventos": dict(cfg["eventos"]),
            "telegram_token": n.telegram_token, "telegram_chat_id": n.telegram_chat_id,
            "ntfy_topic": n.ntfy_topic, "ntfy_servidor": n.ntfy_servidor,
            "lembrar": existe_segredos_notificacao_salvos(),
        }

    def salvar_notificacoes(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        repeticoes = _int(dados.get("alarme_repeticoes", 3), "Repetições do alarme", 1, 20)
        duracao = _int(dados.get("alarme_duracao", 20), "Duração do alarme", 1, 120)
        with self.lock:
            cfg = self.settings["notificacoes"]
            cfg["telegram_ativo"] = _bool(dados.get("telegram_ativo"))
            cfg["ntfy_ativo"] = _bool(dados.get("ntfy_ativo"))
            cfg["alarme_ativo"] = _bool(dados.get("alarme_ativo"))
            cfg["alarme"]["repeticoes"] = repeticoes
            cfg["alarme"]["duracao_seg"] = duracao
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

            if _bool(dados.get("lembrar")):
                salvar_segredos_notificacao(n.telegram_token, n.telegram_chat_id, n.ntfy_topic, n.ntfy_servidor)
                msg = "Configuração salva (incluindo segredos de notificação em disco, como solicitado)."
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

        canal = dados.get("canal")
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
            "nivel_log_console": s.get("debug", {}).get("nivel_log_console", "INFO"),
            "logs": dict(s["logs"]), "json_audit": dict(s["json_audit"]), "urls": dict(s.get("urls", {})),
            "web": dict(s.get("web", {})), "espaco": resumo_espaco_em_disco(),
            "secoes_restauraveis": SECOES_RESTAURAVEIS,
        }

    def salvar_avancado(self, dados: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            novos = dict(self.settings)
            novos["num_workers"] = _int(dados.get("num_workers"), "Quantidade de workers", -10**9, 10**9)
            novos["intervalo_busca"] = round(_float(dados.get("intervalo_busca"), "Intervalo entre buscas"), 2)
            novos["timeout_req"] = _int(dados.get("timeout_req"), "Timeout de requisição", -10**9, 10**9)
            novos["abrir_dashboard_ao_iniciar"] = _bool(dados.get("abrir_dashboard_ao_iniciar"))
            nivel = dados.get("nivel_log_console", "INFO")
            novos["debug"] = {"nivel_log_console": nivel if nivel in ("INFO", "DEBUG") else "INFO"}
            logs, audit = dados.get("logs") or {}, dados.get("json_audit") or {}
            novos["logs"] = {"tamanho_max_mb": _int(logs.get("tamanho_max_mb"), "Tamanho máximo dos logs", 0, 10**6),
                             "arquivos_mantidos": _int(logs.get("arquivos_mantidos"), "Arquivos de log mantidos", 0, 50)}
            novos["json_audit"] = {"tamanho_max_mb": _int(audit.get("tamanho_max_mb"), "Tamanho máximo do JSON", 1, 500),
                                   "arquivos_mantidos": _int(audit.get("arquivos_mantidos"), "Arquivos JSON mantidos", 0, 50)}
            urls = dados.get("urls") or {}
            novos["urls"] = {chave: str(urls.get(chave, "")).strip() for chave in self.settings.get("urls", {})}
            web = dados.get("web") or {}
            novos["web"] = {
                "host": str(web.get("host", "127.0.0.1")).strip() or "127.0.0.1",
                "porta": _int(web.get("porta", 8765), "Porta da Interface Web", 0, 10**6),
                "abrir_navegador": _bool(web.get("abrir_navegador", True)),
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
        resultados = [*checar_saude_sistema(), checar_modo_execucao()]
        try:
            resultados.append(asyncio.run(checar_conectividade_sigaa()))
        except Exception as e:
            resultados.append(ResultadoChecagem("Conectividade com o SIGAA", False, str(e)))
        return {"relatorio": gerar_relatorio_texto(resultados), "itens": [_resultado_json(r) for r in resultados]}

    @staticmethod
    def diagnostico_camadas() -> Dict[str, Any]:
        resultados = asyncio.run(checar_conectividade_em_camadas())
        return {"relatorio": gerar_relatorio_texto(resultados), "itens": [_resultado_json(r) for r in resultados]}

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
        return {"versao": VERSAO_APP, "repositorio": URL_REPOSITORIO, "atalho_suportado": suportado(), "guia_manual": GUIA_MANUAL}

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
        with self.lock:
            cred = dados.get("credenciais") or {}
            if any(cred.values()):
                s = self.sessao.sigaa
                s.usuario = str(cred.get("usuario", "")).strip()
                s.senha = str(cred.get("senha", ""))
                s.cpf = str(cred.get("cpf", "")).strip()
                s.nascimento = str(cred.get("nascimento", "")).strip()
            for d in dados.get("disciplinas") or []:
                try:
                    codigo = str(d.get("codigo", "")).strip().upper()
                    turma = str(d.get("turma", "")).strip()
                    depto = int(d.get("departamento") or 0)
                except (TypeError, ValueError, AttributeError):
                    continue
                if codigo and turma and depto > 0:
                    self.disciplinas.append(Disciplina(codigo=codigo, turma=turma, departamento=depto))
            if dados.get("modo") in ("matricula", "monitoramento"):
                self.settings["modo"] = dados["modo"]
            # Igual ao "Finalizar"/"Pular" da GUI: salva, e o assistente não volta a aparecer.
            salvar_settings(self.settings)
            salvar_disciplinas(self.disciplinas)
            self.primeira_execucao = False
        return {"ok": True}

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
