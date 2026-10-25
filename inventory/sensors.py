import json
import uuid
from decimal import Decimal, InvalidOperation
from hmac import compare_digest

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import SensorReading, UserProfile


STALE_AFTER_SECONDS = 180


def _measurement(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Las mediciones deben ser números JSON.")
    try:
        number = Decimal(str(value))
        if not number.is_finite() or not low <= number <= high or number.as_tuple().exponent < -2:
            raise ValueError("Medición fuera de rango o con demasiados decimales.")
        return number
    except InvalidOperation as exc:
        raise ValueError("Medición inválida.") from exc


@csrf_exempt
@require_POST
def sensor_ingest(request):
    configured_token = settings.SENSOR_DEVICE_TOKEN
    supplied = request.headers.get("Authorization", "")
    try:
        authorized = bool(configured_token) and supplied.startswith("Bearer ") and compare_digest(
            supplied[7:].encode("ascii"), configured_token.encode("ascii")
        )
    except UnicodeEncodeError:
        authorized = False
    if not authorized:
        return JsonResponse({"error": "Token de dispositivo inválido."}, status=401)
    if request.content_type != "application/json" or len(request.body) > 1024:
        return JsonResponse({"error": "Se requiere JSON de hasta 1024 bytes."}, status=400)
    try:
        payload = json.loads(request.body)
        if not isinstance(payload, dict) or set(payload) != {"reading_id", "temperature_c", "humidity_percent", "sample_count"}:
            raise ValueError("Campos JSON incorrectos.")
        if not isinstance(payload["reading_id"], str):
            raise ValueError("reading_id debe ser un UUID.")
        reading_id = uuid.UUID(payload["reading_id"])
        temperature = _measurement(payload["temperature_c"], Decimal("0"), Decimal("50"))
        humidity = _measurement(payload["humidity_percent"], Decimal("20"), Decimal("90"))
        count = payload["sample_count"]
        if type(count) is not int or not 1 <= count <= 4:
            raise ValueError("sample_count debe estar entre 1 y 4.")
    except (ValueError, TypeError, KeyError, UnicodeDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    reading, created = SensorReading.objects.get_or_create(
        reading_id=reading_id,
        defaults={"temperature_c": temperature, "humidity_percent": humidity, "sample_count": count},
    )
    if (reading.temperature_c, reading.humidity_percent, reading.sample_count) != (temperature, humidity, count):
        return JsonResponse({"error": "reading_id ya existe con otros valores."}, status=409)
    return JsonResponse({"stored": created, "reading_id": str(reading_id)}, status=201 if created else 200)


@login_required
@require_GET
def sensor_latest(request):
    if not request.user.is_active or not UserProfile.objects.filter(user=request.user).exists():
        return JsonResponse({"error": "Cuenta sin perfil autorizado."}, status=403)
    reading = SensorReading.objects.first()
    response = {
        "status": "waiting" if reading is None else "stale" if (timezone.now() - reading.received_at).total_seconds() > STALE_AFTER_SECONDS else "online",
        "stale_after_seconds": STALE_AFTER_SECONDS,
        "server_time": timezone.now().isoformat(),
        "reading": None if reading is None else {
            "temperature_c": float(reading.temperature_c),
            "humidity_percent": float(reading.humidity_percent),
            "sample_count": reading.sample_count,
            "received_at": reading.received_at.isoformat(),
        },
    }
    result = JsonResponse(response)
    result["Cache-Control"] = "no-store"
    return result
