#!/usr/bin/env python3
"""
Conector de Polar AccessLink.

A diferencia de Garmin (login directo), Polar requiere que cada atleta se
autorice una vez de antemano — ver connectors/polar/authorize.py. Este
script usa esos tokens ya guardados para traer las actividades nuevas.

Polar entrega los datos vía un modelo de "transacciones": hay que abrir
una transacción, listar lo que hay dentro, leer cada actividad, y por
último confirmar (commit) la transacción — solo entonces Polar la marca
como entregada y no la vuelve a repetir al día siguiente.

Variables de entorno requeridas (GitHub Secrets), UNA POR ATLETA vinculado:
  POLAR_CLIENT_ID
  POLAR_CLIENT_SECRET
  POLAR_ACCESS_TOKEN_<ATLETA>   ej. POLAR_ACCESS_TOKEN_CGR
  POLAR_USER_ID_<ATLETA>        ej. POLAR_USER_ID_CGR

Y una lista de atletas a sincronizar en POLAR_ATLETAS (separados por
coma), ej: "CGR,nacho"
"""
import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from core.destinations import enviar_actividad_a_destinos

BASE_URL = "https://www.polaraccesslink.com/v3"

# Sport keys de Polar que consideramos "running". Polar usa nombres como
# RUNNING, TRAIL_RUNNING, TRACK_AND_FIELD_RUNNING, etc.
POLAR_RUNNING_KEYS = {
    "RUNNING", "TRAIL_RUNNING", "TRACK_AND_FIELD_RUNNING", "TREADMILL_RUNNING",
}
POLAR_CYCLING_KEYS = {"CYCLING", "MOUNTAIN_BIKING", "ROAD_BIKING", "INDOOR_CYCLING"}
POLAR_SWIM_KEYS = {"SWIMMING", "OPEN_WATER_SWIMMING", "POOL_SWIMMING"}


def normalizar_tipo(sport):
    sport = (sport or "").upper()
    if sport in POLAR_RUNNING_KEYS:
        return "running"
    if sport in POLAR_CYCLING_KEYS:
        return "cycling"
    if sport in POLAR_SWIM_KEYS:
        return "swimming"
    if "STRENGTH" in sport:
        return "strength"
    return "other"


def sync_atleta(atleta_key):
    access_token = os.environ.get(f"POLAR_ACCESS_TOKEN_{atleta_key.upper()}")
    user_id = os.environ.get(f"POLAR_USER_ID_{atleta_key.upper()}")
    if not access_token or not user_id:
        print(f"⚠️  Faltan credenciales Polar para '{atleta_key}', se salta.", file=sys.stderr)
        return

    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

    # 1. Abrir transacción de ejercicios
    resp = requests.post(f"{BASE_URL}/users/{user_id}/exercise-transactions", headers=headers)
    if resp.status_code == 204:
        print(f"[{atleta_key}] Sin actividades nuevas en Polar.")
        return
    resp.raise_for_status()
    transaction_url = resp.json()["resource-uri"]

    # 2. Listar ejercicios dentro de la transacción
    resp = requests.get(transaction_url, headers=headers)
    resp.raise_for_status()
    exercise_urls = resp.json().get("exercises", [])

    # 3. Leer el resumen de cada ejercicio y repartirlo
    for ex_url in exercise_urls:
        resp = requests.get(ex_url, headers=headers)
        if not resp.ok:
            print(f"⚠️  No se pudo leer {ex_url}: {resp.status_code}", file=sys.stderr)
            continue
        ex = resp.json()

        duracion = ex.get("duration", "PT0S")  # formato ISO 8601, ej. "PT1H5M30S"
        dur_min = round(_parse_iso_duration_seconds(duracion) / 60, 1)

        actividad = {
            "atleta_key": atleta_key,
            "fecha": (ex.get("start-time") or "")[:10],
            "tipo": normalizar_tipo(ex.get("sport")),
            "dur_min": dur_min,
            "dist_km": round((ex.get("distance") or 0) / 1000, 2),
            "fc_avg": (ex.get("heart-rate") or {}).get("average"),
            "fc_max": (ex.get("heart-rate") or {}).get("maximum"),
            "fuente": "polar",
        }
        enviar_actividad_a_destinos(actividad)

    # 4. Confirmar la transacción (si no, Polar repetiría estos datos mañana)
    requests.put(transaction_url, headers=headers)
    print(f"[{atleta_key}] {len(exercise_urls)} actividad(es) sincronizada(s) desde Polar.")


def _parse_iso_duration_seconds(duration):
    """Convierte 'PT1H5M30S' a segundos. Muy simplificado, solo H/M/S."""
    import re
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", duration or "")
    if not m:
        return 0
    h, mi, s = m.groups()
    return (int(h or 0) * 3600) + (int(mi or 0) * 60) + float(s or 0)


def main():
    atletas = [a.strip() for a in os.environ.get("POLAR_ATLETAS", "").split(",") if a.strip()]
    if not atletas:
        print("❌ No hay atletas configurados en POLAR_ATLETAS", file=sys.stderr)
        sys.exit(1)
    for atleta_key in atletas:
        sync_atleta(atleta_key)


if __name__ == "__main__":
    main()
