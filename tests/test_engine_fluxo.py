"""
Regressão do motor de matrícula contra um SIGAA SIMULADO (httpx.MockTransport).

Nenhuma requisição sai do computador. O HTML simulado segue exatamente os
seletores que app/core/engine.py procura (mesma lógica da v4.0), então estes
testes garantem que o fluxo login → departamento → busca → vaga → seleção →
confirmação continua funcionando, e principalmente que:
  - DRY RUN NUNCA envia o POST final de confirmação;
  - modo monitoramento NUNCA tenta selecionar/confirmar turma;
  - os campos de segurança recebem os dados certos (senha/CPF/nascimento).
"""
from __future__ import annotations

import asyncio
import logging
from urllib.parse import parse_qs

import httpx
import pytest

from app.core import engine
from app.core.credentials import CredenciaisSigaa

ACTION_CONFIRMACAO = "/sigaa/graduacao/matricula/extraordinaria/confirmacao.jsf"

PAGINA_CAS = """<html><form><input name="lt" value="LT-1"><input name="execution" value="e1s1">
<input name="_eventId" value="submit"></form></html>"""
PAGINA_PORTAL = """<html><form id="menu:form_menu_discente"><input type="hidden" name="id" value="4242">
<input type="hidden" name="javax.faces.ViewState" id="vs" value="VS-PORTAL"></form>form_menu_discente</html>"""
PAGINA_BUSCA = """<html><form id="form"><input name="form:checkUnidade" value="">
<select name="form:comboDepartamento"></select><input name="form:txtCodigo" value="">
<input type="submit" name="form:buscar" value="Buscar">
<input type="hidden" name="javax.faces.ViewState" value="VS-BUSCA"></form></html>"""


def pagina_resultado(vagas: int) -> str:
    return f"""<html><form id="form"><table id="lista-turmas-extra">
<tr class="disciplina"><td>FGA0211 - CÁLCULO 1</td></tr>
<tr class="linhaPar"><td></td><td>Turma 01</td><td></td><td></td><td></td><td></td><td></td><td>{vagas}</td>
<td><a title="Selecionar turma" onclick="jsfcljs(document.forms['form'],{{'form:selecionarTurma_7':'form:selecionarTurma_7','idTurma':'999'}},'');">sel</a></td></tr>
<tr class="linhaImpar"><td></td><td>Turma 02</td><td></td><td></td><td></td><td></td><td></td><td>5</td>
<td><a title="Selecionar turma" onclick="{{'form:selecionarTurma_8':'x','idTurma':'888'}}">sel</a></td></tr>
</table><input type="hidden" name="javax.faces.ViewState" value="VS-RESULTADO"></form></html>"""


PAGINA_CONFIRMACAO = f"""<html><form id="j_id_jsp_123" action="{ACTION_CONFIRMACAO}">
<input type="hidden" name="j_id_jsp_123:inputHiddenOpcaoExibir" value="1">
<input type="text" name="j_id_jsp_123:Data" title="Data de Nascimento">
<input type="text" name="j_id_jsp_123:cpf" title="CPF">
<input type="password" name="j_id_jsp_123:senha">
<input type="submit" name="j_id_jsp_123:btnConfirmar" value="Confirmar Matrícula">
<input type="hidden" name="javax.faces.ViewState" value="VS-CONF"></form></html>"""


