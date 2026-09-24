"""
Assistente de configuração inicial da interface gráfica (desde a 6.1.0).

Mesmas etapas e mesma regra da Interface Web (app/core/configuracao_inicial.py):
cada etapa é conferida antes de avançar, dá para voltar, "Configurar depois"
fecha sem salvar nada (e o assistente não volta a abrir sozinho), e só a
revisão final salva. Reabre em Config. Avançadas → "Refazer a configuração inicial".
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.core import configuracao_inicial as ci
from app.core.config import PRESETS_CARGA
from app.gui.responsive import aplicar_geometria_responsiva, tornar_rolavel
from app.gui.tema import cor


def primeira_execucao(settings: dict, disciplinas: list) -> bool:
    """Mostra o assistente enquanto ele não foi concluído nem dispensado e não há disciplinas."""
    return not settings.get("assistente_concluido") and not disciplinas


class AssistentePrimeiraExecucao(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Configuração inicial — SIGAA Sniper")
        aplicar_geometria_responsiva(self, largura_ideal=680, altura_ideal=620, largura_min=520, altura_min=460)
        self.protocol("WM_DELETE_WINDOW", self._dispensar)
        self.transient(parent)
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

        self.etapa = 0
        self.dados = {
            "credenciais": {"usuario": "", "senha": "", "cpf": "", "nascimento": ""},
            "disciplinas": [],
            "execucao": {"modo": app.settings.get("modo", "monitoramento"), "dry_run": True, "preset": "leve", "verificacao_previa": True},
            "notificacoes": {"windows_ativo": False, "webhook_ativo": False, "webhook_formato": "discord", "webhook_url": "",
                             "email_ativo": False, "email": {"servidor": "", "porta": 587, "seguranca": "starttls", "usuario": "",
                                                             "destinatario": "", "remetente": ""},
                             "email_senha": "", "lembrar_segredos": False},
            "paineis": {"carregar_ultima_execucao": False, "abrir_dashboard_ao_iniciar": True},
        }
        self.etapas = [self._boas_vindas, self._credenciais, self._disciplinas, self._execucao, self._notificacoes,
                       self._paineis, self._revisao]

        rodape = ttk.Frame(self, padding=(20, 10))
        rodape.pack(side="bottom", fill="x")
        ttk.Button(rodape, text="Configurar depois", command=self._dispensar).pack(side="left")
        self.btn_proximo = ttk.Button(rodape, text="Próximo ▶", command=self._proximo)
        self.btn_proximo.pack(side="right")
        self.btn_voltar = ttk.Button(rodape, text="◀ Voltar", command=self._voltar)
        self.btn_voltar.pack(side="right", padx=(0, 6))
        ttk.Separator(self, orient="horizontal").pack(side="bottom", fill="x")

        self.lbl_passos = ttk.Label(self, text="", foreground=cor("#57606a"), padding=(20, 10, 20, 0))
        self.lbl_passos.pack(side="top", anchor="w")
        self.lbl_erros = ttk.Label(self, text="", foreground=cor("#cf222e"), wraplength=620, justify="left", padding=(20, 4, 20, 0))
        self.lbl_erros.pack(side="top", anchor="w")
        self.area = ttk.Frame(self)
        self.area.pack(side="top", fill="both", expand=True)
        self._renderizar()

    # ── navegação ───────────────────────────────────────────────────────

    def _renderizar(self):
        for w in self.area.winfo_children():
            w.destroy()
        moldura = ttk.Frame(self.area, padding=(20, 8))
        moldura.pack(fill="both", expand=True)
        self.corpo = tornar_rolavel(moldura)
        nomes = [n for _, n in ci.ETAPAS]
        self.lbl_passos.config(text=f"Etapa {self.etapa + 1} de {len(nomes)} · "
                                    + " → ".join(f"[{n}]" if i == self.etapa else n for i, n in enumerate(nomes)))
        self.btn_voltar.config(state="normal" if self.etapa > 0 else "disabled")
        self.btn_proximo.config(text="✔ Concluir" if self.etapa == len(self.etapas) - 1 else "Próximo ▶")
        self.etapas[self.etapa]()

    def _mostrar_problemas(self, problemas, avisos=()):
        texto = "\n".join(f"• {p}" for p in problemas)
        if avisos:
            texto += ("\n" if texto else "") + "\n".join(f"ℹ {a}" for a in avisos)
        self.lbl_erros.config(text=texto, foreground=cor("#cf222e") if problemas else cor("#9a6700"))

    def _proximo(self):
        nome = ci.ETAPAS[self.etapa][0]
        if nome == "revisao":
            self._concluir()
            return
        if nome in ("credenciais", "execucao", "notificacoes"):
            r = ci.validar_etapa(nome, self.dados[nome], self.app.disciplinas)
            if r["problemas"]:
                self._mostrar_problemas(r["problemas"])
                return
            self._mostrar_problemas([], r["avisos"])
        else:
            self._mostrar_problemas([])
        self.etapa += 1
        self._renderizar()

    def _voltar(self):
        if self.etapa > 0:
            self.etapa -= 1
            self._mostrar_problemas([])
            self._renderizar()

    def _dispensar(self):
        self.app.settings = ci.dispensar(self.app.settings)
        self.destroy()

    def _concluir(self):
        settings, disciplinas, problemas = ci.aplicar(self.dados, self.app.settings, self.app.disciplinas, self.app.sessao)
        if problemas:
            self._mostrar_problemas(problemas)
            return
        self.app.settings, self.app.disciplinas = settings, disciplinas
        self.app.recarregar_telas()
        self.destroy()
        messagebox.showinfo("Configuração inicial", "Configuração salva. Você pode mudar tudo depois nas abas.")

    # ── ajudantes de formulário ─────────────────────────────────────────

    def _titulo(self, texto, explicacao=""):
        ttk.Label(self.corpo, text=texto, font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 6))
        if explicacao:
            ttk.Label(self.corpo, text=explicacao, foreground=cor("#57606a"), wraplength=600, justify="left").pack(anchor="w", pady=(0, 8))

    def _campo(self, rotulo, obj, chave, oculto=False):
        ttk.Label(self.corpo, text=rotulo).pack(anchor="w", pady=(4, 0))
        var = tk.StringVar(value=str(obj.get(chave, "")))
        var.trace_add("write", lambda *_: obj.__setitem__(chave, var.get()))
        ttk.Entry(self.corpo, textvariable=var, width=48, show="•" if oculto else "").pack(anchor="w")
        return var

    def _caixa(self, rotulo, obj, chave, rerender=False):
        var = tk.BooleanVar(value=bool(obj.get(chave)))

        def mudar():
            obj[chave] = var.get()
            if rerender:
                self._renderizar()

        ttk.Checkbutton(self.corpo, text=rotulo, variable=var, command=mudar).pack(anchor="w", pady=2)
        return var

    def _ajuda(self, parent, titulo, texto):
        ttk.Button(parent, text="Como funciona?", command=lambda: messagebox.showinfo(titulo, texto, parent=self)).pack(side="left", padx=(6, 0))

    # ── etapas ──────────────────────────────────────────────────────────

    def _boas_vindas(self):
        self._titulo("Bem-vindo ao SIGAA Sniper",
                     "Vamos configurar o essencial em 6 etapas curtas. Cada etapa é conferida antes de avançar e nada é salvo "
                     "até você revisar e concluir.\n\n\"Configurar depois\" fecha o assistente; ele pode ser reaberto em "
                     "Config. Avançadas → Refazer a configuração inicial.")

    def _credenciais(self):
        cr = self.dados["credenciais"]
        self._titulo("1. Credenciais do SIGAA", "Ficam só na memória desta execução — nunca em disco. Pode deixar em branco "
                                               "e preencher depois na aba Credenciais.")
        self._campo("Matrícula (usuário do SIGAA):", cr, "usuario")
        self._campo("Senha:", cr, "senha", oculto=True)
        self._campo("CPF — com ou sem pontos (ex: 123.456.789-09):", cr, "cpf")
        self._campo("Data de nascimento — DD/MM/AAAA (ex: 01/02/2003):", cr, "nascimento")

    def _disciplinas(self):
        from app.core.textos import TEXTO_AJUDA_GRUPO, TEXTO_AJUDA_PRIORIDADE
        from app.gui.escolher_departamento import escolher_departamento
        self._titulo("2. Disciplinas", f"{len(self.app.disciplinas)} já cadastrada(s). Adicione quantas quiser (ou nenhuma agora).")
        nova = {"codigo": "", "turma": "", "departamento": "", "grupo": "", "prioridade": "normal"}
        self._campo("Código da disciplina (ex: FGA0211):", nova, "codigo")
        self._campo("Turma — só números (ex: 01):", nova, "turma")
        ttk.Label(self.corpo, text="Código do departamento (ex: 673):").pack(anchor="w", pady=(4, 0))
        linha = ttk.Frame(self.corpo)
        linha.pack(anchor="w")
        var_depto = tk.StringVar()
        var_depto.trace_add("write", lambda *_: nova.__setitem__("departamento", var_depto.get()))
        ttk.Entry(linha, textvariable=var_depto, width=12).pack(side="left")
        lbl_depto = ttk.Label(self.corpo, text="", foreground=cor("#57606a"), wraplength=600)

        def ver():
            r = escolher_departamento(self)
            if r:
                var_depto.set(str(r[0]))
                lbl_depto.config(text=f"✔ {r[0]} — {r[1]}")

        ttk.Button(linha, text="📋 Ver departamentos", command=ver).pack(side="left", padx=(6, 0))
        lbl_depto.pack(anchor="w")
        linha_g = ttk.Frame(self.corpo)
        linha_g.pack(anchor="w", pady=(6, 0))
        ttk.Label(linha_g, text="Grupo de alternativas (opcional):").pack(side="left")
        self._ajuda(linha_g, "Grupo de alternativas", TEXTO_AJUDA_GRUPO)
        self._campo_simples(nova, "grupo")
        linha_p = ttk.Frame(self.corpo)
        linha_p.pack(anchor="w", pady=(6, 0))
        ttk.Label(linha_p, text="Prioridade:").pack(side="left")
        var_p = tk.StringVar(value="normal")
        var_p.trace_add("write", lambda *_: nova.__setitem__("prioridade", var_p.get()))
        ttk.Combobox(linha_p, textvariable=var_p, values=["alta", "normal", "baixa"], state="readonly", width=10).pack(side="left", padx=(6, 0))
        self._ajuda(linha_p, "Prioridade", TEXTO_AJUDA_PRIORIDADE)
        ttk.Label(self.corpo, text="Mesmo grupo = alternativas (garantida uma, as outras saem da busca). Prioridade só define a ordem.",
                  foreground=cor("#57606a"), wraplength=600).pack(anchor="w", pady=(4, 0))

        def adicionar():
            r = ci.validar_etapa("disciplina", nova, self.app.disciplinas + [ci.disciplina_de_dados(d)[0] for d in self.dados["disciplinas"]])
            self._mostrar_problemas(r["problemas"], r["avisos"])
            if not r["problemas"]:
                self.dados["disciplinas"].append({**nova, "codigo": nova["codigo"].strip().upper(), "turma": nova["turma"].strip()})
                self._renderizar()
                self._mostrar_problemas([], r["avisos"])

        ttk.Button(self.corpo, text="➕ Adicionar esta disciplina", command=adicionar).pack(anchor="w", pady=(8, 4))
        for i, d in enumerate(self.dados["disciplinas"]):
            item = ttk.Frame(self.corpo)
            item.pack(anchor="w", fill="x")
            ttk.Label(item, text=f"• {d['codigo']}-{d['turma']} · depto {d['departamento']}"
                                 + (f" · grupo {d['grupo']}" if d["grupo"] else "") + f" · {d['prioridade']}").pack(side="left")
            ttk.Button(item, text="Remover", command=lambda i=i: (self.dados["disciplinas"].pop(i), self._renderizar())).pack(side="left", padx=6)

    def _campo_simples(self, obj, chave):
        var = tk.StringVar(value=str(obj.get(chave, "")))
        var.trace_add("write", lambda *_: obj.__setitem__(chave, var.get()))
        ttk.Entry(self.corpo, textvariable=var, width=30).pack(anchor="w")

    def _execucao(self):
        ex = self.dados["execucao"]
        self._titulo("3. Execução", "Pode mudar tudo depois na aba Execução e em Config. Avançadas.")
        var_modo = tk.StringVar(value=ex["modo"])

        def mudar_modo():
            ex["modo"] = var_modo.get()
            self._renderizar()

        ttk.Radiobutton(self.corpo, text="👀 Somente monitoramento — avisa quando achar vaga, nunca matricula sozinho",
                        variable=var_modo, value="monitoramento", command=mudar_modo).pack(anchor="w")
        ttk.Radiobutton(self.corpo, text="🎯 Matrícula automática — tenta se matricular assim que achar vaga",
                        variable=var_modo, value="matricula", command=mudar_modo).pack(anchor="w")
        if ex["modo"] == "matricula":
            self._caixa("DRY RUN (recomendado para começar): simula tudo, mas não confirma de verdade", ex, "dry_run", rerender=True)
            if not ex["dry_run"]:
                ttk.Label(self.corpo, text="⚠️ Sem DRY RUN, ao achar vaga o programa confirma a matrícula de verdade.",
                          foreground=cor("#cf222e")).pack(anchor="w")
        ttk.Label(self.corpo, text="Perfil de carga (quanto o programa consulta o SIGAA):").pack(anchor="w", pady=(8, 0))
        rotulos = {k: f"{p['rotulo']} — {p['num_workers']} workers, {p['intervalo_busca']}s" for k, p in PRESETS_CARGA.items()}
        var_p = tk.StringVar(value=rotulos[ex["preset"]])
        var_p.trace_add("write", lambda *_: ex.__setitem__("preset", next(k for k, v in rotulos.items() if v == var_p.get())))
        ttk.Combobox(self.corpo, textvariable=var_p, values=list(rotulos.values()), state="readonly", width=46).pack(anchor="w")
        self._caixa("Verificar login e disciplinas antes de começar (recomendado)", ex, "verificacao_previa")

    def _notificacoes(self):
        from app.core.textos import TEXTO_AJUDA_EMAIL, TEXTO_AJUDA_WEBHOOK
        n = self.dados["notificacoes"]
        self._titulo("4. Notificações (opcional)", "O programa funciona sem nenhuma. Telegram, ntfy e alarme ficam na aba Notificações.")
        self._caixa("🪟 Aviso na área de notificações do Windows (não precisa configurar nada)", n, "windows_ativo")
        linha = ttk.Frame(self.corpo)
        linha.pack(anchor="w", pady=(6, 0))
        var_w = tk.BooleanVar(value=n["webhook_ativo"])
        ttk.Checkbutton(linha, text="🔗 Webhook (Discord, Slack…)", variable=var_w,
                        command=lambda: (n.__setitem__("webhook_ativo", var_w.get()), self._renderizar())).pack(side="left")
        self._ajuda(linha, "Webhook", TEXTO_AJUDA_WEBHOOK)
        if n["webhook_ativo"]:
            ttk.Label(self.corpo, text="Formato:").pack(anchor="w")
            var_f = tk.StringVar(value=n["webhook_formato"])
            var_f.trace_add("write", lambda *_: n.__setitem__("webhook_formato", var_f.get()))
            ttk.Combobox(self.corpo, textvariable=var_f, values=["discord", "slack", "json"], state="readonly", width=12).pack(anchor="w")
            self._campo("URL do webhook (https://…):", n, "webhook_url", oculto=True)
        linha = ttk.Frame(self.corpo)
        linha.pack(anchor="w", pady=(6, 0))
        var_e = tk.BooleanVar(value=n["email_ativo"])
        ttk.Checkbutton(linha, text="✉️ E-mail (SMTP)", variable=var_e,
                        command=lambda: (n.__setitem__("email_ativo", var_e.get()), self._renderizar())).pack(side="left")
        self._ajuda(linha, "E-mail", TEXTO_AJUDA_EMAIL)
        if n["email_ativo"]:
            e = n["email"]
            self._campo("Servidor SMTP (ex: smtp.gmail.com):", e, "servidor")
            ttk.Label(self.corpo, text="Segurança:").pack(anchor="w")
            var_s = tk.StringVar(value=e["seguranca"])

            def mudar_seg(*_):
                e["seguranca"] = var_s.get()
                e["porta"] = 465 if var_s.get() == "ssl" else 587

            var_s.trace_add("write", mudar_seg)
            ttk.Combobox(self.corpo, textvariable=var_s, values=["starttls", "ssl"], state="readonly", width=12).pack(anchor="w")
            self._campo("Usuário (seu e-mail):", e, "usuario")
            self._campo("Senha (Gmail/Outlook: senha de app):", n, "email_senha", oculto=True)
            self._campo("Enviar para:", e, "destinatario")
            self._campo("Remetente (opcional):", e, "remetente")
        if n["webhook_ativo"] or n["email_ativo"]:
            self._caixa("Guardar a URL/senha neste computador (cifradas com a sua conta do Windows)", n, "lembrar_segredos")

    def _paineis(self):
        p = self.dados["paineis"]
        self._titulo("5. Painéis")
        self._caixa("Carregar os dados da última execução ao abrir o programa", p, "carregar_ultima_execucao")
        ttk.Label(self.corpo, foreground=cor("#57606a"), wraplength=600, justify="left",
                  text="Desligado (recomendado): Dashboard e Logs começam vazios até você iniciar uma execução; as anteriores "
                       "ficam na aba Histórico. Ligado: mostram a última execução marcada como recuperada — o tempo não corre "
                       "e nada é iniciado.").pack(anchor="w", pady=(0, 8))
        self._caixa("Abrir o Dashboard automaticamente ao iniciar uma execução", p, "abrir_dashboard_ao_iniciar")

    def _revisao(self):
        self._titulo("6. Revisão", "Confira. \"◀ Voltar\" corrige qualquer etapa; \"✔ Concluir\" confere tudo de novo e salva.")
        for linha in ci.resumo(self.dados):
            ttk.Label(self.corpo, text=linha, wraplength=600, justify="left").pack(anchor="w", pady=1)
