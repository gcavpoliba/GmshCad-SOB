@echo off
setlocal enabledelayedexpansion

REM Spostati nella cartella del progetto
cd /d "%~dp0"

REM Imposta codifica UTF-8 per il terminale Windows
chcp 65001 >nul 2>nul
set PYTHONIOENCODING=utf-8

REM 1. Verifica se siamo già nell'ambiente conda "gmshcad" con python disponibile
if /i "%CONDA_DEFAULT_ENV%"=="gmshcad" (
    where python >nul 2>nul
    if !errorlevel! equ 0 (
        python main.py %*
        goto :handle_exit
    )
)

REM 2. Prova ad attivare tramite il comando 'conda' già presente nel PATH
where conda >nul 2>nul
if %errorlevel% equ 0 (
    call conda activate gmshcad 2>nul
    if /i "!CONDA_DEFAULT_ENV!"=="gmshcad" (
        python main.py %*
        goto :handle_exit
    )
)

REM 3. Ricerca automatica di conda.bat nei percorsi standard di installazione
set "CONDA_BAT="
for %%P in (
    "%USERPROFILE%\anaconda3\condabin\conda.bat"
    "%USERPROFILE%\miniconda3\condabin\conda.bat"
    "%LOCALAPPDATA%\anaconda3\condabin\conda.bat"
    "%LOCALAPPDATA%\miniconda3\condabin\conda.bat"
    "%PROGRAMDATA%\anaconda3\condabin\conda.bat"
    "%PROGRAMDATA%\miniconda3\condabin\conda.bat"
    "C:\anaconda3\condabin\conda.bat"
    "C:\miniconda3\condabin\conda.bat"
) do (
    if not defined CONDA_BAT if exist "%%~P" set "CONDA_BAT=%%~P"
)

if defined CONDA_BAT (
    call "!CONDA_BAT!" activate gmshcad 2>nul
    if /i "!CONDA_DEFAULT_ENV!"=="gmshcad" (
        python main.py %*
        goto :handle_exit
    )
)

REM 4. Fallback: esecuzione diretta di python.exe nell'ambiente gmshcad
set "PYTHON_EXE="
for %%P in (
    "%USERPROFILE%\anaconda3\envs\gmshcad\python.exe"
    "%USERPROFILE%\miniconda3\envs\gmshcad\python.exe"
    "%LOCALAPPDATA%\anaconda3\envs\gmshcad\python.exe"
    "%LOCALAPPDATA%\miniconda3\envs\gmshcad\python.exe"
    "%PROGRAMDATA%\anaconda3\envs\gmshcad\python.exe"
    "%PROGRAMDATA%\miniconda3\envs\gmshcad\python.exe"
    "C:\anaconda3\envs\gmshcad\python.exe"
    "C:\miniconda3\envs\gmshcad\python.exe"
) do (
    if not defined PYTHON_EXE if exist "%%~P" set "PYTHON_EXE=%%~P"
)

if defined PYTHON_EXE (
    "!PYTHON_EXE!" main.py %*
    goto :handle_exit
)

echo ======================================================================
echo [ERRORE] Impossibile trovare o attivare l'ambiente Conda "gmshcad".
echo Verificare che Anaconda o Miniconda sia installato e che l'ambiente esista.
echo.
echo Per creare l'ambiente conda richiesto:
echo     conda env create -f environment.yml
echo ======================================================================
echo.
pause
exit /b 1

:handle_exit
set "EXIT_CODE=%errorlevel%"
if %EXIT_CODE% neq 0 (
    echo.
    echo [INFO] Applicazione terminata con codice: %EXIT_CODE%
)
exit /b %EXIT_CODE%
