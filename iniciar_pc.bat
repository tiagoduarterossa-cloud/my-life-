@echo off
rem Arranca a central num PC com Windows (para testar; o tablet continua a ser a central principal).
rem Precisa do Python 3 (python.org, com "Add python.exe to PATH" marcado na instalacao).
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set VIDA_PORT=8080

rem usa o "py" (o lancador do python.org) se o "python" nao estiver no PATH
set PY=
py -3 --version >nul 2>nul && set PY=py -3
if not defined PY python --version >nul 2>nul && set PY=python
if not defined PY (
  echo Nao encontrei o Python. Instala de python.org e marca "Add python.exe to PATH".
  pause
  exit /b 1
)

%PY% -c "import anthropic" 2>nul || %PY% -m pip install --quiet "anthropic>=1.1.0"
%PY% -c "import edge_tts" 2>nul || %PY% -m pip install --quiet edge-tts

echo A abrir a central no Chrome em http://127.0.0.1:8080
start "" "http://127.0.0.1:8080"
%PY% server.py
pause
