@echo off
chcp 65001 >nul
title Painel do Investidor
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo.
  echo Para abrir o painel no computador, instale antes o Node.js, que e gratuito.
  echo Vou abrir a pagina de download: escolha a versao LTS, instale e depois
  echo de dois cliques neste arquivo de novo.
  echo.
  start "" https://nodejs.org/pt-br/download
  pause
  exit /b 1
)
node local\servidor.js
pause
