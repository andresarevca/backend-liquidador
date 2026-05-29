"""
core/ia_client.py
=================
Cliente HTTP para comunicarse con el microservicio ia-liquidador.

Usado por las vistas y tareas Celery del backend Django para:
  - Obtener los datos estructurados del pre-informe (POST /api/preinforme/generar)
  - (Futuro) Delegar el pipeline directamente al microservicio

Requiere: requests (pip install requests)
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 120  # segundos — el pipeline puede tardar con documentos grandes


def _get_base_url() -> str:
    return getattr(settings, "IA_LIQUIDADOR_URL", "http://ia:8001").rstrip("/")


def _get_headers() -> dict:
    key = getattr(settings, "IA_LIQUIDADOR_API_KEY", "")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-Api-Key"] = key
    return headers


def generar_preinforme(
    caso_id: str,
    paso_b: dict,
    paso_c: dict | None,
    metadatos: dict | None = None,
) -> dict:
    """
    Llama a POST /api/preinforme/generar del microservicio ia-liquidador.

    Returns:
        dict con los campos PreinformeData.
    Raises:
        RuntimeError si el servicio no responde o devuelve error.
    """
    url = f"{_get_base_url()}/api/preinforme/generar"
    payload = {
        "caso_id": caso_id,
        "paso_b": paso_b,
        "paso_c": paso_c,
        "metadatos": metadatos or {},
    }
    try:
        resp = requests.post(url, json=payload, headers=_get_headers(), timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError as e:
        logger.error("ia-liquidador no disponible: %s", e)
        raise RuntimeError(
            "El servicio ia-liquidador no está disponible. "
            "Verifique que el contenedor esté corriendo en IA_LIQUIDADOR_URL."
        ) from e
    except requests.exceptions.HTTPError as e:
        detalle = ""
        try:
            detalle = e.response.json().get("detail", "")
        except Exception:
            pass
        logger.error("Error HTTP desde ia-liquidador (%s): %s", e.response.status_code, detalle)
        raise RuntimeError(f"Error del servicio ia-liquidador: {detalle or str(e)}") from e


def health_check() -> dict:
    """Verifica que el microservicio ia-liquidador esté disponible."""
    url = f"{_get_base_url()}/api/pipeline/health"
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"estado": "error", "detalle": str(e)}
