import json
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from inventory.models import SensorReading, UserProfile


@override_settings(SENSOR_DEVICE_TOKEN="test-device-token")
class SensorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.owner = users.objects.create_user(username="owner-sensor@example.test", password="test-pass")
        cls.employee = users.objects.create_user(username="employee-sensor@example.test", password="test-pass")
        cls.no_profile = users.objects.create_user(username="other@example.test", password="test-pass")
        UserProfile.objects.create(user=cls.owner, role=UserProfile.Role.OWNER)
        UserProfile.objects.create(user=cls.employee, role=UserProfile.Role.EMPLOYEE)

    def payload(self):
        return {"reading_id": str(uuid.uuid4()), "temperature_c": 24.25, "humidity_percent": 61.5, "sample_count": 4}

    def post(self, payload, token="test-device-token"):
        return self.client.post(reverse("sensor_ingest"), json.dumps(payload), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_device_token_and_retry_idempotency(self):
        payload = self.payload()
        self.assertEqual(self.post(payload, token="wrong").status_code, 401)
        self.assertEqual(self.post(payload, token="tóken").status_code, 401)
        self.assertEqual(SensorReading.objects.count(), 0)
        self.assertEqual(self.post(payload).status_code, 201)
        self.assertEqual(self.post(payload).status_code, 200)
        self.assertEqual(SensorReading.objects.count(), 1)
        changed = dict(payload, temperature_c=25)
        self.assertEqual(self.post(changed).status_code, 409)
        self.assertEqual(SensorReading.objects.count(), 1)

    def test_invalid_measurements_are_rejected(self):
        for field, value in [
            ("temperature_c", -1), ("temperature_c", 51), ("temperature_c", True),
            ("temperature_c", float("nan")), ("humidity_percent", 19),
            ("humidity_percent", 91), ("humidity_percent", "45"),
            ("sample_count", 0), ("sample_count", 5), ("sample_count", True),
            ("reading_id", "bad-uuid"),
        ]:
            with self.subTest(field=field, value=value):
                payload = self.payload()
                payload[field] = value
                self.assertEqual(self.post(payload).status_code, 400)
        self.assertEqual(SensorReading.objects.count(), 0)

    def test_latest_requires_profile_and_reports_waiting_online_stale(self):
        url = reverse("sensor_latest")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.no_profile)
        self.assertEqual(self.client.get(url).status_code, 403)
        for user in (self.owner, self.employee):
            self.client.force_login(user)
            result = self.client.get(url)
            self.assertEqual(result.json()["status"], "waiting")
            self.assertIsNone(result.json()["reading"])
            self.assertEqual(result["Cache-Control"], "no-store")
            self.assertContains(self.client.get(reverse("inventory")), "Esperando sensor")

        self.assertEqual(self.post(self.payload()).status_code, 201)
        self.assertEqual(self.client.get(url).json()["status"], "online")
        SensorReading.objects.update(received_at=timezone.now() - timedelta(minutes=4))
        self.assertEqual(self.client.get(url).json()["status"], "stale")
