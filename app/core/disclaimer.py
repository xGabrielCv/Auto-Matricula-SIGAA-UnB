"""
Aviso legal / termo de responsabilidade — seção 94.8-94.13 do pedido.

Regra inegociável: este aviso aparece em TODA execução, na GUI e no terminal,
e não é lembrado entre execuções (nenhum "não mostrar de novo" é salvo em
disco). O botão/opção de continuar só libera depois que as 5 confirmações
forem marcadas individualmente.
"""
from __future__ import annotations

TITULO = "Aviso Legal e Termo de Isenção de Responsabilidade"

TEXTO_COMPLETO = """\
⚠️ Aviso Legal e Termo de Isenção de Responsabilidade (Disclaimer)

Este documento estabelece as condições de uso, finalidade e limitações de
responsabilidade referentes a este software. Ao executar, compilar,
modificar ou utilizar qualquer componente deste projeto, o usuário declara
ciência e concordância integral com os termos abaixo.

1. Natureza Estritamente Educacional e Prova de Conceito

Este software foi concebido e desenvolvido exclusivamente para fins
acadêmicos, didáticos e de pesquisa técnica. Seu propósito principal é
servir como prova de conceito (Proof of Concept - PoC) para o estudo de
engenharia de software, requisições HTTP assíncronas, arquiteturas de
monitoramento distribuído (workers) e interfaces de diagnóstico em tempo
real.

2. Isenção de Vínculo Institucional e Responsabilidade

Este projeto não possui qualquer vínculo, chancela, homologação ou
autorização oficial da Universidade de Brasília (UnB), da Superintendência
de Tecnologia da Informação (STI) ou de qualquer instituição mantenedora do
Sistema Integrado de Gestão de Atividades Acadêmicas (SIGAA). O autor e
eventuais colaboradores eximem-se expressamente de qualquer responsabilidade
por ações executadas por terceiros com base neste repositório.

3. Conformidade e Termos de Uso do Sistema

O acesso automatizado a sistemas autenticados por meio de bots, scrapers ou
rotinas programadas pode infringir os Termos de Serviço, Políticas de
Segurança da Informação e Regimentos Disciplinares da universidade. O uso de
automação em períodos de matrícula pode ser passível de auditoria, bloqueio
de conta, perda de matrícula ou sanções administrativas e disciplinares
conforme as normas acadêmicas vigentes. O autor não incentiva, não endossa e
condena o uso deste código para burlar filas, filas de espera ou regras
institucionais.

4. Responsabilidade Integral do Usuário (Uso por Própria Conta e Risco)

A execução deste programa é realizada por sua conta e risco exclusivos. O
usuário é o único responsável legal, técnico e acadêmico por todas as
consequências decorrentes do uso do código, incluindo, mas não se limitando
a:

  - Bloqueios de IP ou suspensão de credenciais de acesso;
  - Invalidação de solicitações de matrícula;
  - Falhas na submissão de turmas devido a instabilidades de rede ou
    alterações no portal acadêmico;
  - Aplicação de penalidades regimentares previstas pela universidade.

5. Ética Operacional e Proteção da Infraestrutura Pública

O envio massivo, concorrente ou excessivamente frequente de requisições pode
degradar a estabilidade do servidor do SIGAA, configurando comportamento
análogo a ataques de negação de serviço (Denial of Service - DoS). Tal
prática sobrecarrega recursos públicos e prejudica diretamente o acesso da
comunidade estudantil. Caso execute testes, respeite intervalos operacionais
razoáveis, configure limites estritos de workers e aja com estrita
responsabilidade e ética.

6. Modalidade Segura: Monitoramento Público Sem Autenticação

Caso o seu objetivo seja unicamente acompanhar a disponibilidade de vagas
sem interferência ativa no sistema:

  - Utilize o modo de monitoramento: esta modalidade não submete dados de
    matrícula, apenas observa e notifica.
  - Redução de riscos: essa abordagem mitiga de forma substancial o risco
    de bloqueios de sessão ou de violação direta das políticas de acesso
    autenticado da plataforma, comparado ao modo de matrícula automática.
"""

# (chave, texto) — seção 94.9. Todas as 5 precisam ser marcadas.
CONFIRMACOES = [
    (
        "finalidade_educacional",
        "Finalidade exclusivamente educacional — Declaro que compreendo que este software é uma "
        "prova de conceito destinada a fins acadêmicos, didáticos, de pesquisa e estudo de "
        "engenharia de software, não possuindo qualquer vínculo, autorização ou homologação "
        "oficial da universidade.",
    ),
    (
        "ciencia_termos_servico",
        "Ciência sobre Termos de Serviço e possíveis consequências — Estou ciente de que o uso de "
        "ferramentas automatizadas pode estar sujeito aos Termos de Uso, políticas de segurança e "
        "normas institucionais aplicáveis ao SIGAA e à universidade, e compreendo que determinadas "
        "formas de utilização podem resultar em bloqueios de acesso, falhas de matrícula ou outras "
        "consequências previstas pelas regras vigentes.",
    ),
    (
        "responsabilidade_pelo_uso",
        "Responsabilidade pelo uso — Assumo responsabilidade pelas ações realizadas utilizando "
        "este software e compreendo que devo verificar previamente as regras e condições "
        "aplicáveis ao meu uso.",
    ),
    (
        "uso_responsavel",
        "Uso responsável e preservação da infraestrutura — Comprometo-me a não realizar "
        "requisições abusivas, excessivamente frequentes ou desnecessariamente concorrentes que "
        "possam prejudicar a infraestrutura do SIGAA ou o acesso de outros estudantes.",
    ),
    (
        "ciencia_modo_publico",
        "Ciência sobre o modo de monitoramento — Compreendo que, caso meu objetivo seja apenas "
        "acompanhar a disponibilidade de vagas, devo preferir o modo de monitoramento (sem "
        "matrícula automática) sempre que ele for suficiente para essa finalidade.",
    ),
]

# Resumo de uma linha por confirmação — usado SÓ como rótulo do checkbox na
# GUI (seção do pedido sobre visibilidade: os 5 checkboxes + botões precisam
# caber na tela sem depender de rolagem). O texto completo de cada item
# continua 100% presente e visível na área rolável (TEXTO_COMPLETO, mesmo
# conteúdo do CONFIRMACOES acima) — nada foi removido, só reorganizado.
# O terminal continua mostrando o texto completo de CONFIRMACOES (lá não há
# o mesmo problema de espaço de tela).
RESUMOS_CURTOS = {
    "finalidade_educacional": "Entendo que é um projeto educacional (PoC), sem vínculo oficial com a UnB/SIGAA.",
    "ciencia_termos_servico": "Estou ciente de que posso sofrer bloqueios ou outras consequências pelo uso de automação.",
    "responsabilidade_pelo_uso": "Assumo total responsabilidade pelas ações realizadas com este software.",
    "uso_responsavel": "Comprometo-me a não fazer uso abusivo que prejudique a infraestrutura do SIGAA.",
    "ciencia_modo_publico": "Sei que devo preferir o modo monitoramento quando só quiser acompanhar vagas.",
}
