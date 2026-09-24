"""
Tabela de referência de departamentos/unidades do SIGAA (UnB) — seções 11-14
do pedido de continuação.

IMPORTANTE: esta lista é uma FOTOGRAFIA do que foi observado na página pública
do SIGAA (https://sigaa.unb.br/sigaa/public/turmas/listar.jsf, campo
`formTurma:inputDepto`) durante o desenvolvimento deste projeto. O SIGAA pode
mudar códigos, nomes ou adicionar/remover unidades a qualquer momento — NUNCA
trate isso como definitivo. É só um ponto de partida para busca e validação
manual (ver `docs/GUIA_DE_USO.md`, seção "Como encontrar o código do
departamento").
"""
from __future__ import annotations

import json
import os
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

# (código, nome da unidade) — ordenado como aparece na página pública do SIGAA
DEPARTAMENTOS_REFERENCIA: List[Tuple[int, str]] = [
    (672, "CAMPUS UNB CEILÂNDIA: FACULDADE DE CIÊNCIAS E TECNOLOGIAS EM SAÚDE - BRASÍLIA"),
    (673, "CAMPUS UNB GAMA: FACULDADE DE CIÊNCIAS E TECNOLOGIAS EM ENGENHARIA - BRASÍLIA"),
    (640, "CENTRO DE DESENVOLVIMENTO SUSTENTÁVEL - BRASÍLIA"),
    (314, "CENTRO DE EXCELÊNCIA EM TURISMO - BRASÍLIA"),
    (650, "CENTRO ESTUDOS AVANÇADOS MULTIDISCIPLIN - BRASÍLIA"),
    (316, "CENTRO INTEGRADO ORDENAMENTO TERRITORIAL - BRASÍLIA"),
    (1448, "CENTRO INTERNACIONAL DE BIOÉTICA E HUMANIDADES - BRASÍLIA"),
    (677, "CENTRO UNB CERRADO - BRASÍLIA"),
    (130, "DECANATO DE ENSINO DE GRADUACAO / DEG - BRASÍLIA"),
    (170, "DECANATO DE PÓS-GRADUAÇÃO / DPG - BRASÍLIA"),
    (158, "DECANATO EXTENSÃO - BRASÍLIA"),
    (351, "DEPARTAMENTO DE AUDIOVISUAIS E PUBLICIDADE/DAP - BRASÍLIA"),
    (345, "DEPARTAMENTO DE COMUNICAÇÃO ORGANIZACIONAL/COM - BRASÍLIA"),
    (660, "DEPARTAMENTO DE DESIGN - BRASÍLIA"),
    (449, "DEPARTAMENTO DE ENGENHARIA MECANICA - BRASÍLIA"),
    (479, "DEPARTAMENTO DE ESTUDOS LATINO AMERICANO - BRASÍLIA"),
    (678, "DEPARTAMENTO DE FARMACIA - BRASÍLIA"),
    (791, "DEPARTAMENTO DE GESTAO DE POLITICAS PUBL - BRASÍLIA"),
    (352, "DEPARTAMENTO DE JORNALISMO/JOR - BRASÍLIA"),
    (518, "DEPARTAMENTO DE MATEMÁTICA - BRASÍLIA"),
    (390, "DEPARTAMENTO DE MÉTODOS E TÉCNICAS - BRASÍLIA"),
    (391, "DEPARTAMENTO DE POLÍTICAS PÚBLICAS E GESTÃO DA EDUCAÇÃO - BRASÍLIA"),
    (592, "DEPARTAMENTO DE PSICOLOGIA CLÍNICA - BRASÍLIA"),
    (483, "DEPARTAMENTO DE SOCIOLOGIA - BRASÍLIA"),
    (392, "DEPARTAMENTO DE TEORIA E FUNDAMENTOS - BRASÍLIA"),
    (327, "DEPTO ADMINISTRAÇÃO - BRASÍLIA"),
    (481, "DEPTO ANTROPOLOGIA - BRASÍLIA"),
    (492, "DEPTO ARTES CÊNICAS - BRASÍLIA"),
    (498, "DEPTO ARTES VISUAIS - BRASÍLIA"),
    (464, "DEPTO BIOLOGIA CELULAR - BRASÍLIA"),
    (462, "DEPTO BOTÂNICA - BRASÍLIA"),
    (333, "DEPTO CIÊNCIAS CONTÁBEIS ATUARIAIS - BRASÍLIA"),
    (508, "DEPTO CIÊNCIAS DA COMPUTAÇÃO - BRASÍLIA"),
    (466, "DEPTO CIÊNCIAS FISIOLÓGICAS - BRASÍLIA"),
    (337, "DEPTO CIÊNCIAS INFORMAÇÃO DOCUMENTAÇÃO - BRASÍLIA"),
    (467, "DEPTO ECOLOGIA - BRASÍLIA"),
    (548, "DEPTO ECONOMIA - BRASÍLIA"),
    (422, "DEPTO ENFERMAGEM - BRASÍLIA"),
    (437, "DEPTO ENGENHARIA CIVIL E AMBIENTAL - BRASÍLIA"),
    (760, "DEPTO ENGENHARIA DE PRODUCAO - BRASÍLIA"),
    (443, "DEPTO ENGENHARIA ELETRICA - BRASÍLIA"),
    (433, "DEPTO ENGENHARIA FLORESTAL - BRASÍLIA"),
    (514, "DEPTO ESTATÍSTICA - BRASÍLIA"),
    (552, "DEPTO FILOSOFIA - BRASÍLIA"),
    (469, "DEPTO FITOPATOLOGIA - BRASÍLIA"),
    (471, "DEPTO GENÉTICA E MORFOLOGIA - BRASÍLIA"),
    (555, "DEPTO GEOGRAFIA - BRASÍLIA"),
    (539, "DEPTO GEOLOGIA GERAL APLICADA - BRASÍLIA"),
    (541, "DEPTO GEOQUÍMICA E RECURSOS MINERAIS - BRASÍLIA"),
    (559, "DEPTO HISTÓRIA - BRASÍLIA"),
    (578, "DEPTO LINGUISTICA, PORT. LING. CLASSICAS - BRASÍLIA"),
    (574, "DEPTO LÍNGUAS ESTRANGEIRAS E TRADUÇÃO - BRASÍLIA"),
    (540, "DEPTO MINERALOGIA E PETROLOGIA - BRASÍLIA"),
    (495, "DEPTO MÚSICA - BRASÍLIA"),
    (424, "DEPTO NUTRICAO - BRASÍLIA"),
    (427, "DEPTO ODONTOLOGIA - BRASÍLIA"),
    (594, "DEPTO PROCESSOS PSICOLÓGICOS BÁSICOS - BRASÍLIA"),
    (360, "DEPTO PROJETOS EXPRES REPRES ARQ E URBAN - BRASÍLIA"),
    (593, "DEPTO PSICOLOGIA ESCOLAR DESENVOLVIMENTO - BRASÍLIA"),
    (596, "DEPTO PSICOLOGIA SOCIAL E DO TRABALHO - BRASÍLIA"),
    (420, "DEPTO SAUDE COLETIVA - BRASÍLIA"),
    (563, "DEPTO SERVIÇO SOCIAL - BRASÍLIA"),
    (361, "DEPTO TECNOLOGIA ARQUITETURA URBANISMO - BRASÍLIA"),
    (362, "DEPTO TEORIA HISTORIA ARQUIT E URBANISM - BRASÍLIA"),
    (580, "DEPTO TEORIA LITERÁRIA E LITERATURA - BRASÍLIA"),
    (472, "DEPTO ZOOLOGIA - BRASÍLIA"),
    (643, "DIRETORIA DO CENTRO DE APOIO AO DESENVOLVIMENTO TECNOLÓGICO - BRASÍLIA"),
    (363, "FACULDADE DE AGRONOMIA E MEDICINA VETERINÁRIA - BRASÍLIA"),
    (353, "FACULDADE DE ARQUITETURA E URBANISMO - BRASÍLIA"),
    (674, "FACULDADE DE CIÊNCIA DA INFORMAÇÃO - BRASÍLIA"),
    (410, "FACULDADE DE CIÊNCIAS DA SAÚDE - BRASÍLIA"),
    (343, "FACULDADE DE COMUNICAÇÃO - BRASÍLIA"),
    (370, "FACULDADE DE DIREITO - BRASÍLIA"),
    (381, "FACULDADE DE EDUCAÇÃO - BRASÍLIA"),
    (393, "FACULDADE DE EDUCAÇÃO FÍSICA - BRASÍLIA"),
    (402, "FACULDADE DE MEDICINA - BRASÍLIA"),
    (666, "FACULDADE DE PLANALTINA - BRASÍLIA"),
    (429, "FACULDADE DE TECNOLOGIA - BRASÍLIA"),
    (323, "FACULDADE ECONOMIA, ADMINISTRAÇÃO, CONTABILIDADE E GEST POL PÚBLICAS - BRASÍLIA"),
    (284, "FAZENDA AGUA LIMPA - BRASÍLIA"),
    (1201, "GRADUAÇÃO EM ADMINISTRAÇÃO - BACHARELADO - BRASÍLIA"),
    (288, "HOSP-HOSPITAL UNIVERSITÁRIO DE BRASÍLIA - BRASÍLIA"),
    (485, "INSTITUTO DE ARTES - BRASÍLIA"),
    (668, "INSTITUTO DE CIÊNCIA POLÍTICA - BRASÍLIA"),
    (455, "INSTITUTO DE CIÊNCIAS BIOLÓGICAS - BRASÍLIA"),
    (504, "INSTITUTO DE CIÊNCIAS EXATAS - BRASÍLIA"),
    (544, "INSTITUTO DE CIÊNCIAS HUMANAS - BRASÍLIA"),
    (473, "INSTITUTO DE CIÊNCIAS SOCIAIS - BRASÍLIA"),
    (524, "INSTITUTO DE FÍSICA - BRASÍLIA"),
    (533, "INSTITUTO DE GEOCIÊNCIAS - BRASÍLIA"),
    (567, "INSTITUTO DE LETRAS - BRASÍLIA"),
    (583, "INSTITUTO DE PSICOLOGIA - BRASÍLIA"),
    (610, "INSTITUTO DE QUÍMICA - BRASÍLIA"),
    (669, "INSTITUTO DE RELAÇÕES INTERNACIONAIS - BRASÍLIA"),
    (542, "OBSERVATÓRIO SISMOLÓGICO - BRASÍLIA"),
    (1080, "PARQUE CIENTÍFICO E TECNOLÓGICO DA UNB - BRASÍLIA"),
    (1615, "PARQUE DE INOVAÇÃO E SUSTENTABILIDADE DO AMBIENTE CONSTRUÍDO - BRASÍLIA"),
    (1617, "PROGRAMA DE PÓS-GRADUAÇÃO EM ADMINISTRAÇÃO (PROFISSIONAL) - BRASÍLIA"),
    (664, "PROGRAMA DE PÓS-GRADUAÇÃO EM ADMINISTRAÇÃO - BRASÍLIA"),
    (1847, "PROGRAMA DE PÓS-GRADUAÇÃO EM ADMINISTRAÇÃO PÚBLICA (PROFISSIONAL) - BRASÍLIA"),
    (853, "PROGRAMA DE PÓS-GRADUAÇÃO EM AGRONEGÓCIOS - BRASÍLIA"),
    (854, "PROGRAMA DE PÓS-GRADUAÇÃO EM AGRONOMIA - BRASÍLIA"),
    (855, "PROGRAMA DE PÓS-GRADUAÇÃO EM ANTROPOLOGIA - BRASÍLIA"),
    (927, "PROGRAMA DE PÓS-GRADUAÇÃO EM ARQUITETURA E URBANISMO - BRASÍLIA"),
    (842, "PROGRAMA DE PÓS-GRADUAÇÃO EM ARTES CÊNICAS - BRASÍLIA"),
    (911, "PROGRAMA DE PÓS-GRADUAÇÃO EM ARTES VISUAIS - BRASÍLIA"),
    (1877, "PROGRAMA DE PÓS-GRADUAÇÃO EM ASSISTÊNCIA FARMACÊUTICA - BRASÍLIA"),
    (1491, "PROGRAMA DE PÓS-GRADUAÇÃO EM BIOLOGIA ANIMAL - BRASÍLIA"),
    (1501, "PROGRAMA DE PÓS-GRADUAÇÃO EM BIOLOGIA MICROBIANA - BRASÍLIA"),
    (1492, "PROGRAMA DE PÓS-GRADUAÇÃO EM BIOTECNOLOGIA E BIODIVERSIDADE - REDE PRÓ-CENTRO-OESTE - BRASÍLIA"),
    (831, "PROGRAMA DE PÓS-GRADUAÇÃO EM BIOÉTICA - BRASÍLIA"),
    (1489, "PROGRAMA DE PÓS-GRADUAÇÃO EM BOTÂNICA - BRASÍLIA"),
    (900, "PROGRAMA DE PÓS-GRADUAÇÃO EM CIÊNCIA POLÍTICA - BRASÍLIA"),
    (995, "PROGRAMA DE PÓS-GRADUAÇÃO EM CIÊNCIAS AMBIENTAIS - BRASÍLIA"),
    (909, "PROGRAMA DE PÓS-GRADUAÇÃO EM CIÊNCIAS ANIMAIS - BRASÍLIA"),
    (1488, "PROGRAMA DE PÓS-GRADUAÇÃO EM CIÊNCIAS BIOLÓGICAS (BIOLOGIA MOLECULAR) - BRASÍLIA"),
    (896, "PROGRAMA DE PÓS-GRADUAÇÃO EM CIÊNCIAS CONTÁBEIS - BRASÍLIA"),
    (946, "PROGRAMA DE PÓS-GRADUAÇÃO EM CIÊNCIAS DA INFORMAÇÃO - BRASÍLIA"),
    (898, "PROGRAMA DE PÓS-GRADUAÇÃO EM CIÊNCIAS DA REABILITAÇÃO - BRASÍLIA"),
    (902, "PROGRAMA DE PÓS-GRADUAÇÃO EM CIÊNCIAS DA SAÚDE - BRASÍLIA"),
    (988, "PROGRAMA DE PÓS-GRADUAÇÃO EM CIÊNCIAS DE MATERIAIS - BRASÍLIA"),
    (903, "PROGRAMA DE PÓS-GRADUAÇÃO EM CIÊNCIAS DO COMPORTAMENTO - BRASÍLIA"),
    (897, "PROGRAMA DE PÓS-GRADUAÇÃO EM CIÊNCIAS E TECNOLOGIAS EM SAÚDE - BRASÍLIA"),
    (906, "PROGRAMA DE PÓS-GRADUAÇÃO EM CIÊNCIAS FARMACÊUTICAS - BRASÍLIA"),
    (997, "PROGRAMA DE PÓS-GRADUAÇÃO EM CIÊNCIAS FLORESTAIS - BRASÍLIA"),
    (904, "PROGRAMA DE PÓS-GRADUAÇÃO EM CIÊNCIAS MECÂNICAS - BRASÍLIA"),
    (845, "PROGRAMA DE PÓS-GRADUAÇÃO EM CIÊNCIAS MÉDICAS - BRASÍLIA"),
    (840, "PROGRAMA DE PÓS-GRADUAÇÃO EM COMPUTAÇÃO APLICADA (PROFISSIONAL) - BRASÍLIA"),
    (841, "PROGRAMA DE PÓS-GRADUAÇÃO EM COMUNICAÇÃO/PPGCOM - BRASÍLIA"),
    (929, "PROGRAMA DE PÓS-GRADUAÇÃO EM DESENVOLVIMENTO E COOPERAÇÃO INTERNACIONAL - BRASÍLIA"),
    (1487, "PROGRAMA DE PÓS-GRADUAÇÃO EM DESENVOLVIMENTO SUSTENTÁVEL - BRASÍLIA"),
    (875, "PROGRAMA DE PÓS-GRADUAÇÃO EM DESIGN - BRASÍLIA"),
    (914, "PROGRAMA DE PÓS-GRADUAÇÃO EM DIREITO - BRASÍLIA"),
    (1505, "PROGRAMA DE PÓS-GRADUAÇÃO EM DIREITO, REGULAÇÃO E POLÍTICAS PÚBLICAS - BRASÍLIA"),
    (916, "PROGRAMA DE PÓS-GRADUAÇÃO EM DIREITOS HUMANOS E CIDADANIA - BRASÍLIA"),
    (1490, "PROGRAMA DE PÓS-GRADUAÇÃO EM ECOLOGIA - BRASÍLIA"),
    (1619, "PROGRAMA DE PÓS-GRADUAÇÃO EM ECONOMIA (PROFISSIONAL) - BRASÍLIA"),
    (1198, "PROGRAMA DE PÓS-GRADUAÇÃO EM ECONOMIA - BRASÍLIA"),
    (1620, "PROGRAMA DE PÓS-GRADUAÇÃO EM EDUCAÇÃO (PROFISSIONAL) - BRASÍLIA"),
    (977, "PROGRAMA DE PÓS-GRADUAÇÃO EM EDUCAÇÃO - BRASÍLIA"),
    (1185, "PROGRAMA DE PÓS-GRADUAÇÃO EM EDUCAÇÃO EM CIÊNCIAS - BRASÍLIA"),
    (1625, "PROGRAMA DE PÓS-GRADUAÇÃO EM EDUCAÇÃO FÍSICA (PROFISSIONAL) - BRASÍLIA"),
    (910, "PROGRAMA DE PÓS-GRADUAÇÃO EM EDUCAÇÃO FÍSICA - BRASÍLIA"),
    (2050, "PROGRAMA DE PÓS-GRADUAÇÃO EM EDUCAÇÃO INCLUSIVA - BRASÍLIA"),
    (843, "PROGRAMA DE PÓS-GRADUAÇÃO EM ENFERMAGEM - BRASÍLIA"),
    (959, "PROGRAMA DE PÓS-GRADUAÇÃO EM ENGENHARIA BIOMÉDICA - BRASÍLIA"),
    (949, "PROGRAMA DE PÓS-GRADUAÇÃO EM ENGENHARIA DE SISTEMAS ELETRÔNICOS E AUTOMAÇÃO - BRASÍLIA"),
    (948, "PROGRAMA DE PÓS-GRADUAÇÃO EM ENGENHARIA ELÉTRICA - BRASÍLIA"),
    (1186, "PROGRAMA DE PÓS-GRADUAÇÃO EM ENSINO DE CIÊNCIAS (PROFISSIONAL) - BRASÍLIA"),
    (1506, "PROGRAMA DE PÓS-GRADUAÇÃO EM ENSINO DE FÍSICA (PROFISSIONAL) - BRASÍLIA"),
    (1613, "PROGRAMA DE PÓS-GRADUAÇÃO EM ENSINO DE GEOGRAFIA EM REDE (PROFISSIONAL) - BRASÍLIA"),
    (876, "PROGRAMA DE PÓS-GRADUAÇÃO EM ESTATÍSTICA - BRASÍLIA"),
    (829, "PROGRAMA DE PÓS-GRADUAÇÃO EM ESTRUTURAS E CONSTRUÇÃO CIVIL - BRASÍLIA"),
    (1225, "PROGRAMA DE PÓS-GRADUAÇÃO EM ESTUDOS COMPARADOS SOBRE AS AMÉRICAS - BRASÍLIA"),
    (1494, "PROGRAMA DE PÓS-GRADUAÇÃO EM ESTUDOS DA TRADUÇÃO - BRASÍLIA"),
    (1664, "PROGRAMA DE PÓS-GRADUAÇÃO EM FILOSOFIA (PROFISSIONAL) - BRASÍLIA"),
    (917, "PROGRAMA DE PÓS-GRADUAÇÃO EM FILOSOFIA - BRASÍLIA"),
    (947, "PROGRAMA DE PÓS-GRADUAÇÃO EM FITOPATOLOGIA - BRASÍLIA"),
    (985, "PROGRAMA DE PÓS-GRADUAÇÃO EM FÍSICA - BRASÍLIA"),
    (932, "PROGRAMA DE PÓS-GRADUAÇÃO EM GEOCIÊNCIAS APLICADAS E GEODINÂMICA - BRASÍLIA"),
    (1493, "PROGRAMA DE PÓS-GRADUAÇÃO EM GEOGRAFIA - BRASÍLIA"),
    (931, "PROGRAMA DE PÓS-GRADUAÇÃO EM GEOLOGIA - BRASÍLIA"),
    (901, "PROGRAMA DE PÓS-GRADUAÇÃO EM GEOTECNIA - BRASÍLIA"),
    (1503, "PROGRAMA DE PÓS-GRADUAÇÃO EM GESTÃO E REGULAÇÃO DE RECURSOS HÍDRICOS - PROFÁGUA (PROFISSIONAL) - BRASÍLIA"),
    (933, "PROGRAMA DE PÓS-GRADUAÇÃO EM GESTÃO PÚBLICA (PROFISSIONAL) - BRASÍLIA"),
    (1616, "PROGRAMA DE PÓS-GRADUAÇÃO EM GOVERNANÇA E INOVAÇÃO EM POLÍTICAS PÚBLICAS (PROFISSIONAL) - BRASÍLIA"),
    (928, "PROGRAMA DE PÓS-GRADUAÇÃO EM HISTÓRIA - BRASÍLIA"),
    (895, "PROGRAMA DE PÓS-GRADUAÇÃO EM INFORMÁTICA - BRASÍLIA"),
    (960, "PROGRAMA DE PÓS-GRADUAÇÃO EM INTEGRIDADE DE MATERIAIS DA ENGENHARIA - BRASÍLIA"),
    (1989, "PROGRAMA DE PÓS-GRADUAÇÃO EM LETRAS - PROFLETRAS (PROFISSIONAL) - BRASÍLIA"),
    (1495, "PROGRAMA DE PÓS-GRADUAÇÃO EM LINGUÍSTICA - BRASÍLIA"),
    (1203, "PROGRAMA DE PÓS-GRADUAÇÃO EM LINGUÍSTICA APLICADA - BRASÍLIA"),
    (987, "PROGRAMA DE PÓS-GRADUAÇÃO EM LITERATURA - BRASÍLIA"),
    (983, "PROGRAMA DE PÓS-GRADUAÇÃO EM MATEMÁTICA - BRASÍLIA"),
    (990, "PROGRAMA DE PÓS-GRADUAÇÃO EM MATEMÁTICA EM REDE NACIONAL (PROFISSIONAL) - BRASÍLIA"),
    (874, "PROGRAMA DE PÓS-GRADUAÇÃO EM MEDICINA TROPICAL - BRASÍLIA"),
    (996, "PROGRAMA DE PÓS-GRADUAÇÃO EM MEIO AMBIENTE EM DESENVOLVIMENTO RURAL - BRASÍLIA"),
    (926, "PROGRAMA DE PÓS-GRADUAÇÃO EM METAFÍSICA - BRASÍLIA"),
    (873, "PROGRAMA DE PÓS-GRADUAÇÃO EM MÚSICA - BRASÍLIA"),
    (1502, "PROGRAMA DE PÓS-GRADUAÇÃO EM NANOCIÊNCIA E NANOBIOTECNOLOGIA - BRASÍLIA"),
    (899, "PROGRAMA DE PÓS-GRADUAÇÃO EM NUTRIÇÃO HUMANA - BRASÍLIA"),
    (907, "PROGRAMA DE PÓS-GRADUAÇÃO EM ODONTOLOGIA - BRASÍLIA"),
    (1496, "PROGRAMA DE PÓS-GRADUAÇÃO EM PATOLOGIA MOLECULAR - BRASÍLIA"),
    (1990, "PROGRAMA DE PÓS-GRADUAÇÃO EM PLANEJAMENTO TERRITORIAL, PARTICIPAÇÃO E TURISMO - BRASÍLIA"),
    (1499, "PROGRAMA DE PÓS-GRADUAÇÃO EM POLÍTICA SOCIAL - BRASÍLIA"),
    (1624, "PROGRAMA DE PÓS-GRADUAÇÃO EM POLÍTICAS PÚBLICAS PARA INFÂNCIA E JUVENTUDE (PROFISSIONAL) - BRASÍLIA"),
    (982, "PROGRAMA DE PÓS-GRADUAÇÃO EM PROCESSOS DE DESENVOLVIMENTO HUMANO E SAÚDE - BRASÍLIA"),
    (1618, "PROGRAMA DE PÓS-GRADUAÇÃO EM PROFARTES (PROFISSIONAL) - BRASÍLIA"),
    (1545, "PROGRAMA DE PÓS-GRADUAÇÃO EM PROFARTES - BRASÍLIA"),
    (978, "PROGRAMA DE PÓS-GRADUAÇÃO EM PROFNIT - PROPRIEDADE INTELECTUAL E TRANSFERÊNCIA DE TECNOLOGIA PARA A INOVAÇÃO (PROFISSIONAL) - BRASÍLIA"),
    (986, "PROGRAMA DE PÓS-GRADUAÇÃO EM PSICOLOGIA CLÍNICA E CULTURA - BRASÍLIA"),
    (1497, "PROGRAMA DE PÓS-GRADUAÇÃO EM PSICOLOGIA DO DESENVOLVIMENTO E ESCOLAR - BRASÍLIA"),
    (913, "PROGRAMA DE PÓS-GRADUAÇÃO EM PSICOLOGIA SOCIAL, DO TRABALHO E DAS ORGANIZAÇÕES (PSTO) - BRASÍLIA"),
    (844, "PROGRAMA DE PÓS-GRADUAÇÃO EM QUÍMICA - BRASÍLIA"),
    (1622, "PROGRAMA DE PÓS-GRADUAÇÃO EM REDE NACIONAL PARA ENSINO DAS CIÊNCIAS AMBIENTAIS (PROFISSIONAL) - BRASÍLIA"),
    (1546, "PROGRAMA DE PÓS-GRADUAÇÃO EM REDE NACIONAL PARA ENSINO DAS CIÊNCIAS AMBIENTAIS - BRASÍLIA"),
    (1498, "PROGRAMA DE PÓS-GRADUAÇÃO EM RELAÇÕES INTERNACIONAIS - BRASÍLIA"),
    (872, "PROGRAMA DE PÓS-GRADUAÇÃO EM SAÚDE ANIMAL - BRASÍLIA"),
    (1623, "PROGRAMA DE PÓS-GRADUAÇÃO EM SAÚDE COLETIVA (PROFISSIONAL) - BRASÍLIA"),
    (908, "PROGRAMA DE PÓS-GRADUAÇÃO EM SAÚDE COLETIVA - BRASÍLIA"),
    (912, "PROGRAMA DE PÓS-GRADUAÇÃO EM SISTEMAS MECATRÔNICOS - BRASÍLIA"),
    (915, "PROGRAMA DE PÓS-GRADUAÇÃO EM SOCIOLOGIA - BRASÍLIA"),
    (1504, "PROGRAMA DE PÓS-GRADUAÇÃO EM SUSTENTABILIDADE JUNTO A POVOS E TERRITÓRIOS TRADICIONAIS - BRASÍLIA"),
    (830, "PROGRAMA DE PÓS-GRADUAÇÃO EM TECNOLOGIA AMBIENTAL E RECURSOS HÍDRICOS - BRASÍLIA"),
    (930, "PROGRAMA DE PÓS-GRADUAÇÃO EM TECNOLOGIAS QUÍMICA E BIOLÓGICA - BRASÍLIA"),
    (828, "PROGRAMA DE PÓS-GRADUAÇÃO EM TRANSPORTES - BRASÍLIA"),
    (1500, "PROGRAMA DE PÓS-GRADUAÇÃO EM ZOOLOGIA - BRASÍLIA"),
    (1543, "PROGRAMA DE PÓS-GRADUAÇÃO PROFBIO ENSINO DE BIOLOGIA EM REDE NACIONAL (PROFISSIONAL) - BRASÍLIA"),
    (1621, "PROGRAMA DE PÓS-GRADUAÇÃO PROFISSIONAL EM ENGENHARIA ELÉTRICA - BRASÍLIA"),
    (69, "REITORIA - BRASÍLIA"),
    (140, "SECRETARIA DE ADMINISTRACAO ACADEMICA - BRASÍLIA"),
]


