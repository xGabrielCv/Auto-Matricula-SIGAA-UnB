# -*- mode: python ; coding: utf-8 -*-


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
    a.binaries,
    a.datas,
    [],
    name='SIGAA-Sniper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
)
