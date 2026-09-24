"""
Janela obrigatória de aviso legal — seções 94.8-94.11.

Aparece em TODA execução da GUI, sem exceção, e sem opção de "não mostrar de
novo" (isso não é persistido em nenhum arquivo). O botão de continuar só
libera quando as 5 confirmações estiverem marcadas.

CORREÇÃO DE USABILIDADE (bug real relatado pelo usuário): antes, os 5
checkboxes com texto longo + os botões podiam ficar fora da área visível em
telas menores, sem nenhuma pista de que dava pra rolar. Agora:
  - o tamanho da janela é calculado a partir da resolução real da tela
    (nunca maior do que ela cabe), ver app/gui/responsive.py;
  - os 5 checkboxes + os botões ficam numa área FIXA na parte de baixo, que
    o gerenciador de layout sempre reserva primeiro (pack(side="bottom")
    antes da área rolável) — ela NUNCA é espremida para fora da tela;
  - o texto de cada checkbox foi resumido a uma linha (o texto completo de
    cada item continua 100% presente, sem cortes, na área de leitura rolável
    logo acima, que é só para a íntegra do disclaimer — nada foi removido).
"""
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk

from app.core.disclaimer import CONFIRMACOES, RESUMOS_CURTOS, TEXTO_COMPLETO, TITULO
from app.gui.responsive import aplicar_geometria_responsiva
from app.versao import URL_REPOSITORIO
from app.gui.tema import cor


class DialogoAvisoLegal(tk.Toplevel):
    """Uso: dlg = DialogoAvisoLegal(root); root.wait_window(dlg); if not dlg.aceito: sair."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title(TITULO)
        aplicar_geometria_responsiva(self, largura_ideal=680, altura_ideal=680, largura_min=520, altura_min=520)
        self.aceito = False

        self.protocol("WM_DELETE_WINDOW", self._recusar)
        self.deiconify()  # garante que a janela não herde um estado "withdrawn" do pai
        self.transient(parent)

        self._construir()

        # grab_set() pode falhar com "window not viewable" se chamado antes da
        # janela ser realmente mapeada pelo gerenciador de janelas — força a
        # atualização primeiro (bug real encontrado: sem isso, em alguns casos
        # o diálogo travava invisível e o programa ficava esperando um clique
        # que nunca podia acontecer). Ver app/gui/app.py para o resto da causa.
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            self.after(50, self._tentar_grab_novamente)

        self._after_id_centralizar = self.after(100, self._centralizar)
        # <Destroy> cobre também o caso de destruição em cascata (quando a
        # janela PAI é destruída e o Tcl destrói este Toplevel diretamente,
        # sem necessariamente passar pelo destroy() Python sobrescrito abaixo)
        # — bug real encontrado em teste (ver app/gui/screens/dashboard.py).
        self.bind("<Destroy>", lambda _e: self._cancelar_centralizacao(), add="+")

    def _cancelar_centralizacao(self):
        after_id = getattr(self, "_after_id_centralizar", None)
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
            self._after_id_centralizar = None

    def _tentar_grab_novamente(self):
        if self.winfo_exists():
            try:
                self.grab_set()
            except tk.TclError:
                pass  # segue sem grab modal em vez de travar — melhor que uma janela invisível

    def destroy(self):
        # Cancela o callback agendado de centralização — sem isso, fechar a janela
        # rápido demais (ex: em testes automatizados, ou um clique muito rápido do
        # usuário) faz o Tk tentar rodar o callback depois que o widget já morreu,
        # jogando "invalid command name" no console (cosmético, mas evitável).
        after_id = getattr(self, "_after_id_centralizar", None)
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
        super().destroy()

    def _centralizar(self):
        if not self.winfo_exists():
            return  # janela já foi fechada (usuário decidiu rápido) — nada a fazer
        self.update_idletasks()
        largura, altura = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (largura // 2)
        y = (self.winfo_screenheight() // 2) - (altura // 2)
        self.geometry(f"+{x}+{y}")

    def _construir(self):
        # ── ÁREA FIXA (sempre visível, empacotada PRIMEIRO com side="bottom") ──
        # Isso garante que o gerenciador de layout reserva o espaço dela antes
        # de dar o restante pra área rolável — os checkboxes e botões NUNCA
        # ficam de fora, mesmo numa janela pequena.
        rodape = ttk.Frame(self, padding=(16, 8))
        rodape.pack(side="bottom", fill="x")
        link = ttk.Label(rodape, text="🔗 Repositório oficial no GitHub", foreground=cor("#0969da"), cursor="hand2")
        link.pack(side="left")
        link.bind("<Button-1>", lambda _e: webbrowser.open(URL_REPOSITORIO))
        ttk.Button(rodape, text="Recusar e sair", command=self._recusar).pack(side="right")
        self.btn_continuar = ttk.Button(rodape, text="Aceitar e continuar", command=self._aceitar, state="disabled")
        self.btn_continuar.pack(side="right", padx=(0, 8))

        ttk.Separator(self, orient="horizontal").pack(side="bottom", fill="x")

        frame_check = ttk.LabelFrame(self, text="Confirme todos os pontos para continuar", padding=(16, 10))
        frame_check.pack(side="bottom", fill="x", padx=16, pady=(0, 8))

        self.vars_confirmacao = {}
        for chave, texto_completo in CONFIRMACOES:
            var = tk.BooleanVar(value=False)
            self.vars_confirmacao[chave] = var
            linha = ttk.Frame(frame_check)
            linha.pack(fill="x", pady=1)
            cb = ttk.Checkbutton(linha, variable=var, command=self._atualizar_botao)
            cb.pack(side="left", anchor="n")
            resumo = RESUMOS_CURTOS.get(chave, texto_completo[:80])
            ttk.Label(linha, text=resumo, wraplength=560, justify="left").pack(side="left", anchor="w", padx=(4, 0))
            # Um label clicável sozinho não marca a caixa (evita concordância sem ler) —
            # só o próprio checkbox alterna o estado, de propósito.

        ttk.Label(
            frame_check, foreground=cor("#666"), wraplength=560, justify="left",
            text="(o texto completo de cada item está disponível na íntegra do aviso acima ↑)",
        ).pack(anchor="w", pady=(4, 0))

        # ── ÁREA ROLÁVEL (texto completo do disclaimer, ocupa o espaço restante) ──
        topo = ttk.Frame(self, padding=(16, 12, 16, 4))
        topo.pack(side="top", fill="x")
        ttk.Label(topo, text="⚠️ Antes de continuar, leia o aviso completo abaixo:", font=("Segoe UI", 12, "bold")).pack(anchor="w")

        frame_texto = ttk.Frame(self, padding=(16, 0))
        frame_texto.pack(side="top", fill="both", expand=True)
        scroll = ttk.Scrollbar(frame_texto)
        scroll.pack(side="right", fill="y")
        txt = tk.Text(frame_texto, wrap="word", yscrollcommand=scroll.set, height=8)
        txt.insert("1.0", TEXTO_COMPLETO)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)
        scroll.config(command=txt.yview)

    def _atualizar_botao(self):
        todas_marcadas = all(v.get() for v in self.vars_confirmacao.values())
        self.btn_continuar.config(state="normal" if todas_marcadas else "disabled")

    def _aceitar(self):
        if not all(v.get() for v in self.vars_confirmacao.values()):
            return  # defesa extra — nunca deveria acontecer, o botão já fica desabilitado
        self.aceito = True
        self.destroy()

    def _recusar(self):
        self.aceito = False
        self.destroy()
