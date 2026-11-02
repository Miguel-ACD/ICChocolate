"""Keep seven days of ordinary sensor cycles while preserving alert evidence."""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import SensorReading


def prune_sensor_readings(now=None):
    cutoff = (now or timezone.now()) - timedelta(days=7)
    candidates = SensorReading.objects.filter(received_at__lt=cutoff).exclude(
        Q(started_alerts__isnull=False)
        | Q(latest_alerts__isnull=False)
        | Q(closed_alerts__isnull=False)
    ).values("pk").distinct()
    count = candidates.count()
    SensorReading.objects.filter(pk__in=candidates).delete()
    return count
