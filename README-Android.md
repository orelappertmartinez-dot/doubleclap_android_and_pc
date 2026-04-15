# Clap Trigger Android

Versión Android del Clap Trigger para detectar doble palmada y abrir aplicaciones.

## Requisitos

- Linux (Ubuntu recomendado)
- Python 3
- Buildozer

## Instalación

1. Instala buildozer:
   ```
   pip install buildozer
   ```

2. Instala dependencias del sistema:
   ```
   sudo apt update
   sudo apt install -y git zip unzip openjdk-17-jdk python3-pip autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev
   ```

3. Configura Android SDK/NDK (buildozer lo hace automáticamente).

## Compilación

1. Clona o copia los archivos `clap-trigger-android.py` y `buildozer.spec`.

2. Ejecuta:
   ```
   buildozer init  # Si no tienes buildozer.spec
   buildozer android debug
   ```

3. El APK se generará en `bin/`.

## Uso

- Abre la app en Android.
- Configura el umbral y agrega aplicaciones (paquetes Android).
- Presiona "Iniciar Clap Trigger" para empezar a escuchar.
- Doble palmada abre las apps configuradas.

Nota: Para abrir apps, usa nombres de paquete como `com.example.app`. Necesitas permisos de micrófono.