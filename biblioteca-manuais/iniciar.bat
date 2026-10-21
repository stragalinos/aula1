@echo off
chcp 65001 >nul
title Biblioteca de Manuais
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo.
  echo O Node.js nao esta instalado neste computador.
  echo Baixe a versao LTS em https://nodejs.org, instale e abra este arquivo de novo.
  echo.
  pause
  exit /b 1
)
node servidor.js
echo.
echo A biblioteca foi desligada.
pause
