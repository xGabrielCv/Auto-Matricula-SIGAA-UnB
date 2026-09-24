"""
Suporte e privacidade (Fase 5 — sugestões 066, 064 e 051).

  - `redigir_html` / `redigir_texto` (066): mascaram dados pessoais antes de um
    dump de debug ir para o disco ou de qualquer coisa sair num pacote de
    suporte. Usam os próprios valores da sessão (matrícula, CPF, nascimento,
    senha) como referência, mais padrões genéricos (CPF, e-mail, matrícula da
    UnB) e os valores de todos os campos de formulário.
  - `listar_dumps` / `ler_dump` (064): os dumps de `logs/` como TEXTO redigido
    (a interface mostra num <pre>; o HTML do SIGAA nunca é renderizado).
  - `conteudo_pacote_suporte` / `gerar_pacote_suporte` (051): um .zip com
    diagnóstico, versão, configuração sem segredos, eventos recentes e dumps,
    tudo redigido. A lista do que vai no pacote é mostrada antes de salvar.

Limite conhecido (documentado para o usuário): o nome do estudante é mascarado
pelos blocos de identificação conhecidos das páginas do SIGAA; um nome que
apareça solto em outro ponto da página pode escapar. Por isso a interface
sempre recomenda conferir o pacote antes de compartilhar.
"""
from __future__ import annotations

import io
import json
import os
import platform
import re
import sys
import time
import zipfile
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

MASCARA = "***"
MAX_DUMP_BYTES = 300 * 1024
DUMPS_NO_PACOTE = 5
EVENTOS_NO_PACOTE = 300

_RE_CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b")
_RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_RE_MATRICULA = re.compile(r"\b\d{2}/\d{7}\b|\b\d{9}\b")
_RE_INPUT = re.compile(r"<input\b[^>]*>", re.I)
_RE_VALUE = re.compile(r"""(\bvalue\s*=\s*)("[^"]*"|'[^']*'|[^\s>]+)""", re.I)
_RE_TYPE = re.compile(r"""\btype\s*=\s*["']?(\w+)""", re.I)
_RE_TEXTAREA = re.compile(r"(<textarea\b[^>]*>)(.*?)(</textarea>)", re.I | re.S)
# Blocos em que o SIGAA mostra quem está logado (nome, matrícula, curso).
_RE_BLOCO_USUARIO = re.compile(r"usuario|discente|nome-?aluno|info-?user|perfil", re.I)
_CONTEINERES = {"html", "body", "form", "table", "tbody", "main"}
_TIPOS_SEM_DADO = {"submit", "button", "reset", "image", "checkbox", "radio"}

MOTIVOS_DUMP = {
    "selecao_falha": "Tela de confirmação não detectada após selecionar a turma",
    "confirmacao_sem_senha": "Campo de senha não encontrado na tela de confirmação",
    "confirmacao_inconclusiva": "Resposta da confirmação sem mensagem de sucesso nem de erro",
}


def _valores_sensiveis(credenciais: Any = None, extras: Iterable[str] = ()) -> List[str]:
    valores: List[str] = [v for v in extras if v]
    if credenciais is not None:
        for campo in ("usuario", "senha", "cpf", "nascimento"):
            v = str(getattr(credenciais, campo, "") or "").strip()
            if v:
                valores.append(v)
        cpf = re.sub(r"\D", "", str(getattr(credenciais, "cpf", "") or ""))
        if cpf:
            valores.append(cpf)
    # Só valores com tamanho suficiente para não mascarar pedaços aleatórios da página.
    return sorted({v for v in valores if len(v) >= 4}, key=len, reverse=True)


def redigir_texto(texto: str, credenciais: Any = None, extras: Iterable[str] = ()) -> str:
    """Mascara valores da sessão, CPF, e-mail e matrícula num texto qualquer (logs, relatórios)."""
    if not texto:
        return texto
    for valor in _valores_sensiveis(credenciais, extras):
        texto = re.sub(re.escape(valor), MASCARA, texto, flags=re.I)
    texto = _RE_CPF.sub(MASCARA, texto)
    texto = _RE_EMAIL.sub(MASCARA, texto)
    return _RE_MATRICULA.sub(MASCARA, texto)


def _mascarar_input(m: "re.Match[str]") -> str:
    tag = m.group(0)
    tipo = _RE_TYPE.search(tag)
    if tipo and tipo.group(1).lower() in _TIPOS_SEM_DADO:
        return tag
    return _RE_VALUE.sub(lambda v: f'{v.group(1)}"{MASCARA}"', tag)


class _FormatadorOrdemOriginal:
    """Wrapper preguiçoso: o formatador padrão do BeautifulSoup reordena os
    atributos em ordem alfabética; para diagnóstico a página deve sair igual."""

    def __new__(cls):
        from bs4.formatter import HTMLFormatter

        class _Formatador(HTMLFormatter):
            def attributes(self, tag):
                return list(tag.attrs.items())

        return _Formatador()


