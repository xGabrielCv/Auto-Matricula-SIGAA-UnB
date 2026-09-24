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
    PRESETS_CARGA, Disciplina, analisar_disciplina, aplicar_segredos_notificacao_salvos, carregar_disciplinas,
    existe_segredos_notificacao_salvos,
    carregar_settings, estimar_carga, interpretar_lote, salvar_disciplinas, salvar_settings, validar_disciplinas,
    validar_settings,
)
from app.core.disclaimer import CONFIRMACOES, TEXTO_COMPLETO
from app.core.departamentos import buscar_departamentos, codigo_conhecido
from app.versao import URL_REPOSITORIO, VERSAO_APP
from app.core.credentials import encerrar_sessao, normalizar_nascimento, obter_sessao
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
    from app.core import auditoria
    auditoria.definir_origem("terminal")
    if not mostrar_aviso_legal():
        auditoria.registrar("aviso_recusado")
        print("\nVocê optou por não aceitar os termos. Encerrando.")
        sys.exit(0)
    auditoria.registrar_aceite_aviso()

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
        print("[7] 🎓 Demonstração (SIGAA simulado, sem login — para aprender e testar notificações)")
        print("[6] Sair")
        escolha = input("\nEscolha: ").strip()

        if escolha == "7":
            fluxo_demonstracao()
        elif escolha == "0":
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
    while True:
        from app.core.validadores import normalizar_cpf
        sessao.sigaa.cpf = normalizar_cpf(input("CPF (com ou sem pontos, ex: 123.456.789-09): "))
        sessao.sigaa.nascimento = normalizar_nascimento(input("Data de nascimento — DD/MM/AAAA (ex: 01/02/2003): "))
        problemas = sessao.sigaa.problemas()
        if not problemas:
            from app.core import auditoria
            auditoria.registrar("credenciais_preenchidas")
            return
        # Mesma regra da GUI e da Web: com CPF/data errados, cada vaga viraria
        # uma confirmação recusada pelo SIGAA.
        print("\n⚠️  Confira os dados:")
        for p in problemas:
            print(f"  • {p}")
        if input("\nDigitar CPF e data de novo? [S/n]: ").strip().lower() == "n":
            print("A execução não será iniciada enquanto houver problema nas credenciais.")
            return


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
    termo = input("Código do departamento, parte do nome para buscar, ou L para ver a lista completa: ").strip()
    if not termo:
        return 0
    if termo.lower() == "l":
        return _listar_departamentos_paginado()

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


def _listar_departamentos_paginado() -> int:
    """Desde a 6.1.0: a lista completa, 20 por página, escolhida pelo número."""
    from app.core.departamentos import info_lista, listar_departamentos
    todos = listar_departamentos()
    print(f"\n{info_lista()['texto']}")
    inicio = 0
    while True:
        pagina = todos[inicio:inicio + 20]
        for i, d in enumerate(pagina, start=inicio + 1):
            print(f"[{i:>3}] {d.codigo:>5} — {d.nome}")
        opcoes = "número para escolher" + (" · ENTER próxima página" if inicio + 20 < len(todos) else "") + " · V voltar"
        escolha = input(f"\n{opcoes}: ").strip().lower()
        if escolha == "v":
            return 0
        if not escolha:
            if inicio + 20 >= len(todos):
                return 0
            inicio += 20
            continue
        if escolha.isdigit() and 1 <= int(escolha) <= len(todos):
            d = todos[int(escolha) - 1]
            print(f"✔ {d.codigo} — {d.nome}")
            return d.codigo


def _pedir_grupo_e_prioridade(grupo_atual: str = "", prioridade_atual: str = "normal") -> tuple:
    """Grupo e prioridade com ajuda sob demanda (digite ? para ver como funciona)."""
    from app.core.textos import RESUMO_GRUPO, RESUMO_PRIORIDADE, TEXTO_AJUDA_GRUPO, TEXTO_AJUDA_PRIORIDADE
    print(f"\nGrupo de alternativas: {RESUMO_GRUPO}")
    while True:
        grupo = input(f"Grupo (ENTER = {grupo_atual or 'nenhum'}, - = nenhum, ? = como funciona): ").strip()
        if grupo == "?":
            print("\n" + TEXTO_AJUDA_GRUPO + "\n")
            continue
        grupo = "" if grupo == "-" else (grupo[:40] or grupo_atual)
        break
    print(f"Prioridade: {RESUMO_PRIORIDADE}")
    while True:
        p = input(f"Prioridade [a]lta / [n]ormal / [b]aixa (ENTER = {prioridade_atual}, ? = como funciona): ").strip().lower()
        if p == "?":
            print("\n" + TEXTO_AJUDA_PRIORIDADE + "\n")
            continue
        return grupo, {"a": "alta", "b": "baixa", "n": "normal"}.get(p[:1], prioridade_atual)


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
        print(f"[{len(disciplinas) + 5}] Adicionar várias de uma vez (colar lista)")
        print(f"[{len(disciplinas) + 6}] Editar disciplina")

        escolha = input("\nEscolha: ").strip()
        if not escolha.isdigit():
            continue
        n = int(escolha)

        if n == len(disciplinas) + 1:
            codigo = input("Código da disciplina (ex: FGA0211): ").strip().upper()
            turma = input("Turma (ex: 01): ").strip()
            depto = pedir_departamento()
            grupo, prioridade = _pedir_grupo_e_prioridade()
            if codigo and turma and depto:
                nova = Disciplina(codigo=codigo, turma=turma, departamento=depto, grupo=grupo, prioridade=prioridade)
                if _confirmar_disciplina(nova, disciplinas):
                    disciplinas.append(nova)
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
        elif n == len(disciplinas) + 5:
            novas = cadastrar_em_lote(disciplinas)
            if novas:
                disciplinas.extend(novas)
                salvar_disciplinas(disciplinas)
        elif n == len(disciplinas) + 6:
            idx = input("Número da disciplina a editar: ").strip()
            if idx.isdigit() and 1 <= int(idx) <= len(disciplinas):
                _editar_disciplina(disciplinas, int(idx) - 1)


