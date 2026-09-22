"""
Dashboard de terminal — reescrita de legacy/base_v4.0/dashboard_sniper.py
usando o ColetorMetricas auditado (app/dashboard/metrics.py) em vez da lógica
antiga com bugs de métrica. Visual equivalente (rich), números confiáveis.
"""
from __future__ import annotations

import re
import time

from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from app.dashboard.metrics import ColetorMetricas, LogTailer, formatar_uptime
from app.utils.paths import caminho as caminho_projeto

SEM_DADOS = "[dim]sem dados[/]"


def _fmt(valor, sufixo="", casas=1):
    return f"{valor:.{casas}f}{sufixo}" if valor is not None else SEM_DADOS


def _fmt_ms(valor):
    return f"{valor:.0f} ms" if valor is not None else SEM_DADOS


def _texto_saude(saude: dict) -> str:
    # Se-elif em vez de dict literal: um dict literal avaliaria as f-strings de
    # TODOS os status de uma vez (mesmo os não escolhidos), e taxa_erro é None
    # quando status="aguardando_trafego" — formatá-lo com :.0% quebraria sempre.
    status = saude["status"]
    if status == "estavel":
        return "[bold white on green] ✅ SISTEMA ESTÁVEL [/]"
    if status == "degradado":
        return f"[bold black on yellow] ⚠️ DEGRADADO (Erros: {saude['taxa_erro']:.0%}) [/]"
    if status == "critico":
        return f"[bold white on red] 📛 CRÍTICO (Erros: {saude['taxa_erro']:.0%}) [/]"
    return "[bold yellow]AGUARDANDO TRÁFEGO[/]"


def gerar_painel_topo(coletor: ColetorMetricas) -> Panel:
    m = coletor.snapshot()
    saude_txt = _texto_saude(m["saude"])

    grid = Table.grid(expand=True)
    for _ in range(4):
        grid.add_column(justify="center", ratio=1)

    grid.add_row(
        f"[b]Atual (RPS):[/] [cyan]{_fmt(m['rps_atual'], ' req/s')}[/]",
        f"[b]Atual (BPS):[/] [yellow]{_fmt(m['bps_atual'], ' bps')}[/]",
        f"[b]Latência (Últ. 100):[/] [cyan]{_fmt_ms(m['latencia_recente_ms'])}[/]",
        f"[b]Saúde do Link:[/] {saude_txt}",
    )
    grid.add_row(
        f"Média Histórica: [blue]{_fmt(m['avg_rps'], ' req/s')}[/]",
        f"Média Histórica: [blue]{_fmt(m['avg_bps'], ' bps')}[/]",
        f"Média Geral: [blue]{_fmt_ms(m['latencia_media_ms'])}[/]",
        f"[b]Uptime Bot:[/] [dim]{formatar_uptime(m['uptime_bot_seg'])}[/]",
    )
    grid.add_row(
        f"[b]Total Reqs:[/] {m['total_reqs']} [dim]({m['total_reqs_falha_rede']} c/ falha de rede)[/]",
        f"[b]Total Buscas:[/] [magenta]{m['total_buscas']}[/]",
        f"[b]Mín/Máx:[/] [green]{_fmt_ms(m['latencia_min_ms'])}[/] / [red]{_fmt_ms(m['latencia_max_ms'])}[/]",
        f"[b]Uptime Painel:[/] [dim]{formatar_uptime(m['uptime_dashboard_seg'])}[/]",
    )

    return Panel(grid, title="[bold white]⚡ RADAR DE TRÁFEGO E TELEMETRIA[/]", style="blue")


