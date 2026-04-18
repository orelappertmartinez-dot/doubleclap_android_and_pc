#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script simple para iniciar el servidor web
"""

import os
import subprocess
import sys

def main():
    print("\n" + "="*50)
    print("  🎉 Clap Trigger - Servidor Web")
    print("="*50 + "\n")
    
    print("📂 Directorio:", os.getcwd())
    print("🌐 Abre: http://localhost:8000")
    print("\n⚠️  Presiona Ctrl+C para detener el servidor\n")
    
    try:
        # Ejecutar el servidor
        os.system("python server.py")
    except KeyboardInterrupt:
        print("\n\n👋 Servidor detenido.")
        sys.exit(0)

if __name__ == "__main__":
    main()
