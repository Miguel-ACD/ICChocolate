"""Manual, read-only benchmark: python scripts/evaluate_phase5_photos.py /photos."""

import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inventory.local_ocr import propose_catalog_codes
from inventory.photo_service import prepare_photo


CODES = {"BARRA-100", "CAJA-BARRA-12", "POLVO-100", "POLVO-1000"}
EXPECTED = {
    "1000128881": CODES, "1000128880": CODES,
    "1000128879": {"POLVO-100"}, "1000128878": {"POLVO-100"},
    "1000128877": {"POLVO-1000"}, "1000128876": {"POLVO-1000"},
    "1000128873": {"BARRA-100"}, "1000128872": {"BARRA-100"},
    "1000128875": {"CAJA-BARRA-12"}, "1000128874": {"CAJA-BARRA-12"},
}


def variants(photo):
    with Image.open(BytesIO(photo.jpeg)) as image:
        for angle in (0, 90, 270):
            oriented = image.rotate(angle, expand=True)
            gray = ImageOps.autocontrast(ImageOps.grayscale(oriented))
            for mode, prepared in (("original", oriented), ("contrast", gray.resize((gray.width * 2, gray.height * 2))),
                                   ("threshold", gray.point(lambda p: 255 if p > 150 else 0).resize((gray.width * 2, gray.height * 2)))):
                output = BytesIO()
                prepared.save(output, "PNG")
                yield angle, mode, output.getvalue()


def ocr(data, psm):
    result = subprocess.run(["tesseract", "stdin", "stdout", "-l", "spa+eng", "--psm", str(psm)],
                            input=data, capture_output=True, timeout=25)
    return result.stdout.decode("utf-8", errors="replace")


def main(folder):
    total = correct = 0
    for path in sorted(Path(folder).rglob("*.jpg")):
        stem = path.stem.split("-")[-1]
        if stem not in EXPECTED:
            continue
        with path.open("rb") as source:
            photo = prepare_photo(source)
        best = (0, "original", 6, [], "")
        for angle, mode, candidate in variants(photo):
            for psm in (6, 11):
                text = ocr(candidate, psm)
                proposals = propose_catalog_codes(text, CODES)
                if len(proposals) > len(best[3]):
                    best = (angle, mode, psm, proposals, text)
        found = {item["code"] for item in best[3]}
        total += len(EXPECTED[stem])
        correct += len(found & EXPECTED[stem])
        print(json.dumps({"file": path.name, "rotation": best[0], "preprocess": best[1], "psm": best[2],
                          "expected": sorted(EXPECTED[stem]), "found": sorted(found), "quantities": best[3],
                          "text_excerpt": best[4][:400]}, ensure_ascii=False), flush=True)
    print(f"Exact catalog code recall: {correct}/{total}")


if __name__ == "__main__":
    main(sys.argv[1])