class SigaaSimulado:
    def __init__(self, vagas: int = 2, resposta_final: str = "Matrícula realizada com sucesso!"):
        self.vagas = vagas
        self.resposta_final = resposta_final
        self.requisicoes = []  # (metodo, caminho, dados_form)
        # Cenários de falha (sugestão 074):
        self.login_recusado = False   # CAS responde, mas o portal não abre (senha errada)
        self.portal_sem_menu = False  # logado, mas sem o formulário do menu (departamento não prepara)
        self.falhas_rede_cas = 0      # quantas requisições ao CAS falham por rede antes de funcionar
        self.falhar_busca_a_cada = 0  # >0: a cada N buscas, uma responde HTTP 500 (sessão expirada)
        self.sobrecarga_nas_primeiras = 0  # as N primeiras buscas respondem HTTP 503 (SIGAA sobrecarregado)
        self.logins_simultaneos_max = 0
        self._logins_agora = 0
        self._buscas = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        dados = parse_qs(request.content.decode("utf-8")) if request.method == "POST" else {}
        caminho = request.url.path
        self.requisicoes.append((request.method, caminho, dados))
        if request.url.host == "autenticacao.unb.br":
            if self.falhas_rede_cas > 0:
                self.falhas_rede_cas -= 1
                raise httpx.ConnectError("rede simulada fora do ar", request=request)
            return httpx.Response(200, text=PAGINA_CAS if request.method == "GET" else "<html>ok</html>")
        if caminho.endswith("discente.jsf"):
            if self.login_recusado:
                return httpx.Response(200, text="<html>Usuário e/ou senha inválidos</html>")
            if self.portal_sem_menu and request.method == "GET":
                return httpx.Response(200, text="<html>form_menu_discente (sem id/ViewState)</html>")
            return httpx.Response(200, text=PAGINA_PORTAL if request.method == "GET" else PAGINA_BUSCA)
        if caminho.endswith("matricula_extraordinaria.jsf"):
            if request.method == "GET":
                return httpx.Response(200, text=PAGINA_BUSCA)
            if "form:buscar" in dados:
                self._buscas += 1
                if self._buscas <= self.sobrecarga_nas_primeiras:
                    return httpx.Response(503, text="<html>Service Unavailable</html>")
                if self.falhar_busca_a_cada and self._buscas % self.falhar_busca_a_cada == 0:
                    return httpx.Response(500, text="<html>erro interno</html>")
                return httpx.Response(200, text=pagina_resultado(self.vagas))
            return httpx.Response(200, text=PAGINA_CONFIRMACAO)  # POST de seleção de turma
        if caminho == ACTION_CONFIRMACAO:
            return httpx.Response(200, text=f"<html><div class='info'>{self.resposta_final}</div></html>")
        return httpx.Response(404, text="não simulado")

    def posts_confirmacao(self):
        return [r for r in self.requisicoes if r[0] == "POST" and r[1] == ACTION_CONFIRMACAO]

    def posts_selecao(self):
        return [r for r in self.requisicoes if r[0] == "POST" and r[1].endswith("matricula_extraordinaria.jsf") and "form:buscar" not in r[2]]


