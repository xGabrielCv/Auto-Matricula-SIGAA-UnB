"""
Aba de Dashboard da GUI — seções 18-21 do pedido.

Reaproveita exatamente o mesmo ColetorMetricas/LogTailer usado pelo painel
de terminal (app/dashboard/metrics.py): mesma fonte de verdade, duas telas.
A leitura do log acontece com `self.after(...)` na thread principal do
Tkinter, então nunca compete com o motor (que roda em outra thread) por
acesso a widgets — só lê um arquivo, o que é seguro entre threads.
"""
from __future__ import annotations

import os
import re

import tkinter as tk
from tkinter import ttk

from app.dashboard.metrics import ColetorMetricas, LogTailer, formatar_uptime
from app.gui.responsive import tornar_rolavel
from app.utils.paths import caminho as caminho_projeto

SEM_DADOS = "sem dados"


def _fmt(v, sufixo="", casas=1):
    return f"{v:.{casas}f}{sufixo}" if v is not None else SEM_DADOS


def _fmt_ms(v):
    return f"{v:.0f} ms" if v is not None else SEM_DADOS


COR_SAUDE = {
    "aguardando_trafego": ("Aguardando tráfego", "#9a6700"),
    "estavel": ("✅ Sistema estável", "#1a7f37"),
    "degradado": ("⚠️ Degradado", "#9a6700"),
    "critico": ("📛 Crítico", "#cf222e"),
}


