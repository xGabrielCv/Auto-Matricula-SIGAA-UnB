"""
Regras puras usadas pelo motor na Fase 4 (sem rede, fáceis de testar):

  - janela de execução (035): está dentro do horário/dia permitido?
  - classificação da resposta de confirmação do SIGAA (092);
  - inspeção de turma para a verificação prévia (040) — uma função SEPARADA
    do parser de matrícula (engine.parse_hot_path não é tocado).

Sobre a classificação (092): as frases vêm do que já se conhecia do SIGAA e
de mensagens usuais; sem páginas reais anonimizadas (sugestão 076) elas não
cobrem tudo. Por isso só há duas decisões NOVAS, e ambas na direção segura
(parar e avisar, nunca insistir): dados de confirmação incorretos e período
encerrado. O resto só ganha nome e explicação — a decisão continua a da v4.0.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

# ── Janela de execução (035) ──────────────────────────────────────────────

DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
RE_HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def problemas_janela(janela: Dict[str, Any]) -> List[str]:
    if not janela or not janela.get("ativa"):
        return []
    problemas = []
    for campo in ("inicio", "fim"):
        if not RE_HORA.match(str(janela.get(campo, ""))):
            problemas.append(f"Janela de execução: horário de {campo} inválido (use HH:MM, ex: 07:00).")
    dias = janela.get("dias")
    if not isinstance(dias, list) or not dias or any(d not in range(7) for d in dias):
        problemas.append("Janela de execução: escolha pelo menos um dia da semana.")
    if not problemas and janela["inicio"] == janela["fim"]:
        problemas.append("Janela de execução: início e fim não podem ser iguais.")
    return problemas


def dentro_da_janela(janela: Dict[str, Any], agora: Optional[datetime] = None) -> bool:
    """Janela desligada = sempre dentro. Aceita janela que cruza a meia-noite
    (ex: 22:00–02:00 — a parte depois da meia-noite pertence ao dia do início)."""
    if not janela or not janela.get("ativa") or problemas_janela(janela):
        return True
    agora = agora or datetime.now()
    atual, ini, fim = agora.hour * 60 + agora.minute, _minutos(janela["inicio"]), _minutos(janela["fim"])
    dia = agora.weekday()
    if ini < fim:
        return dia in janela["dias"] and ini <= atual < fim
    if atual >= ini:
        return dia in janela["dias"]
    return atual < fim and (dia - 1) % 7 in janela["dias"]


def descrever_janela(janela: Dict[str, Any]) -> str:
    if not janela or not janela.get("ativa"):
        return "sem janela (roda até ser parado)"
    nomes = ", ".join(DIAS[d] for d in sorted(janela.get("dias", [])))
    return f"das {janela['inicio']} às {janela['fim']} ({nomes})"


# ── Classificação da resposta de confirmação (092) ────────────────────────

CLASSES_RESPOSTA: List[Dict[str, Any]] = [
    {"categoria": "pre_requisito", "padroes": ["pré-requisito", "pre-requisito", "co-requisito"],
     "explicacao": "Falta um pré-requisito/co-requisito desta disciplina.", "decisao": "remover"},
    {"categoria": "choque_horario", "padroes": ["choque de horário", "choque de horario"],
     "explicacao": "Conflita com o horário de outra disciplina em que você já está matriculado.", "decisao": "remover"},
    {"categoria": "limite_credito", "padroes": ["limite de crédito", "limite de credito", "limite máximo de créditos"],
     "explicacao": "Passaria do limite de créditos do semestre.", "decisao": "remover"},
    {"categoria": "ja_matriculado", "padroes": ["já encontra-se matriculado", "já está matriculado", "ja esta matriculado"],
     "explicacao": "Você já está matriculado nesta disciplina.", "decisao": "remover"},
    {"categoria": "outra_turma", "padroes": ["mais de uma turma do componente"],
     "explicacao": "Você já tem outra turma deste componente — o SIGAA só permite uma.", "decisao": "remover"},
    {"categoria": "dados_incorretos", "padroes": [
        "senha incorreta", "senha inválida", "senha invalida", "senha não confere", "senha nao confere",
        "data de nascimento incorreta", "data de nascimento inválida", "data de nascimento invalida",
        "cpf incorreto", "cpf inválido", "cpf invalido", "dados informados estão incorretos", "dados de confirmação inválidos"],
     "explicacao": "O SIGAA recusou os dados de confirmação (senha, CPF ou data de nascimento). Repetir só arriscaria "
                   "bloquear a conta — a execução foi parada. Confira as credenciais.", "decisao": "parar"},
    {"categoria": "periodo_encerrado", "padroes": [
        "fora do período", "fora do periodo", "período de matrícula encerrado", "periodo de matricula encerrado",
        "prazo encerrado", "período encerrado", "não está no período"],
     "explicacao": "O SIGAA informou que o período de matrícula não está aberto — não adianta continuar agora.", "decisao": "parar"},
    {"categoria": "vaga_esgotada", "padroes": ["não há vagas", "nao ha vagas", "vagas esgotadas", "turma lotada", "sem vagas"],
     "explicacao": "A vaga acabou antes da confirmação. O programa continua procurando.", "decisao": "tentar_de_novo"},
]


def classificar_resposta_confirmacao(texto_erro: str) -> Dict[str, Any]:
    """Classifica a MENSAGEM DE ERRO devolvida pelo SIGAA na confirmação.
    Usar o texto do elemento de erro (não a página inteira) evita casar com
    rótulos do formulário, como "Data de Nascimento"."""
    t = (texto_erro or "").lower()
    for classe in CLASSES_RESPOSTA:
        if any(p in t for p in classe["padroes"]):
            return {k: classe[k] for k in ("categoria", "explicacao", "decisao")}
    return {"categoria": "desconhecido", "explicacao": "Resposta não reconhecida — o programa tenta de novo.",
            "decisao": "tentar_de_novo"}


# ── Inspeção de turma para a verificação prévia (040) ─────────────────────

def inspecionar_turma(html: str, codigo: str, turma: str) -> Dict[str, Any]:
    """Na página de resultado da busca: a disciplina aparece? a turma existe?
    quantas vagas? Usa as mesmas marcas da tabela que o parser de matrícula
    (lista-turmas-extra, linhas "disciplina"/"linhaPar"/"linhaImpar",
    colunas 1 e 7), mas NÃO substitui nem altera o parser."""
    resultado = {"disciplina_encontrada": False, "turma_encontrada": False, "vagas": None, "turmas_vistas": []}
    minusculo = (html or "").lower()
    if "não foram encontradas" in minusculo or "nenhum resultado" in minusculo:
        return resultado
    tabela = BeautifulSoup(html or "", "html.parser").find(id="lista-turmas-extra")
    if not tabela:
        return resultado
    ativa = False
    for tr in tabela.find_all("tr"):
        classes = " ".join(tr.get("class", []))
        if "disciplina" in classes:
            ativa = codigo.upper() in tr.get_text().upper()
            resultado["disciplina_encontrada"] = resultado["disciplina_encontrada"] or ativa
            continue
        if not ativa or ("linhaPar" not in classes and "linhaImpar" not in classes):
            continue
        tds = tr.find_all("td")
        if len(tds) < 8:
            continue
        m_turma = re.search(r"(\d+)", tds[1].get_text(strip=True))
        numero = m_turma.group(1) if m_turma else ""
        resultado["turmas_vistas"].append(numero)
        if numero == turma:
            m_vagas = re.search(r"(\d+)", tds[7].get_text(strip=True))
            resultado["turma_encontrada"] = True
            resultado["vagas"] = int(m_vagas.group(1)) if m_vagas else 0
    return resultado
