# Segurança e Privacidade

## O que NUNCA é salvo em disco

- Matrícula, senha, CPF e data de nascimento do SIGAA.
- Token de bot e Chat ID do Telegram (a menos que você marque explicitamente "Salvar neste computador").
- Tópico do ntfy (mesma regra acima).

Isso vale também para a configuração inicial guiada: o que você digita nas etapas de credenciais fica só na memória. Essas informações existem apenas na memória do processo Python enquanto o programa está aberto (veja `app/core/credentials.py`). Ao fechar o programa — pela GUI, pelo terminal, ou com Ctrl+C — elas são sobrescritas e descartadas.

## O que É salvo em disco (e por quê)

| Arquivo | Conteúdo | Sensível? |
|---|---|---|
| `config/settings.json` | modo de execução, workers, intervalos, timeouts, preferências de notificação (quais canais/eventos; do e-mail, servidor, porta, usuário, remetente e destinatário — nunca a senha), limites de log, se a configuração inicial já foi concluída | Não — os endereços de e-mail do canal de notificação são seus, mas não são credenciais. |
| `config/disciplinas.json` | código, turma, departamento, professor das disciplinas cadastradas | Não |
| `config/notificacoes.secrets.json` | token do Telegram, chat ID, tópico do ntfy, URL do webhook, senha do e-mail | **Sim — só existe se você marcar "Salvar neste computador" explicitamente.** No Windows é **cifrado com a proteção de dados do Windows (DPAPI)**, atrelado à sua conta: copiado para outro computador ou outra conta, não pode ser lido. Onde a DPAPI não está disponível, fica em texto simples — e o Diagnóstico avisa. Arquivos antigos, em texto simples, continuam sendo lidos e passam a ser cifrados no próximo salvamento. |
| `config/historico/*.json` | versões anteriores de `settings.json` e `disciplinas.json` (as 20 mais recentes de cada), para desfazer alterações | Não — o mesmo conteúdo dos arquivos acima. |
| `config/perfis/*.json` | perfis salvos por você (modo, desempenho, notificações sem segredos, disciplinas) | Não. |
| `config/departamentos.json` | lista de departamentos lida da página pública do SIGAA (sem login) | Não. |
| `data/auditoria.jsonl` | ações registradas: aceite do aviso legal (com a versão do texto), início/parada, mudanças de configuração, perfis… | Não — nunca inclui senha, CPF, nascimento, tokens nem URLs de webhook; de configurações sensíveis só o nome da chave. |
| `logs/*.log`, `data/*.json` | logs de execução (mensagens do robô, latências, eventos). Os campos estruturados do log vêm de uma lista fechada (evento, disciplina, turma, vagas, tempos…) — qualquer outro nome é descartado antes de gravar | Não deveria conter credenciais — se encontrar algum dado sensível num log, é um bug, avise. |
| `data/historico.db` | histórico das execuções (SQLite): resumos, mudanças na quantidade de vagas de cada disciplina, buscas/tempos/erros por minuto. Guardado por 180 dias (configurável; pode ser desligado ou apagado) | Não — nenhuma credencial; só códigos de disciplina, contagens e tempos. |
| `data/historico.db.corrompido-*` | cópia de um histórico que estava danificado, separada automaticamente para o programa seguir funcionando | Não — o mesmo tipo de conteúdo do histórico. Pode ser apagada. |
| `data/relatorios/*.json` | resumo de cada execução: duração, modo, resultado de cada disciplina, contagens de buscas/vagas/erros, configuração de desempenho usada (os 50 mais recentes) | Não — só códigos de disciplina e contagens. |
| `logs/debug_*.html` | páginas HTML capturadas quando uma página do SIGAA não vem como esperado, para diagnóstico | Gravadas **já mascaradas**: matrícula, CPF, data de nascimento, senha, e-mail, valores de todos os campos de formulário e o bloco com o seu nome viram `***`. Se o mascaramento falhar, a página não é gravada. Um nome que apareça solto em outro ponto da página pode escapar — por isso confira antes de compartilhar. Apagadas automaticamente após alguns dias. |
| `data/exportacoes/*.zip` | pacotes de suporte gerados por você (Diagnóstico → Pacote de suporte) | Não contêm senha, CPF, nascimento nem tokens; eventos e páginas vão mascarados. |

