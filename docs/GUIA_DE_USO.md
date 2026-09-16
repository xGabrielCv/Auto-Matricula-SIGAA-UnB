# Guia de Uso — SIGAA Sniper

## Instalação

1. Instale o Python 3.9 ou mais recente (https://www.python.org/downloads/), marcando "Add Python to PATH" durante a instalação.
2. Coloque a pasta do SIGAA Sniper em qualquer lugar do seu computador (Desktop, Downloads, pendrive — não importa).
3. Dê duplo clique em `run.bat`. Ele confere se o Python e as bibliotecas necessárias (httpx, beautifulsoup4, rich) estão instaladas e instala automaticamente o que faltar.

## Primeira execução

Ao abrir, você verá um menu numerado:

```
[1] Interface gráfica
[2] Matrícula automática
[3] Somente monitoramento
[4] Configurações
[5] Diagnóstico
[6] Sair
```

Recomendado para a primeira vez: escolha **[1] Interface gráfica** — é mais fácil configurar tudo por lá.

## Credenciais

Toda vez que você abrir o programa, ele vai pedir sua matrícula, senha, CPF e data de nascimento do SIGAA. **Isso é proposital: o programa nunca salva essas informações em disco.** Elas ficam só na memória enquanto o programa está aberto e são apagadas quando você fecha.

## Disciplinas

Cadastre as disciplinas que quer acompanhar: código (ex: `FGA0211`), turma (ex: `01`) e o ID do departamento. O ID do departamento aparece na página de matrícula extraordinária do SIGAA quando você escolhe a unidade/departamento da disciplina — cada departamento tem um número diferente.

Essas informações **não são sensíveis** e ficam salvas em `config/disciplinas.json` para você não ter que digitar tudo de novo.

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

## Modo Somente Monitoramento

O robô observa as disciplinas e avisa quando encontrar vaga (por notificação e/ou no dashboard), mas **nunca tenta se matricular sozinho**. Use esse modo se você só quer ficar de olho, ou se quer decidir manualmente quando confirmar a matrícula.

## Dashboard

Mostra em tempo real: requisições por segundo, latência, disciplinas monitoradas, vagas encontradas, estado de cada "worker" (atirador), erros recentes e histórico de eventos. Está disponível tanto na aba "Dashboard" da interface gráfica quanto como painel de terminal independente.

Qualquer número que o programa não consiga calcular com confiança aparece como "sem dados" em vez de mostrar um valor inventado.

## Notificações (opcional)

O programa funciona perfeitamente sem nenhuma notificação configurada. Se quiser, você pode ativar:

- **Telegram:** avisa por mensagem no Telegram. Veja o botão "Como configurar?" na aba de Notificações.
- **ntfy:** avisa por um app/site gratuito de notificações push.
- **Alarme sonoro:** toca um som no computador quando encontra vaga.

Por padrão, o token do Telegram e o tópico do ntfy também não são salvos em disco — só o restante da configuração (quais canais estão ativos, quais eventos notificam). Há uma opção explícita para salvá-los localmente se você preferir não redigitar toda vez.

## Configurações Avançadas

Fica separada da tela principal de propósito. Lá você ajusta: quantidade de workers, intervalo entre buscas, timeout de requisição, e os limites de tamanho/retenção de logs e do arquivo JSON de auditoria.

## Diagnóstico

Roda verificações de: versão do Python, bibliotecas instaladas, espaço em disco, tamanho dos logs, integridade da configuração e conectividade com o SIGAA. O relatório nunca inclui suas credenciais.

## Modo terminal

Todas as funções também estão disponíveis sem abrir a interface gráfica, navegando só por números — sem precisar digitar comandos.

## Atualização

Para atualizar, basta substituir os arquivos do programa por uma versão nova, mantendo as pastas `config/` (suas disciplinas e preferências) e `logs/`/`data/` se quiser manter o histórico. Nenhuma credencial precisa ser migrada — você digita de novo na próxima execução.

## Segurança

Veja o guia separado: `SEGURANCA.md` (também disponível na aba Ajuda → Segurança e privacidade da interface).
