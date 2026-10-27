"""Identity, assignments and cycle persistence for ESP32 devices."""
import hashlib
import re
import secrets
import uuid
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from .models import Location, SensorAssignment, SensorDevice, SensorReading
from .services import InventoryError, is_owner


def token_digest(token):
    if not isinstance(token, str) or not token or len(token) > 256 or not token.isascii():
        raise ValueError("Token inválido.")
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def authenticate_device(header):
    if not isinstance(header, str) or not header.startswith("Bearer "):
        return None
    try:
        digest = token_digest(header[7:])
    except ValueError:
        return None
    return SensorDevice.objects.filter(token_hash=digest, active=True).first()


def register_device(*, user, code, location_id, token=None, started_at=None):
    if not is_owner(user):
        raise InventoryError("Solo el dueño puede registrar dispositivos.")
    code = code.strip().upper() if isinstance(code, str) else ""
    if not re.fullmatch(r"[A-Z0-9_-]{3,40}", code):
        raise InventoryError("Código de dispositivo inválido.")
    token = token or secrets.token_urlsafe(32)
    try:
        digest = token_digest(token)
        with transaction.atomic():
            location = Location.objects.get(pk=location_id, active=True)
            device = SensorDevice.objects.create(code=code, token_hash=digest)
            SensorAssignment.objects.create(device=device, location=location,
                                            started_at=started_at or timezone.now())
            from .alerts import ensure_rule
            ensure_rule(device, created_by=user)
            return device, token
    except ValueError:
        raise InventoryError("Token de dispositivo inválido.") from None
    except Location.DoesNotExist:
        raise InventoryError("Ubicación inexistente o inactiva.") from None
    except IntegrityError:
        raise InventoryError("Código o token de dispositivo ya registrado.") from None


def assign_device(*, user, device_id, location_id):
    if not is_owner(user):
        raise InventoryError("Solo el dueño puede asignar dispositivos.")
    with transaction.atomic():
        try:
            device = SensorDevice.objects.select_for_update().get(pk=device_id)
            location = Location.objects.get(pk=location_id, active=True)
        except (SensorDevice.DoesNotExist, Location.DoesNotExist):
            raise InventoryError("Dispositivo o ubicación inexistente.") from None
        current = SensorAssignment.objects.select_for_update().filter(device=device, ended_at__isnull=True).first()
        if current and current.location_id == location.pk:
            return current
        from .alerts import close_device_context
        from .models import AlertEpisode
        close_device_context(device, AlertEpisode.Status.REASSIGNED)
        now = timezone.now()
        if current:
            current.ended_at = now
            current.save(update_fields=["ended_at"])
        return SensorAssignment.objects.create(device=device, location=location, started_at=now)


def set_device_active(*, user, device_id, active):
    if not is_owner(user):
        raise InventoryError("Solo el dueño puede cambiar dispositivos.")
    with transaction.atomic():
        try:
            device = SensorDevice.objects.select_for_update().get(pk=device_id)
        except SensorDevice.DoesNotExist:
            raise InventoryError("Dispositivo inexistente.") from None
        if not active and device.active:
            from .alerts import close_device_context
            from .models import AlertEpisode
            close_device_context(device, AlertEpisode.Status.CONFIGURATION)
        device.active = bool(active)
        device.save(update_fields=["active"])
        return device


def rotate_device_token(*, user, device_id):
    if not is_owner(user):
        raise InventoryError("Solo el dueño puede rotar tokens.")
    new_token = secrets.token_urlsafe(32)
    with transaction.atomic():
        try:
            device = SensorDevice.objects.select_for_update().get(pk=device_id)
        except SensorDevice.DoesNotExist:
            raise InventoryError("Dispositivo inexistente.") from None
        device.token_hash = token_digest(new_token)
        device.save(update_fields=["token_hash"])
    return new_token


def store_cycle(*, device, cycle_id, status, sample_count, temperature_c=None,
                humidity_percent=None, error_code="", cycle_started_at=None):
    """Return (cycle, created); a changed retry raises InventoryError."""
    try:
        cycle_id = uuid.UUID(str(cycle_id))
    except (ValueError, TypeError):
        raise InventoryError("ciclo_id inválido.") from None
    with transaction.atomic():
        locked_device = SensorDevice.objects.select_for_update().get(pk=device.pk, active=True)
        previous = SensorReading.objects.filter(device=locked_device, reading_id=cycle_id).first()
        expected = (status, sample_count, temperature_c, humidity_percent, error_code, cycle_started_at)
        if previous:
            actual = (previous.status, previous.sample_count, previous.temperature_c,
                      previous.humidity_percent, previous.error_code, previous.cycle_started_at)
            if actual != expected:
                raise InventoryError("El ciclo ya existe con otros datos.")
            return previous, False
        assignments = SensorAssignment.objects.select_for_update().filter(device=locked_device)
        if cycle_started_at is not None:
            assignment = assignments.filter(started_at__lte=cycle_started_at).filter(
                Q(ended_at__gt=cycle_started_at) | Q(ended_at__isnull=True)).first()
        else:
            assignment = assignments.filter(ended_at__isnull=True).first()
        if assignment is None:
            raise InventoryError("Dispositivo sin ubicación activa.")
        cycle = SensorReading.objects.create(reading_id=cycle_id, device=locked_device,
                                             assignment=assignment, status=status,
                                             sample_count=sample_count,
                                             temperature_c=temperature_c,
                                             humidity_percent=humidity_percent,
                                             error_code=error_code,
                                             cycle_started_at=cycle_started_at)
        from .alerts import evaluate_cycle
        evaluate_cycle(cycle)
        return cycle, True
