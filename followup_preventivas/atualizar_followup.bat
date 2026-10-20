@echo off
chcp 65001 >nul
title Atualizar follow-up de pecas
cd /d "%~dp0"

set "PY=python"
where python >nul 2>nul || set "PY=py"
%PY% --version >nul 2>nul || (
  echo Python nao encontrado. Instale em https://www.python.org/downloads/ marcando "Add python.exe to PATH".
  pause
  exit /b 1
)

%PY% -c "import pandas, openpyxl" 2>nul || (
  echo Instalando bibliotecas necessarias ^(pandas, openpyxl^)...
  %PY% -m pip install --user pandas openpyxl
)

%PY% atualizar_followup.py --abrir %*
if errorlevel 1 (
  echo.
  echo Houve um problema na atualizacao. Leia as mensagens acima.
)
echo.
pause
