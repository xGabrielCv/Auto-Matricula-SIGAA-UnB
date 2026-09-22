"""Tela de Diagnóstico — seções 39, 44-45, 69-71 do pedido de continuação."""
from __future__ import annotations

import asyncio
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app.core.diagnostics import (
    checar_conectividade_em_camadas, checar_conectividade_sigaa, checar_configuracao,
    checar_dependencias, checar_espaco_em_disco, checar_modo_execucao, checar_python,
    checar_saude_sistema, checar_tamanho_dados, gerar_relatorio_texto,
)


class TelaDiagnostico(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self._ultimo_relatorio = ""
        self._construir()

    def _construir(self):
        ttk.Label(self, text="Diagnóstico", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(self, text="Não inclui credenciais nem tokens.", foreground="#666").pack(anchor="w", pady=(0, 10))

        botoes = ttk.Frame(self)
        botoes.pack(fill="x")
        ttk.Button(botoes, text="🔍 Diagnóstico completo", command=self._rodar).pack(side="left")
        ttk.Button(botoes, text="🌐 Testar conectividade em camadas", command=self._rodar_camadas).pack(side="left", padx=(8, 0))
        ttk.Button(botoes, text="💾 Exportar relatório", command=self._exportar).pack(side="left", padx=(8, 0))
        ttk.Button(botoes, text="📋 Copiar diagnóstico", command=self._copiar).pack(side="left", padx=(8, 0))

        # Frame com scrollbar de verdade pro relatório (podia ficar comprido e
        # sem nenhuma forma óbvia de rolar até o fim) — os botões acima ficam
        # sempre visíveis porque são empacotados primeiro, com tamanho fixo.
        frame_txt = ttk.Frame(self)
        frame_txt.pack(fill="both", expand=True, pady=(10, 0))
        scroll = ttk.Scrollbar(frame_txt)
        scroll.pack(side="right", fill="y")
        self.txt = tk.Text(frame_txt, wrap="word", state="disabled", height=20, yscrollcommand=scroll.set)
        self.txt.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.txt.yview)

    def _rodar(self):
        self._escrever("Rodando diagnóstico completo...\n")
        threading.Thread(target=self._rodar_thread, daemon=True).start()

    def _rodar_thread(self):
        resultados = [
            *checar_saude_sistema(),
            checar_modo_execucao(),
        ]
        try:
            resultados.append(asyncio.run(checar_conectividade_sigaa()))
        except Exception as e:
            from app.core.diagnostics import ResultadoChecagem
            resultados.append(ResultadoChecagem("Conectividade com o SIGAA", False, str(e)))

        relatorio = gerar_relatorio_texto(resultados)
        self.after(0, lambda: self._escrever(relatorio, limpar=True))

    def _rodar_camadas(self):
        self._escrever("Testando conectividade em camadas (Internet → SIGAA → consulta pública → ...)...\n")

        def alvo():
            resultados = asyncio.run(checar_conectividade_em_camadas())
            relatorio = gerar_relatorio_texto(resultados)
            self.after(0, lambda: self._escrever(relatorio, limpar=True))

        threading.Thread(target=alvo, daemon=True).start()

    def _escrever(self, texto, limpar=False):
        self._ultimo_relatorio = texto
        self.txt.config(state="normal")
        if limpar:
            self.txt.delete("1.0", "end")
        self.txt.insert("end", texto)
        self.txt.config(state="disabled")

    def _exportar(self):
        if not self._ultimo_relatorio:
            return
        caminho = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="diagnostico_sigaa_sniper.txt")
        if caminho:
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(self._ultimo_relatorio)

    def _copiar(self):
        if not self._ultimo_relatorio:
            messagebox.showinfo("Nada para copiar", "Rode um diagnóstico primeiro.")
            return
        # O relatório já é sanitizado na origem (gerar_relatorio_texto nunca inclui
        # credenciais) — seção 71 pede uma sanitização "antes de copiar" explicitamente,
        # então revalidamos aqui como segunda camada em vez de confiar só na origem.
        texto = self._ultimo_relatorio
        for termo_proibido in ("senha=", "password=", "token=", "cpf="):
            if termo_proibido in texto.lower():
                messagebox.showerror("Bloqueado", "O relatório parece conter um dado sensível — cópia cancelada por segurança.")
                return
        self.clipboard_clear()
        self.clipboard_append(texto)
        messagebox.showinfo("Copiado", "Diagnóstico copiado para a área de transferência.")
