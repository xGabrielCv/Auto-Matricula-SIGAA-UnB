# 🤖 SIGAA Sniper — Auto-Matrícula SIGAA (UnB)

<p align="center">

**Automação, monitoramento e gerenciamento de matrícula no SIGAA da UnB**

Interface gráfica • Terminal • Dashboard • Monitoramento • Notificações • DRY RUN • Diagnóstico

<br>

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=for-the-badge\&logo=python\&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge\&logo=windows\&logoColor=white)](#requisitos)
[![GUI](https://img.shields.io/badge/GUI-Tkinter-FFCA28?style=for-the-badge)](#interface)
[![Tests](https://img.shields.io/badge/Tests-52%20passing-2EA44F?style=for-the-badge)](#testes)
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

# ✨ Principais funcionalidades

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
* restauração de padrões.

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

Existem duas formas principais de executar o projeto.

## Opção 1 — Executável

A forma mais simples no Windows é utilizar:

```text
SIGAA-Sniper.exe
```

O executável foi empacotado com PyInstaller e não exige uma instalação separada do Python para execução.

Mantenha a estrutura do pacote original, incluindo os arquivos e diretórios necessários à aplicação.

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
├── main.py
├── run.bat
├── requirements.txt
│
├── app/
│   ├── core/
│   ├── gui/
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
├── tests/
│
└── tools/
    └── build_exe.bat
```

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

A interface gráfica utiliza **Tkinter/ttk**, normalmente disponibilizado junto com o Python no Windows.

---

# 🧪 Testes

A versão atual foi submetida a uma suíte automatizada com:

```text
52 testes
52 aprovados
0 falhas
```

Os testes abrangem diferentes componentes da aplicação, incluindo:

* configuração;
* departamentos;
* engine;
* integração com mocks;
* regressão da lógica principal;
* concorrência;
* DRY RUN;
* interface;
* terminal;
* recursos;
* assistente de primeira execução;
* sanitização;
* diagnóstico.

### ⚠️ Limitações dos testes

Os testes automatizados **não substituem uma operação real no SIGAA**.

Não foram considerados como validação real:

* matrícula contra uma conta acadêmica real;
* execução durante uma janela real de matrícula;
* operação contínua por horas/dias;
* validação física em múltiplas máquinas diferentes.

Essas limitações devem ser consideradas antes de qualquer utilização.

---

# 🏗️ Arquitetura

A versão atual foi organizada de forma modular para separar responsabilidades.

```text
                    ┌─────────────────┐
                    │    main.py      │
                    └────────┬────────┘
                             │
             ┌───────────────┴───────────────┐
             │                               │
      ┌──────▼──────┐                 ┌──────▼──────┐
      │     GUI     │                 │   Terminal  │
      └──────┬──────┘                 └──────┬──────┘
             │                               │
             └───────────────┬───────────────┘
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
| `SEGURANCA.md`            | Segurança, credenciais e dados persistidos |
| `ARQUITETURA.md`          | Organização interna do projeto             |
| Documentação Experimental | Recursos experimentais e suas limitações   |

---

# 🐛 Problemas, sugestões e contribuições

Este é um projeto **open source** e sugestões, melhorias, correções e relatos de problemas são bem-vindos.

Para acompanhar o desenvolvimento, consultar atualizações ou relatar problemas, utilize o repositório oficial:

**[GitHub — Auto-Matrícula SIGAA UnB](https://github.com/xGabrielCv/Auto-Matricula-SIGAA-UnB?utm_source=chatgpt.com)**

Ao relatar um problema, procure incluir:

* versão utilizada;
* sistema operacional;
* método de execução (`.exe`, `run.bat` ou `python main.py`);
* mensagem de erro;
* diagnóstico sanitizado, quando apropriado;
* passos necessários para reproduzir o problema.

> [!WARNING]
> Nunca envie senhas, CPF, tokens, cookies, credenciais ou outros dados pessoais em uma issue ou outro espaço público.

---

# 🖥️ Atalho para a área de trabalho

A aplicação possui suporte à criação de atalho para facilitar futuras execuções.

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