def _editar_disciplina(disciplinas, i: int) -> None:
    """Sugestão 013: editar pelo terminal (ENTER mantém cada campo)."""
    d = disciplinas[i]
    print("\nENTER mantém o valor atual.")
    codigo = input(f"Código [{d.codigo}]: ").strip().upper() or d.codigo
    turma = input(f"Turma [{d.turma}]: ").strip() or d.turma
    trocar = input(f"Departamento [{d.departamento}] — trocar? (s/N): ").strip().lower() == "s"
    depto = pedir_departamento() if trocar else d.departamento
    grupo, prioridade = _pedir_grupo_e_prioridade(d.grupo, d.prioridade)
    nova = Disciplina(codigo=codigo, turma=turma, departamento=depto, ativa=d.ativa, professor=d.professor,
                      grupo=grupo, prioridade=prioridade)
    outras = disciplinas[:i] + disciplinas[i + 1:]
    if _confirmar_disciplina(nova, outras):
        disciplinas[i] = nova
        salvar_disciplinas(disciplinas)
        print(f"✅ {nova.chave()} atualizada.")
        pausar()


def _confirmar_disciplina(nova: Disciplina, existentes) -> bool:
    """Mesma regra da GUI e da Web: erros impedem salvar, avisos pedem confirmação.
    O aviso de departamento desconhecido já foi confirmado em pedir_departamento()."""
    erros, avisos = analisar_disciplina(nova, existentes)
    avisos = [a for a in avisos if "código de departamento" not in a]
    if erros:
        print()
        for e in erros:
            print(f"❌ {e}")
        pausar()
        return False
    if avisos:
        print()
        for a in avisos:
            print(f"⚠️  {a}")
        return input("\nSalvar mesmo assim? [s/N]: ").strip().lower() == "s"
    return True


def cadastrar_em_lote(existentes):
    """Sugestão 005 no terminal: colar várias linhas, ver a prévia e confirmar."""
    from app.core.textos import TEXTO_AJUDA_LOTE
    cabecalho("Adicionar várias disciplinas")
    print(TEXTO_AJUDA_LOTE)
    print("\nCole as linhas abaixo e termine com uma linha vazia:\n")
    linhas = []
    while True:
        linha = input()
        if not linha.strip():
            break
        linhas.append(linha)
    itens = interpretar_lote("\n".join(linhas), existentes)
    if not itens:
        print("Nenhuma linha informada.")
        pausar()
        return []
    print("\nPré-visualização:")
    for it in itens:
        rotulo = it["disciplina"].chave() if it["disciplina"] else it["texto"]
        if it["erros"]:
            print(f"  ❌ linha {it['linha']}: {rotulo} — {it['erros'][0]}")
        elif it["avisos"]:
            print(f"  ⚠️  linha {it['linha']}: {rotulo} — {it['avisos'][0]}")
        else:
            print(f"  ✅ linha {it['linha']}: {rotulo}")
    validos = [it["disciplina"] for it in itens if it["disciplina"] and not it["erros"]]
    if not validos:
        print("\nNenhuma linha válida para adicionar.")
        pausar()
        return []
    if input(f"\nAdicionar {len(validos)} disciplina(s) válida(s)? [s/N]: ").strip().lower() != "s":
        return []
    return validos


# ── Execução (matrícula ou monitoramento) ───────────────────────────────

def fluxo_demonstracao():
    """Sugestão 077: o fluxo inteiro contra um SIGAA simulado (nenhuma requisição sai do computador)."""
    cabecalho("🎓 Demonstração — SIGAA simulado")
    print("Nada aqui fala com o SIGAA de verdade: login, busca e matrícula são simulados neste")
    print("computador. As credenciais são fictícias, o DRY RUN fica sempre ligado e nada vai para")
    print("o histórico. Vagas aparecem ao acaso. Notificações ligadas chegam com [DEMONSTRAÇÃO].\n")
    settings = carregar_settings()
    disciplinas = carregar_disciplinas()
    if not any(d.ativa for d in disciplinas):
        print("(sem disciplinas ativas — usando FGA0211-01 e MAT0025-02 de exemplo)")
    modo = input("[1] Matrícula automática (DRY RUN) · [2] Somente monitoramento (ENTER = 1): ").strip()
    settings["modo"] = "monitoramento" if modo == "2" else "matricula"
    print("\nDurante a execução: [Q] parar · [D] painel/linhas de log · [P] pausar/retomar")
    input("Pressione ENTER para iniciar a demonstração...")
    from app.terminal.acompanhamento import acompanhar_execucao
    motor = construir_motor(settings, obter_sessao(), disciplinas, demo=True)
    erro = acompanhar_execucao(motor)
    print(f"\n❌ A demonstração terminou com erro: {erro}" if erro else "\nDemonstração encerrada.")
    if getattr(motor, "resumo", None):
        from app.core.relatorios import texto_relatorio
        print("\n" + texto_relatorio(motor.resumo))
        print("\n(demonstração: este resumo não foi guardado no histórico)")
    pausar()


