# 🎉 Clap Trigger - Detector de Palmadas

Controla tus aplicaciones con palmadas en Android y Windows/Linux/macOS.

## 📋 Contenido del Proyecto

```
launcher/
├── index.html              # Página web principal
├── server.py              # Servidor web para descargas
├── clap-trigger.py        # Código Python para PC
├── clap-trigger-android.py # Código Kivy para Android
├── buildozer.spec         # Configuración de compilación
├── Dockerfile             # Para compilar APK con Docker
├── build-apk.bat          # Script compilación (Windows)
├── build-apk.sh           # Script compilación (Linux/Mac)
├── DOCKER_BUILD.md        # Guía de compilación con Docker
├── requirements.txt       # Dependencias Python
└── README.md              # Este archivo
```

## 🚀 Inicio Rápido

### Opción 1: Usar la Página Web (Recomendado)

```bash
python server.py
```

Luego abre `http://localhost:8000` en tu navegador.

### Opción 2: Compilar Localmente

#### Para Windows/Linux/macOS (Python):

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar con interfaz gráfica
python clap-trigger.py --configure
```

#### Para Android:

```bash
# Opción 1: Con Docker (Fácil)
docker build -t clap-trigger-builder .
docker run --rm -v $(pwd)/bin:/app/bin clap-trigger-builder

# Opción 2: Script automático
build-apk.bat          # Windows
./build-apk.sh         # Linux/Mac
```

## 📱 Instalación Android

### Método 1: Desde el Navegador
1. Abre `http://localhost:8000`
2. Descarga la documentación
3. Sigue las instrucciones

### Método 2: Desde archivo APK
1. Compila: `build-apk.bat` o `./build-apk.sh`
2. Transfiere `bin/claptrigger-0.1-debug.apk` a tu teléfono
3. Instala desde el gestor de archivos

### Método 3: Con ADB
```bash
# Instalar Android Platform Tools
# Luego:
adb install bin/claptrigger-0.1-debug.apk
```

## 💻 Instalación PC

### Windows

```bash
# 1. Instalar Python 3.7+
# 2. Ejecutar:
pip install -r requirements.txt
python clap-trigger.py --configure
```

### Linux/macOS

```bash
# 1. Instalar Python 3.7+
# 2. Ejecutar:
pip install -r requirements.txt
python clap-trigger.py --configure
```

### Arranque Automático (Windows)

```bash
python clap-trigger.py --configure
# En la interfaz, marca "Iniciar con Windows"
```

## ⚙️ Configuración

### Archivo de Configuración

El archivo `clap-config.json` almacena:
- Umbral de sensibilidad (dB)
- Lista de aplicaciones

```json
{
  "threshold": 30.0,
  "apps": [
    "C:\\Path\\To\\App.lnk",
    "C:\\Path\\To\\Another\\App.lnk"
  ]
}
```

### Ajustar Sensibilidad

En la interfaz gráfica:
- **Umbral más bajo (20-25)**: Más sensible
- **Umbral más alto (35-40)**: Menos sensible

## 🐳 Compilación con Docker

### Requisitos

1. [Docker Desktop](https://www.docker.com/products/docker-desktop) instalado
2. ~5GB de espacio en disco
3. Conexión a internet

### Pasos

```bash
# Windows
build-apk.bat

# Linux/Mac
chmod +x build-apk.sh
./build-apk.sh
```

**Tiempo estimado: 15-20 minutos**

Ver [DOCKER_BUILD.md](DOCKER_BUILD.md) para más detalles.

## 📖 Uso

### Android

1. Abre la app
2. Toca el ícono de engranaje para configurar
3. Agrega aplicaciones
4. Ajusta el umbral si es necesario
5. Presiona "Iniciar" y comienza a dar palmadas

### PC (Windows/Linux/macOS)

```bash
# Modo interfaz gráfica
python clap-trigger.py --configure

# Modo línea de comandos
python clap-trigger.py -t 30  # Umbral = 30dB
```

## 🔧 Soporte

### Problema: No detecta palmadas

- Aumenta el volumen del micrófono
- Disminuye el umbral (valor más bajo)
- Asegúrate de que el micrófono funciona

### Problema: Abre apps sin querer

- Aumenta el umbral (valor más alto)
- Usa un micrófono con mejor cancelación de ruido

### Problema: No compila con Docker

- Verifica que Docker está corriendo: `docker --version`
- Elimina la imagen anterior: `docker rmi clap-trigger-builder`
- Vuelve a intentar

## 📝 Licencia

MIT - Siéntete libre de usar, modificar y distribuir.

## 👨‍💻 Desarrollo

### Estructura del Código

```
PC (Windows/Linux/macOS)          Android
└─ clap-trigger.py               └─ clap-trigger-android.py
   ├─ Tkinter (GUI)                 └─ Kivy (UI Framework)
   ├─ sounddevice (micrófono)       └─ audiostream (micrófono)
   └─ numpy (procesamiento)
```

### Dependencias

Ver `requirements.txt`

### Compilar APK

Ver `DOCKER_BUILD.md`

## 🎯 Roadmap

- [ ] Acceso a cámara para verificación visual
- [ ] Grabar eventos de palmada
- [ ] Interfaz más avanzada en Android
- [ ] Soporte para iOS
- [ ] App para sincronización en la nube

## 🤝 Contribuciones

Eres bienvenido a contribuir. Por favor:

1. Fork el repositorio
2. Crea una rama para tu característica
3. Commit con mensajes claros
4. Push a la rama
5. Abre un Pull Request

---

**Hecho con ❤️ por desarrolladores apasionados**
