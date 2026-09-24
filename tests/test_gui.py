"""GUI (Tkinter): aviso legal, construção das telas e as correções de sincronização."""
from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")


def _tk_disponivel() -> bool:
    try:
        r = tk.Tk()
        r.destroy()
        return True
    except tk.TclError:
        return False


pytestmark = pytest.mark.skipif(not _tk_disponivel(), reason="sem ambiente gráfico para o Tkinter")


def test_aviso_legal_so_libera_com_as_5_confirmacoes():
    from app.gui.disclaimer_dialog import DialogoAvisoLegal
    raiz = tk.Tk()
    try:
        dlg = DialogoAvisoLegal(raiz)
        assert len(dlg.vars_confirmacao) == 5
        assert str(dlg.btn_continuar.cget("state")) == "disabled"
        variaveis = list(dlg.vars_confirmacao.values())
        for v in variaveis[:-1]:
            v.set(True)
        dlg._atualizar_botao()
        assert str(dlg.btn_continuar.cget("state")) == "disabled"
        variaveis[-1].set(True)
        dlg._atualizar_botao()
        assert str(dlg.btn_continuar.cget("state")) == "normal"
        dlg._aceitar()
        assert dlg.aceito is True
    finally:
        raiz.destroy()


@pytest.fixture
def app_gui(monkeypatch):
    import app.gui.app as modulo

    class AvisoAceito:
        aceito = True

        def __init__(self, _parent):
            pass

    monkeypatch.setattr(modulo, "DialogoAvisoLegal", AvisoAceito)
    monkeypatch.setattr(modulo.SniperApp, "wait_window", lambda self, w=None: None)
    monkeypatch.setattr(modulo.SniperApp, "_talvez_mostrar_assistente_primeira_execucao", lambda self: None)
    janela = modulo.SniperApp()
    janela.withdraw()
    yield janela
    janela.destroy()


def test_todas_as_telas_constroem(app_gui):
    esperadas = {"execucao", "dashboard", "logs", "historico", "credenciais", "disciplinas", "notificacoes",
                 "avancado", "diagnostico", "experimental", "ajuda", "sobre"}
    assert set(app_gui._telas) == esperadas
    for nome in esperadas:
        app_gui._mostrar(nome)
        app_gui.update_idletasks()


def test_recarregar_telas_apos_restaurar(app_gui):
    from app.core.config import Disciplina, restaurar_padroes
    tela_av = app_gui._telas["avancado"]
    tela_av.var_workers.set(3)
    app_gui.settings["num_workers"] = 3
    app_gui.settings = restaurar_padroes(app_gui.settings)
    app_gui.disciplinas.append(Disciplina("FGA0211", "01", 673))
    app_gui.sessao.sigaa.usuario = "200012345"
    app_gui.recarregar_telas()
    assert tela_av.var_workers.get() == 20
    assert app_gui._telas["disciplinas"].tree.get_children() == ("0",)
    assert app_gui._telas["credenciais"].var_usuario.get() == "200012345"


def test_editar_disciplina_nao_reativa(app_gui, monkeypatch):
    from app.core.config import Disciplina
    import app.gui.screens.disciplinas as tela_mod

    app_gui.disciplinas.append(Disciplina("FGA0211", "01", 673, ativa=False))
    tela = app_gui._telas["disciplinas"]
    tela.recarregar()
    tela.tree.selection_set("0")

    class DialogoFalso:
        def __init__(self, _parent, _d=None):
            self.resultado = Disciplina("FGA0211", "02", 673)  # ativa=True por padrão, como o diálogo real

    monkeypatch.setattr(tela_mod, "DialogoDisciplina", DialogoFalso)
    monkeypatch.setattr(tela, "wait_window", lambda _w: None)
    tela._editar()
    assert app_gui.disciplinas[0].turma == "02"
    assert app_gui.disciplinas[0].ativa is False


# ── Fase 1 ───────────────────────────────────────────────────────────────

