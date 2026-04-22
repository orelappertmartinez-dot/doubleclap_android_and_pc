#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import http.server
import os
import socketserver

PORT = 8000
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class ClapTriggerHandler(http.server.SimpleHTTPRequestHandler):
    """Servidor estatico simple para index.html y archivos de descarga."""

    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".apk": "application/vnd.android.package-archive",
        ".exe": "application/octet-stream",
    }

    def do_GET(self):
        if self.path == "/":
            self.path = "/index.html"
        return super().do_GET()


if __name__ == "__main__":
    os.chdir(SCRIPT_DIR)

    print("\n" + "=" * 46)
    print("  Clap Trigger - Servidor de descargas")
    print("=" * 46 + "\n")
    print(f"Directorio: {SCRIPT_DIR}")
    print(f"Abre en el navegador: http://localhost:{PORT}")
    print("\nPresiona Ctrl+C para detener el servidor.\n")

    with socketserver.TCPServer(("", PORT), ClapTriggerHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor detenido.")
