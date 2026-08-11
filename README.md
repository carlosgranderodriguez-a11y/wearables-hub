# wearables-hub

Hub central que lee datos de dispositivos/marcas (Garmin, Polar, Huawei,
Coros...) y los reparte a las apps de Carlos (triatlon-atleta, GymCoach
Pro, y las que vengan) — sin que ninguna app tenga que saber de qué marca
vienen los datos.

## Arquitectura

```
connectors/
  garmin/sync.py   ← ACTIVO. Login Garmin, lee wellness + actividades.
  polar/sync.py    ← stub, pendiente de credenciales/API
  huawei/sync.py   ← stub, pendiente de credenciales/API
  coros/sync.py    ← stub, pendiente de credenciales/API

core/
  schema.py        ← formato común de "actividad normalizada"
  destinations.py  ← qué apps reciben qué datos, y con qué nombre de atleta
```

Cada conector de marca:
1. Se autentica con la API de esa marca.
2. Traduce sus datos al esquema común (`core/schema.py`).
3. Llama a `enviar_actividad_a_destinos(...)` de `core/destinations.py`,
   que decide a qué apps mandar cada actividad según su tipo y si el
   atleta está vinculado a esa app.

## Añadir una app destino nueva

Edita `core/destinations.py`:
1. Añade un diccionario nuevo (URL del Apps Script, qué tipos de
   actividad acepta, mapeo `atleta_key → nombre exacto en esa app`).
2. Añádelo a la lista `DESTINOS`.
3. Si el formato del payload que espera esa app es distinto, añade un
   caso en `_payload_para_destino(...)`.

No hace falta tocar los conectores de marca.

## Añadir una marca nueva (Polar, Huawei, Coros...)

1. Completa el conector correspondiente en `connectors/<marca>/sync.py`
   (cada uno trae ya las instrucciones y pasos necesarios).
2. Añade sus Secrets en GitHub (Settings → Secrets and variables →
   Actions).
3. Copia `.github/workflows/garmin-sync.yml` como plantilla para un
   nuevo workflow `<marca>-sync.yml`.

## Secrets necesarios (GitHub Actions)

- `GARMIN_EMAIL`
- `GARMIN_PASSWORD`

(Polar/Huawei/Coros usarán tokens OAuth2 por atleta cuando se
implementen — ver cada conector.)

## Atletas vinculados actualmente

| Atleta | Garmin | triatlon-atleta | GymCoach Pro |
|---|---|---|---|
| Carlos (CGR) | ✅ | ✅ (todo tipo de actividad) | ✅ (solo running) |

Este repo sustituye al script de Garmin que antes vivía dentro de
`triatlon-atleta` (`scripts/garmin_sync.py`) — **ese workflow debe
desactivarse/eliminarse** para no duplicar el sync.
