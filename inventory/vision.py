"""Gemini proposals for human review. This module never changes inventory."""

import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.utils import timezone

from .models import PhotoDocument, Presentation


class VisionUnavailable(RuntimeError):
    pass


MODEL = "gemini-3.6-flash"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


def normalize_items(items, kind, codes):
    if not isinstance(items, list) or len(items) > 40:
        raise VisionUnavailable("La respuesta de IA no tiene una lista válida.")
    result = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise VisionUnavailable("La respuesta de IA contiene un renglón inválido.")
        code = str(item.get("codigo", "")).strip().upper()[:40]
        if not code or code in seen:
            continue
        seen.add(code)
        quantity = item.get("cantidad")
        if kind == PhotoDocument.Kind.LABEL or type(quantity) is not int or not 0 < quantity <= 9_000_000_000_000_000_000:
            quantity = None
        result.append({
            "code": code,
            "presentation_id": codes.get(code),
            "quantity": quantity,
            "evidence": str(item.get("evidencia", ""))[:160],
        })
    return result


def extract_document(document):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise VisionUnavailable("Gemini no está configurado; completa los renglones manualmente.")
    codes = dict(Presentation.objects.filter(active=True, product__active=True)
                 .values_list("code", "id"))
    codes = {code.upper(): pk for code, pk in codes.items()}
    if len(codes) > 200:
        raise VisionUnavailable("El catálogo supera el límite de esta función de IA.")
    prompt = (
        "Analiza esta foto de chocolate como boleta o etiqueta. Catálogo permitido: "
        + ", ".join(sorted(codes))
        + '. Devuelve SOLO JSON {"items":[{"codigo":"...","cantidad":null,"evidencia":"..."}]}. '
        "Copia únicamente códigos visibles; omite los ilegibles y no adivines. "
        "En boletas, cantidad es la cifra de unidades del renglón junto al código; puede haber varios renglones. "
        "En etiquetas, cantidad SIEMPRE es null: peso, contenido de caja y lote no son compra ni venta. "
        "Si no se lee la cantidad, usa null. No uses precio ni total como cantidad."
    )
    with document.image.open("rb") as image:
        jpeg = image.read()
    body = {"contents": [{"parts": [
        {"text": prompt},
        {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpeg).decode("ascii")}},
    ]}], "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                            "maxOutputTokens": 4096, "thinkingConfig": {"thinkingLevel": "low"}}}
    request = Request(ENDPOINT, data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json", "X-goog-api-key": key})
    try:
        with urlopen(request, timeout=45) as response:
            payload = json.load(response)
        content = "".join(part.get("text", "") for part in payload["candidates"][0]["content"]["parts"])
        items = normalize_items(json.loads(content)["items"], document.kind, codes)
    except HTTPError as exc:
        if exc.code == 429:
            raise VisionUnavailable("Se alcanzó la cuota gratuita de Gemini; ingresa los renglones manualmente.") from None
        raise VisionUnavailable(f"Gemini respondió HTTP {exc.code}; ingresa los renglones manualmente.") from None
    except (URLError, TimeoutError):
        raise VisionUnavailable("No se pudo conectar con Gemini; ingresa los renglones manualmente.") from None
    except (KeyError, IndexError, ValueError, TypeError):
        raise VisionUnavailable("Gemini devolvió una respuesta inválida; ingresa los renglones manualmente.") from None
    document.extraction_status = "LISTO"
    document.extraction_provider = MODEL
    document.extraction_items = items
    document.extraction_error = ""
    document.extracted_at = timezone.now()
    document.save(update_fields=["extraction_status", "extraction_provider", "extraction_items",
                                 "extraction_error", "extracted_at"])
    return items
