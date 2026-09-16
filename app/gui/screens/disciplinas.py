"""Tela de Disciplinas — seção 25 do pedido. Persistido em config/disciplinas.json (não é sensível)."""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk, messagebox

from app.core.config import Disciplina, salvar_disciplinas
from app.core.departamentos import buscar_departamentos, codigo_conhecido, nome_do_departamento

TEXTO_AJUDA_DEPARTAMENTO = (
    "Como encontrar o código do departamento\n\n"
    "1. Acesse https://sigaa.unb.br/sigaa/public/turmas/listar.jsf\n"
    "2. Abra as ferramentas de desenvolvedor do navegador (tecla F12).\n"
    "3. Inspecione o campo de seleção \"Unidade\" (formTurma:inputDepto).\n"
    "4. Encontre a opção com o nome do departamento desejado — o atributo\n"
    "   value=\"...\" dela é o código atual usado pelo SIGAA.\n\n"
    "Exemplo do que você vai ver no HTML:\n"
    '  <option value="673">CAMPUS UNB GAMA: FACULDADE DE CIÊNCIAS E\n'
    "   TECNOLOGIAS EM ENGENHARIA - BRASÍLIA</option>\n\n"
    "Aqui, 673 é o código daquele departamento NAQUELE MOMENTO."
)


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

        d = disciplina or Disciplina(codigo="", turma="", departamento=0)

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        aviso = ttk.Frame(frame, padding=8, relief="solid", borderwidth=1)
        aviso.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(
            aviso, foreground="#9a6700", wraplength=380, justify="left",
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

        ttk.Label(frame, text="Departamento (digite para buscar):").grid(row=3, column=0, sticky="w", pady=4)
        valor_inicial = f"{d.departamento} — {nome_do_departamento(d.departamento)}" if d.departamento else ""
        self.var_depto_busca = tk.StringVar(value=valor_inicial)
        self.combo_depto = ttk.Combobox(frame, textvariable=self.var_depto_busca, width=32)
        self.combo_depto.grid(row=3, column=1, pady=4, padx=(8, 0))
        self.combo_depto.bind("<KeyRelease>", self._atualizar_busca_departamento)

        ttk.Button(frame, text="Como encontrar?", command=self._mostrar_ajuda_departamento).grid(row=4, column=1, sticky="w", padx=(8, 0), pady=(0, 6))

        self.lbl_aviso_depto = ttk.Label(frame, text="", foreground="#9a6700", wraplength=380, justify="left")
        self.lbl_aviso_depto.grid(row=5, column=0, columnspan=2, sticky="w")

        ttk.Label(frame, text="Professor (opcional):").grid(row=6, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.var_professor, width=34).grid(row=6, column=1, pady=4, padx=(8, 0))

        botoes = ttk.Frame(frame)
        botoes.grid(row=7, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(botoes, text="Salvar", command=self._salvar).pack(side="right")

        self._atualizar_busca_departamento()  # só depois de TODOS os widgets acima existirem

    def _atualizar_busca_departamento(self, _event=None):
        termo = self.var_depto_busca.get()
        # Se já está no formato "codigo — nome" (veio de uma seleção), não refiltra
        if re.match(r"^\d+\s+—\s+", termo):
            codigo = int(termo.split("—", 1)[0].strip())
            if not codigo_conhecido(codigo):
                self.lbl_aviso_depto.config(text=f"⚠️ Código {codigo} não está na lista de referência conhecida (pode ser novo, ou a lista pode estar desatualizada).")
            else:
                self.lbl_aviso_depto.config(text="")
            return
        encontrados = buscar_departamentos(termo)[:25]
        self.combo_depto["values"] = [f"{d.codigo} — {d.nome}" for d in encontrados]
        self.lbl_aviso_depto.config(text="" if termo.strip().isdigit() or not termo.strip() else "")

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
        codigo = self.var_codigo.get().strip().upper()
        turma = self.var_turma.get().strip()
        depto = self._extrair_codigo_departamento()

        if not codigo or not turma or not depto:
            messagebox.showwarning(
                "Dados inválidos",
                "Preencha código da disciplina, turma, e selecione (ou digite) um departamento válido.",
                parent=self,
            )
            return

        if not codigo_conhecido(depto):
            if not messagebox.askyesno(
                "Código não reconhecido",
                f"O código de departamento {depto} não está na lista de referência conhecida.\n\n"
                "Isso pode ser normal (departamento novo, ou a lista está desatualizada) — "
                "mas confira com o botão \"Como encontrar?\" se não tiver certeza.\n\n"
                "Salvar mesmo assim?",
                parent=self,
            ):
                return

        self.resultado = Disciplina(codigo=codigo, turma=turma, departamento=depto, professor=self.var_professor.get().strip())
        self.destroy()


class TelaDisciplinas(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self._construir()
        self._atualizar_lista()

    def _construir(self):
        ttk.Label(self, text="Disciplinas monitoradas", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(self, text="O robô atira em todas as disciplinas ativas ao mesmo tempo.", foreground="#666").pack(anchor="w", pady=(0, 10))

        colunas = ("codigo", "turma", "departamento", "professor", "ativa")
        self.tree = ttk.Treeview(self, columns=colunas, show="headings", height=10, selectmode="browse")
        for col, titulo, largura in [
            ("codigo", "Código", 100), ("turma", "Turma", 70), ("departamento", "Departamento", 100),
            ("professor", "Professor", 160), ("ativa", "Ativa?", 70),
        ]:
            self.tree.heading(col, text=titulo)
            self.tree.column(col, width=largura, anchor="center" if col != "professor" else "w")
        self.tree.pack(fill="both", expand=True, pady=(0, 10))
        self.tree.bind("<Double-1>", lambda _e: self._editar())

        botoes = ttk.Frame(self)
        botoes.pack(fill="x")
        ttk.Button(botoes, text="➕ Adicionar", command=self._adicionar).pack(side="left")
        ttk.Button(botoes, text="✏️ Editar", command=self._editar).pack(side="left", padx=6)
        ttk.Button(botoes, text="🗑️ Remover", command=self._remover).pack(side="left")
        ttk.Button(botoes, text="🔁 Ativar/Desativar", command=self._alternar_ativa).pack(side="left", padx=6)

    def _atualizar_lista(self):
        self.tree.delete(*self.tree.get_children())
        for i, d in enumerate(self.app.disciplinas):
            self.tree.insert("", "end", iid=str(i), values=(d.codigo, d.turma, d.departamento, d.professor, "Sim" if d.ativa else "Não"))

    def _indice_selecionado(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _adicionar(self):
        dlg = DialogoDisciplina(self)
        self.wait_window(dlg)
        if dlg.resultado:
            self.app.disciplinas.append(dlg.resultado)
            self._persistir()

    def _editar(self):
        idx = self._indice_selecionado()
        if idx is None:
            return
        dlg = DialogoDisciplina(self, self.app.disciplinas[idx])
        self.wait_window(dlg)
        if dlg.resultado:
            self.app.disciplinas[idx] = dlg.resultado
            self._persistir()

    def _remover(self):
        idx = self._indice_selecionado()
        if idx is None:
            return
        d = self.app.disciplinas[idx]
        if messagebox.askyesno("Remover", f"Remover {d.codigo}-{d.turma} da lista?"):
            self.app.disciplinas.pop(idx)
            self._persistir()

    def _alternar_ativa(self):
        idx = self._indice_selecionado()
        if idx is None:
            return
        self.app.disciplinas[idx].ativa = not self.app.disciplinas[idx].ativa
        self._persistir()

    def _persistir(self):
        salvar_disciplinas(self.app.disciplinas)
        self._atualizar_lista()
