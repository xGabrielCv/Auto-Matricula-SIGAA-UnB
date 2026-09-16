# Segurança e Privacidade

## O que NUNCA é salvo em disco

- Matrícula, senha, CPF e data de nascimento do SIGAA.
- Token de bot e Chat ID do Telegram (a menos que você marque explicitamente "Salvar neste computador").
- Tópico do ntfy (mesma regra acima).

Essas informações existem apenas na memória do processo Python enquanto o programa está aberto (veja `app/core/credentials.py`). Ao fechar o programa — pela GUI, pelo terminal, ou com Ctrl+C — elas são sobrescritas e descartadas.

## O que É salvo em disco (e por quê)

| Arquivo | Conteúdo | Sensível? |
|---|---|---|
| `config/settings.json` | modo de execução, workers, intervalos, timeouts, preferências de notificação (quais canais/eventos), limites de log | Não |
| `config/disciplinas.json` | código, turma, departamento, professor das disciplinas cadastradas | Não |
| `config/notificacoes.secrets.json` | token do Telegram, chat ID, tópico do ntfy | **Sim — só existe se você marcar a opção "Salvar neste computador" explicitamente; não é criptografado.** |
| `logs/*.log`, `data/*.json` | logs de execução (mensagens do robô, latências, eventos) | Não deveria conter credenciais — se encontrar algum dado sensível num log, é um bug, avise. |
| `logs/debug_*.html` | páginas HTML capturadas quando o parser falha, para diagnóstico | Pode conter sua matrícula (o SIGAA a inclui nas páginas). Apagados automaticamente após alguns dias. |

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
