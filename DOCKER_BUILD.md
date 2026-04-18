# 📱 Compilación de APK con Docker

## Requisitos Previos

1. **Docker instalado**: [Descargar Docker Desktop](https://www.docker.com/products/docker-desktop)
   - Windows: Docker Desktop para Windows
   - Mac: Docker Desktop para Mac
   - Linux: `sudo apt install docker.io`

2. **Permisos de Docker** (Linux/Mac):
   ```bash
   sudo usermod -aG docker $USER
   ```

## Opciones de Compilación

### 🪟 En Windows

Simplemente ejecuta:
```bash
build-apk.bat
```

O desde PowerShell:
```powershell
.\build-apk.bat
```

### 🐧 En Linux/Mac

Ejecuta:
```bash
chmod +x build-apk.sh
./build-apk.sh
```

## Proceso de Compilación

1. Docker descargará la imagen base de Ubuntu (primera vez ~2GB)
2. Instalará todas las dependencias del sistema
3. Instalará Python, Java, Android SDK/NDK
4. Compilará la APK (10-20 minutos dependiendo del PC)
5. Guardará el APK en la carpeta `bin/`

## Resultado

Después de la compilación, encontrarás:
```
bin/claptrigger-0.1-debug.apk
```

## Instalar el APK

### Opción 1: Transferencia USB
1. Conecta tu teléfono Android por USB
2. Activa el "Modo de desarrollador" en tu teléfono
3. Ejecuta:
   ```bash
   adb install bin/claptrigger-0.1-debug.apk
   ```

### Opción 2: Transferir archivo
1. Copia el APK a tu teléfono
2. Abre el archivo desde el gestor de archivos
3. Instala normalmente

## Solución de Problemas

### "Docker no está instalado"
Instala Docker Desktop desde https://www.docker.com/

### "El puerto 8000 ya está en uso"
Docker está usando un puerto ocupado. Cambia el puerto en el Dockerfile.

### "No hay espacio en disco"
Las imágenes de Docker pueden ser grandes. Necesitas ~5GB libres.

### "Permiso denegado" (Linux/Mac)
```bash
sudo chmod +x build-apk.sh
sudo ./build-apk.sh
```

## Personalizar la Compilación

### Cambiar versión
Edita `buildozer.spec`:
```ini
version = 0.2  # Cambiar aquí
```

### Cambiar nombre de la app
```ini
title = Mi Aplicación
package.name = miapp
```

### Agregar permisos
```ini
# En buildozer.spec, busca la sección [app:permissions]
android.permissions = RECORD_AUDIO,INTERNET,CAMERA
```

## Tamaño Final

- APK sin optimizar: ~30-50 MB
- APK optimizado: ~15-25 MB

## Información Técnica

La compilación incluye:
- Python 3.11
- Kivy (framework UI)
- audiostream (acceso a micrófono)
- numpy (procesamiento de audio)
- Android SDK/NDK más reciente

## Soporte

Si tienes problemas:
1. Verifica que Docker esté corriendo
2. Intenta eliminar la imagen y volver a compilar:
   ```bash
   docker rmi clap-trigger-builder
   ```
3. Consulta los logs de Docker:
   ```bash
   docker logs [container_id]
   ```

---

**¡Listo para crear tu APK! 🚀**