def test_barra_de_status_reflete_modo_e_matricula_real(app_gui):
    from app.gui.barra_status import descrever_estado
    assert descrever_estado({"em_execucao": False})[1] == "parado"
    assert descrever_estado({"em_execucao": True, "modo": "monitoramento"})[1] == "monitoramento"
    assert descrever_estado({"em_execucao": True, "modo": "matricula", "dry_run": True})[1] == "dry_run"
    texto, chave = descrever_estado({"em_execucao": True, "modo": "matricula", "dry_run": False})
    assert chave == "real" and "REAL" in texto
    assert descrever_estado({"em_execucao": True, "parando": True, "modo": "matricula"})[1] == "parando"

    class ExecutorFalso:
        def em_execucao(self):
            return True

    app_gui._executor = ExecutorFalso()
    app_gui._execucao_info = {"modo": "matricula", "dry_run": False}
    app_gui.barra_status.atualizar_agora()
    assert "MATRÍCULA REAL" in app_gui.barra_status.lbl_estado.cget("text")
    assert "req/s" in app_gui.barra_status.lbl_carga.cget("text")
    app_gui._executor = None
    app_gui.barra_status.atualizar_agora()
    assert "Parado" in app_gui.barra_status.lbl_estado.cget("text")


def test_preset_de_carga_na_tela_avancada(app_gui):
    tela = app_gui._telas["avancado"]
    assert tela.var_preset.get() == "Intenso (padrão original)"
    tela.var_preset.set("Leve")
    tela._aplicar_preset()
    assert tela.var_workers.get() == 4 and tela.var_intervalo.get() == 1.5
    assert "(baixa)" in tela.lbl_carga.cget("text")
    tela.var_workers.set(7)
    assert tela.var_preset.get() == "Personalizado"


def test_credenciais_invalidas_na_gui(app_gui, monkeypatch):
    import app.gui.screens.credenciais as tela_mod
    avisos = []
    monkeypatch.setattr(tela_mod.messagebox, "showwarning", lambda titulo, texto: avisos.append(texto))
    tela = app_gui._telas["credenciais"]
    tela.var_usuario.set("200012345"); tela.var_senha.set("x"); tela.var_cpf.set("12345678900"); tela.var_nascimento.set("01022003")
    tela._salvar()
    assert avisos and "CPF inválido" in avisos[0]
    assert tela.var_nascimento.get() == "01/02/2003"
    tela.var_cpf.set("12345678909")
    tela._salvar()
    assert len(avisos) == 1 and "memória" in tela.lbl_status.cget("text")


def test_dialogo_de_lote_previa_e_adiciona(app_gui, monkeypatch):
    from app.core.config import Disciplina
    import app.gui.screens.disciplinas as tela_mod
    monkeypatch.setattr(tela_mod.messagebox, "askyesno", lambda *a, **k: True)
    tela = app_gui._telas["disciplinas"]
    dlg = tela_mod.DialogoLote(tela, [Disciplina("FGA0211", "01", 673)])
    dlg.txt.insert("1.0", "FGA0211 01 673\nMAT0025 02 518\nCIC0004 03 99999\nruim")
    dlg._previsualizar()
    assert len(dlg.tree.get_children()) == 4
    assert str(dlg.btn_adicionar.cget("state")) == "normal" and "2" in dlg.btn_adicionar.cget("text")
    dlg._adicionar()
    assert [d.chave() for d in dlg.resultado] == ["MAT0025-02", "CIC0004-03"]


# ── Fase 2 ───────────────────────────────────────────────────────────────

def test_dashboard_da_gui_mostra_dados_do_motor(app_gui, monkeypatch):
    import httpx
    from app.core import engine
    from tests.test_engine_fluxo import SigaaSimulado, montar, rodar_ate
    simulado = SigaaSimulado(vagas=0)
    simulado.falhar_busca_a_cada = 2  # metade das buscas devolve HTTP 500 (sessão expirada)
    original = httpx.AsyncClient
    monkeypatch.setattr(engine.httpx, "AsyncClient", lambda *a, **k: original(*a, **{**k, "transport": httpx.MockTransport(simulado)}))
    motor, _ = montar(dry_run=True)
    rodar_ate(motor, lambda m: m.telemetria.erros["sessao"] >= 2)

    tela = app_gui._telas["dashboard"]
    tela._atualizar()  # antes de qualquer execução: sem dados do motor
    assert tela.tree_alvos.get_children() == ()
    app_gui._motor = motor
    tela._atualizar()
    linha = tela.tree_alvos.item(tela.tree_alvos.get_children()[0], "values")
    assert linha[0] == "FGA0211-01" and linha[1] == "Sem vagas" and int(linha[4]) >= 1
    assert tela.tree_erros.exists("sessao")
    tela.tree_erros.selection_set("sessao")
    tela._mostrar_acao_erro()
    assert "O que fazer" in tela.lbl_acao_erro.cget("text")
    assert tela.tree.get_children() == ("W0",) and "Encerrado" in tela.tree.item("W0", "values")[3]
    assert tela.lbl_fase.cget("text") == "Execução encerrada."
    app_gui._mostrar("dashboard")
    app_gui.update_idletasks()
    tela._atualizar()
    assert tela.btn_resumo.winfo_ismapped()