## Interface Web: por que ela é segura de usar

- O servidor escuta apenas em `127.0.0.1` (este computador). Nenhum outro computador da rede consegue acessá-lo, a menos que você mude o endereço em Configurações Avançadas — nesse caso o terminal mostra um aviso.
- Cada execução gera uma **chave de acesso aleatória**, incluída no link aberto no navegador. Sem ela, nenhuma função responde.
- A página recusa chamadas vindas de outros sites (verificação do cabeçalho `Host`, cabeçalho de segurança obrigatório e política de conteúdo restritiva), então um site malicioso aberto no mesmo navegador não consegue comandar o programa.
- As credenciais digitadas na página continuam só em memória, como na GUI e no terminal. A senha nunca é enviada de volta ao navegador.

## Sessão da Interface Web por inatividade

Opcionalmente (Configurações Avançadas → Interface Web), depois de alguns minutos sem uso e **sem execução em andamento**, a Interface Web apaga as credenciais da memória, troca a chave de acesso (o link e a página antiga deixam de funcionar) e mostra um novo link no terminal. As consultas automáticas da página não contam como uso — só cliques, teclas e ações.

## Modo demonstração

No modo demonstração nenhuma requisição sai do computador: o SIGAA é simulado localmente, as credenciais são fictícias, o DRY RUN fica ligado e nada entra no histórico.

## Alertas de configuração insegura

O Diagnóstico (e a lista "Pronto para iniciar?") avisa quando a Interface Web está aberta para outros aparelhos da rede, quando algum endereço do SIGAA aponta para fora de `unb.br` (suas credenciais seriam enviadas para lá), quando a proteção de carga está desligada, quando há tokens de notificação salvos em disco, quando a pasta do programa está sincronizada com a nuvem e quando a matrícula real está ligada. O botão **Testar endereços** nunca acessa endereços fora de `unb.br`.

## Como excluir seus dados

Para remover completamente qualquer traço de configuração: apague as pastas `config/`, `logs/` e `data/`. O programa recria tudo do zero (sem disciplinas cadastradas, configurações padrão) na próxima execução.

## Como compartilhar o projeto com outra pessoa

1. Apague (ou nunca compartilhe) as pastas `config/`, `logs/` e `data/` — são específicas da sua conta e do seu histórico de uso.
2. A pasta `legacy/` contém versões antigas do projeto; todas as credenciais reais que existiam nelas foram substituídas por textos como `SEU_USUARIO`, `SUA_SENHA`, `SEU_CPF` etc. durante a reorganização deste projeto. Ainda assim, se for redistribuir, prefira remover `legacy/logs_historicos/` (arquivos de log antigos, pesados e sem utilidade para quem recebe).
3. O código em `app/` nunca teve credenciais reais — só nomes de variáveis e placeholders.

## O que nunca colocar no código

Nunca escreva senha, CPF, matrícula, token de bot ou chat ID diretamente em nenhum arquivo `.py`, `.json` ou `.md` deste projeto — nem "temporariamente para testar". Use sempre os campos da interface/terminal, que mantêm esses dados só em memória.

## Histórico de segurança deste projeto

Durante a reorganização registrada neste repositório, foram encontradas e removidas credenciais reais (SIGAA e um token de bot do Telegram) hardcoded em 8 arquivos legados. Se você é o autor original: **considere revogar o token do Telegram que ficou exposto em texto puro** (crie um novo bot ou gere um novo token pelo @BotFather), já que ele pode ter ficado visível para qualquer pessoa com acesso a essa pasta antes da limpeza.