@pytest.fixture
def sigaa(monkeypatch):
    simulado = SigaaSimulado()
    original = httpx.AsyncClient

    def cliente(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(simulado)
        return original(*args, **kwargs)

    monkeypatch.setattr(engine.httpx, "AsyncClient", cliente)
    return simulado


def credenciais():
    return CredenciaisSigaa(usuario="200012345", senha="s3nh@", cpf="123.456.789-00", nascimento="01/02/2003")


def rodar(motor, timeout=15):
    asyncio.run(asyncio.wait_for(motor.executar(), timeout))


def rodar_ate(motor, condicao, timeout=15):
    """Roda o motor e o para assim que `condicao(motor)` for verdadeira — em vez
    de parar após um tempo fixo, que fica curto com a máquina ocupada."""
    async def vigiar():
        while not condicao(motor):
            await asyncio.sleep(0.02)
        motor.parar()

    async def cenario():
        await asyncio.gather(motor.executar(), vigiar())

    asyncio.run(asyncio.wait_for(cenario(), timeout))


def montar(modo="matricula", dry_run=True, eventos=None, parar_em=None):
    eventos = [] if eventos is None else eventos
    motor_ref = {}

    def on_evento(tipo, dados):
        eventos.append((tipo, dados))
        if parar_em and tipo == parar_em:
            motor_ref["m"].parar()

    motor = engine.MotorMatricula(
        credenciais=credenciais(), disciplinas=[["FGA0211", "01", 673]], num_workers=1,
        intervalo_busca=0.01, timeout_req=5, dry_run=dry_run, modo=modo,
        logger=logging.getLogger("teste_engine"), on_evento=on_evento,
    )
    motor_ref["m"] = motor
    return motor, eventos


def test_dry_run_nunca_envia_confirmacao(sigaa):
    motor, eventos = montar(dry_run=True)
    rodar(motor)
    tipos = [t for t, _ in eventos]
    assert "vaga_detectada" in tipos
    assert "dry_run_interrompido" in tipos
    assert ("matricula_sucesso", {"codigo": "FGA0211", "turma": "01", "dry_run": True}) in eventos
    assert sigaa.posts_selecao(), "o fluxo deve chegar até a tela de confirmação"
    assert sigaa.posts_confirmacao() == [], "DRY RUN jamais pode enviar o POST final"
    assert motor.alvos_ativos == {}


def test_matricula_real_preenche_campos_de_seguranca(sigaa):
    motor, eventos = montar(dry_run=False)
    rodar(motor)
    posts = sigaa.posts_confirmacao()
    assert len(posts) == 1
    form = posts[0][2]
    assert form["j_id_jsp_123:senha"] == ["s3nh@"]
    assert form["j_id_jsp_123:cpf"] == ["12345678900"]
    assert form["j_id_jsp_123:Data"] == ["01/02/2003"]
    assert form["javax.faces.ViewState"] == ["VS-CONF"]
    assert "j_id_jsp_123:btnConfirmar" in form
    assert ("matricula_sucesso", {"codigo": "FGA0211", "turma": "01", "dry_run": False}) in eventos


def test_seleciona_a_turma_certa(sigaa):
    motor, _ = montar(dry_run=True)
    rodar(motor)
    selecao = sigaa.posts_selecao()[0][2]
    assert selecao["idTurma"] == ["999"]  # turma 01, não a 02 (idTurma 888)
    assert "form:selecionarTurma_7" in selecao


def test_bloqueio_por_regra_remove_disciplina(sigaa):
    sigaa.resposta_final = "Erro: pré-requisito não cumprido"
    motor, eventos = montar(dry_run=False)
    rodar(motor)
    assert ("matricula_bloqueada", {"codigo": "FGA0211", "turma": "01"}) in eventos
    assert motor.alvos_ativos == {}


def test_monitoramento_nunca_seleciona_turma(sigaa):
    motor, eventos = montar(modo="monitoramento", dry_run=False, parar_em="vaga_detectada")
    rodar(motor)
    assert eventos[0][0] == "vaga_detectada"
    assert sigaa.posts_selecao() == []
    assert sigaa.posts_confirmacao() == []


def test_sem_vagas_nao_age(sigaa):
    sigaa.vagas = 0
    motor, eventos = montar(dry_run=False)

    async def parar_logo():
        await asyncio.sleep(1.5)
        motor.parar()

    async def cenario():
        await asyncio.gather(motor.executar(), parar_logo())

    asyncio.run(asyncio.wait_for(cenario(), 15))
    assert eventos == []
    assert sigaa.posts_selecao() == []


def test_trava_independente_do_dry_run():
    motor, _ = montar(dry_run=True)
    worker = engine.SigaaWorker(0, motor)

    async def tentar():
        try:
            await worker._enviar_confirmacao_real("https://exemplo.invalido", {})
        finally:
            await worker.fechar()

    with pytest.raises(RuntimeError, match="DRY RUN"):
        asyncio.run(tentar())


def test_marcador_de_execucao_removido_ao_terminar(sigaa, raiz_temporaria):
    from app.core.crash_recovery import verificar_encerramento_anterior
    motor, _ = montar(dry_run=True)
    rodar(motor)
    assert verificar_encerramento_anterior() is None


# ── Espera após falhas de login/departamento (sugestão 074) ─────────────

class _Coletor(logging.Handler):
    def __init__(self):
        super().__init__()
        self.mensagens = []

    def emit(self, record):
        self.mensagens.append(record.getMessage())


def _com_log(motor):
    coletor = _Coletor()
    motor.log.addHandler(coletor)
    motor.log.setLevel(logging.INFO)
    return coletor


def test_departamento_com_falha_espera_em_vez_de_repetir(sigaa, monkeypatch):
    monkeypatch.setattr(engine.SigaaWorker, "ESPERA_FALHA_BASE_SEG", 0.5)
    sigaa.portal_sem_menu = True
    motor, _ = montar(dry_run=True)
    coletor = _com_log(motor)

    async def cenario():
        async def parar():
            await asyncio.sleep(1.6)
            motor.parar()
        await asyncio.gather(motor.executar(), parar())

    try:
        asyncio.run(asyncio.wait_for(cenario(), 15))
    finally:
        motor.log.removeHandler(coletor)
    gets_portal = [r for r in sigaa.requisicoes if r[0] == "GET" and r[1].endswith("discente.jsf")]
    # 1 GET no login + tentativas de preparar o departamento em t≈0, 0,5 s e 1,5 s.
    # Sem a espera (intervalo de 0,01 s) seriam dezenas.
    assert len(gets_portal) <= 5, len(gets_portal)
    assert any("Aguardando" in m and "departamento 673" in m for m in coletor.mensagens)


def test_login_recusado_nao_insiste_e_encerra_execucao(sigaa):
    sigaa.login_recusado = True
    motor, eventos = montar(dry_run=True)
    coletor = _com_log(motor)
    try:
        rodar(motor, timeout=10)  # termina sozinha, sem precisar de "Parar"
    finally:
        motor.log.removeHandler(coletor)
    posts_cas = [r for r in sigaa.requisicoes if r[0] == "POST" and "sso-server" in r[1]]
    assert len(posts_cas) == 1, "senha recusada não pode ser reenviada em laço"
    assert any("Nenhum worker conseguiu continuar" in m for m in coletor.mensagens)
    assert eventos == []


def test_login_sem_rede_tenta_de_novo_ate_conseguir(sigaa, monkeypatch):
    monkeypatch.setattr(engine.SigaaWorker, "ESPERA_FALHA_BASE_SEG", 0.05)
    sigaa.falhas_rede_cas = 2
    motor, eventos = montar(dry_run=True)
    rodar(motor)
    assert ("matricula_sucesso", {"codigo": "FGA0211", "turma": "01", "dry_run": True}) in eventos
    assert sigaa.posts_confirmacao() == []


def test_espera_cresce_e_tem_teto():
    motor, _ = montar()
    worker = engine.SigaaWorker(0, motor)
    try:
        esperas = [worker._espera_para(n) for n in range(1, 9)]
        assert esperas[:4] == [1.0, 2.0, 4.0, 8.0]
        assert max(esperas) == engine.SigaaWorker.ESPERA_FALHA_MAX_SEG
        worker._adiar_departamento(673)
        worker._adiar_departamento(673)
        assert worker._falhas_depto[673] == 2
    finally:
        asyncio.run(worker.fechar())


# ── 072: pré-checagem do parser não muda o resultado ─────────────────────

def _parse_original_v40(html, codigo_alvo, turma_alvo):
    """Cópia fiel do parse_hot_path da v4.0 (antes da sugestão 072), para comparação."""
    import re
    from bs4 import BeautifulSoup
    if "não foram encontradas" in html.lower() or "nenhum resultado" in html.lower():
        return None
    soup = BeautifulSoup(html, "html.parser")
    tabela = soup.find(id="lista-turmas-extra")
    if not tabela:
        return None
    ativa = False
    for tr in tabela.find_all("tr"):
        classes = " ".join(tr.get("class", []))
        if "disciplina" in classes:
            ativa = codigo_alvo.upper() in tr.get_text().upper()
            continue
        if not ativa or ("linhaPar" not in classes and "linhaImpar" not in classes):
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
        m_id = re.search(r"'idTurma'\s*:\s*'(\d+)'", onclick)
        m_link = re.search(r"'(form:selecionarTurma[^']*)':", onclick)
        if not m_id or not m_link:
            continue
        tag_vs = soup.find("input", attrs={"name": "javax.faces.ViewState"})
        if not tag_vs:
            return None
        return {"idTurma": m_id.group(1), "link_id": m_link.group(1), "viewstate": tag_vs["value"], "vagas": vagas}
    return None


def test_parser_com_pre_checagem_e_equivalente_ao_original():
    motor, _ = montar()
    worker = engine.SigaaWorker(0, motor)
    try:
        paginas = [pagina_resultado(2), pagina_resultado(0), pagina_resultado(7).replace("FGA0211", "fga0211"),
                   pagina_resultado(3).replace("FGA0211", "MAT0025"), "<html>Nenhum resultado encontrado</html>",
                   "<html>sem tabela FGA0211</html>", pagina_resultado(1).replace('value="VS-RESULTADO"', "")]
        for html in paginas:
            for codigo, turma in (("FGA0211", "01"), ("FGA0211", "02"), ("FGA0211", "03"), ("MAT0025", "01"), ("fga0211", "01")):
                def resultado(funcao):  # compara também o comportamento em erro (mesma exceção)
                    try:
                        return funcao(html, codigo, turma)
                    except Exception as e:  # noqa: BLE001
                        return type(e)
                assert resultado(worker.parse_hot_path) == resultado(_parse_original_v40), (codigo, turma)
    finally:
        asyncio.run(worker.fechar())
