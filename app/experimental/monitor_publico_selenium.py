"""
Experimento: monitorar a página pública do SIGAA (sem precisar de login) via
Selenium.

Origem: legacy/monitores_selenium/ (Monitorador_Puro.py e família) — todos
usam a página pública `https://sigaa.unb.br/sigaa/public/turmas/listar.jsf`,
que não exige autenticação.

Por que é experimental: investiguei reproduzir essa busca via requisição
HTTP direta (sem navegador) para o modo "somente monitoramento" do programa
principal, mas o botão de busca daquela página é controlado por ajax parcial
do JSF/Mojarra — o servidor não processa um POST de formulário comum, só uma
chamada ajax que só um navegador executando JavaScript de verdade consegue
reproduzir com confiança (ver docs/ARQUITETURA.md para os detalhes técnicos
da investigação). Os scripts legados funcionam porque usam Selenium (um
navegador real). Portar isso para o motor principal significaria adicionar
Selenium/ChromeDriver como dependência obrigatória — o que vai contra a meta
de manter a distribuição principal leve e sem depender de navegador (seção 34
do primeiro pedido). Por isso fica isolado aqui.

Dependências: selenium, webdriver_manager (NÃO estão em requirements.txt).
"""
from __future__ import annotations

import importlib.util
import os

from app.experimental import Experimento, registrar
from app.utils.paths import raiz_projeto

GUIA_INSTALACAO = """\
Como instalar manualmente (só necessário para este experimento específico):

1. Instale o Google Chrome, se ainda não tiver: https://www.google.com/chrome/
2. No terminal, dentro da pasta do projeto, rode:
     pip install selenium webdriver-manager
3. Pronto — não precisa baixar o ChromeDriver manualmente, o
   webdriver-manager faz isso na primeira execução.

Como testar se funcionou:
   Depois de instalar, marque de novo esta tela — o status deve mudar para
   "Pronto para executar".

Como executar o monitor original:
   O script completo (já com as credenciais em branco, prontas pra você
   preencher) está em:
     legacy/monitores_selenium/Monitorador_Puro.py
   Edite as constantes no topo do arquivo (disciplina, turma, professor) e
   rode:
     python legacy/monitores_selenium/Monitorador_Puro.py

Como parar:
   Feche a janela do navegador que o script abre, ou pressione Ctrl+C no
   terminal onde ele está rodando.

Erros comuns:
   - "chromedriver não encontrado": normalmente o webdriver-manager resolve
     sozinho; se persistir, confira se o Chrome está instalado e atualizado.
   - Script trava sem avançar: o layout da página pública pode ter mudado
     desde que este script foi escrito — é exatamente o tipo de coisa que
     torna isso "experimental" em vez de parte do caminho principal.

Como remover/desativar:
   pip uninstall selenium webdriver-manager
   (o programa principal não é afetado, nunca dependeu desses pacotes)
"""


def _selenium_disponivel() -> bool:
    return importlib.util.find_spec("selenium") is not None


def _executar() -> str:
    if not _selenium_disponivel():
        return "Selenium não está instalado. Veja o guia de instalação manual abaixo antes de executar."

    caminho_script = os.path.join(raiz_projeto(), "legacy", "monitores_selenium", "Monitorador_Puro.py")
    return (
        "Selenium está instalado. Por segurança, este botão não abre um navegador\n"
        "automaticamente a partir da interface (evita uma janela inesperada surgir\n"
        "sem contexto) — rode manualmente em um terminal:\n\n"
        f"  python \"{caminho_script}\"\n\n"
        "Lembre-se de editar as constantes no topo do arquivo (disciplina/turma/\n"
        "professor) antes de rodar — veja o guia de instalação para mais detalhes."
    )


registrar(Experimento(
    id="monitor_publico_selenium",
    nome="Monitor via página pública (Selenium, sem login)",
    descricao="Monitora a disponibilidade de turmas na página pública do SIGAA sem precisar fornecer suas credenciais — usa um navegador de verdade (Selenium) em vez de requisições HTTP diretas.",
    origem="legacy/monitores_selenium/Monitorador_Puro.py",
    dependencias=["selenium", "webdriver-manager"],
    riscos="Depende do layout atual da página pública do SIGAA, que pode mudar sem aviso. Mais lento e mais pesado (abre um navegador de verdade) que o monitoramento principal.",
    guia_instalacao=GUIA_INSTALACAO,
    disponivel=_selenium_disponivel,
    executar=_executar,
))
