"""
Lista de departamentos para escolher (desde a 6.1.0).

A lista só abre quando a pessoa clica em "Ver departamentos" — nada de lista
pulando enquanto se digita. Mostra todos os departamentos, com pesquisa por
nome ou código; clicar duas vezes (ou Enter) escolhe.
"""
from __future__ import annotations

import tkinter as tk
import unicodedata
from tkinter import ttk
from typing import Optional, Tuple

from app.gui.tema import cor


def _normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


class EscolherDepartamento(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Departamentos")
        self.resultado: Optional[Tuple[int, str]] = None
        self.transient(parent)
        self.geometry("620x480")
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Pesquisar por nome ou código:").pack(anchor="w")
        self.var_busca = tk.StringVar()
        entrada = ttk.Entry(frame, textvariable=self.var_busca, width=50)
        entrada.pack(fill="x", pady=(2, 6))
        self.lbl_status = ttk.Label(frame, text="Carregando a lista…", foreground=cor("#57606a"))
        self.lbl_status.pack(anchor="w")
        caixa = ttk.Frame(frame)
        caixa.pack(fill="both", expand=True, pady=(6, 0))
        rolagem = ttk.Scrollbar(caixa)
        rolagem.pack(side="right", fill="y")
        self.lista = tk.Listbox(caixa, activestyle="dotbox", yscrollcommand=rolagem.set)
        self.lista.pack(side="left", fill="both", expand=True)
        rolagem.config(command=self.lista.yview)
        botoes = ttk.Frame(frame)
        botoes.pack(fill="x", pady=(8, 0))
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(botoes, text="Escolher", command=self._escolher).pack(side="right", padx=(0, 6))
        self.lista.bind("<Double-Button-1>", lambda _e: self._escolher())
        self.lista.bind("<Return>", lambda _e: self._escolher())
        entrada.bind("<Return>", lambda _e: self._escolher())
        entrada.bind("<Down>", lambda _e: (self.lista.focus_set(), self.lista.selection_set(0)))
        self.var_busca.trace_add("write", lambda *_: self._filtrar())
        self._todos = []
        self._visiveis = []
        self._carregar()
        entrada.focus_set()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _carregar(self):
        try:
            from app.core.departamentos import info_lista, listar_departamentos
            self._todos = [(d.codigo, d.nome) for d in listar_departamentos()]
            self._info = info_lista()["texto"]
        except Exception as e:  # nunca deixa a janela quebrada
            self._todos, self._info = [], f"Não foi possível carregar a lista ({type(e).__name__}) — digite o código no campo."
        self._filtrar()

    def _filtrar(self):
        termo = _normalizar(self.var_busca.get().strip())
        self._visiveis = [d for d in self._todos if not termo or termo == str(d[0]) or termo in _normalizar(d[1])]
        self.lista.delete(0, "end")
        for codigo, nome in self._visiveis:
            self.lista.insert("end", f"{codigo:>5}  {nome}")
        if not self._todos:
            self.lbl_status.config(text=self._info)
        elif not self._visiveis:
            self.lbl_status.config(text="Nenhum departamento com esse nome ou código.")
        else:
            self.lbl_status.config(text=f"{len(self._visiveis)} de {len(self._todos)} · {self._info}")

    def _escolher(self):
        sel = self.lista.curselection()
        if not sel and len(self._visiveis) == 1:
            sel = (0,)
        if sel:
            self.resultado = self._visiveis[sel[0]]
            self.destroy()


def escolher_departamento(parent) -> Optional[Tuple[int, str]]:
    janela = EscolherDepartamento(parent)
    parent.wait_window(janela)
    return janela.resultado
