#!/usr/bin/env python3
"""
Autorización OAuth2 con Polar AccessLink — SE EJECUTA A MANO, UNA VEZ POR
ATLETA. No forma parte del cron diario (ver connectors/polar/sync.py para
eso).

A diferencia de Garmin, Polar no admite login con email/contraseña desde
un script: el atleta tiene que autorizar la app explícitamente en su
navegador (flujo OAuth2). Este script automatiza el resto: levanta un
mini servidor local para capturar el código de autorización, lo cambia
por un access_token, registra al usuario en Polar, y te imprime los
valores que debes guardar como GitHub Secrets.

Requisitos previos (una sola vez, por app, no por atleta):
  1. Entra en https://admin.polaraccesslink.com/ con una cuenta Polar
     Flow y crea un cliente OAuth2 nuevo.
  2. Como "Authorization redirect URL" pon exactamente:
       http://localhost:5050/callback
  3. Copia el Client ID y el Client Secret que te da Polar.

Uso:
  export POLAR_CLIENT_ID="..."
  export POLAR_CLIENT_SECRET="..."
  python connectors/polar/authorize.py

Luego, el atleta (puedes ser tú mismo) abre la URL que imprime el script,
inicia sesión en Polar Flow y da permiso. El script recoge el resultado
automáticamente y lo imprime en la terminal.
"""
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import requests

REDIRECT_URI = "http://localhost:5050/callback"
AUTH_URL = "https://flow.polar.com/oauth2/authorization"
TOKEN_URL = "https://polarremote.com/v2/oauth2/token"
REGISTER_URL = "https://www.polaraccesslink.com/v3/users"

_captured_code = {}


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        code = qs.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if code:
            _captured_code["code"] = code
            self.wfile.write("<h2>✅ Autorización recibida. Puedes cerrar esta pestaña y volver a la terminal.</h2>".encode())
        else:
            self.wfile.write("<h2>❌ No se recibió código de autorización.</h2>".encode())

    def log_message(self, format, *args):
        pass  # silencia el log HTTP por defecto


def main():
    client_id = os.environ.get("POLAR_CLIENT_ID")
    client_secret = os.environ.get("POLAR_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("❌ Faltan POLAR_CLIENT_ID / POLAR_CLIENT_SECRET en el entorno", file=sys.stderr)
        sys.exit(1)

    member_id = input("Clave interna del atleta que se va a vincular (ej. CGR, nacho): ").strip()
    if not member_id:
        print("❌ Necesito una clave de atleta (ej. CGR)", file=sys.stderr)
        sys.exit(1)

    auth_link = f"{AUTH_URL}?response_type=code&client_id={client_id}"
    print(f"\n1. Abre este enlace y autoriza el acceso en Polar Flow:\n\n   {auth_link}\n")
    try:
        webbrowser.open(auth_link)
    except Exception:
        pass

    server = HTTPServer(("localhost", 5050), CallbackHandler)
    print("2. Esperando la autorización en http://localhost:5050 ...")
    while "code" not in _captured_code:
        server.handle_request()

    code = _captured_code["code"]
    print("3. Código recibido, cambiándolo por un access_token...")

    resp = requests.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        headers={"Accept": "application/json"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    resp.raise_for_status()
    token_data = resp.json()
    access_token = token_data["access_token"]
    polar_user_id = token_data["x_user_id"]

    print("4. Registrando al usuario en Polar AccessLink...")
    reg = requests.post(
        REGISTER_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"member-id": member_id},
    )
    if reg.status_code == 409:
        print("   (el usuario ya estaba registrado para esta app, no pasa nada)")
    else:
        reg.raise_for_status()

    print("\n✅ Listo. Guarda estos valores como GitHub Secrets en el repo:\n")
    print(f"   POLAR_CLIENT_ID       = {client_id}")
    print(f"   POLAR_CLIENT_SECRET   = {client_secret}")
    print(f"   POLAR_ACCESS_TOKEN_{member_id.upper()} = {access_token}")
    print(f"   POLAR_USER_ID_{member_id.upper()} = {polar_user_id}")
    print("\n(Los tokens de Polar no caducan salvo que el atleta revoque el acceso.)")


if __name__ == "__main__":
    main()
