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

from app.core.relatorios import texto_relatorio
from app.dashboard.analise import agrupar_erros, avaliar_saude, descrever_fase, tempo_relativo
from app.dashboard.metrics import criar_tailer_da_sessao, ColetorMetricas, LogTailer, formatar_uptime
from app.gui.responsive import tornar_rolavel
from app.utils.paths import caminho as caminho_projeto
from app.gui.tema import cor

SEM_DADOS = "sem dados"


def _fmt(v, sufixo="", casas=1):
    return f"{v:.{casas}f}{sufixo}" if v is not None else SEM_DADOS


def _fmt_ms(v):
    return f"{v:.0f} ms" if v is not None else SEM_DADOS


COR_SAUDE_MOTOR = {"aguardando": cor("#9a6700"), "estavel": cor("#1a7f37"), "atencao": cor("#9a6700"), "critico": cor("#cf222e")}
ICONE_SAUDE = {"aguardando": "⏳", "estavel": "✅", "atencao": "⚠️", "critico": "📛"}

COR_SAUDE = {
    "aguardando_trafego": ("Aguardando tráfego", cor("#9a6700")),
    "estavel": ("✅ Sistema estável", cor("#1a7f37")),
    "degradado": ("⚠️ Degradado", cor("#9a6700")),
    "critico": ("📛 Crítico", cor("#cf222e")),
}


def m_tem_dados(coletor) -> bool:
    return coletor.stats["start_time_log"] is not None


