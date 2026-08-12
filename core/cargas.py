"""
Cálculo de cargas de entrenamiento a partir de datos de FC.

Dos métricas, porque miden cosas distintas y Carlos usa ambas:

  - hrTSS  : carga basada en intensidad relativa al umbral (FC).
             Objetiva, no depende de la percepción del atleta.
  - Foster : sRPE × minutos. Es la que ya usa GymCoach Pro para fuerza,
             así que mantenerla permite sumar carga de fuerza + carrera
             en la misma escala (AU).

Cuando el reloj no aporta RPE (Garmin no lo da salvo que lo metas a mano),
se estima a partir de la distribución de tiempo en zonas — ver
`estimar_rpe_desde_zonas`. Ese RPE estimado se marca como tal para que
el atleta pueda corregirlo luego en la app.
"""


def calcular_hrtss(dur_min, fc_avg, fc_umbral, fc_reposo=None):
    """
    hrTSS ≈ horas × IF² × 100, donde IF = FC media / FC umbral.

    Si se conoce la FC de reposo se usa la reserva de FC (método Karvonen),
    que es más fiel a intensidades bajas; si no, se usa FC bruta.

    Devuelve None si faltan datos imprescindibles.
    """
    if not dur_min or not fc_avg or not fc_umbral:
        return None
    try:
        if fc_reposo and fc_umbral > fc_reposo:
            # Reserva de FC: descuenta el "suelo" fisiológico
            intensidad = (fc_avg - fc_reposo) / (fc_umbral - fc_reposo)
        else:
            intensidad = fc_avg / fc_umbral
        if intensidad <= 0:
            return None
        horas = dur_min / 60.0
        return round(horas * (intensidad ** 2) * 100, 1)
    except (TypeError, ZeroDivisionError):
        return None


def estimar_rpe_desde_zonas(zonas):
    """
    Estima un RPE (1-10) ponderando el tiempo pasado en cada zona de FC.

    Los pesos aproximan la percepción de esfuerzo típica de cada zona.
    Es una ESTIMACIÓN: el atleta debería poder corregirla en la app,
    porque la percepción real depende de fatiga previa, calor, sueño, etc.

    `zonas` es una lista tipo [{'z':1,'min':10}, {'z':2,'min':25}, ...]
    """
    if not zonas:
        return None
    pesos = {1: 2, 2: 4, 3: 6, 4: 8, 5: 10}
    total_min = sum(z.get("min", 0) for z in zonas)
    if not total_min:
        return None
    acumulado = sum(pesos.get(z.get("z"), 5) * z.get("min", 0) for z in zonas)
    return round(acumulado / total_min, 1)


def calcular_foster(dur_min, rpe):
    """Carga Foster clásica: sRPE × duración en minutos. Devuelve unidades arbitrarias (AU)."""
    if not dur_min or not rpe:
        return None
    return round(dur_min * rpe, 1)


def normalizar_zonas_garmin(hr_timezones):
    """
    Traduce la respuesta de get_activity_hr_in_timezones() de Garmin al
    formato del hub: [{'z':1,'min':5.2}, ...] ordenado por zona.

    Garmin devuelve una lista de dicts con 'zoneNumber' y 'secsInZone'.
    Las zonas usadas son las que el propio atleta tiene configuradas en
    su perfil de Garmin Connect, que es justo lo que queremos.
    """
    if not hr_timezones:
        return None
    zonas = []
    for z in hr_timezones:
        num = z.get("zoneNumber")
        secs = z.get("secsInZone") or 0
        if num is None:
            continue
        zonas.append({"z": int(num), "min": round(secs / 60.0, 1)})
    zonas.sort(key=lambda x: x["z"])
    # Si todas las zonas están a cero, no aporta nada
    if not any(z["min"] > 0 for z in zonas):
        return None
    return zonas
