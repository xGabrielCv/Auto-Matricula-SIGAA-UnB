"""
Tela de Credenciais — seção 5-8 do pedido.

Regra inegociável: nada digitado aqui é gravado em disco pelo app. Os campos
alimentam diretamente app.sessao.sigaa (memória de processo) e somem quando
o programa fecha. O aviso de privacidade fica sempre visível, não escondido
num tooltip ou rodapé pequeno.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from app.gui.responsive import tornar_rolavel


class TelaCredenciais(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self._construir()

    def _construir(self):
        corpo = tornar_rolavel(self)
        ttk.Label(corpo, text="Credenciais do SIGAA", font=("Segoe UI", 14, "bold")).pack(anchor="w")

        aviso = ttk.Frame(corpo, padding=12, relief="solid", borderwidth=1)
        aviso.pack(fill="x", pady=(10, 20))
        ttk.Label(aviso, text="🔒 Privacidade e segurança", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(
            aviso,
            wraplength=560,
            justify="left",
            text=(
                "Suas credenciais NÃO são armazenadas pelo aplicativo em nenhum arquivo.\n"
                "Elas ficam apenas na memória desta execução e são apagadas assim que o\n"
                "programa é fechado. Você precisará informá-las novamente na próxima vez\n"
                "que abrir o SIGAA Sniper."
            ),
        ).pack(anchor="w", pady=(4, 0))

        campos = ttk.Frame(corpo)
        campos.pack(fill="x")
        campos.columnconfigure(1, weight=1)

        cred = self.app.sessao.sigaa

        self.var_usuario = tk.StringVar(value=cred.usuario)
        self.var_senha = tk.StringVar(value=cred.senha)
        self.var_cpf = tk.StringVar(value=cred.cpf)
        self.var_nascimento = tk.StringVar(value=cred.nascimento)

        linhas = [
            ("Matrícula / usuário do SIGAA:", self.var_usuario, False),
            ("Senha:", self.var_senha, True),
            ("CPF (apenas números):", self.var_cpf, False),
            ("Data de nascimento (DD/MM/AAAA):", self.var_nascimento, False),
        ]
        for i, (rotulo, var, oculto) in enumerate(linhas):
            ttk.Label(campos, text=rotulo).grid(row=i, column=0, sticky="w", pady=6, padx=(0, 10))
            entrada = ttk.Entry(campos, textvariable=var, show="•" if oculto else "", width=40)
            entrada.grid(row=i, column=1, sticky="ew", pady=6)

        botoes = ttk.Frame(corpo)
        botoes.pack(fill="x", pady=(20, 0))
        ttk.Button(botoes, text="Salvar para esta execução", command=self._salvar).pack(side="left")
        ttk.Button(botoes, text="Limpar campos", command=self._limpar).pack(side="left", padx=(10, 0))

        self.lbl_status = ttk.Label(corpo, text="", foreground="#1a7f37")
        self.lbl_status.pack(anchor="w", pady=(10, 0))

    def recarregar(self):
        cred = self.app.sessao.sigaa
        self.var_usuario.set(cred.usuario)
        self.var_senha.set(cred.senha)
        self.var_cpf.set(cred.cpf)
        self.var_nascimento.set(cred.nascimento)

    def _salvar(self):
        cred = self.app.sessao.sigaa
        cred.usuario = self.var_usuario.get().strip()
        cred.senha = self.var_senha.get()
        cred.cpf = self.var_cpf.get().strip()
        cred.nascimento = self.var_nascimento.get().strip()

        if not cred.preenchida():
            messagebox.showwarning("Campos incompletos", "Preencha matrícula, senha, CPF e data de nascimento.")
            return
        self.lbl_status.config(text="✅ Credenciais mantidas em memória para esta execução (nada foi salvo em disco).")

    def _limpar(self):
        self.var_usuario.set("")
        self.var_senha.set("")
        self.var_cpf.set("")
        self.var_nascimento.set("")
        self.app.sessao.sigaa.limpar()
        self.lbl_status.config(text="Campos apagados da tela e da memória.")
