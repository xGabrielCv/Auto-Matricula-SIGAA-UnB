"""
Modo terminal — seções 22-24 do pedido: navegação só por números, sem
parâmetros de linha de comando, sem eco de senha, sem salvar credenciais.
"""
from __future__ import annotations

import asyncio
import getpass
import os
import sys

from app.core.config import (
    Disciplina, aplicar_segredos_notificacao_salvos, carregar_disciplinas,
    carregar_settings, salvar_disciplinas, salvar_settings, validar_disciplinas, validar_settings,
)
from app.core.disclaimer import CONFIRMACOES, TEXTO_COMPLETO
from app.core.departamentos import buscar_departamentos, codigo_conhecido
from app.core.diagnostics import VERSAO_APP
from app.core.credentials import encerrar_sessao, obter_sessao
from app.core.diagnostics import (
    checar_conectividade_sigaa, checar_configuracao, checar_dependencias,
    checar_espaco_em_disco, checar_modo_execucao, checar_python, checar_tamanho_dados, gerar_relatorio_texto,
)
from app.core.factory import construir_motor
from app.utils.cleanup import limpar_debug_dumps


def limpar_tela():
    os.system("cls" if os.name == "nt" else "clear")


def cabecalho(titulo: str):
    limpar_tela()
    print("=" * 44)
    print(f"{'SIGAA SNIPER':^44}")
    print(f"{('v' + VERSAO_APP):^44}")
    print("=" * 44)
    if titulo:
        print(f"\n{titulo}\n")


def pausar():
    input("\nPressione ENTER para continuar...")


def mostrar_aviso_legal() -> bool:
    """
    Aviso legal obrigatório (seção 94.8/94.12) — aparece em TODA execução do
    terminal, sem exceção, e não é lembrado entre execuções (nada disso é
    salvo em disco). Devolve True se o usuário aceitou todos os termos.
    """
    while True:
        cabecalho("⚠️  Aviso Legal e Termo de Responsabilidade")
        print("Este software é uma prova de conceito para fins educacionais e de")
        print("pesquisa em engenharia de software — sem vínculo oficial com a UnB/SIGAA.")
        print("Automação pode violar normas institucionais e resultar em bloqueios.")
        print("Você é o único responsável pelo uso. Evite requisições abusivas.\n")
        print("Para continuar, é preciso confirmar TODOS os pontos abaixo:\n")
        for i, (_chave, texto) in enumerate(CONFIRMACOES, start=1):
            print(f"  {i}. {texto}\n")

        print("[1] Aceito todos os termos acima e quero continuar")
        print("[2] Ver o texto completo do disclaimer")
        print("[3] Sair")
        escolha = input("\nEscolha: ").strip()

        if escolha == "1":
            return True
        elif escolha == "2":
            cabecalho("Disclaimer completo")
            print(TEXTO_COMPLETO)
            pausar()
        elif escolha == "3":
            return False
        else:
            print("Opção inválida.")
            pausar()


def _avisar_encerramento_anterior():
    """Seção 54 — mesma lógica da GUI, adaptada ao terminal."""
    from app.core.crash_recovery import verificar_encerramento_anterior
    marcador = verificar_encerramento_anterior()
    if marcador:
        cabecalho("⚠️  Execução anterior não finalizada normalmente")
        print(f"A execução anterior do motor (iniciada em {marcador.get('inicio', '?')}, modo: {marcador.get('modo', '?')})")
        print("não foi encerrada de forma controlada — o programa pode ter sido fechado")
        print("abruptamente ou travado.\n")
        print("Isso NÃO significa que uma matrícula foi confirmada. Se tiver dúvida,")
        print("verifique manualmente no SIGAA.")
        pausar()


