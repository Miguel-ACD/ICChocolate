"""Local text recognition and conservative catalog proposals for phase 5."""

import re
import subprocess

from .photo_service import PreparedPhoto


class OCRError(RuntimeError):
    pass


def recognize(photo: PreparedPhoto) -> str:
    try:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "spa+eng", "--psm", "6"],
            input=photo.jpeg, capture_output=True, check=False, timeout=25,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise OCRError("El reconocimiento local no está disponible.") from exc
    if result.returncode:
        raise OCRError("No se pudo reconocer el texto de la foto.")
    return result.stdout.decode("utf-8", errors="replace")


def propose_catalog_codes(text: str, known_codes: set[str]) -> list[dict]:
    """Only exact catalog codes; a label never supplies a purchase quantity."""
    lines = []
    seen = set()
    for line in text.upper().splitlines():
        for code in known_codes:
            if code in seen or not re.search(r"(?<![A-Z0-9-])" + re.escape(code.upper()) + r"(?![A-Z0-9-])", line):
                continue
            match = re.search(r"^\s*(\d{1,3})\s+" + re.escape(code.upper()) + r"(?![A-Z0-9-])", line)
            quantity = int(match.group(1)) if match and int(match.group(1)) > 0 else None
            lines.append({"code": code, "quantity": quantity})
            seen.add(code)
    return lines
