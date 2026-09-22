"""
Assistente de primeira execução — seção 74 do pedido de continuação.

Aparece só quando não existe nenhuma configuração salva ainda (nem
settings.json nem disciplinas.json) — ou seja, de fato a primeira vez que
o programa é usado nesta instalação. Pode ser pulado a qualquer momento;
nenhuma etapa é obrigatória (seção 74: "não complique... permita pular
etapas").
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.core.config import Disciplina, salvar_disciplinas, salvar_settings
from app.core.departamentos import buscar_departamentos
from app.gui.responsive import aplicar_geometria_responsiva


def primeira_execucao(settings: dict, disciplinas: list) -> bool:
    """True se nenhuma configuração foi salva ainda nesta instalação."""
    import os
    from app.utils.paths import pasta_config
    return not os.path.exists(os.path.join(pasta_config(), "settings.json")) and not disciplinas


class AssistentePrimeiraExecucao(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Bem-vindo ao SIGAA Sniper")
        aplicar_geometria_responsiva(self, largura_ideal=620, altura_ideal=520, largura_min=480, altura_min=420)
        self.protocol("WM_DELETE_WINDOW", self._finalizar)
        self.deiconify()
        self.transient(parent)
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

        self.etapa = 0
        self.etapas = [
            self._etapa_boas_vindas, self._etapa_credenciais, self._etapa_disciplina,
            self._etapa_modo, self._etapa_notificacoes, self._etapa_finalizar,
        ]

        # Rodapé (Pular/Voltar/Próximo) empacotado PRIMEIRO com side="bottom" —
        # assim o gerenciador de layout reserva o espaço dele antes de dar o
        # resto pra área de conteúdo, garantindo que os botões nunca fiquem de
        # fora mesmo se uma etapa tiver bastante conteúdo (mesma correção do
        # aviso legal, ver app/gui/disclaimer_dialog.py).
        rodape = ttk.Frame(self, padding=(20, 10))
        rodape.pack(side="bottom", fill="x")
        ttk.Button(rodape, text="Pular assistente", command=self._finalizar).pack(side="left")
        self.btn_voltar = ttk.Button(rodape, text="◀ Voltar", command=self._voltar)
        self.btn_voltar.pack(side="right", padx=(6, 0))
        self.btn_proximo = ttk.Button(rodape, text="Próximo ▶", command=self._proximo)
        self.btn_proximo.pack(side="right")

        ttk.Separator(self, orient="horizontal").pack(side="bottom", fill="x")

        self.frame_conteudo = ttk.Frame(self, padding=20)
        self.frame_conteudo.pack(side="top", fill="both", expand=True)

        self._renderizar()
        self._after_id_centralizar = self.after(100, self._centralizar)
        # Usa o evento <Destroy> em vez de só sobrescrever destroy(): quando a
        # janela PAI é destruída (ex: app.destroy() fecha tudo em cascata), o
        # Tcl destrói este Toplevel diretamente sem necessariamente chamar um
        # destroy() Python sobrescrito — só o bind captura os dois casos
        # (fechamento explícito e em cascata). Mesma correção de
        # app/gui/screens/dashboard.py e logs.py.
        self.bind("<Destroy>", self._cancelar_centralizacao, add="+")

    def _cancelar_centralizacao(self, _event=None):
        after_id = getattr(self, "_after_id_centralizar", None)
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
            self._after_id_centralizar = None

    def _centralizar(self):
        if not self.winfo_exists():
            return
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def _limpar(self):
        for w in self.frame_conteudo.winfo_children():
            w.destroy()

    def _renderizar(self):
        self._limpar()
        self.btn_voltar.config(state="normal" if self.etapa > 0 else "disabled")
        self.btn_proximo.config(text="Finalizar" if self.etapa == len(self.etapas) - 1 else "Próximo ▶")
        self.etapas[self.etapa]()

    def _proximo(self):
        if self.etapa == len(self.etapas) - 1:
            self._finalizar()
            return
        self.etapa += 1
        self._renderizar()

    def _voltar(self):
        if self.etapa > 0:
            self.etapa -= 1
            self._renderizar()

    def _finalizar(self):
        self.app.settings = dict(self.app.settings)
        salvar_settings(self.app.settings)
        salvar_disciplinas(self.app.disciplinas)
        self.destroy()
        recarregar = getattr(self.app, "recarregar_telas", None)
        if recarregar:
            recarregar()  # mostra nas abas o que foi preenchido no assistente

    # ── Etapas ───────────────────────────────────────────────────────────

    def _etapa_boas_vindas(self):
        ttk.Label(self.frame_conteudo, text="Bem-vindo ao SIGAA Sniper", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            self.frame_conteudo, wraplength=560, justify="left",
            text=(
                "Vamos configurar o essencial em algumas etapas rápidas — todas "
                "opcionais, você pode pular a qualquer momento e configurar tudo "
                "depois nas abas normais.\n\n"
                "Etapas: credenciais → disciplina → modo → notificações → concluir."
            ),
        ).pack(anchor="w", pady=(14, 0))

    def _etapa_credenciais(self):
        ttk.Label(self.frame_conteudo, text="1. Credenciais do SIGAA", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(
            self.frame_conteudo, wraplength=560, justify="left", foreground="#666",
            text="Nunca são salvas em disco — só ficam em memória nesta execução. Pode preencher agora ou pular e preencher na aba Credenciais.",
        ).pack(anchor="w", pady=(4, 14))

        cred = self.app.sessao.sigaa
        campos = ttk.Frame(self.frame_conteudo)
        campos.pack(fill="x")
        self.var_usuario = tk.StringVar(value=cred.usuario)
        self.var_senha = tk.StringVar(value=cred.senha)
        self.var_cpf = tk.StringVar(value=cred.cpf)
        self.var_nascimento = tk.StringVar(value=cred.nascimento)
        for i, (rotulo, var, oculto) in enumerate([
            ("Matrícula:", self.var_usuario, False), ("Senha:", self.var_senha, True),
            ("CPF:", self.var_cpf, False), ("Nascimento (DD/MM/AAAA):", self.var_nascimento, False),
        ]):
            ttk.Label(campos, text=rotulo).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Entry(campos, textvariable=var, show="•" if oculto else "", width=30).grid(row=i, column=1, pady=4, padx=(10, 0))
            var.trace_add("write", lambda *_: self._salvar_credenciais_parcial())

    def _salvar_credenciais_parcial(self):
        cred = self.app.sessao.sigaa
        cred.usuario = self.var_usuario.get().strip()
        cred.senha = self.var_senha.get()
        cred.cpf = self.var_cpf.get().strip()
        cred.nascimento = self.var_nascimento.get().strip()

    def _etapa_disciplina(self):
        ttk.Label(self.frame_conteudo, text="2. Adicionar uma disciplina", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(
            self.frame_conteudo, wraplength=560, justify="left", foreground="#666",
            text="Pode adicionar mais depois na aba Disciplinas. Digite o departamento para buscar.",
        ).pack(anchor="w", pady=(4, 14))

        campos = ttk.Frame(self.frame_conteudo)
        campos.pack(fill="x")
        self.var_disc_codigo = tk.StringVar()
        self.var_disc_turma = tk.StringVar()
        self.var_disc_depto_busca = tk.StringVar()
        ttk.Label(campos, text="Código (ex: FGA0211):").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(campos, textvariable=self.var_disc_codigo, width=30).grid(row=0, column=1, pady=4, padx=(10, 0))
        ttk.Label(campos, text="Turma (ex: 01):").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(campos, textvariable=self.var_disc_turma, width=30).grid(row=1, column=1, pady=4, padx=(10, 0))
        ttk.Label(campos, text="Departamento (nome ou código):").grid(row=2, column=0, sticky="w", pady=4)
        combo = ttk.Combobox(campos, textvariable=self.var_disc_depto_busca, width=28)
        combo.grid(row=2, column=1, pady=4, padx=(10, 0))
        combo.bind("<KeyRelease>", lambda _e: combo.configure(values=[f"{d.codigo} — {d.nome}" for d in buscar_departamentos(self.var_disc_depto_busca.get())[:20]]))

        ttk.Button(self.frame_conteudo, text="➕ Adicionar disciplina", command=self._adicionar_disciplina_wizard).pack(anchor="w", pady=(10, 0))
        self.lbl_disc_status = ttk.Label(self.frame_conteudo, text=f"{len(self.app.disciplinas)} disciplina(s) já cadastrada(s).", foreground="#1a7f37")
        self.lbl_disc_status.pack(anchor="w", pady=(6, 0))

    def _adicionar_disciplina_wizard(self):
        import re
        codigo = self.var_disc_codigo.get().strip().upper()
        turma = self.var_disc_turma.get().strip()
        texto_depto = self.var_disc_depto_busca.get().strip()
        m = re.match(r"^(\d+)\s*—", texto_depto)
        depto = int(m.group(1)) if m else (int(texto_depto) if texto_depto.isdigit() else 0)

        if not codigo or not turma or not depto:
            self.lbl_disc_status.config(text="Preencha código, turma e departamento.", foreground="#cf222e")
            return

        self.app.disciplinas.append(Disciplina(codigo=codigo, turma=turma, departamento=depto))
        self.lbl_disc_status.config(text=f"{codigo}-{turma} adicionada! Total: {len(self.app.disciplinas)}.", foreground="#1a7f37")
        self.var_disc_codigo.set("")
        self.var_disc_turma.set("")

    def _etapa_modo(self):
        ttk.Label(self.frame_conteudo, text="3. Modo de operação", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(self.frame_conteudo, wraplength=560, justify="left", foreground="#666", text="Pode mudar isso a qualquer momento na aba Execução.").pack(anchor="w", pady=(4, 14))

        self.var_modo_wizard = tk.StringVar(value=self.app.settings.get("modo", "monitoramento"))
        ttk.Radiobutton(self.frame_conteudo, text="Matrícula automática — tenta se matricular assim que achar vaga", variable=self.var_modo_wizard, value="matricula", command=self._salvar_modo_parcial).pack(anchor="w")
        ttk.Radiobutton(self.frame_conteudo, text="Somente monitoramento — só avisa, nunca matricula sozinho", variable=self.var_modo_wizard, value="monitoramento", command=self._salvar_modo_parcial).pack(anchor="w")

    def _salvar_modo_parcial(self):
        self.app.settings["modo"] = self.var_modo_wizard.get()

    def _etapa_notificacoes(self):
        ttk.Label(self.frame_conteudo, text="4. Notificações (opcional)", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(
            self.frame_conteudo, wraplength=560, justify="left", foreground="#666",
            text="Totalmente opcional — o programa funciona normalmente sem nenhuma. Configure em detalhes na aba Notificações depois, se quiser.",
        ).pack(anchor="w", pady=(4, 14))
        ttk.Label(self.frame_conteudo, text="Disponíveis: Telegram, ntfy e alarme sonoro local.", foreground="#666").pack(anchor="w")

    def _etapa_finalizar(self):
        ttk.Label(self.frame_conteudo, text="Tudo pronto!", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        resumo = [
            f"Credenciais: {'preenchidas' if self.app.sessao.sigaa.preenchida() else 'não preenchidas ainda'}",
            f"Disciplinas cadastradas: {len(self.app.disciplinas)}",
            f"Modo: {'Matrícula automática' if self.app.settings.get('modo') == 'matricula' else 'Somente monitoramento'}",
        ]
        ttk.Label(self.frame_conteudo, text="\n".join(resumo), justify="left").pack(anchor="w", pady=(14, 0))
        ttk.Label(self.frame_conteudo, text="Clique em Finalizar para começar a usar o programa.", foreground="#666").pack(anchor="w", pady=(14, 0))
