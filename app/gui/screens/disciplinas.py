"""Tela de Disciplinas — seção 25 do pedido. Persistido em config/disciplinas.json (não é sensível)."""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk, messagebox

from app.core.config import Disciplina, analisar_disciplina, interpretar_lote, salvar_disciplinas
from app.core.departamentos import buscar_departamentos, codigo_conhecido, nome_do_departamento
from app.core.textos import TEXTO_AJUDA_DEPARTAMENTO, TEXTO_AJUDA_LOTE
from app.gui.tema import cor


class DialogoDisciplina(tk.Toplevel):
    """Formulário modal de adicionar/editar uma disciplina."""

    def __init__(self, parent, disciplina: Disciplina = None):
        super().__init__(parent)
        self.title("Disciplina")
        self.resizable(False, False)
        self.resultado: Disciplina = None
        self.transient(parent)
        self.update_idletasks()  # garante que a janela esteja mapeada antes do grab_set (ver app/gui/app.py)
        self.grab_set()

        self._original = disciplina  # ao editar, não conta como duplicata de si mesma
        d = disciplina or Disciplina(codigo="", turma="", departamento=0)

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        aviso = ttk.Frame(frame, padding=8, relief="solid", borderwidth=1)
        aviso.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(
            aviso, foreground=cor("#9a6700"), wraplength=380, justify="left",
            text=(
                "⚠️ O código do departamento pode mudar — o SIGAA é quem define esse\n"
                "número, não este programa. Se parar de funcionar, use o botão\n"
                "\"Como encontrar?\" abaixo para verificar o valor atual."
            ),
        ).pack(anchor="w")

        self.var_codigo = tk.StringVar(value=d.codigo)
        self.var_turma = tk.StringVar(value=d.turma)
        self.var_professor = tk.StringVar(value=d.professor)

        ttk.Label(frame, text="Código da disciplina (ex: FGA0211):").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.var_codigo, width=34).grid(row=1, column=1, pady=4, padx=(8, 0))

        ttk.Label(frame, text="Turma (ex: 01):").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.var_turma, width=34).grid(row=2, column=1, pady=4, padx=(8, 0))

        # Desde a 6.1.0: o código é digitado OU escolhido na lista completa ("Ver departamentos");
        # nada de lista aparecendo sozinha enquanto se digita.
        ttk.Label(frame, text="Código do departamento (ex: 673):").grid(row=3, column=0, sticky="w", pady=4)
        linha_depto = ttk.Frame(frame)
        linha_depto.grid(row=3, column=1, sticky="w", pady=4, padx=(8, 0))
        self.var_depto_busca = tk.StringVar(value=str(d.departamento) if d.departamento else "")
        self.entrada_depto = ttk.Entry(linha_depto, textvariable=self.var_depto_busca, width=10)
        self.entrada_depto.pack(side="left")
        ttk.Button(linha_depto, text="📋 Ver departamentos", command=self._ver_departamentos).pack(side="left", padx=(6, 0))
        self.var_depto_busca.trace_add("write", lambda *_: self._atualizar_busca_departamento())

        ttk.Button(frame, text="Como encontrar o código?", command=self._mostrar_ajuda_departamento).grid(row=4, column=1, sticky="w", padx=(8, 0), pady=(0, 6))

        self.lbl_aviso_depto = ttk.Label(frame, text="", foreground=cor("#9a6700"), wraplength=380, justify="left")
        self.lbl_aviso_depto.grid(row=5, column=0, columnspan=2, sticky="w")

        ttk.Label(frame, text="Professor (opcional):").grid(row=6, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.var_professor, width=34).grid(row=6, column=1, pady=4, padx=(8, 0))

        # Fase 4: grupo de turmas alternativas (033) e prioridade (034).
        from app.core.textos import TEXTO_AJUDA_GRUPO, TEXTO_AJUDA_PRIORIDADE
        rot_grupo = ttk.Frame(frame)
        rot_grupo.grid(row=7, column=0, sticky="w", pady=4)
        ttk.Label(rot_grupo, text="Grupo de alternativas (opcional):").pack(side="left")
        ttk.Button(rot_grupo, text="?", width=2, command=lambda: messagebox.showinfo("Grupo de alternativas", TEXTO_AJUDA_GRUPO, parent=self)).pack(side="left", padx=(4, 0))
        self.var_grupo = tk.StringVar(value=d.grupo)
        existentes = getattr(getattr(parent, "app", None), "disciplinas", [])
        ttk.Combobox(frame, textvariable=self.var_grupo, width=32,
                     values=sorted({x.grupo for x in existentes if x.grupo})).grid(row=7, column=1, pady=4, padx=(8, 0))
        rot_prio = ttk.Frame(frame)
        rot_prio.grid(row=8, column=0, sticky="w", pady=4)
        ttk.Label(rot_prio, text="Prioridade:").pack(side="left")
        ttk.Button(rot_prio, text="?", width=2, command=lambda: messagebox.showinfo("Prioridade", TEXTO_AJUDA_PRIORIDADE, parent=self)).pack(side="left", padx=(4, 0))
        self.var_prioridade = tk.StringVar(value=d.prioridade)
        ttk.Combobox(frame, textvariable=self.var_prioridade, values=["alta", "normal", "baixa"], state="readonly",
                     width=32).grid(row=8, column=1, pady=4, padx=(8, 0))
        ttk.Label(frame, text="Mesmo grupo = alternativas (garantida uma, as outras saem da busca). Prioridade só define a ordem das consultas.",
                  foreground=cor("#57606a"), wraplength=380).grid(row=9, column=0, columnspan=2, sticky="w")

        botoes = ttk.Frame(frame)
        botoes.grid(row=10, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(botoes, text="Salvar", command=self._salvar).pack(side="right")

        self._atualizar_busca_departamento()  # só depois de TODOS os widgets acima existirem

    def _atualizar_busca_departamento(self, _event=None):
        if not hasattr(self, "lbl_aviso_depto"):
            return
        texto = self.var_depto_busca.get().strip()
        if not texto:
            self.lbl_aviso_depto.config(text="Digite o código ou use \"Ver departamentos\".", foreground=cor("#57606a"))
        elif not texto.isdigit():
            self.lbl_aviso_depto.config(text="O código é só o número. Para procurar pelo nome, use \"Ver departamentos\".",
                                        foreground=cor("#9a6700"))
        elif codigo_conhecido(int(texto)):
            self.lbl_aviso_depto.config(text=f"✔ {texto} — {nome_do_departamento(int(texto))}", foreground=cor("#1a7f37"))
        else:
            self.lbl_aviso_depto.config(text=f"⚠️ {texto} não está na lista de referência (pode ser novo) — confira o código.",
                                        foreground=cor("#9a6700"))

    def _ver_departamentos(self):
        from app.gui.escolher_departamento import escolher_departamento
        r = escolher_departamento(self)
        if r:
            self.var_depto_busca.set(str(r[0]))

    def _mostrar_ajuda_departamento(self):
        janela = tk.Toplevel(self)
        janela.title("Como encontrar o código do departamento")
        janela.geometry("460x320")
        txt = tk.Text(janela, wrap="word", padx=10, pady=10)
        txt.insert("1.0", TEXTO_AJUDA_DEPARTAMENTO)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)
        ttk.Button(janela, text="Fechar", command=janela.destroy).pack(pady=6)

    def _extrair_codigo_departamento(self) -> int:
        texto = self.var_depto_busca.get().strip()
        m = re.match(r"^(\d+)\s*—", texto)
        if m:
            return int(m.group(1))
        if texto.isdigit():
            return int(texto)
        return 0

    def _salvar(self):
        nova = Disciplina(
            codigo=self.var_codigo.get().strip().upper(), turma=self.var_turma.get().strip(),
            departamento=self._extrair_codigo_departamento(), professor=self.var_professor.get().strip(),
            grupo=self.var_grupo.get().strip()[:40], prioridade=self.var_prioridade.get() or "normal",
        )
        # Mesma regra da Web e do terminal (app/core/config.py: analisar_disciplina).
        existentes = getattr(getattr(self.master, "app", None), "disciplinas", [])
        ignorar = next((i for i, d in enumerate(existentes) if d is self._original), None)
        erros, avisos = analisar_disciplina(nova, existentes, ignorar)
        if erros:
            messagebox.showwarning("Dados inválidos", "\n\n".join(erros), parent=self)
            return
        if avisos and not messagebox.askyesno(
            "Confira antes de salvar", "\n\n".join(avisos) + "\n\nSalvar mesmo assim?", parent=self,
        ):
            return

        self.resultado = nova
        self.destroy()


