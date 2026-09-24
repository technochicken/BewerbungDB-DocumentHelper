"""Entwicklungsstart: Server auf festem Port (Standard 8765, per Umgebungsvariable PORT änderbar), ohne Fenster."""

import os

from bewerbungdb.server import create_server

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8765"))
    server, _ = create_server(port=port)
    print(f"http://127.0.0.1:{port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
