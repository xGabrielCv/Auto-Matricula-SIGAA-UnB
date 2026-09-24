"""
Textos de ajuda compartilhados pelas três interfaces (GUI, Web e terminal).

Antes viviam dentro das telas Tkinter, e a Interface Web precisava importar
módulos da GUI (que exigem tkinter) só para ler estas constantes. Aqui eles
não dependem de nenhuma interface — cada modo só apresenta o texto.
"""
from __future__ import annotations

# Configurações avançadas — um texto por opção (botões [?]).
AJUDA_AVANCADO = {
    "workers": "Quantas buscas simultâneas o programa faz. Mais workers = mais rápido para achar "
               "vaga, mas também mais carga no seu computador e no SIGAA. Acima de 20 raramente "
               "ajuda e aumenta o risco de bloqueio temporário.",
    "intervalo": "Quanto tempo cada worker espera entre uma busca e a próxima pela mesma disciplina. "
                 "Muito baixo (perto de 0) pode ser tratado como abuso pelo SIGAA.",
    "timeout": "Quanto tempo esperar uma resposta do SIGAA antes de desistir daquela tentativa "
               "específica e reiniciar a conexão.",
    "dashboard_auto": "Se marcado, a aba Dashboard já aparece com dados assim que uma execução começa.",
    "carregar_ultima": "Desligado (padrão): ao abrir o programa, o Dashboard e a Central de Logs começam vazios — nada de "
                       "execução anterior aparecendo como se fosse a atual. As execuções anteriores continuam na tela "
                       "Histórico. Ligado: mostram os dados da última execução, marcados como recuperados e congelados "
                       "(o tempo não corre e nenhuma execução é iniciada). Vale na próxima vez que a interface abrir.",
    "logs_tamanho": "Tamanho máximo de cada arquivo de log de auditoria antes de rotacionar (criar um novo).",
    "logs_qtd": "Quantos arquivos de log antigos ficam guardados além do atual.",
    "debug": "DEBUG mostra mais detalhes técnicos no console (ex: código HTTP e tamanho da resposta "
             "de cada busca). Nunca inclui senha, CPF ou qualquer credencial, nem em modo DEBUG.",
    "urls": "Endereços usados para falar com o SIGAA. Só mude se o SIGAA tiver alterado essas URLs — "
            "um valor errado impede o programa de funcionar. Use 'Restaurar' se algo der errado.",
    "protecao": "Teto de buscas por segundo para o programa inteiro, qualquer que seja o número de workers "
                "(as etapas de matrícula nunca esperam por ele). 0 desliga o teto. Os logins simultâneos evitam que "
                "todos os workers entrem no CAS no mesmo instante. O disjuntor pausa as buscas quando o SIGAA dá "
                "sinais de queda ou sobrecarga e faz uma busca de teste antes de voltar — em vez de insistir.",
    "carga": "Perfis prontos de desempenho. A carga estimada é aproximadamente workers ÷ intervalo "
             "(requisições por segundo, no máximo). Valores altos aumentam o risco de bloqueio e "
             "pesam no SIGAA — o aviso legal pede uso responsável. 'Leve' costuma bastar para "
             "acompanhar vagas; use mais só quando precisar reagir em segundos.",
}

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

TEXTO_AJUDA_LOTE = (
    "Cadastro em lote — uma disciplina por linha, no formato:\n\n"
    "  CÓDIGO  TURMA  DEPARTAMENTO\n\n"
    "Separadores aceitos: espaço, vírgula, ponto e vírgula ou tabulação\n"
    "(dá para colar direto de uma planilha). Exemplos:\n\n"
    "  FGA0211 01 673\n"
    "  MAT0025;02;518\n"
    "  CIC0004,03,508\n\n"
    "A turma é só o número, como aparece na lista do SIGAA (ex: 01).\n"
    "Linhas em branco e linhas começando com # são ignoradas. Nada é salvo\n"
    "antes de você revisar a pré-visualização e confirmar."
)


# Desde a 6.1.0: ajuda progressiva — o resumo curto fica ao lado do campo; o texto
# completo abre no botão "Como funciona?".
RESUMO_GRUPO = "Turmas com o mesmo nome de grupo são alternativas: garantida uma, as outras saem da busca."
RESUMO_PRIORIDADE = "Alta é consultada primeiro em cada rodada; baixa, a cada três rodadas."

TEXTO_AJUDA_GRUPO = """Grupo de alternativas

O que é: um nome que você dá a turmas que servem para a MESMA necessidade. Ex: FGA0211 turma 01 e FGA0211 turma 03 no grupo "Cálculo 1" — você quer uma delas, não as duas.

Como funciona:
• O programa procura vaga em todas as turmas do grupo ao mesmo tempo.
• Assim que UMA é garantida (ou simulada, no DRY RUN), as outras do grupo saem da busca — nunca há duas matrículas para a mesma necessidade.
• Duas turmas do grupo com vaga ao mesmo tempo: fica a que for confirmada primeiro (a prioridade ajuda a decidir quem é consultada antes).
• Nenhuma com vaga: todas continuam sendo monitoradas.

Quando usar: sempre que qualquer uma de várias turmas resolver o seu caso. Deixe em branco para disciplinas independentes."""

