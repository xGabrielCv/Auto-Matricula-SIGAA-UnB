"""
Motor de matrícula — refatoração da SIGAA-SNIPER-v4.0-JESUS.py.

REGRA: a lógica funcional (login, navegação por departamento, parser da
tabela de turmas, preenchimento da confirmação, classificação de resultado)
é PRESERVADA exatamente como estava na v4.0. As únicas mudanças são
estruturais:

  1. Estado que era global no script (ALVOS_ATIVOS, LOCKS_ALVOS, credenciais,
     NUM_WORKERS etc.) agora vive dentro da classe MotorMatricula, para que a
     GUI possa iniciar/parar execuções sem reiniciar o processo Python.
  2. Um stop_event permite parar os workers de forma limpa (botão "Parar" na
     GUI/terminal) em vez de exigir Ctrl+C.
  3. Um callback on_evento(tipo, dados) é chamado nos mesmos pontos em que a
     v4.0 logava eventos importantes — usado pela GUI (dashboard ao vivo) e
     pelo gerenciador de notificações. Notificações nunca podem travar ou
     derrubar o monitor (seção 39 do pedido): toda chamada ao callback é
     protegida por try/except e não é aguardada de forma bloqueante.
  4. Dumps de debug vão para logs/ em vez da raiz do projeto.
  5. Espera progressiva após falhas de login/departamento (em vez de repetir
     imediatamente) e encerramento da execução quando nenhum worker consegue
     continuar. Não altera parser nem decisão de matrícula.
  6. Telemetria (Fase 2): nos mesmos pontos em que o log já era escrito, o
     motor também registra estado por disciplina e por worker, contadores e
     séries (app/core/telemetria.py), e as linhas do log ganham campos
     estruturados (`evento`, `codigo`, `turma`, `latencia_ms`...). Ao terminar,
     grava um resumo da execução em data/relatorios/. Nenhum desses registros
     participa de decisões — só observam.
  7. Automação avançada (Fase 4): proteção de carga (limitador, logins
     escalonados, disjuntor), pausar/retomar, janela de execução e horário de
     término, agendamento pelo relógio do SIGAA, verificação prévia das
     disciplinas, grupos de turmas alternativas, prioridade e alteração de
     disciplinas com a execução em andamento. A decisão SUCESSO/ERRO_REGRA/
     FALHA da confirmação continua a da v4.0; a classificação de erros só
     acrescenta paradas SEGURAS (dados de confirmação recusados, período
     encerrado) — nunca uma nova tentativa.
  8. Observabilidade (Fase 5): dumps de debug gravados já com dados pessoais
     mascarados, rastreamento de cada tentativa de matrícula (etapas e tempos),
     supervisor que recria um worker travado (nunca durante uma tentativa),
     alertas por limiar, detecção de página de manutenção e resumo periódico
     por notificação. Nada disso muda a decisão de matrícula.

Ver docs/ARQUITETURA.md para o diff detalhado "antes/depois" desta migração.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from collections import Counter, deque
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from app.core.alertas import AvaliadorAlertas, texto_resumo_periodico
from app.core.credentials import CredenciaisSigaa
from app.core.protecao import STATUS_SOBRECARGA, Disjuntor, LimitadorTaxa
from app.core.regras import classificar_resposta_confirmacao, dentro_da_janela, descrever_janela, inspecionar_turma
from app.core.relogio import descrever_offset, medir_offset_relogio
from app.core.suporte import redigir_html
from app.core.telemetria import ESTADOS_ALVO, ESTADOS_FINAIS_ALVO, ESTADOS_WORKER, Telemetria
from app.utils.paths import caminho as caminho_projeto

URL_CAS_LOGIN = "https://autenticacao.unb.br/sso-server/login?service=https%3A%2F%2Fsig.unb.br%2Fsigaa%2Flogin%2Fcas"
URL_PORTAL_DISCENTE = "https://sigaa.unb.br/sigaa/portais/discente/discente.jsf"
URL_MATRICULA_EXTRA = "https://sigaa.unb.br/sigaa/graduacao/matricula/extraordinaria/matricula_extraordinaria.jsf"
URL_CONFIRMACAO = "https://sigaa.unb.br/sigaa/graduacao/matricula/extraordinaria/confirmacao.jsf"
URL_SIGAA_BASE = "https://sigaa.unb.br"

# Seção 79 do pedido de continuação: URLs configuráveis nas Configurações
# Avançadas, para o caso do SIGAA mudar endereços no futuro — sem precisar
# editar código. Os valores acima continuam sendo o padrão; MotorMatricula
# só os sobrescreve se receber algo diferente em `urls=`.
URLS_PADRAO: Dict[str, str] = {
    "cas_login": URL_CAS_LOGIN,
    "portal_discente": URL_PORTAL_DISCENTE,
    "matricula_extra": URL_MATRICULA_EXTRA,
    "confirmacao": URL_CONFIRMACAO,
    "sigaa_base": URL_SIGAA_BASE,
}

RE_VIEWSTATE = re.compile(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"')

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
}

EventoCallback = Callable[[str, dict], None]

# Sugestão 090: assinaturas de página de manutenção/indisponibilidade do SIGAA.
# Só é consultada quando a busca NÃO achou a turma, e só no começo da página.
RE_MANUTENCAO = re.compile(r"em manuten[cç][aã]o|sistema (?:temporariamente )?indispon[ií]vel|"
                           r"servi[cç]o indispon[ií]vel|service unavailable", re.I)

# Etapas de uma tentativa de matrícula (sugestão 059), na ordem em que acontecem.
ETAPAS_TENTATIVA = {
    "selecao_enviada": "turma selecionada",
    "tela_confirmacao": "tela de confirmação recebida",
    "formulario_preenchido": "formulário de confirmação preenchido",
    "confirmacao_enviada": "confirmação enviada ao SIGAA",
    "dry_run_parado": "parado antes da confirmação (DRY RUN)",
}


def _callback_nulo(_tipo: str, _dados: dict) -> None:
    return None


class SigaaWorker:
    """Um worker autossuficiente — idêntico em comportamento ao da v4.0, exceto
    pela espera progressiva depois de falhas de login/departamento (abaixo)."""

    # Espera após falhas SEGUIDAS de login ou de preparação do departamento:
    # 1s, 2s, 4s... até o teto. Antes, a falha fazia o worker repetir na hora
    # (com o SIGAA fora do ar ou fora do período de matrícula, 20 workers
    # martelavam o portal/CAS em laço). Zera no primeiro sucesso.
    #   - login: o worker inteiro espera (sem sessão, nada funciona);
    #   - departamento: só aquele departamento é adiado — disciplinas de outros
    #     departamentos continuam sendo buscadas no ritmo normal.
    ESPERA_FALHA_BASE_SEG = 1.0
    ESPERA_FALHA_MAX_SEG = 30.0

    def __init__(self, worker_id: int, motor: "MotorMatricula"):
        self.id = worker_id
        self.motor = motor
        self.urls = motor.urls  # atalho — mesmo dict, só pra não escrever self.motor.urls toda hora
        self.client = httpx.AsyncClient(
            headers=BROWSER_HEADERS, timeout=motor.timeout_req, follow_redirects=True, **motor.opcoes_cliente
        )
        self.payloads_base: Dict[int, Dict[str, str]] = {}
        self.log_prefix = f"[W{self.id}]"
        self.rotulo_log = f"W{self.id}"
        self.falhas_seguidas = 0
        # "rede" = não houve resposta (vale tentar de novo); "recusado" = o SIGAA
        # respondeu mas o login não entrou (provável credencial errada — repetir
        # só arriscaria bloquear a conta).
        self.motivo_falha_login: Optional[str] = None
        self._falhas_depto: Dict[int, int] = {}
        self._depto_adiado_ate: Dict[int, float] = {}
        # Observabilidade (sugestões 055/056): só leitura pelas interfaces.
        self.estado = "iniciando"
        self.alvo_atual: Optional[str] = None
        self.ultimo_progresso = time.time()
        self.ultima_latencia_ms: Optional[float] = None
        self.contadores: Counter = Counter()
        # Supervisor (057): batimento a cada volta do laço; tentativa em curso (059).
        self.ultimo_batimento = time.time()
        self.tentativa: Optional[Dict[str, Any]] = None

    def mudar_estado(self, estado: str, alvo: Optional[str] = None) -> None:
        self.estado = estado
        if alvo is not None:
            self.alvo_atual = alvo
        self.ultimo_progresso = self.ultimo_batimento = time.time()

    def _etapa(self, nome: str) -> None:
        """Marca uma etapa da tentativa em curso com o tempo desde o início dela (059)."""
        t = self.tentativa
        if not t:
            return
        ms = round((time.perf_counter() - t["_t0"]) * 1000)
        t["etapas"].append({"etapa": nome, "rotulo": ETAPAS_TENTATIVA.get(nome, nome), "ms": ms})
        self.log(f"⏱️ Tentativa {t['id']}: {ETAPAS_TENTATIVA.get(nome, nome)} ({ms} ms).", evento="tentativa_etapa",
                 tentativa_id=t["id"], etapa=nome, duracao_ms=ms, codigo=t["codigo"], turma=t["turma"])

    def _espera_para(self, falhas: int) -> float:
        return min(self.ESPERA_FALHA_MAX_SEG, self.ESPERA_FALHA_BASE_SEG * 2 ** (falhas - 1))

    def _registrar_sucesso(self) -> None:
        self.falhas_seguidas = 0

    async def esperar_apos_falha(self, motivo: str) -> None:
        """Espera crescente após falhas seguidas de login, interrompível pelo botão Parar."""
        self.falhas_seguidas += 1
        espera = self._espera_para(self.falhas_seguidas)
        self.mudar_estado("aguardando")
        self.log(f"⏸️ Aguardando {espera:.0f}s antes de tentar de novo ({motivo}; falha {self.falhas_seguidas} seguida).",
                 evento="espera_falha", espera_seg=espera, motivo=motivo)
        try:
            await asyncio.wait_for(self.motor.stop_event.wait(), timeout=espera)
        except asyncio.TimeoutError:
            pass

    def _adiar_departamento(self, id_depto: int) -> None:
        falhas = self._falhas_depto.get(id_depto, 0) + 1
        self._falhas_depto[id_depto] = falhas
        espera = self._espera_para(falhas)
        self._depto_adiado_ate[id_depto] = time.monotonic() + espera
        self.contadores["falhas_departamento"] += 1
        self.motor.telemetria.registrar_erro("departamento", f"departamento {id_depto}")
        for chave, (_c, _t, depto) in list(self.motor.alvos_ativos.items()):
            if depto == id_depto:
                self.motor.atualizar_alvo(chave, "departamento_indisponivel")
        self.log(f"⏸️ Aguardando {espera:.0f}s antes de tentar de novo o departamento {id_depto} "
                 f"(não foi possível preparar a busca; falha {falhas} seguida).",
                 evento="departamento_adiado", departamento=id_depto, espera_seg=espera)

    async def fechar(self):
        await self.client.aclose()

    async def resetar_cliente(self):
        """Mata o cliente HTTP travado e recria do zero para reviver workers zumbis."""
        try:
            await self.client.aclose()
        except Exception:
            pass
        self.client = httpx.AsyncClient(
            headers=BROWSER_HEADERS, timeout=self.motor.timeout_req, follow_redirects=True, **self.motor.opcoes_cliente
        )
        self.payloads_base.clear()

    def log(self, msg: str, level=logging.INFO, **campos):
        """`campos` viram colunas estruturadas no log JSON (sugestão 053). Só
        entram nomes da lista permitida em logging_setup.CAMPOS_ESTRUTURADOS —
        nunca credenciais."""
        self.motor.log.log(level, f"{self.log_prefix} {msg}", extra={
            "worker_id": self.rotulo_log, "campos": {"execucao_id": self.motor.execucao_id, **campos}})

    def _debug_dump(self, html: str, nome: str) -> None:
        fname = caminho_projeto("logs", f"debug_W{self.id}_{nome}_{int(time.time())}.html")
        try:
            # Sugestão 066: a página vai para o disco já com matrícula, CPF, nascimento,
            # nome e valores de formulário mascarados. Se a redação falhar, nada é gravado.
            conteudo = redigir_html(html, self.motor.credenciais)
            with open(fname, "w", encoding="utf-8") as f:
                f.write(conteudo)
            self.contadores["dumps"] += 1
            if self.tentativa is not None:
                self.tentativa["dump"] = os.path.basename(fname)
            self.log(f"📄 Debug salvo (dados pessoais mascarados): {os.path.basename(fname)}", evento="dump_salvo", motivo=nome,
                     tentativa_id=(self.tentativa or {}).get("id"))
        except Exception as e:
            self.log(f"❌ Erro ao salvar arquivo de debug dump: {repr(e)}", logging.ERROR)

    # --- 1. SETUP ---

    async def realizar_login(self) -> bool:
        """Login no CAS. No máximo `logins_simultaneos` workers fazem login ao
        mesmo tempo (sugestão 073) — o resto espera a vez."""
        semaforo = self.motor._sem_login
        if semaforo is None:
            return await self._realizar_login()
        if semaforo.locked():
            self.mudar_estado("fila_login")  # esperar a vez é legítimo (o supervisor não conta como travado)
        async with semaforo:
            return await self._realizar_login()

    async def _realizar_login(self) -> bool:
        self.mudar_estado("logando")
        self.contadores["logins"] += 1
        self.log("Iniciando processo de Login no CAS...", evento="login_inicio")
        cred = self.motor.credenciais
        try:
            resp = await self.client.get(self.urls["cas_login"])
            soup = BeautifulSoup(resp.text, "html.parser")
            tokens = {
                nome: soup.find("input", attrs={"name": nome}).get("value")
                for nome in ("lt", "execution", "_eventId")
                if soup.find("input", attrs={"name": nome})
            }

            resp_login = await self.client.post(
                self.urls["cas_login"],
                data={"username": cred.usuario, "password": cred.senha, "submit": "Submit", **tokens},
                headers={"Referer": str(resp.url)},
            )

            if "continuar" in resp_login.text.lower() and "aviso" in resp_login.text.lower():
                soup_a = BeautifulSoup(resp_login.text, "html.parser")
                form_a = soup_a.find("form")
                if form_a:
                    action = form_a.get("action", "")
                    action = self.urls["sigaa_base"] + action if not action.startswith("http") else action
                    inputs = {i.get("name"): i.get("value", "") for i in form_a.find_all("input") if i.get("name")}
                    await self.client.post(action, data=inputs)

            resp_p = await self.client.get(self.urls["portal_discente"])
            if "form_menu_discente" in resp_p.text:
                self.log("✅ Login concluído!", evento="login_ok")
                self.motivo_falha_login = None
                self.mudar_estado("logado")
                return True
            self.motivo_falha_login = "recusado"
            self.motor.telemetria.registrar_erro("login", "login recusado pelo SIGAA")
            return False
        except Exception as e:
            self.log(f"💥 Erro fatal e inesperado durante a requisição de login: {repr(e)}", logging.ERROR,
                     evento="login_erro")
            self.motivo_falha_login = "rede"
            self.motor.telemetria.registrar_erro("login", type(e).__name__)
            return False

    async def relogar(self) -> None:
        """Login de recuperação dentro do ciclo: se falhar, espera antes de o
        laço tentar de novo (em vez de repetir imediatamente)."""
        await self.motor.disjuntor.liberar(self.id, self.motor.stop_event.is_set)
        if self.motor.stop_event.is_set():
            return
        self.contadores["relogins"] += 1
        if not await self.realizar_login():
            await self.esperar_apos_falha("login não concluído")

    async def teleportar_departamento(self, id_departamento: int) -> bool:
        self.mudar_estado("preparando")
        self.contadores["teleportes"] += 1
        self.log(f"Teleportando (Depto: {id_departamento})...", evento="preparando_departamento", departamento=id_departamento)
        try:
            resp = await self.client.get(self.urls["portal_discente"])
            match_id = re.search(r'name="id"\s+value="(\d+)"', resp.text)
            matches_vs = RE_VIEWSTATE.findall(resp.text)
            if not match_id or not matches_vs:
                return False

            resp_menu = await self.client.post(
                self.urls["portal_discente"],
                data={
                    "menu:form_menu_discente": "menu:form_menu_discente",
                    "id": match_id.group(1),
                    "jscook_action": "menu_form_menu_discente_discente_menu:A]#{ matriculaExtraordinaria.iniciar}",
                    "javax.faces.ViewState": matches_vs[-1],
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            html = resp_menu.text
            if "form:buscar" not in html:
                resp_mat = await self.client.get(self.urls["matricula_extra"])
                html = resp_mat.text

            soup = BeautifulSoup(html, "html.parser")
            form = soup.find("form", id="form")
            if not form:
                return False

            campos = {}
            for inp in form.find_all(["input", "select"]):
                name = inp.get("name")
                if not name or inp.get("type") in ("submit", "button"):
                    continue
                campos[name] = inp.get("value", "")

            campos["form:checkUnidade"] = "on"
            campos["form:comboDepartamento"] = str(id_departamento)
            self.payloads_base[id_departamento] = campos
            self._falhas_depto.pop(id_departamento, None)
            self._depto_adiado_ate.pop(id_departamento, None)
            return True
        except Exception as e:
            self.log(f"💥 Falha ao extrair tokens ou teleportar para departamento {id_departamento}: {repr(e)}", logging.ERROR)
            return False

    # --- 2. PARSER HÍBRIDO ---
    def parse_hot_path(self, html: str, codigo_alvo: str, turma_alvo: str) -> Optional[Dict[str, str]]:
        # Pré-checagens baratas (sugestão 072) ANTES do BeautifulSoup, sem mudar o
        # resultado: a página em minúsculas é calculada uma vez só, e se o código
        # da disciplina nem aparece no HTML nenhuma linha da tabela poderia casar.
        html_minusculo = html.lower()
        if "não foram encontradas" in html_minusculo or "nenhum resultado" in html_minusculo:
            return None
        if codigo_alvo.lower() not in html_minusculo:
            return None

        soup = BeautifulSoup(html, "html.parser")
        tabela = soup.find(id="lista-turmas-extra")
        if not tabela:
            return None

        disciplina_ativa = False
        for tr in tabela.find_all("tr"):
            classes = " ".join(tr.get("class", []))
            if "disciplina" in classes:
                disciplina_ativa = codigo_alvo.upper() in tr.get_text().upper()
                continue
            if not disciplina_ativa or ("linhaPar" not in classes and "linhaImpar" not in classes):
                continue

            tds = tr.find_all("td")
            if len(tds) < 8:
                continue

            m_turma = re.search(r"(\d+)", tds[1].get_text(strip=True))
            if (m_turma.group(1) if m_turma else "") != turma_alvo:
                continue

            m_vagas = re.search(r"(\d+)", tds[7].get_text(strip=True))
            vagas = int(m_vagas.group(1)) if m_vagas else 0
            if vagas <= 0:
                return None

            link = tr.find("a", title=re.compile(r"[Ss]elecionar turma"))
            if not link:
                continue

            onclick = link.get("onclick", "")
            m_idturma = re.search(r"'idTurma'\s*:\s*'(\d+)'", onclick)
            m_linkid = re.search(r"'(form:selecionarTurma[^']*)':", onclick)
            if not m_idturma or not m_linkid:
                continue

            tag_vs = soup.find("input", attrs={"name": "javax.faces.ViewState"})
            if not tag_vs:
                return None

            return {"idTurma": m_idturma.group(1), "link_id": m_linkid.group(1), "viewstate": tag_vs["value"], "vagas": vagas}
        return None

    # --- 3. CICLO DE BUSCA ---
    async def rodar_ciclo(self):
        alvos = self.motor.alvos_ativos
        locks = self.motor.locks_alvos
        ciclo = 0

        while alvos and not self.motor.stop_event.is_set():
            ciclo += 1
            self.ultimo_batimento = time.time()
            for chave, (codigo, turma, id_depto) in self.motor.alvos_em_ordem():
                self.ultimo_batimento = time.time()
                if self.motor.stop_event.is_set():
                    break
                await self.motor.aguardar_se_pausado(self)
                if self.motor.stop_event.is_set():
                    break
                if chave not in alvos:
                    continue
                # Prioridade (sugestão 034): "baixa" é consultada a cada 3 ciclos — sobra ritmo
                # para as prioritárias sem aumentar o total de buscas.
                if self.motor.prioridade_de(chave) == "baixa" and ciclo % 3 != 1:
                    continue
                if id_depto not in self.payloads_base:
                    if time.monotonic() < self._depto_adiado_ate.get(id_depto, 0.0):
                        continue  # departamento em espera após falhas; as outras disciplinas seguem normais
                    if not await self.teleportar_departamento(id_depto):
                        self._adiar_departamento(id_depto)
                        continue

                payload = self.payloads_base[id_depto].copy()
                payload.update({"form": "form", "form:checkCodigo": "on", "form:txtCodigo": codigo, "form:buscar": "Buscar"})
                telemetria = self.motor.telemetria

                # Proteção de carga (Fase 4): com o disjuntor aberto ninguém busca;
                # o limitador global segura o ritmo total de buscas do programa.
                if self.motor.disjuntor.estado != "fechado":
                    self.mudar_estado("contido")
                await self.motor.disjuntor.liberar(self.id, self.motor.stop_event.is_set)
                await self.motor.limitador.adquirir()
                if self.motor.stop_event.is_set() or chave not in alvos:
                    continue

                try:
                    self.mudar_estado("buscando", chave)
                    self.motor.atualizar_alvo(chave, "buscando", manter_se=("vaga", "falha"))
                    self.log(f"🔍 Buscando {codigo}-{turma}...", evento="busca", codigo=codigo, turma=turma)
                    t0 = time.perf_counter()
                    resp = await asyncio.wait_for(
                        self.client.post(self.urls["matricula_extra"], data=payload),
                        timeout=self.motor.timeout_req + 2,
                    )
                    t_req = (time.perf_counter() - t0) * 1000
                    self.log(f"↳ HTTP {resp.status_code}, {len(resp.text)} bytes recebidos", logging.DEBUG,
                             evento="resposta_http", http_status=resp.status_code, latencia_ms=round(t_req))
                    self.contadores["buscas"] += 1
                    self.ultima_latencia_ms = t_req
                    telemetria.registrar_requisicao(t_req)

                    if resp.status_code in STATUS_SOBRECARGA:
                        # Servidor sobrecarregado/fora: relogar só aumentaria a carga. Conta
                        # para o disjuntor e segue; a sessão provavelmente continua válida.
                        self.contadores["sobrecargas"] += 1
                        telemetria.registrar_erro("sobrecarga", f"HTTP {resp.status_code}")
                        self.motor.disjuntor.registrar_falha()
                        self.log(f"🧯 SIGAA sobrecarregado (HTTP {resp.status_code}). Reduzindo o ritmo...", logging.WARNING,
                                 evento="sigaa_sobrecarregado", http_status=resp.status_code)
                        continue
                    self.motor.disjuntor.registrar_sucesso()

                    if resp.status_code != 200 or "autenticacao" in resp.text:
                        self.contadores["sessoes_expiradas"] += 1
                        telemetria.registrar_erro("sessao", f"HTTP {resp.status_code}")
                        self.log("⚠️ Sessão corrompida. Reiniciando...", logging.WARNING,
                                 evento="sessao_expirada", http_status=resp.status_code)
                        await self.relogar()
                        self.payloads_base.clear()
                        continue

                    self._registrar_sucesso()
                    dados_vaga = self.parse_hot_path(resp.text, codigo, turma)
                    if (not dados_vaga and "javax.faces.ViewState" not in resp.text
                            and RE_MANUTENCAO.search(resp.text[:20000])):
                        # Sugestão 090: página de manutenção não é "sem vagas" — conta como
                        # SIGAA indisponível (disjuntor + alerta) e não mexe no estado da disciplina.
                        # Só vale para páginas SEM formulário JSF: a página normal de busca
                        # sempre tem ViewState, então um texto parecido nela nunca dispara isto.
                        self.contadores["manutencao"] += 1
                        telemetria.registrar_erro("sobrecarga", "página de manutenção do SIGAA")
                        self.motor.disjuntor.registrar_falha()
                        self.motor.alertas.registrar_manutencao()
                        self.log("🚧 O SIGAA respondeu com uma página de manutenção/indisponibilidade.", logging.WARNING,
                                 evento="sigaa_manutencao", codigo=codigo, turma=turma)
                        continue
                    if not dados_vaga:
                        self.motor.atualizar_alvo(chave, "sem_vagas", vagas=0, leitura=True)
                        telemetria.registrar_vagas(chave, 0)
                        self.log(f"📉 Sem vagas ({t_req:.0f}ms).", evento="sem_vagas", codigo=codigo, turma=turma,
                                 latencia_ms=round(t_req))
                        continue

                    t_vaga = time.perf_counter()
                    self.contadores["vagas_vistas"] += 1
                    self.motor.atualizar_alvo(chave, "vaga", vagas=dados_vaga["vagas"], leitura=True, vaga_vista=True)
                    telemetria.registrar_vagas(chave, dados_vaga["vagas"])
                    self.log(f"🚨 VAGA DETECTADA ({t_req:.0f}ms) -> {codigo}-{turma} ({dados_vaga['vagas']} vaga(s))!", logging.WARNING,
                             evento="vaga_detectada", codigo=codigo, turma=turma, vagas=dados_vaga["vagas"], latencia_ms=round(t_req))
                    self.motor.emitir("vaga_detectada", {"codigo": codigo, "turma": turma, "vagas": dados_vaga["vagas"]})

                    if self.motor.modo == "monitoramento":
                        # Modo somente monitoramento (seção 11 do pedido): registra e notifica,
                        # mas NUNCA tenta reservar a vaga. Continua monitorando a mesma disciplina
                        # em vez de removê-la — o objetivo aqui é acompanhar mudanças, não agir.
                        continue

                    if locks[chave].locked():
                        self.log("🔒 Outro worker já está atirando. Abortando fogo amigo.", evento="tiro_duplicado",
                                 codigo=codigo, turma=turma)
                        continue

                    async with locks[chave]:
                        if chave not in alvos:
                            continue

                        self.mudar_estado("tentando", chave)
                        self.contadores["tentativas"] += 1
                        self.motor.atualizar_alvo(chave, "tentando", tentativa=True)
                        self.tentativa = self.motor.abrir_tentativa(self, chave, codigo, turma, t_vaga)
                        self.log(f"🎯 ASSUMINDO O TIRO PARA {codigo}-{turma}!", logging.CRITICAL,
                                 evento="tentativa_iniciada", codigo=codigo, turma=turma, tentativa_id=self.tentativa["id"])
                        self.payloads_base[id_depto]["javax.faces.ViewState"] = dados_vaga["viewstate"]

                        try:
                            resultado = await self.efetivar_matricula(codigo, turma, dados_vaga, self.payloads_base[id_depto])
                        except BaseException:
                            self.motor.fechar_tentativa(self, "ERRO")
                            raise
                        self.motor.fechar_tentativa(self, resultado)

                        if resultado == "SUCESSO":
                            if self.motor.dry_run:
                                self.log(f"🧪 DRY RUN SUCESSO: Matrícula Simulada em {codigo}-{turma}.", logging.CRITICAL,
                                         evento="matricula_sucesso", codigo=codigo, turma=turma, dry_run=True)
                            else:
                                self.log(f"🎉 SUCESSO ABSOLUTO! Matrícula confirmada em {codigo}-{turma}.", logging.CRITICAL,
                                         evento="matricula_sucesso", codigo=codigo, turma=turma, dry_run=False)
                            self.motor.atualizar_alvo(chave, "simulada" if self.motor.dry_run else "matriculada")
                            self.motor.emitir("matricula_sucesso", {"codigo": codigo, "turma": turma, "dry_run": self.motor.dry_run})
                            alvos.pop(chave, None)
                            self.motor.dispensar_grupo(chave)
                        elif resultado == "ERRO_REGRA":
                            self.log(f"🛑 REMOVIDO: A UnB bloqueou {codigo}-{turma} (Pré-req/Choque). Parando de buscar essa matéria.", logging.ERROR,
                                     evento="matricula_bloqueada", codigo=codigo, turma=turma)
                            self.motor.atualizar_alvo(chave, "bloqueada")
                            self.motor.emitir("matricula_bloqueada", {"codigo": codigo, "turma": turma})
                            alvos.pop(chave, None)
                        else:
                            self.log("❌ Falha técnica/desafio. Retornando à busca contínua.", logging.ERROR,
                                     evento="matricula_falha", codigo=codigo, turma=turma)
                            self.motor.telemetria.registrar_erro("confirmacao", f"{codigo}-{turma}")
                            self.motor.atualizar_alvo(chave, "falha")
                            self.motor.emitir("matricula_falha", {"codigo": codigo, "turma": turma})
                            self.payloads_base.pop(id_depto, None)

                except (httpx.TimeoutException, asyncio.TimeoutError):
                    self.motor.disjuntor.registrar_falha()
                    self.contadores["timeouts"] += 1
                    self.motor.telemetria.registrar_requisicao(None)
                    self.motor.telemetria.registrar_erro("timeout", f"W{self.id}")
                    self.mudar_estado("reiniciando")
                    self.log("⏳ Timeout (Socket Preso). Ressuscitando worker...", logging.WARNING, evento="timeout")
                    await self.resetar_cliente()
                    await self.relogar()
                except httpx.RequestError as e:
                    self.motor.disjuntor.registrar_falha()
                    self.contadores["falhas_rede"] += 1
                    self.motor.telemetria.registrar_requisicao(None)
                    self.motor.telemetria.registrar_erro("rede", type(e).__name__)
                    self.mudar_estado("reiniciando")
                    self.log(f"🔌 Falha de rede ({type(e).__name__}). Ressuscitando worker...", logging.WARNING,
                             evento="falha_rede", motivo=type(e).__name__)
                    await self.resetar_cliente()
                    await self.relogar()
                except Exception as e:
                    self.contadores["erros_criticos"] += 1
                    self.motor.telemetria.registrar_requisicao(None)
                    self.motor.telemetria.registrar_erro("critico", repr(e))
                    self.mudar_estado("reiniciando")
                    self.log(f"💥 Erro crítico inesperado: {repr(e)}", logging.ERROR, evento="erro_critico")
                    self.motor.emitir("erro_critico", {"worker": self.id, "erro": repr(e)})
                    await self.resetar_cliente()
                    await self.relogar()

            await asyncio.sleep(self.motor.intervalo_busca)

    async def _enviar_confirmacao_real(self, action_url: str, campos_conf: dict):
        """
        Único ponto de todo o programa que efetivamente confirma uma matrícula
        de verdade (o POST que produz efeito definitivo no SIGAA).

        Existe separado de `efetivar_matricula` de propósito, como uma segunda
        trava independente do `if self.motor.dry_run` que já existe antes desta
        chamada: mesmo que esse método venha a ser chamado por engano de algum
        outro lugar no futuro (ex: um refactor que esqueça o `if`), ele se
        recusa a rodar em modo DRY RUN em vez de depender só daquele `if` mais
        um rótulo visual na tela.
        """
        if self.motor.dry_run:
            raise RuntimeError(
                "Bloqueado por segurança: tentativa de enviar confirmação REAL de matrícula "
                "com DRY RUN ativo. Isso indica um bug — nunca deveria acontecer."
            )
        return await self.client.post(action_url, data=campos_conf)

    # --- 4. A CONFIRMAÇÃO BLINDADA (HTML ATTRIBUTES PARSER) ---
    async def efetivar_matricula(self, codigo: str, turma: str, dados_vaga: dict, payload_busca: dict) -> str:
        self.log("Enviando POST de Seleção...")
        cred = self.motor.credenciais

        payload_selecao = payload_busca.copy()
        payload_selecao.update({dados_vaga["link_id"]: dados_vaga["link_id"], "idTurma": dados_vaga["idTurma"], "javax.faces.ViewState": dados_vaga["viewstate"]})
        payload_selecao.pop("form:buscar", None)

        resp_sel = await self.client.post(self.urls["matricula_extra"], data=payload_selecao)
        self._etapa("selecao_enviada")

        if "btnConfirmar" not in resp_sel.text and "confirmaSenha" not in resp_sel.text:
            self.log("❌ Tela de confirmação não detectada.", logging.ERROR, evento="confirmacao_nao_detectada",
                     codigo=codigo, turma=turma)
            self._debug_dump(resp_sel.text, f"selecao_falha_{codigo}")
            return "FALHA"

        self._etapa("tela_confirmacao")
        self.log("Identificando atributos HTML para preenchimento de segurança...")
        soup = BeautifulSoup(resp_sel.text, "html.parser")

        form_tag = soup.find("form", id=re.compile(r"j_id_jsp"))
        if not form_tag:
            for f in soup.find_all("form"):
                if f.find("input", attrs={"name": re.compile(r"btnConfirmar", re.I)}):
                    form_tag = f
                    break

        if not form_tag:
            self.log("❌ Form de confirmação não encontrado!", logging.ERROR)
            return "FALHA"

        campos_conf = {}

        for inp in form_tag.find_all("input", type="hidden"):
            nome = inp.get("name")
            if nome:
                campos_conf[nome] = inp.get("value", "")

        form_id = form_tag.get("id", "")
        if form_id:
            campos_conf[form_id] = form_id

        tag_vs = soup.find("input", attrs={"name": "javax.faces.ViewState"})
        if tag_vs:
            campos_conf["javax.faces.ViewState"] = tag_vs.get("value", "")

        for inp in form_tag.find_all("input"):
            nome = inp.get("name", "")
            tipo = inp.get("type", "text").lower()

            if not nome or tipo in ["hidden", "submit", "button", "reset"]:
                continue

            titulo = inp.get("title", "").lower()
            onkeypress = inp.get("onkeypress", "")

            if tipo == "password" or "senha" in nome.lower():
                campos_conf[nome] = cred.senha
                self.log(f"🔑 Senha mapeada: {nome}")

            elif tipo in ["text", "tel", "number"]:
                if "nascimento" in titulo or "##/##/####" in onkeypress or nome.endswith(":Data"):
                    campos_conf[nome] = cred.nascimento
                    self.log(f"📅 Data de Nascimento injetada: {nome}")
                elif "cpf" in titulo or "###.###.###-##" in onkeypress or nome.endswith(":cpf"):
                    campos_conf[nome] = cred.cpf_numeros()
                    self.log(f"📄 CPF injetado: {nome}")
                else:
                    opcao = campos_conf.get(f"{form_id}:inputHiddenOpcaoExibir", "")
                    if opcao == "1":
                        campos_conf[nome] = cred.nascimento
                        self.log(f"📅 Data (Fallback Opcao 1): {nome}")
                    elif opcao == "2":
                        campos_conf[nome] = cred.cpf_numeros()
                        self.log(f"📄 CPF (Fallback Opcao 2): {nome}")
                    else:
                        campos_conf[nome] = cred.nascimento
                        self.log(f"⚠️ Campo desconhecido preenchido c/ Data: {nome}")

        btn = form_tag.find("input", attrs={"name": re.compile(r"btnConfirmar", re.I)})
        if btn and btn.get("name"):
            campos_conf[btn["name"]] = btn.get("value", "Confirmar Matrícula")

        if not any("senha" in k.lower() or "password" in k.lower() for k in campos_conf.keys()):
            self.log("❌ Campo senha não encontrado! Abortando payload para evitar bloqueio.", logging.ERROR)
            self._debug_dump(resp_sel.text, f"confirmacao_sem_senha_{codigo}")
            return "FALHA"

        self._etapa("formulario_preenchido")
        raw_action = form_tag.get("action", "")
        action_url = self.urls["sigaa_base"] + raw_action if raw_action.startswith("/") else raw_action if raw_action.startswith("http") else self.urls["confirmacao"]

        if self.motor.dry_run:
            self.log(
                "🔒 DRY RUN ATIVO — o fluxo foi executado até o ponto imediatamente anterior à "
                "confirmação (payload de confirmação montado com sucesso). Nenhuma matrícula foi "
                "confirmada — o POST final NUNCA foi enviado.",
                logging.WARNING,
            )
            self._etapa("dry_run_parado")
            self.motor.emitir("dry_run_interrompido", {"codigo": codigo, "turma": turma, "etapa": "antes_do_post_de_confirmacao"})
            return "SUCESSO"

        self.log("🚀 Disparando o POST Final blindado!")
        resp_conf = await self._enviar_confirmacao_real(action_url, campos_conf)
        self._etapa("confirmacao_enviada")
        txt = resp_conf.text.lower()

        if any(kw in txt for kw in ("sucesso", "matrícula realizada", "matriculado com sucesso", "operação realizada", "turma matriculada")):
            return "SUCESSO"

        erros_fatais = ["pré-requisito", "choque de horário", "limite de crédito", "já encontra-se matriculado", "já está matriculado", "mais de uma turma do componente"]

        soup_err = BeautifulSoup(resp_conf.text, "html.parser")
        errs = soup_err.find_all(class_=re.compile(r"erro|error|alert|warn", re.I))
        msg = ""
        if errs:
            msg = errs[0].get_text(strip=True)[:400]
            self.log(f"❌ O SIGAA respondeu com erro: {msg}", logging.ERROR, evento="resposta_erro_sigaa",
                     codigo=codigo, turma=turma)
        else:
            self.log("⚠️ Resultado inconclusivo.", logging.WARNING)
            self._debug_dump(resp_conf.text, f"confirmacao_inconclusiva_{codigo}")

        regra = any(kw in txt for kw in erros_fatais)
        if not regra:
            # Sugestão 092: nome e explicação para o erro; decisões novas só na direção
            # segura (parar). A mensagem classificada é a do ELEMENTO DE ERRO, não a página.
            classe = classificar_resposta_confirmacao(msg)
            self.log(f"🔎 Resposta do SIGAA classificada como '{classe['categoria']}': {classe['explicacao']}",
                     logging.WARNING, evento="classificacao_resposta", codigo=codigo, turma=turma, motivo=classe["categoria"])
            if classe["decisao"] == "parar":
                self.motor.encerrar_por_seguranca(classe["categoria"], classe["explicacao"])
        return "ERRO_REGRA" if regra else "FALHA"


class MotorMatricula:
    """
    Maestro que orquestra os workers — equivalente ao main()/start_worker() da
    v4.0, encapsulado para poder ser iniciado e parado pela GUI/terminal
    várias vezes na mesma execução do programa.
    """

    def __init__(
        self,
        credenciais: CredenciaisSigaa,
        disciplinas: List[List],  # [[codigo, turma, id_departamento], ...]
        num_workers: int = 20,
        intervalo_busca: float = 0.3,
        timeout_req: int = 10,
        dry_run: bool = True,
        agendar_inicio: Optional[str] = None,
        modo: str = "matricula",
        urls: Optional[Dict[str, str]] = None,
        logger: Optional[logging.Logger] = None,
        on_evento: Optional[EventoCallback] = None,
        historico: Optional[Dict[str, Any]] = None,
        protecao: Optional[Dict[str, Any]] = None,
        agendar_fim: Optional[str] = None,
        janela: Optional[Dict[str, Any]] = None,
        relogio_sigaa: bool = False,
        verificacao_previa: bool = False,
        alertas: Optional[Dict[str, Any]] = None,
        resumo_intervalo_horas: float = 0,
        supervisor_seg: Optional[float] = None,
        transporte: Optional[Any] = None,
        demo: bool = False,
    ):
        self.credenciais = credenciais
        self.num_workers = num_workers
        self.intervalo_busca = intervalo_busca
        self.timeout_req = timeout_req
        self.dry_run = dry_run
        self.agendar_inicio = agendar_inicio
        self.modo = modo  # "matricula" | "monitoramento"
        # Seção 79: URLs sobrescrevíveis via Configurações Avançadas; por padrão,
        # são exatamente as mesmas hardcoded da v4.0 (URLS_PADRAO) — só mudam se
        # o usuário explicitamente customizar algo em `urls`.
        self.urls: Dict[str, str] = {**URLS_PADRAO, **(urls or {})}
        self.log = logger or logging.getLogger("sniper")
        self._on_evento = on_evento or _callback_nulo

        # Cada item: [codigo, turma, id_departamento] (formato da v4.0) e, opcionalmente,
        # grupo e prioridade (Fase 4). O dicionário de alvos continua só com os 3 primeiros.
        self.alvos_ativos: Dict[str, List] = {f"{d[0]}-{d[1]}": list(d[:3]) for d in disciplinas}
        self.meta_alvos: Dict[str, Dict[str, str]] = {
            f"{d[0]}-{d[1]}": {"grupo": (d[3] if len(d) > 3 else "") or "", "prioridade": (d[4] if len(d) > 4 else "") or "normal"}
            for d in disciplinas}
        self.locks_alvos: Dict[str, asyncio.Lock] = {chave: asyncio.Lock() for chave in self.alvos_ativos}
        self.stop_event = asyncio.Event()
        self._workers: List[SigaaWorker] = []
        # ID de execução (seção 24 do pedido de continuação): identifica todos os
        # logs desta execução específica, útil para comparar testes diferentes.
        self.execucao_id = f"{datetime.now().strftime('%Y-%m-%d')}-{uuid.uuid4().hex[:6]}"

        # Observabilidade (Fase 2). Só registra; nunca decide nada.
        self.telemetria = Telemetria()
        agora = time.time()
        self.estado_alvos: Dict[str, Dict[str, Any]] = {
            chave: {"chave": chave, "codigo": d[0], "turma": d[1], "departamento": d[2], "estado": "aguardando",
                    "desde": agora, "vagas": None, "ultima_leitura": None, "buscas": 0, "vagas_vistas": 0, "tentativas": 0}
            for chave, d in self.alvos_ativos.items()
        }
        self.fase = "preparando"  # preparando → agendado → logando → monitorando → encerrado
        self.agendado_para: Optional[str] = None
        self.inicio_ts: Optional[float] = None
        self.fim_ts: Optional[float] = None
        self.motivo_fim: Optional[str] = None
        self.resumo: Optional[Dict[str, Any]] = None
        # Histórico local (Fase 3): gravado uma vez, no encerramento.
        self.cfg_historico = {"ativo": True, "dias_retencao": 180, **(historico or {})}
        # Proteção de carga (Fase 4: 071, 073, 039).
        self.cfg_protecao = {"limite_req_por_seg": 0, "logins_simultaneos": 0, "disjuntor": True, **(protecao or {})}
        self.limitador = LimitadorTaxa(self.cfg_protecao["limite_req_por_seg"])
        self.disjuntor = Disjuntor(ativo=bool(self.cfg_protecao["disjuntor"]), ao_mudar=self._disjuntor_mudou)
        self._sem_login: Optional[asyncio.Semaphore] = None  # criado dentro do loop, em executar()
        # Pausa (036), janela/término (035), relógio do SIGAA (038), verificação prévia (040).
        self.pausado = False
        self.motivo_pausa: Optional[str] = None
        self._liberado: Optional[asyncio.Event] = None
        self.agendar_fim = agendar_fim
        self.janela = janela or {}
        self.relogio_sigaa = relogio_sigaa
        self.verificacao_previa = verificacao_previa
        self.offset_relogio_seg: Optional[float] = None
        self.motivo_forcado: Optional[str] = None
        # Observabilidade (Fase 5): tentativas (059), supervisor (057), alertas (058/090), resumo (052).
        self.tentativas: deque = deque(maxlen=50)
        self._tarefas_workers: Dict[int, asyncio.Task] = {}
        self.reinicios_workers: Counter = Counter()
        # Um worker é considerado travado depois de muito mais tempo do que qualquer
        # espera legítima (timeout da requisição + espera máxima após falhas).
        self.supervisor_seg = supervisor_seg or max(90.0, 4 * (timeout_req + 2), SigaaWorker.ESPERA_FALHA_MAX_SEG * 2)
        self.intervalo_supervisor = 5.0
        self.alertas = AvaliadorAlertas(alertas)
        self.resumo_intervalo_horas = float(resumo_intervalo_horas or 0)
        self.aguardar_notificacoes: Optional[Callable[[float], Any]] = None  # definido pela fábrica
        # Modo demonstração (Fase 6, 077): as requisições vão para um SIGAA simulado
        # (transporte local) e nada é gravado no histórico nem nos relatórios.
        self.demo = demo
        self.opcoes_cliente: Dict[str, Any] = {"transport": transporte} if transporte is not None else {}

    def emitir(self, tipo: str, dados: dict) -> None:
        """Notifica quem estiver ouvindo (GUI/notificações). Nunca deixa uma falha do
        callback derrubar o motor — notificação é sempre secundária ao monitoramento."""
        try:
            self._on_evento(tipo, dados)
        except Exception:
            self.log.warning(f"Callback de evento falhou para '{tipo}' (ignorado, monitor continua)")

    def parar(self) -> None:
        self.stop_event.set()

    # ── Observabilidade (Fase 2) ──────────────────────────────────────────

    # ── Fase 4: pausa, janela, grupos, prioridade, alvos em execução ─────

    def pausar(self, motivo: str = "usuario") -> bool:
        if self.pausado:
            return False
        self.pausado, self.motivo_pausa = True, motivo
        if self._liberado is not None:
            self._liberado.clear()
        if motivo == "janela":
            texto = f"🌙 Fora da janela de execução ({descrever_janela(self.janela)}): buscas pausadas até o próximo horário."
        else:
            texto = "⏸️ Execução pausada pelo usuário (sessões mantidas; nenhuma busca até retomar)."
        self._log_main(logging.INFO, texto, evento="execucao_pausada", motivo=motivo)
        self.emitir("execucao_pausada", {"motivo": motivo})
        if motivo == "usuario":
            from app.core import auditoria
            auditoria.registrar("execucao_pausada", execucao_id=self.execucao_id)
        return True

    def retomar(self, motivo: str = "usuario") -> bool:
        """O usuário não "fura" a janela de execução: fora dela, a retomada é automática."""
        if not self.pausado or (self.motivo_pausa == "janela" and motivo != "janela"):
            return False
        self.pausado, self.motivo_pausa = False, None
        if self._liberado is not None:
            self._liberado.set()
        self._log_main(logging.INFO, "▶️ Execução retomada.", evento="execucao_retomada", motivo=motivo)
        self.emitir("execucao_retomada", {"motivo": motivo})
        if motivo == "usuario":
            from app.core import auditoria
            auditoria.registrar("execucao_retomada", execucao_id=self.execucao_id)
        return True

    async def aguardar_se_pausado(self, worker: "SigaaWorker") -> None:
        while self.pausado and not self.stop_event.is_set():
            worker.mudar_estado("pausado")
            if self._liberado is None:  # pausa pedida antes de o loop criar o evento
                await asyncio.sleep(0.2)
                continue
            try:
                await asyncio.wait_for(self._liberado.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass  # confere de novo o pedido de parada

    def prioridade_de(self, chave: str) -> str:
        return self.meta_alvos.get(chave, {}).get("prioridade", "normal")

    def alvos_em_ordem(self) -> List:
        ordem = {"alta": 0, "normal": 1, "baixa": 2}
        return sorted(list(self.alvos_ativos.items()), key=lambda item: ordem.get(self.prioridade_de(item[0]), 1))

    def dispensar_grupo(self, chave_garantida: str) -> List[str]:
        """Sugestão 033: garantida uma turma do grupo, as alternativas saem da busca."""
        grupo = self.meta_alvos.get(chave_garantida, {}).get("grupo")
        if not grupo:
            return []
        outras = [c for c, m in self.meta_alvos.items()
                  if c != chave_garantida and m.get("grupo") == grupo and c in self.alvos_ativos]
        for c in outras:
            self.alvos_ativos.pop(c, None)
            alvo = self.estado_alvos.get(c)
            if alvo:
                alvo["estado"], alvo["desde"] = "dispensada", time.time()
        if outras:
            self._log_main(logging.INFO, f"🧩 Grupo '{grupo}': {chave_garantida} garantida — dispensando {', '.join(outras)}.",
                           evento="grupo_dispensado", motivo=grupo)
            self.emitir("grupo_dispensado", {"grupo": grupo, "garantida": chave_garantida, "dispensadas": outras})
        return outras

    def adicionar_alvo(self, item: List) -> None:
        """Sugestão 037: nova disciplina entra na busca sem reiniciar (roda no loop do motor)."""
        chave = f"{item[0]}-{item[1]}"
        self.meta_alvos[chave] = {"grupo": (item[3] if len(item) > 3 else "") or "", "prioridade": (item[4] if len(item) > 4 else "") or "normal"}
        if chave in self.alvos_ativos:
            return
        self.alvos_ativos[chave] = list(item[:3])
        self.locks_alvos.setdefault(chave, asyncio.Lock())
        self.estado_alvos[chave] = {"chave": chave, "codigo": item[0], "turma": item[1], "departamento": item[2],
                                    "estado": "buscando" if self.fase == "monitorando" else "aguardando", "desde": time.time(),
                                    "vagas": None, "ultima_leitura": None, "buscas": 0, "vagas_vistas": 0, "tentativas": 0}
        self._log_main(logging.INFO, f"➕ {chave} adicionada à execução em andamento.", evento="alvo_adicionado",
                       codigo=item[0], turma=item[1])

    def remover_alvo(self, chave: str) -> None:
        """Sai da busca; uma tentativa de matrícula já em curso termina normalmente."""
        if self.alvos_ativos.pop(chave, None) is None:
            return
        alvo = self.estado_alvos.get(chave)
        if alvo and alvo["estado"] not in ESTADOS_FINAIS_ALVO:
            alvo["estado"], alvo["desde"] = "removida", time.time()
        self._log_main(logging.INFO, f"➖ {chave} removida da execução em andamento.", evento="alvo_removido")

    def encerrar_por_seguranca(self, motivo: str, explicacao: str) -> None:
        if self.motivo_forcado:
            return
        self.motivo_forcado = motivo
        self._log_main(logging.ERROR, f"🛑 Execução parada por segurança: {explicacao}", evento="parada_seguranca", motivo=motivo)
        self.emitir("parada_seguranca", {"motivo": motivo, "explicacao": explicacao})
        self.stop_event.set()

    # ── Fase 5: tentativas, supervisor, alertas e resumo periódico ─────────

    def abrir_tentativa(self, worker: "SigaaWorker", chave: str, codigo: str, turma: str, t_vaga: float) -> Dict[str, Any]:
        tentativa = {"id": uuid.uuid4().hex[:8], "chave": chave, "codigo": codigo, "turma": turma, "worker": f"W{worker.id}",
                     "inicio": time.time(), "_t0": time.perf_counter(), "_t_vaga": t_vaga,
                     "reacao_ms": round((time.perf_counter() - t_vaga) * 1000), "etapas": [], "resultado": None,
                     "total_ms": None, "dry_run": self.dry_run, "dump": None}
        self.tentativas.append(tentativa)
        return tentativa

    def fechar_tentativa(self, worker: "SigaaWorker", resultado: str) -> None:
        t = worker.tentativa
        worker.tentativa = None
        if not t:
            return
        t["resultado"] = resultado
        t["total_ms"] = round((time.perf_counter() - t["_t0"]) * 1000)
        t["desde_vaga_ms"] = round((time.perf_counter() - t["_t_vaga"]) * 1000)
        worker.log(f"🏁 Tentativa {t['id']} ({t['chave']}): {resultado} em {t['total_ms']} ms "
                   f"({t['desde_vaga_ms']} ms desde a vaga vista).", evento="tentativa_concluida", tentativa_id=t["id"],
                   codigo=t["codigo"], turma=t["turma"], duracao_ms=t["total_ms"], motivo=resultado)

    def tentativas_publicas(self) -> List[Dict[str, Any]]:
        return [{k: v for k, v in t.items() if not k.startswith("_")} | {"etapas": [dict(e) for e in t["etapas"]]}
                for t in list(self.tentativas)]

    def _worker_travado(self, worker: "SigaaWorker", agora: float) -> bool:
        # Nunca mexe num worker no meio de uma tentativa de matrícula, pausado,
        # contido pela proteção de carga ou em espera legítima após falhas.
        if worker.estado in ("iniciando", "fila_login", "tentando", "pausado", "contido", "aguardando", "encerrado") or worker.tentativa:
            return False
        return agora - max(worker.ultimo_batimento, worker.ultimo_progresso) > self.supervisor_seg

    async def _supervisionar(self) -> None:
        """Sugestão 057 + 058/052: recria workers travados, avalia alertas e envia o resumo periódico."""
        proximo_resumo = time.time() + self.resumo_intervalo_horas * 3600 if self.resumo_intervalo_horas > 0 else None
        try:
            while not self.stop_event.is_set():
                await asyncio.sleep(self.intervalo_supervisor)
                agora = time.time()
                if self.fase == "monitorando" and not self.pausado and self.disjuntor.estado == "fechado":
                    for worker in list(self._workers):
                        if self._worker_travado(worker, agora):
                            self._reiniciar_worker(worker)
                try:
                    for mudanca in self.alertas.avaliar(self.snapshot(), agora):
                        ativo = mudanca["estado"] == "ativo"
                        self._log_main(logging.WARNING if ativo else logging.INFO,
                                       f"{'🔔' if ativo else '✅'} {mudanca['titulo'] if ativo else 'Alerta resolvido'}: {mudanca['texto']}",
                                       evento="alerta_limiar", motivo=mudanca["regra"])
                        self.emitir("alerta_limiar", dict(mudanca))
                except Exception as e:  # alerta é secundário: nunca derruba o supervisor
                    self.log.warning(f"Avaliação de alertas falhou ({type(e).__name__}).", extra={"worker_id": "MAIN"})
                if proximo_resumo and agora >= proximo_resumo and self.fase == "monitorando":
                    proximo_resumo = agora + self.resumo_intervalo_horas * 3600
                    self.emitir("resumo_periodico", {"texto": texto_resumo_periodico(self.snapshot())})
        except asyncio.CancelledError:
            pass

    def _reiniciar_worker(self, worker: "SigaaWorker") -> None:
        tarefa = self._tarefas_workers.get(worker.id)
        self.reinicios_workers[worker.id] += 1
        n = self.reinicios_workers[worker.id]
        if n > 5:
            if n == 6:
                self._log_main(logging.ERROR, f"🧟 W{worker.id} travou de novo; depois de 5 reinícios ele fica parado "
                               "(os outros workers continuam).", evento="worker_reiniciado", motivo="limite")
            return
        parado = round(time.time() - max(worker.ultimo_batimento, worker.ultimo_progresso))
        self._log_main(logging.WARNING, f"🧟 W{worker.id} sem progresso há {parado}s ({ESTADOS_WORKER.get(worker.estado, worker.estado)}). "
                       "Recriando o worker...", evento="worker_reiniciado", espera_seg=parado)
        self.emitir("worker_reiniciado", {"worker": worker.id, "parado_seg": parado})
        worker.mudar_estado("encerrado")  # não é reiniciado duas vezes enquanto o cancelamento acontece
        if tarefa and not tarefa.done():
            tarefa.cancel()
        if worker in self._workers:
            self._workers.remove(worker)
        self._tarefas_workers[worker.id] = asyncio.create_task(self._start_worker(worker.id, 0.0))

    async def _controlar_horarios(self) -> None:
        """Horário de término (035) e janela diária: fora dela, pausa; dentro, retoma."""
        fim = None
        if self.agendar_fim:
            try:
                fim = datetime.strptime(self.agendar_fim, "%d/%m/%Y %H:%M:%S")
            except ValueError:
                self._log_main(logging.ERROR, f"❌ Horário de término inválido: {self.agendar_fim!r} (ignorado).")
        try:
            while not self.stop_event.is_set():
                agora = datetime.now()
                if fim and agora >= fim:
                    self.motivo_forcado = self.motivo_forcado or "fim_agendado"
                    self._log_main(logging.INFO, f"⏰ Horário de término atingido ({self.agendar_fim}). Encerrando.", evento="fim_agendado")
                    self.stop_event.set()
                    return
                if self.janela.get("ativa") and self.fase in ("logando", "monitorando"):
                    dentro = dentro_da_janela(self.janela, agora)
                    if not dentro and not self.pausado:
                        self.pausar("janela")
                    elif dentro and self.pausado and self.motivo_pausa == "janela":
                        self.retomar("janela")
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass

    async def _verificacao_previa_das_disciplinas(self) -> bool:
        """Sugestão 040: antes de soltar os workers, UM worker confere login,
        departamentos e se cada disciplina/turma aparece na tabela. Devolve False
        só quando o login foi recusado (não adianta continuar); nos outros casos
        mostra o resultado e segue."""
        self.fase = "verificando"
        w = SigaaWorker(0, self)
        w.log_prefix, w.rotulo_log = "[VERIFICAÇÃO]", "PREVIA"
        resultados = []
        try:
            if not await w.realizar_login():
                if w.motivo_falha_login == "recusado":
                    self.motivo_forcado = "login_recusado"
                    self._log_main(logging.ERROR, "❌ Verificação prévia: o SIGAA recusou o login. Confira matrícula e senha — "
                                   "a execução não foi iniciada para não insistir com uma senha errada.", evento="verificacao_previa",
                                   motivo="login_recusado")
                    self.emitir("verificacao_previa", {"login": "recusado", "resultados": []})
                    return False
                self._log_main(logging.WARNING, "⚠️ Verificação prévia: sem resposta do SIGAA no login — seguindo sem verificar.",
                               evento="verificacao_previa", motivo="sem_resposta")
                return True
            for chave, (codigo, turma, id_depto) in list(self.alvos_ativos.items()):
                if self.stop_event.is_set():
                    break
                if id_depto not in w.payloads_base and not await w.teleportar_departamento(id_depto):
                    resultado, texto = "departamento_indisponivel", f"departamento {id_depto} indisponível (fora do período ou código errado)"
                else:
                    await self.limitador.adquirir()
                    payload = {**w.payloads_base[id_depto], "form": "form", "form:checkCodigo": "on", "form:txtCodigo": codigo, "form:buscar": "Buscar"}
                    resp = await w.client.post(self.urls["matricula_extra"], data=payload)
                    info = inspecionar_turma(resp.text, codigo, turma)
                    if info["turma_encontrada"]:
                        resultado, texto = "ok", f"encontrada ({info['vagas']} vaga(s) agora)"
                    elif info["disciplina_encontrada"]:
                        vistas = ", ".join(info["turmas_vistas"]) or "nenhuma"
                        resultado, texto = "turma_nao_encontrada", f"a disciplina existe, mas a turma {turma} não (turmas vistas: {vistas})"
                    else:
                        resultado, texto = "disciplina_nao_encontrada", "a disciplina não aparece na lista deste departamento (código ou departamento errado?)"
                alvo = self.estado_alvos.get(chave)
                if alvo is not None:
                    alvo["verificacao"] = {"resultado": resultado, "texto": texto}
                resultados.append({"chave": chave, "resultado": resultado, "texto": texto})
                nivel = logging.INFO if resultado == "ok" else logging.WARNING
                self._log_main(nivel, f"{'✅' if resultado == 'ok' else '⚠️'} Verificação prévia — {chave}: {texto}.",
                               evento="verificacao_previa", codigo=codigo, turma=turma, motivo=resultado)
            self.emitir("verificacao_previa", {"login": "ok", "resultados": resultados})
            return True
        except Exception as e:  # a verificação é um extra: nunca impede a execução por falha dela mesma
            self._log_main(logging.WARNING, f"⚠️ Verificação prévia não concluída ({type(e).__name__}) — seguindo sem ela.",
                           evento="verificacao_previa", motivo="erro")
            return True
        finally:
            await w.fechar()

    def _disjuntor_mudou(self, estado: str, espera: float) -> None:
        if estado == "aberto":
            self._log_main(logging.WARNING, f"🧯 SIGAA instável: buscas pausadas por {espera:.0f}s para não sobrecarregá-lo. "
                           "Depois, um worker faz uma busca de teste.", evento="disjuntor_aberto", espera_seg=espera)
            self.emitir("disjuntor_aberto", {"espera_seg": espera})
        elif estado == "fechado":
            self._log_main(logging.INFO, "✅ SIGAA respondendo de novo: buscas retomadas normalmente.", evento="disjuntor_fechado")
            self.emitir("disjuntor_fechado", {})

    def _log_main(self, level: int, msg: str, **campos) -> None:
        self.log.log(level, msg, extra={"worker_id": "MAIN", "campos": {"execucao_id": self.execucao_id, **campos}})

    def atualizar_alvo(self, chave: str, estado: Optional[str] = None, manter_se=(), vagas: Optional[int] = None,
                       leitura: bool = False, vaga_vista: bool = False, tentativa: bool = False) -> None:
        """Atualiza o estado de uma disciplina (sugestão 019). Estados finais
        (matriculada/simulada/bloqueada) nunca são sobrescritos; `manter_se`
        evita que "buscando" apague um estado mais informativo."""
        alvo = self.estado_alvos.get(chave)
        if alvo is None or alvo["estado"] in ESTADOS_FINAIS_ALVO:
            return
        if estado and estado != alvo["estado"] and alvo["estado"] not in manter_se:
            alvo["estado"] = estado
            alvo["desde"] = time.time()
        if vagas is not None:
            alvo["vagas"] = vagas
        if leitura:
            alvo["ultima_leitura"] = time.time()
            alvo["buscas"] += 1
        if vaga_vista:
            alvo["vagas_vistas"] += 1
        if tentativa:
            alvo["tentativas"] += 1

    def _progresso_login(self) -> Dict[str, int]:
        prontos = sum(1 for w in list(self._workers) if w.estado not in ("iniciando", "logando") or w.contadores["buscas"])
        return {"logados": prontos, "total": self.num_workers}

    def snapshot(self) -> Dict[str, Any]:
        """Cópia do estado atual para as interfaces (lida de outra thread; só
        copia valores simples). Inclui disciplinas, workers, fase e telemetria."""
        agora = time.time()
        workers = []
        for w in list(self._workers):
            workers.append({
                "id": f"W{w.id}", "estado": w.estado, "estado_rotulo": ESTADOS_WORKER.get(w.estado, w.estado),
                "alvo": w.alvo_atual,
                "ocioso_seg": None if w.estado == "encerrado" else round(agora - w.ultimo_progresso, 1),
                "latencia_ms": round(w.ultima_latencia_ms) if w.ultima_latencia_ms is not None else None,
                "contadores": dict(w.contadores),
            })
        totais: Counter = Counter()
        for w in workers:
            totais.update(w["contadores"])
        alvos = []
        for a in list(self.estado_alvos.values()):
            copia = dict(a)
            copia["estado_rotulo"] = ESTADOS_ALVO.get(a["estado"], a["estado"])
            copia["ativo"] = a["chave"] in self.alvos_ativos
            alvos.append(copia)
        for a in alvos:
            a.update(self.meta_alvos.get(a["chave"], {}))
        return {
            "execucao_id": self.execucao_id, "modo": self.modo, "dry_run": self.dry_run,
            "pausado": self.pausado, "motivo_pausa": self.motivo_pausa, "janela": descrever_janela(self.janela),
            "janela_ativa": bool(self.janela.get("ativa")), "agendar_fim": self.agendar_fim,
            "offset_relogio_seg": self.offset_relogio_seg,
            "fase": self.fase, "agendado_para": self.agendado_para, "progresso_login": self._progresso_login(),
            "inicio": self.inicio_ts, "fim": self.fim_ts, "motivo_fim": self.motivo_fim,
            "num_workers": self.num_workers, "intervalo_busca": self.intervalo_busca,
            "disjuntor": {"estado": self.disjuntor.estado, "reabre_em_seg": round(self.disjuntor.segundos_para_reabrir()),
                          "aberturas": self.disjuntor.aberturas},
            "limite_req_por_seg": self.limitador.por_segundo,
            "alvos": alvos, "workers": workers, "contadores": dict(totais),
            "telemetria": self.telemetria.snapshot(),
            "tentativas": self.tentativas_publicas(),
            "alertas": self.alertas.snapshot(),
            "reinicios_workers": sum(self.reinicios_workers.values()),
            "demo": self.demo,
        }

    def gerar_resumo(self) -> Dict[str, Any]:
        """Relatório de encerramento (sugestão 048): o que aconteceu nesta execução."""
        from app.versao import VERSAO_APP
        snap = self.snapshot()
        tel = snap["telemetria"]
        alvos = [{k: a[k] for k in ("chave", "codigo", "turma", "departamento", "estado", "estado_rotulo", "vagas",
                                   "buscas", "vagas_vistas", "tentativas")} for a in snap["alvos"]]
        contagem_estados = Counter(a["estado"] for a in alvos)
        inicio, fim = self.inicio_ts or time.time(), self.fim_ts or time.time()
        return {
            "execucao_id": self.execucao_id, "versao": VERSAO_APP, "modo": self.modo, "dry_run": self.dry_run,
            "inicio": datetime.fromtimestamp(inicio).strftime("%Y-%m-%d %H:%M:%S"),
            "fim": datetime.fromtimestamp(fim).strftime("%Y-%m-%d %H:%M:%S"),
            "duracao_seg": round(fim - inicio, 1), "motivo_fim": self.motivo_fim,
            "configuracao": {"num_workers": self.num_workers, "intervalo_busca": self.intervalo_busca,
                             "timeout_req": self.timeout_req, "agendar_inicio": self.agendar_inicio},
            "alvos": alvos,
            "totais": {
                "requisicoes": tel["requisicoes"], "vagas_vistas": tel["vagas_vistas"],
                "tentativas": snap["contadores"].get("tentativas", 0),
                "matriculadas": contagem_estados["matriculada"], "simuladas": contagem_estados["simulada"],
                "bloqueadas": contagem_estados["bloqueada"], "erros": sum(v["total"] for v in tel["erros"].values()),
            },
            "erros": {c: v["total"] for c, v in tel["erros"].items()},
            "latencia_ms": {k: (round(v) if v is not None else None) for k, v in tel["latencia"].items() if k != "amostras"},
            "contadores": snap["contadores"],
            "tentativas": snap["tentativas"],
            "alertas": snap["alertas"]["historico"],
            "demo": self.demo,
        }

    async def _amostrar_periodicamente(self) -> None:
        """Fecha um ponto da série temporal por segundo (gráficos da Fase 2)."""
        try:
            while True:
                await asyncio.sleep(1.0)
                self.telemetria.amostrar()
        except asyncio.CancelledError:
            self.telemetria.amostrar()

    async def _aguardar_agendamento(self):
        if not self.agendar_inicio:
            return
        try:
            alvo = datetime.strptime(self.agendar_inicio, "%d/%m/%Y %H:%M:%S")
        except ValueError as e:
            self.log.error(f"❌ Erro de configuração na formatação do agendamento: {repr(e)}", extra={"worker_id": "MAIN"})
            return

        if self.relogio_sigaa:
            try:
                medicao = await medir_offset_relogio(self.urls["sigaa_base"] + "/sigaa/public/", fabrica_cliente=httpx.AsyncClient)
                self.offset_relogio_seg = medicao["offset_segundos"]
                # offset > 0: o SIGAA está à frente → o horário alvo chega antes no relógio local.
                alvo = alvo - timedelta(seconds=self.offset_relogio_seg)
                self._log_main(logging.INFO, f"🕒 Agendamento pelo relógio do SIGAA: {descrever_offset(self.offset_relogio_seg)}.",
                               evento="relogio_sigaa", espera_seg=self.offset_relogio_seg)
            except Exception as e:
                self._log_main(logging.WARNING, f"⚠️ Não foi possível medir o relógio do SIGAA ({type(e).__name__}) — "
                               "usando o relógio deste computador.", evento="relogio_sigaa", motivo="falhou")

        espera = (alvo - datetime.now()).total_seconds()
        if espera > 0:
            self.fase = "agendado"
            self.agendado_para = self.agendar_inicio
            self.log.info(f"⏳ Agendamento ativado! Aguardando até {self.agendar_inicio}.", extra={"worker_id": "MAIN"})
            while espera > 0 and not self.stop_event.is_set():
                if espera <= 10 or (espera % 60 < 1):
                    self.log.info(f"⏳ Faltam {int(espera)} segundos.", extra={"worker_id": "MAIN"})
                await asyncio.sleep(min(1.0, espera))
                espera = (alvo - datetime.now()).total_seconds()
            if not self.stop_event.is_set():
                self.log.info("🚀 Horário atingido! Disparando o esquadrão...", extra={"worker_id": "MAIN"})

    async def _start_worker(self, worker_id: int, atraso_inicial: float):
        worker = SigaaWorker(worker_id, self)
        self._workers.append(worker)
        try:
            logado = await worker.realizar_login()
            # Sem resposta do SIGAA (rede/instabilidade): tenta de novo com espera
            # crescente. Login RECUSADO não é repetido — com senha errada, insistir
            # só arriscaria bloquear a conta.
            while not logado and worker.motivo_falha_login == "rede" and not self.stop_event.is_set():
                await worker.esperar_apos_falha("sem resposta do SIGAA no login")
                if self.stop_event.is_set():
                    break
                logado = await worker.realizar_login()
            if logado:
                worker._registrar_sucesso()
                self.log.info(f"[W{worker_id}] Em posição. Offset ({atraso_inicial:.2f}s)...", extra={"worker_id": "MAIN"})
                await asyncio.sleep(atraso_inicial)
                if self.fase == "logando":
                    self.fase = "monitorando"
                await worker.rodar_ciclo()
            elif not self.stop_event.is_set():
                self.log.error(f"[W{worker_id}] Login falhou — worker não iniciado.", extra={"worker_id": "MAIN"})
        except asyncio.CancelledError:
            self.log.info(f"[W{worker_id}] Thread finalizada/cancelada pelo Maestro.", extra={"worker_id": "MAIN"})
        except Exception as e:
            self.log.error(f"[W{worker_id}] Worker engasgou gravemente e abortou a operação: {repr(e)}", extra={"worker_id": "MAIN"})
        finally:
            worker.mudar_estado("encerrado")
            await worker.fechar()

    async def executar(self) -> None:
        """Roda até todas as disciplinas serem processadas ou stop_event ser sinalizado."""
        from app.core.crash_recovery import marcar_execucao_encerrada, marcar_execucao_iniciada

        # Marcador consumido por app/dashboard/metrics.py para não misturar estatísticas
        # desta execução com as de uma execução anterior que tenha ficado no mesmo log.
        self._log_main(logging.INFO, f"SESSAO_INICIADA id={self.execucao_id}" + (" (DEMONSTRAÇÃO — SIGAA simulado)" if self.demo else ""),
                       evento="sessao_iniciada", motivo="demo" if self.demo else None)
        # Seção 54: marca que uma execução está em andamento, para detectar na
        # próxima vez se esta terminou de forma abrupta (queda, crash) — o
        # finally abaixo apaga o marcador em qualquer encerramento controlado.
        marcar_execucao_iniciada(self.modo, self.execucao_id)
        self.inicio_ts = time.time()
        if int(self.cfg_protecao.get("logins_simultaneos") or 0) > 0:
            self._sem_login = asyncio.Semaphore(int(self.cfg_protecao["logins_simultaneos"]))
        amostrador = asyncio.create_task(self._amostrar_periodicamente())
        self._liberado = asyncio.Event()
        if not self.pausado:
            self._liberado.set()
        controle = asyncio.create_task(self._controlar_horarios())
        supervisor = asyncio.create_task(self._supervisionar())

        try:
            titulo = "MODO MATRÍCULA AUTOMÁTICA" if self.modo == "matricula" else "MODO SOMENTE MONITORAMENTO"
            self.log.info("╔════════════════════════════════════════════════════════════╗", extra={"worker_id": "MAIN"})
            self.log.info(f"║     INICIANDO SIGAA SNIPER — {titulo:<32}║", extra={"worker_id": "MAIN"})
            self.log.info("╚════════════════════════════════════════════════════════════╝", extra={"worker_id": "MAIN"})

            if self.modo == "monitoramento":
                self.log.info("👀 Modo monitoramento: nenhuma matrícula será realizada automaticamente.", extra={"worker_id": "MAIN"})
            elif self.dry_run:
                self.log.warning("⚠️  ATENÇÃO: MODO DRY_RUN ATIVADO. AS MATRÍCULAS NÃO SERÃO CONFIRMADAS! ⚠️", extra={"worker_id": "MAIN"})

            if self.verificacao_previa and not await self._verificacao_previa_das_disciplinas():
                self.motivo_fim = self.motivo_forcado or "interrompida"
                return
            await self._aguardar_agendamento()
            if self.stop_event.is_set():
                self.motivo_fim = self.motivo_forcado or "interrompida"
                return
            self.fase = "logando"

            for i in range(self.num_workers):
                self._tarefas_workers[i] = asyncio.create_task(
                    self._start_worker(i, i * (self.intervalo_busca / max(1, self.num_workers))))
            sem_workers = False
            while self.alvos_ativos and not self.stop_event.is_set():
                await asyncio.sleep(1)
                tarefas = list(self._tarefas_workers.values())
                if tarefas and all(t.done() for t in tarefas) and self.alvos_ativos and not self.stop_event.is_set():
                    # Todos os workers encerraram (ex: login recusado) — antes a
                    # execução ficava "em andamento" para sempre sem fazer nada.
                    sem_workers = True
                    break

            if self.motivo_forcado:
                self.motivo_fim = self.motivo_forcado
            elif not self.alvos_ativos:
                self.motivo_fim = "concluida"
                self.log.info("🏆 TODAS AS DISCIPLINAS FORAM PROCESSADAS!", extra={"worker_id": "MAIN"})
            elif sem_workers:
                self.motivo_fim = "sem_workers"
                self.log.error(
                    "❌ Nenhum worker conseguiu continuar (login recusado pelo SIGAA ou falhas seguidas). "
                    "Execução encerrada — confira suas credenciais e rode o Diagnóstico.",
                    extra={"worker_id": "MAIN"},
                )
            else:
                self.motivo_fim = "interrompida"
                self.log.info("🛑 Execução interrompida pelo usuário.", extra={"worker_id": "MAIN"})

            tarefas = list(self._tarefas_workers.values())
            for t in tarefas:
                t.cancel()
            await asyncio.gather(*tarefas, return_exceptions=True)
        except BaseException:
            self.motivo_fim = self.motivo_fim or "erro"
            raise
        finally:
            amostrador.cancel()
            controle.cancel()
            supervisor.cancel()
            await asyncio.gather(amostrador, controle, supervisor, return_exceptions=True)
            self.fim_ts = time.time()
            self.fase = "encerrado"
            self._fechar_estados_transitorios()
            self._finalizar_resumo()
            marcar_execucao_encerrada()
            await self._enviar_resumo_final()

    async def _enviar_resumo_final(self) -> None:
        """Resumo ao encerrar (052) e espera curta para as notificações pendentes
        saírem antes de o loop fechar — antes, um aviso disparado no fim se perdia."""
        try:
            if self.inicio_ts and self.fim_ts and self.fim_ts - self.inicio_ts >= 60:
                snap = self.snapshot()
                self.emitir("execucao_encerrada", {"texto": texto_resumo_periodico(snap, final=True), "motivo": self.motivo_fim})
            if self.aguardar_notificacoes:
                await asyncio.wait_for(self.aguardar_notificacoes(8.0), timeout=10.0)
        except Exception:
            pass

    def _fechar_estados_transitorios(self) -> None:
        """Com a execução encerrada, "Buscando"/"Tentando" não é mais verdade:
        cada disciplina volta ao último resultado conhecido (ou "Aguardando
        login", se nunca houve leitura)."""
        for alvo in self.estado_alvos.values():
            if alvo["estado"] in ("buscando", "tentando"):
                alvo["estado"] = ("aguardando" if alvo["vagas"] is None
                                  else "vaga" if alvo["vagas"] > 0 else "sem_vagas")

    def _finalizar_resumo(self) -> None:
        """Monta e grava o relatório de encerramento. Best-effort: um problema
        aqui nunca pode mascarar o fim normal da execução."""
        try:
            from app.core.relatorios import salvar_relatorio
            self.resumo = self.gerar_resumo()
            t = self.resumo["totais"]
            self._log_main(
                logging.INFO,
                f"📋 Resumo da execução: {self.resumo['duracao_seg']:.0f}s, {t['requisicoes']} buscas, "
                f"{t['vagas_vistas']} vaga(s) vista(s), {t['tentativas']} tentativa(s), {t['erros']} erro(s).",
                evento="execucao_resumo", motivo=self.motivo_fim,
            )
            if self.demo:
                return  # demonstração: não mistura dado simulado com o histórico real
            salvar_relatorio(self.resumo)
            if self.cfg_historico.get("ativo"):
                from app.core.historico import aplicar_retencao, registrar_execucao
                registrar_execucao(self.resumo, self.telemetria.snapshot())
                aplicar_retencao(int(self.cfg_historico.get("dias_retencao") or 0))
        except Exception as e:
            self.log.warning(f"Não foi possível gerar o resumo da execução ({type(e).__name__}).", extra={"worker_id": "MAIN"})