def _mascarar_blocos_usuario(html: str) -> str:
    """Troca o texto dos blocos de identificação do usuário por ***."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover — bs4 é dependência obrigatória
        return html
    soup = BeautifulSoup(html, "html.parser")
    alterou = False
    for tag in soup.find_all(True):
        if tag.name in _CONTEINERES:
            continue
        marcadores = " ".join([tag.get("id") or "", *(tag.get("class") or [])])
        # Blocos de identificação são curtos; um contêiner grande com "discente" na
        # classe (ex: o portal inteiro) não pode apagar a página toda do diagnóstico.
        if marcadores.strip() and _RE_BLOCO_USUARIO.search(marcadores) and len(tag.get_text()) <= 300:
            for texto in list(tag.find_all(string=True)):
                if texto.strip():
                    texto.replace_with(MASCARA)
                    alterou = True
    return soup.decode(formatter=_FormatadorOrdemOriginal()) if alterou else html


def redigir_html(html: str, credenciais: Any = None, extras: Iterable[str] = ()) -> str:
    """Versão para páginas do SIGAA: além do texto, mascara todos os valores de
    campos de formulário (inclusive ocultos) e os blocos com o nome do usuário.
    A estrutura da página — o que importa para o diagnóstico — é preservada."""
    if not html:
        return html
    html = _RE_INPUT.sub(_mascarar_input, html)
    html = _RE_TEXTAREA.sub(lambda m: f"{m.group(1)}{MASCARA}{m.group(3)}", html)
    html = _mascarar_blocos_usuario(html)
    return redigir_texto(html, credenciais, extras)


# ── Visualizador de dumps (064) ──────────────────────────────────────────

_RE_NOME_DUMP = re.compile(r"^debug_(W\d+|[A-Z]+)_([A-Za-z0-9_\-]+)_(\d{9,11})\.html$")


def _descrever_dump(nome: str) -> Dict[str, Any]:
    m = _RE_NOME_DUMP.match(nome)
    if not m:
        return {"worker": "?", "motivo": nome, "motivo_texto": "Página capturada para diagnóstico", "quando": None}
    worker, motivo, ts = m.group(1), m.group(2), int(m.group(3))
    base = next((k for k in MOTIVOS_DUMP if motivo.startswith(k)), None)
    disciplina = motivo[len(base) + 1:] if base and len(motivo) > len(base) + 1 else ""
    texto = MOTIVOS_DUMP.get(base, "Página capturada para diagnóstico")
    return {"worker": worker, "motivo": motivo, "disciplina": disciplina,
            "motivo_texto": texto + (f" ({disciplina})" if disciplina else ""),
            "quando": datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S")}


def listar_dumps() -> List[Dict[str, Any]]:
    from app.utils.cleanup import listar_debug_dumps
    itens = []
    for caminho in listar_debug_dumps():
        nome = os.path.basename(caminho)
        try:
            tamanho = os.path.getsize(caminho)
        except OSError:
            continue
        itens.append({"nome": nome, "tamanho_kb": round(tamanho / 1024, 1), **_descrever_dump(nome)})
    return itens


def _caminho_dump(nome: str) -> Optional[str]:
    """Só nomes de dump válidos, sempre dentro de logs/ (sem ../, sem caminho absoluto)."""
    from app.utils.paths import pasta_logs
    if not isinstance(nome, str) or os.path.basename(nome) != nome or not re.fullmatch(r"debug_[A-Za-z0-9_\-]+\.html", nome):
        return None
    caminho = os.path.join(pasta_logs(), nome)
    return caminho if os.path.isfile(caminho) else None


def texto_da_pagina(html: str) -> str:
    """O que a pessoa veria na tela, sem scripts/estilos, com linhas vazias compactadas."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    linhas = [re.sub(r"\s+", " ", l).strip() for l in soup.get_text("\n").splitlines()]
    saida, vazio = [], False
    for l in linhas:
        if l:
            saida.append(l)
            vazio = False
        elif not vazio:
            saida.append("")
            vazio = True
    return "\n".join(saida).strip()


def ler_dump(nome: str, credenciais: Any = None) -> Optional[Dict[str, Any]]:
    caminho = _caminho_dump(nome)
    if not caminho:
        return None
    with open(caminho, "rb") as f:
        bruto = f.read(MAX_DUMP_BYTES + 1)
    cortado = len(bruto) > MAX_DUMP_BYTES
    html = redigir_html(bruto[:MAX_DUMP_BYTES].decode("utf-8", errors="replace"), credenciais)
    return {"nome": nome, **_descrever_dump(nome), "texto": redigir_texto(texto_da_pagina(html), credenciais),
            "html": html, "cortado": cortado}


# ── Pacote de suporte (051) ─────────────────────────────────────────────

