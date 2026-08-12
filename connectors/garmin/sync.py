#!/usr/bin/env python3
"""
Conector de Garmin Connect.

Lee wellness (sueño, HRV, FC reposo, Body Battery) y actividades del día,
las normaliza al esquema común (core/schema.py) y las reparte a las apps
configuradas en core/destinations.py.

Se ejecuta automáticamente cada día vía GitHub Actions
(ver .github/workflows/garmin-sync.yml).

Variables de entorno requeridas (GitHub Secrets):
  GARMIN_EMAIL     - email de la cuenta de Garmin Connect
  GARMIN_PASSWORD  - contraseña de esa cuenta
  GARMIN_ATHLETE   - clave interna del atleta, ej. "CGR" (default: "CGR")
"""
import os
import sys
from datetime import date, timedelta, datetime, timezone

import garminconnect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from core.schema import GARMIN_RUNNING_KEYS
from core.destinations import enviar_actividad_a_destinos, enviar_wellness_a_triatlon
from core.cargas import (
    calcular_hrtss,
    calcular_foster,
    estimar_rpe_desde_zonas,
    normalizar_zonas_garmin,
)


def safe(fn, label):
    """Ejecuta fn() y no rompe todo el script si Garmin no tiene ese dato hoy."""
    try:
        return fn()
    except Exception as e:
        print(f"⚠️  Aviso: no se pudo leer '{label}' ({e})", file=sys.stderr)
        return None


def fmt_local_ts(ms):
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%H:%M")


def normalizar_tipo(type_key):
    """Traduce el typeKey de Garmin a la categoría normalizada del hub."""
    type_key = (type_key or "").lower()
    if type_key in GARMIN_RUNNING_KEYS:
        return "running"
    if "cycling" in type_key or "biking" in type_key:
        return "cycling"
    if "swim" in type_key:
        return "swimming"
    if "strength" in type_key or type_key == "fitness_equipment":
        return "strength"
    return "other"


def obtener_fc_umbral(client):
    """
    FC umbral (LTHR) del atleta, necesaria para calcular hrTSS.

    Se intenta leer de Garmin (test de umbral de lactato). Si Garmin no la
    tiene, se puede fijar a mano con la variable de entorno GARMIN_FC_UMBRAL.
    Sin umbral no se puede calcular hrTSS — se devuelve None y ese campo
    simplemente queda vacío, sin romper el resto del sync.
    """
    manual = os.environ.get("GARMIN_FC_UMBRAL", "").strip()
    if manual.isdigit():
        return int(manual)

    lt = safe(lambda: client.get_lactate_threshold(latest=True), "FC umbral")
    if not lt:
        return None
    # La respuesta varía de forma según versión de la API; se buscan las
    # claves más habituales sin asumir una estructura fija.
    for key in ("heartRate", "lactateThresholdHeartRate", "value"):
        val = lt.get(key) if isinstance(lt, dict) else None
        if isinstance(val, (int, float)) and val > 0:
            return int(val)
    return None


