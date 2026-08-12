"""
Config de destinos: a qué apps se manda cada actividad, y con qué nombre
de atleta en cada una.

Añadir una app nueva = añadir una entrada aquí. No hace falta tocar
los conectores de marca ni el resto de la lógica.
"""

import json
import sys

import requests

# ── Triatlon-atleta ──
# Recibe TODO (wellness + todas las actividades), tal y como funciona hoy.
TRIATLON_ATLETA = {
    "nombre": "triatlon-atleta",
    "url": "https://script.google.com/macros/s/AKfycbz5e_jS99e3xB-DJMbIEm3L_HXoS2rkED_o3n0_U6S2Ihnc9vJ2E0gUIcYukv4ZyVXI/exec",
    "acepta": {"running", "cycling", "swimming", "other"},  # todo tipo de actividad
    "atleta_map": {
        "CGR": "CGR",
        # "nacho": "nacho",  # cuando Nacho tenga su cuenta Garmin propia
    },
}

# ── GymCoach Pro ──
# Solo recibe carreras (running), como sesiones de "Resistencia".
GYMCOACH_PRO = {
    "nombre": "gymcoach-pro",
    "url": "https://script.google.com/macros/s/AKfycbzqXBcIAhrrXHXs2u1_jk8137QI17VxC_IKA3z15cm4ZKwlkTYFbB96zjKpoxk07B4yUA/exec",
    "acepta": {"running"},
    "atleta_map": {
        "CGR": "Carlos Grande",  # nombre tal cual está en el Sheet de GymCoach Pro
    },
}

DESTINOS = [TRIATLON_ATLETA, GYMCOACH_PRO]

# Nota: el RPE ya no se fija por defecto. Se estima desde la distribución
# de zonas de FC (ver core/cargas.py) y se marca como estimado para que el
# atleta pueda corregirlo en la app. Si no hay pulsómetro, queda vacío.


def enviar_actividad_a_destinos(actividad):
    """
    Recorre todos los destinos configurados y envía la actividad a los que
    la acepten (por tipo) y tengan mapeo para ese atleta.
    `actividad` es un dict con las claves de core.schema.Actividad.
    """
    for destino in DESTINOS:
        if actividad["tipo"] not in destino["acepta"]:
            continue
        atleta_destino = destino["atleta_map"].get(actividad["atleta_key"])
        if not atleta_destino:
            continue  # este atleta no está vinculado a esta app

        payload = _payload_para_destino(destino, atleta_destino, actividad)
        try:
            resp = requests.post(destino["url"], json=payload, timeout=30)
            print(f"[{destino['nombre']}] → {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"⚠️  Aviso: fallo enviando a {destino['nombre']} ({e})", file=sys.stderr)


def enviar_wellness_a_triatlon(atleta_key, fecha, wellness):
    """
    El wellness (sueño, HRV, FC reposo, Body Battery) hoy solo lo consume
    triatlon-atleta, así que se envía aparte de las actividades.
    `wellness` es el dict de campos sleep_*, hrv_*, rhr, body_battery_*.
    """
    atleta_destino = TRIATLON_ATLETA["atleta_map"].get(atleta_key)
    if not atleta_destino or not wellness:
        return

    payload = {
        "type": "garmin",
        "athlete": atleta_destino,
        "data": dict(wellness, fecha=fecha),
    }
    try:
        resp = requests.post(TRIATLON_ATLETA["url"], json=payload, timeout=30)
        print(f"[triatlon-atleta wellness] → {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"⚠️  Aviso: fallo enviando wellness a triatlon-atleta ({e})", file=sys.stderr)


def _payload_para_destino(destino, atleta_destino, actividad):
    """Traduce la actividad normalizada al formato que espera cada app."""
    if destino["nombre"] == "triatlon-atleta":
        return {
            "type": "garmin",  # mantenido por compatibilidad con el backend actual
            "athlete": atleta_destino,
            "data": {
                "fecha": actividad["fecha"],
                "actividades": [{
                    "tipo": actividad["tipo"],
                    "dur_seg": (actividad["dur_min"] or 0) * 60,
                    "dist_m": (actividad["dist_km"] or 0) * 1000,
                    "fc_avg": actividad["fc_avg"],
                    "fc_max": actividad["fc_max"],
                }],
            },
        }

    if destino["nombre"] == "gymcoach-pro":
        dur = actividad["dur_min"]
        dist = actividad["dist_km"]
        fuente = actividad["fuente"].capitalize()
        zonas = actividad.get("zonas")
        rpe = actividad.get("rpe")
        payload = {
            "action": "addResistencia",
            "tipo": "sesion",
            "atleta": atleta_destino,
            "fecha": actividad["fecha"],
            "disciplina": "Carrera",
            "nombre": f"Carrera ({fuente})",
            "duracion_min": dur,
            "distancia_km": dist,
            "rpe_objetivo": "",
            "tss": actividad.get("tss") or "",
            "descripcion": f"Sincronizado automáticamente desde {fuente}.",
            "duracion_real": dur,
            "distancia_real": dist,
            "rpe_real": rpe if rpe is not None else "",
            "fc_media": actividad["fc_avg"] or "",
            "fc_max": actividad["fc_max"] or "",
            "notas_atleta": "",
            # ── Campos ampliados ──
            # zonas_real va serializado como JSON porque el backend guarda
            # cada campo en una celda del Sheet.
            "zonas_real": json.dumps(zonas) if zonas else "",
            "tss_real": actividad.get("tss") or "",
            "foster_real": actividad.get("foster") or "",
            "rpe_estimado": "sí" if actividad.get("rpe_estimado") else "",
            "desnivel_m": actividad.get("desnivel_m") or "",
            "ritmo_medio": actividad.get("ritmo_medio") or "",
            "cadencia": actividad.get("cadencia") or "",
            "fuente_datos": fuente,
            # Clave única de la actividad en origen: el backend la usa para
            # actualizar en vez de duplicar si el sync se repite.
            "origen_id": actividad.get("origen_id") or "",
        }
        return payload

    raise ValueError(f"Destino desconocido: {destino['nombre']}")
