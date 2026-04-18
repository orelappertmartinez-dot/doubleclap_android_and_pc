#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor web simple para servir la página de Clap Trigger
Permite descargar archivos y ver instrucciones
"""

import os
import http.server
import socketserver
import json
import zipfile
from pathlib import Path
from urllib.parse import unquote

PORT = 8000
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

class ClapTriggerHandler(http.server.SimpleHTTPRequestHandler):
    """Manejador personalizado para servir archivos y descargas"""
    
    def do_GET(self):
        """Manejar solicitudes GET"""
        # Ruta principal
        if self.path == '/':
            self.path = '/index.html'
        
        # Descargar código Python
        elif self.path == '/api/download-python':
            self.send_python_download()
            return
        
        # Descargar documentación
        elif self.path == '/api/download-docs':
            self.send_docs_download()
            return
        
        # API para obtener estado de compilación
        elif self.path == '/api/build-status':
            self.send_json_response({'status': 'ready', 'message': 'Ready to build with Docker'})
            return
        
        # Servir archivos estáticos
        try:
            super().do_GET()
        except Exception as e:
            self.send_error(500, str(e))
    
    def send_python_download(self):
        """Crear y enviar archivo ZIP con código Python"""
        try:
            # Archivos a incluir
            files = [
                'clap-trigger.py',
                'clap-config.json',
                'requirements.txt',
                'README-Android.md'
            ]
            
            zip_path = os.path.join(SCRIPT_DIR, 'clap-trigger-python.zip')
            
            # Crear ZIP
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file in files:
                    file_path = os.path.join(SCRIPT_DIR, file)
                    if os.path.exists(file_path):
                        zipf.write(file_path, arcname=file)
            
            # Enviar archivo
            self.send_response(200)
            self.send_header('Content-type', 'application/zip')
            self.send_header('Content-Disposition', 'attachment; filename="clap-trigger-python.zip"')
            self.send_header('Content-length', os.path.getsize(zip_path))
            self.end_headers()
            
            with open(zip_path, 'rb') as f:
                self.wfile.write(f.read())
            
            # Limpiar
            os.remove(zip_path)
            
        except Exception as e:
            self.send_error(500, f'Error al descargar: {str(e)}')
    
    def send_docs_download(self):
        """Enviar documentación y guías"""
        try:
            docs = {
                'titulo': 'Clap Trigger - Documentación Completa',
                'version': '0.1',
                'instrucciones_python': """
INSTALACIÓN RÁPIDA (Windows/Linux/Mac):

1. Instala Python 3.7+
2. Instala dependencias:
   pip install -r requirements.txt

3. Ejecuta con interfaz gráfica:
   python clap-trigger.py --configure

4. Selecciona aplicaciones y presiona Iniciar

PARÁMETROS DISPONIBLES:
- python clap-trigger.py -t 25        # Umbral de sensibilidad
- python clap-trigger.py --configure  # Abrir configurador
- python clap-trigger.py --uninstall  # Remover arranque automático

CONFIGURACIÓN AVANZADA:
- Edita clap-config.json para configuración manual
- Aumenta/disminuye threshold para ajustar sensibilidad
                """,
                'instrucciones_android': """
COMPILACIÓN CON DOCKER (Recomendado):

1. Instala Docker Desktop
2. Ejecuta: build-apk.bat (Windows) o ./build-apk.sh (Linux/Mac)
3. Espera 15-20 minutos
4. APK en: bin/claptrigger-0.1-debug.apk

INSTALACIÓN EN DISPOSITIVO:
1. Conecta teléfono por USB
2. Ejecuta: adb install bin/claptrigger-0.1-debug.apk
3. Alternativamente: copia APK al teléfono e instala desde ahí
                """
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Content-Disposition', 'attachment; filename="documentacion.json"')
            self.end_headers()
            self.wfile.write(json.dumps(docs, indent=2, ensure_ascii=False).encode('utf-8'))
            
        except Exception as e:
            self.send_error(500, f'Error: {str(e)}')
    
    def send_json_response(self, data):
        """Enviar respuesta JSON"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def end_headers(self):
        """Agregar headers CORS"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        super().end_headers()


if __name__ == '__main__':
    os.chdir(SCRIPT_DIR)
    
    print("""
    ╔═══════════════════════════════════════╗
    ║   🎉 Clap Trigger - Servidor Web    ║
    ╚═══════════════════════════════════════╝
    """)
    print(f"📂 Directorio: {SCRIPT_DIR}")
    print(f"🌐 Abre tu navegador en: http://localhost:{PORT}")
    print(f"📝 Archivos: index.html")
    print("\n⚠️  Presiona Ctrl+C para detener el servidor\n")
    
    with socketserver.TCPServer(("", PORT), ClapTriggerHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n👋 Servidor detenido.")