def fluxo_execucao(modo: str):
    sessao = obter_sessao()
    if not sessao.sigaa.preenchida() or sessao.sigaa.problemas():
        pedir_credenciais()
    problemas_cred = sessao.sigaa.problemas()
    if not sessao.sigaa.preenchida() or problemas_cred:
        print("\nCredenciais incompletas ou com problema — corrija em Configurações → Credenciais:")
        for p in problemas_cred:
            print(f"  • {p}")
        pausar()
        return

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

    carga = estimar_carga(settings["num_workers"], settings["intervalo_busca"], sum(1 for d in disciplinas if d.ativa),
                          settings.get("protecao", {}).get("limite_req_por_seg", 0))
    print(f"\nCarga estimada: {carga['texto']}")
    if carga["alerta"]:
        print(f"⚠️  {carga['alerta']}")
    print("\nDurante a execução: [Q] parar com segurança · [D] alternar painel/linhas de log")
    input("Pressione ENTER para iniciar...")

    from app.terminal.acompanhamento import acompanhar_execucao
    motor = construir_motor(settings, sessao, disciplinas)
    erro = acompanhar_execucao(motor)
    if erro:
        print(f"\n❌ A execução terminou com erro: {erro}")
    else:
        print("\nExecução encerrada.")
    if getattr(motor, "resumo", None):
        from app.core.relatorios import texto_relatorio
        print("\n" + texto_relatorio(motor.resumo))
        print("\n(uma cópia deste resumo fica em data/relatorios/)")
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
        print("[8] Término automático, janela diária, relógio do SIGAA e verificação prévia")
        print("[9] Perfis (cenários prontos de configuração)")
        print("[10] Atualizar a lista de departamentos (página pública do SIGAA)")
        print("[11] Exportar / importar configuração (backup, sem credenciais)")
        print("[12] Restaurar configurações padrão")
        print("[13] Interface Web e arquivos de log")
        print("[7] Voltar")
        escolha = input("\nEscolha: ").strip()

        if escolha == "8":
            menu_agendamento()
        elif escolha == "9":
            menu_perfis()
        elif escolha == "11":
            menu_exportar_importar()
        elif escolha == "12":
            menu_restaurar_padroes()
        elif escolha == "13":
            menu_web_e_logs()
        elif escolha == "10":
            from app.core.departamentos import atualizar_departamentos, info_lista
            print("\nConsultando a página pública do SIGAA (sem login)...")
            try:
                r = atualizar_departamentos()
                print(f"✅ Lista atualizada: {r['quantidade']} unidades ({r['novos']} nova(s), {r['removidos']} removida(s)).")
            except ValueError as e:
                print(f"❌ {e}")
            print(info_lista()["texto"])
            pausar()
        elif escolha == "1":
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


