"""Tela de Execução — seções 4, 10, 11, 12 do pedido: escolher modo, iniciar/parar."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from app.core.config import validar_disciplinas, validar_settings
from app.gui.responsive import tornar_rolavel


class TelaExecucao(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self._construir()

    def _construir(self):
        corpo = tornar_rolavel(self)  # garante que nada fique inacessível em janelas menores

        ttk.Label(corpo, text="Execução", font=("Segoe UI", 14, "bold")).pack(anchor="w")

        modo_frame = ttk.LabelFrame(corpo, text="Modo de operação", padding=12)
        modo_frame.pack(fill="x", pady=(14, 10))

        self.var_modo = tk.StringVar(value=self.app.settings["modo"])
        ttk.Radiobutton(
            modo_frame, text="Matrícula automática — tenta se matricular assim que achar vaga",
            variable=self.var_modo, value="matricula", command=self._atualizar_visibilidade,
        ).pack(anchor="w")
        ttk.Radiobutton(
            modo_frame, text="Somente monitoramento — avisa quando achar vaga, nunca matricula sozinho",
            variable=self.var_modo, value="monitoramento", command=self._atualizar_visibilidade,
        ).pack(anchor="w")

        self.frame_matricula = ttk.Frame(corpo)
        self.frame_matricula.pack(fill="x", pady=(0, 10))
        self.var_dry_run = tk.BooleanVar(value=self.app.settings["dry_run"])
        ttk.Checkbutton(
            self.frame_matricula,
            text="Modo de teste (DRY RUN) — simula tudo, mas não confirma a matrícula de verdade",
            variable=self.var_dry_run,
        ).pack(anchor="w")

        agenda_frame = ttk.LabelFrame(corpo, text="Agendar início (opcional)", padding=12)
        agenda_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(agenda_frame, text="Formato: DD/MM/AAAA HH:MM:SS — deixe em branco para começar imediatamente").pack(anchor="w")
        self.var_agendar = tk.StringVar(value=self.app.settings.get("agendar_inicio") or "")
        ttk.Entry(agenda_frame, textvariable=self.var_agendar, width=30).pack(anchor="w", pady=(4, 0))

        acoes = ttk.Frame(corpo)
        acoes.pack(fill="x", pady=(10, 0))
        self.btn_iniciar = ttk.Button(acoes, text="▶️ Iniciar", command=self._iniciar)
        self.btn_iniciar.pack(side="left")
        self.btn_parar = ttk.Button(acoes, text="⏹️ Parar", command=self._parar, state="disabled")
        self.btn_parar.pack(side="left", padx=(8, 0))

        self.lbl_status = ttk.Label(corpo, text="Parado.", font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(anchor="w", pady=(14, 0))

        self._atualizar_visibilidade()

    def _atualizar_visibilidade(self):
        if self.var_modo.get() == "matricula":
            self.frame_matricula.pack(fill="x", pady=(0, 10))
        else:
            self.frame_matricula.pack_forget()

    def _validar_pronto(self) -> bool:
        if not self.app.sessao.sigaa.preenchida():
            messagebox.showwarning("Credenciais ausentes", "Preencha suas credenciais do SIGAA na aba Credenciais antes de iniciar.")
            return False

        problemas = validar_settings(self.app.settings) + validar_disciplinas(self.app.disciplinas)
        if problemas:
            messagebox.showwarning("Configuração inválida", "Antes de iniciar, corrija:\n\n" + "\n".join(f"• {p}" for p in problemas))
            return False
        return True

    def _iniciar(self):
        self.app.settings["modo"] = self.var_modo.get()
        self.app.settings["dry_run"] = self.var_dry_run.get()
        self.app.settings["agendar_inicio"] = self.var_agendar.get().strip() or None

        if not self._validar_pronto():
            return
        self.app.salvar_settings()

        try:
            self.app.iniciar_motor(ao_finalizar=self._ao_finalizar)
        except RuntimeError as e:
            messagebox.showerror("Já em execução", str(e))
            return

        self.btn_iniciar.config(state="disabled")
        self.btn_parar.config(state="normal")
        modo_txt = "Matrícula automática" if self.app.settings["modo"] == "matricula" else "Somente monitoramento"
        self.lbl_status.config(text=f"🟢 Em execução — {modo_txt}", foreground="#1a7f37")

        # Seção 21: a configuração "abrir dashboard ao iniciar" existia mas nunca
        # era lida em lugar nenhum — bug real encontrado na auditoria pós-correção
        # do travamento da GUI. Agora ela realmente troca de aba ao iniciar.
        if self.app.settings.get("abrir_dashboard_ao_iniciar"):
            self.app._mostrar("dashboard")

    def _parar(self):
        self.app.parar_motor()
        self.lbl_status.config(text="🟡 Parando... (aguardando workers atuais encerrarem)", foreground="#9a6700")
        self.btn_parar.config(state="disabled")

    def _ao_finalizar(self, erro):
        def atualizar():
            self.btn_iniciar.config(state="normal")
            self.btn_parar.config(state="disabled")
            if erro:
                self.lbl_status.config(text=f"🔴 Encerrado com erro: {erro}", foreground="#cf222e")
            else:
                self.lbl_status.config(text="⚪ Parado.", foreground="black")
        self.after(0, atualizar)
