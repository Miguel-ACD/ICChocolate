"""Transactional temperature episodes and web/email outbox."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.utils import timezone
from .models import AlertEpisode, AlertNotification, AlertRule, SensorDevice, SensorReading, UserProfile
from .services import InventoryError, is_owner


def ensure_rule(device, created_by=None):
    rule = AlertRule.objects.filter(device=device, ended_at__isnull=True).first()
    if rule:
        return rule
    version = (AlertRule.objects.filter(device=device).order_by("-version").values_list("version", flat=True).first() or 0) + 1
    return AlertRule.objects.create(device=device, version=version, threshold_c=Decimal("10.00"),
                                    reminder_seconds=180, stale_seconds=180,
                                    started_at=timezone.now(), created_by=created_by)


def _event(episode, event, reading):
    content = {
        "event": event, "device": episode.device.code, "location": episode.location_snapshot,
        "temperature_c": str(reading.temperature_c), "threshold_c": str(episode.threshold_snapshot),
        "received_at": reading.received_at.isoformat(),
    }
    now = timezone.now()
    for profile in UserProfile.objects.select_related("user").filter(user__is_active=True):
        AlertNotification.objects.get_or_create(
            episode=episode, user=profile.user, event=event, channel=AlertNotification.Channel.WEB,
            defaults={"content": content, "status": AlertNotification.Status.ACCEPTED,
                      "available_at": now, "accepted_at": now})
        if profile.receives_alert_email and profile.alert_email and not profile.alert_email.lower().endswith(".local"):
            AlertNotification.objects.get_or_create(
                episode=episode, user=profile.user, event=event, channel=AlertNotification.Channel.EMAIL,
                defaults={"recipient_snapshot": profile.alert_email, "content": content,
                          "status": AlertNotification.Status.PENDING, "available_at": now})


def close_episode(episode, status, *, at=None, reading=None):
    if episode.status != AlertEpisode.Status.ACTIVE:
        return episode
    episode.status = status
    episode.closed_at = at or timezone.now()
    if reading is not None:
        episode.close_reading = reading
        episode.last_reading = reading
    episode.save(update_fields=["status", "closed_at", "close_reading", "last_reading"])
    AlertNotification.objects.filter(
        episode=episode, event=AlertNotification.Event.REMINDER,
        channel=AlertNotification.Channel.EMAIL, status=AlertNotification.Status.PENDING,
    ).update(status=AlertNotification.Status.CANCELLED)
    if status == AlertEpisode.Status.RECOVERED and reading is not None:
        _event(episode, AlertNotification.Event.RECOVERY, reading)
    return episode


def close_device_context(device, status):
    """Caller holds the device row lock."""
    episode = AlertEpisode.objects.select_for_update().filter(device=device, status=AlertEpisode.Status.ACTIVE).first()
    if episode:
        close_episode(episode, status)


def evaluate_cycle(cycle):
    """Caller holds the device row lock and runs in the same transaction as cycle storage."""
    if cycle.status != SensorReading.Status.VALID:
        return
    device = cycle.device
    rule = ensure_rule(device)
    episode = AlertEpisode.objects.select_for_update().filter(device=device, status=AlertEpisode.Status.ACTIVE).first()
    if episode and (cycle.received_at - episode.last_reading.received_at).total_seconds() >= rule.stale_seconds:
        close_episode(episode, AlertEpisode.Status.NO_DATA, at=cycle.received_at)
        episode = None
    if cycle.temperature_c > rule.threshold_c:
        if episode is None:
            episode = AlertEpisode.objects.create(
                device=device, rule=rule, start_reading=cycle, last_reading=cycle,
                status=AlertEpisode.Status.ACTIVE, started_at=cycle.received_at,
                location_snapshot=cycle.assignment.location.name,
                threshold_snapshot=rule.threshold_c)
            _event(episode, AlertNotification.Event.START, cycle)
        else:
            episode.last_reading = cycle
            episode.save(update_fields=["last_reading"])
            if (cycle.received_at - episode.started_at).total_seconds() >= rule.reminder_seconds:
                _event(episode, AlertNotification.Event.REMINDER, cycle)
    elif episode:
        close_episode(episode, AlertEpisode.Status.RECOVERED, at=cycle.received_at, reading=cycle)


def expire_stale_episodes(*, now=None):
    now = now or timezone.now()
    closed = 0
    for device_id in AlertEpisode.objects.filter(status=AlertEpisode.Status.ACTIVE).values_list("device_id", flat=True)[:100]:
        with transaction.atomic():
            device = SensorDevice.objects.select_for_update().get(pk=device_id)
            episode = AlertEpisode.objects.select_for_update().filter(device=device, status=AlertEpisode.Status.ACTIVE).first()
            if episode and (now - episode.last_reading.received_at).total_seconds() >= episode.rule.stale_seconds:
                close_episode(episode, AlertEpisode.Status.NO_DATA, at=now)
                closed += 1
    return closed


def change_rule(*, user, device_id, threshold_c):
    if not is_owner(user):
        raise InventoryError("Solo el dueño puede cambiar el umbral.")
    try:
        threshold = Decimal(str(threshold_c))
    except (InvalidOperation, ValueError):
        raise InventoryError("Umbral inválido.") from None
    if not threshold.is_finite() or not Decimal("0") <= threshold <= Decimal("50") or threshold.as_tuple().exponent < -2:
        raise InventoryError("El umbral debe estar entre 0 y 50 °C, con hasta dos decimales.")
    with transaction.atomic():
        try:
            device = SensorDevice.objects.select_for_update().get(pk=device_id)
        except SensorDevice.DoesNotExist:
            raise InventoryError("Dispositivo inexistente.") from None
        current = ensure_rule(device)
        if current.threshold_c == threshold:
            return current
        close_device_context(device, AlertEpisode.Status.CONFIGURATION)
        now = timezone.now()
        current.ended_at = now
        current.save(update_fields=["ended_at"])
        return AlertRule.objects.create(device=device, version=current.version + 1,
                                        threshold_c=threshold, reminder_seconds=current.reminder_seconds,
                                        stale_seconds=current.stale_seconds, started_at=now, created_by=user)
