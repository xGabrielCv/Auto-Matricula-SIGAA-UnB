"""Tela Experimental — seções 26-31 do pedido de continuação."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from app.experimental import Experimento, listar_experimentos
from app.gui.tema import cor


class TelaExperimental(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self._construir()

    def _construir(self):
        ttk.Label(self, text="Experimental", font=("Segoe UI", 14, "bold")).pack(anchor="w")

        aviso = ttk.Frame(self, padding=12, relief="solid", borderwidth=1)
        aviso.pack(fill="x", pady=(10, 16))
        ttk.Label(aviso, text="⚠️ Área experimental", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(
            aviso, wraplength=640, justify="left",
            text=(
                "Os recursos desta seção utilizam implementações alternativas encontradas nas "
                "versões antigas do projeto. Essas implementações não fazem parte do caminho "
                "principal validado e podem apresentar incompatibilidades, comportamento diferente, "
                "dependências adicionais ou simplesmente não funcionar.\n\n"
                "Utilize esses recursos apenas para testes e experimentação. Uma falha aqui nunca "
                "afeta o monitoramento/matrícula principal."
            ),
        ).pack(anchor="w", pady=(4, 0))

        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.frame_lista = ttk.Frame(canvas)
        self.frame_lista.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.frame_lista, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for exp in listar_experimentos():
            self._card_experimento(exp)

    def _card_experimento(self, exp: Experimento):
        card = ttk.LabelFrame(self.frame_lista, text=exp.nome, padding=10)
        card.pack(fill="x", pady=6, padx=(0, 10))

        ttk.Label(card, wraplength=600, justify="left", text=exp.descricao).pack(anchor="w")

        info = ttk.Frame(card)
        info.pack(fill="x", pady=(8, 0))
        ttk.Label(info, text=f"Origem: {exp.origem}", foreground=cor("#666")).pack(anchor="w")

        disponivel = exp.disponivel()
        cor_status = cor("#1a7f37") if disponivel else cor("#9a6700")
        ttk.Label(info, text=f"Status: {exp.status}", foreground=cor_status).pack(anchor="w")

        deps_txt = ", ".join(exp.dependencias) if exp.dependencias else "nenhuma (usa o que o programa principal já tem)"
        ttk.Label(info, text=f"Dependências: {deps_txt}", foreground=cor("#666")).pack(anchor="w")
        ttk.Label(info, text=f"Riscos/limitações: {exp.riscos}", foreground=cor("#666"), wraplength=600, justify="left").pack(anchor="w")

        botoes = ttk.Frame(card)
        botoes.pack(fill="x", pady=(8, 0))
        ttk.Button(botoes, text="▶️ Executar", command=lambda: self._executar(exp)).pack(side="left")
        if exp.parar:
            ttk.Button(botoes, text="⏹️ Parar", command=exp.parar).pack(side="left", padx=(6, 0))
        ttk.Button(botoes, text="📖 Ver guia", command=lambda: self._ver_guia(exp)).pack(side="left", padx=(6, 0))

        resultado = tk.Text(card, height=4, wrap="word", state="disabled", background=cor("#f6f8fa"))
        resultado.pack(fill="x", pady=(8, 0))
        exp._widget_resultado = resultado  # anexado dinamicamente só para esta tela

    def _executar(self, exp: Experimento):
        widget = getattr(exp, "_widget_resultado", None)
        if widget is None or exp.executar is None:
            return

        # Seção 81: confirmação obrigatória antes de rodar algo da área experimental.
        if not messagebox.askyesno(
            "Confirmar execução experimental",
            f"Você está prestes a executar o recurso experimental:\n\n\"{exp.nome}\"\n\n"
            "Isso usa uma implementação alternativa, não validada como o caminho principal, "
            "e pode se comportar de forma inesperada.\n\nDeseja continuar?",
        ):
            return

        self._escrever(widget, "Executando...")

        def alvo():
            try:
                resultado = exp.executar()
            except Exception as e:
                # Seção 30: uma falha experimental NUNCA pode derrubar o programa principal.
                resultado = f"❌ O experimento falhou (isso é esperado às vezes — é experimental): {type(e).__name__}: {e}"
            self.after(0, lambda: self._escrever(widget, resultado))

        threading.Thread(target=alvo, daemon=True).start()

    def _escrever(self, widget: tk.Text, texto: str):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", texto)
        widget.config(state="disabled")

    def _ver_guia(self, exp: Experimento):
        janela = tk.Toplevel(self)
        janela.title(f"Guia — {exp.nome}")
        janela.geometry("520x420")
        txt = tk.Text(janela, wrap="word", padx=10, pady=10)
        txt.insert("1.0", exp.guia_instalacao or "Nenhuma instalação adicional necessária para este experimento.")
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)
        ttk.Button(janela, text="Fechar", command=janela.destroy).pack(pady=6)
