@echo off
REM Script para iniciar el servidor web en Windows

echo.
echo ╔════════════════════════════════════════════════╗
echo ║     🎉 Clap Trigger - Servidor Web            ║
echo ╚════════════════════════════════════════════════╝
echo.

REM Verificar si Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python no está instalado.
    echo Instálalo desde: https://www.python.org/
    echo Asegúrate de agregar Python al PATH
    pause
    exit /b 1
)

echo ✅ Python detectado
echo.
echo 🚀 Iniciando servidor...
echo 📂 Directorio: %cd%
echo 🌐 Abre: http://localhost:8000
echo.
echo ⚠️  Presiona Ctrl+C para detener el servidor
echo.

python server.py

pause
