"""
Tela de Configurações Avançadas — seções 9, 32-35, 72, 79, 94.7 do pedido.

Cada opção tem um botão [?] com explicação curta (seção 72/94.7), fica
oculta até o usuário clicar (não polui a tela). Mudanças arriscadas (URLs,
restaurar padrões) pedem confirmação (seção 81).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app.core.config import (
    PADROES_SETTINGS, PRESETS_CARGA, SECOES_RESTAURAVEIS, carregar_disciplinas, carregar_settings, estimar_carga,
    exportar_configuracao, importar_configuracao, pre_visualizar_importacao, restaurar_padroes, validar_settings,
)
from app.core.textos import AJUDA_AVANCADO as AJUDA  # noqa: F401 — nome mantido por compatibilidade
from app.utils.cleanup import limpar_debug_dumps, resumo_espaco_em_disco
from app.gui.tema import cor
from app.core.esquema import faixa

ROTULO_PERSONALIZADO = "Personalizado"


class TelaAvancado(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self._construir()

    def _ajuda(self, parent, chave):
        def mostrar():
            messagebox.showinfo("Ajuda", AJUDA[chave], parent=self)
        ttk.Button(parent, text="?", width=2, command=mostrar).pack(side="left", padx=(6, 0))

    def _linha(self, parent, row, rotulo, var, minimo, maximo, chave_ajuda=None, incremento=1):
        frame_rotulo = ttk.Frame(parent)
        frame_rotulo.grid(row=row, column=0, sticky="w", pady=4)
        ttk.Label(frame_rotulo, text=rotulo).pack(side="left")
        if chave_ajuda:
            self._ajuda(frame_rotulo, chave_ajuda)
        ttk.Spinbox(parent, from_=minimo, to=maximo, increment=incremento, textvariable=var, width=10).grid(row=row, column=1, sticky="w", padx=(10, 0))

    def _construir(self):
        ttk.Label(self, text="Configurações Avançadas", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(self, text="Só mexa aqui se souber o que está fazendo. Clique nos [?] para entender cada opção.", foreground=cor("#666")).pack(anchor="w", pady=(0, 10))

        s = self.app.settings

        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        corpo = ttk.Frame(canvas)
        corpo.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=corpo, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        perf = ttk.LabelFrame(corpo, text="Desempenho", padding=10)
        perf.pack(fill="x", pady=6)
        self.var_workers = tk.IntVar(value=s["num_workers"])
        self.var_intervalo = tk.DoubleVar(value=s["intervalo_busca"])
        self.var_timeout = tk.IntVar(value=s["timeout_req"])
        linha_preset = ttk.Frame(perf)
        linha_preset.grid(row=0, column=0, sticky="w", pady=4)
        ttk.Label(linha_preset, text="Perfil de carga:").pack(side="left")
        self._ajuda(linha_preset, "carga")
        self._rotulos_preset = {p["rotulo"]: chave for chave, p in PRESETS_CARGA.items()}
        self.var_preset = tk.StringVar()
        combo = ttk.Combobox(perf, textvariable=self.var_preset, state="readonly", width=28,
                             values=[*self._rotulos_preset, ROTULO_PERSONALIZADO])
        combo.grid(row=0, column=1, sticky="w", padx=(10, 0))
        combo.bind("<<ComboboxSelected>>", self._aplicar_preset)
        self._linha(perf, 1, "Quantidade de workers:", self.var_workers, *faixa("num_workers"), "workers")
        self._linha(perf, 2, "Intervalo entre buscas (segundos):", self.var_intervalo, *faixa("intervalo_busca"), "intervalo", incremento=0.1)
        self._linha(perf, 3, "Timeout de requisição (segundos):", self.var_timeout, *faixa("timeout_req"), "timeout")
        self.lbl_carga = ttk.Label(perf, text="", wraplength=560, justify="left")
        self.lbl_carga.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.var_workers.trace_add("write", lambda *_: self._atualizar_carga())
        self.var_intervalo.trace_add("write", lambda *_: self._atualizar_carga())
        self._atualizar_carga()

        prot = {**{"limite_req_por_seg": 20, "logins_simultaneos": 3, "disjuntor": True}, **s.get("protecao", {})}
        prot_frame = ttk.LabelFrame(corpo, text="Proteção de carga", padding=10)
        prot_frame.pack(fill="x", pady=6)
        self.var_limite = tk.DoubleVar(value=prot["limite_req_por_seg"])
        self.var_logins = tk.IntVar(value=prot["logins_simultaneos"])
        self.var_disjuntor = tk.BooleanVar(value=prot["disjuntor"])
        self._linha(prot_frame, 0, "Teto de buscas por segundo (0 = sem teto):", self.var_limite, *faixa("protecao.limite_req_por_seg"), "protecao", incremento=1)
        self._linha(prot_frame, 1, "Logins simultâneos no CAS:", self.var_logins, *faixa("protecao.logins_simultaneos"))
        ttk.Checkbutton(prot_frame, text="Pausar as buscas automaticamente quando o SIGAA ficar instável (disjuntor)",
                        variable=self.var_disjuntor).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.var_limite.trace_add("write", lambda *_: self._atualizar_carga())
        self._atualizar_carga()

        exec_frame = ttk.LabelFrame(corpo, text="Execução", padding=10)
        exec_frame.pack(fill="x", pady=6)
        self.var_dashboard_auto = tk.BooleanVar(value=s["abrir_dashboard_ao_iniciar"])
        linha_dash = ttk.Frame(exec_frame)
        linha_dash.pack(anchor="w")
        ttk.Checkbutton(linha_dash, text="Abrir dashboard automaticamente ao iniciar", variable=self.var_dashboard_auto).pack(side="left")
        self._ajuda(linha_dash, "dashboard_auto")
        # Desde a 6.1.0: painéis começam vazios, a menos que a pessoa queira ver a última execução.
        self.var_carregar_ultima = tk.BooleanVar(value=bool(s.get("carregar_ultima_execucao")))
        linha_ultima = ttk.Frame(exec_frame)
        linha_ultima.pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(linha_ultima, text="Carregar dados da última execução ao abrir", variable=self.var_carregar_ultima).pack(side="left")
        self._ajuda(linha_ultima, "carregar_ultima")
        ttk.Button(exec_frame, text="🧭 Refazer a configuração inicial", command=self._refazer_assistente).pack(anchor="w", pady=(6, 0))

        linha_debug = ttk.Frame(exec_frame)
        linha_debug.pack(anchor="w", pady=(6, 0))
        ttk.Label(linha_debug, text="Nível de log no console:").pack(side="left")
        self.var_debug = tk.StringVar(value=s.get("debug", {}).get("nivel_log_console", "INFO"))
        ttk.Combobox(linha_debug, textvariable=self.var_debug, values=["INFO", "DEBUG"], width=8, state="readonly").pack(side="left", padx=(8, 0))
        self._ajuda(linha_debug, "debug")

        logs_frame = ttk.LabelFrame(corpo, text="Logs (dumps de debug HTML)", padding=10)
        logs_frame.pack(fill="x", pady=6)
        self.var_log_mb = tk.IntVar(value=s["logs"]["tamanho_max_mb"])
        self.var_log_qtd = tk.IntVar(value=s["logs"]["arquivos_mantidos"])
        self._linha(logs_frame, 0, "Tamanho máximo (MB, informativo):", self.var_log_mb, *faixa("logs.tamanho_max_mb"))
        self._linha(logs_frame, 1, "Arquivos antigos mantidos:", self.var_log_qtd, *faixa("logs.arquivos_mantidos"), "logs_qtd")

        json_frame = ttk.LabelFrame(corpo, text="JSON de auditoria (log principal)", padding=10)
        json_frame.pack(fill="x", pady=6)
        self.var_json_mb = tk.IntVar(value=s["json_audit"]["tamanho_max_mb"])
        self.var_json_qtd = tk.IntVar(value=s["json_audit"]["arquivos_mantidos"])
        self._linha(json_frame, 0, "Tamanho máximo por arquivo (MB):", self.var_json_mb, *faixa("json_audit.tamanho_max_mb"), "logs_tamanho")
        self._linha(json_frame, 1, "Arquivos antigos mantidos:", self.var_json_qtd, *faixa("json_audit.arquivos_mantidos"))

        urls_frame = ttk.LabelFrame(corpo, text="URLs do SIGAA", padding=10)
        urls_frame.pack(fill="x", pady=6)
        linha_urls_titulo = ttk.Frame(urls_frame)
        linha_urls_titulo.pack(anchor="w")
        ttk.Label(linha_urls_titulo, text="⚠️ Só altere se souber o que está fazendo.", foreground=cor("#9a6700")).pack(side="left")
        self._ajuda(linha_urls_titulo, "urls")
        self.vars_urls = {}
        rotulos_urls = [
            ("cas_login", "Login (CAS):"), ("portal_discente", "Portal do discente:"),
            ("matricula_extra", "Matrícula extraordinária:"), ("confirmacao", "Confirmação:"), ("sigaa_base", "Base do SIGAA:"),
        ]
        for i, (chave, rotulo) in enumerate(rotulos_urls):
            ttk.Label(urls_frame, text=rotulo).pack(anchor="w", pady=(6, 0))
            var = tk.StringVar(value=s.get("urls", {}).get(chave, ""))
            self.vars_urls[chave] = var
            ttk.Entry(urls_frame, textvariable=var, width=70).pack(anchor="w")
        self._rotulos_urls = dict(rotulos_urls)
        ttk.Button(urls_frame, text="🔎 Testar endereços (sem login; fora de unb.br não é acessado)",
                   command=self._testar_urls).pack(anchor="w", pady=(8, 0))
        self.lbl_teste_urls = ttk.Label(urls_frame, text="", justify="left", wraplength=620)
        self.lbl_teste_urls.pack(anchor="w", pady=(4, 0))

        # Aparência (Fase 6 — 010): tema e tamanho da fonte da interface gráfica.
        from app.gui.tema import TEMAS
        interface = {**PADROES_SETTINGS["interface"], **s.get("interface", {})}
        aparencia = ttk.LabelFrame(corpo, text="Aparência da interface gráfica", padding=10)
        aparencia.pack(fill="x", pady=6)
        self._rotulos_tema = dict(TEMAS)
        linha_tema = ttk.Frame(aparencia)
        linha_tema.pack(anchor="w")
        ttk.Label(linha_tema, text="Tema:").pack(side="left")
        self.var_tema = tk.StringVar(value=self._rotulos_tema.get(interface["tema"], "Claro"))
        ttk.Combobox(linha_tema, textvariable=self.var_tema, values=list(self._rotulos_tema.values()), state="readonly",
                     width=18).pack(side="left", padx=(8, 16))
        ttk.Label(linha_tema, text="Tamanho da fonte (%):").pack(side="left")
        self.var_escala = tk.IntVar(value=interface["escala_fonte"])
        ttk.Spinbox(linha_tema, from_=faixa("interface.escala_fonte")[0], to=faixa("interface.escala_fonte")[1], increment=10, textvariable=self.var_escala, width=6).pack(side="left", padx=(8, 0))
        ttk.Label(aparencia, text="Vale na próxima vez que a interface gráfica for aberta.", foreground=cor("#666")).pack(anchor="w", pady=(4, 0))

        # Alertas por limiar (Fase 5 — 058).
        alertas = {**PADROES_SETTINGS["alertas"], **s.get("alertas", {})}
        alertas_frame = ttk.LabelFrame(corpo, text="Alertas de problema", padding=10)
        alertas_frame.pack(fill="x", pady=6)
        self.var_alertas_ativo = tk.BooleanVar(value=alertas["ativo"])
        self.var_alerta_taxa = tk.IntVar(value=alertas["taxa_erro_pct"])
        self.var_alerta_taxa_min = tk.IntVar(value=alertas["taxa_erro_min"])
        self.var_alerta_resposta = tk.IntVar(value=alertas["sem_resposta_min"])
        self.var_alerta_busca = tk.IntVar(value=alertas["sem_busca_min"])
        ttk.Checkbutton(alertas_frame, text="Avisar quando algo parecer errado durante a execução",
                        variable=self.var_alertas_ativo).grid(row=0, column=0, columnspan=2, sticky="w")
        self._linha(alertas_frame, 1, "Taxa de erro acima de (%):", self.var_alerta_taxa, *faixa("alertas.taxa_erro_pct"))
        self._linha(alertas_frame, 2, "…sustentada por (minutos):", self.var_alerta_taxa_min, *faixa("alertas.taxa_erro_min"))
        self._linha(alertas_frame, 3, "SIGAA sem responder por (minutos):", self.var_alerta_resposta, *faixa("alertas.sem_resposta_min"))
        self._linha(alertas_frame, 4, "Nenhuma busca por (minutos):", self.var_alerta_busca, *faixa("alertas.sem_busca_min"))

        hist_frame = ttk.LabelFrame(corpo, text="Histórico de execuções (data/historico.db)", padding=10)
        hist_frame.pack(fill="x", pady=6)
        hist = {**{"ativo": True, "dias_retencao": 180}, **s.get("historico", {})}
        self.var_hist_ativo = tk.BooleanVar(value=hist["ativo"])
        self.var_hist_dias = tk.IntVar(value=hist["dias_retencao"])
        ttk.Checkbutton(hist_frame, text="Gravar cada execução no histórico (sem credenciais)", variable=self.var_hist_ativo).grid(row=0, column=0, columnspan=2, sticky="w")
        self._linha(hist_frame, 1, "Guardar por quantos dias (0 = sempre):", self.var_hist_dias, *faixa("historico.dias_retencao"))

        espaco_frame = ttk.LabelFrame(corpo, text="Espaço em disco usado pelo programa", padding=10)
        espaco_frame.pack(fill="x", pady=6)
        self.lbl_espaco = ttk.Label(espaco_frame, text="—")
        self.lbl_espaco.pack(anchor="w")
        botoes_espaco = ttk.Frame(espaco_frame)
        botoes_espaco.pack(anchor="w", pady=(6, 0))
        ttk.Button(botoes_espaco, text="Atualizar", command=self._atualizar_espaco).pack(side="left")
        ttk.Button(botoes_espaco, text="Limpar dumps de debug antigos", command=self._limpar_dumps).pack(side="left", padx=(8, 0))
        self._atualizar_espaco()

        ttk.Button(corpo, text="💾 Salvar configurações avançadas", command=self._salvar).pack(anchor="w", pady=(14, 6))

        # Fase 6: perfis (042) e versões anteriores (045).
        perfis_frame = ttk.LabelFrame(corpo, text="Perfis (cenários prontos)", padding=10)
        perfis_frame.pack(fill="x", pady=6)
        ttk.Label(perfis_frame, text="Modo, desempenho, proteção, janela, alertas, notificações e disciplinas. "
                                     "O DRY RUN nunca muda ao aplicar um perfil.", foreground=cor("#666"), wraplength=620,
                  justify="left").pack(anchor="w")
        linha_perfis = ttk.Frame(perfis_frame)
        linha_perfis.pack(anchor="w", pady=(6, 0))
        self.var_perfil = tk.StringVar()
        self.combo_perfis = ttk.Combobox(linha_perfis, textvariable=self.var_perfil, state="readonly", width=34)
        self.combo_perfis.pack(side="left")
        ttk.Button(linha_perfis, text="Aplicar", command=self._aplicar_perfil).pack(side="left", padx=(8, 0))
        ttk.Button(linha_perfis, text="Salvar atual como…", command=self._salvar_perfil).pack(side="left", padx=(8, 0))
        ttk.Button(linha_perfis, text="Apagar", command=self._apagar_perfil).pack(side="left", padx=(8, 0))
        self._atualizar_perfis()
        ttk.Button(corpo, text="↩️ Versões anteriores (desfazer alterações)…", command=self._versoes).pack(anchor="w", pady=(4, 6))

        restaurar_frame = ttk.LabelFrame(corpo, text="Restaurar configurações padrão", padding=10)
        restaurar_frame.pack(fill="x", pady=6)
        ttk.Label(restaurar_frame, text="Nunca afeta credenciais (elas não ficam salvas de qualquer forma).", foreground=cor("#666")).pack(anchor="w")
        self.vars_secoes_restaurar = {}
        rotulos_secoes = {
            "monitoramento": "Monitoramento (modo, workers, intervalos)", "dashboard": "Dashboard",
            "notificacoes": "Notificações", "avancado": "Avançado (logs, debug)", "urls": "URLs do SIGAA",
        }
        for secao in SECOES_RESTAURAVEIS:
            var = tk.BooleanVar(value=False)
            self.vars_secoes_restaurar[secao] = var
            ttk.Checkbutton(restaurar_frame, text=rotulos_secoes.get(secao, secao), variable=var).pack(anchor="w")
        ttk.Button(restaurar_frame, text="↩️ Restaurar selecionadas", command=self._restaurar_selecionadas).pack(anchor="w", pady=(8, 2))
        ttk.Button(restaurar_frame, text="↩️ Restaurar TUDO", command=self._restaurar_tudo).pack(anchor="w")

        exportar_frame = ttk.LabelFrame(corpo, text="Configurações exportáveis / backup", padding=10)
        exportar_frame.pack(fill="x", pady=(6, 6))
        ttk.Label(
            exportar_frame, wraplength=560, justify="left", foreground=cor("#666"),
            text="Exporta/importa disciplinas e preferências para levar a outro computador, ou como backup local. NUNCA inclui credenciais.",
        ).pack(anchor="w")
        botoes_export = ttk.Frame(exportar_frame)
        botoes_export.pack(anchor="w", pady=(6, 0))
        ttk.Button(botoes_export, text="📤 Exportar / Backup", command=self._exportar).pack(side="left")
        ttk.Button(botoes_export, text="📥 Importar / Restaurar backup", command=self._importar).pack(side="left", padx=(8, 0))

    def recarregar(self):
        s = self.app.settings
        self.var_workers.set(s["num_workers"])
        self.var_intervalo.set(s["intervalo_busca"])
        self.var_timeout.set(s["timeout_req"])
        self.var_dashboard_auto.set(s["abrir_dashboard_ao_iniciar"])
        self.var_carregar_ultima.set(bool(s.get("carregar_ultima_execucao")))
        self.var_debug.set(s.get("debug", {}).get("nivel_log_console", "INFO"))
        self.var_log_mb.set(s["logs"]["tamanho_max_mb"])
        self.var_log_qtd.set(s["logs"]["arquivos_mantidos"])
        self.var_json_mb.set(s["json_audit"]["tamanho_max_mb"])
        self.var_json_qtd.set(s["json_audit"]["arquivos_mantidos"])
        for chave, var in self.vars_urls.items():
            var.set(s.get("urls", {}).get(chave, ""))
        prot = {**{"limite_req_por_seg": 20, "logins_simultaneos": 3, "disjuntor": True}, **s.get("protecao", {})}
        self.var_limite.set(prot["limite_req_por_seg"])
        self.var_logins.set(prot["logins_simultaneos"])
        self.var_disjuntor.set(prot["disjuntor"])
        hist = {**{"ativo": True, "dias_retencao": 180}, **s.get("historico", {})}
        self.var_hist_ativo.set(hist["ativo"])
        self.var_hist_dias.set(hist["dias_retencao"])
        interface = {**PADROES_SETTINGS["interface"], **s.get("interface", {})}
        self.var_tema.set(self._rotulos_tema.get(interface["tema"], "Claro"))
        self.var_escala.set(interface["escala_fonte"])
        alertas = {**PADROES_SETTINGS["alertas"], **s.get("alertas", {})}
        self.var_alertas_ativo.set(alertas["ativo"])
        self.var_alerta_taxa.set(alertas["taxa_erro_pct"])
        self.var_alerta_taxa_min.set(alertas["taxa_erro_min"])
        self.var_alerta_resposta.set(alertas["sem_resposta_min"])
        self.var_alerta_busca.set(alertas["sem_busca_min"])

    def _atualizar_perfis(self):
        from app.core.config import listar_perfis
        self._perfis = listar_perfis()
        self.combo_perfis["values"] = [p["nome"] for p in self._perfis]
        if self.var_perfil.get() not in self.combo_perfis["values"]:
            self.var_perfil.set(self._perfis[0]["nome"] if self._perfis else "")

    def _perfil_escolhido(self):
        return next((p for p in self._perfis if p["nome"] == self.var_perfil.get()), None)

    def _aplicar_perfil(self):
        from app.core.config import aplicar_perfil, salvar_disciplinas
        perfil = self._perfil_escolhido()
        if not perfil:
            messagebox.showinfo("Perfis", "Nenhum perfil escolhido. Use \"Salvar atual como…\" para criar um.")
            return
        if self.app.estado_execucao().get("em_execucao"):
            messagebox.showwarning("Perfis", "Pare a execução antes de trocar de perfil.")
            return
        if not messagebox.askyesno("Aplicar perfil", f"Aplicar \"{perfil['nome']}\"?\n\n{perfil['resumo']}.\n\n"
                                   "O DRY RUN continua como está. Dá para desfazer em Versões anteriores."):
            return
        try:
            novos, disciplinas = aplicar_perfil(perfil["arquivo"], self.app.settings)
        except ValueError as e:
            messagebox.showerror("Perfil inválido", str(e))
            return
        self.app.settings, self.app.disciplinas = novos, disciplinas
        self.app.salvar_settings()
        salvar_disciplinas(disciplinas)
        self.app.recarregar_telas()
        messagebox.showinfo("Perfis", f"Perfil \"{perfil['nome']}\" aplicado.")

    def _salvar_perfil(self):
        from tkinter import simpledialog
        from app.core.config import listar_perfis, salvar_perfil, _arquivo_perfil
        nome = simpledialog.askstring("Salvar perfil", "Nome do perfil:", parent=self)
        if not nome:
            return
        try:
            arquivo = _arquivo_perfil(nome)
        except ValueError as e:
            messagebox.showwarning("Perfis", str(e))
            return
        if any(p["arquivo"] == arquivo for p in listar_perfis()) and not messagebox.askyesno(
                "Substituir perfil", f"Já existe um perfil \"{nome}\". Substituir pelo que está configurado agora?"):
            return
        salvar_perfil(nome, self.app.settings, self.app.disciplinas)
        self._atualizar_perfis()
        self.var_perfil.set(nome.strip()[:60])

    def _apagar_perfil(self):
        from app.core.config import apagar_perfil
        perfil = self._perfil_escolhido()
        if perfil and messagebox.askyesno("Apagar perfil", f"Apagar o perfil \"{perfil['nome']}\"? A configuração atual não muda."):
            apagar_perfil(perfil["arquivo"])
            self._atualizar_perfis()

    def _versoes(self):
        from app.core.config import listar_versoes_config, restaurar_versao_config
        janela = tk.Toplevel(self)
        janela.title("Versões anteriores")
        janela.transient(self.winfo_toplevel())
        ttk.Label(janela, text="Cada alteração guarda a versão anterior. Restaurar também guarda a atual (dá para desfazer).",
                  foreground=cor("#666")).pack(anchor="w", padx=12, pady=(12, 6))
        arvore = ttk.Treeview(janela, columns=("quando", "tipo", "resumo"), show="headings", height=10)
        for col, titulo, largura in (("quando", "Quando", 140), ("tipo", "O quê", 110), ("resumo", "Se restaurar", 460)):
            arvore.heading(col, text=titulo)
            arvore.column(col, width=largura, anchor="w")
        arvore.pack(fill="both", expand=True, padx=12)
        versoes = {}

        def preencher():
            arvore.delete(*arvore.get_children())
            versoes.clear()
            for v in listar_versoes_config():
                versoes[v["id"]] = v
                arvore.insert("", "end", iid=v["id"], values=(v["quando"], v["tipo_rotulo"], v["resumo"]))

        def restaurar():
            sel = arvore.selection()
            if not sel:
                return
            v = versoes[sel[0]]
            if v["tipo"] == "disciplinas" and self.app.estado_execucao().get("em_execucao"):
                messagebox.showwarning("Versões", "Pare a execução antes de restaurar as disciplinas.", parent=janela)
                return
            if not messagebox.askyesno("Restaurar", f"Voltar {v['tipo_rotulo'].lower()} para {v['quando']}?\n\n{v['resumo']}", parent=janela):
                return
            try:
                r = restaurar_versao_config(v["id"])
            except ValueError as e:
                messagebox.showerror("Não restaurado", str(e), parent=janela)
                return
            if r["tipo"] == "settings":
                self.app.settings = r["settings"]
            else:
                self.app.disciplinas = r["disciplinas"]
            self.app.recarregar_telas()
            preencher()

        preencher()
        ttk.Button(janela, text="↩️ Restaurar a versão selecionada", command=restaurar).pack(anchor="e", padx=12, pady=12)
        return janela

    def _refazer_assistente(self):
        from app.gui.wizard_primeira_execucao import AssistentePrimeiraExecucao
        AssistentePrimeiraExecucao(self.winfo_toplevel(), self.app)

    def _testar_urls(self):
        import threading
        from app.core.seguranca_config import testar_urls
        urls = {chave: var.get().strip() for chave, var in self.vars_urls.items()}
        self.lbl_teste_urls.config(text="Testando cada endereço…")

        def alvo():
            try:
                resultados = testar_urls(urls)
                texto = "\n".join(f"{'✅' if r['ok'] else '❌'} {self._rotulos_urls.get(r['nome'], r['nome'])} {r['texto']}"
                                  for r in resultados)
            except Exception as e:  # nunca derruba a tela
                texto = f"Não foi possível testar ({type(e).__name__})."
            self.after(0, lambda: self.lbl_teste_urls.config(text=texto))

        threading.Thread(target=alvo, daemon=True).start()

    def _aplicar_preset(self, _event=None):
        chave = self._rotulos_preset.get(self.var_preset.get())
        if chave:
            self.var_workers.set(PRESETS_CARGA[chave]["num_workers"])
            self.var_intervalo.set(PRESETS_CARGA[chave]["intervalo_busca"])

    def _atualizar_carga(self):
        try:
            workers, intervalo = self.var_workers.get(), self.var_intervalo.get()
        except (tk.TclError, ValueError):  # campo sendo digitado / vazio
            workers = intervalo = None
        ativas = sum(1 for d in self.app.disciplinas if d.ativa)
        try:
            teto = self.var_limite.get()
        except (tk.TclError, ValueError, AttributeError):
            teto = self.app.settings.get("protecao", {}).get("limite_req_por_seg", 0)
        carga = estimar_carga(workers, intervalo, ativas, teto)
        preset = carga["preset"]
        self.var_preset.set(PRESETS_CARGA[preset]["rotulo"] if preset else ROTULO_PERSONALIZADO)
        texto = carga["texto"] + (f"\n⚠️ {carga['alerta']}" if carga["alerta"] else "")
        tom = {"baixa": cor("#1a7f37"), "moderada": cor("#9a6700"), "alta": cor("#cf222e")}.get(carga["nivel"], cor("#57606a"))
        self.lbl_carga.config(text=texto, foreground=tom)

    def _atualizar_espaco(self):
        resumo = resumo_espaco_em_disco()
        self.lbl_espaco.config(text=f"logs/: {resumo['logs_mb']} MB   data/: {resumo['data_mb']} MB   config/: {resumo['config_mb']} MB")

    def _limpar_dumps(self):
        removidos = limpar_debug_dumps(manter=self.app.settings["logs"]["arquivos_mantidos"])
        messagebox.showinfo("Limpeza concluída", f"{removidos} arquivo(s) de debug antigo removido(s).")
        self._atualizar_espaco()

    def _coletar_settings_da_tela(self) -> dict:
        s = dict(self.app.settings)
        s["num_workers"] = self.var_workers.get()
        s["intervalo_busca"] = round(self.var_intervalo.get(), 2)
        s["timeout_req"] = self.var_timeout.get()
        s["abrir_dashboard_ao_iniciar"] = self.var_dashboard_auto.get()
        s["carregar_ultima_execucao"] = self.var_carregar_ultima.get()
        s["debug"] = {"nivel_log_console": self.var_debug.get()}
        s["logs"] = {"tamanho_max_mb": self.var_log_mb.get(), "arquivos_mantidos": self.var_log_qtd.get()}
        s["json_audit"] = {"tamanho_max_mb": self.var_json_mb.get(), "arquivos_mantidos": self.var_json_qtd.get()}
        s["urls"] = {chave: var.get().strip() for chave, var in self.vars_urls.items()}
        s["historico"] = {"ativo": self.var_hist_ativo.get(), "dias_retencao": self.var_hist_dias.get()}
        s["protecao"] = {"limite_req_por_seg": self.var_limite.get(), "logins_simultaneos": self.var_logins.get(),
                         "disjuntor": self.var_disjuntor.get()}
        tema = next((k for k, v in self._rotulos_tema.items() if v == self.var_tema.get()), "claro")
        s["interface"] = {"tema": tema, "escala_fonte": self.var_escala.get()}
        s["alertas"] = {"ativo": self.var_alertas_ativo.get(), "taxa_erro_pct": self.var_alerta_taxa.get(),
                        "taxa_erro_min": self.var_alerta_taxa_min.get(), "sem_resposta_min": self.var_alerta_resposta.get(),
                        "sem_busca_min": self.var_alerta_busca.get()}
        return s

    def _salvar(self):
        novos = self._coletar_settings_da_tela()
        problemas = validar_settings(novos)
        if problemas:
            messagebox.showwarning("Configuração inválida", "Corrija antes de salvar:\n\n" + "\n".join(f"• {p}" for p in problemas))
            return

        urls_mudaram = novos["urls"] != self.app.settings.get("urls", {})
        if urls_mudaram and not messagebox.askyesno(
            "Confirmar alteração de URLs",
            "Você alterou as URLs do SIGAA. Um valor incorreto pode impedir o programa de "
            "funcionar completamente.\n\nTem certeza que quer salvar assim mesmo?",
        ):
            return

        self.app.settings = novos
        self.app.salvar_settings()
        messagebox.showinfo("Salvo", "Configurações avançadas salvas.")

    def _restaurar_selecionadas(self):
        secoes = [s for s, v in self.vars_secoes_restaurar.items() if v.get()]
        if not secoes:
            messagebox.showinfo("Nada selecionado", "Marque pelo menos uma seção para restaurar.")
            return
        if not messagebox.askyesno("Confirmar", f"Restaurar os valores padrão de: {', '.join(secoes)}?"):
            return
        self.app.settings = restaurar_padroes(self.app.settings, secoes)
        self.app.salvar_settings()
        self.app.recarregar_telas()
        messagebox.showinfo("Restaurado", "Seções restauradas — os campos já mostram os novos valores.")

    def _restaurar_tudo(self):
        if not messagebox.askyesno("Confirmar", "Restaurar TODAS as configurações avançadas para o padrão? (credenciais nunca são afetadas)"):
            return
        self.app.settings = restaurar_padroes(self.app.settings)
        self.app.salvar_settings()
        self.app.recarregar_telas()
        messagebox.showinfo("Restaurado", "Todas as configurações foram restauradas — os campos já mostram os novos valores.")

    def _exportar(self):
        caminho = filedialog.asksaveasfilename(
            defaultextension=".json", initialfile="sigaa_sniper_config.json",
            title="Exportar configurações (sem credenciais)",
        )
        if caminho:
            exportar_configuracao(caminho)
            messagebox.showinfo("Exportado", f"Configurações (disciplinas + preferências) exportadas para:\n{caminho}")

    def _importar(self):
        caminho = filedialog.askopenfilename(title="Importar configurações", filetypes=[("JSON", "*.json")])
        if not caminho:
            return
        try:
            resumo = pre_visualizar_importacao(caminho)
        except Exception as e:
            messagebox.showerror("Arquivo rejeitado", str(e))
            return

        if resumo["problemas_settings"]:
            messagebox.showerror("Configurações inválidas", "O arquivo tem problemas e não será importado:\n\n" + "\n".join(resumo["problemas_settings"]))
            return

        texto_resumo = f"Disciplinas válidas: {resumo['qtd_disciplinas']}\n"
        if resumo["problemas_disciplinas"]:
            texto_resumo += f"Disciplinas ignoradas (inválidas): {len(resumo['problemas_disciplinas'])}\n"
        texto_resumo += f"Configurações: {'sim, serão substituídas' if resumo['tem_settings'] else 'não incluídas neste arquivo'}"

        if not messagebox.askyesno("Confirmar importação", f"Resumo do que será importado:\n\n{texto_resumo}\n\nAplicar agora?"):
            return

        try:
            importar_configuracao(caminho)
        except Exception as e:
            messagebox.showerror("Erro ao importar", str(e))
            return
        self.app.settings = carregar_settings()
        self.app.disciplinas = carregar_disciplinas()
        self.app.recarregar_telas()
        messagebox.showinfo("Importado", "Configurações importadas — as telas já mostram os novos valores.")
