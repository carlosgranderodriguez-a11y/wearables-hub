#!/usr/bin/env python3
"""
Conector de Huawei (Huawei Health Kit) — PENDIENTE de implementar.

Huawei Health Kit requiere:
  1. Registrar una app en Huawei Developer Console (AppGallery Connect) y
     habilitar "Health Kit".
  2. Cada atleta autoriza vía OAuth2 (similar a Polar) — no hay
     login email/password directo.
  3. La API de Huawei está pensada sobre todo para apps móviles nativas
     (Android); el acceso server-to-server es más limitado que Garmin o
     Polar — puede requerir que el propio atleta exporte datos desde
     la app Huawei Health, o un intermediario.
  4. Traducir la respuesta al esquema común de core/schema.py (mismo
     patrón que connectors/garmin/sync.py).
  5. Llamar a enviar_actividad_a_destinos(actividad) por cada actividad.

No añadir credenciales reales a este archivo — solo vía variables de
entorno / GitHub Secrets.
"""

raise NotImplementedError("Conector de Huawei aún no implementado.")
