"""
Diagnóstico — seção 44 do pedido. Usado pela GUI e pelo terminal.

Regra: o relatório de diagnóstico NUNCA inclui credenciais, tokens ou
qualquer dado sensível — só versões, tamanhos e status de conectividade.
"""
from __future__ import annotations

import importlib.metadata
import platform
import shutil
import sys
from dataclasses import dataclass
from typing import List, Optional

import httpx

from app.core.config import carregar_disciplinas, carregar_settings
from app.core.crash_recovery import verificar_encerramento_anterior
from app.core.resource_monitor import resumo_recursos
from app.utils.cleanup import resumo_espaco_em_disco
from app.utils.paths import raiz_projeto
from app.versao import VERSAO_APP  # reexportado: GUI/terminal/Web importam daqui

PACOTES_NECESSARIOS = ["httpx", "beautifulsoup4", "rich"]


@dataclass
class ResultadoChecagem:
    nome: str
    ok: Optional[bool]  # True=OK, False=ERRO, None=NÃO TESTADO/DESATIVADO (nunca uma pontuação arbitrária)
    detalhe: str


def checar_python() -> ResultadoChecagem:
    versao = sys.version.split()[0]
    ok = sys.version_info >= (3, 9)
    return ResultadoChecagem("Versão do Python", ok, f"{versao} ({platform.system()} {platform.release()})" + ("" if ok else " — recomendado 3.9+"))


MODULO_DO_PACOTE = {"httpx": "httpx", "beautifulsoup4": "bs4", "rich": "rich"}


def checar_dependencias() -> List[ResultadoChecagem]:
    """
    Checa por versão via importlib.metadata quando possível, mas cai para um
    import direto do módulo se isso falhar. Necessário porque, dentro de um
    executável empacotado com PyInstaller, importlib.metadata não enxerga os
    pacotes embutidos no bundle (não há dist-info ali) mesmo que o pacote
    esteja perfeitamente funcional — sem esse fallback, o diagnóstico reporta
    "NÃO instalada" para bibliotecas que na verdade estão funcionando (bug
    real encontrado ao testar o .exe gerado, ver docs/ARQUITETURA.md).
    """
    resultados = []
    for pacote in PACOTES_NECESSARIOS:
        try:
            versao = importlib.metadata.version(pacote)
            resultados.append(ResultadoChecagem(f"Biblioteca {pacote}", True, f"instalada (versão {versao})"))
            continue
        except importlib.metadata.PackageNotFoundError:
            pass

        try:
            __import__(MODULO_DO_PACOTE[pacote])
            resultados.append(ResultadoChecagem(f"Biblioteca {pacote}", True, "instalada (versão não detectável neste empacotamento)"))
        except ImportError:
            resultados.append(ResultadoChecagem(f"Biblioteca {pacote}", False, "NÃO instalada"))
    return resultados


def checar_espaco_em_disco() -> ResultadoChecagem:
    total, usado, livre = shutil.disk_usage(raiz_projeto())
    livre_gb = livre / (1024 ** 3)
    ok = livre_gb > 0.5
    return ResultadoChecagem("Espaço livre em disco", ok, f"{livre_gb:.1f} GB livres")


def checar_tamanho_dados() -> ResultadoChecagem:
    resumo = resumo_espaco_em_disco()
    total = resumo["logs_mb"] + resumo["data_mb"] + resumo["config_mb"]
    return ResultadoChecagem("Tamanho de logs/dados", True, f"{total:.1f} MB (logs: {resumo['logs_mb']}, data: {resumo['data_mb']}, config: {resumo['config_mb']})")


def checar_configuracao() -> ResultadoChecagem:
    try:
        settings = carregar_settings()
        disciplinas = carregar_disciplinas()
        return ResultadoChecagem("Arquivos de configuração", True, f"settings.json OK, {len(disciplinas)} disciplina(s) cadastrada(s)")
    except Exception as e:
        return ResultadoChecagem("Arquivos de configuração", False, f"Erro ao ler configuração: {e}")


def checar_modo_execucao() -> ResultadoChecagem:
    """Seção 4/10 do pedido de continuação: o diagnóstico deve deixar claro,
    sem ambiguidade, se a próxima execução vai (ou não) confirmar matrículas de verdade."""
    settings = carregar_settings()
    modo = settings.get("modo", "monitoramento")
    dry_run = settings.get("dry_run", True)

    if modo == "monitoramento":
        return ResultadoChecagem("Modo configurado", True, "SOMENTE MONITORAMENTO — nunca confirma matrícula, independente do DRY RUN")
    if dry_run:
        return ResultadoChecagem("Modo configurado", True, "MATRÍCULA em modo DRY RUN — simula tudo, mas NÃO confirma matrícula real")
    return ResultadoChecagem("Modo configurado", True, "⚠️ MATRÍCULA REAL — DRY RUN desligado, vai confirmar matrícula de verdade quando achar vaga")


async def checar_conectividade_sigaa() -> ResultadoChecagem:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get("https://sigaa.unb.br/sigaa/verTelaLogin.do", follow_redirects=True)
            ok = resp.status_code < 500
            return ResultadoChecagem("Conectividade com o SIGAA", ok, f"HTTP {resp.status_code}")
    except Exception as e:
        return ResultadoChecagem("Conectividade com o SIGAA", False, f"Sem resposta: {type(e).__name__}")


