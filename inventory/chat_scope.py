"""General semantic boundary for the local inventory assistant."""

import json
import math
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# These describe areas of work, not individual user phrasings.
APP_AREAS = (
    "Productos y presentaciones del catálogo de inventario",
    "Cantidad disponible de un producto y existencias en la tienda",
    "Registrar movimientos de compra, venta y merma de productos",
    "Crear, editar o desactivar productos y presentaciones",
    "Ubicaciones y zonas de almacenamiento de productos",
    "Historial de movimientos de inventario",
    "Temperatura y humedad del sensor ESP32 de la tienda",
    "Alertas y umbrales de temperatura del almacén",
    "Guía de uso de formularios de ICChocolate",
)
OTHER_AREAS = (
    "Preguntas de geografía, ciudades, países y capitales",
    "Consultas de programación, código y tecnología general",
    "Preguntas de clima, pronósticos y tiempo meteorológico",
    "Recetas de cocina e información general sobre alimentos",
    "Preguntas sobre otros servicios, Gmail y cuentas externas",
    "Cálculos matemáticos y problemas de aritmética",
    "Deportes, partidos, fútbol y resultados",
    "Cine, películas y recomendaciones de entretenimiento",
    "Historia, ciencia, astronomía y conocimientos generales",
)
GUIDE_AREAS = {
    "remove": "Retirar unidades del inventario o desactivar un producto del catálogo",
    "alert": "Configurar alertas térmicas, cambiar el umbral de temperatura y destinatarios de correo",
    "sensor": "Registrar o configurar un dispositivo sensor ESP32 para temperatura y humedad",
    "movement": "Registrar un movimiento de compra, venta, traslado, consumo o merma",
    "product": "Crear o editar un producto del catálogo de chocolate",
    "presentation": "Crear o editar una presentación, envase o unidad de un producto",
    "location": "Crear o editar una ubicación o zona de almacenamiento",
    "conversion": "Convertir unidades de una presentación en otra mediante equivalencias",
    "photo": "Registrar movimientos usando una foto de boleta o etiqueta",
}


def _similarity(left, right):
    return sum(a * b for a, b in zip(left, right))


def _embed(inputs):
    if os.environ.get("OLLAMA_CHAT_ENABLED", "0") != "1":
        return None
    endpoint = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
    if endpoint not in ("http://host.docker.internal:11434", "http://127.0.0.1:11434"):
        return None
    payload = {"model": os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
               "input": inputs, "truncate": False, "keep_alive": "5m"}
    request = Request(endpoint + "/api/embed", data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=40) as response:
            vectors = json.load(response)["embeddings"]
        if len(vectors) != len(inputs) or not vectors or not vectors[0] or not all(isinstance(vector, list) and len(vector) == len(vectors[0])
                                                  and all(isinstance(value, (int, float)) and math.isfinite(value)
                                                          for value in vector) for vector in vectors):
            return None
        return vectors
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError, KeyError, IndexError):
        return None


def in_scope(question):
    """Return True/False from local semantic contrast, or None if unavailable."""
    vectors = _embed([*APP_AREAS, *OTHER_AREAS, question])
    if vectors is None:
        return None
    query = vectors[-1]
    app = max(_similarity(query, vector) for vector in vectors[:len(APP_AREAS)])
    other = max(_similarity(query, vector) for vector in vectors[len(APP_AREAS):-1])
    return app > other


def grounded_guide(question, suggested):
    """Check a model-selected guide against all guide descriptions."""
    if suggested not in GUIDE_AREAS:
        return None
    topics = list(GUIDE_AREAS)
    vectors = _embed([*GUIDE_AREAS.values(), question])
    if vectors is None:
        return None
    query = vectors[-1]
    scores = sorted(((_similarity(query, vector), topic)
                     for topic, vector in zip(topics, vectors[:-1])), reverse=True)
    best_score, best_topic = scores[0]
    selected_score = next(score for score, topic in scores if topic == suggested)
    if best_score - selected_score <= 0.12:
        return suggested
    if best_score >= 0.55 and best_score - scores[1][0] >= 0.05:
        return best_topic
    return None