TEXTO_AJUDA_PRIORIDADE = """Prioridade

• Alta: consultada primeiro em cada rodada de buscas.
• Normal: ordem padrão.
• Baixa: consultada só a cada três rodadas — sobra ritmo para as outras e alivia o SIGAA.

O que acontece:
• Prioritária e secundária com vaga ao mesmo tempo: a prioritária é consultada (e tentada) antes.
• Só a secundária com vaga: ela é tentada normalmente — prioridade não bloqueia nada, só define a ordem.
• Nenhuma com vaga: continuam sendo consultadas, cada uma no seu ritmo.

Combine com grupos: dentro de um grupo, deixe como "alta" a turma que você prefere.
Para mudar, edite a disciplina (na Web e na interface gráfica, ou no terminal em Disciplinas → Editar)."""

TEXTO_AJUDA_WEBHOOK = """Webhook (Discord, Slack ou JSON)

Para que serve: envia os avisos (vaga, matrícula, alertas) para um canal seu no Discord ou no Slack, ou para qualquer serviço que receba JSON.

Como configurar:
• Discord: no canal, Editar canal → Integrações → Webhooks → Novo webhook → Copiar URL do webhook.
• Slack: crie um "Incoming Webhook" no seu workspace e copie a URL.
• Cole a URL aqui (precisa começar com https://), escolha o formato e use "Enviar teste".

Segurança: a URL funciona como uma senha do canal — quem a tiver posta lá. Ela fica só em memória (ou cifrada, se você marcar "Salvar neste computador") e nunca aparece em logs, relatórios ou pacotes de suporte.
Se o envio falhar, o monitoramento continua normalmente; o erro aparece no teste e na Central de Logs."""

TEXTO_AJUDA_EMAIL = """E-mail (SMTP)

Para que serve: recebe os avisos por e-mail, sem instalar nada.

Como configurar:
• Servidor e segurança: Gmail = smtp.gmail.com, STARTTLS, porta 587. Outlook/Hotmail = smtp-mail.outlook.com, STARTTLS, porta 587. Servidores com SSL costumam usar a porta 465.
• Usuário: o seu endereço de e-mail.
• Senha: Gmail e Outlook exigem uma "senha de app" (gerada na conta, em Segurança) — a senha normal é recusada.
• Enviar para: onde você quer receber (pode ser o mesmo endereço).
• Remetente (opcional): o endereço que aparece como "de"; em branco, usa o usuário.
• Use "Enviar teste" antes de ativar.

Segurança: a senha nunca é enviada sem criptografia, nunca vai para logs, relatórios ou pacotes de suporte, e só fica salva (cifrada) se você marcar "Salvar neste computador".
Se o envio falhar, o monitoramento continua normalmente."""


def textos_ajuda() -> dict:
    """Todos os textos num único dicionário (formato consumido pela Interface Web)."""
    textos = {f"avancado_{chave}": texto for chave, texto in AJUDA_AVANCADO.items()}
    textos.update({
        "departamento": TEXTO_AJUDA_DEPARTAMENTO, "telegram": TEXTO_AJUDA_TELEGRAM,
        "ntfy": TEXTO_AJUDA_NTFY, "alarme": TEXTO_AJUDA_ALARME, "lote": TEXTO_AJUDA_LOTE,
        "grupo": TEXTO_AJUDA_GRUPO, "prioridade": TEXTO_AJUDA_PRIORIDADE,
        "webhook": TEXTO_AJUDA_WEBHOOK, "email": TEXTO_AJUDA_EMAIL,
    })
    return textos


# Eventos que podem virar notificação externa (Telegram/ntfy/alarme) — mesmos
# rótulos na Web, na interface gráfica e no terminal.
ROTULOS_EVENTOS_NOTIFICACAO = {
    "vaga_detectada": "Vaga encontrada",
    "matricula_sucesso": "Matrícula confirmada",
    "matricula_falha": "Tentativa de matrícula falhou (retry automático)",
    "matricula_bloqueada": "Disciplina bloqueada pelo SIGAA (pré-requisito/choque)",
    "erro_critico": "Erro crítico",
    "alerta_limiar": "Alertas de problema (muitos erros, SIGAA sem responder, lentidão, manutenção)",
    "worker_reiniciado": "Worker travado recriado automaticamente",
    "resumo_periodico": "Resumo periódico da execução (\"está tudo bem?\")",
    "execucao_encerrada": "Resumo ao encerrar a execução",
}