# ── Fase 3 ───────────────────────────────────────────────────────────────

def test_tela_historico_da_gui(app_gui, monkeypatch, tmp_path):
    from datetime import datetime
    import app.gui.screens.historico as tela_mod
    from app.core import historico
    from tests.test_historico import _resumo
    agora = datetime.now().replace(microsecond=0)
    historico.registrar_execucao(_resumo("g1", agora, vagas=2))
    historico.registrar_execucao(_resumo("g2", agora, alvos=("MAT0025-02",)))
    tela = app_gui._telas["historico"]
    tela.recarregar()
    assert set(tela.tree.get_children()) == {"g1", "g2"} and "2 execução" in tela.lbl_totais.cget("text")
    tela.var_disciplina.set("MAT0025-02")
    tela.recarregar()
    assert tela.tree.get_children() == ("g2",)
    tela.tree.selection_set("g2")
    tela._mostrar_detalhe()
    assert "Resumo da execução g2" in tela.txt.get("1.0", "end")
    destino = tmp_path / "h.csv"
    monkeypatch.setattr(tela_mod.filedialog, "asksaveasfilename", lambda **k: str(destino))
    monkeypatch.setattr(tela_mod.messagebox, "showinfo", lambda *a, **k: None)
    tela._exportar()
    assert "g2" in destino.read_text(encoding="utf-8-sig") and "g1" not in destino.read_text(encoding="utf-8-sig")
    monkeypatch.setattr(tela_mod.messagebox, "askyesno", lambda *a, **k: True)
    tela._apagar()
    tela.recarregar()
    assert tela.tree.get_children() == ()


def test_historico_nas_configuracoes_avancadas_da_gui(app_gui):
    tela = app_gui._telas["avancado"]
    assert tela.var_hist_ativo.get() is True and tela.var_hist_dias.get() == 180
    tela.var_hist_ativo.set(False)
    tela.var_hist_dias.set(30)
    assert tela._coletar_settings_da_tela()["historico"] == {"ativo": False, "dias_retencao": 30}


# ── Fase 4 ───────────────────────────────────────────────────────────────

def test_execucao_pausa_e_disciplinas_ao_vivo_na_gui(app_gui, monkeypatch):
    import app.gui.screens.disciplinas as tela_mod
    from app.core.config import Disciplina
    chamadas = []

    class MotorFalso:
        pausado = False
        motivo_pausa = None

        def pausar(self, motivo):
            self.pausado, self.motivo_pausa = True, motivo

        def retomar(self, motivo):
            self.pausado, self.motivo_pausa = False, None

        def adicionar_alvo(self, item):
            chamadas.append(("add", tuple(item)))

        def remover_alvo(self, chave):
            chamadas.append(("rem", chave))

    class ExecutorFalso:
        def em_execucao(self):
            return True

        def chamar(self, f, *a):
            f(*a)

    app_gui._motor, app_gui._executor = MotorFalso(), ExecutorFalso()
    tela = app_gui._telas["execucao"]
    tela._alternar_pausa()
    assert app_gui._motor.pausado and app_gui.estado_execucao()["pausado"] and tela.btn_pausar.cget("text") == "▶️ Retomar"
    app_gui.barra_status.atualizar_agora()
    assert "Pausado" in app_gui.barra_status.lbl_estado.cget("text")
    tela._alternar_pausa()
    assert not app_gui._motor.pausado
    app_gui._motor.pausado, app_gui._motor.motivo_pausa = True, "janela"
    assert app_gui.retomar_motor() is False  # só a janela retoma

    disc = app_gui._telas["disciplinas"]

    class DialogoFalso:
        def __init__(self, _parent, _d=None):
            self.resultado = Disciplina("FGA0211", "02", 673, grupo="calculo", prioridade="alta")

    monkeypatch.setattr(tela_mod, "DialogoDisciplina", DialogoFalso)
    monkeypatch.setattr(disc, "wait_window", lambda _w: None)
    disc._adicionar()
    assert ("add", ("FGA0211", "02", 673, "calculo", "alta")) in chamadas
    assert "execução em andamento" in disc.lbl_aplicado.cget("text")
    assert disc.tree.item("0", "values")[4] == "calculo"
    disc.tree.selection_set("0")
    disc._alternar_ativa()
    assert ("rem", "FGA0211-02") in chamadas
    app_gui._executor = None


