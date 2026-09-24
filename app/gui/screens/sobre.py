"""Tela "Sobre" — versão, repositório oficial (seção 94.3-94.4) e atalho (seção 94.5)."""
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from app.core.shortcut import GUIA_MANUAL, criar_atalho_area_trabalho, suportado
from app.gui.responsive import tornar_rolavel
from app.versao import URL_REPOSITORIO, VERSAO_APP
from app.gui.tema import cor


class TelaSobre(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self._construir()

    def _construir(self):
        corpo = tornar_rolavel(self)
        ttk.Label(corpo, text="Sobre o SIGAA Sniper", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(corpo, text=f"Versão {VERSAO_APP}", foreground=cor("#666")).pack(anchor="w", pady=(2, 16))

        repo = ttk.LabelFrame(corpo, text="Repositório oficial", padding=14)
        repo.pack(fill="x", pady=(0, 14))
        ttk.Label(
            repo, wraplength=600, justify="left",
            text=(
                "Este é um pacote distribuível do projeto. Para atualizações, correções, "
                "melhorias e versões futuras, consulte o repositório oficial no GitHub — é lá "
                "que o projeto continua evoluindo.\n\n"
                "O projeto é open source. Sugestões de melhorias e relatos de bugs são bem-vindos, "
                "preferencialmente através do GitHub (issues/discussions)."
            ),
        ).pack(anchor="w")

        link = ttk.Label(repo, text=f"🔗 {URL_REPOSITORIO}", foreground=cor("#0969da"), cursor="hand2")
        link.pack(anchor="w", pady=(10, 0))
        link.bind("<Button-1>", lambda _e: webbrowser.open(URL_REPOSITORIO))
        ttk.Button(repo, text="Abrir no navegador", command=lambda: webbrowser.open(URL_REPOSITORIO)).pack(anchor="w", pady=(8, 0))

        # Fase 7: integridade (069) e aviso de versão nova (099).
        from app.core.distribuicao import hash_executavel
        versao = ttk.LabelFrame(corpo, text="Versão e integridade", padding=14)
        versao.pack(fill="x", pady=(0, 14))
        hash_exe = hash_executavel()
        ttk.Label(versao, wraplength=600, justify="left",
                  text=(f"SHA-256 deste executável (compare com o SHA256SUMS.txt do pacote):\n{hash_exe}" if hash_exe
                        else "Rodando pelo código-fonte — não há executável para verificar.")).pack(anchor="w")
        ttk.Button(versao, text="🔄 Verificar se há versão nova", command=self._verificar_atualizacao).pack(anchor="w", pady=(8, 0))
        self.lbl_atualizacao = ttk.Label(versao, text="", wraplength=600, justify="left")
        self.lbl_atualizacao.pack(anchor="w", pady=(6, 0))

        atalho = ttk.LabelFrame(corpo, text="Atalho na Área de Trabalho", padding=14)
        atalho.pack(fill="x", pady=(0, 14))
        ttk.Label(atalho, text="Cria um atalho para abrir o programa direto da Área de Trabalho.").pack(anchor="w")
        ttk.Button(atalho, text="🖥️ Criar atalho", command=self._criar_atalho).pack(anchor="w", pady=(8, 0))
        self.lbl_status_atalho = ttk.Label(atalho, text="", foreground=cor("#1a7f37"))
        self.lbl_status_atalho.pack(anchor="w", pady=(6, 0))

        if not suportado():
            ttk.Label(atalho, text=GUIA_MANUAL, foreground=cor("#666"), wraplength=600, justify="left").pack(anchor="w", pady=(8, 0))

    def _verificar_atualizacao(self):
        import threading
        from app.core.distribuicao import verificar_atualizacao
        self.lbl_atualizacao.config(text="Consultando o GitHub...")

        def alvo():
            r = verificar_atualizacao()
            self.after(0, lambda: self.lbl_atualizacao.config(
                text=r["texto"] + (f"\n{r['url']}" if r.get("nova") else ""),
                foreground=cor("#0969da") if r.get("nova") else cor("#57606a")))

        threading.Thread(target=alvo, daemon=True).start()

    def _criar_atalho(self):
        try:
            caminho = criar_atalho_area_trabalho()
            self.lbl_status_atalho.config(text=f"✅ Atalho criado em: {caminho}", foreground=cor("#1a7f37"))
        except Exception as e:
            self.lbl_status_atalho.config(text=f"❌ Não foi possível criar automaticamente ({e}). Veja o guia manual abaixo.", foreground=cor("#cf222e"))
            messagebox.showinfo("Criar atalho manualmente", GUIA_MANUAL)
