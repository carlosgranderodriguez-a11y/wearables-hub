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
    tipo: str          # categoría interna: 'running' | 'cycling' | 'swimming' | 'strength' | 'padel' | 'tenis' | 'rowing' | 'futbol' | 'trail' | 'walking' | 'other'
    etiqueta: str = ""  # nombre legible en ES para mostrar como "disciplina" (ver CATALOGO_DEPORTES)
    dur_min: float = 0
    dist_km: float = 0
    fc_avg: Optional[int] = None
    fc_max: Optional[int] = None
    fuente: str = ""
    # ── Métricas ampliadas (pueden faltar según el reloj/actividad) ──
    zonas: Optional[list] = None      # [{'z':1,'min':5.2}, ...] tiempo en cada zona de FC
    tss: Optional[float] = None       # hrTSS calculado desde FC media y umbral
    foster: Optional[float] = None    # carga Foster (RPE × minutos)
    rpe: Optional[float] = None       # RPE usado para Foster (estimado si no lo da el reloj)
    desnivel_m: Optional[float] = None
    ritmo_medio: Optional[str] = None  # 'mm:ss' por km
    cadencia: Optional[float] = None

    def to_dict(self):
        return {
            "atleta_key": self.atleta_key,
            "fecha": self.fecha,
            "tipo": self.tipo,
            "etiqueta": self.etiqueta,
            "dur_min": self.dur_min,
            "dist_km": self.dist_km,
            "fc_avg": self.fc_avg,
            "fc_max": self.fc_max,
            "fuente": self.fuente,
            "zonas": self.zonas,
            "tss": self.tss,
            "foster": self.foster,
            "rpe": self.rpe,
            "desnivel_m": self.desnivel_m,
            "ritmo_medio": self.ritmo_medio,
            "cadencia": self.cadencia,
        }


# Colores por zona de FC, compartidos entre apps para que las gráficas
# sean coherentes (Z1 gris-azul suave → Z5 rojo).
ZONA_COLORES = {
    1: "#60a5fa",  # azul  - recuperación
    2: "#4ade80",  # verde - aeróbico ligero
    3: "#fbbf24",  # ámbar - aeróbico medio
    4: "#fb923c",  # naranja - umbral
    5: "#ef4444",  # rojo  - VO2máx / anaeróbico
}
ZONA_NOMBRES = {
    1: "Z1 · Recuperación",
    2: "Z2 · Aeróbico",
    3: "Z3 · Tempo",
    4: "Z4 · Umbral",
    5: "Z5 · VO2máx",
}


# Tipos de actividad "crudos" (tal cual los da cada marca) que consideramos
# running. Se mantiene por compatibilidad; el reconocimiento real ahora
# usa coincidencia de texto (ver CATALOGO_DEPORTES más abajo).
GARMIN_RUNNING_KEYS = {
    "running", "trail_running", "treadmill_running",
    "track_running", "indoor_running", "street_running",
}

# Catálogo de deportes reconocidos, en orden de prioridad (el primero que
# coincida por substring en el typeKey de la marca gana). Cada entrada:
#   (categoria interna, [substrings a buscar en el typeKey], etiqueta en ES)
#
# La "categoria interna" es la que usan destinations.py y cargas.py para
# decidir cálculos y enrutado. La "etiqueta en ES" es la que ve Carlos en
# GymCoach Pro como "disciplina" — coincide con DISC_ICONS de index.html
# donde ya existe una entrada equivalente, para que salga con su icono.
#
# Para reconocer un deporte nuevo (ej. pádel, pickleball...) basta con
# añadir una línea aquí: no hace falta tocar los conectores.
CATALOGO_DEPORTES = [
    ("running",  ["run"],                                   "Carrera"),
    ("cycling",  ["cycling", "biking", "bike", "mtb"],       "Ciclismo ruta"),
    ("swimming", ["swim"],                                   "Natación"),
    ("strength", ["strength", "fitness_equipment"],          "Fuerza"),
    ("padel",    ["padel", "paddle_tennis"],                 "Pádel"),
    ("tenis",    ["tennis"],                                 "Tenis"),
    ("rowing",   ["rowing"],                                 "Remo"),
    ("futbol",   ["soccer", "football"],                     "Fútbol"),
    ("trail",    ["hiking", "mountaineering"],                "Trail"),
    ("walking",  ["walking"],                                "Caminata"),
]


def clasificar_actividad(type_key):
    """
    Clasifica el typeKey crudo de una marca contra CATALOGO_DEPORTES.
    Devuelve (categoria_interna, etiqueta_en_es). Si no reconoce nada,
    devuelve ("other", etiqueta_legible_generada_del_typeKey) — nunca
    se pierde silenciosamente, aunque no esté en el catálogo.
    """
    tk = (type_key or "").lower()
    for categoria, patrones, etiqueta in CATALOGO_DEPORTES:
        if any(p in tk for p in patrones):
            return categoria, etiqueta
    generica = (type_key or "Actividad").replace("_", " ").strip().title() or "Actividad"
    return "other", generica