def menu_agendamento():
    """Fase 4 no terminal: término (035), janela diária (035), relógio do SIGAA (038), verificação prévia (040)."""
    from app.core.regras import DIAS, descrever_janela
    settings = carregar_settings()
    janela = dict(settings.get("janela") or {})
    cabecalho("Término, janela, relógio e verificação prévia")
    print(f"Término automático atual: {settings.get('agendar_fim') or 'nenhum'}")
    print(f"Janela diária atual: {descrever_janela(janela)}")
    print(f"Relógio do SIGAA no agendamento: {'sim' if settings.get('agendamento_relogio_sigaa') else 'não'}")
    print(f"Verificação prévia: {'sim' if settings.get('verificacao_previa', True) else 'não'}\n")
    fim = input("Encerrar automaticamente em (DD/MM/AAAA HH:MM:SS, '-' para nenhum, ENTER mantém): ").strip()
    if fim == "-":
        settings["agendar_fim"] = None
    elif fim:
        settings["agendar_fim"] = fim
    resposta = input("Rodar só numa janela diária? [s/n, ENTER mantém]: ").strip().lower()
    if resposta in ("s", "n"):
        janela["ativa"] = resposta == "s"
    if janela.get("ativa"):
        janela["inicio"] = input(f"Início (HH:MM) [{janela.get('inicio', '07:00')}]: ").strip() or janela.get("inicio", "07:00")
        janela["fim"] = input(f"Fim (HH:MM) [{janela.get('fim', '23:00')}]: ").strip() or janela.get("fim", "23:00")
        texto_dias = input("Dias (ex: seg,ter,qua,qui,sex; ENTER mantém): ").strip().lower()
        if texto_dias:
            janela["dias"] = sorted({DIAS.index(d.strip()[:3]) for d in texto_dias.split(",") if d.strip()[:3] in DIAS})
    settings["janela"] = {**{"ativa": False, "inicio": "07:00", "fim": "23:00", "dias": list(range(7))}, **janela}
    resposta = input("Agendar pelo relógio do SIGAA? [s/n, ENTER mantém]: ").strip().lower()
    if resposta in ("s", "n"):
        settings["agendamento_relogio_sigaa"] = resposta == "s"
    resposta = input("Verificar login e disciplinas antes de começar? [s/n, ENTER mantém]: ").strip().lower()
    if resposta in ("s", "n"):
        settings["verificacao_previa"] = resposta == "s"
    problemas = validar_settings(settings)
    if problemas:
        print("\nNão salvo — corrija:")
        for p in problemas:
            print(f"  • {p}")
    else:
        salvar_settings(settings)
        print(f"\nSalvo. Janela: {descrever_janela(settings['janela'])}.")
    pausar()


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
        print(f"[7] Notificação do Windows: {'ATIVA' if cfg.get('windows_ativo') else 'desativada'}")
        print(f"[8] Webhook (Discord/Slack/JSON): {'ATIVO' if cfg.get('webhook_ativo') else 'desativado'}")
        print(f"[9] E-mail (SMTP): {'ATIVO' if cfg.get('email_ativo') else 'desativado'}")
        print("[4] Testar canais habilitados")
        print("[6] Quais eventos notificar e resumo periódico")
        print(f"[10] Guardar os tokens/senhas neste computador ({'salvos' if existe_segredos_notificacao_salvos() else 'não salvos'})")
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
                servidor = input(f"Servidor do ntfy (ENTER = {sessao.notificacao.ntfy_servidor}): ").strip()
                if servidor.startswith("https://"):
                    sessao.notificacao.ntfy_servidor = servidor
        elif escolha == "3":
            cfg["alarme_ativo"] = not cfg["alarme_ativo"]
        elif escolha == "10":
            from app.core.cofre import descricao_armazenamento
            from app.core.config import apagar_segredos_notificacao, salvar_segredos_notificacao
            if existe_segredos_notificacao_salvos():
                if input("Apagar os tokens/senhas salvos neste computador? (s/N): ").strip().lower() == "s":
                    apagar_segredos_notificacao()
                    print("✅ Apagados.")
            else:
                print(f"\nOs segredos de notificação serão {descricao_armazenamento()}.")
                if input("Guardar neste computador? (s/N): ").strip().lower() == "s":
                    n = sessao.notificacao
                    salvar_segredos_notificacao(n.telegram_token, n.telegram_chat_id, n.ntfy_topic, n.ntfy_servidor,
                                                n.webhook_url, n.email_senha)
                    print("✅ Guardados.")
            pausar()
        elif escolha == "7":
            cfg["windows_ativo"] = not cfg.get("windows_ativo", False)
        elif escolha == "8":
            cfg["webhook_ativo"] = not cfg.get("webhook_ativo", False)
            if cfg["webhook_ativo"]:
                formato = input("Formato [D]iscord, [S]lack ou [J]SON (ENTER = Discord): ").strip().lower()
                cfg["webhook_formato"] = {"s": "slack", "j": "json"}.get(formato, "discord")
                from app.core.textos import TEXTO_AJUDA_WEBHOOK
                from app.core.validadores import problema_url_webhook
                url = input("URL do webhook (https://…, fica só em memória; ? = como configurar): ").strip()
                if url == "?":
                    print("\n" + TEXTO_AJUDA_WEBHOOK + "\n")
                    url = input("URL do webhook: ").strip()
                if problema_url_webhook(url):
                    print(f"❌ {problema_url_webhook(url)} Webhook desativado.")
                    cfg["webhook_ativo"] = False
                    pausar()
                else:
                    sessao.notificacao.webhook_url = url
        elif escolha == "9":
            cfg["email_ativo"] = not cfg.get("email_ativo", False)
            if cfg["email_ativo"]:
                email = {**{"servidor": "", "porta": 587, "usuario": "", "destinatario": "", "seguranca": "starttls"},
                         **(cfg.get("email") or {})}
                email["servidor"] = input(f"Servidor SMTP [{email['servidor']}]: ").strip() or email["servidor"]
                seguranca = input("Segurança [1] STARTTLS (587) · [2] SSL (465) (ENTER = 1): ").strip()
                email["seguranca"] = "ssl" if seguranca == "2" else "starttls"
                email["porta"] = 465 if email["seguranca"] == "ssl" else 587
                email["usuario"] = input(f"Usuário (seu e-mail) [{email['usuario']}]: ").strip() or email["usuario"]
                email["destinatario"] = input(f"Enviar para [{email['destinatario'] or email['usuario']}]: ").strip() \
                    or email["destinatario"] or email["usuario"]
                email["remetente"] = input("Remetente (opcional — ENTER usa o usuário): ").strip()
                senha = getpass.getpass("Senha do e-mail (Gmail/Outlook: senha de app; fica só em memória): ")
                from app.core.validadores import problemas_email_cfg
                problemas = problemas_email_cfg(email, senha)
                if problemas:
                    print("\n❌ E-mail não ativado — revise:")
                    for p in problemas:
                        print(f"  • {p}")
                    cfg["email_ativo"] = False
                    pausar()
                else:
                    cfg["email"] = email
                    sessao.notificacao.email_senha = senha
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
            from app.notifications import windows as windows_notif
            from app.notifications.email import configurado as email_ok, testar_email
            from app.notifications.webhook import testar_webhook
            extras = []
            if cfg.get("windows_ativo") and windows_notif.disponivel():
                extras.append(("Windows", windows_notif.testar_windows))
            if cfg.get("webhook_ativo") and sessao.notificacao.webhook_configurado():
                extras.append(("Webhook", lambda: testar_webhook(sessao.notificacao.webhook_url, cfg.get("webhook_formato", "discord"))))
            if cfg.get("email_ativo") and email_ok(cfg.get("email") or {}, sessao.notificacao.email_senha):
                extras.append(("E-mail", lambda: testar_email(cfg["email"], sessao.notificacao.email_senha)))
            for nome, fabrica in extras:
                try:
                    _asyncio.run(fabrica())
                    print(f"{nome}: OK")
                except Exception as e:
                    print(f"{nome}: falhou ({e})")
            pausar()
        elif escolha == "6":
            from app.core.textos import ROTULOS_EVENTOS_NOTIFICACAO
            chaves = list(ROTULOS_EVENTOS_NOTIFICACAO)
            while True:
                cabecalho("Quais eventos notificar")
                for i, chave in enumerate(chaves, start=1):
                    print(f"[{i}] [{'x' if cfg['eventos'].get(chave) else ' '}] {ROTULOS_EVENTOS_NOTIFICACAO[chave]}")
                print(f"[H] Resumo periódico a cada {cfg.get('resumo_intervalo_horas', 6)} hora(s)")
                print("[V] Voltar")
                opcao = input("\nNúmero para ligar/desligar: ").strip().lower()
                if opcao == "v" or not opcao:
                    break
                if opcao == "h":
                    try:
                        horas = float(input("Intervalo em horas (0,5 a 48): ").strip().replace(",", "."))
                    except ValueError:
                        horas = -1
                    if 0.5 <= horas <= 48:
                        cfg["resumo_intervalo_horas"] = horas
                    else:
                        print("❌ Valor fora do intervalo — mantido o anterior.")
                        pausar()
                elif opcao.isdigit() and 1 <= int(opcao) <= len(chaves):
                    chave = chaves[int(opcao) - 1]
                    cfg["eventos"][chave] = not cfg["eventos"].get(chave, False)
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
        print(f"  {URL_REPOSITORIO}\n")
        print("O projeto é open source. Sugestões e relatos de bugs são bem-vindos,")
        print("preferencialmente pelo GitHub (issues/discussions).\n")
        from app.core.distribuicao import hash_executavel
        hash_exe = hash_executavel()
        if hash_exe:
            print(f"SHA-256 deste executável: {hash_exe}")
            print("(compare com o SHA256SUMS.txt publicado junto do pacote)\n")
        print("[1] Criar atalho na Área de Trabalho")
        print("[3] Verificar se há versão nova (uma consulta ao GitHub)")
        print("[2] Voltar")
        escolha = input("\nEscolha: ").strip()

        if escolha == "3":
            from app.core.distribuicao import verificar_atualizacao
            r = verificar_atualizacao()
            print(f"\n{r['texto']}" + (f"\n{r['url']}" if r.get("nova") else ""))
            pausar()
            continue

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
    ativas = sum(1 for d in carregar_disciplinas() if d.ativa)
    limite = settings.get("protecao", {}).get("limite_req_por_seg", 0)
    print(f"Carga estimada atual: {estimar_carga(settings['num_workers'], settings['intervalo_busca'], ativas, limite)['texto']}\n")
    print("Perfis prontos de carga (digite a letra no lugar do número de workers):")
    atalhos = {"l": "leve", "m": "moderado", "p": "padrao"}
    for letra, chave in atalhos.items():
        p = PRESETS_CARGA[chave]
        print(f"  [{letra.upper()}] {p['rotulo']}: {p['num_workers']} workers, {p['intervalo_busca']}s — {p['descricao']}")
    print(f"\nWorkers atuais: {settings['num_workers']}")
    novo = input("Novo número de workers (ENTER para manter, ou L/M/P para um perfil): ").strip()
    if novo.lower() in atalhos:
        preset = PRESETS_CARGA[atalhos[novo.lower()]]
        settings["num_workers"] = preset["num_workers"]
        settings["intervalo_busca"] = preset["intervalo_busca"]
        print(f"Perfil {preset['rotulo']} aplicado.")
    else:
        if novo.isdigit():
            settings["num_workers"] = int(novo)

        print(f"\nIntervalo de busca atual (segundos): {settings['intervalo_busca']}")
        novo = input("Novo intervalo (ENTER para manter): ").strip()
        try:
            if novo:
                settings["intervalo_busca"] = float(novo.replace(",", "."))
        except ValueError:
            pass

    print(f"\nTimeout de requisição atual (segundos): {settings['timeout_req']}")
    novo = input("Novo timeout (ENTER para manter): ").strip()
    if novo.isdigit():
        settings["timeout_req"] = int(novo)

    problemas = validar_settings(settings)
    if problemas:
        # Antes o terminal salvava qualquer valor (ex: 500 workers) sem conferir.
        print("\nNão salvo — corrija:")
        for p in problemas:
            print(f"  • {p}")
        pausar()
        return
    salvar_settings(settings)
    carga = estimar_carga(settings["num_workers"], settings["intervalo_busca"], ativas, limite)
    print(f"\nSalvo. Carga estimada: {carga['texto']}")
    if carga["alerta"]:
        print(f"⚠️  {carga['alerta']}")
    pausar()


