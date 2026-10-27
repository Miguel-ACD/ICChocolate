"""Authenticated ESP32 cycles and read-only monitoring for web users."""
import json
import uuid
from datetime import timedelta, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from .device_service import authenticate_device, store_cycle
from .models import SensorAssignment, SensorDevice, SensorReading, UserProfile
from .services import InventoryError

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


def _authorized_user(request):
    return request.user.is_active and UserProfile.objects.filter(user=request.user).exists()


def _device_response(request, parser, legacy=False):
    device = authenticate_device(request.headers.get("Authorization", ""))
    if device is None:
        return JsonResponse({"error": "Dispositivo no autorizado."}, status=401)
    if request.content_type != "application/json":
        return JsonResponse({"error": "Se requiere JSON."}, status=400 if legacy else 415)
    if len(request.body) > 1024:
        return JsonResponse({"error": "La solicitud supera 1024 bytes."}, status=400 if legacy else 413)
    try:
        payload = json.loads(request.body)
        values = parser(payload)
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400 if legacy else 422)
    try:
        reading, created = store_cycle(device=device, **values)
    except SensorDevice.DoesNotExist:
        return JsonResponse({"error": "Dispositivo no autorizado."}, status=401)
    except InventoryError as exc:
        return JsonResponse({"error": str(exc)}, status=409 if "ya existe" in str(exc) else 422)
    if legacy:
        return JsonResponse({"stored": created, "reading_id": str(reading.reading_id)}, status=201 if created else 200)
    return JsonResponse({"medicion_id": reading.pk, "duplicado": not created,
                         "recibido_en": reading.received_at.isoformat()}, status=201 if created else 200)


def _legacy_payload(payload):
    if not isinstance(payload, dict) or set(payload) != {"reading_id", "temperature_c", "humidity_percent", "sample_count"}:
        raise ValueError("Campos JSON incorrectos.")
    if not isinstance(payload["reading_id"], str):
        raise ValueError("reading_id debe ser un UUID.")
    try:
        cycle_id = uuid.UUID(payload["reading_id"])
    except ValueError:
        raise ValueError("reading_id debe ser un UUID.") from None
    temp = _measurement(payload["temperature_c"], Decimal("0"), Decimal("50"))
    humidity = _measurement(payload["humidity_percent"], Decimal("20"), Decimal("90"))
    count = payload["sample_count"]
    if type(count) is not int or not 1 <= count <= 4:
        raise ValueError("sample_count debe estar entre 1 y 4.")
    if count < 4:
        return dict(cycle_id=cycle_id, status=SensorReading.Status.INVALID, sample_count=count,
                    error_code="INCOMPLETE_LEGACY")
    return dict(cycle_id=cycle_id, status=SensorReading.Status.VALID, sample_count=4,
                temperature_c=temp, humidity_percent=humidity)


def _v1_payload(payload):
    required = {"version", "ciclo_id", "estado", "muestras_validas", "temperatura_c", "humedad_pct"}
    optional = {"error_codigo", "ciclo_en"}
    if not isinstance(payload, dict) or not required <= set(payload) or set(payload) - required - optional:
        raise ValueError("Campos JSON incorrectos.")
    if type(payload["version"]) is not int or payload["version"] != 1:
        raise ValueError("Versión de ciclo no compatible.")
    try:
        cycle_id = uuid.UUID(payload["ciclo_id"])
    except (TypeError, ValueError, AttributeError):
        raise ValueError("ciclo_id debe ser un UUID.") from None
    count = payload["muestras_validas"]
    if type(count) is not int or not 0 <= count <= 4:
        raise ValueError("muestras_validas debe estar entre 0 y 4.")
    started_at = None
    if "ciclo_en" in payload and payload["ciclo_en"] is not None:
        if not isinstance(payload["ciclo_en"], str):
            raise ValueError("ciclo_en inválido.")
        started_at = parse_datetime(payload["ciclo_en"])
        if started_at is None or timezone.is_naive(started_at):
            raise ValueError("ciclo_en requiere fecha y zona horaria.")
        started_at = started_at.astimezone(dt_timezone.utc)
        if started_at > timezone.now() + timedelta(minutes=5):
            raise ValueError("ciclo_en no puede estar en el futuro.")
    status = payload["estado"]
    if status == SensorReading.Status.VALID:
        if count != 4 or payload.get("error_codigo") not in (None, ""):
            raise ValueError("Un ciclo válido requiere cuatro muestras sin error.")
        return dict(cycle_id=cycle_id, status=status, sample_count=4,
                    temperature_c=_measurement(payload["temperatura_c"], Decimal("0"), Decimal("50")),
                    humidity_percent=_measurement(payload["humedad_pct"], Decimal("20"), Decimal("90")),
                    cycle_started_at=started_at)
    if status == SensorReading.Status.INVALID:
        if count == 4 or payload["temperatura_c"] is not None or payload["humedad_pct"] is not None:
            raise ValueError("Un ciclo inválido no lleva promedios.")
        if payload.get("error_codigo") != "SENSOR_LECTURA":
            raise ValueError("Un ciclo inválido requiere error_codigo SENSOR_LECTURA.")
        return dict(cycle_id=cycle_id, status=status, sample_count=count,
                    error_code="SENSOR_LECTURA", cycle_started_at=started_at)
    raise ValueError("Estado de ciclo inválido.")


