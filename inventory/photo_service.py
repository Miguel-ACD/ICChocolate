"""Image preparation for phase 5; never changes inventory."""

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_INPUT_PIXELS = 20_000_000
MAX_SIDE = 1600


class PhotoError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedPhoto:
    jpeg: bytes
    sha256: str
    width: int
    height: int


def prepare_photo(upload) -> PreparedPhoto:
    """Validate and normalize JPEG/PNG uploads without retaining EXIF metadata."""
    chunks = []
    size = 0
    for chunk in upload.chunks() if hasattr(upload, "chunks") else iter(lambda: upload.read(65536), b""):
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise PhotoError("La foto supera 5 MB.")
        chunks.append(chunk)
    if not size:
        raise PhotoError("La foto está vacía.")
    raw = b"".join(chunks)
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in {"JPEG", "PNG"}:
                raise PhotoError("Solo se admiten fotos JPEG o PNG.")
            if image.width * image.height > MAX_INPUT_PIXELS:
                raise PhotoError("La foto supera 20 megapíxeles.")
            image.load()
            normalized = ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        if isinstance(exc, PhotoError):
            raise
        raise PhotoError("La imagen no se puede leer.") from exc
    normalized.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    output = BytesIO()
    normalized.save(output, "JPEG", quality=85, optimize=True)
    jpeg = output.getvalue()
    return PreparedPhoto(jpeg=jpeg, sha256=sha256(jpeg).hexdigest(), width=normalized.width, height=normalized.height)