def menu_principal():
    if not mostrar_aviso_legal():
        print("\nVocê optou por não aceitar os termos. Encerrando.")
        sys.exit(0)

    limpar_debug_dumps(manter=carregar_settings()["logs"]["arquivos_mantidos"])
    # Mesmo comportamento da GUI: segredos de notificação salvos (opt-in) são
    # carregados na sessão — antes o terminal os ignorava silenciosamente.
    aplicar_segredos_notificacao_salvos(obter_sessao().notificacao)
    _avisar_encerramento_anterior()
    while True:
        cabecalho("")
        print("[0] 🌐 Interface Web  ★ RECOMENDADO — abre no navegador")
        print("[1] Interface gráfica")
        print("[2] Matrícula automática")
        print("[3] Somente monitoramento")
        print("[4] Configurações")
        print("[5] Diagnóstico")
        print("[6] Sair")
        escolha = input("\nEscolha: ").strip()

        if escolha == "0":
            from app.web.server import executar_interface_web
            executar_interface_web()
        elif escolha == "1":
            from app.gui.app import main as gui_main
            gui_main()
        elif escolha == "2":
            fluxo_execucao("matricula")
        elif escolha == "3":
            fluxo_execucao("monitoramento")
        elif escolha == "4":
            menu_configuracoes()
        elif escolha == "5":
            menu_diagnostico()
        elif escolha == "6":
            encerrar_sessao()
            print("\nEncerrando. Credenciais apagadas da memória. Até mais!")
            sys.exit(0)
        else:
            print("Opção inválida.")
            pausar()


# ── Credenciais (nunca salvas) ──────────────────────────────────────────

def pedir_credenciais():
    sessao = obter_sessao()
    cabecalho("Credenciais do SIGAA")
    print("Suas credenciais NÃO são salvas em nenhum arquivo — só ficam em")
    print("memória durante esta execução e são apagadas ao sair.\n")

    sessao.sigaa.usuario = input("Matrícula: ").strip()
    sessao.sigaa.senha = getpass.getpass("Senha (não aparece na tela): ")
    sessao.sigaa.cpf = input("CPF (somente números): ").strip()
    sessao.sigaa.nascimento = input("Data de nascimento (DD/MM/AAAA): ").strip()


# ── Departamento (busca) ─────────────────────────────────────────────────

def pedir_departamento() -> int:
    """Busca por nome em vez de exigir que o usuário já saiba o número de cor.
    Seções 11-15: o código pode mudar, então sempre avisamos quando não é
    reconhecido em vez de aceitar cegamente."""
    print(
        "\nAtenção: o código do departamento pode mudar — quem define esse número é\n"
        "o SIGAA, não este programa. Se parar de funcionar, consulte\n"
        "https://sigaa.unb.br/sigaa/public/turmas/listar.jsf (ver docs/GUIA_DE_USO.md).\n"
    )
    termo = input("Digite o nome (ou parte) do departamento, ou o código se já souber: ").strip()
    if not termo:
        return 0

    if termo.isdigit():
        codigo = int(termo)
        if not codigo_conhecido(codigo):
            print(f"⚠️  Código {codigo} não está na lista de referência conhecida (pode ser novo, ou a lista desatualizada).")
            if input("Usar mesmo assim? [s/N]: ").strip().lower() != "s":
                return 0
        return codigo

    encontrados = buscar_departamentos(termo)[:15]
    if not encontrados:
        print("Nenhum departamento encontrado com esse termo.")
        return 0

    for i, d in enumerate(encontrados, start=1):
        print(f"[{i}] {d.codigo} — {d.nome}")
    escolha = input("\nEscolha o número do departamento (ENTER para cancelar): ").strip()
    if escolha.isdigit() and 1 <= int(escolha) <= len(encontrados):
        return encontrados[int(escolha) - 1].codigo
    return 0


# ── Disciplinas ──────────────────────────────────────────────────────────