class DialogoLote(tk.Toplevel):
    """Cadastro de várias disciplinas de uma vez (sugestão 005): colar →
    pré-visualizar com validação por linha → confirmar. Nada é salvo antes."""

    def __init__(self, parent, existentes):
        super().__init__(parent)
        self.title("Adicionar várias disciplinas")
        self.existentes = existentes
        self.resultado = []
        self._itens = []
        self.transient(parent)
        self.update_idletasks()
        self.grab_set()

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=TEXTO_AJUDA_LOTE, justify="left", foreground=cor("#57606a")).pack(anchor="w")
        self.txt = tk.Text(frame, height=8, width=60, wrap="none")
        self.txt.pack(fill="x", pady=(8, 6))
        ttk.Button(frame, text="🔍 Pré-visualizar", command=self._previsualizar).pack(anchor="w")

        colunas = ("linha", "disciplina", "situacao", "detalhe")
        self.tree = ttk.Treeview(frame, columns=colunas, show="headings", height=7)
        for col, titulo, largura in [("linha", "Linha", 50), ("disciplina", "Disciplina", 110),
                                     ("situacao", "Situação", 90), ("detalhe", "Detalhe", 380)]:
            self.tree.heading(col, text=titulo)
            self.tree.column(col, width=largura, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=(8, 6))
        self.lbl_resumo = ttk.Label(frame, text="Cole as linhas e clique em Pré-visualizar.")
        self.lbl_resumo.pack(anchor="w")

        botoes = ttk.Frame(frame)
        botoes.pack(fill="x", pady=(10, 0))
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        self.btn_adicionar = ttk.Button(botoes, text="Adicionar", command=self._adicionar, state="disabled")
        self.btn_adicionar.pack(side="right")

    def _previsualizar(self):
        self._itens = interpretar_lote(self.txt.get("1.0", "end"), self.existentes)
        self.tree.delete(*self.tree.get_children())
        validas = 0
        for it in self._itens:
            d = it["disciplina"]
            if it["erros"]:
                situacao, detalhe = "❌ erro", it["erros"][0]
            elif it["avisos"]:
                situacao, detalhe = "⚠️ aviso", it["avisos"][0]
                validas += 1
            else:
                situacao, detalhe = "✅ ok", ""
                validas += 1
            self.tree.insert("", "end", values=(it["linha"], d.chave() if d else it["texto"][:20], situacao, detalhe))
        invalidas = sum(1 for it in self._itens if it["erros"])
        self.lbl_resumo.config(text=f"{validas} válida(s) para adicionar, {invalidas} com erro (serão ignoradas).")
        self.btn_adicionar.config(text=f"Adicionar {validas}", state="normal" if validas else "disabled")

    def _adicionar(self):
        # Reinterpreta na hora de salvar (o texto pode ter mudado depois da prévia).
        self._previsualizar()
        validos = [it for it in self._itens if it["disciplina"] and not it["erros"]]
        if not validos:
            return
        com_aviso = [it for it in validos if it["avisos"]]
        if com_aviso and not messagebox.askyesno(
            "Confirmar cadastro em lote",
            f"{len(com_aviso)} linha(s) têm avisos (ex.: linha {com_aviso[0]['linha']}: {com_aviso[0]['avisos'][0]})\n\n"
            f"Adicionar as {len(validos)} disciplina(s) válidas mesmo assim?",
            parent=self,
        ):
            return
        self.resultado = [it["disciplina"] for it in validos]
        self.destroy()


