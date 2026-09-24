@echo off
setlocal
title SIGAA Sniper - Build do executavel
cd /d "%~dp0.."

echo ============================================================
echo   SIGAA Sniper - build do executavel (.exe)
echo ============================================================
echo.
echo Este script gera SIGAA-Sniper.exe a partir do codigo-fonte,
echo usando um ambiente Python isolado (pasta .buildenv) para nao
echo misturar pacotes de outros projetos no executavel final.
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Python nao foi encontrado no seu computador.
    echo Instale o Python 3.9 ou mais recente em https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist ".buildenv\Scripts\python.exe" (
    echo Criando ambiente virtual isolado em .buildenv ...
    python -m venv .buildenv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar o ambiente virtual.
        pause
        exit /b 1
    )
)

echo Instalando dependencias de build ^(isoladas do resto do sistema^)...
".buildenv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check --upgrade pip
".buildenv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt "pyinstaller==6.22.3"
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias de build.
    pause
    exit /b 1
)

echo.
echo Gerando version_info.txt a partir de app\versao.py ...
".buildenv\Scripts\python.exe" tools\gerar_version_info.py
if errorlevel 1 (
    echo [ERRO] Falha ao gerar version_info.txt.
    pause
    exit /b 1
)

echo.
echo Gerando o executavel a partir de SIGAA-Sniper.spec ...
".buildenv\Scripts\pyinstaller.exe" SIGAA-Sniper.spec --clean --noconfirm --distpath "." --workpath "build"
if errorlevel 1 (
    echo [ERRO] PyInstaller falhou. Veja as mensagens acima.
    pause
    exit /b 1
)

timeout /t 1 /nobreak >nul
rmdir /s /q "build" >nul 2>nul

echo.
echo Gerando SHA256SUMS.txt (impressao digital do executavel) ...
".buildenv\Scripts\python.exe" tools\gerar_hashes.py SIGAA-Sniper.exe
echo Gerando SIGAA-Sniper.zip (pacote de distribuicao) ...
".buildenv\Scripts\python.exe" tools\gerar_zip.py

echo.
echo ============================================================
echo Build concluido: SIGAA-Sniper.exe atualizado na raiz do projeto.
echo ============================================================
echo.
echo Observacoes importantes:
echo  - O executavel NAO e assinado digitalmente (nenhum certificado
echo    de assinatura de codigo foi adquirido para este projeto).
echo  - O antivirus do Windows pode, mesmo assim, apresentar um alerta
echo    na primeira execucao em cada computador novo. Consulte a secao
echo    "Executando em um Windows novo" do README.md para orientacoes.
echo.
pause