def menu_disciplinas():
    disciplinas = carregar_disciplinas()
    while True:
        cabecalho("Disciplinas configuradas")
        if not disciplinas:
            print("(nenhuma disciplina cadastrada ainda)\n")
        for i, d in enumerate(disciplinas, start=1):
            status = "ativa" if d.ativa else "inativa"
            print(f"[{i}] {d.codigo} — Turma {d.turma} (depto {d.departamento}) [{status}]")

        print(f"\n[{len(disciplinas) + 1}] Adicionar disciplina")
        print(f"[{len(disciplinas) + 2}] Remover disciplina")
        print(f"[{len(disciplinas) + 3}] Ativar/Desativar disciplina")
        print(f"[{len(disciplinas) + 4}] Continuar")

        escolha = input("\nEscolha: ").strip()
        if not escolha.isdigit():
            continue
        n = int(escolha)

        if n == len(disciplinas) + 1:
            codigo = input("Código da disciplina (ex: FGA0211): ").strip().upper()
            turma = input("Turma (ex: 01): ").strip()
            depto = pedir_departamento()
            if codigo and turma and depto:
                disciplinas.append(Disciplina(codigo=codigo, turma=turma, departamento=depto))
                salvar_disciplinas(disciplinas)
        elif n == len(disciplinas) + 2:
            idx = input("Número da disciplina a remover: ").strip()
            if idx.isdigit() and 1 <= int(idx) <= len(disciplinas):
                disciplinas.pop(int(idx) - 1)
                salvar_disciplinas(disciplinas)
        elif n == len(disciplinas) + 3:
            idx = input("Número da disciplina para ativar/desativar: ").strip()
            if idx.isdigit() and 1 <= int(idx) <= len(disciplinas):
                disciplinas[int(idx) - 1].ativa = not disciplinas[int(idx) - 1].ativa
                salvar_disciplinas(disciplinas)
        elif n == len(disciplinas) + 4:
            return disciplinas


# ── Execução (matrícula ou monitoramento) ───────────────────────────────

def fluxo_execucao(modo: str):
    sessao = obter_sessao()
    if not sessao.sigaa.preenchida():
        pedir_credenciais()

    disciplinas = menu_disciplinas()
    if not any(d.ativa for d in disciplinas):
        print("\nNenhuma disciplina ativa. Volte ao menu de disciplinas e ative pelo menos uma.")
        pausar()
        return

    settings = carregar_settings()
    settings["modo"] = modo

    if modo == "matricula":
        cabecalho("Modo Matrícula Automática")
        resposta = input("Ativar modo de teste (DRY RUN — não confirma matrícula de verdade)? [S/n]: ").strip().lower()
        settings["dry_run"] = resposta != "n"
    else:
        cabecalho("Modo Somente Monitoramento")
        print("Este modo apenas avisa quando encontrar vaga — nunca tenta matricular sozinho.")
        settings["dry_run"] = True

    problemas = validar_settings(settings) + validar_disciplinas(disciplinas)
    if problemas:
        print("\nConfiguração inválida — corrija antes de iniciar:")
        for p in problemas:
            print(f"  • {p}")
        pausar()
        return

    salvar_settings(settings)

    print("\nIniciando... pressione Ctrl+C para parar.\n")
    motor = construir_motor(settings, sessao, disciplinas)
    try:
        asyncio.run(motor.executar())
    except KeyboardInterrupt:
        motor.parar()
        print("\nParado pelo usuário.")
    pausar()


# ── Configurações ────────────────────────────────────────────────────────

def menu_configuracoes():
    while True:
        cabecalho("Configurações")
        print("[1] Credenciais do SIGAA")
        print("[2] Disciplinas")
        print("[3] Notificações (Telegram / ntfy / alarme)")
        print("[4] Configurações avançadas (workers, intervalos, logs)")
        print("[5] Sobre / Repositório oficial / Criar atalho")
        print("[6] Experimental (recursos alternativos dos legados)")
        print("[7] Voltar")
        escolha = input("\nEscolha: ").strip()

        if escolha == "1":
            pedir_credenciais()
            pausar()
        elif escolha == "2":
            menu_disciplinas()
        elif escolha == "3":
            menu_notificacoes()
        elif escolha == "4":
            menu_avancado()
        elif escolha == "5":
            menu_sobre()
        elif escolha == "6":
            menu_experimental()
        elif escolha == "7":
            return