class TelaDashboard(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self.coletor = ColetorMetricas()
        self.tailer = None
        self._after_id = None
        self._construir()
        self._agendar_atualizacao()
        # Bug real encontrado em teste: checar winfo_exists() DENTRO do
        # callback não basta — o Tcl já falha ao tentar DESPACHAR o comando
        # agendado numa janela cujo interpretador já foi destruído (erro
        # "invalid command name" acontece antes do código Python rodar).
        # A correção de verdade é cancelar o after() pendente explicitamente
        # quando o widget é destruído.
        self.bind("<Destroy>", self._cancelar_atualizacao, add="+")

    def _cancelar_atualizacao(self, _event=None):
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _construir(self):
        # Corrige um problema real de usabilidade: cards + workers + painéis de
        # vagas/erros empilhados podiam ultrapassar a altura da janela sem
        # nenhuma forma de rolar até o fim. Agora tudo fica numa área rolável.
        corpo = tornar_rolavel(self)

        topo = ttk.Frame(corpo)
        topo.pack(fill="x")
        ttk.Label(topo, text="Dashboard ao vivo", font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Button(topo, text="📜 Ver logs", command=lambda: self.app._mostrar("logs")).pack(side="right", padx=(0, 10))
        self.lbl_saude = ttk.Label(topo, text="—", font=("Segoe UI", 10, "bold"))
        self.lbl_saude.pack(side="right", padx=(0, 10))

        cards = ttk.Frame(corpo)
        cards.pack(fill="x", pady=(10, 10))
        self.labels_cards = {}
        campos = [
            ("rps", "Requisições/s"), ("bps", "Buscas/s"), ("latencia", "Latência (últ. 100)"),
            ("total_buscas", "Total de buscas"), ("vagas", "Vagas encontradas"), ("uptime", "Tempo rodando"),
        ]
        for i, (chave, rotulo) in enumerate(campos):
            card = ttk.LabelFrame(cards, text=rotulo, padding=8)
            card.grid(row=i // 3, column=i % 3, sticky="ew", padx=4, pady=4)
            cards.columnconfigure(i % 3, weight=1)
            lbl = ttk.Label(card, text="—", font=("Segoe UI", 12, "bold"))
            lbl.pack()
            self.labels_cards[chave] = lbl

        self.lbl_alerta_workers = ttk.Label(corpo, text="", foreground="#cf222e", wraplength=900, justify="left")
        self.lbl_alerta_workers.pack(anchor="w", pady=(4, 0))

        cabecalho_workers = ttk.Frame(corpo)
        cabecalho_workers.pack(fill="x", pady=(10, 4))
        ttk.Label(cabecalho_workers, text="Workers", font=("Segoe UI", 11, "bold")).pack(side="left")
        colunas = ("worker", "erros", "buscas", "acao", "latencia", "idle")
        self.tree = ttk.Treeview(corpo, columns=colunas, show="headings", height=8)
        for col, titulo, largura in [
            ("worker", "Worker", 70), ("erros", "Erros", 60), ("buscas", "Buscas", 70),
            ("acao", "Última ação", 220), ("latencia", "Latência", 90), ("idle", "Ocioso", 90),
        ]:
            self.tree.heading(col, text=titulo)
            self.tree.column(col, width=largura, anchor="center" if col != "acao" else "w")
        self.tree.pack(fill="both", expand=True)

        base = ttk.Frame(corpo)
        base.pack(fill="both", expand=True, pady=(10, 0))
        base.configure(height=180)
        base.pack_propagate(False)  # dentro de uma área rolável, garante que vagas/erros tenham altura própria em vez de colapsar a zero
        base.columnconfigure(0, weight=2)
        base.columnconfigure(1, weight=1)

        vagas_frame = ttk.LabelFrame(base, text="Eventos recentes de vagas", padding=8)
        vagas_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.txt_vagas = tk.Text(vagas_frame, height=6, wrap="word", state="disabled")
        self.txt_vagas.pack(fill="both", expand=True)
        ttk.Button(vagas_frame, text="📈 Ver histórico por disciplina", command=self._ver_historico_vagas).pack(anchor="w", pady=(4, 0))

        erros_frame = ttk.LabelFrame(base, text="Erros recentes", padding=8)
        erros_frame.grid(row=0, column=1, sticky="nsew")
        self.txt_erros = tk.Text(erros_frame, height=6, wrap="word", state="disabled")
        self.txt_erros.pack(fill="both", expand=True)

    def _garantir_tailer(self):
        if self.tailer is None:
            caminho_log = caminho_projeto("data", "sigaa_sniper_audit.json")
            if os.path.exists(caminho_log):
                self.tailer = LogTailer(caminho_log)

    def _agendar_atualizacao(self):
        if not self.winfo_exists():
            return
        self._atualizar()
        self._after_id = self.after(500, self._agendar_atualizacao)

    def _atualizar(self):
        self._garantir_tailer()
        if self.tailer:
            for linha in self.tailer.read_new_lines():
                self.coletor.processar_linha(linha, ao_vivo=True)

        m = self.coletor.snapshot()

        texto_saude, cor = COR_SAUDE[m["saude"]["status"]]
        self.lbl_saude.config(text=texto_saude, foreground=cor)

        self.labels_cards["rps"].config(text=_fmt(m["rps_atual"], " req/s"))
        self.labels_cards["bps"].config(text=_fmt(m["bps_atual"], " bps"))
        self.labels_cards["latencia"].config(text=_fmt_ms(m["latencia_recente_ms"]))
        self.labels_cards["total_buscas"].config(text=str(m["total_buscas"]))
        self.labels_cards["vagas"].config(text=str(m["vagas_encontradas"]))
        self.labels_cards["uptime"].config(text=formatar_uptime(m["uptime_bot_seg"]))

        self._atualizar_workers(m["workers"])
        self._atualizar_texto(self.txt_vagas, m["registro_vagas"])
        self._atualizar_texto(self.txt_erros, m["log_erros"])
        self._historico_vagas_atual = m["historico_vagas"]

        if m["workers_com_alerta"]:
            self.lbl_alerta_workers.config(text="⚠ Possível problema detectado: " + " | ".join(m["workers_com_alerta"]))
        else:
            self.lbl_alerta_workers.config(text="")

    def _ver_historico_vagas(self):
        historico = getattr(self, "_historico_vagas_atual", {})
        janela = tk.Toplevel(self)
        janela.title("Histórico de vagas por disciplina")
        janela.geometry("420x420")
        txt = tk.Text(janela, wrap="word", padx=10, pady=10, state="normal")
        if not historico:
            txt.insert("1.0", "Ainda não há histórico suficiente nesta execução.")
        else:
            for disciplina, entradas in historico.items():
                txt.insert("end", f"{disciplina}\n")
                for hora, vagas in entradas:
                    txt.insert("end", f"  {hora} — {vagas} vaga(s)\n")
                txt.insert("end", "\n")
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)
        ttk.Button(janela, text="Fechar", command=janela.destroy).pack(pady=6)

    def _atualizar_workers(self, workers: dict):
        import time
        agora = time.time()

        def ordenar(k):
            mm = re.match(r"^W(\d+)$", k)
            return int(mm.group(1)) if mm else 9999

        vistos = set()
        for w_id in sorted(workers.keys(), key=ordenar):
            w = workers[w_id]
            ocioso = agora - w["timestamp"]
            lat = w["latencia"]
            valores = (w_id, w["erros_count"], w["buscas_feitas"], w["ultima_acao"], f"{lat} ms" if lat else "-", f"{ocioso:.1f}s")
            if self.tree.exists(w_id):
                self.tree.item(w_id, values=valores)
            else:
                self.tree.insert("", "end", iid=w_id, values=valores)
            vistos.add(w_id)

        for item in self.tree.get_children():
            if item not in vistos:
                self.tree.delete(item)

    def _atualizar_texto(self, widget: tk.Text, linhas: list):
        conteudo_atual = widget.get("1.0", "end-1c")
        novo_conteudo = "\n".join(linhas) if linhas else "(nenhum evento ainda)"
        if conteudo_atual != novo_conteudo:
            widget.config(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", novo_conteudo)
            widget.config(state="disabled")
