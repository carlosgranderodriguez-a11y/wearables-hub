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

**Garmin** (por atleta vinculado, mismo patrón que Polar):
- `GARMIN_EMAIL_<ATLETA>` ej. `GARMIN_EMAIL_CGR`, `GARMIN_EMAIL_NACHO`
- `GARMIN_PASSWORD_<ATLETA>` ej. `GARMIN_PASSWORD_CGR`, `GARMIN_PASSWORD_NACHO`
- Opcionales, admiten también sufijo `_<ATLETA>` (si no existe esa
  variante, se usa la versión sin sufijo como valor por defecto):
  `GARMIN_FC_UMBRAL`, `GARMIN_FC_MAX`

Y la variable `GARMIN_ATLETAS` con la lista separada por comas de
atletas a sincronizar en el cron diario, ej. `CGR,nacho`.

Cada atleta nuevo en Garmin implica: 1) sus dos secrets
`GARMIN_EMAIL_X` / `GARMIN_PASSWORD_X` — el conector self-service (ver
"Conectar un atleta nuevo" más abajo) ya los escribe él solo, sin que
nadie los vea en texto plano — 2) su clave se añade sola a
`GARMIN_ATLETAS` cuando se conecta, y 3) una línea
`GARMIN_EMAIL_X` / `GARMIN_PASSWORD_X` en `.github/workflows/garmin-sync.yml`
(paso manual, una sola vez por atleta — GitHub Actions no permite
nombres de secret dinámicos).

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

## Conectar un atleta nuevo (Garmin/Huawei/Coros) sin que nadie vea su contraseña

Para marcas de email+contraseña (Garmin, y Huawei/Coros cuando se
implementen), hay un relay independiente (`relay-conector/` — proyecto
Apps Script aparte, no confundir con el de la Sheet de triatlon-atleta)
que recibe el email/contraseña del atleta desde una página web sencilla
y los escribe directamente como GitHub Secrets cifrados con la clave
pública del repo (`crypto_box_seal`, igual que hace `gh secret set` o la
propia web de GitHub). Una vez escritos, los Secrets de GitHub son de
solo escritura — ni el dueño del repo puede volver a leerlos por la UI
ni por la API — así que el entrenador nunca ve, guarda ni gestiona esa
contraseña en ningún momento.

Flujo:
1. El entrenador genera un enlace de un solo uso para ese atleta y esa
   marca (`createInviteLink_('nacho', 'garmin')` desde el editor de
   Apps Script del relay) y se lo manda.
2. El atleta abre el enlace, mete su email/contraseña, pulsa conectar.
3. El relay cifra y escribe `GARMIN_EMAIL_<ATLETA>` /
   `GARMIN_PASSWORD_<ATLETA>` en este repo, y añade su clave a
   `GARMIN_ATLETAS` si no estaba ya.
4. Queda un único paso manual (ver arriba): añadir esa línea de secret
   en `garmin-sync.yml` la primera vez que ese atleta se conecta.

Añadir Huawei/Coros a este mismo relay es solo añadir su entrada al
`BRAND_CONFIG` del relay (`secretNames`, `athleteListVar`) — no hace
falta tocar la parte de cifrado ni el flujo de invitación.

## Atletas vinculados actualmente

| Atleta | Garmin | triatlon-atleta | GymCoach Pro |
|---|---|---|---|
| Carlos (CGR) | ✅ | ✅ (todo tipo de actividad) | ✅ (solo running) |

Este repo sustituye al script de Garmin que antes vivía dentro de
`triatlon-atleta` (`scripts/garmin_sync.py`) — **ese workflow debe
desactivarse/eliminarse** para no duplicar el sync.
