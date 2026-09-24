"""
Tela de Logs (Central de Logs) — seções 18-25 do pedido de continuação.

Mostra os eventos em linguagem simples, com filtros, e um painel de
"detalhes técnicos" expansível para quem quiser o dado bruto. Não depende de
nada além da leitura do arquivo de log (mesmo padrão de app/dashboard —
não interfere no motor).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tkinter as tk
from collections import deque
from tkinter import ttk

from app.dashboard.log_humano import CATEGORIAS, traduzir
from app.dashboard.metrics import LogTailer, criar_tailer_da_sessao  # noqa: F401
from app.utils.paths import caminho as caminho_projeto
from app.gui.tema import cor

CORES_CATEGORIA = {
    "ERRO": cor("#cf222e"), "AVISO": cor("#9a6700"), "SUCESSO": cor("#1a7f37"),
    "REDE": cor("#0969da"), "SEGURANCA": cor("#8250df"), "SISTEMA": cor("#57606a"),
    "MATRICULA": cor("#bf3989"), "MONITORAMENTO": cor("#1a7f37"), "NOTIFICACAO": cor("#0969da"), "DEBUG": cor("#57606a"),
}

MAX_LINHAS_MEMORIA = 1000


class TelaLogs(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self.tailer = criar_tailer_da_sessao(caminho_projeto("data", "sigaa_sniper_audit.json"),
                                             bool(app.settings.get("carregar_ultima_execucao")))
        self.buffer = deque(maxlen=MAX_LINHAS_MEMORIA)
        self.pausado = False
        self.workers_vistos = {"Todos"}
        self._after_id = None
        self._construir()
        self._agendar_atualizacao()
        # Mesmo fix de app/gui/screens/dashboard.py: cancela o after() pendente
        # ao destruir, em vez de só checar winfo_exists() dentro do callback
        # (o Tcl falha ao despachar antes do Python rodar).
        self.bind("<Destroy>", self._cancelar_atualizacao, add="+")

    def _cancelar_atualizacao(self, _event=None):
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _construir(self):
        topo = ttk.Frame(self)
        topo.pack(fill="x")
        ttk.Label(topo, text="Logs", font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Button(topo, text="📂 Abrir arquivo completo", command=self._abrir_arquivo).pack(side="right")
        ttk.Button(topo, text="🧹 Limpar tela", command=self._limpar_tela).pack(side="right", padx=(0, 8))

        filtros = ttk.Frame(self)
        filtros.pack(fill="x", pady=(10, 10))

        ttk.Label(filtros, text="Nível:").grid(row=0, column=0, padx=(0, 4))
        self.var_nivel = tk.StringVar(value="Todos")
        ttk.Combobox(filtros, textvariable=self.var_nivel, values=["Todos", "INFO", "WARNING", "ERROR", "CRITICAL"], width=10, state="readonly").grid(row=0, column=1, padx=(0, 10))

        ttk.Label(filtros, text="Categoria:").grid(row=0, column=2, padx=(0, 4))
        self.var_categoria = tk.StringVar(value="Todas")
        ttk.Combobox(filtros, textvariable=self.var_categoria, values=["Todas"] + CATEGORIAS, width=14, state="readonly").grid(row=0, column=3, padx=(0, 10))

        ttk.Label(filtros, text="Worker:").grid(row=0, column=4, padx=(0, 4))
        self.var_worker = tk.StringVar(value="Todos")
        self.combo_worker = ttk.Combobox(filtros, textvariable=self.var_worker, values=["Todos"], width=10, state="readonly")
        self.combo_worker.grid(row=0, column=5, padx=(0, 10))

        ttk.Label(filtros, text="Buscar texto:").grid(row=0, column=6, padx=(0, 4))
        self.var_busca = tk.StringVar()
        ttk.Entry(filtros, textvariable=self.var_busca, width=20).grid(row=0, column=7, padx=(0, 10))

        self.var_pausar = tk.BooleanVar(value=False)
        ttk.Checkbutton(filtros, text="Pausar atualização", variable=self.var_pausar).grid(row=0, column=8, padx=(4, 0))

        for var in (self.var_nivel, self.var_categoria, self.var_worker, self.var_busca):
            var.trace_add("write", lambda *_: self._renderizar())

        divisor = ttk.PanedWindow(self, orient="vertical")
        divisor.pack(fill="both", expand=True)

        frame_lista = ttk.Frame(divisor)
        colunas = ("hora", "worker", "categoria", "nivel", "titulo")
        self.tree = ttk.Treeview(frame_lista, columns=colunas, show="headings", height=18)
        for col, titulo, largura in [
            ("hora", "Hora", 90), ("worker", "Worker", 70), ("categoria", "Categoria", 110),
            ("nivel", "Nível", 80), ("titulo", "Evento", 400),
        ]:
            self.tree.heading(col, text=titulo)
            self.tree.column(col, width=largura, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._mostrar_detalhes)
        divisor.add(frame_lista, weight=3)

        frame_detalhes = ttk.LabelFrame(divisor, text="Detalhes", padding=8)
        self.txt_corpo = tk.Text(frame_detalhes, height=4, wrap="word")
        self.txt_corpo.pack(fill="x")
        self.txt_corpo.config(state="disabled")

        self.var_tecnico = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame_detalhes, text="Mostrar detalhes técnicos", variable=self.var_tecnico, command=self._mostrar_detalhes).pack(anchor="w", pady=(6, 0))
        self.txt_tecnico = tk.Text(frame_detalhes, height=5, wrap="word", state="disabled", background=cor("#f6f8fa"))
        self.txt_tecnico.pack(fill="both", expand=True, pady=(4, 0))
        divisor.add(frame_detalhes, weight=1)

        self._registros_por_iid = {}

    # ── Atualização ──────────────────────────────────────────────────────

    def _garantir_tailer(self):
        if self.tailer is None:
            caminho_log = caminho_projeto("data", "sigaa_sniper_audit.json")
            if os.path.exists(caminho_log):
                self.tailer = LogTailer(caminho_log)

    def _agendar_atualizacao(self):
        if not self.winfo_exists():
            return
        self._atualizar()
        self._after_id = self.after(700, self._agendar_atualizacao)

    def _atualizar(self):
        if self.var_pausar.get():
            return
        self._garantir_tailer()
        if not self.tailer:
            return
        novas = self.tailer.read_new_lines()
        if not novas:
            return
        for linha in novas:
            try:
                registro = json.loads(linha)
            except (json.JSONDecodeError, ValueError):
                continue
            self.buffer.append(registro)
            worker = registro.get("worker", "MAIN")
            if worker not in self.workers_vistos:
                self.workers_vistos.add(worker)
                self.combo_worker["values"] = ["Todos"] + sorted(w for w in self.workers_vistos if w != "Todos")
        self._renderizar()

    def _passa_filtro(self, registro: dict, evento) -> bool:
        if self.var_nivel.get() != "Todos" and registro.get("level") != self.var_nivel.get():
            return False
        if self.var_categoria.get() != "Todas" and evento.categoria != self.var_categoria.get():
            return False
        if self.var_worker.get() != "Todos" and registro.get("worker") != self.var_worker.get():
            return False
        busca = self.var_busca.get().strip().lower()
        if busca and busca not in evento.titulo.lower() and busca not in evento.corpo.lower() and busca not in evento.mensagem_original.lower():
            return False
        return True

    def _renderizar(self):
        self.tree.delete(*self.tree.get_children())
        self._registros_por_iid.clear()

        for i, registro in enumerate(self.buffer):
            evento = traduzir(registro)
            if not self._passa_filtro(registro, evento):
                continue
            hora = registro.get("timestamp", "")[-8:]
            iid = str(i)
            self.tree.insert(
                "", "end", iid=iid,
                values=(hora, evento.worker, evento.categoria, evento.nivel, evento.titulo),
                tags=(evento.categoria,),
            )
            self._registros_por_iid[iid] = (registro, evento)

        for cat, tom in CORES_CATEGORIA.items():
            self.tree.tag_configure(cat, foreground=tom)

        filhos = self.tree.get_children()
        if filhos:
            self.tree.see(filhos[-1])

    def _mostrar_detalhes(self, _event=None):
        sel = self.tree.selection()
        self.txt_corpo.config(state="normal")
        self.txt_corpo.delete("1.0", "end")
        self.txt_tecnico.config(state="normal")
        self.txt_tecnico.delete("1.0", "end")

        if sel and sel[0] in self._registros_por_iid:
            registro, evento = self._registros_por_iid[sel[0]]
            self.txt_corpo.insert("1.0", evento.corpo)
            if self.var_tecnico.get():
                bruto = json.dumps(registro, ensure_ascii=False, indent=2)
                self.txt_tecnico.insert("1.0", bruto)

        self.txt_corpo.config(state="disabled")
        self.txt_tecnico.config(state="disabled")

    def _limpar_tela(self):
        """Limpa só a visualização — o arquivo de log continua intacto (seção 21)."""
        self.buffer.clear()
        self._renderizar()

    def _abrir_arquivo(self):
        caminho_log = caminho_projeto("data", "sigaa_sniper_audit.json")
        if not os.path.exists(caminho_log):
            return
        try:
            if sys.platform == "win32":
                os.startfile(caminho_log)
            elif sys.platform == "darwin":
                subprocess.run(["open", caminho_log])
            else:
                subprocess.run(["xdg-open", caminho_log])
        except Exception:
            pass
