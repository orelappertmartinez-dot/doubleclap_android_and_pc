#!/bin/bash
set -e

echo "Iniciando compilación de APK..."
echo "ANDROID_SDK_ROOT: $ANDROID_SDK_ROOT"

# Compilar APK
buildozer android debug

# Si la compilación fue exitosa
if [ -f "bin/*.apk" ]; then
    echo "✓ APK compilado exitosamente"
    ls -lh bin/
else
    echo "✗ Error: APK no se generó"
    exit 1
fi