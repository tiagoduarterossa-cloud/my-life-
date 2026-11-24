@echo off
rem Arranca a central num PC com Windows (para testar; o tablet continua a ser a central principal).
rem Precisa do Python 3 (python.org, com "Add python.exe to PATH" marcado na instalacao).
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1

rem vai buscar a versao mais recente antes de arrancar (se nao houver internet, arranca com a que tem)
where git >nul 2>nul && git pull --quiet
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

rem so o ecra do Jarvis, em ecra inteiro (Esc ou F11 para sair do ecra inteiro).
rem Para abrir a central toda: muda "jarvis" para "central" na linha de baixo.
set VIDA_ABRIR=jarvis
echo A abrir o Jarvis no Chrome (http://127.0.0.1:8080/?jarvis=1)
%PY% server.py
pause
