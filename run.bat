@echo off
setlocal
title SIGAA Sniper
cd /d "%~dp0"

echo ========================================
echo           SIGAA SNIPER
echo ========================================
echo.
echo Verificando Python...

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERRO] Python nao foi encontrado no seu computador.
    echo Instale o Python 3.9 ou mais recente em https://www.python.org/downloads/
    echo Durante a instalacao, marque a opcao "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

echo Verificando dependencias (httpx, beautifulsoup4, rich)...
python -c "import httpx, bs4, rich" >nul 2>nul
if errorlevel 1 (
    echo Instalando dependencias necessarias, aguarde...
    python -m pip install --quiet --disable-pip-version-check -r requirements.txt
)

echo Sistema pronto. Iniciando...
echo.
python main.py

pause
