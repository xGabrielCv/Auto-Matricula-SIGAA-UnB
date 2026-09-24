"""
Tema e escala de fonte da interface gráfica (Fase 6 — sugestão 010).

As telas usavam cores fixas espalhadas ("#666", "#1a7f37"...). Agora toda cor
passa por `cor()`, que devolve a variante do tema escolhido; os valores do tema
escuro são os mesmos da Interface Web (tokens de app.css), para as duas
interfaces terem a mesma cara.

O tema e a escala são lidos das configurações quando a interface gráfica abre
("interface": {"tema", "escala_fonte"}) — mudar vale ao reabrir.
"""
from __future__ import annotations

import sys
from typing import Dict

TEMAS = {"claro": "Claro", "escuro": "Escuro", "sistema": "Seguir o Windows"}

# Cor clara (a que as telas usavam) → equivalente no tema escuro.
ESCURO: Dict[str, str] = {
    "#666": "#9aa5b8", "#57606a": "#9aa5b8",          # texto suave
    "#1a7f37": "#4ade80", "#116329": "#4ade80",       # sucesso
    "#9a6700": "#fbbf24", "#7d4e00": "#fbbf24",       # aviso
    "#cf222e": "#f87171",                              # perigo
    "#0969da": "#6d9bff",                              # destaque
    "#8250df": "#c4a5ff", "#bf3989": "#f28cc4",        # categorias da Central de Logs
    "#f6f8fa": "#1d2536", "#eaeef2": "#2b3548",        # fundos sutis
    "#dafbe1": "#14301f", "#fff8c5": "#33290f",        # fundos da barra de status
    "#24292f": "#e6eaf2", "black": "#e6eaf2",          # texto principal
    "#ffffff": "#ffffff",
}
FUNDO_ESCURO, SUPERFICIE_ESCURA, BORDA_ESCURA, TEXTO_ESCURO = "#0f1420", "#171e2c", "#2b3548", "#e6eaf2"
SELECAO_ESCURA = "#1c2a4a"

_tema_atual = "claro"


def tema_do_windows() -> str:
    """'escuro' quando o Windows está com os aplicativos no modo escuro."""
    if sys.platform != "win32":
        return "claro"
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as chave:
            valor, _ = winreg.QueryValueEx(chave, "AppsUseLightTheme")
        return "claro" if valor else "escuro"
    except OSError:
        return "claro"


def definir_tema(nome: str) -> str:
    global _tema_atual
    _tema_atual = tema_do_windows() if nome == "sistema" else ("escuro" if nome == "escuro" else "claro")
    return _tema_atual


def cor(valor: str) -> str:
    """Cor do tema atual. Recebe a cor clara de referência (a que a tela usava)."""
    if _tema_atual == "escuro":
        return ESCURO.get(valor, valor)
    return valor


def _carregar_preferencias() -> Dict:
    try:
        from app.core.config import carregar_settings
        return carregar_settings().get("interface") or {}
    except Exception:
        return {}


def preparar(raiz) -> Dict:
    """Chamar logo depois de criar a janela principal e ANTES de montar as telas:
    define o tema (as cores das telas são lidas na criação) e a escala de fonte."""
    prefs = {"tema": "claro", "escala_fonte": 100, **_carregar_preferencias()}
    nome = definir_tema(str(prefs.get("tema", "claro")))
    try:
        escala = max(80, min(160, int(prefs.get("escala_fonte") or 100)))
    except (TypeError, ValueError):
        escala = 100
    if escala != 100:
        # "tk scaling" escala TODAS as fontes em pontos e medidas da interface de uma vez.
        base = float(raiz.tk.call("tk", "scaling"))
        raiz.tk.call("tk", "scaling", base * escala / 100)
    if nome == "escuro":
        _aplicar_escuro(raiz)
    return {"tema": nome, "escala_fonte": escala}


def _aplicar_escuro(raiz) -> None:
    from tkinter import ttk
    estilo = ttk.Style(raiz)
    estilo.theme_use("clam")  # o tema nativo do Windows ignora cores de fundo
    raiz.configure(background=FUNDO_ESCURO)
    comum = {"background": FUNDO_ESCURO, "foreground": TEXTO_ESCURO}
    for nome in ("TFrame", "TLabel", "TCheckbutton", "TRadiobutton", "TLabelframe", "TNotebook"):
        estilo.configure(nome, **comum)
    estilo.configure("TLabelframe.Label", background=FUNDO_ESCURO, foreground=TEXTO_ESCURO)
    estilo.configure("TButton", background=SUPERFICIE_ESCURA, foreground=TEXTO_ESCURO, bordercolor=BORDA_ESCURA)
    estilo.map("TButton", background=[("active", SELECAO_ESCURA), ("disabled", FUNDO_ESCURO)],
               foreground=[("disabled", "#6b7588")])
    estilo.map("TCheckbutton", background=[("active", FUNDO_ESCURO)], foreground=[("disabled", "#6b7588")])
    estilo.map("TRadiobutton", background=[("active", FUNDO_ESCURO)])
    for nome in ("TEntry", "TCombobox", "TSpinbox"):
        estilo.configure(nome, fieldbackground=SUPERFICIE_ESCURA, foreground=TEXTO_ESCURO, background=SUPERFICIE_ESCURA,
                         insertcolor=TEXTO_ESCURO, bordercolor=BORDA_ESCURA)
    estilo.map("TCombobox", fieldbackground=[("readonly", SUPERFICIE_ESCURA)], foreground=[("readonly", TEXTO_ESCURO)])
    estilo.configure("Treeview", background=SUPERFICIE_ESCURA, fieldbackground=SUPERFICIE_ESCURA, foreground=TEXTO_ESCURO,
                     bordercolor=BORDA_ESCURA)
    estilo.map("Treeview", background=[("selected", SELECAO_ESCURA)], foreground=[("selected", TEXTO_ESCURO)])
    estilo.configure("Treeview.Heading", background=BORDA_ESCURA, foreground=TEXTO_ESCURO)
    estilo.configure("TNotebook.Tab", background=SUPERFICIE_ESCURA, foreground=TEXTO_ESCURO)
    estilo.map("TNotebook.Tab", background=[("selected", SELECAO_ESCURA)])
    for nome in ("TScrollbar", "Vertical.TScrollbar", "Horizontal.TScrollbar"):
        estilo.configure(nome, background=BORDA_ESCURA, troughcolor=FUNDO_ESCURO, bordercolor=BORDA_ESCURA,
                         arrowcolor=TEXTO_ESCURO, lightcolor=BORDA_ESCURA, darkcolor=BORDA_ESCURA)
    estilo.configure("Horizontal.TProgressbar", background="#6d9bff", troughcolor=SUPERFICIE_ESCURA)
    # Widgets tk "clássicos" (Text, Listbox, Canvas, janelas extras) criados daqui em diante.
    for padrao, valor in (("*Text.background", SUPERFICIE_ESCURA), ("*Text.foreground", TEXTO_ESCURO),
                          ("*Text.insertBackground", TEXTO_ESCURO), ("*Listbox.background", SUPERFICIE_ESCURA),
                          ("*Listbox.foreground", TEXTO_ESCURO), ("*Canvas.background", FUNDO_ESCURO),
                          ("*Toplevel.background", FUNDO_ESCURO), ("*Label.background", FUNDO_ESCURO),
                          ("*Label.foreground", TEXTO_ESCURO), ("*Frame.background", FUNDO_ESCURO)):
        raiz.option_add(padrao, valor)