class TelaDashboard(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self.coletor = ColetorMetricas()
        # Desde a 6.1.0: começa do fim do log (nada de execução anterior como se fosse a atual),
        # a menos que "carregar_ultima_execucao" esteja ligado.
        self.carregar_ultima = bool(app.settings.get("carregar_ultima_execucao"))
        self.tailer = criar_tailer_da_sessao(caminho_projeto("data", "sigaa_sniper_audit.json"), self.carregar_ultima)
        self._backlog_lido = False
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
        self.btn_resumo = ttk.Button(topo, text="📋 Resumo da execução", command=self._ver_resumo)
        self.lbl_saude = ttk.Label(topo, text="—", font=("Segoe UI", 10, "bold"))
        self.lbl_saude.pack(side="right", padx=(0, 10))

        # Fase da execução (sugestão 086) e nota sobre os gráficos (só na Web).
        self.lbl_fase = ttk.Label(corpo, text="", foreground=cor("#57606a"))
        self.lbl_fase.pack(anchor="w", pady=(4, 0))
        self.barra_fase = ttk.Progressbar(corpo, mode="determinate", maximum=100)

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

        self.lbl_alerta_workers = ttk.Label(corpo, text="", foreground=cor("#cf222e"), wraplength=900, justify="left")
        self.lbl_alerta_workers.pack(anchor="w", pady=(4, 0))
        # Fase 5: alertas por limiar ativos (058/090) e a última tentativa de matrícula (059).
        self.lbl_alertas_limiar = ttk.Label(corpo, text="", foreground=cor("#9a6700"), wraplength=900, justify="left")
        self.lbl_alertas_limiar.pack(anchor="w")
        self.lbl_tentativa = ttk.Label(corpo, text="", foreground=cor("#57606a"), wraplength=900, justify="left")
        self.lbl_tentativa.pack(anchor="w")

        # Estado de cada disciplina (sugestão 019).
        ttk.Label(corpo, text="Disciplinas", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(10, 4))
        colunas_alvos = ("disciplina", "estado", "vagas", "leitura", "buscas", "vistas", "tentativas")
        self.tree_alvos = ttk.Treeview(corpo, columns=colunas_alvos, show="headings", height=4)
        for col, titulo, largura in [
            ("disciplina", "Disciplina", 110), ("estado", "Estado", 220), ("vagas", "Vagas", 60), ("leitura", "Última leitura", 110),
            ("buscas", "Buscas", 70), ("vistas", "Vaga vista", 80), ("tentativas", "Tentativas", 80),
        ]:
            self.tree_alvos.heading(col, text=titulo)
            self.tree_alvos.column(col, width=largura, anchor="w" if col in ("disciplina", "estado") else "center")
        self.tree_alvos.pack(fill="x")
        self.lbl_alvos_vazio = ttk.Label(corpo, text="Inicie uma execução para acompanhar cada disciplina aqui.", foreground=cor("#57606a"))
        self.lbl_alvos_vazio.pack(anchor="w")

        # Saúde com causa provável (020) e erros por tipo com ação (021).
        meio = ttk.Frame(corpo)
        meio.pack(fill="x", pady=(10, 0))
        meio.columnconfigure(0, weight=1)
        meio.columnconfigure(1, weight=1)
        saude_frame = ttk.LabelFrame(meio, text="Saúde da conexão", padding=8)
        saude_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.lbl_saude_causa = ttk.Label(saude_frame, text="Inicie uma execução para ver a saúde da conexão com o SIGAA.",
                                         wraplength=420, justify="left")
        self.lbl_saude_causa.pack(anchor="w")
        self.lbl_saude_indicadores = ttk.Label(saude_frame, text="", foreground=cor("#57606a"), wraplength=420, justify="left")
        self.lbl_saude_indicadores.pack(anchor="w", pady=(6, 0))
        erros_tipo = ttk.LabelFrame(meio, text="Erros por tipo (nesta execução)", padding=8)
        erros_tipo.grid(row=0, column=1, sticky="nsew")
        self.tree_erros = ttk.Treeview(erros_tipo, columns=("tipo", "qtd", "ultima"), show="headings", height=4)
        for col, titulo, largura in [("tipo", "Tipo", 170), ("qtd", "Qtd.", 70), ("ultima", "Última", 90)]:
            self.tree_erros.heading(col, text=titulo)
            self.tree_erros.column(col, width=largura, anchor="w" if col == "tipo" else "center")
        self.tree_erros.pack(fill="x")
        self.tree_erros.bind("<<TreeviewSelect>>", self._mostrar_acao_erro)
        self.lbl_acao_erro = ttk.Label(erros_tipo, text="Selecione um tipo para ver o que fazer.", foreground=cor("#57606a"),
                                       wraplength=380, justify="left")
        self.lbl_acao_erro.pack(anchor="w", pady=(4, 0))
        ttk.Label(corpo, text="Gráficos (tempo de resposta, buscas por segundo, vagas no tempo, erros por tipo) estão na "
                              "Interface Web → Dashboard → Gráficos.", foreground=cor("#57606a")).pack(anchor="w", pady=(6, 0))

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
        for linha in self.tailer.read_new_lines():
            self.coletor.processar_linha(linha, ao_vivo=self._backlog_lido)
        self._backlog_lido = True

        ativa = bool(self.app.estado_execucao().get("em_execucao"))
        m = self.coletor.snapshot(execucao_ativa=ativa)
        motor = getattr(self.app, "_motor", None)
        snap = motor.snapshot() if motor is not None and hasattr(motor, "snapshot") else None
        recuperado = bool(self.carregar_ultima and motor is None and m["tem_dados"])

        if not snap and not ativa:
            self.lbl_saude.config(text="📂 Última execução (recuperada)" if recuperado else "⚪ Nenhuma execução em andamento",
                                  foreground=cor("#57606a"))
        elif snap:
            saude = avaliar_saude(snap)
            self.lbl_saude.config(text=f"{ICONE_SAUDE[saude['nivel']]} {saude['titulo']}", foreground=COR_SAUDE_MOTOR[saude["nivel"]])
        else:
            texto_saude, tom = COR_SAUDE[m["saude"]["status"]]
            self.lbl_saude.config(text=texto_saude, foreground=tom)
        self._atualizar_motor(snap, motor)

        self.labels_cards["rps"].config(text=_fmt(m["rps_atual"], " req/s"))
        self.labels_cards["bps"].config(text=_fmt(m["bps_atual"], " bps"))
        self.labels_cards["latencia"].config(text=_fmt_ms(m["latencia_recente_ms"]))
        self.labels_cards["total_buscas"].config(text=str(m["total_buscas"]))
        self.labels_cards["vagas"].config(text=str(m["vagas_encontradas"]))
        self.labels_cards["uptime"].config(text=formatar_uptime(m["uptime_bot_seg"]))

        if snap:
            self._atualizar_workers_motor(snap["workers"])
        else:
            self._atualizar_workers(m["workers"], ativa)
        self._atualizar_texto(self.txt_vagas, m["registro_vagas"])
        self._atualizar_texto(self.txt_erros, m["log_erros"])
        self._historico_vagas_atual = m["historico_vagas"]

        alertas = ([f"{w['id']} sem progresso há {w['ocioso_seg']:.0f}s ({w['estado_rotulo']})" for w in snap["workers"]
                    if w["estado"] != "encerrado" and w["ocioso_seg"] > 30] if snap else m["workers_com_alerta"])
        if alertas:
            self.lbl_alerta_workers.config(text="⚠ Possível problema detectado: " + " | ".join(alertas))
        else:
            self.lbl_alerta_workers.config(text="")

    def _atualizar_motor(self, snap, motor):
        """Seções que só existem com uma execução nesta sessão (dados do motor)."""
        import time
        agora = (snap or {}).get("fim") or time.time()  # encerrada: congelado no instante do fim
        fase = descrever_fase(snap, agora)
        self.lbl_fase.config(text=fase["texto"] if snap else (
            "Mostrando dados recuperados da última execução (já encerrada). Nenhuma execução em andamento."
            if self.carregar_ultima and m_tem_dados(self.coletor) else
            "Nenhuma execução em andamento. Os números aparecem quando você iniciar uma execução."))
        if fase["progresso"] is not None:
            self.barra_fase["value"] = round(fase["progresso"] * 100)
            if not self.barra_fase.winfo_ismapped():
                self.barra_fase.pack(fill="x", pady=(2, 0), after=self.lbl_fase)
        elif self.barra_fase.winfo_ismapped():
            self.barra_fase.pack_forget()
        if getattr(motor, "resumo", None):
            if not self.btn_resumo.winfo_ismapped():
                self.btn_resumo.pack(side="right", padx=(0, 10))
        elif self.btn_resumo.winfo_ismapped():
            self.btn_resumo.pack_forget()

        self.tree_alvos.delete(*self.tree_alvos.get_children())
        if snap:
            for a in snap["alvos"]:
                self.tree_alvos.insert("", "end", values=(
                    a["chave"], a["estado_rotulo"], "—" if a["vagas"] is None else a["vagas"],
                    tempo_relativo(a["ultima_leitura"], agora), a["buscas"], a["vagas_vistas"], a["tentativas"]))
        if snap and snap["alvos"]:
            self.lbl_alvos_vazio.pack_forget()
        elif not self.lbl_alvos_vazio.winfo_ismapped():
            self.lbl_alvos_vazio.pack(anchor="w", after=self.tree_alvos)

        ativos = (snap.get("alertas") or {}).get("ativos", []) if snap else []
        self.lbl_alertas_limiar.config(text="\n".join(f"🔔 {a['titulo']} — {a['texto']}" for a in ativos))
        tentativas = snap.get("tentativas", []) if snap else []
        if tentativas:
            t = tentativas[-1]
            etapas = " → ".join(f"{e['rotulo']} {e['ms']} ms" for e in t["etapas"]) or "—"
            resultado = {"SUCESSO": "sucesso" + (" (DRY RUN)" if t.get("dry_run") else ""), "ERRO_REGRA": "bloqueada pelo SIGAA",
                         "FALHA": "falhou", "ERRO": "interrompida"}.get(t.get("resultado"), "em andamento")
            self.lbl_tentativa.config(text=f"🎯 Última tentativa ({len(tentativas)} no total): {t['chave']} por {t['worker']} — "
                                           f"{resultado}. Etapas: {etapas}.")
        else:
            self.lbl_tentativa.config(text="")

        if not snap:
            return
        saude = avaliar_saude(snap)
        self.lbl_saude_causa.config(text=saude["causa"])
        i = saude["indicadores"]
        taxa = "—" if i["taxa_erro"] is None else f"{round(i['taxa_erro'] * 100)}%"
        self.lbl_saude_indicadores.config(text=(
            f"Resposta agora: {_fmt_ms(i['latencia_recente_ms'])} · típica: {_fmt_ms(i['latencia_mediana_ms'])} · "
            f"taxa de erro ({i['janela_seg']}s): {taxa}\nTempos esgotados: {i['timeouts']} · sessões expiradas: "
            f"{i['sessoes_expiradas']} · novos logins: {i['relogins']} · falhas de rede: {i['falhas_rede']}"))
        selecionado = self.tree_erros.selection()
        self._grupos_erros = {g["categoria"]: g for g in agrupar_erros(snap)}
        self.tree_erros.delete(*self.tree_erros.get_children())
        for cat, g in self._grupos_erros.items():
            self.tree_erros.insert("", "end", iid=cat, values=(g["rotulo"], f"{g['total']} ({g['percentual']}%)", tempo_relativo(g["ultima"], agora)))
        if selecionado and self.tree_erros.exists(selecionado[0]):
            self.tree_erros.selection_set(selecionado[0])

    def _mostrar_acao_erro(self, _event=None):
        sel = self.tree_erros.selection()
        grupo = getattr(self, "_grupos_erros", {}).get(sel[0]) if sel else None
        if grupo:
            self.lbl_acao_erro.config(text=f"O que fazer: {grupo['acao']}")

    def _ver_resumo(self):
        resumo = getattr(getattr(self.app, "_motor", None), "resumo", None)
        if not resumo:
            return
        janela = tk.Toplevel(self)
        janela.title("Resumo da execução")
        janela.geometry("640x420")
        txt = tk.Text(janela, wrap="none", padx=10, pady=10, font=("Consolas", 10))
        txt.insert("1.0", texto_relatorio(resumo) + "\n\nUma cópia deste resumo fica em data/relatorios/.")
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)
        ttk.Button(janela, text="Fechar", command=janela.destroy).pack(pady=6)

    def _atualizar_workers_motor(self, workers: list):
        """Estado REAL de cada worker, vindo do motor (sugestão 055) — antes era deduzido do log."""
        vistos = set()
        for w in sorted(workers, key=lambda x: int(x["id"][1:]) if x["id"][1:].isdigit() else 9999):
            c = w["contadores"]
            erros = c.get("timeouts", 0) + c.get("falhas_rede", 0) + c.get("sessoes_expiradas", 0) + c.get("erros_criticos", 0)
            acao = w["estado_rotulo"] + (f" · {w['alvo']}" if w["alvo"] else "")
            ocioso = "—" if w["estado"] == "encerrado" else f"{w['ocioso_seg']:.1f}s"
            valores = (w["id"], erros, c.get("buscas", 0), acao, f"{w['latencia_ms']} ms" if w["latencia_ms"] is not None else "-", ocioso)
            if self.tree.exists(w["id"]):
                self.tree.item(w["id"], values=valores)
            else:
                self.tree.insert("", "end", iid=w["id"], values=valores)
            vistos.add(w["id"])
        for item in self.tree.get_children():
            if item not in vistos:
                self.tree.delete(item)

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

    def _atualizar_workers(self, workers: dict, ativa: bool = True):
        import time
        agora = time.time()

        def ordenar(k):
            mm = re.match(r"^W(\d+)$", k)
            return int(mm.group(1)) if mm else 9999

        vistos = set()
        for w_id in sorted(workers.keys(), key=ordenar):
            w = workers[w_id]
            ocioso = f"{agora - w['timestamp']:.1f}s" if ativa else "—"
            lat = w["latencia"]
            valores = (w_id, w["erros_count"], w["buscas_feitas"], w["ultima_acao"], f"{lat} ms" if lat else "-", ocioso)
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
