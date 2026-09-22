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
from app.gui.responsive import tornar_rolavel
from app.notifications.alarm import testar_alarme
from app.notifications.ntfy import testar_ntfy
from app.notifications.telegram import testar_telegram

TEXTO_AJUDA_TELEGRAM = (
    "Como configurar o Telegram:\n\n"
    "1. No Telegram, converse com @BotFather e envie /newbot.\n"
    "2. Siga as instruções e copie o TOKEN gerado (algo como 123456:ABC-def...).\n"
    "3. Envie qualquer mensagem para o seu novo bot.\n"
    "4. Abra no navegador: https://api.telegram.org/bot<SEU_TOKEN>/getUpdates\n"
    "5. Procure o campo \"chat\":{\"id\": ...} — esse número é o seu Chat ID.\n"
    "6. Cole o token e o chat ID nesta tela."
)
TEXTO_AJUDA_NTFY = (
    "Como configurar o ntfy:\n\n"
    "1. Instale o app ntfy (Android/iOS) ou use https://ntfy.sh no navegador.\n"
    "2. Escolha um nome de tópico difícil de adivinhar (ele funciona como senha),\n"
    "   ex: sigaa-vagas-8f2ak9.\n"
    "3. Inscreva-se nesse mesmo tópico no app ou no site.\n"
    "4. Digite o mesmo nome de tópico nesta tela."
)
TEXTO_AJUDA_ALARME = (
    "Como funciona o alarme local:\n\n"
    "Quando uma vaga é detectada (ou uma matrícula é confirmada), o programa\n"
    "toca um som repetido no computador onde ele está rodando. Não depende de\n"
    "internet nem de configuração externa — só funciona enquanto o programa\n"
    "está aberto neste computador."
)


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
        ttk.Label(self, text="O programa funciona normalmente com tudo desligado aqui.", foreground="#666").pack(anchor="w", pady=(0, 10))

        # Corrige um problema real de usabilidade: com muitos blocos (Telegram,
        # ntfy, alarme, eventos, persistência) empilhados, o conteúdo podia
        # ultrapassar a altura da janela e o botão "Testar todos" ficar
        # inacessível. Agora tudo — inclusive o botão e o status — fica dentro
        # de uma área rolável (ver app/gui/responsive.py).
        canvas_frame = tornar_rolavel(self)

        self._bloco_telegram(canvas_frame)
        self._bloco_ntfy(canvas_frame)
        self._bloco_alarme(canvas_frame)
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

    def _bloco_eventos(self, parent):
        """Seção 41: quais eventos disparam notificação — não obriga o usuário a receber tudo."""
        cfg = self.app.settings["notificacoes"]["eventos"]
        frame = ttk.LabelFrame(parent, text="Quais eventos notificar", padding=10)
        frame.pack(fill="x", pady=6)

        rotulos = {
            "vaga_detectada": "Vaga encontrada",
            "matricula_sucesso": "Matrícula confirmada",
            "matricula_falha": "Tentativa de matrícula falhou (retry automático)",
            "matricula_bloqueada": "Disciplina bloqueada pelo SIGAA (pré-requisito/choque)",
            "erro_critico": "Erro crítico",
        }
        self.vars_eventos = {}
        for chave, rotulo in rotulos.items():
            var = tk.BooleanVar(value=cfg.get(chave, False))
            self.vars_eventos[chave] = var
            ttk.Checkbutton(frame, text=rotulo, variable=var).pack(anchor="w")

    def _bloco_persistencia(self, parent):
        frame = ttk.LabelFrame(parent, text="Salvar dados de notificação neste computador", padding=10)
        frame.pack(fill="x", pady=6)
        ttk.Label(
            frame, wraplength=560, justify="left", foreground="#9a6700",
            text=(
                "⚠️ Por padrão, o token do Telegram e o tópico do ntfy também são só de\n"
                "memória (como as credenciais do SIGAA). Se marcar a opção abaixo, eles\n"
                "serão gravados em texto simples (não criptografado) em\n"
                "config/notificacoes.secrets.json, só para não precisar redigitar toda vez."
            ),
        ).pack(anchor="w")

        self.var_lembrar = tk.BooleanVar(value=existe_segredos_notificacao_salvos())
        ttk.Checkbutton(frame, text="Salvar neste computador (arquivo não criptografado)", variable=self.var_lembrar, command=self._alternar_persistencia).pack(anchor="w", pady=(6, 0))

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
        cfg = self.app.settings["notificacoes"]
        cfg["telegram_ativo"] = self.var_telegram_ativo.get()
        cfg["ntfy_ativo"] = self.var_ntfy_ativo.get()
        cfg["alarme_ativo"] = self.var_alarme_ativo.get()
        cfg["alarme"]["repeticoes"] = self.var_alarme_rep.get()
        cfg["alarme"]["duracao_seg"] = self.var_alarme_dur.get()
        for chave, var in self.vars_eventos.items():
            cfg["eventos"][chave] = var.get()
        self.app.salvar_settings()

        notif = self.app.sessao.notificacao
        notif.telegram_token = self.var_tg_token.get().strip()
        notif.telegram_chat_id = self.var_tg_chat.get().strip()
        notif.ntfy_topic = self.var_ntfy_topic.get().strip()
        notif.ntfy_servidor = self.var_ntfy_servidor.get().strip() or "https://ntfy.sh"

        if self.var_lembrar.get():
            salvar_segredos_notificacao(notif.telegram_token, notif.telegram_chat_id, notif.ntfy_topic, notif.ntfy_servidor)
            self.lbl_status.config(text="✅ Configuração salva (incluindo segredos de notificação em disco, como solicitado).")
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