def _eventos_recentes(limite: int, credenciais: Any) -> str:
    from app.utils.paths import caminho
    arquivo = caminho("data", "sigaa_sniper_audit.json")
    if not os.path.exists(arquivo):
        return ""
    with open(arquivo, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - 2 * 1024 * 1024))
        linhas = f.read().decode("utf-8", errors="replace").splitlines()[-limite:]
    return "\n".join(redigir_texto(l, credenciais) for l in linhas if l.strip()) + "\n"


def _diagnostico_offline() -> str:
    from app.core.diagnostics import checar_modo_execucao, checar_saude_sistema, gerar_relatorio_texto
    from app.core.seguranca_config import checar_configuracoes_inseguras
    resultados = [*checar_saude_sistema(), checar_modo_execucao(), *checar_configuracoes_inseguras()]
    return gerar_relatorio_texto(resultados)


def _configuracao_sem_segredos() -> str:
    from dataclasses import asdict
    from app.core.config import carregar_disciplinas, carregar_settings
    pacote = {"settings": carregar_settings(), "disciplinas": [asdict(d) for d in carregar_disciplinas()]}
    return json.dumps(pacote, ensure_ascii=False, indent=2)


def _versao() -> str:
    from app.versao import NOME_APP, VERSAO_APP
    return (f"{NOME_APP} {VERSAO_APP}\nPython {sys.version.split()[0]}\n{platform.system()} {platform.release()} "
            f"({platform.machine()})\nExecutável: {'sim' if getattr(sys, 'frozen', False) else 'não (código-fonte)'}\n"
            f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")


def _ultima_execucao() -> str:
    from app.core.relatorios import listar_relatorios, texto_relatorio
    lista = listar_relatorios(1)
    return texto_relatorio(lista[0]) if lista else ""


def _montar(credenciais: Any) -> List[Dict[str, Any]]:
    """Arquivos do pacote (nome, descrição, conteúdo). Cada parte é best-effort:
    uma falha vira um arquivo de aviso, nunca impede o resto do pacote."""
    partes = [
        ("versao.txt", "Versão do programa, do Python e do Windows", _versao),
        ("diagnostico.txt", "Diagnóstico local (sem testes de rede) e alertas de configuração", _diagnostico_offline),
        ("configuracao.json", "Configurações e disciplinas — nunca inclui senha, CPF, nascimento ou tokens",
         _configuracao_sem_segredos),
        ("eventos_recentes.jsonl", f"Últimos {EVENTOS_NO_PACOTE} eventos do log, com dados pessoais mascarados",
         lambda: _eventos_recentes(EVENTOS_NO_PACOTE, credenciais)),
        ("ultima_execucao.txt", "Resumo da última execução", _ultima_execucao),
    ]
    arquivos = []
    for nome, descricao, gerar in partes:
        try:
            conteudo = gerar()
        except Exception as e:
            conteudo = f"Não foi possível gerar esta parte ({type(e).__name__})."
        if conteudo:
            arquivos.append({"nome": nome, "descricao": descricao, "conteudo": conteudo})
    for d in listar_dumps()[:DUMPS_NO_PACOTE]:
        lido = ler_dump(d["nome"], credenciais)
        if lido:
            arquivos.append({"nome": f"paginas/{d['nome']}", "descricao": f"Página capturada — {d['motivo_texto']} (mascarada)",
                             "conteudo": lido["html"]})
    leia = ["Pacote de suporte do SIGAA Sniper", "",
            "Conteúdo (dados pessoais mascarados com ***):", ""]
    leia += [f"- {a['nome']}: {a['descricao']}" for a in arquivos]
    leia += ["", "Confira os arquivos antes de compartilhar. O mascaramento cobre matrícula, CPF, data de",
             "nascimento, senha, e-mail e campos de formulário; um nome solto numa página pode escapar."]
    arquivos.insert(0, {"nome": "LEIA-ME.txt", "descricao": "O que tem neste pacote", "conteudo": "\n".join(leia) + "\n"})
    return arquivos


def conteudo_pacote_suporte(credenciais: Any = None) -> List[Dict[str, Any]]:
    """Lista mostrada antes de salvar: nome, descrição e tamanho de cada arquivo."""
    return [{"nome": a["nome"], "descricao": a["descricao"], "tamanho_kb": round(len(a["conteudo"].encode("utf-8")) / 1024, 1)}
            for a in _montar(credenciais)]


def gerar_pacote_suporte(credenciais: Any = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for a in _montar(credenciais):
            z.writestr(a["nome"], a["conteudo"])
    return buffer.getvalue()


def nome_pacote_suporte() -> str:
    return f"sigaa_sniper_suporte_{time.strftime('%Y%m%d_%H%M%S')}.zip"


def salvar_pacote_suporte(credenciais: Any = None) -> str:
    """Para GUI e terminal: grava em data/exportacoes/ e devolve o caminho."""
    from app.utils.paths import caminho
    pasta = caminho("data", "exportacoes")
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, nome_pacote_suporte())
    with open(destino, "wb") as f:
        f.write(gerar_pacote_suporte(credenciais))
    return destino