def menu_experimental():
    from app.experimental import listar_experimentos

    while True:
        cabecalho("⚠️  Área Experimental")
        print("Recursos alternativos encontrados nas versões antigas do projeto.")
        print("Não fazem parte do caminho principal validado — use só para testar.\n")

        experimentos = listar_experimentos()
        for i, exp in enumerate(experimentos, start=1):
            print(f"[{i}] {exp.nome}  [{exp.status}]")
        print(f"[{len(experimentos) + 1}] Voltar")

        escolha = input("\nEscolha: ").strip()
        if not escolha.isdigit():
            continue
        n = int(escolha)
        if n == len(experimentos) + 1:
            return
        if 1 <= n <= len(experimentos):
            exp = experimentos[n - 1]
            cabecalho(exp.nome)
            print(exp.descricao + "\n")
            print(f"Origem: {exp.origem}")
            print(f"Dependências: {', '.join(exp.dependencias) or 'nenhuma'}")
            print(f"Riscos/limitações: {exp.riscos}\n")
            print("[1] Executar (com confirmação)")
            print("[2] Ver guia de instalação")
            print("[3] Voltar")
            sub = input("\nEscolha: ").strip()
            if sub == "1":
                if input("\nTem certeza que quer executar este recurso experimental? [s/N]: ").strip().lower() == "s":
                    if exp.executar:
                        try:
                            print("\n" + exp.executar())
                        except Exception as e:
                            print(f"\n❌ O experimento falhou (isso é esperado às vezes): {e}")
                pausar()
            elif sub == "2":
                print("\n" + (exp.guia_instalacao or "Nenhuma instalação adicional necessária."))
                pausar()


def menu_notificacoes():
    import asyncio as _asyncio
    from app.notifications.alarm import testar_alarme
    from app.notifications.ntfy import testar_ntfy
    from app.notifications.telegram import testar_telegram

    settings = carregar_settings()
    sessao = obter_sessao()
    cfg = settings["notificacoes"]

    while True:
        cabecalho("Notificações (opcional — o programa funciona sem nenhuma)")
        print(f"[1] Telegram: {'ATIVO' if cfg['telegram_ativo'] else 'desativado'}")
        print(f"[2] ntfy: {'ATIVO' if cfg['ntfy_ativo'] else 'desativado'}")
        print(f"[3] Alarme sonoro: {'ATIVO' if cfg['alarme_ativo'] else 'desativado'}")
        print("[4] Testar canais habilitados")
        print("[5] Salvar e voltar")
        escolha = input("\nEscolha: ").strip()

        if escolha == "1":
            cfg["telegram_ativo"] = not cfg["telegram_ativo"]
            if cfg["telegram_ativo"]:
                sessao.notificacao.telegram_token = input("Bot Token: ").strip()
                sessao.notificacao.telegram_chat_id = input("Chat ID: ").strip()
        elif escolha == "2":
            cfg["ntfy_ativo"] = not cfg["ntfy_ativo"]
            if cfg["ntfy_ativo"]:
                sessao.notificacao.ntfy_topic = input("Tópico do ntfy: ").strip()
        elif escolha == "3":
            cfg["alarme_ativo"] = not cfg["alarme_ativo"]
        elif escolha == "4":
            print()
            if cfg["telegram_ativo"] and sessao.notificacao.telegram_configurado():
                try:
                    _asyncio.run(testar_telegram(sessao.notificacao.telegram_token, sessao.notificacao.telegram_chat_id))
                    print("Telegram: OK")
                except Exception as e:
                    print(f"Telegram: falhou ({e})")
            if cfg["ntfy_ativo"] and sessao.notificacao.ntfy_configurado():
                try:
                    _asyncio.run(testar_ntfy(sessao.notificacao.ntfy_topic, sessao.notificacao.ntfy_servidor))
                    print("ntfy: OK")
                except Exception as e:
                    print(f"ntfy: falhou ({e})")
            if cfg["alarme_ativo"]:
                try:
                    _asyncio.run(testar_alarme(cfg["alarme"]["repeticoes"], min(3, cfg["alarme"]["duracao_seg"])))
                    print("Alarme: OK (tocado)")
                except Exception as e:  # ex: computador sem dispositivo de som
                    print(f"Alarme: falhou ({e})")
            pausar()
        elif escolha == "5":
            salvar_settings(settings)
            return


