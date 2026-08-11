# wearables-hub

Hub central que lee datos de dispositivos/marcas (Garmin, Polar, Huawei,
Coros...) y los reparte a las apps de Carlos (triatlon-atleta, GymCoach
Pro, y las que vengan) — sin que ninguna app tenga que saber de qué marca
vienen los datos.

## Arquitectura

```
connectors/
  garmin/sync.py   ← ACTIVO. Login Garmin, lee wellness + actividades.
  polar/authorize.py ← ACTIVO (manual). OAuth2, se ejecuta una vez por atleta.
  polar/sync.py    ← ACTIVO. Cron diario, usa el modelo de transacciones de Polar.
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

**Garmin:**
- `GARMIN_EMAIL`
- `GARMIN_PASSWORD`

**Polar** (por app, una sola vez):
- `POLAR_CLIENT_ID`
- `POLAR_CLIENT_SECRET`

**Polar** (por atleta vinculado — ver `connectors/polar/authorize.py`):
- `POLAR_ACCESS_TOKEN_<ATLETA>` ej. `POLAR_ACCESS_TOKEN_CGR`
- `POLAR_USER_ID_<ATLETA>` ej. `POLAR_USER_ID_CGR`

Y la variable (no secret) `POLAR_ATLETAS` con la lista separada por comas
de claves de atleta a sincronizar, ej. `CGR,nacho` (Settings → Secrets
and variables → Actions → pestaña **Variables**).

Cada atleta nuevo en Polar implica: 1) añadir sus dos secrets
`POLAR_ACCESS_TOKEN_X` / `POLAR_USER_ID_X`, 2) añadir su clave a
`POLAR_ATLETAS`, 3) añadir una línea `POLAR_ACCESS_TOKEN_X` /
`POLAR_USER_ID_X` en `.github/workflows/polar-sync.yml` (GitHub Actions
no permite nombres de secret dinámicos, así que hay que declararlos
explícitamente).

(Huawei/Coros usarán tokens OAuth2 por atleta cuando se implementen —
ver cada conector.)

## Atletas vinculados actualmente

| Atleta | Garmin | triatlon-atleta | GymCoach Pro |
|---|---|---|---|
| Carlos (CGR) | ✅ | ✅ (todo tipo de actividad) | ✅ (solo running) |

Este repo sustituye al script de Garmin que antes vivía dentro de
`triatlon-atleta` (`scripts/garmin_sync.py`) — **ese workflow debe
desactivarse/eliminarse** para no duplicar el sync.
