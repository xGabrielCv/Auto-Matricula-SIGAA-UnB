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
    SECOES_RESTAURAVEIS, carregar_disciplinas, carregar_settings, exportar_configuracao,
    importar_configuracao, pre_visualizar_importacao, restaurar_padroes, validar_settings,
)
from app.utils.cleanup import limpar_debug_dumps, resumo_espaco_em_disco

AJUDA = {
    "workers": "Quantas buscas simultâneas o programa faz. Mais workers = mais rápido para achar "
               "vaga, mas também mais carga no seu computador e no SIGAA. Acima de 20 raramente "
               "ajuda e aumenta o risco de bloqueio temporário.",
    "intervalo": "Quanto tempo cada worker espera entre uma busca e a próxima pela mesma disciplina. "
                 "Muito baixo (perto de 0) pode ser tratado como abuso pelo SIGAA.",
    "timeout": "Quanto tempo esperar uma resposta do SIGAA antes de desistir daquela tentativa "
               "específica e reiniciar a conexão.",
    "dashboard_auto": "Se marcado, a aba Dashboard já aparece com dados assim que uma execução começa.",
    "logs_tamanho": "Tamanho máximo de cada arquivo de log de auditoria antes de rotacionar (criar um novo).",
    "logs_qtd": "Quantos arquivos de log antigos ficam guardados além do atual.",
    "debug": "DEBUG mostra mais detalhes técnicos no console (ex: código HTTP e tamanho da resposta "
             "de cada busca). Nunca inclui senha, CPF ou qualquer credencial, nem em modo DEBUG.",
    "urls": "Endereços usados para falar com o SIGAA. Só mude se o SIGAA tiver alterado essas URLs — "
            "um valor errado impede o programa de funcionar. Use 'Restaurar' se algo der errado.",
}


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
        ttk.Label(self, text="Só mexa aqui se souber o que está fazendo. Clique nos [?] para entender cada opção.", foreground="#666").pack(anchor="w", pady=(0, 10))

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
        self._linha(perf, 0, "Quantidade de workers:", self.var_workers, 1, 100, "workers")
        self._linha(perf, 1, "Intervalo entre buscas (segundos):", self.var_intervalo, 0.05, 60, "intervalo", incremento=0.1)
        self._linha(perf, 2, "Timeout de requisição (segundos):", self.var_timeout, 1, 120, "timeout")

        exec_frame = ttk.LabelFrame(corpo, text="Execução", padding=10)
        exec_frame.pack(fill="x", pady=6)
        self.var_dashboard_auto = tk.BooleanVar(value=s["abrir_dashboard_ao_iniciar"])
        linha_dash = ttk.Frame(exec_frame)
        linha_dash.pack(anchor="w")
        ttk.Checkbutton(linha_dash, text="Abrir dashboard automaticamente ao iniciar", variable=self.var_dashboard_auto).pack(side="left")
        self._ajuda(linha_dash, "dashboard_auto")

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
        self._linha(logs_frame, 0, "Tamanho máximo (MB, informativo):", self.var_log_mb, 1, 500)
        self._linha(logs_frame, 1, "Arquivos antigos mantidos:", self.var_log_qtd, 0, 50, "logs_qtd")

        json_frame = ttk.LabelFrame(corpo, text="JSON de auditoria (log principal)", padding=10)
        json_frame.pack(fill="x", pady=6)
        self.var_json_mb = tk.IntVar(value=s["json_audit"]["tamanho_max_mb"])
        self.var_json_qtd = tk.IntVar(value=s["json_audit"]["arquivos_mantidos"])
        self._linha(json_frame, 0, "Tamanho máximo por arquivo (MB):", self.var_json_mb, 1, 500, "logs_tamanho")
        self._linha(json_frame, 1, "Arquivos antigos mantidos:", self.var_json_qtd, 0, 50)

        urls_frame = ttk.LabelFrame(corpo, text="URLs do SIGAA", padding=10)
        urls_frame.pack(fill="x", pady=6)
        linha_urls_titulo = ttk.Frame(urls_frame)
        linha_urls_titulo.pack(anchor="w")
        ttk.Label(linha_urls_titulo, text="⚠️ Só altere se souber o que está fazendo.", foreground="#9a6700").pack(side="left")
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

        restaurar_frame = ttk.LabelFrame(corpo, text="Restaurar configurações padrão", padding=10)
        restaurar_frame.pack(fill="x", pady=6)
        ttk.Label(restaurar_frame, text="Nunca afeta credenciais (elas não ficam salvas de qualquer forma).", foreground="#666").pack(anchor="w")
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
            exportar_frame, wraplength=560, justify="left", foreground="#666",
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
        self.var_debug.set(s.get("debug", {}).get("nivel_log_console", "INFO"))
        self.var_log_mb.set(s["logs"]["tamanho_max_mb"])
        self.var_log_qtd.set(s["logs"]["arquivos_mantidos"])
        self.var_json_mb.set(s["json_audit"]["tamanho_max_mb"])
        self.var_json_qtd.set(s["json_audit"]["arquivos_mantidos"])
        for chave, var in self.vars_urls.items():
            var.set(s.get("urls", {}).get(chave, ""))

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
        s["debug"] = {"nivel_log_console": self.var_debug.get()}
        s["logs"] = {"tamanho_max_mb": self.var_log_mb.get(), "arquivos_mantidos": self.var_log_qtd.get()}
        s["json_audit"] = {"tamanho_max_mb": self.var_json_mb.get(), "arquivos_mantidos": self.var_json_qtd.get()}
        s["urls"] = {chave: var.get().strip() for chave, var in self.vars_urls.items()}
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
