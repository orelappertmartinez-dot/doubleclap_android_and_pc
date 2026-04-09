@echo off
echo === Building workspace.exe ===
echo.

REM Auto-detect Python from PATH
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python not found in PATH!
    echo Install Python and add to PATH.
    pause
    exit /b 1
)

set PYTHON=python

echo [1/2] Installing PyInstaller...
"%PYTHON%" -m pip install pyinstaller sounddevice numpy

echo.
echo [2/2] Building .exe...
"%PYTHON%" -m PyInstaller ^
    --onefile ^
    --name WorkspaceLauncher ^
    --icon NONE ^
    --console ^
    --distpath "%~dp0dist" ^
    --workpath "%~dp0build" ^
    --specpath "%~dp0build" ^
    "%~dp0workspace.py"

echo.
echo === Copying config next to .exe ===
copy "%~dp0workspace-config.json" "%~dp0dist\workspace-config.json"

echo.
echo ======================================
echo   DONE!
echo   Plik: %~dp0dist\WorkspaceLauncher.exe
echo   Config: %~dp0dist\workspace-config.json
echo.
echo   Copy these 2 files to any computer.
echo ======================================
echo.
pause