# ── Diagnóstico ──────────────────────────────────────────────────────────

def menu_diagnostico():
    from app.core.diagnostics import checar_conectividade_em_camadas, checar_saude_sistema

    while True:
        cabecalho("Diagnóstico")
        print("[1] Diagnóstico completo")
        print("[2] Testar conectividade em camadas (Internet → SIGAA → ...)")
        print("[3] Ver eventos recentes (Central de Logs em linguagem simples)")
        print("[4] Histórico de execuções")
        print("[6] Assistente de solução de problemas e recomendações")
        print("[7] Páginas capturadas (dados pessoais mascarados)")
        print("[8] Gerar pacote de suporte (.zip sem dados pessoais)")
        print("[5] Voltar")
        escolha = input("\nEscolha: ").strip()

        if escolha == "1":
            from app.core.seguranca_config import checar_configuracoes_inseguras
            print("\nRodando verificações...\n")
            resultados = [*checar_saude_sistema(), checar_modo_execucao(), *checar_configuracoes_inseguras()]
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
            menu_eventos()
        elif escolha == "4":
            menu_historico()
        elif escolha == "6":
            menu_assistente()
        elif escolha == "7":
            menu_paginas_capturadas()
        elif escolha == "8":
            menu_pacote_suporte()
        elif escolha == "5":
            return


