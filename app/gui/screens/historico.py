"""
Tela de Histórico da GUI (Fase 3 — sugestões 061, 024, 049).

Lista as execuções gravadas em data/historico.db com filtro de período e de
disciplina, mostra o relatório da execução selecionada e exporta em CSV.
Os gráficos do histórico (vagas por dia, mapa de calor, comparação) ficam na
Interface Web; aqui vai o essencial em texto e tabela.
"""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from app.core import historico
from app.core.relatorios import MOTIVOS_FIM, texto_relatorio
from app.gui.tema import cor

PERIODOS = {"7 dias": 7, "30 dias": 30, "90 dias": 90, "Tudo": None}


class TelaHistorico(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self._construir()

    def _acoes(self):
        """Sugestões 062/063: o que foi feito e quando (sem senha, CPF ou tokens)."""
        from app.core import auditoria
        janela = tk.Toplevel(self)
        janela.title("Ações registradas")
        janela.transient(self.winfo_toplevel())
        arvore = ttk.Treeview(janela, columns=("quando", "acao", "detalhe", "onde"), show="headings", height=14)
        for col, titulo, largura in (("quando", "Quando", 140), ("acao", "Ação", 250), ("detalhe", "Detalhe", 330), ("onde", "Onde", 110)):
            arvore.heading(col, text=titulo)
            arvore.column(col, width=largura, anchor="w")
        for a in auditoria.listar(200):
            arvore.insert("", "end", values=(a["quando"], a["rotulo"], a["descricao"] or "—", a["origem"]))
        arvore.pack(fill="both", expand=True, padx=12, pady=12)
        return arvore

    def _construir(self):
        ttk.Label(self, text="Histórico de execuções", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(self, text="Cada execução encerrada entra aqui automaticamente. Gráficos do histórico: Interface Web → Histórico.",
                  foreground=cor("#666")).pack(anchor="w", pady=(0, 10))

        filtros = ttk.Frame(self)
        filtros.pack(fill="x")
        ttk.Label(filtros, text="Período:").pack(side="left")
        self.var_periodo = tk.StringVar(value="30 dias")
        combo = ttk.Combobox(filtros, textvariable=self.var_periodo, values=list(PERIODOS), state="readonly", width=10)
        combo.pack(side="left", padx=(6, 14))
        combo.bind("<<ComboboxSelected>>", lambda _e: self.recarregar())
        ttk.Label(filtros, text="Disciplina:").pack(side="left")
        self.var_disciplina = tk.StringVar(value="Todas")
        self.combo_disciplina = ttk.Combobox(filtros, textvariable=self.var_disciplina, state="readonly", width=14)
        self.combo_disciplina.pack(side="left", padx=(6, 14))
        self.combo_disciplina.bind("<<ComboboxSelected>>", lambda _e: self.recarregar())
        ttk.Button(filtros, text="🔄 Atualizar", command=self.recarregar).pack(side="left")
        ttk.Button(filtros, text="🗑️ Apagar histórico", command=self._apagar).pack(side="right")
        ttk.Button(filtros, text="📊 Exportar CSV", command=self._exportar).pack(side="right", padx=(0, 6))
        ttk.Button(filtros, text="🧾 Ações registradas", command=self._acoes).pack(side="right", padx=(0, 6))

        self.lbl_totais = ttk.Label(self, text="", foreground=cor("#57606a"))
        self.lbl_totais.pack(anchor="w", pady=(10, 4))

        colunas = ("inicio", "duracao", "modo", "fim", "buscas", "vagas", "erros")
        self.tree = ttk.Treeview(self, columns=colunas, show="headings", height=8, selectmode="browse")
        for col, titulo, largura in [("inicio", "Início", 130), ("duracao", "Duração", 80), ("modo", "Modo", 150),
                                     ("fim", "Fim", 100), ("buscas", "Buscas", 80), ("vagas", "Vagas vistas", 90), ("erros", "Erros", 60)]:
            self.tree.heading(col, text=titulo)
            self.tree.column(col, width=largura, anchor="w" if col in ("inicio", "modo", "fim") else "center")
        self.tree.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", self._mostrar_detalhe)

        self.txt = tk.Text(self, height=12, wrap="none", font=("Consolas", 10), state="disabled")
        self.txt.pack(fill="both", expand=True, pady=(10, 0))
        self.recarregar()

    def _filtros(self):
        disciplina = self.var_disciplina.get()
        return PERIODOS.get(self.var_periodo.get()), (None if disciplina in ("", "Todas") else disciplina)

    def recarregar(self):
        try:
            historico.importar_relatorios_antigos()
            dias, disciplina = self._filtros()
            execucoes = historico.listar_execucoes(dias, disciplina)
            self.combo_disciplina["values"] = ["Todas", *historico.disciplinas_no_historico()]
        except Exception as e:  # o histórico nunca pode derrubar a GUI
            self.lbl_totais.config(text=f"Não foi possível ler o histórico: {e}")
            return
        self.tree.delete(*self.tree.get_children())
        for e in execucoes:
            modo = "Monitoramento" if e["modo"] == "monitoramento" else ("Matrícula (DRY RUN)" if e["dry_run"] else "Matrícula REAL")
            minutos = int((e["duracao_seg"] or 0) // 60)
            self.tree.insert("", "end", iid=e["id"], values=(
                datetime.fromtimestamp(e["inicio"]).strftime("%d/%m/%Y %H:%M"), f"{minutos // 60}h {minutos % 60}m", modo,
                MOTIVOS_FIM.get(e["motivo_fim"], "—"), e["requisicoes"], e["vagas_vistas"], e["erros"]))
        horas = sum((e["duracao_seg"] or 0) for e in execucoes) / 3600
        self.lbl_totais.config(text=(f"{len(execucoes)} execução(ões) · {horas:.1f} h monitoradas · "
                                     f"{sum(e['vagas_vistas'] or 0 for e in execucoes)} vaga(s) vista(s) · "
                                     f"{sum(e['matriculadas'] or 0 for e in execucoes)} matrícula(s)"))
        self._escrever("Selecione uma execução para ver o relatório." if execucoes else
                       "Nenhuma execução no período. Cada execução encerrada entra aqui automaticamente.")

    def _escrever(self, texto: str):
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", texto)
        self.txt.config(state="disabled")

    def _mostrar_detalhe(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        detalhe = historico.obter_execucao(sel[0])
        if detalhe:
            self._escrever(texto_relatorio(detalhe["resumo"]))

    def _exportar(self):
        caminho = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="sigaa_sniper_historico.csv",
                                               filetypes=[("Planilha CSV", "*.csv")], title="Exportar histórico")
        if not caminho:
            return
        dias, disciplina = self._filtros()
        with open(caminho, "w", encoding="utf-8", newline="") as f:
            f.write(historico.exportar_execucoes("csv", dias, disciplina))
        messagebox.showinfo("Exportado", f"Histórico exportado para:\n{caminho}")

    def _apagar(self):
        if not messagebox.askyesno("Apagar histórico", "Apagar TODO o histórico de execuções (data/historico.db)? "
                                   "Os resumos em data/relatorios/ não são afetados. Isso não pode ser desfeito."):
            return
        historico.apagar_tudo()
        self.tree.delete(*self.tree.get_children())
        self.lbl_totais.config(text="Histórico apagado.")
        self._escrever("")