@dataclass
class Departamento:
    codigo: int
    nome: str


# Fase 6 (046): lista atualizada a partir da página pública do SIGAA (sem login),
# guardada em config/departamentos.json. A lista acima continua como reserva.
URL_LISTA_PUBLICA = "https://sigaa.unb.br/sigaa/public/turmas/listar.jsf"
ARQUIVO_CACHE = "departamentos.json"
MINIMO_ESPERADO = 5


def _caminho_cache() -> str:
    from app.utils.paths import pasta_config
    return os.path.join(pasta_config(), ARQUIVO_CACHE)


def _lista_efetiva() -> List[Tuple[int, str]]:
    try:
        with open(_caminho_cache(), encoding="utf-8") as f:
            dados = json.load(f)
        lista = [(int(c), str(n)) for c, n in dados.get("departamentos", [])]
        if len(lista) >= MINIMO_ESPERADO:
            return lista
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return DEPARTAMENTOS_REFERENCIA


def info_lista() -> Dict[str, Any]:
    """De onde vem a lista usada agora (para mostrar ao usuário)."""
    try:
        with open(_caminho_cache(), encoding="utf-8") as f:
            dados = json.load(f)
        if len(dados.get("departamentos", [])) >= MINIMO_ESPERADO:
            return {"fonte": "sigaa", "atualizado_em": dados.get("atualizado_em"), "quantidade": len(dados["departamentos"]),
                    "texto": f"Lista atualizada do SIGAA em {dados.get('atualizado_em')} ({len(dados['departamentos'])} unidades)."}
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {"fonte": "embutida", "atualizado_em": None, "quantidade": len(DEPARTAMENTOS_REFERENCIA),
            "texto": f"Lista embutida no programa ({len(DEPARTAMENTOS_REFERENCIA)} unidades) — pode estar desatualizada."}