def _contexto_ultima_execucao() -> dict:
    """No terminal a execução já terminou quando se chega ao Diagnóstico: usa a última gravada."""
    from app.core.relatorios import listar_relatorios
    lista = listar_relatorios(1)
    return {"snap": None, "ultima": lista[0] if lista else None}


def menu_assistente():
    """Sugestões 079 e 089: sintoma → causa provável e ação; recomendações aplicáveis."""
    from app.core.assistente import SINTOMAS, aplicar_recomendacao, diagnosticar, recomendar_configuracao
    rotulo = {"certa": "CONFIRMADO", "provavel": "PROVÁVEL", "sugestao": "VERIFIQUE"}
    chaves = list(SINTOMAS)
    while True:
        cabecalho("Assistente de solução de problemas")
        for i, chave in enumerate(chaves, start=1):
            print(f"[{i}] {SINTOMAS[chave]}")
        print("[R] Recomendações de configuração")
        print("[V] Voltar")
        escolha = input("\nO que está acontecendo? ").strip().lower()
        if escolha == "v":
            return
        settings = carregar_settings()
        if escolha == "r":
            recs = recomendar_configuracao(settings, **_contexto_ultima_execucao())
            if not recs:
                print("\nNenhuma recomendação agora — elas aparecem depois de uma execução com pelo menos 100 buscas.")
            for r in recs:
                print(f"\n💡 {r['texto']}\n   {r['motivo']}")
                if input("   Aplicar? (s/N): ").strip().lower() == "s":
                    problemas = aplicar_recomendacao(settings, r)
                    if problemas:
                        print("   Não aplicado: " + "; ".join(problemas))
                    else:
                        salvar_settings(settings)
                        print("   ✅ Aplicado (vale na próxima execução).")
            pausar()
            continue
        if not (escolha.isdigit() and 1 <= int(escolha) <= len(chaves)):
            continue
        r = diagnosticar(chaves[int(escolha) - 1], settings, carregar_disciplinas(), obter_sessao().sigaa,
                         **_contexto_ultima_execucao())
        print(f"\n🧭 {r['pergunta']}")
        print(f"(analisado com base em {r['fonte'] or 'nenhuma execução gravada'} e na configuração atual)\n")
        for a in r["achados"]:
            print(f"[{rotulo[a['certeza']]}] {a['causa']}")
            if a["evidencia"]:
                print(f"   Evidência: {a['evidencia']}")
            print(f"   O que fazer: {a['acao']}\n")
        pausar()


def menu_paginas_capturadas():
    """Sugestão 064: páginas do SIGAA guardadas para diagnóstico, só como texto e mascaradas."""
    from app.core.suporte import ler_dump, listar_dumps
    while True:
        cabecalho("Páginas capturadas (dados pessoais mascarados)")
        dumps = listar_dumps()[:20]
        if not dumps:
            print("(nenhuma página capturada — bom sinal)")
            pausar()
            return
        for i, d in enumerate(dumps, start=1):
            print(f"[{i:>2}] {d['quando'] or '—'}  {d['worker']}  {d['motivo_texto']}  ({d['tamanho_kb']} KB)")
        escolha = input("\nNúmero para ver como texto · [V] voltar: ").strip().lower()
        if escolha == "v" or not escolha:
            return
        if escolha.isdigit() and 1 <= int(escolha) <= len(dumps):
            lido = ler_dump(dumps[int(escolha) - 1]["nome"], obter_sessao().sigaa)
            if lido:
                cabecalho(lido["motivo_texto"])
                print(lido["texto"][:6000] or "(página sem texto visível)")
                if len(lido["texto"]) > 6000 or lido["cortado"]:
                    print("\n(... página longa: mostrando o começo)")
            pausar()


def menu_pacote_suporte():
    """Sugestão 051: mostra o conteúdo e grava o .zip em data/exportacoes/."""
    from app.core.suporte import conteudo_pacote_suporte, salvar_pacote_suporte
    cabecalho("Pacote de suporte")
    sessao = obter_sessao()
    for a in conteudo_pacote_suporte(sessao.sigaa):
        print(f"• {a['nome']} ({a['tamanho_kb']} KB) — {a['descricao']}")
    print("\nDados pessoais são mascarados; senha, CPF, data de nascimento e tokens nunca entram.")
    if input("Gerar o pacote agora? (s/N): ").strip().lower() == "s":
        print(f"\n✅ Pacote salvo em: {salvar_pacote_suporte(sessao.sigaa)}\nConfira antes de compartilhar.")
    pausar()


