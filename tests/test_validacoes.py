"""
Validações compartilhadas pelas três interfaces: CPF/data de nascimento,
cadastro de disciplinas (individual e em lote), presets e estimativa de carga,
textos de ajuda sem depender do Tkinter e a fonte única de versão.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date

from app.core.config import (
    PRESETS_CARGA, Disciplina, analisar_disciplina, estimar_carga, interpretar_lote,
    preset_correspondente, validar_disciplinas,
)
from app.core.credentials import CredenciaisSigaa, cpf_valido, normalizar_nascimento, problema_nascimento

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── 068: CPF e data de nascimento ────────────────────────────────────────

def test_cpf_digitos_verificadores():
    assert cpf_valido("529.982.247-25") and cpf_valido("12345678909")
    assert not cpf_valido("123.456.789-00")      # dígito verificador errado
    assert not cpf_valido("111.111.111-11")      # sequência repetida passa na conta, mas não existe
    assert not cpf_valido("1234567890") and not cpf_valido("")


def test_nascimento_normalizado_e_validado():
    assert normalizar_nascimento("01022003") == "01/02/2003"
    assert normalizar_nascimento("1/2/2003") == "01/02/2003"
    assert normalizar_nascimento(" 01-02-2003 ") == "01/02/2003"
    assert normalizar_nascimento("ontem") == "ontem"
    hoje = date(2026, 9, 24)
    assert problema_nascimento("01/02/2003", hoje) is None
    assert "inválida" in problema_nascimento("31/02/2003", hoje)
    assert "futuro" in problema_nascimento("01/02/2030", hoje)
    assert "improvável" in problema_nascimento("01/02/1850", hoje)


def test_problemas_das_credenciais_so_olham_campos_preenchidos():
    assert CredenciaisSigaa().problemas() == []
    cred = CredenciaisSigaa("u", "s", "123.456.789-00", "31/02/2003")
    assert len(cred.problemas()) == 2
    assert CredenciaisSigaa("u", "s", "12345678909", "01/02/2003").problemas() == []


# ── 085: validação ao cadastrar disciplinas ──────────────────────────────

def test_disciplina_valida_sem_avisos():
    erros, avisos = analisar_disciplina(Disciplina("FGA0211", "01", 673), [])
    assert erros == [] and avisos == []


def test_turma_com_letras_e_duplicata_sao_erros():
    erros, _ = analisar_disciplina(Disciplina("FGA0211", "A", 673), [])
    assert erros and "só os números" in erros[0]
    existentes = [Disciplina("FGA0211", "01", 673)]
    erros, _ = analisar_disciplina(Disciplina("FGA0211", "01", 673), existentes)
    assert erros == ["FGA0211-01 já está cadastrada."]
    # editar a própria disciplina não conta como duplicata
    assert analisar_disciplina(Disciplina("FGA0211", "01", 673), existentes, ignorar_indice=0) == ([], [])


def test_avisos_de_formato_turma_curta_depto_e_outra_turma():
    existentes = [Disciplina("FGA0211", "01", 673)]
    _, avisos = analisar_disciplina(Disciplina("fga211".upper(), "1", 99999), existentes)
    texto = " ".join(avisos)
    assert "formato usual" in texto and "um só dígito" in texto and "99999" in texto
    _, avisos = analisar_disciplina(Disciplina("FGA0211", "03", 673), existentes)
    assert any("mais de uma turma do componente" in a for a in avisos)


def test_validar_disciplinas_bloqueia_turma_que_nunca_seria_encontrada():
    problemas = validar_disciplinas([Disciplina("FGA0211", "A", 673)])
    assert any("só números" in p for p in problemas)
    assert validar_disciplinas([Disciplina("FGA0211", "01", 673)]) == []


# ── 005: interpretação do cadastro em lote ───────────────────────────────

def test_lote_aceita_separadores_e_detecta_problemas():
    texto = "\n".join([
        "# comentário ignorado",
        "FGA0211 01 673",
        "mat0025;02;518",
        "CIC0004,03,508,Prof Fulano",
        "",
        "FGA0211 01 673",          # duplicata dentro do próprio lote
        "XYZ 01",                  # faltando departamento
        "FGA0212 01 gama",         # departamento não numérico
        "FGA0213 B 673",           # turma com letra
    ])
    itens = interpretar_lote(texto, [])
    assert [i["linha"] for i in itens] == [2, 3, 4, 6, 7, 8, 9]
    ok = [i for i in itens if i["disciplina"] and not i["erros"]]
    assert [i["disciplina"].chave() for i in ok] == ["FGA0211-01", "MAT0025-02", "CIC0004-03"]
    assert ok[2]["disciplina"].professor == "Prof Fulano"
    assert "já está cadastrada" in itens[3]["erros"][0]
    assert "Formato esperado" in itens[4]["erros"][0]
    assert "número (código)" in itens[5]["erros"][0]
    assert "só os números" in itens[6]["erros"][0]


def test_lote_considera_as_ja_cadastradas():
    itens = interpretar_lote("FGA0211 01 673", [Disciplina("FGA0211", "01", 673)])
    assert itens[0]["erros"]


# ── 043: presets e carga estimada ────────────────────────────────────────

def test_presets_e_estimativa_de_carga():
    assert preset_correspondente(20, 0.3) == "padrao"
    assert preset_correspondente(7, 0.3) is None
    for chave, p in PRESETS_CARGA.items():
        assert estimar_carga(p["num_workers"], p["intervalo_busca"])["preset"] == chave
    leve = estimar_carga(4, 1.5)
    assert leve["nivel"] == "baixa" and leve["alerta"] is None
    alta = estimar_carga(20, 0.3)
    assert alta["nivel"] == "alta" and alta["alerta"] and alta["req_por_seg"] > 15
    # mais disciplinas ativas → mais buscas por ciclo → carga maior
    assert estimar_carga(8, 0.8, 3)["req_por_seg"] > estimar_carga(8, 0.8, 1)["req_por_seg"]
    assert estimar_carga("x", 0.3)["nivel"] == "desconhecida"


# ── 096 / 095: textos sem Tkinter e versão única ─────────────────────────

def test_interface_web_nao_depende_do_tkinter():
    codigo = (
        "import sys; sys.modules['tkinter'] = None\n"
        "from app.web.estado import EstadoWeb\n"
        "from app.core.textos import textos_ajuda\n"
        "t = textos_ajuda(); assert 'avancado_workers' in t and 'telegram' in t and 'lote' in t\n"
        "print('ok')\n"
    )
    r = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr


def test_version_info_gerado_bate_com_a_versao_do_programa():
    from app.versao import VERSAO_APP
    sys.path.insert(0, os.path.join(RAIZ, "tools"))
    try:
        import gerar_version_info
    finally:
        sys.path.pop(0)
    with open(os.path.join(RAIZ, "version_info.txt"), encoding="utf-8") as f:
        atual = f.read()
    assert atual == gerar_version_info.conteudo(), "rode tools/gerar_version_info.py após mudar a versão"
    assert f"u'{VERSAO_APP}.0'" in atual


def test_spec_nao_embute_documentos_internos():
    with open(os.path.join(RAIZ, "SIGAA-Sniper.spec"), encoding="utf-8") as f:
        spec = f.read()
    assert "('docs', 'docs')" not in spec
    assert "GUIA_DE_USO.md" in spec and "SEGURANCA.md" in spec
