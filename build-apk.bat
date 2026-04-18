@echo off
REM Script para compilar la APK usando Docker en Windows

echo 🐳 Compilando APK con Docker...
echo.

REM Verificar si Docker está instalado
docker --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker no está instalado.
    echo Instálalo desde: https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

REM Crear/reconstruir imagen Docker
echo 📦 Creando imagen Docker...
docker build -t clap-trigger-builder .
if errorlevel 1 (
    echo ❌ Error al crear la imagen
    pause
    exit /b 1
)

REM Asegurar carpeta bin local
if not exist "%cd%\bin" mkdir "%cd%\bin"

REM Ejecutar contenedor y compilar
echo.
echo ⚙️ Compilando APK (esto puede tardar 10-20 minutos)...
docker run --rm -v %cd%:/app -w /app clap-trigger-builder bash -lc "buildozer android debug --no-input"

if errorlevel 1 (
    echo ❌ Error en la compilación
    pause
    exit /b 1
)

echo.
echo ✅ Compilación completada!
echo.
echo 📂 APK generada en: bin\claptrigger-0.1-debug.apk
pause
