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
from app.gui.tema import cor


class TelaDiagnostico(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self._ultimo_relatorio = ""
        self._construir()

    def _construir(self):
        ttk.Label(self, text="Diagnóstico", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(self, text="Não inclui credenciais nem tokens.", foreground=cor("#666")).pack(anchor="w", pady=(0, 10))

        botoes = ttk.Frame(self)
        botoes.pack(fill="x")
        ttk.Button(botoes, text="🔍 Diagnóstico completo", command=self._rodar).pack(side="left")
        ttk.Button(botoes, text="🌐 Testar conectividade em camadas", command=self._rodar_camadas).pack(side="left", padx=(8, 0))
        ttk.Button(botoes, text="💾 Exportar relatório", command=self._exportar).pack(side="left", padx=(8, 0))
        ttk.Button(botoes, text="📋 Copiar diagnóstico", command=self._copiar).pack(side="left", padx=(8, 0))

        # Fase 5: assistente (079), recomendações (089), páginas capturadas (064), pacote de suporte (051).
        extras = ttk.Frame(self)
        extras.pack(fill="x", pady=(8, 0))
        ttk.Button(extras, text="🧭 Assistente de problemas", command=self._assistente).pack(side="left")
        ttk.Button(extras, text="💡 Recomendações", command=self._recomendacoes).pack(side="left", padx=(8, 0))
        ttk.Button(extras, text="📄 Páginas capturadas", command=self._paginas).pack(side="left", padx=(8, 0))
        ttk.Button(extras, text="📦 Pacote de suporte", command=self._pacote).pack(side="left", padx=(8, 0))

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
        from app.core.seguranca_config import checar_configuracoes_inseguras
        resultados = [
            *checar_saude_sistema(),
            checar_modo_execucao(),
            *checar_configuracoes_inseguras(),
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

    # ── Fase 5 ────────────────────────────────────────────────────────────

    def _contexto(self) -> dict:
        from app.core.relatorios import listar_relatorios
        motor = getattr(self.app, "_motor", None)
        snap = motor.snapshot() if motor is not None and hasattr(motor, "snapshot") else None
        ultima = None
        if snap is None:
            lista = listar_relatorios(1)
            ultima = lista[0] if lista else None
        return {"snap": snap, "ultima": ultima}

    def _assistente(self):
        from app.core.assistente import SINTOMAS, diagnosticar
        janela = tk.Toplevel(self)
        janela.title("Assistente de solução de problemas")
        janela.transient(self.winfo_toplevel())
        ttk.Label(janela, text="O que está acontecendo?", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=14, pady=(12, 6))
        var = tk.StringVar(value=next(iter(SINTOMAS)))
        for chave, texto in SINTOMAS.items():
            ttk.Radiobutton(janela, text=texto, variable=var, value=chave).pack(anchor="w", padx=14)

        def analisar():
            r = diagnosticar(var.get(), self.app.settings, self.app.disciplinas, self.app.sessao.sigaa, **self._contexto())
            rotulo = {"certa": "CONFIRMADO", "provavel": "PROVÁVEL", "sugestao": "VERIFIQUE"}
            linhas = [f"🧭 {r['pergunta']}", f"(analisado com base em {r['fonte'] or 'nenhuma execução'} e na configuração atual)", ""]
            for a in r["achados"]:
                linhas.append(f"[{rotulo[a['certeza']]}] {a['causa']}")
                if a["evidencia"]:
                    linhas.append(f"   Evidência: {a['evidencia']}")
                linhas.append(f"   O que fazer: {a['acao']}")
                linhas.append("")
            self._escrever("\n".join(linhas), limpar=True)
            janela.destroy()

        ttk.Button(janela, text="Analisar", command=analisar).pack(anchor="e", padx=14, pady=12)

    def _recomendacoes(self):
        from app.core.assistente import aplicar_recomendacao, recomendar_configuracao
        recs = recomendar_configuracao(self.app.settings, **self._contexto())
        if not recs:
            self._escrever("💡 Nenhuma recomendação agora.\n\nElas aparecem quando uma execução tem métricas suficientes "
                           "(pelo menos 100 buscas) e algo pode ser melhor ajustado.", limpar=True)
            return
        self._escrever("💡 Recomendações de configuração\n\n" + "\n\n".join(f"• {r['texto']}\n  {r['motivo']}" for r in recs), limpar=True)
        for r in recs:
            if messagebox.askyesno("Aplicar recomendação?", f"{r['texto']}\n\n{r['motivo']}\n\nVale a partir da próxima execução."):
                novos = dict(self.app.settings)
                problemas = aplicar_recomendacao(novos, r)
                if problemas:
                    messagebox.showwarning("Não aplicado", "\n".join(problemas))
                    continue
                self.app.settings = novos
                self.app.salvar_settings()

    def _paginas(self):
        from app.core.suporte import ler_dump, listar_dumps
        dumps = listar_dumps()
        if not dumps:
            self._escrever("📄 Nenhuma página capturada — bom sinal.\n\nQuando uma página do SIGAA não vem como esperado, "
                           "ela é guardada (com dados pessoais mascarados) e aparece aqui.", limpar=True)
            return
        janela = tk.Toplevel(self)
        janela.title("Páginas capturadas (dados pessoais mascarados)")
        janela.transient(self.winfo_toplevel())
        lista = tk.Listbox(janela, width=90, height=min(12, len(dumps)))
        for d in dumps:
            lista.insert("end", f"{d['quando'] or '—'}  {d['worker']}  {d['motivo_texto']}  ({d['tamanho_kb']} KB)")
        lista.pack(fill="both", expand=True, padx=12, pady=(12, 6))

        def ver(_evento=None):
            sel = lista.curselection()
            if not sel:
                return
            lido = ler_dump(dumps[sel[0]]["nome"], self.app.sessao.sigaa)
            if lido:
                self._escrever(f"📄 {lido['motivo_texto']} — {lido['quando']} ({lido['worker']})\n"
                               "Dados pessoais mascarados com ***.\n\n" + (lido["texto"] or "(página sem texto visível)"), limpar=True)
            janela.destroy()

        lista.bind("<Double-Button-1>", ver)
        ttk.Button(janela, text="Ver como texto", command=ver).pack(anchor="e", padx=12, pady=(0, 12))

    def _pacote(self):
        from app.core.suporte import conteudo_pacote_suporte, gerar_pacote_suporte, nome_pacote_suporte
        conteudo = conteudo_pacote_suporte(self.app.sessao.sigaa)
        resumo = "\n".join(f"• {a['nome']} ({a['tamanho_kb']} KB) — {a['descricao']}" for a in conteudo)
        if not messagebox.askyesno("Pacote de suporte", "O pacote vai conter (dados pessoais mascarados):\n\n" + resumo
                                   + "\n\nSenha, CPF, data de nascimento e tokens nunca entram. Salvar agora?"):
            return
        caminho = filedialog.asksaveasfilename(defaultextension=".zip", initialfile=nome_pacote_suporte(),
                                               filetypes=[("Arquivo ZIP", "*.zip")])
        if caminho:
            with open(caminho, "wb") as f:
                f.write(gerar_pacote_suporte(self.app.sessao.sigaa))
            self._escrever(f"📦 Pacote de suporte salvo em:\n{caminho}\n\nConteúdo:\n{resumo}\n\nConfira antes de compartilhar.", limpar=True)

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
