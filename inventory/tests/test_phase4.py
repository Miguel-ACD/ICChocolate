import json
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from inventory.alerts import change_rule, expire_stale_episodes
from inventory.alert_mail import (ConfirmedFailure, UncertainDelivery, mark_expired_leases,
                                  process_one_email)
from inventory.device_service import assign_device, register_device, store_cycle
from inventory.models import (AlertEpisode, AlertNotification, AlertRule, Location,
                              SensorReading, UserProfile)


class AlertPhaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.owner = users.objects.create_user(username="alert-owner@qa.test", password="test-password")
        cls.employee = users.objects.create_user(username="alert-employee@qa.test", password="test-password")
        UserProfile.objects.create(user=cls.owner, role="DUENO", alert_email="recipient@example.org",
                                   receives_alert_email=True)
        UserProfile.objects.create(user=cls.employee, role="EMPLEADO")
        cls.warehouse = Location.objects.create(code="AL-WH", name="Almacén")
        cls.display = Location.objects.create(code="AL-DIS", name="Display")
        cls.device, cls.token = register_device(user=cls.owner, code="ESP32-AL", location_id=cls.warehouse.pk,
                                                 token="phase4-device-token")

    def setUp(self):
        self.t0 = timezone.now()

    def cycle(self, temp, seconds=0, *, device=None, status="VALIDO", cycle_id=None):
        device = device or self.device
        at = self.t0 + timedelta(seconds=seconds)
        with patch("django.utils.timezone.now", return_value=at):
            return store_cycle(device=device, cycle_id=cycle_id or uuid.uuid4(), status=status,
                               sample_count=4 if status == "VALIDO" else 2,
                               temperature_c=Decimal(str(temp)) if status == "VALIDO" else None,
                               humidity_percent=Decimal("90.00") if status == "VALIDO" else None,
                               error_code="" if status == "VALIDO" else "SENSOR_LECTURA")[0]

    def events(self, channel="WEB"):
        return list(AlertNotification.objects.filter(channel=channel).order_by("created_at", "pk").values_list("event", flat=True))

    def test_exact_limit_humidity_and_first_deviation(self):
        self.cycle("10.00")
        self.assertFalse(AlertEpisode.objects.exists())
        self.cycle("10.01", 60)
        episode = AlertEpisode.objects.get()
        self.assertEqual(episode.threshold_snapshot, Decimal("10.00"))
        self.assertEqual(episode.location_snapshot, "Almacén")
        self.assertEqual(self.events(), ["INICIO", "INICIO"])
        self.assertEqual(self.events("EMAIL"), ["INICIO"])

    def test_one_reminder_only_after_three_minutes_with_fresh_reading(self):
        first = self.cycle("12.00")
        for seconds in (60, 120, 179):
            self.cycle("12.00", seconds)
        self.assertEqual(self.events("EMAIL"), ["INICIO"])
        at_boundary = self.cycle("12.00", 180)
        self.assertEqual(self.events("EMAIL"), ["INICIO", "RECORDATORIO"])
        self.cycle("12.00", 240)
        self.assertEqual(self.events("EMAIL"), ["INICIO", "RECORDATORIO"])
        self.assertEqual(AlertEpisode.objects.get().last_reading, SensorReading.objects.order_by("-pk").first())
        self.assertNotEqual(first.pk, at_boundary.pk)

    def test_recovery_and_second_episode_without_old_reminder(self):
        self.cycle("12.00")
        self.cycle("9.99", 120)
        first = AlertEpisode.objects.get()
        self.assertEqual(first.status, AlertEpisode.Status.RECOVERED)
        self.assertEqual(self.events("EMAIL"), ["INICIO", "RECUPERACION"])
        expire_stale_episodes(now=self.t0 + timedelta(seconds=300))
        self.assertEqual(self.events("EMAIL"), ["INICIO", "RECUPERACION"])
        self.cycle("11.00", 360)
        self.assertEqual(AlertEpisode.objects.count(), 2)
        self.assertEqual(self.events("EMAIL"), ["INICIO", "RECUPERACION", "INICIO"])

    def test_invalid_and_stale_never_claim_thermal_recovery(self):
        self.cycle("12.00")
        self.cycle(None, 60, status="INVALIDO")
        self.assertEqual(AlertEpisode.objects.get().status, AlertEpisode.Status.ACTIVE)
        self.assertEqual(expire_stale_episodes(now=self.t0 + timedelta(seconds=180)), 1)
        self.assertEqual(AlertEpisode.objects.get().status, AlertEpisode.Status.NO_DATA)
        self.assertEqual(self.events("EMAIL"), ["INICIO"])
        self.cycle("12.00", 181)
        self.assertEqual(AlertEpisode.objects.count(), 2)
        self.assertEqual(self.events("EMAIL"), ["INICIO", "INICIO"])

    def test_rule_change_and_zone_change_close_without_fake_recovery(self):
        self.cycle("12.00")
        with patch("django.utils.timezone.now", return_value=self.t0 + timedelta(seconds=60)):
            current = change_rule(user=self.owner, device_id=self.device.pk, threshold_c="30.00")
        self.assertEqual(current.version, 2)
        self.assertEqual(AlertEpisode.objects.get().status, AlertEpisode.Status.CONFIGURATION)
        self.cycle("20.00", 120)
        self.assertEqual(AlertEpisode.objects.count(), 1)
        self.cycle("31.00", 180)
        self.assertEqual(AlertEpisode.objects.count(), 2)
        assign_device(user=self.owner, device_id=self.device.pk, location_id=self.display.pk)
        self.assertEqual(AlertEpisode.objects.order_by("-pk").first().status, AlertEpisode.Status.REASSIGNED)
        self.assertNotIn("RECUPERACION", self.events("EMAIL"))

    def test_two_devices_do_not_mix_alerts(self):
        other, _ = register_device(user=self.owner, code="ESP32-OTHER", location_id=self.display.pk,
                                   token="other-phase4-token")
        self.cycle("12.00")
        self.cycle("13.00", device=other)
        self.assertEqual(AlertEpisode.objects.filter(status="ACTIVO").count(), 2)
        self.assertEqual(set(AlertEpisode.objects.values_list("location_snapshot", flat=True)), {"Almacén", "Display"})
        self.cycle("10.00", 60)
        self.assertEqual(AlertEpisode.objects.filter(status="ACTIVO").count(), 1)
        self.assertEqual(AlertEpisode.objects.get(status="ACTIVO").device, other)

    def test_web_roles_recipient_validation_and_ingest_integration(self):
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get(reverse("alert_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("alert_rules")).status_code, 403)
        self.assertEqual(self.client.post(reverse("alert_rule_edit", args=[self.device.pk]), {"threshold_c": "30"}).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("alert_rules")).status_code, 200)
        profile = self.owner.profile
        bad = self.client.post(reverse("alert_recipient_edit", args=[profile.pk]),
                               {"alert_email": "owner@local.local", "receives_alert_email": "on"})
        self.assertContains(bad, "dirección real")
        payload = {"version": 1, "ciclo_id": str(uuid.uuid4()), "estado": "VALIDO", "muestras_validas": 4,
                   "temperatura_c": 12.0, "humedad_pct": 60.0}
        response = self.client.post(reverse("sensor_cycle_ingest"), json.dumps(payload),
                                    content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(response.status_code, 201)
        self.assertContains(self.client.get(reverse("alert_list")), "ESP32-AL")
        self.assertEqual(AlertNotification.objects.filter(channel="WEB", user=self.owner).count(), 1)

    def test_pending_reminder_is_cancelled_on_recovery(self):
        for seconds in (0, 60, 120, 180):
            self.cycle("12.00", seconds)
        reminder = AlertNotification.objects.get(channel="EMAIL", event="RECORDATORIO")
        self.assertEqual(reminder.status, "PENDIENTE")
        self.cycle("10.00", 240)
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, "CANCELADA")
        self.assertEqual(AlertEpisode.objects.get().status, "RECUPERADO")

    def test_same_http_cycle_never_duplicates_alerts(self):
        payload = {"version": 1, "ciclo_id": str(uuid.uuid4()), "estado": "VALIDO", "muestras_validas": 4,
                   "temperatura_c": 12.0, "humedad_pct": 60.0}
        def submit():
            return self.client.post(reverse("sensor_cycle_ingest"), json.dumps(payload),
                                    content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(submit().status_code, 201)
        self.assertEqual(submit().status_code, 200)
        self.assertEqual(AlertEpisode.objects.count(), 1)
        self.assertEqual(AlertNotification.objects.count(), 3)

    def test_owner_updates_recipient_and_threshold_in_web(self):
        self.client.force_login(self.owner)
        profile = self.owner.profile
        response = self.client.post(reverse("alert_recipient_edit", args=[profile.pk]),
                                    {"alert_email": "new@example.org", "receives_alert_email": "on"})
        self.assertRedirects(response, reverse("alert_recipients"))
        profile.refresh_from_db()
        self.assertEqual(profile.alert_email, "new@example.org")
        response = self.client.post(reverse("alert_rule_edit", args=[self.device.pk]), {"threshold_c": "15.25"})
        self.assertRedirects(response, reverse("alert_rules"))
        self.assertEqual(AlertRule.objects.get(device=self.device, ended_at__isnull=True).threshold_c, Decimal("15.25"))

    @override_settings(ALERT_SMTP_HOST="smtp.example.org", ALERT_SMTP_USERNAME="sender@example.org",
                       ALERT_SMTP_PASSWORD="local-test-only", ALERT_SMTP_FROM="sender@example.org")
    def test_smtp_accept_retry_ambiguous_and_dead_worker(self):
        self.cycle("12.00")
        pending = AlertNotification.objects.get(channel="EMAIL")
        self.assertTrue(process_one_email(now=self.t0, sender=lambda _: None))
        pending.refresh_from_db()
        self.assertEqual(pending.status, "ACEPTADA")
        self.assertFalse(process_one_email(now=self.t0, sender=lambda _: None))
        self.cycle("12.00", 60)
        self.cycle("12.00", 120)
        self.cycle("12.00", 180)
        reminder = AlertNotification.objects.get(channel="EMAIL", event="RECORDATORIO")
        def rejected(_):
            raise ConfirmedFailure("SMTP_REJECTED")
        self.assertTrue(process_one_email(now=self.t0 + timedelta(seconds=180), sender=rejected))
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, "PENDIENTE")
        self.assertEqual(reminder.attempts, 1)
        self.assertFalse(process_one_email(now=self.t0 + timedelta(seconds=181), sender=rejected))
        def unknown(_):
            raise UncertainDelivery("SMTP_TIMEOUT")
        self.assertTrue(process_one_email(now=self.t0 + timedelta(seconds=210), sender=unknown))
        reminder.refresh_from_db()
        self.assertEqual(reminder.status, "INCIERTA")
        self.assertFalse(process_one_email(now=self.t0 + timedelta(seconds=1000), sender=lambda _: None))
        self.cycle("9.00", 250)
        recovery = AlertNotification.objects.get(channel="EMAIL", event="RECUPERACION")
        recovery.status = "ENVIANDO"
        recovery.lease_until = self.t0 + timedelta(seconds=260)
        recovery.save(update_fields=["status", "lease_until"])
        self.assertEqual(mark_expired_leases(now=self.t0 + timedelta(seconds=400)), 1)
        recovery.refresh_from_db()
        self.assertEqual(recovery.status, "INCIERTA")

    @override_settings(ALERT_SMTP_HOST="smtp.example.org", ALERT_SMTP_USERNAME="sender@example.org",
                       ALERT_SMTP_PASSWORD="local-test-only", ALERT_SMTP_FROM="sender@example.org")
    def test_deactivated_recipient_cancels_pending_email(self):
        self.cycle("12.00")
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.assertTrue(process_one_email(now=self.t0, sender=lambda _: None))
        self.assertEqual(AlertNotification.objects.get(channel="EMAIL").status, "CANCELADA")
