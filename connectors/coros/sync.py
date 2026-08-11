#!/usr/bin/env python3
"""
Conector de Coros — PENDIENTE de implementar.

Coros tiene una API oficial para partners ("Coros Open API"), de acceso
más restringido que Garmin (normalmente requiere solicitud y aprobación
como partner, no solo registro libre). Pasos:

  1. Solicitar acceso a la API de partners de Coros
     (https://open.coros.com/ o contacto directo con Coros).
  2. Flujo de autorización OAuth2 por atleta, como Polar/Huawei.
  3. Traducir la respuesta al esquema común de core/schema.py (mismo
     patrón que connectors/garmin/sync.py).
  4. Llamar a enviar_actividad_a_destinos(actividad) por cada actividad.

No añadir credenciales reales a este archivo — solo vía variables de
entorno / GitHub Secrets.
"""

raise NotImplementedError("Conector de Coros aún no implementado.")
