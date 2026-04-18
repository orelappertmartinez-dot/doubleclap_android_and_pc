#!/bin/bash

# Script para iniciar el servidor web en Linux/macOS

clear
echo ""
echo "╔════════════════════════════════════════════════╗"
echo "║     🎉 Clap Trigger - Servidor Web            ║"
echo "╚════════════════════════════════════════════════╝"
echo ""

# Verificar si Python está instalado
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 no está instalado."
    echo "Instálalo con: sudo apt install python3 (Linux) o brew install python3 (Mac)"
    exit 1
fi

echo "✅ Python 3 detectado"
echo ""
echo "🚀 Iniciando servidor..."
echo "📂 Directorio: $(pwd)"
echo "🌐 Abre: http://localhost:8000"
echo ""
echo "⚠️  Presiona Ctrl+C para detener el servidor"
echo ""

python3 server.py
