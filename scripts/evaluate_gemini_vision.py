"""One-off, read-only vision benchmark. Requires GEMINI_API_KEY and a folder of demo JPGs.

Sends the same prepared images used for local OCR; does not save images, API output,
or inventory records. Run only with a confirmed Free Tier project.
"""

import base64
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inventory.photo_service import prepare_photo


MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-3.6-flash")
if MODEL not in {"gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"}:
    raise SystemExit("Modelo fuera de la lista gratuita validada para esta prueba.")
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
CODES = {"BARRA-100", "CAJA-BARRA-12", "POLVO-100", "POLVO-1000"}
RECEIPT = {"BARRA-100": 2, "CAJA-BARRA-12": 1, "POLVO-100": 3, "POLVO-1000": 1}
EXPECTED = {
    "1000128881": RECEIPT, "1000128880": RECEIPT,
    "1000128879": {"POLVO-100": None}, "1000128878": {"POLVO-100": None},
    "1000128877": {"POLVO-1000": None}, "1000128876": {"POLVO-1000": None},
    "1000128873": {"BARRA-100": None}, "1000128872": {"BARRA-100": None},
    "1000128875": {"CAJA-BARRA-12": None}, "1000128874": {"CAJA-BARRA-12": None},
}
PROMPT = """Analiza UNA fotografía de prueba de una boleta o una etiqueta de chocolate.
Catálogo permitido: BARRA-100 = barra individual de 100 g; CAJA-BARRA-12 = caja de 12 barras;
POLVO-100 = bolsa de polvo de 100 g; POLVO-1000 = saco de polvo de 1 kg.
Devuelve SOLO JSON con formato {"items":[{"codigo":"...","cantidad":null,"evidencia":"..."}]}.
Cada código debe ser uno de los cuatro del catálogo y debe poder leerse en la foto.
En boletas, cantidad es el número de unidades compradas junto al código en la columna CANT.
En etiquetas, cantidad es SIEMPRE null: el peso neto y el número de barras por caja NO son compras.
Si un código o su cantidad no son legibles, omítelo o deja cantidad null. No adivines.
Una boleta puede contener varios artículos. No uses precios ni totales como cantidades."""


class TemporaryAPIError(RuntimeError):
    pass


def call_api(key: str, jpeg: bytes) -> list[dict]:
    body = {
        "contents": [{"parts": [
            {"text": PROMPT},
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpeg).decode("ascii")}},
        ]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                             "maxOutputTokens": 4096, "thinkingConfig": {"thinkingLevel": "low"}},
    }
    request = Request(ENDPOINT, data=json.dumps(body).encode("utf-8"), headers={
        "Content-Type": "application/json", "X-goog-api-key": key,
    }, method="POST")
    try:
        with urlopen(request, timeout=45) as response:
            payload = json.load(response)
    except HTTPError as exc:
        try:
            detail = json.load(exc).get("error", {}).get("message", "")
        except (ValueError, OSError):
            detail = ""
        detail = detail.replace(key, "[REDACTED]")[:300]
        if exc.code == 503:
            raise TemporaryAPIError(f"HTTP 503: {detail}") from None
        raise RuntimeError(f"La API respondió HTTP {exc.code}: {detail}; se detiene la prueba sin reintentar.") from None
    except URLError as exc:
        raise RuntimeError("No se pudo conectar a la API; se detiene la prueba.") from exc
    try:
        text = "".join(part.get("text", "") for part in payload["candidates"][0]["content"]["parts"])
        items = json.loads(text)["items"]
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise TypeError("items debe ser una lista de objetos")
        return items
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("La API no devolvió la estructura esperada; se detiene la prueba.") from exc


def score(items: list[dict], expected: dict) -> dict:
    found = {}
    extras = []
    for item in items:
        code = str(item.get("codigo", "")).upper().strip()
        if code not in CODES or code in found:
            extras.append(code)
            continue
        quantity = item.get("cantidad")
        found[code] = quantity if type(quantity) is int and quantity > 0 else None
    return {
        "codes_correct": len(set(found) & set(expected)),
        "codes_expected": len(expected),
        "receipt_quantities_correct": sum(found.get(code) == qty and code in found for code, qty in expected.items() if qty is not None),
        "receipt_quantities_expected": sum(qty is not None for qty in expected.values()),
        "label_quantity_violations": sum(found.get(code) is not None for code, qty in expected.items() if qty is None),
        "false_codes": sorted(set(found) - set(expected)) + extras,
        "found": found,
    }


def main(folder: Path):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise SystemExit("Falta GEMINI_API_KEY en la configuración privada.")
    files = [(p, EXPECTED[p.stem.split("-")[-1]]) for p in sorted(folder.rglob("*.jpg"))
             if p.stem.split("-")[-1] in EXPECTED]
    if len(files) != 10:
        raise SystemExit(f"Se esperaban 10 fotos de evaluación; encontradas: {len(files)}")
    output = Path("/app/materials/fase5_pruebas") / f"vision_{MODEL}_results.jsonl"
    prior = {}
    if output.exists():
        for line in output.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            prior[record["photo"]] = record
    totals = {"codes_correct": 0, "codes_expected": 0, "receipt_quantities_correct": 0,
              "receipt_quantities_expected": 0, "label_quantity_violations": 0, "false_codes": 0}
    for index, (path, expected) in enumerate(files):
        if path.name in prior:
            record = prior[path.name]
            result = record["result"]
        else:
            with path.open("rb") as source:
                photo = prepare_photo(source)
            for attempt in range(3):
                try:
                    items = call_api(key, photo.jpeg)
                    break
                except TemporaryAPIError:
                    if attempt == 2:
                        raise
                    time.sleep(10 * (attempt + 1))
            result = score(items, expected)
            record = {"model": MODEL, "photo": path.name, "expected": expected, "result": result}
            with output.open("a", encoding="utf-8") as target:
                target.write(json.dumps(record, ensure_ascii=False) + "\n")
        for name in totals:
            totals[name] += len(result[name]) if name == "false_codes" else result[name]
        print(json.dumps({"photo": path.name, "expected": expected, **result,
                          "cached": path.name in prior}, ensure_ascii=False), flush=True)
        if index < len(files) - 1 and path.name not in prior:
            time.sleep(6)  # Fixed spacing; HTTP 429 stops rather than triggering paid fallbacks.
    print(json.dumps({"model": MODEL, "summary": totals}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
