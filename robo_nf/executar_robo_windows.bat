@echo off
rem Robo de NFs - versao que nao precisa instalar nada (usa o OCR do proprio Windows)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0robo_nf.ps1" %*
echo.
pause