def menu_sobre():
    from app.core.shortcut import GUIA_MANUAL, criar_atalho_area_trabalho, suportado

    while True:
        cabecalho("Sobre / Repositório oficial")
        print(f"SIGAA Sniper v{VERSAO_APP}\n")
        print("Este é um pacote distribuível do projeto. Para atualizações, correções,")
        print("melhorias e versões futuras, consulte o repositório oficial:\n")
        print("  https://github.com/xGabrielCv/Auto-Matricula-SIGAA-UnB\n")
        print("O projeto é open source. Sugestões e relatos de bugs são bem-vindos,")
        print("preferencialmente pelo GitHub (issues/discussions).\n")
        print("[1] Criar atalho na Área de Trabalho")
        print("[2] Voltar")
        escolha = input("\nEscolha: ").strip()

        if escolha == "1":
            if not suportado():
                print("\nCriação automática só é suportada no Windows.")
                print(GUIA_MANUAL)
            else:
                try:
                    caminho = criar_atalho_area_trabalho()
                    print(f"\n✅ Atalho criado em: {caminho}")
                except Exception as e:
                    print(f"\n❌ Não foi possível criar automaticamente ({e}).")
                    print(GUIA_MANUAL)
            pausar()
        elif escolha == "2":
            return


def menu_avancado():
    settings = carregar_settings()
    cabecalho("Configurações Avançadas")
    print(f"Workers atuais: {settings['num_workers']}")
    novo = input("Novo número de workers (ENTER para manter): ").strip()
    if novo.isdigit():
        settings["num_workers"] = int(novo)

    print(f"\nIntervalo de busca atual (segundos): {settings['intervalo_busca']}")
    novo = input("Novo intervalo (ENTER para manter): ").strip()
    try:
        if novo:
            settings["intervalo_busca"] = float(novo)
    except ValueError:
        pass

    print(f"\nTimeout de requisição atual (segundos): {settings['timeout_req']}")
    novo = input("Novo timeout (ENTER para manter): ").strip()
    if novo.isdigit():
        settings["timeout_req"] = int(novo)

    salvar_settings(settings)
    print("\nSalvo.")
    pausar()


# ── Diagnóstico ──────────────────────────────────────────────────────────

def menu_diagnostico():
    from app.core.diagnostics import checar_conectividade_em_camadas, checar_saude_sistema

    while True:
        cabecalho("Diagnóstico")
        print("[1] Diagnóstico completo")
        print("[2] Testar conectividade em camadas (Internet → SIGAA → ...)")
        print("[3] Voltar")
        escolha = input("\nEscolha: ").strip()

        if escolha == "1":
            print("\nRodando verificações...\n")
            resultados = [*checar_saude_sistema(), checar_modo_execucao()]
            try:
                resultados.append(asyncio.run(checar_conectividade_sigaa()))
            except Exception:
                pass
            print(gerar_relatorio_texto(resultados))
            pausar()
        elif escolha == "2":
            print("\nTestando cada camada...\n")
            resultados = asyncio.run(checar_conectividade_em_camadas())
            print(gerar_relatorio_texto(resultados))
            pausar()
        elif escolha == "3":
            return


if __name__ == "__main__":
    menu_principal()
