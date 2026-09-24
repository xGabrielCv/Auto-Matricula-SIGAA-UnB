# Guia de Uso — SIGAA Sniper

## Instalação

**Jeito mais simples (Windows):** extraia o `SIGAA-Sniper.zip` e dê duplo clique em `SIGAA-Sniper.exe`. Não é preciso instalar Python nem nada mais.

**Pelo código-fonte:**

1. Instale o Python 3.9 ou mais recente (https://www.python.org/downloads/), marcando "Add Python to PATH" durante a instalação.
2. Coloque a pasta do SIGAA Sniper em qualquer lugar do seu computador (Desktop, Downloads, pendrive — não importa).
3. Dê duplo clique em `run.bat`. Ele confere se o Python e as bibliotecas necessárias (httpx, beautifulsoup4, rich) estão instaladas e instala automaticamente o que faltar.

## Primeira execução

Ao abrir, você verá um menu numerado:

```
[0] 🌐 Interface Web  ★ RECOMENDADO — abre no navegador
[1] Interface gráfica
[2] Matrícula automática
[3] Somente monitoramento
[4] Configurações
[5] Diagnóstico
[6] Sair
```

Recomendado: escolha **[0] 🌐 Interface Web** — é o jeito mais fácil de configurar e acompanhar tudo. A interface gráfica ([1]) e o modo terminal ([2] a [5]) continuam disponíveis e funcionam como antes.

### Configuração inicial guiada

Na primeira vez que você abre a Interface Web ou a interface gráfica, um assistente guia a configuração em etapas: **Boas-vindas → Credenciais → Disciplinas → Execução → Notificações → Painéis → Revisão**. Cada etapa é conferida antes de avançar — se algo estiver errado, a mensagem diz exatamente o quê (ex: "O CPF precisa ter 11 dígitos — você digitou 10."). Você pode **voltar**, **cancelar** ou escolher **Configurar depois** (nenhum dado é salvo — o assistente só deixa de abrir sozinho). Na Revisão aparece tudo o que foi escolhido; **✔ Concluir** salva.

Depois de concluído, o assistente não reaparece. Para refazê-lo: **Config. Avançadas → 🧭 Refazer a configuração inicial** (ou `Ctrl + K` → "Refazer a configuração inicial" na Web). As credenciais digitadas no assistente continuam só na memória, a menos que você marque para salvá-las.

## Interface Web (recomendada)

Ao escolher **[0]**, o programa abre um pequeno servidor **só neste computador** e abre o navegador automaticamente. No terminal aparece o endereço, por exemplo:

```
Endereço:  http://127.0.0.1:8765
http://127.0.0.1:8765/?chave=Abc123...
```

- Use o **link completo** (com `?chave=`): ele contém uma chave de acesso nova a cada execução. Sem ela a página não abre — isso impede que outros programas ou sites acessem o SIGAA Sniper.
- Se o navegador não abrir sozinho, copie o link do terminal e cole no navegador.
- Por padrão a interface abre numa **janela própria** do Edge/Chrome, sem barra de endereço (parece um programa, não mais uma aba). Se preferir uma aba comum, desmarque "Abrir em janela própria" em **Config. Avançadas → Interface Web**. Sem Edge/Chrome instalado, usa o navegador padrão.
- **Atalhos:** `Ctrl + K` abre a **paleta de ações** — digite o que quer fazer ("iniciar", "logs", "adicionar disciplina") e tecle Enter. `G` e depois uma letra vai direto para uma tela (`G D` Dashboard, `G L` Logs, `G M` Disciplinas, `G C` Credenciais…). `?` mostra todos os atalhos.
- **Central de notificações (🔔):** guarda os avisos desta sessão, inclusive os que já sumiram da tela. Vagas encontradas e o fim de uma execução aparecem como aviso em **qualquer** tela, não só no Dashboard.
- Se a conexão com o programa falhar por um instante (computador sob carga, por exemplo), a página mostra "Reconectando…" e tenta de novo sozinha por alguns segundos antes de considerar a interface encerrada. A execução, se houver, continua no programa.
- O **aviso legal** aparece de novo no navegador e é preciso marcar as 5 confirmações, exatamente como na interface gráfica.
- Todas as funções da interface gráfica existem na Web: execução, dashboard ao vivo, logs, credenciais, disciplinas, notificações, configurações avançadas, diagnóstico, experimental, ajuda e atalho.
- Para encerrar: botão **⏻ Encerrar** na página, ou **ENTER** no terminal. O programa volta ao menu e apaga as credenciais da memória.
- Porta ocupada? O programa tenta automaticamente as 10 portas seguintes. Para fixar outra porta, altere em **Config. Avançadas → Interface Web** (vale na próxima abertura).
- Funciona sem internet (a página não usa nada externo) — a internet só é necessária para falar com o SIGAA e com Telegram/ntfy.

## Credenciais

Toda vez que você abrir o programa, ele vai pedir sua matrícula, senha, CPF e data de nascimento do SIGAA. **Isso é proposital: o programa nunca salva essas informações em disco.** Elas ficam só na memória enquanto o programa está aberto e são apagadas quando você fecha.

O programa confere o **CPF** (11 dígitos e dígitos verificadores; pode ser digitado com ou sem pontos — `123.456.789-09` ou `12345678909` — e é guardado sempre no formato com pontos) e a **data de nascimento** (formato `DD/MM/AAAA`, dia e mês que existam, sem datas no futuro) antes de iniciar. As mesmas regras valem na Web, na interface gráfica e no terminal. Isso evita o pior erro silencioso: com um desses dados errado, cada vaga encontrada viraria uma confirmação recusada pelo SIGAA. A data pode ser digitada como `01022003` ou `1/2/2003` — ela é ajustada para `01/02/2003` automaticamente.

## Disciplinas

Cadastre as disciplinas que quer acompanhar: código (ex: `FGA0211`), turma (ex: `01`) e o código do departamento.

**Escolhendo o departamento:** se você já sabe o código (ex: `673`), digite-o — o programa mostra ao lado o nome do departamento, ou avisa se o código não é conhecido. Se não souber, clique em **📋 Ver departamentos**: abre a lista completa, com uma caixa de pesquisa por nome ou código; clique no departamento para escolhê-lo. A lista só abre quando você pede — nunca enquanto você digita. No terminal, ao pedir o departamento, digite o código, parte do nome para buscar, ou **L** para ver a lista completa (20 por página, escolha pelo número).

Essas informações **não são sensíveis** e ficam salvas em `config/disciplinas.json` para você não ter que digitar tudo de novo.

Ao salvar, o programa confere:

- **turma só com números**, como aparece na lista do SIGAA (ex: `01`) — o programa localiza a turma pelo número, então uma turma com letras nunca seria encontrada;
- **disciplina repetida** (mesmo código e turma) — não é aceita;
- código fora do formato usual (3 letras + 4 números), turma de um dígito, departamento desconhecido ou a mesma disciplina em duas turmas — o programa avisa e pergunta se quer salvar mesmo assim.

**Várias de uma vez:** use **📋 Adicionar várias** (Web e interface gráfica) ou a última opção do menu de disciplinas no terminal. Cole uma disciplina por linha no formato `CÓDIGO TURMA DEPARTAMENTO` (separados por espaço, vírgula, ponto e vírgula ou tabulação — dá para colar de uma planilha), confira a pré-visualização e confirme. Linhas com erro são ignoradas; nada é salvo antes de você confirmar.

**Grupo de alternativas:** dê o mesmo nome de grupo (ex: `Cálculo`) a turmas que são alternativas entre si. Assim que uma delas for garantida, as outras do grupo **saem da busca** — o programa não tenta se matricular em duas turmas da mesma disciplina. Deixe em branco se a disciplina não tem alternativa. O botão **?** ao lado do campo (no terminal, digite `?`) explica com exemplos.

**Prioridade:** *alta*, *normal* ou *baixa*. Disciplinas de prioridade alta são verificadas primeiro em cada rodada; as de prioridade baixa, com menos frequência (a cada três rodadas), o que também alivia o SIGAA. Também tem o botão **?** com a explicação.

**Mudanças durante a execução:** adicionar, editar, ativar/desativar ou remover uma disciplina com o programa rodando (Web e interface gráfica) vale **na hora** — não é preciso parar e iniciar de novo.

**Lista de departamentos atualizada:** o botão **🔄 Atualizar lista de departamentos** (tela Disciplinas; no terminal, Configurações → [10]) lê a lista da página pública do SIGAA, sem login, e passa a usá-la na busca e na conferência dos códigos. Se o SIGAA não responder ou a página vier diferente, a lista atual é mantida.

### Sobre o código do departamento

**Atenção: o código do departamento pode mudar.** Cada departamento/unidade tem um código identificador usado internamente pelo SIGAA (por exemplo, `673` para a Faculdade de Engenharia do Gama) — mas quem define esse número é o próprio SIGAA, não este programa, e ele pode ser alterado a qualquer momento.

O programa vem com uma lista de referência (`app/core/departamentos.py`) observada durante o desenvolvimento, usada para busca por nome na interface — mas essa lista **não é definitiva**. Se um código parar de funcionar, confira o valor atual:

1. Acesse https://sigaa.unb.br/sigaa/public/turmas/listar.jsf
2. Abra as ferramentas de desenvolvedor do navegador (tecla F12) e inspecione o campo "Unidade" (`formTurma:inputDepto`).
3. Encontre a opção do departamento desejado — o `value="..."` dela é o código atual.

Exemplo do HTML que você vai encontrar:
```html
<option value="673">CAMPUS UNB GAMA: FACULDADE DE CIÊNCIAS E TECNOLOGIAS EM ENGENHARIA - BRASÍLIA</option>
```
Aqui, `673` é o código naquele momento.

## Modo Matrícula Automática

O robô monitora as disciplinas cadastradas e, assim que encontrar vaga, tenta se matricular sozinho — usando a mesma lógica testada da versão 4.0 (login, busca, seleção de turma e confirmação).

- **Modo de teste (DRY RUN):** simula todo o processo, mas não confirma a matrícula de verdade. Ótimo para testar se está tudo configurado certo sem risco.
- Quando uma disciplina é bloqueada pelo SIGAA (pré-requisito, choque de horário etc.), o robô para de tentar aquela disciplina especificamente e continua com as outras.

## Controles da execução

- **Pausar / Retomar:** interrompe as buscas sem encerrar as sessões no SIGAA; ao retomar, não é feito novo login. No terminal, use a tecla **P**.
- **Término automático:** informe data e hora (`DD/MM/AAAA HH:MM:SS`) para a execução parar sozinha.
- **Janela diária:** faça o programa rodar só em certos horários e dias da semana (ex: das 08:00 às 18:00, de segunda a sexta). Fora da janela as buscas pausam e voltam sozinhas no próximo horário; a janela pode atravessar a meia-noite (ex: 22:00 às 02:00).
- **Relógio do SIGAA:** ao agendar o início, o programa mede a diferença entre o relógio deste computador e o do SIGAA e corrige o horário — útil quando a matrícula abre num minuto exato.
- **Verificação prévia (recomendada):** antes de começar, o programa faz um login de teste e confere se cada disciplina existe na lista do departamento. Se o login for recusado, a execução não começa (evita bloquear a conta); disciplinas não encontradas são avisadas.

Na Web e na interface gráfica essas opções ficam na tela **Execução**; no terminal, em **Configurações → [8]**.

**Proteção automática:** se o SIGAA começar a responder com sobrecarga (erros 429/503) ou ficar instável, o programa **reduz o ritmo e pausa as buscas por alguns segundos** antes de tentar de novo, em vez de insistir. O limite de requisições por segundo, de logins simultâneos e essa pausa automática podem ser ajustados em Configurações Avançadas → Proteção de carga (Web e interface gráfica). A execução também para sozinha, com uma mensagem clara, quando o SIGAA avisa que os dados pessoais estão incorretos ou que o período de matrícula terminou.

## Modo demonstração

Marque **🎓 Modo demonstração** na tela Execução (no terminal, opção **[7]** do menu principal) para rodar o programa inteiro contra um **SIGAA simulado neste computador**: não pede credenciais, não acessa o SIGAA, as vagas aparecem e somem ao acaso e o DRY RUN fica sempre ligado. Serve para aprender a usar os painéis, testar as notificações (elas chegam marcadas com "[DEMONSTRAÇÃO]") ou apresentar o programa. Nada da demonstração vai para o histórico. Sem disciplinas cadastradas, são usadas FGA0211-01 e MAT0025-02 como exemplo.

## Modo Somente Monitoramento

O robô observa as disciplinas e avisa quando encontrar vaga (por notificação e/ou no dashboard), mas **nunca tenta se matricular sozinho**. Use esse modo se você só quer ficar de olho, ou se quer decidir manualmente quando confirmar a matrícula.

## Dashboard

Acompanha a execução em tempo real. Na Interface Web ele tem quatro abas:

- **Visão geral** — a etapa atual ("Fazendo login 3 de 8", "Monitorando 2 disciplinas…"), números principais com tendência do último minuto, e um cartão por **disciplina** com o estado dela (buscando, sem vagas, vaga vista, tentando matricular, matriculada, bloqueada, departamento indisponível), as vagas da última leitura e quando foi. Mostra também a **saúde da conexão** com a causa provável em linguagem simples (sua internet? o SIGAA lento? login? departamento?) e os **erros por tipo**, cada um com o que fazer.
- **Gráficos** — tempo de resposta do SIGAA (mediana e 95º percentil), buscas por segundo, vagas por disciplina ao longo do tempo, erros por tipo ao longo do tempo e a distribuição dos tempos de resposta. Escolha o período (5 min, 15 min, 1 hora ou a execução inteira). Passe o mouse — ou selecione o gráfico com Tab e use as setas — para ler cada ponto; "Ver dados em tabela" mostra os mesmos números sem depender de cores.
- **Workers** — o estado real de cada worker (fazendo login, buscando, aguardando após falha…) e as falhas de cada um, por tipo.
- **Linha do tempo** — a história da execução em ordem: início, verificação prévia, logins, vagas, cada etapa de cada tentativa de matrícula, pausas, proteção de carga, alertas e erros — sem as milhares de buscas "sem vaga". Eventos repetidos em sequência viram um item só ("×20"). Filtre por tipo de evento, veja só a última hora ou os últimos 15 minutos, e escolha uma execução anterior (enquanto ela ainda estiver no log).

**Tentativas de matrícula:** cada tentativa ganha um identificador e o tempo de cada etapa (turma selecionada → tela de confirmação → formulário preenchido → confirmação enviada) e o tempo total desde a vaga vista. A Visão geral mostra as tentativas mais recentes; na linha do tempo, **Ver etapas** abre o detalhe.

**Alertas de problema:** o programa avisa (no Dashboard, na central de avisos e, se você quiser, no Telegram/ntfy) quando algo parece errado — muitos erros por alguns minutos, o SIGAA sem responder, nenhuma busca acontecendo, respostas muito mais lentas que o normal ou uma página de manutenção do SIGAA — e avisa de novo quando normaliza. Nunca dispara com a execução pausada. Os limites ficam em Configurações Avançadas → Alertas de problema.

**Worker travado:** se um worker ficar muito tempo sem nenhum progresso (bem mais que qualquer espera normal), ele é recriado automaticamente. Um worker no meio de uma tentativa de matrícula nunca é interrompido.

Ao terminar uma execução, o botão **📋 Resumo da execução** mostra o que aconteceu: duração, resultado de cada disciplina, buscas, vagas vistas, tentativas e erros. Uma cópia de cada resumo fica em `data/relatorios/` (os 50 mais recentes).

A interface gráfica mostra o mesmo, exceto os gráficos (que ficam na Web). No terminal, o painel ao vivo inclui a tabela de disciplinas, e o resumo é impresso quando a execução termina.

Qualquer número que o programa não consiga calcular com confiança aparece como "sem dados" em vez de mostrar um valor inventado.

**Sem execução em andamento:** o Dashboard mostra **"⚪ Nenhuma execução em andamento"** e fica parado — nenhum tempo corre, nenhum worker aparece "sem atividade", nenhum alerta surge. Uma execução anterior nunca é mostrada como se fosse a atual.

**Carregar dados da última execução ao abrir** (Config. Avançadas → Execução, na Web e na interface gráfica; no terminal, Configurações → [13]): desligado por padrão — o Dashboard e os Logs abrem limpos, e as execuções anteriores continuam na tela Histórico. Ligado, o Dashboard e os Logs abrem com os dados da última execução, marcados como **"📂 Última execução (recuperada)"**, congelados (o tempo não avança) e nunca com aparência de execução ativa. Ao iniciar uma nova execução, o painel passa a mostrar só ela.

## Histórico

Cada execução encerrada é gravada no computador (`data/historico.db`) — sem credenciais, só disciplinas, contagens e tempos. Se esse arquivo for danificado (desligamento no meio de uma gravação, por exemplo), o programa guarda a cópia danificada como `historico.db.corrompido-<data>` e começa um histórico novo, sem travar. Na Interface Web, a tela **🗂️ Histórico** mostra:

- totais do período escolhido (7, 30, 90 dias ou tudo), com filtro por disciplina;
- **vagas vistas por dia** e **horas monitoradas por dia**;
- **quando as vagas abrem**: um mapa de calor de dia da semana × hora com quantas vezes uma vaga surgiu. É estatística do seu próprio histórico, não garantia — serve para concentrar o monitoramento nos horários úteis e buscar menos no resto do tempo;
- a lista de execuções: **Ver** abre o relatório completo (com botão **Imprimir / salvar PDF**, que usa o "Salvar como PDF" do próprio navegador); marque duas e use **Comparar** para ver as configurações e resultados lado a lado;
- **Exportar** gera planilhas CSV (abrem direto no Excel) ou JSON, respeitando os filtros.

**Horários em que as vagas costumam surgir:** para cada disciplina com dados suficientes, a tela mostra a faixa de horário que concentrou a maior parte das vagas no período (ex: "70% das vagas de FGA0211-01 surgiram entre 8h e 10h") e sugere uma janela diária. **Usar como janela diária** a aplica às próximas execuções. É estatística do seu histórico — nunca garantia.

**Ações registradas:** a mesma tela lista o que foi feito e quando — aceite do aviso legal (com a versão do texto aceito), início e parada de execuções, mudanças de configuração (de quanto para quanto, quando não é dado sensível), perfis aplicados, importações… Nunca guarda senha, CPF ou tokens. No terminal: Diagnóstico → Histórico → **[A]**.

A Central de Logs também exporta os eventos filtrados em CSV. Na interface gráfica há a aba **Histórico** (lista, relatório e exportação); no terminal, **Diagnóstico → Histórico de execuções** (a exportação vai para `data/exportacoes/`).

Em **Config. Avançadas** você pode desligar o histórico ou mudar quantos dias ele guarda (padrão: 180; 0 guarda para sempre). **Apagar histórico** remove o banco inteiro.

## Notificações (opcional)

O programa funciona perfeitamente sem nenhuma notificação configurada. Se quiser, você pode ativar:

- **Telegram:** avisa por mensagem no Telegram. Veja o botão "Como configurar?" na aba de Notificações.
- **ntfy:** avisa por um app/site gratuito de notificações push.
- **Alarme sonoro:** toca um som no computador quando encontra vaga.

Além de vagas e matrículas, você pode receber **alertas de problema**, o aviso de **worker recriado**, um **resumo periódico** ("está tudo bem?": buscas, vagas, erros e alertas das últimas horas — o intervalo é ajustável, padrão 6 horas) e um **resumo ao encerrar**. Marque só o que quiser em "Quais eventos notificar".

Também há três canais que não dependem de aplicativos de terceiros:

- **Notificação do Windows:** um aviso na área de notificações, sem configurar nada.
- **Webhook:** envia para um canal do Discord, do Slack ou para qualquer endereço que receba JSON. No Discord: configurações do canal → Integrações → Webhooks → Novo webhook → Copiar URL. A URL precisa começar com `https://`, funciona como uma senha do canal e é tratada como segredo.
- **E-mail:** pelo servidor SMTP da sua conta. Informe servidor (ex: `smtp.gmail.com`), porta (587 com STARTTLS ou 465 com SSL), usuário, senha, destinatário e, se quiser, um **remetente** diferente do usuário. Gmail e Outlook exigem uma **"senha de app"** (não a senha normal da conta). A senha é enviada sempre com conexão criptografada.

Webhook e e-mail têm o botão **Como configurar?** com o passo a passo. A configuração é conferida **antes** de ser salva (endereços de e-mail, porta, servidor, URL) e nada é alterado se houver erro. Use **Testar** para enviar uma mensagem de teste; o resultado diz se funcionou ou o que falhou, sem nunca mostrar a senha ou a URL.

Por padrão, os segredos de notificação (token do Telegram, tópico do ntfy, URL do webhook, senha do e-mail) também não são salvos em disco — só o restante da configuração (quais canais estão ativos, quais eventos notificam). Há uma opção explícita para salvá-los localmente se você preferir não redigitar toda vez — no Windows, eles ficam **cifrados com a proteção de dados do Windows**, atrelada à sua conta: uma cópia do arquivo em outro computador não pode ser lida.

## Configurações Avançadas

Fica separada da tela principal de propósito. Lá você ajusta: quantidade de workers, intervalo entre buscas, timeout de requisição, e os limites de tamanho/retenção de logs e do arquivo JSON de auditoria.

**Perfil de carga:** em vez de adivinhar workers e intervalo, escolha um perfil pronto — **Leve** (4 workers, 1,5 s), **Moderado** (8 workers, 0,8 s) ou **Intenso** (20 workers, 0,3 s, o padrão original). O programa mostra a **carga estimada** em requisições por segundo e avisa quando ela é alta. Cargas altas pesam no SIGAA e aumentam o risco de bloqueio; para só acompanhar vagas, o perfil Leve costuma bastar. A estimativa também aparece na lista "Pronto para iniciar?" da Execução e na barra de status da interface gráfica.

Quando o login ou a preparação de um departamento falham várias vezes seguidas (SIGAA fora do ar, fora do período de matrícula), o programa **espera cada vez mais entre as tentativas** (até 30 s) em vez de repetir sem parar. Se o SIGAA **recusar o login** (senha errada), ele não insiste — repetir poderia bloquear sua conta — e a execução é encerrada com uma mensagem clara.

**Perfis:** guarde cenários prontos — por exemplo "Acompanhar (calmo)" e "Semana de matrícula" — com modo, desempenho, proteção, janela, alertas, notificações e disciplinas, e troque de um para outro com um clique (no terminal: Configurações → [9]). Aplicar um perfil **nunca liga a matrícula real**: o DRY RUN continua como está.

**Versões anteriores:** cada alteração de configurações ou de disciplinas guarda a versão anterior (as 20 mais recentes de cada). **Restaurar** volta para uma delas — e a versão atual também fica guardada, então dá para desfazer.

**Aparência da interface gráfica:** tema claro, escuro ou seguindo o Windows, e tamanho da fonte (80% a 160%). Vale ao reabrir a interface gráfica. Na Web, o botão **🔠 Exibição** ajusta a densidade (compacta mostra mais linhas por tela) e o tamanho do texto, só naquele navegador.

**Encerrar a sessão da Web por inatividade:** em Configurações Avançadas → Interface Web, escolha depois de quantos minutos sem uso a Interface Web apaga as credenciais da memória e passa a exigir o novo link mostrado no terminal. Nunca acontece com uma execução em andamento. O padrão é não expirar.

## Diagnóstico

Roda verificações de: versão do Python, bibliotecas instaladas, espaço em disco, tamanho dos logs, integridade da configuração, **configurações inseguras** e conectividade com o SIGAA. O relatório nunca inclui suas credenciais.

Na mesma tela:

- **🧭 Assistente de solução de problemas** — escolha o que está acontecendo ("o login não funciona", "não encontra minha turma", "nunca aparece vaga", "muitos erros", "achou vaga mas não confirma", "parou sozinho"). O assistente cruza a execução atual (ou a última gravada), os erros, os alertas, a verificação prévia e a sua configuração e mostra a causa provável — marcada como *Confirmado*, *Provável* ou *Verifique* — com a evidência e o que fazer.
- **🔒 Configurações de segurança** — avisa sobre Interface Web aberta para a rede, endereços do SIGAA fora de `unb.br`, proteção de carga desligada, tokens de notificação salvos, pasta do programa sincronizada com a nuvem (OneDrive, Dropbox…) e matrícula real ligada. Os mais importantes também aparecem em "Pronto para iniciar?" na tela Execução.
- **💡 Recomendações de configuração** — depois de uma execução com métricas suficientes, sugere ajustes como aumentar o timeout (quando muitas buscas esgotam o tempo) ou usar menos workers (quando os extras não trazem ganho ou o SIGAA mostra sobrecarga). **Aplicar** passa pela mesma validação do formulário.
- **📄 Páginas capturadas** — quando uma página do SIGAA não vem como esperado, ela é guardada para diagnóstico **já com matrícula, CPF, nome, data de nascimento, e-mail e valores de formulário mascarados (`***`)**. Aqui você lê o texto dela, sem abrir o HTML.
- **📦 Pacote de suporte** — um `.zip` para pedir ajuda: versão, diagnóstico, configuração (sem segredos), os últimos eventos do log e as páginas capturadas, tudo mascarado. A lista do conteúdo aparece antes de baixar. Confira antes de compartilhar: um nome solto numa página pode escapar do mascaramento.

Em **Configurações Avançadas → URLs do SIGAA**, o botão **Testar endereços** confere se cada endereço responde (sem fazer login). Endereços fora de `unb.br` não são acessados.

No terminal, **Diagnóstico → Ver eventos recentes** mostra os últimos eventos do log em linguagem simples (a mesma tradução da Central de Logs), com filtro por texto e por categoria; **[6]** abre o assistente e as recomendações, **[7]** as páginas capturadas e **[8]** gera o pacote de suporte em `data/exportacoes/`. Na interface gráfica, os mesmos recursos ficam em botões na aba Diagnóstico.

## Modo terminal (e interface gráfica)

Todas as funções também estão disponíveis sem abrir a interface gráfica, navegando só por números — sem precisar digitar comandos. Em **Configurações** o terminal também edita disciplinas, guarda os tokens de notificação (opcional), exporta/importa a configuração (**[11]**), restaura os padrões (**[12]**) e ajusta a Interface Web e os arquivos de log (**[13]**).

Durante uma execução pelo terminal ([2] ou [3]), a tela mostra um **painel ao vivo** (tráfego, workers, vagas e erros) em vez de linhas de log rolando. Teclas:

- **Q** — para com segurança (o mesmo "Parar" da interface: espera os workers atuais encerrarem);
- **D** — alterna entre o painel e as linhas de log;
- **P** — pausa ou retoma as buscas (as sessões continuam abertas).

O log continua sendo gravado em `data/sigaa_sniper_audit.json` o tempo todo. Se a entrada do terminal não for interativa (ex: redirecionada), o programa mostra as linhas de log e para com `Ctrl+C`, como antes.

Na interface gráfica, uma **barra de status** no topo de todas as abas mostra se o programa está parado ou em execução, e em qual modo — a matrícula real (DRY RUN desligado) aparece em vermelho.

## Tour pela interface

Depois de concluir o assistente de primeira execução, a Interface Web mostra um tour rápido apontando onde acompanhar cada coisa. Para ver de novo: **Ctrl+K → "Tour pela interface"**.

## Atualização

Para atualizar, basta substituir os arquivos do programa por uma versão nova, mantendo as pastas `config/` (suas disciplinas e preferências) e `logs/`/`data/` se quiser manter o histórico. Nenhuma credencial precisa ser migrada — você digita de novo na próxima execução.

**Saber se há versão nova:** em **Sobre**, o botão **Verificar se há versão nova** faz uma única consulta ao repositório oficial no GitHub e avisa se existe uma versão mais recente, com o link — nada é baixado nem instalado sozinho. Na Web dá para ligar a verificação automática ao abrir (desligada por padrão).

**Conferir se o executável é o legítimo:** a tela **Sobre** mostra a impressão digital (SHA-256) do executável em uso. Compare com o arquivo `SHA256SUMS.txt` que acompanha o pacote (ou gere no Windows com `certutil -hashfile SIGAA-Sniper.exe SHA256`). Se forem diferentes, não use esse arquivo.

## Segurança

Veja o guia separado: `SEGURANCA.md` (também disponível na aba Ajuda → Segurança e privacidade da interface).
