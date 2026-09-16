# SIGAA Sniper

Monitoramento e matrícula automática de disciplinas no SIGAA (UnB), com interface gráfica, modo terminal, dashboard ao vivo e notificações opcionais.

## Uso rápido

Você tem duas formas de usar, escolha uma:

- **Sem instalar nada**: dê duplo clique em `SIGAA-Sniper.exe`. Não precisa de Python nem de mais nenhum arquivo — mas mantenha o `.exe` na mesma pasta que veio no `.zip` (ele usa a pasta `docs/` ao lado para mostrar a aba de Ajuda, e cria sozinho as pastas `config/`, `data/` e `logs/` que usa).
- **Com Python instalado**: dê duplo clique em `run.bat` (Windows) — ele confere/instala as dependências e abre o menu. Sem Windows: `python main.py`.

Os dois caminhos abrem o mesmo menu:

```
[1] Interface gráfica
[2] Matrícula automática
[3] Somente monitoramento
[4] Configurações
[5] Diagnóstico
[6] Sair
```

## Segurança em uma frase

Suas credenciais do SIGAA nunca são salvas em disco — são pedidas de novo a cada execução e ficam só em memória. Veja `docs/SEGURANCA.md` para os detalhes completos.

## Documentação

- `docs/GUIA_DE_USO.md` — guia completo para quem vai usar o programa.
- `docs/SEGURANCA.md` — o que é e não é persistido, e como compartilhar o projeto com segurança.

## Estrutura deste pacote

```
SIGAA-Sniper.exe     → executável pronto para usar, sem precisar instalar Python
main.py, run.bat      → forma alternativa de rodar via código-fonte (precisa de Python)
app/                   → código da aplicação (core, gui, terminal, dashboard, notifications, utils)
config/                → suas disciplinas e preferências (não-sensível; gerado no primeiro uso)
data/, logs/            → logs de execução (rotacionados automaticamente)
docs/                   → documentação para quem vai usar o programa
```

## Requisitos

Para usar o `.exe`: nenhum (já vem pronto). Para usar via código-fonte: Python 3.9+ e as dependências `httpx`, `beautifulsoup4`, `rich` (instaladas automaticamente por `run.bat`, ou via `pip install -r requirements.txt`) — a interface gráfica usa Tkinter, incluído no Python padrão do Windows.