# ── Fase 5 ───────────────────────────────────────────────────────────────

def test_observabilidade_na_gui(app_gui, monkeypatch, tmp_path, raiz_temporaria):
    import io
    import time
    import zipfile

    import httpx
    import app.gui.screens.diagnostico as diag_mod
    from app.core import engine
    from tests.test_engine_fluxo import SigaaSimulado, montar, rodar_ate

    # Dashboard: última tentativa com as etapas.
    simulado = SigaaSimulado(vagas=2)
    original = httpx.AsyncClient
    monkeypatch.setattr(engine.httpx, "AsyncClient", lambda *a, **k: original(*a, **{**k, "transport": httpx.MockTransport(simulado)}))
    motor, _ = montar(dry_run=True)
    rodar_ate(motor, lambda m: not m.alvos_ativos)
    app_gui._motor = motor
    dash = app_gui._telas["dashboard"]
    dash._atualizar()
    assert "sucesso (DRY RUN)" in dash.lbl_tentativa.cget("text") and "turma selecionada" in dash.lbl_tentativa.cget("text")

    # Diagnóstico: completo com segurança, recomendações, páginas e pacote de suporte.
    tela = app_gui._telas["diagnostico"]
    tela._rodar_thread()
    app_gui.update()
    assert "Segurança: Carga alta" in tela.txt.get("1.0", "end")
    tela._recomendacoes()
    assert "Nenhuma recomendação agora" in tela.txt.get("1.0", "end")
    tela._paginas()
    assert "Nenhuma página capturada" in tela.txt.get("1.0", "end")
    (raiz_temporaria / "logs").mkdir(exist_ok=True)
    (raiz_temporaria / "logs" / f"debug_W0_selecao_falha_FGA0211_{int(time.time())}.html").write_text(
        "<div id='info-usuario'>JOAO</div><p>Turma lotada</p>", encoding="utf-8")
    destino = tmp_path / "suporte.zip"
    monkeypatch.setattr(diag_mod.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(diag_mod.filedialog, "asksaveasfilename", lambda **k: str(destino))
    tela._pacote()
    nomes = zipfile.ZipFile(io.BytesIO(destino.read_bytes())).namelist()
    assert "LEIA-ME.txt" in nomes and any(n.startswith("paginas/") for n in nomes)
    assert "Pacote de suporte salvo" in tela.txt.get("1.0", "end")

    # Configurações avançadas: alertas por limiar entram nas configurações salvas.
    av = app_gui._telas["avancado"]
    av.var_alerta_taxa.set(45)
    assert av._coletar_settings_da_tela()["alertas"]["taxa_erro_pct"] == 45


# ── Fase 6 ───────────────────────────────────────────────────────────────

def test_perfis_versoes_e_acoes_na_gui(app_gui, monkeypatch):
    import app.gui.screens.avancado as av_mod
    from tkinter import simpledialog
    av = app_gui._telas["avancado"]
    monkeypatch.setattr(simpledialog, "askstring", lambda *a, **k: "Calmo")
    monkeypatch.setattr(av_mod.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(av_mod.messagebox, "showinfo", lambda *a, **k: None)
    av._salvar_perfil()
    assert av.var_perfil.get() == "Calmo" and list(av.combo_perfis["values"]) == ["Calmo"]
    app_gui.settings["num_workers"] = 3
    app_gui.salvar_settings()
    av._aplicar_perfil()
    assert app_gui.settings["num_workers"] == 20 and av.var_workers.get() == 20  # telas recarregadas
    janela = av._versoes()
    arvore = [w for w in janela.winfo_children() if w.winfo_class() == "Treeview"][0]
    assert arvore.get_children()
    janela.destroy()
    av._apagar_perfil()
    assert list(av.combo_perfis["values"]) == []
    arvore = app_gui._telas["historico"]._acoes()
    acoes = [arvore.item(i, "values")[1] for i in arvore.get_children()]
    assert "Aplicou um perfil" in acoes and "Salvou um perfil" in acoes
    arvore.winfo_toplevel().destroy()
    assert "Lista embutida" in app_gui._telas["disciplinas"].lbl_deptos.cget("text")


def test_novos_canais_de_notificacao_na_gui(app_gui):
    tela = app_gui._telas["notificacoes"]
    tela.var_webhook_ativo.set(True)
    tela.var_webhook_url.set("http://inseguro")
    tela._salvar_config()
    assert "https" in tela.lbl_status.cget("text") and app_gui.sessao.notificacao.webhook_url == ""
    tela.var_webhook_url.set("https://discord.com/api/webhooks/1/x")
    tela.var_email_ativo.set(True)
    tela.vars_email["servidor"].set("smtp.exemplo.com")
    tela._salvar_config()  # e-mail ativo sem usuário/destinatário: recusado antes de mexer na configuração
    assert "e-mail" in tela.lbl_status.cget("text") and not app_gui.settings["notificacoes"]["email_ativo"]
    tela.vars_email["usuario"].set("eu@exemplo.com")
    tela.vars_email["destinatario"].set("eu@exemplo.com")
    tela.var_email_seguranca.set("ssl")
    tela.var_email_senha.set("pw")
    tela._salvar_config()
    cfg = app_gui.settings["notificacoes"]
    assert cfg["webhook_ativo"] and cfg["email"]["servidor"] == "smtp.exemplo.com" and cfg["email"]["seguranca"] == "ssl"
    assert app_gui.sessao.notificacao.webhook_url.startswith("https://") and app_gui.sessao.notificacao.email_senha == "pw"


# ── Pós-6.0.0 ────────────────────────────────────────────────────────────

def test_assistente_inicial_da_gui(app_gui, monkeypatch, raiz_temporaria):
    import app.gui.wizard_primeira_execucao as wiz
    from app.core.config import carregar_settings
    monkeypatch.setattr(wiz.messagebox, "showinfo", lambda *a, **k: None)
    w = wiz.AssistentePrimeiraExecucao(app_gui, app_gui)
    w._proximo()                                   # boas-vindas → credenciais
    w.dados["credenciais"].update({"usuario": "200012345", "senha": "s", "cpf": "123", "nascimento": "01/02/2003"})
    w._proximo()
    assert w.etapa == 1 and "11 dígitos" in w.lbl_erros.cget("text")   # não avança com CPF inválido
    w.dados["credenciais"]["cpf"] = "12345678909"
    w._proximo()
    assert w.etapa == 2
    w.dados["disciplinas"].append({"codigo": "FGA0211", "turma": "01", "departamento": "673", "grupo": "", "prioridade": "normal"})
    w._proximo(); w._proximo()                      # execução (padrões válidos)
    w.dados["notificacoes"].update({"webhook_ativo": True, "webhook_url": "http://inseguro"})
    w._proximo()
    assert w.etapa == 4 and "https://" in w.lbl_erros.cget("text")
    w.dados["notificacoes"]["webhook_ativo"] = False
    w._proximo(); w._voltar(); w._proximo(); w._proximo()   # voltar funciona
    assert w.etapa == 6
    w._proximo()                                   # concluir
    s = carregar_settings()
    assert s["assistente_concluido"] and app_gui.disciplinas[0].chave() == "FGA0211-01" and app_gui.sessao.sigaa.cpf == "123.456.789-09"


def test_seletor_de_departamentos_da_gui(app_gui):
    from app.gui.escolher_departamento import EscolherDepartamento
    j = EscolherDepartamento(app_gui)
    assert j.lista.size() > 100
    j.var_busca.set("gama")
    assert j.lista.size() >= 1 and "673" in j.lista.get(0)
    j.lista.selection_set(0)
    j._escolher()
    assert j.resultado[0] == 673
