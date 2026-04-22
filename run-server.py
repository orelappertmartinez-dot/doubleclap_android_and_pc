#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys


def main():
    print("\n" + "=" * 50)
    print("  Clap Trigger - Servidor de descargas")
    print("=" * 50 + "\n")
    print("Directorio:", os.getcwd())
    print("Abre: http://localhost:8000")
    print("\nPresiona Ctrl+C para detener el servidor.\n")

    try:
        os.system("python server.py")
    except KeyboardInterrupt:
        print("\nServidor detenido.")
        sys.exit(0)


if __name__ == "__main__":
    main()
