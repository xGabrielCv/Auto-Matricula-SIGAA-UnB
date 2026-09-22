"""
Utilitários de responsividade da GUI — corrige um problema real relatado
pelo usuário: a janela abria com tamanho fixo (980x680) que podia ser maior
que a tela disponível (notebooks com resolução menor, escala de DPI, etc.),
ou pequena demais para o conteúdo de uma tela específica, sem nenhuma forma
de rolar para ver o que ficava cortado.

Duas correções, usadas em toda a GUI:

  1. `geometria_responsiva()` — calcula um tamanho de janela baseado na
     resolução REAL da tela (nunca maior que ela), centralizado, em vez de
     um valor fixo que pode não caber.
  2. `tornar_rolavel()` — envolve o conteúdo de uma tela num Canvas com
     scrollbar vertical (e mouse wheel), garantindo que MESMO se a janela
     for menor que o conteúdo, dá pra rolar até o fim — em vez de esconder
     controles sem nenhuma pista visual de que existem.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Tuple


def geometria_responsiva(
    janela: tk.Misc,
    largura_ideal: int,
    altura_ideal: int,
    largura_min: int = 0,
    altura_min: int = 0,
    fracao_max_tela: float = 0.9,
) -> Tuple[int, int, int, int]:
    """
    Devolve (largura, altura, x, y) — um tamanho de janela que:
      - nunca ultrapassa `fracao_max_tela` da tela real (padrão 90%);
      - tenta usar o tamanho ideal quando a tela é grande o bastante;
      - nunca fica menor que o mínimo pedido, a menos que a própria tela
        seja menor que esse mínimo (nesse caso, usa a tela toda) — assim a
        janela NUNCA nasce maior do que cabe na tela do usuário.
      - já vem centralizada (x, y).
    """
    largura_tela = janela.winfo_screenwidth()
    altura_tela = janela.winfo_screenheight()

    limite_largura = int(largura_tela * fracao_max_tela)
    limite_altura = int(altura_tela * fracao_max_tela)

    largura = min(largura_ideal, limite_largura)
    altura = min(altura_ideal, limite_altura)

    if largura_min:
        largura = max(largura, min(largura_min, limite_largura))
    if altura_min:
        altura = max(altura, min(altura_min, limite_altura))

    x = max(0, (largura_tela - largura) // 2)
    y = max(0, (altura_tela - altura) // 2)
    return largura, altura, x, y


def aplicar_geometria_responsiva(
    janela: tk.Misc,
    largura_ideal: int,
    altura_ideal: int,
    largura_min: int = 0,
    altura_min: int = 0,
    fracao_max_tela: float = 0.9,
) -> None:
    largura, altura, x, y = geometria_responsiva(janela, largura_ideal, altura_ideal, largura_min, altura_min, fracao_max_tela)
    janela.geometry(f"{largura}x{altura}+{x}+{y}")
    # O tamanho MÍNIMO que o usuário pode encolher a janela nunca deve passar
    # do que ela já nasceu (senão o usuário fica "preso" sem poder diminuir
    # nem ver tudo) — usa o menor entre o mínimo desejado e o tamanho atual.
    if hasattr(janela, "minsize"):
        janela.minsize(min(largura_min or largura, largura), min(altura_min or altura, altura))


def tornar_rolavel(container: tk.Widget) -> ttk.Frame:
    """
    Envolve `container` (deve estar vazio) com um Canvas + Scrollbar vertical
    e devolve o Frame interno onde o conteúdo real deve ser colocado (em vez
    de `container` diretamente). Rolagem também funciona com a roda do mouse.

    Uso:
        corpo = tornar_rolavel(self)   # self é a Tela (ttk.Frame) da tela
        ttk.Label(corpo, text="...").pack(...)   # empacota em `corpo`, não em `self`
    """
    canvas = tk.Canvas(container, highlightthickness=0, borderwidth=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    frame_interno = ttk.Frame(canvas)

    frame_interno.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    janela_id = canvas.create_window((0, 0), window=frame_interno, anchor="nw")
    # O frame interno acompanha a largura do canvas (evita conteúdo cortado
    # horizontalmente ou uma faixa em branco à direita quando a janela é larga).
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(janela_id, width=e.width))

    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def _rolar_com_mouse(event):
        # Windows manda event.delta em múltiplos de 120; normaliza pra +-1 "clique" de roda.
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _ligar_mousewheel(_e):
        canvas.bind_all("<MouseWheel>", _rolar_com_mouse)

    def _desligar_mousewheel(_e):
        canvas.unbind_all("<MouseWheel>")

    # Só ativa a roda do mouse quando o cursor está sobre ESTA tela — evita
    # capturar a rolagem de outras telas quando o usuário troca de aba.
    canvas.bind("<Enter>", _ligar_mousewheel)
    canvas.bind("<Leave>", _desligar_mousewheel)

    return frame_interno
