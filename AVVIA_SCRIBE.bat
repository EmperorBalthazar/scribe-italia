@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo Scribe Italia non e' ancora installato.
  echo Esegui prima INSTALLA_SCRIBE.bat.
  pause
  exit /b 1
)

echo.
echo Scribe Italia e' in avvio...
echo Quando compare "Running on http://127.0.0.1:5000", apri Chrome e vai a:
echo http://127.0.0.1:5000
echo.
echo NON chiudere questa finestra mentre usi il sito.
echo Per spegnere il sito premi CTRL+C.
echo.
.venv\Scripts\python.exe -m flask --app app run --debug
pause
