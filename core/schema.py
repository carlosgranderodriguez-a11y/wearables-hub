"""
Esquema común de "actividad normalizada".

Cada conector de marca (garmin, polar, huawei, coros...) debe traducir
los datos de su propia API a este formato antes de pasarlos a
core/destinations.py. Así el resto del sistema (a qué apps se manda,
cómo se calcula la carga, etc.) no necesita saber nada de la marca de
origen.

Campos:
    atleta_key   str   Clave interna del atleta (ej. "CGR"), NO el nombre.
                        El mapeo a nombres de cada app vive en destinations.py
    fecha        str   'YYYY-MM-DD'
    tipo         str   Categoría normalizada: 'running' | 'cycling' | 'swimming'
                        | 'strength' | 'other'
    dur_min      float Duración en minutos
    dist_km      float Distancia en km (0 si no aplica, ej. fuerza)
    fc_avg       int | None  Frecuencia cardíaca media
    fc_max       int | None  Frecuencia cardíaca máxima
    fuente       str   Nombre de la marca de origen, ej. 'garmin'

Wellness (sueño, HRV, body battery, FC reposo) se mantiene como un
diccionario aparte más flexible, ya que varía mucho entre marcas.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Actividad:
    atleta_key: str
    fecha: str
    tipo: str          # 'running' | 'cycling' | 'swimming' | 'strength' | 'other'
    dur_min: float = 0
    dist_km: float = 0
    fc_avg: Optional[int] = None
    fc_max: Optional[int] = None
    fuente: str = ""

    def to_dict(self):
        return {
            "atleta_key": self.atleta_key,
            "fecha": self.fecha,
            "tipo": self.tipo,
            "dur_min": self.dur_min,
            "dist_km": self.dist_km,
            "fc_avg": self.fc_avg,
            "fc_max": self.fc_max,
            "fuente": self.fuente,
        }


# Tipos de actividad "crudos" (tal cual los da cada marca) que consideramos
# running. Cada conector mapea aquí sus propios valores.
GARMIN_RUNNING_KEYS = {
    "running", "trail_running", "treadmill_running",
    "track_running", "indoor_running", "street_running",
}
