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

Ver docs/ARQUITETURA.md para o diff detalhado "antes/depois" desta migração.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from datetime import datetime
from typing import Callable, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from app.core.credentials import CredenciaisSigaa
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


def _callback_nulo(_tipo: str, _dados: dict) -> None:
    return None


class SigaaWorker:
    """Um worker autossuficiente — idêntico em comportamento ao da v4.0."""

    def __init__(self, worker_id: int, motor: "MotorMatricula"):
        self.id = worker_id
        self.motor = motor
        self.urls = motor.urls  # atalho — mesmo dict, só pra não escrever self.motor.urls toda hora
        self.client = httpx.AsyncClient(
            headers=BROWSER_HEADERS, timeout=motor.timeout_req, follow_redirects=True
        )
        self.payloads_base: Dict[int, Dict[str, str]] = {}
        self.log_prefix = f"[W{self.id}]"

    async def fechar(self):
        await self.client.aclose()

    async def resetar_cliente(self):
        """Mata o cliente HTTP travado e recria do zero para reviver workers zumbis."""
        try:
            await self.client.aclose()
        except Exception:
            pass
        self.client = httpx.AsyncClient(
            headers=BROWSER_HEADERS, timeout=self.motor.timeout_req, follow_redirects=True
        )
        self.payloads_base.clear()

    def log(self, msg: str, level=logging.INFO):
        self.motor.log.log(level, f"{self.log_prefix} {msg}", extra={"worker_id": f"W{self.id}"})

    def _debug_dump(self, html: str, nome: str) -> None:
        fname = caminho_projeto("logs", f"debug_W{self.id}_{nome}_{int(time.time())}.html")
        try:
            with open(fname, "w", encoding="utf-8") as f:
                f.write(html)
            self.log(f"📄 Debug salvo: {os.path.basename(fname)}")
        except Exception as e:
            self.log(f"❌ Erro ao salvar arquivo de debug dump: {repr(e)}", logging.ERROR)

    # --- 1. SETUP ---

    async def realizar_login(self) -> bool:
        self.log("Iniciando processo de Login no CAS...")
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
                self.log("✅ Login concluído!")
                return True
            return False
        except Exception as e:
            self.log(f"💥 Erro fatal e inesperado durante a requisição de login: {repr(e)}", logging.ERROR)
            return False

    async def teleportar_departamento(self, id_departamento: int) -> bool:
        self.log(f"Teleportando (Depto: {id_departamento})...")
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
            return True
        except Exception as e:
            self.log(f"💥 Falha ao extrair tokens ou teleportar para departamento {id_departamento}: {repr(e)}", logging.ERROR)
            return False

    # --- 2. PARSER HÍBRIDO ---
    def parse_hot_path(self, html: str, codigo_alvo: str, turma_alvo: str) -> Optional[Dict[str, str]]:
        if "não foram encontradas" in html.lower() or "nenhum resultado" in html.lower():
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

        while alvos and not self.motor.stop_event.is_set():
            for chave, (codigo, turma, id_depto) in list(alvos.items()):
                if self.motor.stop_event.is_set():
                    break
                if chave not in alvos:
                    continue
                if id_depto not in self.payloads_base:
                    if not await self.teleportar_departamento(id_depto):
                        continue

                payload = self.payloads_base[id_depto].copy()
                payload.update({"form": "form", "form:checkCodigo": "on", "form:txtCodigo": codigo, "form:buscar": "Buscar"})

                try:
                    self.log(f"🔍 Buscando {codigo}-{turma}...")
                    t0 = time.perf_counter()
                    resp = await asyncio.wait_for(
                        self.client.post(self.urls["matricula_extra"], data=payload),
                        timeout=self.motor.timeout_req + 2,
                    )
                    t_req = (time.perf_counter() - t0) * 1000
                    self.log(f"↳ HTTP {resp.status_code}, {len(resp.text)} bytes recebidos", logging.DEBUG)

                    if resp.status_code != 200 or "autenticacao" in resp.text:
                        self.log("⚠️ Sessão corrompida. Reiniciando...", logging.WARNING)
                        await self.realizar_login()
                        self.payloads_base.clear()
                        continue

                    dados_vaga = self.parse_hot_path(resp.text, codigo, turma)
                    if not dados_vaga:
                        self.log(f"📉 Sem vagas ({t_req:.0f}ms).")
                        continue

                    self.log(f"🚨 VAGA DETECTADA ({t_req:.0f}ms) -> {codigo}-{turma} ({dados_vaga['vagas']} vaga(s))!", logging.WARNING)
                    self.motor.emitir("vaga_detectada", {"codigo": codigo, "turma": turma, "vagas": dados_vaga["vagas"]})

                    if self.motor.modo == "monitoramento":
                        # Modo somente monitoramento (seção 11 do pedido): registra e notifica,
                        # mas NUNCA tenta reservar a vaga. Continua monitorando a mesma disciplina
                        # em vez de removê-la — o objetivo aqui é acompanhar mudanças, não agir.
                        continue

                    if locks[chave].locked():
                        self.log("🔒 Outro worker já está atirando. Abortando fogo amigo.")
                        continue

                    async with locks[chave]:
                        if chave not in alvos:
                            continue

                        self.log(f"🎯 ASSUMINDO O TIRO PARA {codigo}-{turma}!", logging.CRITICAL)
                        self.payloads_base[id_depto]["javax.faces.ViewState"] = dados_vaga["viewstate"]

                        resultado = await self.efetivar_matricula(codigo, turma, dados_vaga, self.payloads_base[id_depto])

                        if resultado == "SUCESSO":
                            if self.motor.dry_run:
                                self.log(f"🧪 DRY RUN SUCESSO: Matrícula Simulada em {codigo}-{turma}.", logging.CRITICAL)
                            else:
                                self.log(f"🎉 SUCESSO ABSOLUTO! Matrícula confirmada em {codigo}-{turma}.", logging.CRITICAL)
                            self.motor.emitir("matricula_sucesso", {"codigo": codigo, "turma": turma, "dry_run": self.motor.dry_run})
                            alvos.pop(chave, None)
                        elif resultado == "ERRO_REGRA":
                            self.log(f"🛑 REMOVIDO: A UnB bloqueou {codigo}-{turma} (Pré-req/Choque). Parando de buscar essa matéria.", logging.ERROR)
                            self.motor.emitir("matricula_bloqueada", {"codigo": codigo, "turma": turma})
                            alvos.pop(chave, None)
                        else:
                            self.log("❌ Falha técnica/desafio. Retornando à busca contínua.", logging.ERROR)
                            self.motor.emitir("matricula_falha", {"codigo": codigo, "turma": turma})
                            self.payloads_base.pop(id_depto, None)

                except (httpx.TimeoutException, asyncio.TimeoutError):
                    self.log("⏳ Timeout (Socket Preso). Ressuscitando worker...", logging.WARNING)
                    await self.resetar_cliente()
                    await self.realizar_login()
                except httpx.RequestError as e:
                    self.log(f"🔌 Falha de rede ({type(e).__name__}). Ressuscitando worker...", logging.WARNING)
                    await self.resetar_cliente()
                    await self.realizar_login()
                except Exception as e:
                    self.log(f"💥 Erro crítico inesperado: {repr(e)}", logging.ERROR)
                    self.motor.emitir("erro_critico", {"worker": self.id, "erro": repr(e)})
                    await self.resetar_cliente()
                    await self.realizar_login()

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

        if "btnConfirmar" not in resp_sel.text and "confirmaSenha" not in resp_sel.text:
            self.log("❌ Tela de confirmação não detectada.", logging.ERROR)
            self._debug_dump(resp_sel.text, f"selecao_falha_{codigo}")
            return "FALHA"

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

        raw_action = form_tag.get("action", "")
        action_url = self.urls["sigaa_base"] + raw_action if raw_action.startswith("/") else raw_action if raw_action.startswith("http") else self.urls["confirmacao"]

        if self.motor.dry_run:
            self.log(
                "🔒 DRY RUN ATIVO — o fluxo foi executado até o ponto imediatamente anterior à "
                "confirmação (payload de confirmação montado com sucesso). Nenhuma matrícula foi "
                "confirmada — o POST final NUNCA foi enviado.",
                logging.WARNING,
            )
            self.motor.emitir("dry_run_interrompido", {"codigo": codigo, "turma": turma, "etapa": "antes_do_post_de_confirmacao"})
            return "SUCESSO"

        self.log("🚀 Disparando o POST Final blindado!")
        resp_conf = await self._enviar_confirmacao_real(action_url, campos_conf)
        txt = resp_conf.text.lower()

        if any(kw in txt for kw in ("sucesso", "matrícula realizada", "matriculado com sucesso", "operação realizada", "turma matriculada")):
            return "SUCESSO"

        erros_fatais = ["pré-requisito", "choque de horário", "limite de crédito", "já encontra-se matriculado", "já está matriculado", "mais de uma turma do componente"]

        soup_err = BeautifulSoup(resp_conf.text, "html.parser")
        errs = soup_err.find_all(class_=re.compile(r"erro|error|alert|warn", re.I))
        if errs:
            msg = errs[0].get_text(strip=True)[:400]
            self.log(f"❌ O SIGAA respondeu com erro: {msg}", logging.ERROR)
        else:
            self.log("⚠️ Resultado inconclusivo.", logging.WARNING)
            self._debug_dump(resp_conf.text, f"confirmacao_inconclusiva_{codigo}")

        return "ERRO_REGRA" if any(kw in txt for kw in erros_fatais) else "FALHA"


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

        self.alvos_ativos: Dict[str, List] = {f"{d[0]}-{d[1]}": d for d in disciplinas}
        self.locks_alvos: Dict[str, asyncio.Lock] = {chave: asyncio.Lock() for chave in self.alvos_ativos}
        self.stop_event = asyncio.Event()
        self._workers: List[SigaaWorker] = []
        # ID de execução (seção 24 do pedido de continuação): identifica todos os
        # logs desta execução específica, útil para comparar testes diferentes.
        self.execucao_id = f"{datetime.now().strftime('%Y-%m-%d')}-{uuid.uuid4().hex[:6]}"

    def emitir(self, tipo: str, dados: dict) -> None:
        """Notifica quem estiver ouvindo (GUI/notificações). Nunca deixa uma falha do
        callback derrubar o motor — notificação é sempre secundária ao monitoramento."""
        try:
            self._on_evento(tipo, dados)
        except Exception:
            self.log.warning(f"Callback de evento falhou para '{tipo}' (ignorado, monitor continua)")

    def parar(self) -> None:
        self.stop_event.set()

    async def _aguardar_agendamento(self):
        if not self.agendar_inicio:
            return
        try:
            alvo = datetime.strptime(self.agendar_inicio, "%d/%m/%Y %H:%M:%S")
        except ValueError as e:
            self.log.error(f"❌ Erro de configuração na formatação do agendamento: {repr(e)}", extra={"worker_id": "MAIN"})
            return

        espera = (alvo - datetime.now()).total_seconds()
        if espera > 0:
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
            if await worker.realizar_login():
                self.log.info(f"[W{worker_id}] Em posição. Offset ({atraso_inicial:.2f}s)...", extra={"worker_id": "MAIN"})
                await asyncio.sleep(atraso_inicial)
                await worker.rodar_ciclo()
            else:
                self.log.error(f"[W{worker_id}] Login falhou — worker não iniciado.", extra={"worker_id": "MAIN"})
        except asyncio.CancelledError:
            self.log.info(f"[W{worker_id}] Thread finalizada/cancelada pelo Maestro.", extra={"worker_id": "MAIN"})
        except Exception as e:
            self.log.error(f"[W{worker_id}] Worker engasgou gravemente e abortou a operação: {repr(e)}", extra={"worker_id": "MAIN"})
        finally:
            await worker.fechar()

    async def executar(self) -> None:
        """Roda até todas as disciplinas serem processadas ou stop_event ser sinalizado."""
        from app.core.crash_recovery import marcar_execucao_encerrada, marcar_execucao_iniciada

        # Marcador consumido por app/dashboard/metrics.py para não misturar estatísticas
        # desta execução com as de uma execução anterior que tenha ficado no mesmo log.
        self.log.info(f"SESSAO_INICIADA id={self.execucao_id}", extra={"worker_id": "MAIN"})
        # Seção 54: marca que uma execução está em andamento, para detectar na
        # próxima vez se esta terminou de forma abrupta (queda, crash) — o
        # finally abaixo apaga o marcador em qualquer encerramento controlado.
        marcar_execucao_iniciada(self.modo, self.execucao_id)

        try:
            titulo = "MODO MATRÍCULA AUTOMÁTICA" if self.modo == "matricula" else "MODO SOMENTE MONITORAMENTO"
            self.log.info("╔════════════════════════════════════════════════════════════╗", extra={"worker_id": "MAIN"})
            self.log.info(f"║     INICIANDO SIGAA SNIPER — {titulo:<32}║", extra={"worker_id": "MAIN"})
            self.log.info("╚════════════════════════════════════════════════════════════╝", extra={"worker_id": "MAIN"})

            if self.modo == "monitoramento":
                self.log.info("👀 Modo monitoramento: nenhuma matrícula será realizada automaticamente.", extra={"worker_id": "MAIN"})
            elif self.dry_run:
                self.log.warning("⚠️  ATENÇÃO: MODO DRY_RUN ATIVADO. AS MATRÍCULAS NÃO SERÃO CONFIRMADAS! ⚠️", extra={"worker_id": "MAIN"})

            await self._aguardar_agendamento()
            if self.stop_event.is_set():
                return

            tarefas = [
                asyncio.create_task(self._start_worker(i, i * (self.intervalo_busca / max(1, self.num_workers))))
                for i in range(self.num_workers)
            ]
            while self.alvos_ativos and not self.stop_event.is_set():
                await asyncio.sleep(1)

            if not self.alvos_ativos:
                self.log.info("🏆 TODAS AS DISCIPLINAS FORAM PROCESSADAS!", extra={"worker_id": "MAIN"})
            else:
                self.log.info("🛑 Execução interrompida pelo usuário.", extra={"worker_id": "MAIN"})

            for t in tarefas:
                t.cancel()
            await asyncio.gather(*tarefas, return_exceptions=True)
        finally:
            marcar_execucao_encerrada()