async def checar_conectividade_em_camadas() -> List[ResultadoChecagem]:
    """
    Seção 45: testa cada camada separadamente, para facilitar descobrir
    exatamente onde está o problema (Internet → SIGAA → consulta pública →
    autenticação → monitoramento → notificações).

    Autenticação e Monitoramento dependem de uma execução real com
    credenciais — não são testados aqui (não temos e não devemos usar
    credenciais automaticamente); ficam marcados como NÃO TESTADO.
    """
    resultados = []

    try:
        async with httpx.AsyncClient(timeout=6) as client:
            resp = await client.get("https://www.google.com", follow_redirects=True)
            resultados.append(ResultadoChecagem("1. Internet", resp.status_code < 500, f"HTTP {resp.status_code}"))
    except Exception as e:
        resultados.append(ResultadoChecagem("1. Internet", False, f"Sem conexão: {type(e).__name__}"))
        # Sem internet, as camadas seguintes não têm como funcionar — mas ainda
        # assim tentamos, para o relatório mostrar o mesmo padrão de falha em todas.

    resultados.append(await checar_conectividade_sigaa())

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get("https://sigaa.unb.br/sigaa/public/turmas/listar.jsf")
            ok = resp.status_code == 200 and "formTurma" in resp.text
            resultados.append(ResultadoChecagem("3. Consulta pública de turmas", ok, f"HTTP {resp.status_code}" + ("" if ok else " — página não teve o conteúdo esperado")))
    except Exception as e:
        resultados.append(ResultadoChecagem("3. Consulta pública de turmas", False, f"Sem resposta: {type(e).__name__}"))

    resultados.append(ResultadoChecagem("4. Autenticação (login real)", None, "NÃO TESTADO — requer suas credenciais, não testado automaticamente por segurança"))
    resultados.append(ResultadoChecagem("5. Monitoramento (ciclo completo)", None, "NÃO TESTADO — só é possível avaliar durante uma execução real"))

    settings = carregar_settings()
    cfg = settings.get("notificacoes", {})
    if not (cfg.get("telegram_ativo") or cfg.get("ntfy_ativo") or cfg.get("alarme_ativo")):
        resultados.append(ResultadoChecagem("6. Notificações", None, "DESATIVADO — nenhum canal está ativado"))
    else:
        resultados.append(ResultadoChecagem("6. Notificações", None, "NÃO TESTADO — use o botão 'Testar todos os canais' na aba Notificações"))

    return resultados


def checar_recursos(medir_cpu: bool = False) -> ResultadoChecagem:
    """Seção 37: só reporta o que consegue medir de verdade (memória sempre;
    CPU só quando pedido explicitamente, pois exige uma amostragem de ~0.5s)."""
    r = resumo_recursos(medir_cpu=medir_cpu)
    partes = []
    if r["memoria_mb"] is not None:
        partes.append(f"memória: {r['memoria_mb']:.1f} MB")
    else:
        partes.append("memória: não foi possível medir neste sistema")
    if medir_cpu:
        if r["cpu_percentual"] is not None:
            partes.append(f"CPU: {r['cpu_percentual']:.1f}% (amostra curta, aproximado)")
        else:
            partes.append("CPU: não foi possível medir")
    partes.append(f"{r['num_cpus_logicos']} CPUs lógicos disponíveis")
    return ResultadoChecagem("Uso de recursos deste processo", True, ", ".join(partes))


def checar_saude_sistema() -> List[ResultadoChecagem]:
    """
    Seção 39: visão objetiva por componente — nunca uma pontuação arbitrária,
    só OK / ATENÇÃO / ERRO / NÃO TESTADO / DESATIVADO. `ok=None` é usado aqui
    como o estado "NÃO TESTADO / DESATIVADO" (nem sucesso nem falha).
    """
    resultados = [checar_python(), *checar_dependencias(), checar_configuracao(), checar_espaco_em_disco(), checar_tamanho_dados(), checar_recursos()]

    marcador = verificar_encerramento_anterior()
    if marcador:
        resultados.append(ResultadoChecagem(
            "Encerramento da execução anterior", False,
            f"A execução anterior (iniciada em {marcador.get('inicio', '?')}, modo {marcador.get('modo', '?')}) "
            "não foi encerrada normalmente. Isso NÃO significa que uma matrícula foi confirmada — "
            "verifique manualmente no SIGAA se tiver dúvida.",
        ))
    else:
        resultados.append(ResultadoChecagem("Encerramento da execução anterior", True, "Normal (ou o programa ainda não rodou o motor nesta instalação)"))

    return resultados


def gerar_relatorio_texto(resultados: List[ResultadoChecagem]) -> str:
    linhas = [f"Relatório de Diagnóstico — SIGAA Sniper v{VERSAO_APP}", "=" * 50, ""]
    problemas = 0
    for r in resultados:
        if r.ok is False:
            problemas += 1
        marca = {"True": "✅", "False": "❌", "None": "⚪"}[str(r.ok)]
        linhas.append(f"{marca} {r.nome}: {r.detalhe}")
    linhas.append("")
    linhas.append(f"DIAGNÓSTICO CONCLUÍDO — {problemas} problema(s) encontrado(s)")
    linhas.append("(este relatório não contém credenciais nem tokens)")
    return "\n".join(linhas)