def extrair_departamentos(html: str) -> List[Tuple[int, str]]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    campo = soup.find("select", attrs={"name": "formTurma:inputDepto"}) or soup.find("select", id="formTurma:inputDepto")
    if campo is None:
        return []
    lista = []
    for opcao in campo.find_all("option"):
        valor = str(opcao.get("value") or "").strip()
        nome = " ".join(opcao.get_text().split())
        if valor.isdigit() and int(valor) > 0 and nome:
            lista.append((int(valor), nome))
    return lista


def atualizar_departamentos(cliente: Any = None) -> Dict[str, Any]:
    """Uma requisição GET à página pública (sem login). Só substitui a lista se
    a página trouxe uma lista plausível; senão lança ValueError e nada muda."""
    import httpx
    from datetime import datetime
    proprio = cliente is None
    cliente = cliente or httpx.Client(timeout=15, follow_redirects=True,
                                      headers={"User-Agent": "Mozilla/5.0 (SIGAA Sniper - lista de departamentos)"})
    try:
        resp = cliente.get(URL_LISTA_PUBLICA)
    except httpx.HTTPError as e:
        raise ValueError(f"Não foi possível acessar a página pública do SIGAA ({type(e).__name__}).")
    finally:
        if proprio:
            cliente.close()
    if resp.status_code != 200:
        raise ValueError(f"A página pública do SIGAA respondeu HTTP {resp.status_code}.")
    lista = extrair_departamentos(resp.text)
    if len(lista) < MINIMO_ESPERADO:
        raise ValueError("A página do SIGAA não trouxe a lista de departamentos esperada — a lista atual foi mantida.")
    antes = {c for c, _ in _lista_efetiva()}
    depois = {c for c, _ in lista}
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    caminho = _caminho_cache()
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"atualizado_em": agora, "fonte": URL_LISTA_PUBLICA, "departamentos": [[c, n] for c, n in lista]},
                  f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)
    from app.core import auditoria
    auditoria.registrar("departamentos_atualizados", quantidade=len(lista))
    return {"quantidade": len(lista), "novos": len(depois - antes), "removidos": len(antes - depois), "atualizado_em": agora}


def listar_departamentos() -> List[Departamento]:
    return [Departamento(c, n) for c, n in _lista_efetiva()]


def _normalizar(texto: str) -> str:
    """Maiúsculas e sem acento — buscar 'computacao' precisa achar 'COMPUTAÇÃO'.
    Sem isso, a busca por nome falha silenciosamente pra quem digita sem
    acento (comum em teclado/hábito no Brasil) — bug real encontrado em teste."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.upper()


def buscar_departamentos(termo: str) -> List[Departamento]:
    """Busca por nome (substring, sem diferenciar maiúsculas/acentos) ou por código exato."""
    termo = termo.strip()
    if not termo:
        return listar_departamentos()
    if termo.isdigit():
        alvo = int(termo)
        exatos = [d for d in listar_departamentos() if d.codigo == alvo]
        if exatos:
            return exatos
    termo_norm = _normalizar(termo)
    return [d for d in listar_departamentos() if termo_norm in _normalizar(d.nome) or termo == str(d.codigo)]


def nome_do_departamento(codigo: int) -> str:
    for c, n in _lista_efetiva():
        if c == codigo:
            return n
    return ""


def codigo_conhecido(codigo: int) -> bool:
    return any(c == codigo for c, _ in _lista_efetiva())
