# relay-conector

Apps Script Web App independiente (proyecto propio, **no** el de la Sheet
de triatlon-atleta) cuyo único trabajo es recibir el email/contraseña de
un atleta desde una página web sencilla, cifrarlos con la clave pública
de GitHub Secrets de este repo, y escribirlos directamente ahí — sin
que el entrenador los vea, los guarde ni pueda volver a leerlos.

Ver la sección "Conectar un atleta nuevo" en el `README.md` de la raíz
del repo para el flujo completo. Esto de aquí son solo los pasos de
despliegue.

## Archivos

- `VendoredCrypto.gs` — tweetnacl.js + blakejs adaptados para Apps
  Script (que no tiene Web Crypto API ni CSPRNG nativo), implementando
  `crypto_box_seal` de libsodium — el mismo cifrado que usa `gh secret
  set` o la propia web de GitHub para escribir secrets. Incluye un
  autotest determinista (`testSealedBoxDeterministic_`) verificado
  contra una implementación real de libsodium (PyNaCl) antes de subir
  este código — **ejecútalo tú también la primera vez** para confirmar
  que Apps Script lo reproduce byte a byte (ver "Primer despliegue"
  más abajo).
- `Relay.gs` — configuración de marcas (`BRAND_CONFIG`), enlaces de
  invitación de un solo uso, y las llamadas a la API de GitHub
  (`doGet`/`submitConnect`).
- `connect.html` — la página que ve el atleta.

## Primer despliegue

1. Ve a [script.google.com](https://script.google.com) → Nuevo proyecto.
2. Bórrale el `Code.gs` que trae por defecto. Crea tres archivos con
   estos nombres exactos y pega el contenido de cada uno:
   - `VendoredCrypto.gs`
   - `Relay.gs`
   - `connect` (tipo **HTML**, no script — al crearlo Apps Script ya le
     pone la extensión `.html`) — pega el contenido de `connect.html`
3. **Verifica el cifrado antes de seguir**: en el desplegable de
   funciones (arriba, junto a "Depurar") elige
   `testSealedBoxDeterministic_` y pulsa ▶ Ejecutar. Mira el log
   (Ver → Registros): debe decir `✅ MATCH`. Si dice `❌ MISMATCH`, no
   sigas — algo se copió mal, vuelve a pegar los archivos.
4. Project Settings (el engranaje) → Script properties → añade:
   - `GITHUB_PAT` = un token de acceso fino (fine-grained PAT) para
     **este repo** (`wearables-hub`) con permisos: **Secrets: Read and
     write**, **Variables: Read and write**, **Actions: Read-only**.
   - `GITHUB_OWNER` = `carlosgranderodriguez-a11y`
   - `GITHUB_REPO` = `wearables-hub`
5. Desplegar → Nueva implementación → tipo **Aplicación web**.
   - Ejecutar como: **Yo**
   - Quién tiene acceso: **Cualquier usuario**
   - Copia la URL que te da — es la URL base del relay, pero **no se la
     mandes a nadie directamente**: los enlaces que se mandan a los
     atletas llevan además su token de invitación (paso siguiente).
6. Para invitar a un atleta: en el editor, pega esto en cualquier
   función temporal (o usa el propio editor de funciones) y ejecútalo:
   ```js
   createInviteLink_('nacho', 'garmin')
   ```
   El resultado (visible en Ver → Registros) es el enlace exacto que
   le mandas a Nacho. Es de un solo uso: en cuanto lo envía, deja de
   funcionar.

## Migrar las credenciales de Carlos (CGR) al nuevo esquema

Los secrets actuales de Garmin (`GARMIN_EMAIL` / `GARMIN_PASSWORD`, en
el Environment "CGR") no se pueden leer para copiarlos automáticamente
— son de solo escritura, por diseño. La forma más simple de migrar sin
que ni tú mismo tengas que volver a teclear tu contraseña en la web de
GitHub es usar este mismo relay contigo:

```js
createInviteLink_('CGR', 'garmin')
```

Abre el enlace que te da y mete tus propias credenciales de Garmin —
quedan escritas como `GARMIN_EMAIL_CGR` / `GARMIN_PASSWORD_CGR` (los
nombres nuevos que ya espera `garmin-sync.yml`). Después, desde
Settings → Secrets and variables → Actions, borra los antiguos
`GARMIN_EMAIL` / `GARMIN_PASSWORD` del Environment "CGR" (ya no los usa
nadie) y crea la variable `GARMIN_ATLETAS` con valor `CGR` (Settings →
Secrets and variables → Actions → pestaña Variables).

## Antes de que un atleta real use esto

Prueba el flujo completo con un email/contraseña falsos:
`createInviteLink_('test', 'garmin')` → abre el enlace → mete
cualquier cosa → confirma en GitHub (Settings → Secrets and variables
→ Actions) que aparecen `GARMIN_EMAIL_TEST` / `GARMIN_PASSWORD_TEST` y
que `GARMIN_ATLETAS` incluye `test` → borra ambos secrets y quita
`test` de la variable antes de dejarlo en producción.
