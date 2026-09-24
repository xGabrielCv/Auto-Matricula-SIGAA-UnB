"""
Tela de Notificações — seções 13-17 do pedido.

Telegram/ntfy/alarme são 100% opcionais: o app funciona perfeitamente com
tudo desligado. Os segredos (token, chat_id, tópico) só são salvos em disco
se o usuário marcar explicitamente a caixa de "lembrar neste computador".
"""
from __future__ import annotations

import asyncio
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from app.core.config import (
    apagar_segredos_notificacao, carregar_segredos_notificacao,
    existe_segredos_notificacao_salvos, salvar_segredos_notificacao,
)
from app.core.cofre import descricao_armazenamento
from app.core.textos import TEXTO_AJUDA_ALARME, TEXTO_AJUDA_NTFY, TEXTO_AJUDA_TELEGRAM
from app.gui.responsive import tornar_rolavel
from app.notifications.alarm import testar_alarme
from app.notifications.ntfy import testar_ntfy
from app.notifications.telegram import testar_telegram
from app.gui.tema import cor


def _rodar_async_em_thread(coro_factory, ao_terminar):
    def alvo():
        try:
            resultado = asyncio.run(coro_factory())
            ao_terminar(resultado, None)
        except Exception as e:
            ao_terminar(None, e)
    threading.Thread(target=alvo, daemon=True).start()


