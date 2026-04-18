@echo off
REM Script para compilar la APK usando Docker en Windows

set "APK_NAME=claptrigger-0.1-arm64-v8a-debug.apk"
set "APK_PATH=%cd%\bin\%APK_NAME%"

echo Compilando APK con Docker...
echo.

REM Verificar si Docker esta instalado
docker --version >nul 2>&1
if errorlevel 1 (
    echo Docker no esta instalado.
    echo Instalalo desde: https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

REM Crear/reconstruir imagen Docker
echo Creando imagen Docker...
docker build -t clap-trigger-builder .
if errorlevel 1 (
    echo Error al crear la imagen
    pause
    exit /b 1
)

REM Asegurar carpeta bin local
if not exist "%cd%\bin" mkdir "%cd%\bin"

REM Ejecutar contenedor y compilar
echo.
echo Compilando APK (esto puede tardar 10-20 minutos)...
docker run --rm -v %cd%:/app -w /app clap-trigger-builder bash -lc "buildozer android debug --no-input"

if errorlevel 1 (
    echo Error en la compilacion
    pause
    exit /b 1
)

if not exist "%APK_PATH%" (
    echo Error: APK no se genero
    echo Se esperaba encontrar: %APK_PATH%
    pause
    exit /b 1
)

echo.
echo Compilacion completada.
echo.
echo APK generada en: bin\%APK_NAME%
pause
