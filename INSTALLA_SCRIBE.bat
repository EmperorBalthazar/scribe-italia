@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ======================================
echo      INSTALLAZIONE SCRIBE ITALIA
echo ======================================
echo.

py --version >nul 2>&1
if errorlevel 1 (
  echo ERRORE: il comando "py" non e' disponibile.
  echo Controlla che Python sia installato correttamente.
  pause
  exit /b 1
)

echo Python rilevato:
py --version

echo.
if not exist .venv\Scripts\python.exe (
  echo Creo l'ambiente Python...
  py -m venv .venv
  if errorlevel 1 (
    echo.
    echo ERRORE: non sono riuscito a creare l'ambiente virtuale.
    pause
    exit /b 1
  )
) else (
  echo Ambiente Python gia' presente.
)

echo.
echo Installo le librerie necessarie...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Installazione non riuscita. Controlla la connessione Internet e riprova.
  pause
  exit /b 1
)

echo.
echo Creo il database e gli account demo...
.venv\Scripts\python.exe -m flask --app app seed
if errorlevel 1 (
  echo.
  echo ERRORE durante la creazione del database.
  pause
  exit /b 1
)

echo.
echo ======================================
echo       INSTALLAZIONE COMPLETATA
 echo ======================================
echo Ora puoi usare AVVIA_SCRIBE.bat.
pause
