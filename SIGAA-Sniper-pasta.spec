# -*- mode: python ; coding: utf-8 -*-
# Variante "em pasta" (Fase 7 — sugestão 100): SIGAA-Sniper\SIGAA-Sniper.exe + _internal\.
# Abre mais rápido (não extrai ~18 MB a cada execução) e costuma gerar menos
# alertas de antivírus. O pacote padrão continua sendo o executável único
# (SIGAA-Sniper.spec); esta é uma alternativa. Build:
#   .buildenv\Scripts\pyinstaller.exe SIGAA-Sniper-pasta.spec --clean --noconfirm --distpath dist_pasta
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # Interface Web (HTML/CSS/JS) e a ajuda offline vão DENTRO do .exe —
    # o programa funciona mesmo que só o executável seja copiado.
    # Só os documentos de ajuda ao usuário: a pasta docs/ também guarda
    # documentos internos de desenvolvimento, que não devem ir no pacote.
    datas=[
        ('app/web/static', 'app/web/static'),
        ('docs/GUIA_DE_USO.md', 'docs'),
        ('docs/SEGURANCA.md', 'docs'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)


exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SIGAA-Sniper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SIGAA-Sniper',
)