class TelaDisciplinas(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self._construir()
        self._atualizar_lista()

    def _construir(self):
        ttk.Label(self, text="Disciplinas monitoradas", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(self, text="O robô atira em todas as disciplinas ativas ao mesmo tempo.", foreground=cor("#666")).pack(anchor="w", pady=(0, 10))

        colunas = ("codigo", "turma", "departamento", "professor", "grupo", "prioridade", "ativa")
        self.tree = ttk.Treeview(self, columns=colunas, show="headings", height=10, selectmode="browse")
        for col, titulo, largura in [
            ("codigo", "Código", 100), ("turma", "Turma", 70), ("departamento", "Departamento", 100),
            ("professor", "Professor", 150), ("grupo", "Grupo", 90), ("prioridade", "Prioridade", 80), ("ativa", "Ativa?", 60),
        ]:
            self.tree.heading(col, text=titulo)
            self.tree.column(col, width=largura, anchor="center" if col != "professor" else "w")
        self.tree.pack(fill="both", expand=True, pady=(0, 10))
        self.tree.bind("<Double-1>", lambda _e: self._editar())

        botoes = ttk.Frame(self)
        botoes.pack(fill="x")
        ttk.Button(botoes, text="➕ Adicionar", command=self._adicionar).pack(side="left")
        ttk.Button(botoes, text="📋 Adicionar várias", command=self._adicionar_lote).pack(side="left", padx=(6, 0))
        ttk.Button(botoes, text="✏️ Editar", command=self._editar).pack(side="left", padx=6)
        ttk.Button(botoes, text="🗑️ Remover", command=self._remover).pack(side="left")
        ttk.Button(botoes, text="🔁 Ativar/Desativar", command=self._alternar_ativa).pack(side="left", padx=6)
        self.lbl_aplicado = ttk.Label(self, text="", foreground=cor("#1a7f37"))
        self.lbl_aplicado.pack(anchor="w", pady=(6, 0))

        # Sugestão 046: lista de departamentos atualizada pela página pública do SIGAA.
        deptos = ttk.Frame(self)
        deptos.pack(fill="x", pady=(8, 0))
        from app.core.departamentos import info_lista
        self.lbl_deptos = ttk.Label(deptos, text=info_lista()["texto"], foreground=cor("#57606a"))
        self.lbl_deptos.pack(side="left")
        ttk.Button(deptos, text="🔄 Atualizar lista de departamentos", command=self._atualizar_departamentos).pack(side="right")

    def recarregar(self):
        self._atualizar_lista()

    def _atualizar_departamentos(self):
        import threading
        from app.core.departamentos import atualizar_departamentos, info_lista
        self.lbl_deptos.config(text="Consultando a página pública do SIGAA…")

        def alvo():
            try:
                r = atualizar_departamentos()
                texto = f"{info_lista()['texto']} ({r['novos']} nova(s), {r['removidos']} removida(s))"
            except ValueError as e:
                texto = f"{info_lista()['texto']} — {e}"
            self.after(0, lambda: self.lbl_deptos.config(text=texto))

        threading.Thread(target=alvo, daemon=True).start()

    def _atualizar_lista(self):
        self.tree.delete(*self.tree.get_children())
        for i, d in enumerate(self.app.disciplinas):
            self.tree.insert("", "end", iid=str(i), values=(d.codigo, d.turma, d.departamento, d.professor, d.grupo or "—", d.prioridade, "Sim" if d.ativa else "Não"))

    def _indice_selecionado(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _adicionar(self):
        dlg = DialogoDisciplina(self)
        self.wait_window(dlg)
        if dlg.resultado:
            self.app.disciplinas.append(dlg.resultado)
            self._persistir(adicionar=[dlg.resultado])

    def _adicionar_lote(self):
        dlg = DialogoLote(self, self.app.disciplinas)
        self.wait_window(dlg)
        if dlg.resultado:
            self.app.disciplinas.extend(dlg.resultado)
            self._persistir(adicionar=dlg.resultado)

    def _editar(self):
        idx = self._indice_selecionado()
        if idx is None:
            return
        dlg = DialogoDisciplina(self, self.app.disciplinas[idx])
        self.wait_window(dlg)
        if dlg.resultado:
            # Bug real corrigido: o diálogo cria a disciplina com ativa=True, então
            # editar uma disciplina DESATIVADA a reativava silenciosamente (e ela
            # voltava a ser monitorada/matriculada). Preserva o estado anterior.
            dlg.resultado.ativa = self.app.disciplinas[idx].ativa
            antiga = self.app.disciplinas[idx]
            self.app.disciplinas[idx] = dlg.resultado
            self._persistir(adicionar=[dlg.resultado], remover=[antiga.chave()] if antiga.chave() != dlg.resultado.chave() else [])

    def _remover(self):
        idx = self._indice_selecionado()
        if idx is None:
            return
        d = self.app.disciplinas[idx]
        if messagebox.askyesno("Remover", f"Remover {d.codigo}-{d.turma} da lista?"):
            self.app.disciplinas.pop(idx)
            self._persistir(remover=[d.chave()])

    def _alternar_ativa(self):
        idx = self._indice_selecionado()
        if idx is None:
            return
        d = self.app.disciplinas[idx]
        d.ativa = not d.ativa
        self._persistir(adicionar=[d] if d.ativa else [], remover=[] if d.ativa else [d.chave()])

    def _persistir(self, adicionar=(), remover=()):
        salvar_disciplinas(self.app.disciplinas)
        self._atualizar_lista()
        # Sugestão 037: com o motor rodando, a mudança vale na hora (sem reiniciar).
        aplicar = getattr(self.app, "aplicar_disciplinas_na_execucao", None)
        if aplicar and (adicionar or remover) and aplicar(adicionar=adicionar, remover=remover):
            self.lbl_aplicado.config(text="✅ Mudança aplicada também à execução em andamento.")
