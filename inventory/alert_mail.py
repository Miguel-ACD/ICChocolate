"""Persistent SMTP outbox; uncertain sends are never retried automatically."""
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import AlertNotification

RETRY_SECONDS = (30, 120, 300)


class ConfirmedFailure(Exception):
    pass


class UncertainDelivery(Exception):
    pass


def smtp_ready():
    return all((settings.ALERT_SMTP_HOST, settings.ALERT_SMTP_USERNAME,
                settings.ALERT_SMTP_PASSWORD, settings.ALERT_SMTP_FROM))


def _message(notification):
    data = notification.content
    labels = {"INICIO": "Temperatura fuera de umbral", "RECORDATORIO": "Temperatura aún fuera de umbral",
              "RECUPERACION": "Temperatura recuperada"}
    message = EmailMessage()
    message["Subject"] = f"ICChocolate: {labels[notification.event]} · {data['device']}"
    message["From"] = settings.ALERT_SMTP_FROM
    message["To"] = notification.recipient_snapshot
    message["Message-ID"] = notification.message_id
    message.set_content(
        f"Evento: {notification.get_event_display()}\n"
        f"Dispositivo: {data['device']}\nZona: {data['location']}\n"
        f"Temperatura: {data['temperature_c']} °C\nUmbral: {data['threshold_c']} °C\n"
        f"Recepción: {data['received_at']}\n\n"
        "La aceptación SMTP no confirma la llegada al buzón."
    )
    return message


def send_smtp(notification):
    """Raise ConfirmedFailure for a known rejection, UncertainDelivery for an unknown send result."""
    phase = "connect"
    try:
        with smtplib.SMTP(settings.ALERT_SMTP_HOST, settings.ALERT_SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo()
            if settings.ALERT_SMTP_STARTTLS:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            smtp.login(settings.ALERT_SMTP_USERNAME, settings.ALERT_SMTP_PASSWORD)
            phase = "send"
            refused = smtp.send_message(_message(notification))
            if refused:
                raise ConfirmedFailure("SMTP_RECIPIENT_REFUSED")
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as exc:
        raise ConfirmedFailure(type(exc).__name__) from None
    except smtplib.SMTPAuthenticationError:
        raise ConfirmedFailure("SMTP_AUTH") from None
    except ConfirmedFailure:
        raise
    except Exception as exc:
        if phase == "send":
            raise UncertainDelivery(type(exc).__name__) from None
        raise ConfirmedFailure(type(exc).__name__) from None


def mark_expired_leases(*, now=None):
    now = now or timezone.now()
    return AlertNotification.objects.filter(
        channel=AlertNotification.Channel.EMAIL, status=AlertNotification.Status.SENDING,
        lease_until__lte=now,
    ).update(status=AlertNotification.Status.UNCERTAIN, error_code="WORKER_LEASE_EXPIRED", lease_until=None)


def process_one_email(*, now=None, sender=send_smtp):
    if not smtp_ready():
        return False
    now = now or timezone.now()
    with transaction.atomic():
        notification = AlertNotification.objects.select_for_update(skip_locked=True, of=("self",)).filter(
            channel=AlertNotification.Channel.EMAIL, status=AlertNotification.Status.PENDING,
            available_at__lte=now).select_related("user__profile", "episode").order_by("available_at", "pk").first()
        if notification is None:
            return False
        profile = getattr(notification.user, "profile", None)
        if not notification.user.is_active or profile is None or not profile.receives_alert_email or profile.alert_email != notification.recipient_snapshot:
            notification.status = AlertNotification.Status.CANCELLED
            notification.save(update_fields=["status"])
            return True
        notification.status = AlertNotification.Status.SENDING
        notification.attempts += 1
        notification.lease_until = now + timedelta(seconds=90)
        if not notification.message_id:
            notification.message_id = f"<icchocolate-alert-{notification.pk}@icchocolate.local>"
        notification.save(update_fields=["status", "attempts", "lease_until", "message_id"])
    try:
        sender(notification)
    except UncertainDelivery as exc:
        status = AlertNotification.Status.UNCERTAIN
        error_code = str(exc)[:60]
    except ConfirmedFailure as exc:
        status = AlertNotification.Status.PENDING if notification.attempts <= len(RETRY_SECONDS) else AlertNotification.Status.FAILED
        error_code = str(exc)[:60]
    else:
        status = AlertNotification.Status.ACCEPTED
        error_code = ""
    with transaction.atomic():
        locked = AlertNotification.objects.select_for_update().get(pk=notification.pk)
        if locked.status != AlertNotification.Status.SENDING:
            return True
        locked.status = status
        locked.lease_until = None
        locked.error_code = error_code
        if status == AlertNotification.Status.ACCEPTED:
            locked.accepted_at = timezone.now()
        elif status == AlertNotification.Status.PENDING:
            locked.available_at = now + timedelta(seconds=RETRY_SECONDS[notification.attempts - 1])
        locked.save(update_fields=["status", "lease_until", "error_code", "accepted_at", "available_at"])
    return True
