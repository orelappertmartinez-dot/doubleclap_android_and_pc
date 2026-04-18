#!/bin/bash

# Script para compilar la APK usando Docker

echo "🐳 Compilando APK con Docker..."
echo ""

# Verificar si Docker está instalado
if ! command -v docker &> /dev/null; then
    echo "❌ Docker no está instalado. Instálalo desde: https://www.docker.com/"
    exit 1
fi

# Crear/reconstruir imagen Docker
echo "📦 Creando imagen Docker..."
docker build -t clap-trigger-builder .
if [ $? -ne 0 ]; then
    echo "❌ Error al crear la imagen"
    exit 1
fi

# Asegurar carpeta bin local
mkdir -p ./bin

# Ejecutar contenedor y compilar
echo ""
echo "⚙️ Compilando APK (esto puede tardar 10-20 minutos)..."
docker run --rm -v "$(pwd)":/app -w /app clap-trigger-builder bash -lc "buildozer android debug --no-input"

if [ $? -ne 0 ]; then
    echo "❌ Error en la compilación"
    exit 1
fi

echo ""
echo "✅ Compilación completada!"
echo ""
echo "📂 APK generada en: bin/claptrigger-0.1-debug.apk"
