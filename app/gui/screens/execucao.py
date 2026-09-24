"""Tela de Execução — seções 4, 10, 11, 12 do pedido: escolher modo, iniciar/parar."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from app.core.config import validar_disciplinas, validar_settings
from app.gui.responsive import tornar_rolavel
from app.gui.tema import cor


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
        ttk.Label(agenda_frame, text="Encerrar automaticamente em (opcional, mesmo formato):").pack(anchor="w", pady=(8, 0))
        self.var_fim = tk.StringVar(value=self.app.settings.get("agendar_fim") or "")
        ttk.Entry(agenda_frame, textvariable=self.var_fim, width=30).pack(anchor="w", pady=(4, 0))

        # Fase 4: janela diária (035), relógio do SIGAA (038), verificação prévia (040).
        extras = ttk.LabelFrame(corpo, text="Janela diária, relógio do SIGAA e verificação prévia", padding=12)
        extras.pack(fill="x", pady=(0, 10))
        janela = {**{"ativa": False, "inicio": "07:00", "fim": "23:00", "dias": list(range(7))}, **(self.app.settings.get("janela") or {})}
        self.var_janela = tk.BooleanVar(value=janela["ativa"])
        ttk.Checkbutton(extras, text="Rodar só numa janela diária (fora dela as buscas pausam e voltam sozinhas)",
                        variable=self.var_janela).pack(anchor="w")
        linha = ttk.Frame(extras)
        linha.pack(anchor="w", pady=(4, 0))
        ttk.Label(linha, text="Das").pack(side="left")
        self.var_janela_ini = tk.StringVar(value=janela["inicio"])
        ttk.Entry(linha, textvariable=self.var_janela_ini, width=6).pack(side="left", padx=4)
        ttk.Label(linha, text="às").pack(side="left")
        self.var_janela_fim = tk.StringVar(value=janela["fim"])
        ttk.Entry(linha, textvariable=self.var_janela_fim, width=6).pack(side="left", padx=4)
        dias = ttk.Frame(extras)
        dias.pack(anchor="w", pady=(4, 0))
        self.vars_dias = []
        for i, nome in enumerate(["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]):
            var = tk.BooleanVar(value=i in janela["dias"])
            ttk.Checkbutton(dias, text=nome, variable=var).pack(side="left")
            self.vars_dias.append(var)
        self.var_relogio = tk.BooleanVar(value=bool(self.app.settings.get("agendamento_relogio_sigaa")))
        ttk.Checkbutton(extras, text="Agendar pelo relógio do SIGAA (corrige a diferença do relógio deste computador)",
                        variable=self.var_relogio).pack(anchor="w", pady=(6, 0))
        self.var_verificacao = tk.BooleanVar(value=self.app.settings.get("verificacao_previa", True))
        ttk.Checkbutton(extras, text="Verificar login e disciplinas antes de começar (recomendado)",
                        variable=self.var_verificacao).pack(anchor="w")

        # Fase 6 (077): modo demonstração com SIGAA simulado.
        self.var_demo = tk.BooleanVar(value=False)
        ttk.Checkbutton(corpo, text="🎓 Modo demonstração — SIGAA simulado neste computador, sem login e sem tocar no SIGAA "
                                    "(sempre em DRY RUN; nada vai para o histórico)",
                        variable=self.var_demo).pack(anchor="w", pady=(4, 0))

        acoes = ttk.Frame(corpo)
        acoes.pack(fill="x", pady=(10, 0))
        self.btn_iniciar = ttk.Button(acoes, text="▶️ Iniciar", command=self._iniciar)
        self.btn_iniciar.pack(side="left")
        self.btn_pausar = ttk.Button(acoes, text="⏸️ Pausar", command=self._alternar_pausa, state="disabled")
        self.btn_pausar.pack(side="left", padx=(8, 0))
        self.btn_parar = ttk.Button(acoes, text="⏹️ Parar", command=self._parar, state="disabled")
        self.btn_parar.pack(side="left", padx=(8, 0))

        self.lbl_status = ttk.Label(corpo, text="Parado.", font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(anchor="w", pady=(14, 0))

        self._atualizar_visibilidade()

    def recarregar(self):
        if str(self.btn_iniciar.cget("state")) == "disabled":
            return  # em execução: não mexe nos campos da execução atual
        self.var_modo.set(self.app.settings["modo"])
        self.var_dry_run.set(self.app.settings["dry_run"])
        self.var_agendar.set(self.app.settings.get("agendar_inicio") or "")
        self.var_fim.set(self.app.settings.get("agendar_fim") or "")
        self._atualizar_visibilidade()

    def _atualizar_visibilidade(self):
        if self.var_modo.get() == "matricula":
            self.frame_matricula.pack(fill="x", pady=(0, 10))
        else:
            self.frame_matricula.pack_forget()

    def _validar_pronto(self) -> bool:
        if self.var_demo.get():
            problemas = validar_settings(self.app.settings)
            if problemas:
                messagebox.showwarning("Configuração inválida", "Antes de iniciar, corrija:\n\n" + "\n".join(f"• {p}" for p in problemas))
                return False
            return True
        if not self.app.sessao.sigaa.preenchida():
            messagebox.showwarning("Credenciais ausentes", "Preencha suas credenciais do SIGAA na aba Credenciais antes de iniciar.")
            return False
        problemas_cred = self.app.sessao.sigaa.problemas()
        if problemas_cred:
            messagebox.showwarning("Credenciais com problema", "Corrija na aba Credenciais antes de iniciar:\n\n" + "\n".join(f"• {p}" for p in problemas_cred))
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
        self.app.settings["agendar_fim"] = self.var_fim.get().strip() or None
        self.app.settings["janela"] = {"ativa": self.var_janela.get(), "inicio": self.var_janela_ini.get().strip(),
                                       "fim": self.var_janela_fim.get().strip(),
                                       "dias": [i for i, v in enumerate(self.vars_dias) if v.get()]}
        self.app.settings["agendamento_relogio_sigaa"] = self.var_relogio.get()
        self.app.settings["verificacao_previa"] = self.var_verificacao.get()

        if not self._validar_pronto():
            return
        self.app.salvar_settings()

        try:
            self.app.iniciar_motor(ao_finalizar=self._ao_finalizar, demo=self.var_demo.get())
        except RuntimeError as e:
            messagebox.showerror("Já em execução", str(e))
            return

        self.btn_iniciar.config(state="disabled")
        self.btn_parar.config(state="normal")
        self.btn_pausar.config(state="normal", text="⏸️ Pausar")
        modo_txt = "Matrícula automática" if self.app.settings["modo"] == "matricula" else "Somente monitoramento"
        if self.var_demo.get():
            modo_txt = "DEMONSTRAÇÃO (SIGAA simulado) · " + modo_txt
        self.lbl_status.config(text=f"🟢 Em execução — {modo_txt}", foreground=cor("#1a7f37"))

        # Seção 21: a configuração "abrir dashboard ao iniciar" existia mas nunca
        # era lida em lugar nenhum — bug real encontrado na auditoria pós-correção
        # do travamento da GUI. Agora ela realmente troca de aba ao iniciar.
        if self.app.settings.get("abrir_dashboard_ao_iniciar"):
            self.app._mostrar("dashboard")

    def _alternar_pausa(self):
        """Sugestão 036: pausa sem perder as sessões; retomar não faz novo login."""
        if self.app.estado_execucao().get("pausado"):
            if not self.app.retomar_motor():
                messagebox.showinfo("Fora da janela", "A execução está fora da janela de execução e volta sozinha no próximo horário.")
                return
            self.btn_pausar.config(text="⏸️ Pausar")
        else:
            self.app.pausar_motor()
            self.btn_pausar.config(text="▶️ Retomar")

    def _parar(self):
        self.app.parar_motor()
        self.btn_pausar.config(state="disabled")
        self.lbl_status.config(text="🟡 Parando... (aguardando workers atuais encerrarem)", foreground=cor("#9a6700"))
        self.btn_parar.config(state="disabled")

    def _ao_finalizar(self, erro):
        def atualizar():
            self.btn_iniciar.config(state="normal")
            self.btn_parar.config(state="disabled")
            self.btn_pausar.config(state="disabled", text="⏸️ Pausar")
            if erro:
                self.lbl_status.config(text=f"🔴 Encerrado com erro: {erro}", foreground=cor("#cf222e"))
            else:
                self.lbl_status.config(text="⚪ Parado.", foreground=cor("black"))
        self.after(0, atualizar)