def gerar_tabela_workers(coletor: ColetorMetricas) -> Panel:
    m = coletor.snapshot()
    table = Table(expand=True, show_header=True, header_style="bold magenta", border_style="dim")
    table.add_column("Worker", justify="center", width=8)
    table.add_column("Erros", justify="center", width=8)
    table.add_column("Buscas", justify="center", width=10)
    table.add_column("Última Ação", justify="left")
    table.add_column("Latência", justify="center", width=12)
    table.add_column("Idle (Ocioso)", justify="center", width=15)

    agora_real = time.time()

    def worker_sort(key):
        m2 = re.match(r"^W(\d+)$", key)
        return int(m2.group(1)) if m2 else 9999

    for w_id in sorted(m["workers"].keys(), key=worker_sort):
        w = m["workers"][w_id]
        ocioso = agora_real - w["timestamp"]
        str_ocioso = f"{ocioso:.1f}s" if ocioso <= 5.0 else f"[bold red]{ocioso:.1f}s (Sleep)[/]"

        lat = w["latencia"]
        cor_lat = {"verde": "green", "amarelo": "yellow", "vermelho": "red"}.get(w.get("cor_lat"), "white")
        str_lat = f"[{cor_lat}]{lat} ms[/]" if lat > 0 else "-"

        err_c = w["erros_count"]
        str_erros = f"[bold red]{err_c}[/]" if err_c > 0 else "[dim]0[/]"

        table.add_row(f"[bold]{w_id}[/]", str_erros, str(w["buscas_feitas"]), w["ultima_acao"], str_lat, str_ocioso)

    return Panel(table, title="[bold white]🤖 ESQUADRÃO DE SNIPERS[/]", style="cyan")


def gerar_painel_vagas(coletor: ColetorMetricas) -> Panel:
    m = coletor.snapshot()
    if not m["registro_vagas"]:
        return Panel(Align.center("\n[dim italic]Aguardando o surgimento de vagas...[/]"), title="[bold green]🎯 REGISTRO DE EVENTOS (VAGAS)[/]", style="green")
    return Panel("\n".join(m["registro_vagas"]), title="[bold green]🎯 REGISTRO DE EVENTOS (VAGAS)[/]", style="green")


def gerar_painel_erros(coletor: ColetorMetricas) -> Panel:
    m = coletor.snapshot()
    if not m["log_erros"]:
        return Panel(Align.center("\n[dim green]Sistema rodando liso e sem falhas.[/]"), title="[bold red]⚠️ EXCEÇÕES E FALHAS[/]", style="red")
    return Panel("\n".join(m["log_erros"]), title="[bold red]⚠️ EXCEÇÕES E FALHAS[/]", style="red")


def main(arquivo_log: str = None) -> None:
    log_file = arquivo_log or caminho_projeto("data", "sigaa_sniper_audit.json")

    # legacy_windows=False evita uma falha real encontrada em testes: em alguns
    # terminais Windows (cp1252), o modo "legacy" do rich tenta escrever emojis
    # direto pela API do console e quebra com UnicodeEncodeError.
    console = Console(legacy_windows=False)
    console.clear()

    if not __import__("os").path.exists(log_file):
        console.print(f"Aguardando a criação do log em: {log_file}")
        while not __import__("os").path.exists(log_file):
            time.sleep(1)

    layout = Layout()
    layout.split(Layout(name="topo", size=5), Layout(name="meio"), Layout(name="base", size=10))
    layout["base"].split_row(Layout(name="vagas", ratio=2), Layout(name="erros", ratio=1))

    tailer = LogTailer(log_file)
    coletor = ColetorMetricas()

    for linha in tailer.read_new_lines():
        coletor.processar_linha(linha, ao_vivo=False)

    with Live(layout, console=console, refresh_per_second=5) as live:
        while True:
            novas = tailer.read_new_lines()
            if not novas:
                time.sleep(0.05)
            else:
                for linha in novas:
                    coletor.processar_linha(linha, ao_vivo=True)

            layout["topo"].update(gerar_painel_topo(coletor))
            layout["meio"].update(gerar_tabela_workers(coletor))
            layout["vagas"].update(gerar_painel_vagas(coletor))
            layout["erros"].update(gerar_painel_erros(coletor))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[ Sniper Dashboard ] Sessão finalizada pelo usuário.")
