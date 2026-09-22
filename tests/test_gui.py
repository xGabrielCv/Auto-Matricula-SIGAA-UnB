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
    esperadas = {"execucao", "dashboard", "logs", "credenciais", "disciplinas", "notificacoes",
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