@csrf_exempt
@require_POST
def sensor_ingest(request):
    """Compatibility endpoint for the firmware already flashed on the ESP32."""
    return _device_response(request, _legacy_payload, legacy=True)


@csrf_exempt
@require_POST
def sensor_cycle_ingest(request):
    return _device_response(request, _v1_payload)


def _device_for_query(request):
    code = request.GET.get("device")
    if code:
        return SensorDevice.objects.filter(code=code).first()
    return SensorDevice.objects.filter(code="ESP32-01").first() or SensorDevice.objects.order_by("pk").first()


def _cycle_json(reading):
    if reading is None:
        return None
    return {"cycle_id": str(reading.reading_id), "status": reading.status,
            "temperature_c": float(reading.temperature_c) if reading.temperature_c is not None else None,
            "humidity_percent": float(reading.humidity_percent) if reading.humidity_percent is not None else None,
            "sample_count": reading.sample_count, "error_code": reading.error_code or None,
            "received_at": reading.received_at.isoformat(),
            "measured_at": (reading.cycle_started_at or reading.received_at).isoformat(),
            "location": reading.assignment.location.name if reading.assignment else None}


@login_required
@require_GET
def sensor_latest(request):
    if not _authorized_user(request):
        return JsonResponse({"error": "Cuenta sin perfil autorizado."}, status=403)
    device = _device_for_query(request)
    if request.GET.get("device") and device is None:
        return JsonResponse({"error": "Dispositivo no encontrado."}, status=404)
    cycles = SensorReading.objects.select_related("assignment__location")
    if device:
        cycles = cycles.filter(device=device)
    latest_cycle = cycles.first()
    latest_valid = cycles.filter(status=SensorReading.Status.VALID).annotate(
        effective_at=Coalesce("cycle_started_at", "received_at")).order_by("-effective_at", "-pk").first()
    now = timezone.now()
    valid_fresh = latest_valid is not None and (now - latest_valid.effective_at).total_seconds() <= STALE_AFTER_SECONDS
    communication_fresh = latest_cycle is not None and (now - latest_cycle.received_at).total_seconds() <= STALE_AFTER_SECONDS
    assignment = SensorAssignment.objects.filter(device=device, ended_at__isnull=True).select_related("location").first() if device else None
    response = {
        "device": device.code if device else None,
        "current_location": assignment.location.name if assignment else None,
        "status": "waiting" if latest_valid is None else "online" if valid_fresh else "stale",
        "communication_status": "waiting" if latest_cycle is None else "online" if communication_fresh else "stale",
        "stale_after_seconds": STALE_AFTER_SECONDS,
        "server_time": now.isoformat(),
        "reading": _cycle_json(latest_valid),
        "last_cycle": _cycle_json(latest_cycle),
    }
    result = JsonResponse(response)
    result["Cache-Control"] = "no-store"
    return result


@login_required
@require_GET
def sensor_history(request):
    if not _authorized_user(request):
        return JsonResponse({"error": "Cuenta sin perfil autorizado."}, status=403)
    device = _device_for_query(request)
    if request.GET.get("device") and device is None:
        return JsonResponse({"error": "Dispositivo no encontrado."}, status=404)
    query = SensorReading.objects.select_related("assignment__location", "device")
    if device:
        query = query.filter(device=device)
    rows = [_cycle_json(item) for item in query[:100]]
    result = JsonResponse({"device": device.code if device else None, "cycles": rows})
    result["Cache-Control"] = "no-store"
    return result