class TelaNotificacoes(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self._construir()

    def _construir(self):
        ttk.Label(self, text="Notificações (opcional)", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(self, text="O programa funciona normalmente com tudo desligado aqui.", foreground=cor("#666")).pack(anchor="w", pady=(0, 10))

        # Corrige um problema real de usabilidade: com muitos blocos (Telegram,
        # ntfy, alarme, eventos, persistência) empilhados, o conteúdo podia
        # ultrapassar a altura da janela e o botão "Testar todos" ficar
        # inacessível. Agora tudo — inclusive o botão e o status — fica dentro
        # de uma área rolável (ver app/gui/responsive.py).
        canvas_frame = tornar_rolavel(self)

        self._bloco_telegram(canvas_frame)
        self._bloco_ntfy(canvas_frame)
        self._bloco_alarme(canvas_frame)
        self._bloco_novos_canais(canvas_frame)
        self._bloco_eventos(canvas_frame)
        self._bloco_persistencia(canvas_frame)

        ttk.Button(canvas_frame, text="🔔 Testar todos os canais habilitados", command=self._testar_todos).pack(anchor="w", pady=(10, 0))
        self.lbl_status = ttk.Label(canvas_frame, text="")
        self.lbl_status.pack(anchor="w", pady=(6, 0))

    def _bloco_telegram(self, parent):
        cfg = self.app.settings["notificacoes"]
        notif = self.app.sessao.notificacao

        frame = ttk.LabelFrame(parent, text="Telegram", padding=10)
        frame.pack(fill="x", pady=6)

        self.var_telegram_ativo = tk.BooleanVar(value=cfg["telegram_ativo"])
        ttk.Checkbutton(frame, text="Ativar notificações por Telegram", variable=self.var_telegram_ativo).grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Label(frame, text="Bot Token:").grid(row=1, column=0, sticky="w", pady=4)
        self.var_tg_token = tk.StringVar(value=notif.telegram_token)
        ttk.Entry(frame, textvariable=self.var_tg_token, width=40, show="•").grid(row=1, column=1, sticky="ew")

        ttk.Label(frame, text="Chat ID:").grid(row=2, column=0, sticky="w", pady=4)
        self.var_tg_chat = tk.StringVar(value=notif.telegram_chat_id)
        ttk.Entry(frame, textvariable=self.var_tg_chat, width=40).grid(row=2, column=1, sticky="ew")

        botoes = ttk.Frame(frame)
        botoes.grid(row=1, column=2, rowspan=2, padx=(10, 0))
        ttk.Button(botoes, text="Como configurar?", command=lambda: self._mostrar_ajuda("Telegram", TEXTO_AJUDA_TELEGRAM)).pack(fill="x", pady=2)
        ttk.Button(botoes, text="Enviar teste", command=self._testar_telegram).pack(fill="x", pady=2)
        frame.columnconfigure(1, weight=1)

    def _bloco_ntfy(self, parent):
        cfg = self.app.settings["notificacoes"]
        notif = self.app.sessao.notificacao

        frame = ttk.LabelFrame(parent, text="ntfy", padding=10)
        frame.pack(fill="x", pady=6)

        self.var_ntfy_ativo = tk.BooleanVar(value=cfg["ntfy_ativo"])
        ttk.Checkbutton(frame, text="Ativar notificações por ntfy", variable=self.var_ntfy_ativo).grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Label(frame, text="Tópico:").grid(row=1, column=0, sticky="w", pady=4)
        self.var_ntfy_topic = tk.StringVar(value=notif.ntfy_topic)
        ttk.Entry(frame, textvariable=self.var_ntfy_topic, width=40).grid(row=1, column=1, sticky="ew")

        ttk.Label(frame, text="Servidor:").grid(row=2, column=0, sticky="w", pady=4)
        self.var_ntfy_servidor = tk.StringVar(value=notif.ntfy_servidor)
        ttk.Entry(frame, textvariable=self.var_ntfy_servidor, width=40).grid(row=2, column=1, sticky="ew")

        botoes = ttk.Frame(frame)
        botoes.grid(row=1, column=2, rowspan=2, padx=(10, 0))
        ttk.Button(botoes, text="Como configurar?", command=lambda: self._mostrar_ajuda("ntfy", TEXTO_AJUDA_NTFY)).pack(fill="x", pady=2)
        ttk.Button(botoes, text="Enviar teste", command=self._testar_ntfy).pack(fill="x", pady=2)
        frame.columnconfigure(1, weight=1)

    def _bloco_alarme(self, parent):
        cfg = self.app.settings["notificacoes"]
        frame = ttk.LabelFrame(parent, text="Alarme sonoro local", padding=10)
        frame.pack(fill="x", pady=6)

        self.var_alarme_ativo = tk.BooleanVar(value=cfg["alarme_ativo"])
        ttk.Checkbutton(frame, text="Ativar alarme sonoro ao encontrar vaga", variable=self.var_alarme_ativo).grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Label(frame, text="Repetições:").grid(row=1, column=0, sticky="w", pady=4)
        self.var_alarme_rep = tk.IntVar(value=cfg["alarme"]["repeticoes"])
        ttk.Spinbox(frame, from_=1, to=20, textvariable=self.var_alarme_rep, width=6).grid(row=1, column=1, sticky="w")

        ttk.Label(frame, text="Duração máx. (segundos):").grid(row=2, column=0, sticky="w", pady=4)
        self.var_alarme_dur = tk.IntVar(value=cfg["alarme"]["duracao_seg"])
        ttk.Spinbox(frame, from_=1, to=120, textvariable=self.var_alarme_dur, width=6).grid(row=2, column=1, sticky="w")

        botoes = ttk.Frame(frame)
        botoes.grid(row=1, column=2, rowspan=2, padx=(10, 0))
        ttk.Button(botoes, text="Como funciona?", command=lambda: self._mostrar_ajuda("Alarme local", TEXTO_AJUDA_ALARME)).pack(fill="x", pady=2)
        ttk.Button(botoes, text="Testar alarme", command=self._testar_alarme).pack(fill="x", pady=2)

    def _bloco_novos_canais(self, parent):
        """Fase 6: notificação do Windows (080), webhook (081) e e-mail (082)."""
        from app.notifications import windows as windows_notif
        cfg = self.app.settings["notificacoes"]
        notif = self.app.sessao.notificacao

        win = ttk.LabelFrame(parent, text="Notificação do Windows", padding=10)
        win.pack(fill="x", pady=6)
        self.var_windows_ativo = tk.BooleanVar(value=cfg.get("windows_ativo", False))
        ttk.Checkbutton(win, text="Mostrar um aviso na área de notificações do Windows (não precisa configurar nada)",
                        variable=self.var_windows_ativo,
                        state="normal" if windows_notif.disponivel() else "disabled").pack(side="left")
        ttk.Button(win, text="Enviar teste", command=lambda: self._testar_canal("Windows", windows_notif.testar_windows)).pack(side="right")

        wh = ttk.LabelFrame(parent, text="Webhook (Discord, Slack…)", padding=10)
        wh.pack(fill="x", pady=6)
        self.var_webhook_ativo = tk.BooleanVar(value=cfg.get("webhook_ativo", False))
        ttk.Checkbutton(wh, text="Enviar para um webhook", variable=self.var_webhook_ativo).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(wh, text="Formato:").grid(row=1, column=0, sticky="w", pady=4)
        self.var_webhook_formato = tk.StringVar(value=cfg.get("webhook_formato", "discord"))
        ttk.Combobox(wh, textvariable=self.var_webhook_formato, values=["discord", "slack", "json"], state="readonly",
                     width=12).grid(row=1, column=1, sticky="w")
        ttk.Label(wh, text="URL (segredo):").grid(row=2, column=0, sticky="w", pady=4)
        self.var_webhook_url = tk.StringVar(value=notif.webhook_url)
        ttk.Entry(wh, textvariable=self.var_webhook_url, width=40, show="•").grid(row=2, column=1, sticky="ew")
        ttk.Button(wh, text="Enviar teste", command=self._testar_webhook).grid(row=2, column=2, padx=(10, 0))
        from app.core.textos import TEXTO_AJUDA_EMAIL, TEXTO_AJUDA_WEBHOOK
        ttk.Button(wh, text="Como configurar?", command=lambda: self._mostrar_ajuda("Webhook", TEXTO_AJUDA_WEBHOOK)).grid(row=1, column=2, padx=(10, 0))
        wh.columnconfigure(1, weight=1)

        em = ttk.LabelFrame(parent, text="E-mail (SMTP)", padding=10)
        em.pack(fill="x", pady=6)
        email = {**{"servidor": "", "porta": 587, "usuario": "", "destinatario": "", "seguranca": "starttls"}, **(cfg.get("email") or {})}
        self.var_email_ativo = tk.BooleanVar(value=cfg.get("email_ativo", False))
        ttk.Checkbutton(em, text="Enviar por e-mail", variable=self.var_email_ativo).grid(row=0, column=0, columnspan=3, sticky="w")
        self.vars_email = {}
        email.setdefault("remetente", "")
        ttk.Button(em, text="Como configurar?", command=lambda: self._mostrar_ajuda("E-mail", TEXTO_AJUDA_EMAIL)).grid(row=0, column=2, padx=(10, 0))
        for i, (chave, rotulo) in enumerate((("servidor", "Servidor SMTP:"), ("porta", "Porta:"), ("usuario", "Usuário (seu e-mail):"),
                                             ("destinatario", "Enviar para:"), ("remetente", "Remetente (opcional):")), start=1):
            ttk.Label(em, text=rotulo).grid(row=i, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=str(email[chave]))
            self.vars_email[chave] = var
            ttk.Entry(em, textvariable=var, width=40).grid(row=i, column=1, sticky="ew")
        ttk.Label(em, text="Segurança:").grid(row=6, column=0, sticky="w", pady=2)
        self.var_email_seguranca = tk.StringVar(value=email["seguranca"])
        ttk.Combobox(em, textvariable=self.var_email_seguranca, values=["starttls", "ssl"], state="readonly", width=12).grid(row=6, column=1, sticky="w")
        ttk.Label(em, text="Senha (segredo):").grid(row=7, column=0, sticky="w", pady=2)
        self.var_email_senha = tk.StringVar(value=notif.email_senha)
        ttk.Entry(em, textvariable=self.var_email_senha, width=40, show="•").grid(row=7, column=1, sticky="ew")
        ttk.Button(em, text="Enviar teste", command=self._testar_email).grid(row=7, column=2, padx=(10, 0))
        em.columnconfigure(1, weight=1)

    def _email_cfg(self) -> dict:
        try:
            porta = int(self.vars_email["porta"].get())
        except ValueError:
            porta = 587
        return {"servidor": self.vars_email["servidor"].get().strip(), "porta": porta,
                "usuario": self.vars_email["usuario"].get().strip(), "destinatario": self.vars_email["destinatario"].get().strip(),
                "remetente": self.vars_email["remetente"].get().strip(),
                "seguranca": "ssl" if self.var_email_seguranca.get() == "ssl" else "starttls"}

    def _testar_canal(self, nome, fabrica):
        self.lbl_status.config(text=f"Testando {nome}...")

        async def rodar():
            await fabrica()
            return f"{nome}: OK"

        _rodar_async_em_thread(rodar, self._resultado_teste)

    def _testar_webhook(self):
        from app.notifications.webhook import testar_webhook
        url, formato = self.var_webhook_url.get().strip(), self.var_webhook_formato.get()
        if not url.startswith("https://"):
            messagebox.showwarning("Webhook", "Preencha a URL do webhook (https://…) antes de testar.")
            return
        self._testar_canal("Webhook", lambda: testar_webhook(url, formato))

    def _testar_email(self):
        from app.core.validadores import problemas_email_cfg
        from app.notifications.email import testar_email
        cfg, senha = self._email_cfg(), self.var_email_senha.get()
        problemas = problemas_email_cfg(cfg, senha)
        if problemas:
            messagebox.showwarning("E-mail", "Revise antes de testar:\n\n" + "\n".join(f"• {p}" for p in problemas))
            return
        self._testar_canal("E-mail", lambda: testar_email(cfg, senha))

    def _bloco_eventos(self, parent):
        """Seção 41: quais eventos disparam notificação — não obriga o usuário a receber tudo."""
        cfg = self.app.settings["notificacoes"]["eventos"]
        frame = ttk.LabelFrame(parent, text="Quais eventos notificar", padding=10)
        frame.pack(fill="x", pady=6)

        from app.core.textos import ROTULOS_EVENTOS_NOTIFICACAO
        self.vars_eventos = {}
        for chave, rotulo in ROTULOS_EVENTOS_NOTIFICACAO.items():
            var = tk.BooleanVar(value=cfg.get(chave, False))
            self.vars_eventos[chave] = var
            ttk.Checkbutton(frame, text=rotulo, variable=var).pack(anchor="w")
        linha = ttk.Frame(frame)
        linha.pack(anchor="w", pady=(6, 0))
        ttk.Label(linha, text="Resumo periódico a cada (horas):").pack(side="left")
        self.var_resumo_horas = tk.StringVar(value=str(self.app.settings["notificacoes"].get("resumo_intervalo_horas", 6)))
        ttk.Spinbox(linha, from_=0.5, to=48, increment=0.5, textvariable=self.var_resumo_horas, width=6).pack(side="left", padx=6)

    def _bloco_persistencia(self, parent):
        frame = ttk.LabelFrame(parent, text="Salvar dados de notificação neste computador", padding=10)
        frame.pack(fill="x", pady=6)
        ttk.Label(
            frame, wraplength=560, justify="left", foreground=cor("#9a6700"),
            text=(
                "⚠️ Por padrão, os segredos de notificação (token do Telegram, tópico do ntfy, URL do webhook, "
                "senha do e-mail) também são só de memória, como as credenciais do SIGAA. Se marcar a opção abaixo, "
                f"eles serão guardados em config/notificacoes.secrets.json — {descricao_armazenamento()}."
            ),
        ).pack(anchor="w")

        self.var_lembrar = tk.BooleanVar(value=existe_segredos_notificacao_salvos())
        ttk.Checkbutton(frame, text="Salvar neste computador", variable=self.var_lembrar, command=self._alternar_persistencia).pack(anchor="w", pady=(6, 0))

        ttk.Button(frame, text="💾 Salvar configuração de notificações", command=self._salvar_config).pack(anchor="w", pady=(8, 0))

    def recarregar(self):
        cfg = self.app.settings["notificacoes"]
        notif = self.app.sessao.notificacao
        self.var_telegram_ativo.set(cfg["telegram_ativo"])
        self.var_ntfy_ativo.set(cfg["ntfy_ativo"])
        self.var_alarme_ativo.set(cfg["alarme_ativo"])
        self.var_alarme_rep.set(cfg["alarme"]["repeticoes"])
        self.var_alarme_dur.set(cfg["alarme"]["duracao_seg"])
        for chave, var in self.vars_eventos.items():
            var.set(cfg["eventos"].get(chave, False))
        self.var_resumo_horas.set(str(cfg.get("resumo_intervalo_horas", 6)))
        self.var_windows_ativo.set(cfg.get("windows_ativo", False))
        self.var_webhook_ativo.set(cfg.get("webhook_ativo", False))
        self.var_webhook_formato.set(cfg.get("webhook_formato", "discord"))
        self.var_email_ativo.set(cfg.get("email_ativo", False))
        for chave, var in self.vars_email.items():
            var.set(str((cfg.get("email") or {}).get(chave, "")))
        self.var_email_seguranca.set((cfg.get("email") or {}).get("seguranca", "starttls"))
        self.var_webhook_url.set(notif.webhook_url)
        self.var_email_senha.set(notif.email_senha)
        self.var_tg_token.set(notif.telegram_token)
        self.var_tg_chat.set(notif.telegram_chat_id)
        self.var_ntfy_topic.set(notif.ntfy_topic)
        self.var_ntfy_servidor.set(notif.ntfy_servidor)

    def _mostrar_ajuda(self, titulo, texto):
        janela = tk.Toplevel(self)
        janela.title(f"Ajuda — {titulo}")
        janela.geometry("480x320")
        txt = tk.Text(janela, wrap="word", padx=10, pady=10)
        txt.insert("1.0", texto)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)
        ttk.Button(janela, text="Fechar", command=janela.destroy).pack(pady=6)

    def _alternar_persistencia(self):
        if not self.var_lembrar.get():
            apagar_segredos_notificacao()
            self.lbl_status.config(text="Segredos de notificação salvos anteriormente foram apagados do disco.")

    def _salvar_config(self):
        # Desde a 6.1.0: tudo conferido ANTES de mexer na configuração.
        from app.core.validadores import problema_url_webhook, problemas_email_cfg
        url = self.var_webhook_url.get().strip()
        if (url or self.var_webhook_ativo.get()) and problema_url_webhook(url):
            self.lbl_status.config(text=f"❌ Não salvo: {problema_url_webhook(url)}")
            return
        if self.var_email_ativo.get():
            problemas = problemas_email_cfg(self._email_cfg(), self.var_email_senha.get())
            if problemas:
                self.lbl_status.config(text="❌ Não salvo — e-mail: " + " ".join(problemas))
                return
        cfg = self.app.settings["notificacoes"]
        cfg["telegram_ativo"] = self.var_telegram_ativo.get()
        cfg["ntfy_ativo"] = self.var_ntfy_ativo.get()
        cfg["alarme_ativo"] = self.var_alarme_ativo.get()
        cfg["alarme"]["repeticoes"] = self.var_alarme_rep.get()
        cfg["alarme"]["duracao_seg"] = self.var_alarme_dur.get()
        for chave, var in self.vars_eventos.items():
            cfg["eventos"][chave] = var.get()
        try:
            horas = float(self.var_resumo_horas.get().replace(",", "."))
        except ValueError:
            horas = -1
        if not 0.5 <= horas <= 48:
            self.lbl_status.config(text="❌ Não salvo: o intervalo do resumo periódico deve estar entre 0,5 e 48 horas.")
            return
        cfg["resumo_intervalo_horas"] = horas
        cfg["windows_ativo"] = self.var_windows_ativo.get()
        cfg["webhook_ativo"] = self.var_webhook_ativo.get()
        cfg["webhook_formato"] = self.var_webhook_formato.get()
        cfg["email_ativo"] = self.var_email_ativo.get()
        cfg["email"] = self._email_cfg()
        self.app.salvar_settings()

        notif = self.app.sessao.notificacao
        notif.telegram_token = self.var_tg_token.get().strip()
        notif.telegram_chat_id = self.var_tg_chat.get().strip()
        notif.ntfy_topic = self.var_ntfy_topic.get().strip()
        notif.ntfy_servidor = self.var_ntfy_servidor.get().strip() or "https://ntfy.sh"
        notif.webhook_url = url
        notif.email_senha = self.var_email_senha.get()

        if self.var_lembrar.get():
            salvar_segredos_notificacao(notif.telegram_token, notif.telegram_chat_id, notif.ntfy_topic, notif.ntfy_servidor,
                                        notif.webhook_url, notif.email_senha)
            self.lbl_status.config(text="✅ Configuração salva (segredos de notificação guardados neste computador, como solicitado).")
        else:
            self.lbl_status.config(text="✅ Configuração salva (segredos de notificação só em memória).")

    def _testar_telegram(self):
        token, chat = self.var_tg_token.get().strip(), self.var_tg_chat.get().strip()
        if not token or not chat:
            messagebox.showwarning("Faltam dados", "Preencha o token e o chat ID antes de testar.")
            return
        self.lbl_status.config(text="Enviando teste do Telegram...")
        _rodar_async_em_thread(lambda: testar_telegram(token, chat), self._resultado_teste)

    def _testar_ntfy(self):
        topic, servidor = self.var_ntfy_topic.get().strip(), self.var_ntfy_servidor.get().strip() or "https://ntfy.sh"
        if not topic:
            messagebox.showwarning("Faltam dados", "Preencha o tópico antes de testar.")
            return
        self.lbl_status.config(text="Enviando teste do ntfy...")
        _rodar_async_em_thread(lambda: testar_ntfy(topic, servidor), self._resultado_teste)

    def _testar_alarme(self):
        self.lbl_status.config(text="Tocando alarme de teste...")
        _rodar_async_em_thread(lambda: testar_alarme(self.var_alarme_rep.get(), min(3, self.var_alarme_dur.get())), self._resultado_teste)

    def _testar_todos(self):
        """Seção 44: testa todos os canais habilitados de uma vez, mostrando OK/erro de cada um."""
        tarefas = []
        if self.var_telegram_ativo.get():
            token, chat = self.var_tg_token.get().strip(), self.var_tg_chat.get().strip()
            if token and chat:
                tarefas.append(("Telegram", lambda: testar_telegram(token, chat)))
        if self.var_ntfy_ativo.get():
            topic, servidor = self.var_ntfy_topic.get().strip(), self.var_ntfy_servidor.get().strip() or "https://ntfy.sh"
            if topic:
                tarefas.append(("ntfy", lambda: testar_ntfy(topic, servidor)))
        if self.var_alarme_ativo.get():
            tarefas.append(("Alarme", lambda: testar_alarme(self.var_alarme_rep.get(), min(3, self.var_alarme_dur.get()))))
        if self.var_windows_ativo.get():
            from app.notifications import windows as windows_notif
            if windows_notif.disponivel():
                tarefas.append(("Windows", windows_notif.testar_windows))
        if self.var_webhook_ativo.get() and self.var_webhook_url.get().strip().startswith("https://"):
            from app.notifications.webhook import testar_webhook
            url, formato = self.var_webhook_url.get().strip(), self.var_webhook_formato.get()
            tarefas.append(("Webhook", lambda: testar_webhook(url, formato)))
        if self.var_email_ativo.get():
            from app.notifications.email import configurado, testar_email
            cfg_email, senha = self._email_cfg(), self.var_email_senha.get()
            if configurado(cfg_email, senha):
                tarefas.append(("E-mail", lambda: testar_email(cfg_email, senha)))

        if not tarefas:
            messagebox.showinfo("Nada para testar", "Nenhum canal de notificação está ativado e preenchido.")
            return

        self.lbl_status.config(text="Testando todos os canais habilitados...")

        async def rodar_tudo():
            linhas = []
            for nome, corotina_factory in tarefas:
                try:
                    await corotina_factory()
                    linhas.append(f"{nome}: OK")
                except Exception as e:
                    linhas.append(f"{nome}: falhou ({e})")
            return "\n".join(linhas)

        _rodar_async_em_thread(rodar_tudo, self._resultado_teste)

    def _resultado_teste(self, resultado, erro):
        def atualizar():
            if erro:
                self.lbl_status.config(text=f"❌ Falha no teste: {erro}")
            else:
                self.lbl_status.config(text=f"✅ {resultado}")
        self.after(0, atualizar)
