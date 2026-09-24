"""
Modo demonstração — o programa inteiro contra um SIGAA SIMULADO (Fase 6, 077).

Serve para aprender a usar, testar as notificações e apresentar o projeto sem
conta, sem período de matrícula e sem tocar no SIGAA: TODAS as requisições do
motor passam por um `httpx.MockTransport` que responde localmente (nenhuma
sai do computador). Vagas aparecem e somem ao acaso, com tempos de resposta
variados, para os painéis e gráficos terem o que mostrar.

Garantias do modo:
  - credenciais fictícias (as suas não são pedidas nem usadas);
  - DRY RUN sempre ligado;
  - nada vai para o histórico nem para os relatórios (não mistura dado falso
    com o seu histórico real de vagas);
  - notificações externas saem marcadas com "[DEMONSTRAÇÃO]".

O HTML segue os mesmos seletores do SIGAA real que o motor usa (o mesmo
formato do simulador dos testes automatizados).
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

import httpx

from app.core.credentials import CredenciaisSigaa

CREDENCIAIS_DEMO = CredenciaisSigaa(usuario="demonstracao", senha="demonstracao", cpf="111.444.777-35",
                                    nascimento="01/01/2000")
DISCIPLINAS_EXEMPLO = [["FGA0211", "01", 673], ["MAT0025", "02", 518]]

_PAGINA_CAS = """<html><body><form><input name="lt" value="LT-DEMO"><input name="execution" value="e1s1">
<input name="_eventId" value="submit"></form></body></html>"""
_PAGINA_PORTAL = """<html><body><form id="menu:form_menu_discente"><input type="hidden" name="id" value="4242">
<input type="hidden" name="javax.faces.ViewState" id="vs" value="VS-PORTAL"></form>form_menu_discente</body></html>"""
_PAGINA_BUSCA = """<html><body><form id="form"><input name="form:checkUnidade" value="">
<select name="form:comboDepartamento"></select><input name="form:txtCodigo" value="">
<input type="submit" name="form:buscar" value="Buscar">
<input type="hidden" name="javax.faces.ViewState" value="VS-BUSCA"></form></body></html>"""
_PAGINA_CONFIRMACAO = """<html><body><form id="j_id_jsp_1" action="{acao}">
<input type="hidden" name="j_id_jsp_1:inputHiddenOpcaoExibir" value="1">
<input type="text" name="j_id_jsp_1:Data" title="Data de Nascimento">
<input type="password" name="j_id_jsp_1:senha">
<input type="submit" name="j_id_jsp_1:btnConfirmar" value="Confirmar Matrícula">
<input type="hidden" name="javax.faces.ViewState" value="VS-CONF"></form></body></html>"""


class SigaaDemo:
    """Handler assíncrono para `httpx.MockTransport`."""

    def __init__(self, disciplinas: List[List], urls: Dict[str, str], semente: Optional[int] = None,
                 prob_abrir: float = 0.03, duracao_vaga: Tuple[float, float] = (4.0, 15.0),
                 latencia: Tuple[float, float] = (0.08, 0.35)):
        self.rng = random.Random(semente)
        self.urls = urls
        self.prob_abrir, self.duracao_vaga, self.latencia = prob_abrir, duracao_vaga, latencia
        self.turmas: Dict[str, List[str]] = {}
        for d in disciplinas:
            self.turmas.setdefault(str(d[0]).upper(), []).append(str(d[1]))
        self._vagas: Dict[Tuple[str, str], Tuple[int, float]] = {}
        self.requisicoes = 0

    def _caminho(self, chave: str) -> str:
        return urlsplit(self.urls.get(chave, "")).path

    def _vagas_de(self, codigo: str, turma: str) -> int:
        agora = time.monotonic()
        vagas, ate = self._vagas.get((codigo, turma), (0, 0.0))
        if agora < ate:
            return vagas
        if self.rng.random() < self.prob_abrir:
            vagas = self.rng.randint(1, 3)
            self._vagas[(codigo, turma)] = (vagas, agora + self.rng.uniform(*self.duracao_vaga))
            return vagas
        self._vagas[(codigo, turma)] = (0, 0.0)
        return 0

    def _resultado(self, codigo: str) -> str:
        turmas = sorted(set(self.turmas.get(codigo, []) + ["01", "02"]))
        linhas = []
        for i, turma in enumerate(turmas):
            vagas = self._vagas_de(codigo, turma)
            id_turma = 900000 + (abs(hash((codigo, turma))) % 99999)
            classe = "linhaPar" if i % 2 == 0 else "linhaImpar"
            linhas.append(
                f'<tr class="{classe}"><td></td><td>Turma {turma}</td><td></td><td></td><td></td><td></td><td></td>'
                f'<td>{vagas}</td><td><a title="Selecionar turma" onclick="jsfcljs(document.forms[\'form\'],'
                f"{{'form:selecionarTurma_{i}':'form:selecionarTurma_{i}','idTurma':'{id_turma}'}},'');\">sel</a></td></tr>")
        return (f'<html><body><form id="form"><table id="lista-turmas-extra"><tr class="disciplina"><td>{codigo} - '
                f'DISCIPLINA DE DEMONSTRAÇÃO</td></tr>{"".join(linhas)}</table>'
                '<input type="hidden" name="javax.faces.ViewState" value="VS-RESULTADO"></form></body></html>')

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requisicoes += 1
        await asyncio.sleep(self.rng.uniform(*self.latencia))
        caminho = request.url.path
        dados = parse_qs(request.content.decode("utf-8")) if request.method == "POST" else {}
        if caminho == self._caminho("cas_login"):
            return httpx.Response(200, text=_PAGINA_CAS if request.method == "GET" else "<html>ok</html>")
        if caminho == self._caminho("portal_discente"):
            return httpx.Response(200, text=_PAGINA_PORTAL if request.method == "GET" else _PAGINA_BUSCA)
        if caminho == self._caminho("matricula_extra"):
            if request.method == "GET":
                return httpx.Response(200, text=_PAGINA_BUSCA)
            if "form:buscar" in dados:
                codigo = (dados.get("form:txtCodigo") or [""])[0].upper()
                return httpx.Response(200, text=self._resultado(codigo))
            return httpx.Response(200, text=_PAGINA_CONFIRMACAO.format(acao=self._caminho("confirmacao")))
        if caminho == self._caminho("confirmacao"):
            return httpx.Response(200, text="<html><div class='info'>Matrícula realizada com sucesso! (demonstração)</div></html>")
        if caminho.endswith("/sigaa/public/"):
            return httpx.Response(200, text="<html>SIGAA (demonstração)</html>")
        return httpx.Response(404, text="não simulado na demonstração")


def transporte_demo(disciplinas: List[List], urls: Dict[str, str], **opcoes) -> httpx.MockTransport:
    return httpx.MockTransport(SigaaDemo(disciplinas, urls, **opcoes))