def formatea_ritmo(dur_seg, dist_m):
    """Ritmo medio en mm:ss por km. Devuelve None si no aplica (ej. fuerza)."""
    if not dur_seg or not dist_m or dist_m < 100:
        return None
    seg_por_km = dur_seg / (dist_m / 1000.0)
    minutos = int(seg_por_km // 60)
    segundos = int(round(seg_por_km % 60))
    if segundos == 60:
        minutos, segundos = minutos + 1, 0
    return f"{minutos}:{segundos:02d}"


def enriquecer_actividad(client, a, actividad, fc_umbral, fc_reposo):
    """
    Añade a la actividad las métricas ampliadas: tiempo en zonas de FC,
    hrTSS, RPE estimado y carga Foster.

    Cada dato es opcional: si Garmin no lo tiene para esa actividad
    (por ejemplo una carrera sin pulsómetro), se deja vacío y el resto
    del sync continúa igual.
    """
    activity_id = a.get("activityId")

    # ── Tiempo en zonas de FC (usa las zonas configuradas por el atleta en Garmin) ──
    if activity_id:
        hr_zones = safe(
            lambda: client.get_activity_hr_in_timezones(str(activity_id)),
            f"zonas FC actividad {activity_id}",
        )
        actividad["zonas"] = normalizar_zonas_garmin(hr_zones)

    # ── Cargas ──
    actividad["tss"] = calcular_hrtss(
        actividad["dur_min"], actividad["fc_avg"], fc_umbral, fc_reposo
    )

    # Garmin no aporta RPE; se estima desde la distribución de zonas.
    # Si no hay zonas (sin pulsómetro), no se inventa: queda vacío para
    # que el atleta lo rellene a mano en la app.
    rpe = estimar_rpe_desde_zonas(actividad.get("zonas"))
    actividad["rpe"] = rpe
    actividad["rpe_estimado"] = bool(rpe)  # marca que NO lo puso el atleta
    actividad["foster"] = calcular_foster(actividad["dur_min"], rpe)

    # ── Métricas extra ──
    actividad["desnivel_m"] = a.get("elevationGain")
    actividad["ritmo_medio"] = formatea_ritmo(a.get("duration"), a.get("distance"))
    actividad["cadencia"] = a.get("averageRunningCadenceInStepsPerMinute")

    return actividad


def main():
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    atleta_key = os.environ.get("GARMIN_ATHLETE", "CGR")
    if not email or not password:
        print("❌ Faltan GARMIN_EMAIL / GARMIN_PASSWORD en el entorno", file=sys.stderr)
        sys.exit(1)

    client = garminconnect.Garmin(email, password)
    client.login()

    # Los datos de sueño/HRV/Body Battery de la noche corresponden al día "de ayer".
    # Se puede forzar una fecha concreta (para recuperar un día que falló)
    # con la variable de entorno GARMIN_SYNC_DATE=YYYY-MM-DD.
    override = os.environ.get("GARMIN_SYNC_DATE", "").strip()
    d = override if override else (date.today() - timedelta(days=1)).isoformat()
    today = date.today().isoformat()

    # ── Wellness (solo lo consume triatlon-atleta por ahora) ──
    wellness = {}

    sleep = safe(lambda: client.get_sleep_data(d), "sueño")
    if sleep:
        dto = sleep.get("dailySleepDTO") or {}
        wellness["sleep_score"] = (dto.get("sleepScores") or {}).get("overall", {}).get("value")
        wellness["sleep_total_min"] = (dto.get("sleepTimeSeconds") or 0) // 60
        wellness["sleep_deep_min"] = (dto.get("deepSleepSeconds") or 0) // 60
        wellness["sleep_light_min"] = (dto.get("lightSleepSeconds") or 0) // 60
        wellness["sleep_rem_min"] = (dto.get("remSleepSeconds") or 0) // 60
        wellness["sleep_awake_min"] = (dto.get("awakeSleepSeconds") or 0) // 60
        wellness["sleep_start"] = fmt_local_ts(dto.get("sleepStartTimestampLocal") or dto.get("sleepStartTimestampGMT"))
        wellness["sleep_end"] = fmt_local_ts(dto.get("sleepEndTimestampLocal") or dto.get("sleepEndTimestampGMT"))

    hrv = safe(lambda: client.get_hrv_data(d), "HRV")
    if hrv:
        wellness["hrv_last_night_avg"] = (hrv.get("hrvSummary") or {}).get("lastNightAvg")

    rhr = safe(lambda: client.get_rhr_day(d), "FC reposo")
    if rhr:
        try:
            metrics = rhr["allMetrics"]["metricsMap"]["WELLNESS_RESTING_HEART_RATE"]
            wellness["rhr"] = metrics[0]["value"] if metrics else None
        except Exception:
            pass

    bb = safe(lambda: client.get_body_battery(d, d), "Body Battery")
    if bb:
        try:
            vals = [p[1] for p in bb[0].get("bodyBatteryValuesArray", []) if p[1] is not None]
            if vals:
                wellness["body_battery_min"] = min(vals)
                wellness["body_battery_max"] = max(vals)
        except Exception:
            pass

    enviar_wellness_a_triatlon(atleta_key, d, wellness)

    # ── Actividades (repartidas según core/destinations.py) ──
    # La FC umbral y la de reposo se leen una sola vez y se reutilizan
    # para calcular la carga de todas las actividades del día.
    fc_umbral = obtener_fc_umbral(client)
    fc_reposo = wellness.get("rhr")
    if not fc_umbral:
        print(
            "⚠️  Sin FC umbral: no se podrá calcular hrTSS. "
            "Puedes fijarla con el Secret GARMIN_FC_UMBRAL.",
            file=sys.stderr,
        )

    activities = safe(lambda: client.get_activities_by_date(d, today), "actividades")
    if activities:
        for a in activities:
            actividad = {
                "atleta_key": atleta_key,
                "fecha": d,
                "tipo": normalizar_tipo((a.get("activityType") or {}).get("typeKey")),
                "dur_min": round((a.get("duration") or 0) / 60, 1),
                "dist_km": round((a.get("distance") or 0) / 1000, 2),
                "fc_avg": a.get("averageHR"),
                "fc_max": a.get("maxHR"),
                "fuente": "garmin",
            }
            actividad = enriquecer_actividad(client, a, actividad, fc_umbral, fc_reposo)
            enviar_actividad_a_destinos(actividad)


if __name__ == "__main__":
    main()