def menu_exportar_importar():
    """Sugestão 013: backup da configuração pelo terminal (nunca inclui credenciais)."""
    from datetime import datetime
    from app.core.config import exportar_configuracao, importar_configuracao, pre_visualizar_importacao
    from app.utils.paths import pasta_data
    cabecalho("Exportar / importar configuração")
    print("[1] Exportar para data/exportacoes/")
    print("[2] Importar de um arquivo")
    print("[3] Voltar")
    escolha = input("\nEscolha: ").strip()
    if escolha == "1":
        pasta = os.path.join(pasta_data(), "exportacoes")
        os.makedirs(pasta, exist_ok=True)
        destino = os.path.join(pasta, f"sigaa_sniper_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        exportar_configuracao(destino)
        print(f"\n✅ Exportado para: {destino}")
    elif escolha == "2":
        caminho = input("Caminho do arquivo .json exportado pelo programa: ").strip().strip('"')
        try:
            resumo = pre_visualizar_importacao(caminho)
        except Exception as e:
            print(f"\n❌ Arquivo rejeitado: {e}")
            pausar()
            return
        if resumo["problemas_settings"]:
            print("\n❌ O arquivo tem problemas e não será importado:")
            for p in resumo["problemas_settings"]:
                print(f"  • {p}")
        else:
            print(f"\nDisciplinas válidas: {resumo['qtd_disciplinas']} · configurações: {'sim' if resumo['tem_settings'] else 'não'}")
            if input("Aplicar agora? (s/N): ").strip().lower() == "s":
                importar_configuracao(caminho)
                print("✅ Importado (dá para desfazer em Versões anteriores, na interface gráfica ou na Web).")
    else:
        return
    pausar()


def menu_restaurar_padroes():
    from app.core.config import SECOES_RESTAURAVEIS, restaurar_padroes
    cabecalho("Restaurar configurações padrão")
    print("Nunca mexe em credenciais nem nas disciplinas.\n")
    for i, secao in enumerate(SECOES_RESTAURAVEIS, start=1):
        print(f"[{i}] {secao}")
    print(f"[{len(SECOES_RESTAURAVEIS) + 1}] TUDO")
    print("[V] Voltar")
    escolha = input("\nEscolha: ").strip().lower()
    if not escolha.isdigit() or not 1 <= int(escolha) <= len(SECOES_RESTAURAVEIS) + 1:
        return
    secoes = None if int(escolha) == len(SECOES_RESTAURAVEIS) + 1 else [SECOES_RESTAURAVEIS[int(escolha) - 1]]
    if input(f"Restaurar {'TUDO' if secoes is None else secoes[0]} para o padrão? (s/N): ").strip().lower() == "s":
        salvar_settings(restaurar_padroes(carregar_settings(), secoes))
        print("✅ Restaurado.")
    pausar()


def menu_web_e_logs():
    """Sugestão 013: Interface Web (porta, endereço, expiração) e retenção de logs pelo terminal."""
    settings = carregar_settings()
    web, logs, audit = settings["web"], settings["logs"], settings["json_audit"]
    cabecalho("Interface Web e arquivos de log")
    print("ENTER mantém o valor atual.\n")

    def pedir(rotulo, atual, conversor=int):
        texto = input(f"{rotulo} [{atual}]: ").strip()
        if not texto:
            return atual
        try:
            return conversor(texto)
        except ValueError:
            print("  (valor inválido — mantido)")
            return atual

    web["host"] = pedir("Endereço da Interface Web (127.0.0.1 = só este computador)", web["host"], str)
    web["porta"] = pedir("Porta da Interface Web", web["porta"])
    web["expirar_inatividade_min"] = pedir("Encerrar a sessão Web após N minutos sem uso (0 = nunca)", web.get("expirar_inatividade_min", 0))
    logs["arquivos_mantidos"] = pedir("Dumps de debug mantidos", logs["arquivos_mantidos"])
    audit["tamanho_max_mb"] = pedir("Tamanho máximo do log principal (MB)", audit["tamanho_max_mb"])
    audit["arquivos_mantidos"] = pedir("Arquivos antigos do log principal mantidos", audit["arquivos_mantidos"])
    atual = "s" if settings.get("carregar_ultima_execucao") else "n"
    resposta = input(f"Web/interface gráfica: carregar os dados da última execução ao abrir? (s/n) [{atual}]: ").strip().lower()
    settings["carregar_ultima_execucao"] = (resposta or atual) == "s"
    problemas = validar_settings(settings)
    if problemas:
        print("\nNão salvo — corrija:")
        for p in problemas:
            print(f"  • {p}")
    else:
        salvar_settings(settings)
        print("\n✅ Salvo. Mudanças na Interface Web valem na próxima vez que ela for aberta.")
    pausar()


def menu_perfis():
    """Sugestão 042: salvar e aplicar cenários (o DRY RUN nunca vem do perfil)."""
    from app.core.config import aplicar_perfil, apagar_perfil, listar_perfis, salvar_perfil
    while True:
        cabecalho("Perfis")
        perfis = listar_perfis()
        if not perfis:
            print("(nenhum perfil ainda — salve a configuração atual com [S])")
        for i, p in enumerate(perfis, start=1):
            print(f"[{i}] {p['nome']} — {p['resumo']}")
        print("\n[S] Salvar a configuração atual como perfil · [A] Apagar um perfil · [V] Voltar")
        escolha = input("\nNúmero para aplicar: ").strip().lower()
        if escolha in ("v", ""):
            return
        if escolha == "s":
            nome = input("Nome do perfil: ").strip()
            try:
                salvar_perfil(nome, carregar_settings(), carregar_disciplinas())
                print(f"✅ Perfil \"{nome}\" salvo.")
            except ValueError as e:
                print(f"❌ {e}")
            pausar()
        elif escolha == "a":
            numero = input("Número do perfil a apagar: ").strip()
            if numero.isdigit() and 1 <= int(numero) <= len(perfis):
                apagar_perfil(perfis[int(numero) - 1]["arquivo"])
                print("✅ Perfil apagado.")
                pausar()
        elif escolha.isdigit() and 1 <= int(escolha) <= len(perfis):
            p = perfis[int(escolha) - 1]
            print(f"\n{p['resumo']}. O DRY RUN continua como está.")
            if input(f"Aplicar \"{p['nome']}\"? (s/N): ").strip().lower() == "s":
                try:
                    novos, disciplinas = aplicar_perfil(p["arquivo"], carregar_settings())
                    salvar_settings(novos)
                    salvar_disciplinas(disciplinas)
                    print("✅ Perfil aplicado.")
                except ValueError as e:
                    print(f"❌ {e}")
                pausar()


def menu_acoes_registradas():
    from app.core import auditoria
    cabecalho("Ações registradas (mais recentes primeiro)")
    acoes = auditoria.listar(40)
    if not acoes:
        print("(nenhuma ação registrada ainda)")
    for a in acoes:
        print(f"{a['quando']}  {a['rotulo']}" + (f" — {a['descricao']}" if a["descricao"] else "") + f"  [{a['origem']}]")
    pausar()


def menu_historico():
    """Fase 3 (061/049) no terminal: execuções gravadas, relatório de cada uma e exportação CSV."""
    from datetime import datetime

    from app.core import historico
    from app.core.relatorios import MOTIVOS_FIM, texto_relatorio
    from app.utils.paths import pasta_data

    historico.importar_relatorios_antigos()
    while True:
        cabecalho("Histórico de execuções (últimas 20)")
        execucoes = historico.listar_execucoes(limite=20)
        if not execucoes:
            print("(nenhuma execução gravada ainda — cada execução encerrada entra aqui automaticamente)")
        for i, e in enumerate(execucoes, start=1):
            modo = "monitoramento" if e["modo"] == "monitoramento" else ("DRY RUN" if e["dry_run"] else "MATRÍCULA REAL")
            minutos = int((e["duracao_seg"] or 0) // 60)
            print(f"[{i:>2}] {datetime.fromtimestamp(e['inicio']).strftime('%d/%m/%Y %H:%M')}  {minutos // 60}h{minutos % 60:02d}m  "
                  f"{modo:<14} {MOTIVOS_FIM.get(e['motivo_fim'], '—'):<46.46} buscas {e['requisicoes']:>6} · vagas {e['vagas_vistas']}")
        print("\nDigite o número para ver o relatório · [E] exportar tudo em CSV · [A] ações registradas · [V] voltar")
        escolha = input("\nEscolha: ").strip().lower()
        if escolha == "v":
            return
        if escolha == "a":
            menu_acoes_registradas()
            continue
        if escolha == "e":
            pasta = os.path.join(pasta_data(), "exportacoes")
            os.makedirs(pasta, exist_ok=True)
            destino = os.path.join(pasta, f"historico_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            with open(destino, "w", encoding="utf-8", newline="") as f:
                f.write(historico.exportar_execucoes("csv"))
            print(f"\n✅ Exportado para: {destino}")
            pausar()
        elif escolha.isdigit() and 1 <= int(escolha) <= len(execucoes):
            detalhe = historico.obter_execucao(execucoes[int(escolha) - 1]["id"])
            cabecalho("Relatório da execução")
            print(texto_relatorio(detalhe["resumo"]) if detalhe else "Execução não encontrada.")
            pausar()


def menu_eventos():
    """Sugestão 016: a mesma tradução para linguagem simples da Central de Logs (GUI/Web)."""
    from app.terminal.acompanhamento import CATEGORIAS, eventos_recentes, imprimir_eventos

    texto, categoria = "", ""
    while True:
        cabecalho("Eventos recentes")
        filtros = []
        if texto:
            filtros.append(f"texto: {texto!r}")
        if categoria:
            filtros.append(f"categoria: {categoria}")
        print(f"Filtros: {', '.join(filtros) or 'nenhum'} — mostrando os 30 mais recentes\n")
        eventos = eventos_recentes(30, texto, categoria)
        if eventos:
            imprimir_eventos(eventos)
        else:
            print("(nenhum evento encontrado — o log fica em data/sigaa_sniper_audit.json)")
        print("\n[1] Filtrar por texto   [2] Filtrar por categoria   [3] Limpar filtros   [4] Atualizar   [5] Voltar")
        escolha = input("\nEscolha: ").strip()
        if escolha == "1":
            texto = input("Texto (ex: vaga, timeout, W3): ").strip()
        elif escolha == "2":
            for i, c in enumerate(CATEGORIAS, start=1):
                print(f"  [{i}] {c}")
            n = input("Categoria: ").strip()
            categoria = CATEGORIAS[int(n) - 1] if n.isdigit() and 1 <= int(n) <= len(CATEGORIAS) else ""
        elif escolha == "3":
            texto, categoria = "", ""
        elif escolha == "5":
            return


if __name__ == "__main__":
    menu_principal()
