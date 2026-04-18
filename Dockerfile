FROM ubuntu:22.04

# Evitar prompts interactivos
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    zip \
    unzip \
    openjdk-17-jdk \
    python3 \
    python3-pip \
    autoconf \
    libtool \
    pkg-config \
    zlib1g-dev \
    libncurses5-dev \
    libncursesw5-dev \
    libtinfo6 \
    cmake \
    libffi-dev \
    libssl-dev \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar Buildozer y python-for-android con todas las dependencias
RUN pip3 install --upgrade pip setuptools packaging
RUN pip3 install Cython==0.29.36 kivy numpy python-for-android buildozer appdirs colorama jinja2 sh toml

# Crear usuario no-root PRIMERO (antes de usar /home/builduser/)
RUN useradd --create-home --shell /bin/bash builduser

# Configurar Android SDK/NDK variables para buildozer
ENV ANDROID_SDK_ROOT=/home/builduser/.buildozer/android/platform/android-sdk
ENV ANDROID_HOME=/home/builduser/.buildozer/android/platform/android-sdk
ENV PATH=/home/builduser/.buildozer/android/platform/android-sdk/cmdline-tools/latest/bin:$PATH

# Instalar Android SDK tools y plataforma requerida para API 33
RUN mkdir -p /home/builduser/.buildozer/android/platform/android-sdk/cmdline-tools && \
    cd /home/builduser/.buildozer/android/platform/android-sdk && \
    wget -q https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -O /tmp/cmdline-tools.zip && \
    unzip -q /tmp/cmdline-tools.zip -d /home/builduser/.buildozer/android/platform/android-sdk/cmdline-tools && \
    mv /home/builduser/.buildozer/android/platform/android-sdk/cmdline-tools/cmdline-tools /home/builduser/.buildozer/android/platform/android-sdk/cmdline-tools/latest && \
    yes | /home/builduser/.buildozer/android/platform/android-sdk/cmdline-tools/latest/bin/sdkmanager --sdk_root=/home/builduser/.buildozer/android/platform/android-sdk --licenses && \
    /home/builduser/.buildozer/android/platform/android-sdk/cmdline-tools/latest/bin/sdkmanager --sdk_root=/home/builduser/.buildozer/android/platform/android-sdk --install "platform-tools" "platforms;android-33" "build-tools;33.0.0" && \
    chown -R builduser:builduser /home/builduser/.buildozer

# Crear directorio de trabajo
WORKDIR /app

# Copiar código fuente
COPY . /app/

# Cambiar propietario de los archivos copiados
RUN chown -R builduser:builduser /app

# Copiar entrypoint script antes de cambiar de usuario para evitar errores de permisos
COPY --chmod=755 entrypoint.sh /entrypoint.sh

USER builduser

# Configurar JAVA_HOME
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

# Usar el entrypoint para compilar APK
ENTRYPOINT ["/entrypoint.sh"]
