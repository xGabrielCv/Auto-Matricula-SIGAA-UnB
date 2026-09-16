"""
Janela principal da GUI — seção 4 do pedido.

Navegação lateral simples (lista de botões) trocando o frame de conteúdo,
para ficar fácil de auditar (seção 51): cada tela é um arquivo em
app/gui/screens/, sem frameworks extras além de tkinter/ttk (decisão tomada
com o usuário: Tkinter + ttk puro, zero dependência de GUI extra).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional

from app.core.config import carregar_disciplinas, carregar_settings, carregar_segredos_notificacao, salvar_settings
from app.core.credentials import encerrar_sessao, obter_sessao
from app.core.factory import construir_motor
from app.core.diagnostics import VERSAO_APP
from app.core.runner import ExecutorMotor
from app.utils.cleanup import limpar_debug_dumps

from app.gui.screens.credenciais import TelaCredenciais
from app.gui.screens.disciplinas import TelaDisciplinas
from app.gui.screens.execucao import TelaExecucao
from app.gui.screens.notificacoes import TelaNotificacoes
from app.gui.screens.avancado import TelaAvancado
from app.gui.screens.dashboard import TelaDashboard
from app.gui.screens.logs import TelaLogs
from app.gui.screens.diagnostico import TelaDiagnostico
from app.gui.screens.experimental import TelaExperimental
from app.gui.screens.ajuda import TelaAjuda
from app.gui.screens.sobre import TelaSobre
from app.gui.disclaimer_dialog import DialogoAvisoLegal
from app.gui.responsive import aplicar_geometria_responsiva


class SniperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"SIGAA Sniper — v{VERSAO_APP}")
        # Bug real relatado pelo usuário: um tamanho fixo (980x680) podia ser
        # maior que a tela disponível (notebooks menores, escala de DPI),
        # abrindo a janela cortada sem indicação de que dava pra rolar.
        # Agora o tamanho é calculado a partir da resolução real da tela,
        # nunca ultrapassando 90% dela, e cada tela internamente também é
        # rolável (ver app/gui/responsive.py) como segunda camada de segurança.
        aplicar_geometria_responsiva(self, largura_ideal=1080, altura_ideal=740, largura_min=760, altura_min=560)
        self.aceitou_aviso_legal = True

        # Aviso legal obrigatório em TODA execução (seção 94.8) — mostrado
        # como um modal (grab_set) por cima da janela principal, e "aceitar
        # antes" não é lembrado entre execuções (nada aqui é salvo em disco).
        #
        # BUG REAL CORRIGIDO: a versão anterior escondia a janela principal
        # com self.withdraw() ANTES de criar o diálogo transient(self). No
        # Windows, uma janela transient de um "owner" escondido também fica
        # travada em estado "withdrawn" e nunca é exibida de verdade — o
        # programa ficava esperando para sempre um clique numa janela
        # invisível (terminal "travado", GUI nunca abria). Confirmado com
        # `winfo_viewable()`/`state()` antes e depois da correção: a janela
        # simplesmente nunca era mapeada na tela. A correção é manter a
        # janela principal visível (nunca escondida) antes de abrir o
        # diálogo transient — o grab_set() já impede qualquer interação com
        # ela enquanto o aviso não for respondido, então não há problema em
        # deixá-la visível (em branco) por trás do aviso.
        self.update_idletasks()
        dlg = DialogoAvisoLegal(self)
        self.wait_window(dlg)
        if not dlg.aceito:
            self.aceitou_aviso_legal = False
            self.destroy()
            return

        self.sessao = obter_sessao()
        self.settings = carregar_settings()
        self.disciplinas = carregar_disciplinas()

        segredos = carregar_segredos_notificacao()
        if segredos:
            self.sessao.notificacao.telegram_token = segredos.get("telegram_token", "")
            self.sessao.notificacao.telegram_chat_id = segredos.get("telegram_chat_id", "")
            self.sessao.notificacao.ntfy_topic = segredos.get("ntfy_topic", "")

        self._executor: Optional[ExecutorMotor] = None

        limpar_debug_dumps(manter=self.settings["logs"]["arquivos_mantidos"])  # limpeza automática silenciosa ao abrir (seção 28)

        self._construir_layout()
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)
        self._checar_encerramento_anterior()
        self._talvez_mostrar_assistente_primeira_execucao()

    def _talvez_mostrar_assistente_primeira_execucao(self):
        """Seção 74 — só na primeira vez (nenhuma configuração salva ainda)."""
        from app.gui.wizard_primeira_execucao import AssistentePrimeiraExecucao, primeira_execucao
        if primeira_execucao(self.settings, self.disciplinas):
            AssistentePrimeiraExecucao(self, self)

    def _construir_layout(self):
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)

        sidebar = ttk.Frame(container, width=190, padding=10)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        ttk.Label(sidebar, text="SIGAA Sniper", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(sidebar, text=f"Versão {VERSAO_APP}", foreground="#666", font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 16))

        self.conteudo = ttk.Frame(container)
        self.conteudo.pack(side="left", fill="both", expand=True)

        self._telas = {}
        self._registrar_tela("execucao", "▶️ Execução", TelaExecucao)
        self._registrar_tela("dashboard", "📊 Dashboard", TelaDashboard)
        self._registrar_tela("logs", "📜 Logs", TelaLogs)
        self._registrar_tela("credenciais", "🔑 Credenciais", TelaCredenciais)
        self._registrar_tela("disciplinas", "📚 Disciplinas", TelaDisciplinas)
        self._registrar_tela("notificacoes", "🔔 Notificações", TelaNotificacoes)
        self._registrar_tela("avancado", "⚙️ Config. Avançadas", TelaAvancado)
        self._registrar_tela("diagnostico", "🩺 Diagnóstico", TelaDiagnostico)
        self._registrar_tela("experimental", "🧪 Experimental", TelaExperimental)
        self._registrar_tela("ajuda", "❓ Ajuda", TelaAjuda)
        self._registrar_tela("sobre", "ℹ️ Sobre", TelaSobre)

        for nome, rotulo, _cls in self._ordem_menu:
            ttk.Button(sidebar, text=rotulo, command=lambda n=nome: self._mostrar(n)).pack(fill="x", pady=2)

        self._mostrar("execucao")

    def _registrar_tela(self, nome, rotulo, classe):
        if not hasattr(self, "_ordem_menu"):
            self._ordem_menu = []
        self._ordem_menu.append((nome, rotulo, classe))
        frame = classe(self.conteudo, self)
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._telas[nome] = frame

    def _mostrar(self, nome):
        self._telas[nome].tkraise()

    def _checar_encerramento_anterior(self):
        """Seção 54: avisa se a execução anterior do motor não terminou de forma
        controlada — sem nunca assumir que uma matrícula foi confirmada por causa disso."""
        from app.core.crash_recovery import verificar_encerramento_anterior
        marcador = verificar_encerramento_anterior()
        if marcador:
            messagebox.showwarning(
                "Execução anterior não finalizada normalmente",
                f"A execução anterior do motor (iniciada em {marcador.get('inicio', '?')}, "
                f"modo: {marcador.get('modo', '?')}) não foi encerrada de forma controlada — "
                "o programa pode ter sido fechado abruptamente ou travado.\n\n"
                "Isso NÃO significa que uma matrícula foi confirmada. Se tiver dúvida, "
                "verifique manualmente no SIGAA.",
            )

    # ── Ponte com o motor assíncrono (rodando em thread separada) ──────────

    def salvar_settings(self):
        salvar_settings(self.settings)

    def iniciar_motor(self, ao_finalizar: Callable[[Optional[Exception]], None]):
        if self._executor and self._executor.em_execucao():
            raise RuntimeError("O motor já está em execução. Pare antes de iniciar de novo.")
        motor = construir_motor(self.settings, self.sessao, self.disciplinas)
        self._executor = ExecutorMotor(motor, ao_finalizar=ao_finalizar)
        self._executor.iniciar()

    def parar_motor(self):
        if self._executor:
            self._executor.parar()

    def _ao_fechar(self):
        if self._executor and self._executor.em_execucao():
            if not messagebox.askyesno("Sair", "O monitor ainda está em execução. Parar e sair mesmo assim?"):
                return
            self._executor.parar()
            self._executor.aguardar(timeout=5)
        encerrar_sessao()  # apaga credenciais da memória antes de fechar
        self.destroy()


def main():
    app = SniperApp()
    if not app.aceitou_aviso_legal:
        return  # usuário recusou o aviso legal — a janela já foi destruída, não há o que rodar
    app.mainloop()


if __name__ == "__main__":
    main()
