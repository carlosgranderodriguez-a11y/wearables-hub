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


def buscar_valor_recursivo(obj, claves):
    """
    Busca la primera clave de `claves` dentro de una estructura anidada
    (dicts y listas) y devuelve su valor numérico.

    Necesario porque la forma exacta de las respuestas de Garmin cambia
    entre versiones de la API y entre perfiles de usuario; buscar por
    nombre de clave es más resistente que asumir una ruta fija.
    """
    if isinstance(obj, dict):
        for k in claves:
            v = obj.get(k)
            if isinstance(v, (int, float)) and 100 < v < 240:
                return int(v)
        for v in obj.values():
            r = buscar_valor_recursivo(v, claves)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = buscar_valor_recursivo(v, claves)
            if r:
                return r
    return None


def obtener_fc_max(client, activities=None):
    """
    FC máxima del atleta, probando varias fuentes en orden de fiabilidad.
    Se usa para estimar el umbral cuando Garmin no lo tiene medido.
    """
    manual = os.environ.get("GARMIN_FC_MAX", "").strip()
    if manual.isdigit():
        return int(manual), "Secret GARMIN_FC_MAX"

    claves = [
        "maxHeartRateUsed", "maxHeartRate", "userMaxHeartRate",
        "maxHr", "max_hr", "lactateThresholdMaxHeartRate",
    ]

    for nombre, fn in [
        ("zonas FC del perfil", lambda: client.get_heart_rate_zones()),
        ("ajustes de perfil", lambda: client.get_userprofile_settings()),
        ("perfil de usuario", lambda: client.get_user_profile()),
    ]:
        datos = safe(fn, nombre)
        val = buscar_valor_recursivo(datos, claves)
        if val:
            return val, nombre

    # Último recurso: la FC más alta registrada hoy en sus propias actividades.
    # Es un suelo, no un techo real: si hoy no apretó, subestimará la FC máx.
    if activities:
        picos = [a.get("maxHR") for a in activities if isinstance(a.get("maxHR"), (int, float))]
        if picos:
            return int(max(picos)), "FC máx observada hoy (aproximación baja)"

    return None, None


def umbral_desde_zonas(client):
    """
    Deriva la FC umbral del límite inferior de la Zona 4 configurada en Garmin.

    Es la mejor fuente disponible cuando no hay un test de lactato: por
    definición, la Z4 empieza en el umbral. Además usa la configuración
    que el propio atleta ya tiene hecha, en vez de inventar porcentajes.

    Se imprime la estructura recibida para poder diagnosticarla desde el
    log del Action, ya que el formato varía entre perfiles.
    """
    zonas = safe(lambda: client.get_heart_rate_zones(), "zonas FC del perfil")
    if not zonas:
        return None

    print(f"[diagnóstico] zonas FC del perfil: {str(zonas)[:600]}")

    perfiles = zonas if isinstance(zonas, list) else [zonas]
    for perfil in perfiles:
        if not isinstance(perfil, dict):
            continue
        # Garmin suele exponer los límites como zoneNLowBoundary
        for clave in ("zone4LowBoundary", "zone4Floor", "zone4Low"):
            val = perfil.get(clave)
            if isinstance(val, (int, float)) and 100 < val < 220:
                deporte = perfil.get("sport") or perfil.get("sportType") or "general"
                print(f"FC umbral: {int(val)} ppm (inicio de Z4 configurado en Garmin, perfil '{deporte}')")
                return int(val)
    return None


def obtener_fc_umbral(client, activities=None):
    """
    FC umbral (LTHR), necesaria para calcular hrTSS.

    Prioridad, de más a menos fiable:
      1. Umbral medido que Garmin mantiene (test de lactato).
      2. Secret GARMIN_FC_UMBRAL, si lo has fijado a mano.
      3. Inicio de la Zona 4 configurada en Garmin — por definición, el umbral.
      4. Porcentaje de la FC máxima (88% por defecto).

    Sobre las opciones 3 y 4: el hrTSS depende del CUADRADO de la intensidad,
    así que un error de 8-10 ppm en el umbral se amplifica en la carga. Son
    válidas para seguir TENDENCIAS entre semanas, pero para valores absolutos
    comparables conviene un test real de 20-30 min.
    """
    lt = safe(lambda: client.get_lactate_threshold(latest=True), "FC umbral")
    val = buscar_valor_recursivo(lt, ["heartRate", "lactateThresholdHeartRate", "value"])
    if val:
        print(f"FC umbral: {val} ppm (medido por Garmin)")
        return val

    manual = os.environ.get("GARMIN_FC_UMBRAL", "").strip()
    if manual.isdigit():
        print(f"FC umbral: {manual} ppm (Secret GARMIN_FC_UMBRAL)")
        return int(manual)

    val = umbral_desde_zonas(client)
    if val:
        return val

    # Estimación desde FC máx. Porcentaje configurable: corredores
    # entrenados suelen situarse en 88-92% de la FC máx.
    try:
        pct = float(os.environ.get("GARMIN_UMBRAL_PCT", "88")) / 100.0
    except ValueError:
        pct = 0.88

    fc_max, origen = obtener_fc_max(client, activities)
    if fc_max:
        estimado = int(round(fc_max * pct))
        aviso = ""
        if origen and "observada" in origen:
            # La FC máx de una sesión cualquiera NO es la FC máx real del
            # atleta salvo que ese día fuese a tope: subestima el techo y,
            # por tanto, infla la intensidad relativa y el TSS.
            aviso = " ⚠️ Basado en una sesión no máxima: el TSS saldrá inflado."
        print(
            f"FC umbral: {estimado} ppm ESTIMADO como {int(pct*100)}% de FC máx "
            f"{fc_max} (origen: {origen}).{aviso}"
        )
        return estimado

    print("⚠️  Sin FC umbral ni FC máx: no se puede calcular hrTSS.", file=sys.stderr)
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

    # Identificador único y estable de la actividad en su plataforma de origen.
    # Permite que el destino haga "upsert" en vez de insertar: si el sync se
    # repite (relanzado a mano, reintento del cron...), la fila se actualiza
    # en lugar de duplicarse.
    if activity_id:
        actividad["origen_id"] = f"garmin_{activity_id}"

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
    activities = safe(lambda: client.get_activities_by_date(d, today), "actividades")

    # La FC umbral y la de reposo se calculan una sola vez y se reutilizan
    # para todas las actividades del día. Se pasan las actividades porque,
    # si no hay otra fuente, la FC máx observada sirve de último recurso.
    fc_umbral = obtener_fc_umbral(client, activities)
    fc_reposo = wellness.get("rhr")

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
