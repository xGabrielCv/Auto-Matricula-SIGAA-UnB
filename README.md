# 🤖 SIGAA Sniper — Auto-Matrícula SIGAA (UnB)

<p align="center">

**Automação, monitoramento e gerenciamento de matrícula no SIGAA da UnB**

Interface Web • Interface gráfica • Terminal • Dashboard • Monitoramento • Notificações • DRY RUN • Diagnóstico

<br>

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=for-the-badge\&logo=python\&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge\&logo=windows\&logoColor=white)](#requisitos)
[![Web](https://img.shields.io/badge/Interface%20Web-recomendada-1D4ED8?style=for-the-badge)](#-interface-web)
[![GUI](https://img.shields.io/badge/GUI-Tkinter-FFCA28?style=for-the-badge)](#interface)
[![Tests](https://img.shields.io/badge/Tests-62%20passing-2EA44F?style=for-the-badge)](#-testes)
[![License](https://img.shields.io/badge/License-Open%20Source-blue?style=for-the-badge)](#licença)

</p>

> [!WARNING]
>
> ## ⚠️ Aviso importante — leia antes de utilizar
>
> Este projeto é uma **prova de conceito (PoC) e ferramenta educacional**, desenvolvida para estudo de engenharia de software, automação e integração com aplicações web.
>
> O projeto **não possui vínculo, afiliação, autorização ou endosso da Universidade de Brasília (UnB), do STI ou do SIGAA**.
>
> O uso de automação para acessar sistemas autenticados ou realizar operações acadêmicas pode estar sujeito aos Termos de Uso do SIGAA, às políticas institucionais de segurança e às normas acadêmicas da universidade.
>
> O usuário é **integralmente responsável** por todas as consequências decorrentes da utilização do software, incluindo eventuais bloqueios de conta, falhas de autenticação, solicitações de matrícula inválidas, perda de vagas, interrupções de serviço ou consequências administrativas e acadêmicas.
>
> O uso deve ser **ético e responsável**. Requisições excessivas, concorrência inadequada ou utilização abusiva podem sobrecarregar a infraestrutura do SIGAA e prejudicar outros estudantes.
>
> **Nunca utilize o software para tentar contornar filas, regras, mecanismos de segurança ou limitações impostas pelo sistema.**
>
> Para quem deseja apenas acompanhar a disponibilidade de vagas, o projeto possui um **modo de somente monitoramento**, destinado a separar essa finalidade da execução de matrícula.

---

## 📌 Sobre o projeto

O **SIGAA Sniper** é a evolução do projeto **Auto-Matrícula SIGAA (UnB)**, reorganizado a partir da versão funcional anterior e expandido com uma arquitetura modular.

A versão atual reúne em uma única aplicação:

* 🌐 Interface Web local (modo recomendado);
* 🖥️ Interface gráfica;
* 💻 Interface de terminal;
* 📊 Dashboard em tempo real;
* 👀 Monitoramento de disponibilidade;
* 📝 Automação do fluxo de matrícula;
* 🔔 Notificações;
* 🧪 DRY RUN;
* 🩺 Diagnóstico do sistema;
* 📋 Central de logs;
* ⚙️ Configurações persistentes;
* 🧰 Recursos experimentais isolados;
* 🔐 mecanismos de proteção e sanitização;
* 📚 documentação e ajuda contextual.

O objetivo da refatoração foi **preservar a lógica funcional existente**, enquanto a aplicação foi reorganizada para facilitar manutenção, testes, diagnóstico e evolução futura.

---

# 🧭 Três modos de execução

Ao abrir o programa (`SIGAA-Sniper.exe`, `run.bat` ou `python main.py`), o aviso legal é exibido e, depois de aceito, aparece o menu:

```text
[0] 🌐 Interface Web  ★ RECOMENDADO — abre no navegador
[1] Interface gráfica
[2] Matrícula automática
[3] Somente monitoramento
[4] Configurações
[5] Diagnóstico
[6] Sair
```

| Modo | Como abrir | Para quem |
| --- | --- | --- |
| 🌐 **Interface Web — recomendado** | opção `[0]` | Uso do dia a dia: visual moderno, dashboard ao vivo, tudo em um só lugar, no navegador |
| 🖥️ **Interface gráfica (Tkinter)** | opção `[1]` | Quem prefere uma janela desktop tradicional |
| ⌨️ **Terminal** | opções `[2]` a `[5]` | Uso só com teclado, sem janelas |

Os três modos usam **o mesmo núcleo** (mesmo motor de matrícula, mesmas validações, mesmas configurações salvas) e continuam suportados. As opções `[1]` a `[6]` têm a mesma numeração das versões anteriores.

---

# ✨ Principais funcionalidades

### 🌐 Interface Web

Interface moderna no navegador, **local** (roda só no seu computador) e **recomendada** para o uso normal. Veja a seção [🌐 Interface Web](#-interface-web) para detalhes de uso e segurança.

* todas as telas da interface gráfica: Execução, Dashboard, Logs, Credenciais, Disciplinas, Notificações, Configurações Avançadas, Diagnóstico, Experimental, Ajuda e Sobre;
* assistente de primeira execução;
* aviso legal com as **mesmas 5 confirmações obrigatórias**;
* tema claro/escuro, layout responsivo (funciona também em telas pequenas) e navegação por teclado;
* sem dependências externas: HTML/CSS/JS embutidos no programa, funciona offline.

---

### 🖥️ Interface gráfica

Interface desktop desenvolvida com Tkinter/ttk, contendo:

* Dashboard;
* Configurações;
* Disciplinas;
* Departamentos;
* Notificações;
* Diagnóstico;
* Central de Logs;
* Ajuda;
* Recursos experimentais;
* Tela Sobre;
* Assistente de primeira execução.

A aplicação também possui validações e mensagens de orientação para configurações potencialmente incorretas.

---

### 💻 Terminal

O projeto pode ser utilizado diretamente pelo terminal através de um menu integrado:

```text
[0] 🌐 Interface Web  ★ RECOMENDADO — abre no navegador
[1] Interface gráfica
[2] Matrícula automática
[3] Somente monitoramento
[4] Configurações
[5] Diagnóstico
[6] Sair
```

Sempre que tecnicamente possível, os recursos disponíveis na GUI também são disponibilizados no modo terminal.

---

### 📊 Dashboard

O dashboard apresenta informações de execução e monitoramento de forma visual, incluindo:

* estado do programa;
* disciplinas monitoradas;
* disponibilidade de vagas;
* eventos recentes;
* notificações;
* informações de execução;
* indicadores de saúde;
* recursos do sistema.

---

### 👀 Somente monitoramento

O projeto possui um modo separado para **monitoramento de disponibilidade**, sem executar a confirmação de matrícula.

Esse modo permite acompanhar eventos relacionados às disciplinas configuradas sem utilizar o fluxo de matrícula automática.

> [!TIP]
> Se o seu objetivo for exclusivamente receber alertas de disponibilidade, prefira sempre o modo de monitoramento e evite utilizar funcionalidades de autenticação ou matrícula quando elas não forem necessárias.

---

### 🧪 DRY RUN

O modo `DRY RUN` permite executar o fluxo de teste sem efetivar a etapa final de confirmação da matrícula.

Ele possui uma **segunda camada independente de proteção**, reduzindo o risco de uma configuração incorreta transformar um teste em uma operação real.

> [!IMPORTANT]
> Utilize o `DRY RUN` durante os testes e validações antes de considerar qualquer operação real.

---

### 🔔 Notificações

O sistema possui suporte a canais de notificação configuráveis, incluindo recursos recuperados da versão anterior do projeto.

Entre eles:

* Telegram;
* ntfy;
* alarme sonoro.

As notificações podem ser configuradas individualmente conforme o evento.

---

### 📋 Central de Logs

A aplicação possui uma central dedicada para análise dos eventos de execução.

Inclui:

* filtros por nível;
* filtros por categoria;
* filtros por worker;
* pesquisa por texto;
* detalhes técnicos expansíveis;
* tradução de mensagens técnicas para linguagem mais simples;
* rotação automática;
* retenção configurável;
* limpeza de arquivos de debug.

Os logs também passam por mecanismos de sanitização para evitar exposição acidental de informações sensíveis.

---

### 🩺 Diagnóstico

O sistema possui uma ferramenta de diagnóstico em camadas para verificar problemas relacionados à execução.

Entre os recursos:

* dependências;
* configuração;
* diretórios;
* conectividade;
* ambiente;
* integridade da aplicação;
* saúde do sistema;
* informações relevantes para suporte.

O relatório de diagnóstico possui mecanismos adicionais de sanitização antes de ser copiado ou compartilhado.

---

### ⚙️ Configuração

As configurações podem ser gerenciadas pela GUI ou pelo terminal.

Incluem:

* disciplinas;
* turmas;
* departamentos;
* notificações;
* URLs;
* opções avançadas;
* parâmetros de execução;
* preferências do dashboard;
* restauração de padrões;
* porta, endereço e abertura automática do navegador da Interface Web.

A aplicação valida configurações antes da execução e possui mecanismos de importação, exportação, backup e migração de configuração.

---

### 🧰 Recursos experimentais

Funcionalidades recuperadas ou estudadas a partir de versões anteriores foram isoladas em uma área **Experimental**.

Entre os recursos experimentais/documentados estão:

* sincronização de relógio;
* retry com backoff;
* scheduler baseado em NTP;
* monitoramento utilizando Selenium;
* outras abordagens avaliadas durante a evolução do projeto.

Esses recursos são mantidos separados do caminho principal para evitar que uma funcionalidade experimental comprometa a execução normal da aplicação.

> [!CAUTION]
> Recursos experimentais podem exigir dependências adicionais e podem não funcionar em todos os ambientes.

---

# 🔐 Segurança e privacidade

A aplicação foi estruturada para reduzir a exposição de informações sensíveis.

Entre os cuidados implementados:

* 🔒 credenciais não são armazenadas permanentemente pela aplicação;
* 🧹 logs passam por sanitização;
* 🧹 diagnósticos passam por sanitização;
* 🚫 credenciais ocultas são rejeitadas durante importações;
* 🚫 tokens e dados pessoais não devem fazer parte da distribuição;
* 🛡️ mecanismos adicionais de proteção existem no `DRY RUN`;
* 📦 arquivos de distribuição passam por auditoria antes de serem disponibilizados.

Para informações detalhadas sobre armazenamento, configuração e compartilhamento seguro, consulte:

```text
docs/SEGURANCA.md
```

> [!IMPORTANT]
> Nunca publique credenciais, senhas, tokens, cookies, dados acadêmicos ou informações pessoais no repositório.

---

# ⚖️ Aviso legal

O aviso legal é apresentado **em toda inicialização da aplicação**.

A aceitação anterior não elimina a apresentação do aviso em execuções futuras.

Na GUI, o usuário deve confirmar os itens obrigatórios antes de continuar.

Na **Interface Web**, o aviso é exibido novamente no navegador a cada abertura, com as **mesmas 5 confirmações obrigatórias** (cada uma marcada individualmente; clicar no texto não marca a caixa, e o aviso não pode ser fechado sem aceitar ou recusar). Nenhuma função da Web responde antes do aceite.

No terminal, o programa exige uma confirmação explícita antes de prosseguir.

O aviso aborda:

1. finalidade exclusivamente educacional;
2. ausência de vínculo oficial com a UnB;
3. possíveis restrições dos Termos de Uso;
4. responsabilidade integral do usuário;
5. uso ético e preservação da infraestrutura;
6. modalidade de menor risco para monitoramento.

---

# 🚀 Uso rápido

```text
1. Baixe o SIGAA-Sniper.zip
2. Extraia
3. Dê duplo clique em SIGAA-Sniper.exe
4. Aceite o aviso legal e escolha [0] 🌐 Interface Web
```

O navegador abre sozinho com o programa. Existem duas formas principais de executar o projeto.

## Opção 1 — Executável

A forma mais simples no Windows é utilizar:

```text
SIGAA-Sniper.exe
```

O executável foi empacotado com PyInstaller e não exige uma instalação separada do Python, Node.js ou qualquer outro runtime para execução — tudo o que é necessário já está incorporado no próprio `.exe`.

O `SIGAA-Sniper.zip` contém apenas o necessário para uso: o executável, este README e a pasta `docs/`. A Interface Web e a ajuda já estão embutidas no `.exe`.

---

# 🌐 Interface Web

A Interface Web é o **modo recomendado**. Ela mantém as mesmas funcionalidades, validações, confirmações e avisos dos modos existentes, com uma experiência mais simples de usar.

**Como iniciar:** abra o programa, aceite o aviso legal no terminal e escolha **`[0] 🌐 Interface Web`**. O navegador padrão abre automaticamente.

**Endereço:** o terminal mostra algo como:

```text
  Endereço:  http://127.0.0.1:8765
  Abra ESTE link completo (contém a chave de acesso desta execução):

  http://127.0.0.1:8765/?chave=Abc123...
```

* Porta padrão: **8765**. Se estiver ocupada, o programa usa automaticamente uma das 10 seguintes e avisa no terminal.
* Se o navegador não abrir sozinho, copie o **link completo** (com `?chave=`) do terminal.
* Para encerrar: botão **⏻ Encerrar** na página ou **ENTER** no terminal. O programa volta ao menu e apaga as credenciais da memória.

**Funciona localmente:** o servidor é da própria biblioteca padrão do Python (nada extra para instalar) e escuta só em `127.0.0.1` — nenhum outro computador acessa. A página não carrega nada da internet; a conexão só é usada para falar com o SIGAA e, se ativados, Telegram/ntfy.

**Como alterar a porta:** em **Config. Avançadas → 🌐 Interface Web** (na própria Web ou editando `config/settings.json`):

```json
"web": { "host": "127.0.0.1", "porta": 8765, "abrir_navegador": true }
```

A mudança vale na próxima vez que a Interface Web for aberta. Mantenha `127.0.0.1`; qualquer outro endereço expõe o programa à rede (o terminal mostra um alerta nesse caso).

**Segurança:** chave de acesso aleatória a cada execução (vira um cookie `HttpOnly`/`SameSite=Strict`), bloqueio de chamadas vindas de outros sites (verificação de `Host`, cabeçalho obrigatório e `Content-Security-Policy`), e a senha nunca é enviada de volta à página. Detalhes em `docs/SEGURANCA.md`.

**Confirmações preservadas:** remover disciplina, código de departamento desconhecido, alteração de URLs, restaurar padrões, importar configuração, executar recurso experimental e sair com o monitor rodando pedem confirmação, como na GUI. A Web ainda pede uma **confirmação extra antes de iniciar uma matrícula real** (DRY RUN desligado).

---

## 🖥️ Executando em um Windows novo (sem ambiente de desenvolvimento)

Este passo a passo assume um computador Windows "limpo", sem Python nem nenhuma ferramenta de desenvolvimento instalada — por exemplo, ao copiar o projeto para o computador de outra pessoa.

### 1. Onde colocar o `.exe`

Copie a **pasta inteira do projeto** (não apenas o arquivo `SIGAA-Sniper.exe` sozinho) para o local desejado — Área de Trabalho, Documentos, um pendrive, etc. O programa cria as pastas `config/`, `data/` e `logs/` ao lado do `.exe` na primeira execução; qualquer pasta funciona, inclusive com espaços no nome ou em outra unidade (D:, E:, um pendrive...).

Não é necessário nenhum caminho fixo como `C:\Usuarios\...` — o programa descobre sozinho onde está instalado.

### 2. Como executar

Dê duplo clique em `SIGAA-Sniper.exe`. Uma janela de terminal abre com o aviso legal e depois o menu do programa. Escolha `[0]` para abrir a Interface Web no navegador (a janela do terminal precisa continuar aberta enquanto você usa a Web).

### 3. É preciso "Executar como administrador"?

**Não.** O programa não precisa de privilégios de administrador para nenhuma de suas funções (GUI, terminal, matrícula, monitoramento, notificações). Execute com duplo clique normal.

### 4. O Windows vai pedir alguma permissão?

Sim, é esperado que apareça uma ou ambas as telas abaixo — isso acontece com qualquer executável novo, não é exclusivo deste projeto:

* **"O Windows protegeu o computador" (SmartScreen)** — aparece porque o `.exe` é novo e não possui uma assinatura digital paga (ver seção sobre o Windows Defender, logo abaixo). Clique em **"Mais informações"** e depois em **"Executar assim mesmo"**, apenas se você confia na origem do arquivo (por exemplo, recebeu diretamente de quem gerou o `.exe`, ou baixou do repositório oficial no GitHub).
* **Firewall do Windows perguntando sobre acesso à rede** — o programa precisa de acesso à internet para falar com o SIGAA e, opcionalmente, com o Telegram/ntfy. Marque **"Redes privadas"** e clique em **"Permitir acesso"**.

Se o Windows Defender remover ou bloquear o arquivo em vez de apenas avisar, veja a seção **"Windows Defender identificou o executável como ameaça"** logo abaixo.

### 5. Existe alguma configuração inicial?

Sim, na primeira execução:

1. Um aviso legal é exibido — leia e confirme os itens para continuar (ver seção "Aviso legal" acima).
2. Um assistente de primeira execução ajuda a cadastrar suas credenciais do SIGAA e as disciplinas de interesse. Nenhuma dessas informações fica salva em disco a menos que você marque explicitamente para salvar (ver `docs/SEGURANCA.md`).

Não é necessário instalar nada além disso, nem editar arquivos de configuração manualmente.

### 6. Executando pelo Explorador de Arquivos

Basta navegar até a pasta onde o projeto foi colocado e dar duplo clique em `SIGAA-Sniper.exe`, como qualquer outro programa `.exe` do Windows.

### 7. Abrindo um terminal na pasta do programa (para diagnóstico)

1. Na pasta do projeto, clique na barra de endereço do Explorador de Arquivos (ou clique com o botão direito num espaço vazio da pasta e escolha "Abrir no Terminal", disponível no Windows 11 e no Windows 10 atualizado).
2. Digite `cmd` e pressione Enter na barra de endereço, se a opção acima não estiver disponível.
3. Com o terminal aberto na pasta, digite `SIGAA-Sniper.exe` e pressione Enter para rodar o programa vendo diretamente qualquer mensagem de erro no console.

### 8. Como saber se está funcionando corretamente

* A janela do terminal abre e mostra o cabeçalho "SIGAA SNIPER" seguido do aviso legal ou do menu numerado `[0]` a `[6]`.
* A opção `[5] Diagnóstico` roda uma verificação de dependências, configuração, diretórios e conectividade — se tudo aparecer certo ali, o programa está funcionando corretamente.
* As pastas `config/`, `data/` e `logs/` aparecem ao lado do `.exe` depois da primeira execução.

### 9. Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| Windows Defender apagou o `.exe` sozinho | Falso positivo do antivírus (comum em executáveis PyInstaller novos e sem assinatura digital paga) | Veja a seção seguinte |
| A janela abre e fecha instantaneamente | O programa encerrou por um erro antes de mostrar o menu | Abra pelo terminal (passo 7) para ver a mensagem de erro completa |
| "Não é possível acessar o SIGAA" no diagnóstico | Falta de conexão com a internet, ou o site do SIGAA está fora do ar | Verifique a conexão; tente novamente mais tarde |
| Emojis aparecem como `?` no terminal | Terminal Windows configurado com uma página de código antiga (cp1252) | Comportamento esperado e inofensivo — não afeta o funcionamento |
| A Interface Web mostra "Link de acesso necessário" | O endereço foi aberto sem a chave (ou é de uma execução anterior) | Copie o link completo exibido no terminal, com `?chave=` |
| A página da Interface Web diz "Interface Web encerrada" | O terminal foi fechado ou recebeu ENTER | Abra o programa de novo e escolha `[0]` |
| A pasta foi movida e o programa "esqueceu" as disciplinas configuradas | `config/`, `data/` ou `logs/` não foram copiadas junto com o `.exe` | Copie a pasta inteira do projeto, não apenas o `.exe` |

### 10. Sem dependências adicionais

Nenhuma instalação de Python, bibliotecas, runtimes (.NET, Node.js, Java, Visual C++ Redistributable adicional, etc.) é necessária para rodar `SIGAA-Sniper.exe`. Tudo o que o programa precisa para funcionar já está embutido no próprio arquivo.

**Limitação conhecida:** o executável foi compilado para **Windows 64-bit**. Ele não funciona em Windows 32-bit nem em outros sistemas operacionais (Linux, macOS) — nesses casos, use a Opção 2 (código-fonte) com Python instalado.

---

## 🛡️ Windows Defender identificou o executável como ameaça (falso positivo)

Executáveis gerados com PyInstaller — como o `SIGAA-Sniper.exe` — são um alvo frequente de **falsos positivos** de antivírus. Isso acontece porque, para funcionar sem exigir Python instalado, o `.exe` empacota o interpretador Python e as bibliotecas do programa dentro de um único arquivo e os extrai para uma pasta temporária a cada execução — um padrão que também é usado por alguns programas maliciosos, então mecanismos de heurística podem confundir os dois. Some-se a isso o fato de o arquivo ser novo e **não possuir uma assinatura digital paga** (um certificado de assinatura de código custa dinheiro e exige verificação de identidade do editor, o que está fora do escopo de um projeto educacional e gratuito).

Este projeto **não usa nenhuma técnica de ofuscação, compactação por UPX ou qualquer mecanismo de evasão de antivírus** — o executável é gerado com as opções padrão e recomendadas do PyInstaller (`tools/build_exe.bat` mostra exatamente como).

### O que fazer se isso acontecer

1. **Verifique a origem do arquivo.** Só prossiga se você obteve o `.exe` diretamente do repositório oficial no GitHub ou de alguém em quem confia — nunca de um link ou anexo desconhecido.
2. **Confirme que é o executável legítimo.** No repositório oficial, o arquivo `SIGAA-Sniper.exe` tem o mesmo tamanho e nome descritos neste README; se quiser mais garantia, gere o `.exe` você mesmo a partir do código-fonte com `tools/build_exe.bat` (assim você sabe exatamente o que foi empacotado).
3. **Veja a detecção no Windows Security:** abra `Segurança do Windows` → `Proteção contra vírus e ameaças` → `Histórico de proteção`, localize a entrada referente ao `SIGAA-Sniper.exe` e veja o nome da ameaça detectada.
4. **Se confiar no arquivo, adicione uma exclusão específica** (nunca desative o Defender por completo):
   1. Abra `Segurança do Windows` → `Proteção contra vírus e ameaças`.
   2. Em `Configurações de proteção contra vírus e ameaças`, clique em `Gerenciar configurações`.
   3. Role até `Exclusões` e clique em `Adicionar ou remover exclusões`.
   4. Clique em `Adicionar uma exclusão` → `Pasta` (ou `Arquivo`, se preferir excluir só o `.exe`).
   5. Selecione **apenas a pasta deste projeto** (ex.: `C:\Users\SeuUsuario\Documents\SIGAA-Sniper`) — nunca uma pasta genérica como `C:\` ou `Downloads` inteira.
   6. Confirme. O Defender para de escanear (e de remover) arquivos dentro dessa pasta específica.
5. **Se o arquivo já tiver sido removido**, restaure-o pelo histórico de proteção (`Ações` → `Restaurar`) antes ou depois de criar a exclusão, ou copie o `.exe` novamente para a pasta.

### Riscos de criar uma exclusão

Uma exclusão diz ao Windows Defender para **parar de verificar** os arquivos daquela pasta. Isso significa que, se algum dia um arquivo realmente malicioso for colocado nessa mesma pasta (por exemplo, por engano, ou por outro programa), o Defender não vai detectá-lo. Por isso:

* Exclua **apenas a pasta deste projeto**, nunca pastas amplas como toda a pasta de Downloads ou todo o disco `C:\`.
* Não guarde outros arquivos dentro da pasta do projeto além dos que vieram com ele.
* **Nunca desative completamente o Windows Defender ou o Windows Security** — isso remove toda a proteção do computador contra qualquer ameaça real, não só falsos positivos deste programa.

### Como remover a exclusão depois

Repita os passos 1–3 acima, mas na lista de `Exclusões` selecione a entrada da pasta do projeto e clique em `Remover`.

### Ajudando a resolver isso de forma definitiva

Falsos positivos como este podem ser reportados diretamente à Microsoft, que analisa o arquivo e, se confirmado como inofensivo, ajusta a detecção para todos os usuários do Windows Defender — não apenas o seu computador:

**https://www.microsoft.com/pt-br/wdsi/filesubmission**

Isso é opcional, mas ajuda outras pessoas que forem usar o projeto no futuro.

---

## Opção 2 — Código-fonte

Com Python instalado:

```bat
run.bat
```

ou:

```bash
python main.py
```

O `run.bat` verifica o ambiente e tenta instalar automaticamente as dependências necessárias quando possível.

---

# 📦 Estrutura do projeto

```text
SIGAA-Sniper/
│
├── SIGAA-Sniper.exe
├── SIGAA-Sniper.spec       # receita reprodutível do PyInstaller (usada pelo build_exe.bat)
├── version_info.txt        # metadados de versão embutidos no .exe
├── main.py
├── run.bat
├── requirements.txt
├── requirements-dev.txt    # pytest (e, opcionalmente, playwright) — só para testes
│
├── app/
│   ├── core/
│   ├── gui/
│   ├── web/                # Interface Web: servidor local + static/ (HTML/CSS/JS)
│   ├── terminal/
│   ├── dashboard/
│   ├── notifications/
│   ├── experimental/
│   └── utils/
│
├── config/
├── data/
├── logs/
│
├── docs/
│   ├── GUIA_DE_USO.md
│   ├── SEGURANCA.md
│   └── ...
│
├── tests/                  # testes automatizados (pytest)
│
└── tools/
    └── build_exe.bat       # gera SIGAA-Sniper.exe a partir do código-fonte
```

**Desenvolvimento x distribuição:** o repositório guarda o código-fonte, os testes e a documentação. Para o usuário final basta o `SIGAA-Sniper.zip` (executável + README + `docs/`). Pastas geradas (`build/`, `.buildenv/`, caches, `config/*.json`, `data/*.json`, logs) ficam fora do Git (ver `.gitignore`).

Os diretórios `config/`, `data/` e `logs/` podem ser criados automaticamente durante a utilização.

---

# 💻 Requisitos

## Executável

Para utilizar o `.exe` no Windows:

* Windows compatível;
* arquivos da distribuição mantidos em sua estrutura original.

Não é necessário instalar Python separadamente para utilizar o executável.

## Código-fonte

Para executar diretamente o código:

* Python **3.9 ou superior**;
* dependências listadas em `requirements.txt`.

Instalação manual:

```bash
pip install -r requirements.txt
```

A interface gráfica utiliza **Tkinter/ttk**, normalmente disponibilizado junto com o Python no Windows. A Interface Web não exige nada além disso: usa a biblioteca padrão do Python e qualquer navegador atual (Edge, Chrome, Firefox).

---

# 🧪 Testes

Suíte automatizada em `tests/` (pytest):

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Resultado na versão 5.1.0: **62 testes, 62 aprovados, 0 falhas.** São 60 testes da suíte principal, mais 2 testes ponta a ponta no navegador (`tests/test_web_e2e.py`, que exigem `playwright`).

| Arquivo | O que cobre |
| --- | --- |
| `test_engine_fluxo.py` | Motor de matrícula completo contra um **SIGAA simulado** (sem rede): login, busca, detecção de vaga, seleção da turma certa, DRY RUN **nunca** enviando a confirmação final, matrícula real com os campos de segurança corretos, bloqueio por pré-requisito, monitoramento que nunca seleciona turma |
| `test_web_api.py` | Servidor Web real: chave de acesso, bloqueio de `Host`/CSRF, limites de corpo, aviso legal obrigatório, confirmações (409), credenciais só em memória, disciplinas, execução, dashboard/logs, notificações, avançado, importar/exportar |
| `test_web_e2e.py` | Navegador real (Edge/Chrome via Playwright) usando **o motor real** contra o SIGAA simulado: aviso legal, assistente, credenciais, disciplinas, execução, dashboard ao vivo, logs, validações, tema escuro, celular e encerramento |
| `test_terminal.py` | Programa real por stdin/stdout: aviso legal, menu, configurações e abertura/encerramento da Interface Web pelo menu. Com `SIGAA_SNIPER_EXE=caminho\do.exe`, os mesmos testes rodam contra o executável |
| `test_gui.py` | GUI Tkinter: aviso legal com 5 confirmações, construção de todas as telas e sincronização das telas |
| `test_config.py`, `test_log_tailer.py`, `test_utilitarios.py` | Configuração/migração/validação, rotação de log, atalho com acentos, Telegram, departamentos |

O executável gerado também foi testado: os testes de terminal rodaram contra o `.exe`, e a Interface Web do `.exe` foi aberta num navegador real, com só o `.exe` copiado para uma pasta vazia e o `PATH` limitado a `C:\Windows`, sem Python visível.

### ⚠️ Limitações dos testes

Os testes automatizados **não substituem uma operação real no SIGAA**.

A conectividade real com o SIGAA foi verificada pelo diagnóstico em camadas (páginas públicas responderam HTTP 200). Não foram considerados como validação real:

* login e matrícula contra uma conta acadêmica real (exigem credenciais, que o teste não usa);
* execução durante uma janela real de matrícula;
* operação contínua por horas/dias;
* validação física em múltiplas máquinas diferentes (o "ambiente limpo" foi simulado na mesma máquina).

Essas limitações devem ser consideradas antes de qualquer utilização.

---

# 🏗️ Arquitetura

A versão atual foi organizada de forma modular para separar responsabilidades.

```text
                    ┌─────────────────┐
                    │    main.py      │
                    └────────┬────────┘
                             │
     ┌───────────────────────┼───────────────────────┐
     │                       │                       │
┌────▼─────┐          ┌──────▼──────┐         ┌──────▼──────┐
│   Web    │          │     GUI     │         │   Terminal  │
│ (local)  │          │  (Tkinter)  │         │   (menu)    │
└────┬─────┘          └──────┬──────┘         └──────┬──────┘
     │                       │                       │
     └───────────────────────┼───────────────────────┘
                             │
                    ┌────────▼────────┐
                    │      Core       │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
 ┌──────▼──────┐      ┌──────▼──────┐      ┌──────▼──────┐
 │ Monitoramento│      │ Matrícula   │      │Notificações │
 └─────────────┘      └─────────────┘      └─────────────┘
                             │
                      ┌──────▼──────┐
                      │ Experimental│
                      └─────────────┘
```

A arquitetura procura manter funcionalidades experimentais isoladas do caminho principal da aplicação.

---

# 🕰️ Evolução do projeto

O projeto atual é uma evolução do **Auto-Matrícula SIGAA (UnB)**.

A versão funcional anterior foi utilizada como referência para preservar comportamentos importantes do fluxo existente, enquanto recursos adicionais foram reorganizados em módulos independentes.

Recursos recuperados ou adaptados de versões anteriores incluem, entre outros:

* Telegram;
* ntfy;
* alarme sonoro;
* controle de taxa;
* scheduler;
* backoff;
* busca de departamento;
* recursos experimentais.

A existência de código legado não significa que todas as versões anteriores façam parte do fluxo atual.

---

# 📚 Documentação

Consulte a pasta `docs/` para obter informações detalhadas.

Principais documentos:

| Documento                 | Descrição                                  |
| ------------------------- | ------------------------------------------ |
| `GUIA_DE_USO.md`          | Guia completo de utilização                |
| `SEGURANCA.md`            | Segurança, credenciais, dados persistidos e Interface Web |

Os dois documentos também aparecem na tela **Ajuda** (GUI e Web), inclusive no `.exe`.

---

# 🐛 Problemas, sugestões e contribuições

Este é um projeto **open source** e sugestões, melhorias, correções e relatos de problemas são bem-vindos.

Para acompanhar o desenvolvimento, consultar atualizações ou relatar problemas, utilize o repositório oficial:

**[GitHub — Auto-Matrícula SIGAA UnB](https://github.com/xGabrielCv/Auto-Matricula-SIGAA-UnB)**

Ao relatar um problema, procure incluir:

* versão utilizada;
* sistema operacional;
* método de execução (`.exe`, `run.bat` ou `python main.py`) e modo (Web, GUI ou terminal);
* mensagem de erro;
* diagnóstico sanitizado, quando apropriado;
* passos necessários para reproduzir o problema.

> [!WARNING]
> Nunca envie senhas, CPF, tokens, cookies, credenciais ou outros dados pessoais em uma issue ou outro espaço público.

---

# 🖥️ Atalho para a área de trabalho

A aplicação possui suporte à criação de atalho para facilitar futuras execuções (tela **Sobre** na Web/GUI, ou **Configurações → Sobre** no terminal). No executável, o atalho aponta para o próprio `SIGAA-Sniper.exe`.

Quando disponível, essa opção pode ser utilizada diretamente pela aplicação.

Caso o sistema operacional impeça a criação automática, consulte a documentação para o procedimento manual.

---


# 📜 Licença

Consulte o arquivo de licença distribuído com o projeto.

Este software é disponibilizado para fins educacionais e de estudo. A utilização do projeto permanece sujeita às regras, termos e políticas aplicáveis aos sistemas e serviços acessados.

---

# ❤️ Projeto educacional e comunidade

O SIGAA Sniper nasceu como um projeto de estudo e experimentação em:

* 🐍 Python;
* 🌐 automação web;
* 🔌 integração HTTP;
* 🧵 concorrência;
* 🖥️ desenvolvimento de interfaces;
* 📊 monitoramento;
* 🔔 sistemas de notificação;
* 🧪 testes automatizados;
* 🔐 práticas de segurança;
* 🏗️ arquitetura modular.

Contribuições, sugestões e correções são bem-vindas através do repositório oficial.

---

<p align="center">

**SIGAA Sniper 🤖**

*Automação com responsabilidade.*

</p>
