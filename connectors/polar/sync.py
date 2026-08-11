#!/usr/bin/env python3
"""
Conector de Polar — PENDIENTE de implementar.

Polar usa el "Polar Accesslink" API (OAuth2 + webhooks o polling), distinto
al de Garmin. Pasos para activarlo cuando toque:

  1. Registrar una app en https://admin.polaraccesslink.com/ (requiere
     cuenta de desarrollador Polar).
  2. Cada atleta debe autorizar la app (flujo OAuth2), esto da un
     access_token + user_id por atleta — no hay login email/password
     como en Garmin.
  3. Guardar esos tokens como Secrets (uno por atleta, ej.
     POLAR_TOKEN_CGR, POLAR_TOKEN_NACHO...).
  4. Traducir la respuesta de Accesslink al esquema común de
     core/schema.py (mismo patrón que connectors/garmin/sync.py):
     atleta_key, fecha, tipo, dur_min, dist_km, fc_avg, fc_max, fuente.
  5. Llamar a enviar_actividad_a_destinos(actividad) por cada actividad.

No añadir credenciales reales a este archivo — solo vía variables de
entorno / GitHub Secrets, igual que con Garmin.
"""

raise NotImplementedError("Conector de Polar aún no implementado.")
