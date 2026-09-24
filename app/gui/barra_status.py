"""
Barra de status global da GUI (sugestão 009): fica acima de todas as abas e
mostra, o tempo todo, se o motor está parado ou rodando — e em qual modo.
Matrícula REAL (DRY RUN desligado) aparece em vermelho para nunca passar
despercebida, como no cabeçalho da Interface Web.

À direita, a carga estimada da configuração atual (sugestão 043).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.core.config import estimar_carga
from app.gui.tema import cor

# (fundo, texto)
CORES = {
    "parado": (cor("#eaeef2"), cor("#24292f")),
    "monitoramento": (cor("#dafbe1"), cor("#116329")),
    "dry_run": (cor("#fff8c5"), cor("#7d4e00")),
    "real": (cor("#cf222e"), cor("#ffffff")),
    "parando": (cor("#fff8c5"), cor("#7d4e00")),
}
COR_CARGA = {"baixa": cor("#1a7f37"), "moderada": cor("#9a6700"), "alta": cor("#cf222e"), "desconhecida": cor("#57606a")}


def descrever_estado(estado: dict) -> tuple:
    """(texto, chave de cor) a partir de SniperApp.estado_execucao()."""
    if not estado.get("em_execucao"):
        return "⚪ Parado", "parado"
    if estado.get("parando"):
        return "🟡 Parando… (aguardando os workers atuais encerrarem)", "parando"
    if estado.get("pausado"):
        if estado.get("motivo_pausa") == "janela":
            return "⏸️ Pausado · fora da janela de execução (volta sozinho)", "parando"
        return "⏸️ Pausado pelo usuário · sessões mantidas", "parando"
    if estado.get("demo"):
        return "🎓 DEMONSTRAÇÃO · SIGAA simulado (nada vai para o SIGAA de verdade)", "monitoramento"
    if estado.get("modo") == "monitoramento":
        return "🟢 Em execução · Somente monitoramento (nunca matricula)", "monitoramento"
    if estado.get("dry_run", True):
        return "🟢 Em execução · Matrícula em DRY RUN (teste — não confirma)", "dry_run"
    return "🔴 Em execução · MATRÍCULA REAL — confirma de verdade ao achar vaga", "real"


class BarraStatus(tk.Frame):
    INTERVALO_MS = 1000

    def __init__(self, parent, app):
        super().__init__(parent, padx=12, pady=6)
        self.app = app
        self.lbl_estado = tk.Label(self, text="⚪ Parado", font=("Segoe UI", 10, "bold"), anchor="w")
        self.lbl_estado.pack(side="left")
        self.lbl_carga = tk.Label(self, text="", font=("Segoe UI", 9), anchor="e")
        self.lbl_carga.pack(side="right")
        self._after_id = None
        self.bind("<Destroy>", self._cancelar, add="+")
        self.atualizar()

    def _cancelar(self, _event=None):
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def atualizar_agora(self):
        """Reflete uma mudança na hora (ex: clicou em Iniciar/Parar), sem esperar o próximo ciclo."""
        self._cancelar()
        self.atualizar()

    def atualizar(self):
        try:
            texto, chave = descrever_estado(self.app.estado_execucao())
            fundo, tom = CORES[chave]
            self.config(bg=fundo)
            self.lbl_estado.config(text=texto, bg=fundo, fg=tom)
            s = self.app.settings
            ativas = sum(1 for d in self.app.disciplinas if d.ativa)
            carga = estimar_carga(s.get("num_workers"), s.get("intervalo_busca"), ativas, s.get("protecao", {}).get("limite_req_por_seg", 0))
            texto_carga = f"Carga estimada ≈ {carga['req_por_seg']} req/s ({carga['nivel']})" if carga["req_por_seg"] is not None else ""
            self.lbl_carga.config(text=texto_carga, bg=fundo,
                                  fg=tom if chave == "real" else COR_CARGA.get(carga["nivel"], cor("#57606a")))
        except Exception:
            pass  # a barra é informativa: nunca pode derrubar a GUI
        self._after_id = self.after(self.INTERVALO_MS, self.atualizar)
