"""Tela de Ajuda — seções 41-42 do pedido. Lê docs/*.md locais, sem depender de internet."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from app.utils.paths import pasta_docs


class TelaAjuda(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self._construir()

    def _construir(self):
        ttk.Label(self, text="Ajuda / Guia de uso", font=("Segoe UI", 14, "bold")).pack(anchor="w")

        abas = ttk.Notebook(self)
        abas.pack(fill="both", expand=True, pady=(10, 0))

        for nome_arquivo, titulo in [("GUIA_DE_USO.md", "Guia de uso"), ("SEGURANCA.md", "Segurança e privacidade")]:
            aba = ttk.Frame(abas)
            abas.add(aba, text=titulo)
            self._carregar_texto(aba, nome_arquivo)

    def _carregar_texto(self, parent, nome_arquivo):
        caminho = os.path.join(pasta_docs(), nome_arquivo)
        scroll = ttk.Scrollbar(parent)
        scroll.pack(side="right", fill="y")
        texto_widget = tk.Text(parent, wrap="word", padx=10, pady=10, yscrollcommand=scroll.set)
        texto_widget.tag_configure("titulo", font=("Segoe UI", 12, "bold"), spacing3=6)
        texto_widget.pack(side="left", fill="both", expand=True)
        scroll.config(command=texto_widget.yview)

        if not os.path.exists(caminho):
            texto_widget.insert("1.0", "Arquivo de ajuda não encontrado.")
        else:
            with open(caminho, "r", encoding="utf-8") as f:
                for linha in f:
                    if linha.startswith("#"):
                        texto_widget.insert("end", linha.lstrip("#").strip() + "\n", "titulo")
                    else:
                        texto_widget.insert("end", linha)
        texto_widget.config(state="disabled")
