import json
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from inventory.device_service import (assign_device, register_device, rotate_device_token, store_cycle,
                                      set_device_active, token_digest)
from inventory.models import Location, SensorAssignment, SensorDevice, SensorReading, UserProfile
from inventory.services import InventoryError


class DeviceCycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.owner = users.objects.create_user(username="sensor-owner@qa.test", password="strong-test-pass")
        cls.employee = users.objects.create_user(username="sensor-employee@qa.test", password="strong-test-pass")
        UserProfile.objects.create(user=cls.owner, role="DUENO")
        UserProfile.objects.create(user=cls.employee, role="EMPLEADO")
        cls.warehouse = Location.objects.create(code="S-WH", name="Almacén")
        cls.display = Location.objects.create(code="S-DIS", name="Display")
        cls.device, _ = register_device(user=cls.owner, code="ESP32-01", location_id=cls.warehouse.pk,
                                        token="unique-test-device-token")

    def payload(self, **changes):
        data = {"version": 1, "ciclo_id": str(uuid.uuid4()), "estado": "VALIDO",
                "muestras_validas": 4, "temperatura_c": 12.5, "humedad_pct": 63.25}
        data.update(changes)
        return data

    def post(self, payload, token="unique-test-device-token"):
        return self.client.post(reverse("sensor_cycle_ingest"), json.dumps(payload),
                                content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_valid_cycle_dedup_conflict_and_stored_assignment(self):
        payload = self.payload()
        first = self.post(payload)
        self.assertEqual(first.status_code, 201)
        self.assertFalse(first.json()["duplicado"])
        second = self.post(payload)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["duplicado"])
        self.assertEqual(first.json()["medicion_id"], second.json()["medicion_id"])
        self.assertEqual(SensorReading.objects.count(), 1)
        reading = SensorReading.objects.get()
        self.assertEqual(reading.device, self.device)
        self.assertEqual(reading.assignment.location, self.warehouse)
        self.assertEqual(reading.sample_count, 4)
        self.assertEqual(reading.temperature_c, 12.5)
        self.assertEqual(self.post(dict(payload, temperatura_c=13)).status_code, 409)
        self.assertEqual(SensorReading.objects.count(), 1)

    def test_incomplete_cycle_has_no_average_and_does_not_refresh_valid(self):
        valid = self.payload()
        self.assertEqual(self.post(valid).status_code, 201)
        SensorReading.objects.update(received_at=timezone.now() - timedelta(minutes=4))
        invalid = self.payload(estado="INVALIDO", muestras_validas=3,
                               temperatura_c=None, humedad_pct=None, error_codigo="SENSOR_LECTURA")
        self.assertEqual(self.post(invalid).status_code, 201)
        reading = SensorReading.objects.get(reading_id=invalid["ciclo_id"])
        self.assertIsNone(reading.temperature_c)
        self.assertIsNone(reading.humidity_percent)
        self.client.force_login(self.employee)
        latest = self.client.get(reverse("sensor_latest")).json()
        self.assertEqual(latest["status"], "stale")
        self.assertEqual(latest["communication_status"], "online")
        self.assertEqual(latest["reading"]["cycle_id"], valid["ciclo_id"])
        self.assertEqual(latest["last_cycle"]["status"], "INVALIDO")
        self.assertEqual(self.client.get(reverse("sensor_history")).json()["cycles"][0]["status"], "INVALIDO")

    def test_inconsistent_payloads_never_write(self):
        bad = [
            {"muestras_validas": 3}, {"temperatura_c": 51}, {"temperatura_c": True},
            {"estado": "INVALIDO", "temperatura_c": None, "humedad_pct": None, "muestras_validas": 4,
             "error_codigo": "SENSOR_LECTURA"},
            {"estado": "INVALIDO", "temperatura_c": 0, "humedad_pct": None, "muestras_validas": 2,
             "error_codigo": "SENSOR_LECTURA"},
            {"estado": "INVALIDO", "temperatura_c": None, "humedad_pct": None, "muestras_validas": 2},
            {"version": 2}, {"ciclo_id": "no-uuid"}, {"muestras_validas": True},
            {"ciclo_en": "sin-zona"},
        ]
        for change in bad:
            with self.subTest(change=change):
                self.assertEqual(self.post(self.payload(**change)).status_code, 422)
        self.assertEqual(SensorReading.objects.count(), 0)

    def test_unknown_disabled_and_rotated_tokens_are_rejected(self):
        self.assertNotEqual(self.device.token_hash, "unique-test-device-token")
        self.assertEqual(self.device.token_hash, token_digest("unique-test-device-token"))
        self.assertEqual(self.post(self.payload(), token="wrong").status_code, 401)
        new_token = rotate_device_token(user=self.owner, device_id=self.device.pk)
        self.assertEqual(self.post(self.payload()).status_code, 401)
        self.assertEqual(self.post(self.payload(), token=new_token).status_code, 201)
        set_device_active(user=self.owner, device_id=self.device.pk, active=False)
        self.assertEqual(self.post(self.payload(), token=new_token).status_code, 401)
        self.assertEqual(SensorReading.objects.count(), 1)

    def test_second_device_and_reassignment_keep_zones_separate(self):
        first = self.payload()
        self.assertEqual(self.post(first).status_code, 201)
        before = SensorReading.objects.get(reading_id=first["ciclo_id"])
        original_assignment = before.assignment_id
        assign_device(user=self.owner, device_id=self.device.pk, location_id=self.display.pk)
        second = self.payload()
        self.assertEqual(self.post(second).status_code, 201)
        before.refresh_from_db()
        self.assertEqual(before.assignment_id, original_assignment)
        self.assertEqual(before.assignment.location_id, self.warehouse.pk)
        self.assertEqual(SensorReading.objects.get(reading_id=second["ciclo_id"]).assignment.location_id,
                         self.display.pk)
        other, other_token = register_device(user=self.owner, code="ESP32-02", location_id=self.warehouse.pk,
                                              token="another-unique-test-token")
        same_id = self.payload(ciclo_id=second["ciclo_id"], temperatura_c=17)
        self.assertEqual(self.post(same_id, token=other_token).status_code, 201)
        self.assertEqual(SensorReading.objects.filter(reading_id=second["ciclo_id"]).count(), 2)
        self.client.force_login(self.employee)
        display_latest = self.client.get(reverse("sensor_latest") + "?device=ESP32-01").json()
        warehouse_latest = self.client.get(reverse("sensor_latest") + "?device=ESP32-02").json()
        self.assertEqual(display_latest["reading"]["location"], "Display")
        self.assertEqual(warehouse_latest["reading"]["location"], "Almacén")
        self.assertEqual(other.code, "ESP32-02")

    def test_delayed_cycle_keeps_historical_zone_and_does_not_replace_newer_value(self):
        SensorAssignment.objects.filter(device=self.device).update(started_at=timezone.now() - timedelta(minutes=3))
        first = self.payload()
        self.assertEqual(self.post(first).status_code, 201)
        initial = SensorReading.objects.get(reading_id=first["ciclo_id"])
        initial_time = timezone.now() - timedelta(minutes=2)
        initial.cycle_started_at = initial_time
        initial.save(update_fields=["cycle_started_at"])
        assign_device(user=self.owner, device_id=self.device.pk, location_id=self.display.pk)
        newer = self.payload(temperatura_c=18)
        self.assertEqual(self.post(newer).status_code, 201)
        delayed = self.payload(temperatura_c=11, ciclo_en=initial_time.isoformat())
        self.assertEqual(self.post(delayed).status_code, 201)
        self.assertEqual(SensorReading.objects.get(reading_id=delayed["ciclo_id"]).assignment.location,
                         self.warehouse)
        self.client.force_login(self.employee)
        latest = self.client.get(reverse("sensor_latest")).json()
        self.assertEqual(latest["reading"]["cycle_id"], newer["ciclo_id"])

    def test_future_cycle_timestamp_is_rejected(self):
        too_late = (timezone.now() + timedelta(minutes=6)).isoformat()
        self.assertEqual(self.post(self.payload(ciclo_en=too_late)).status_code, 422)
        self.assertEqual(SensorReading.objects.count(), 0)
    def test_web_roles_and_history(self):
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get(reverse("monitoring")).status_code, 200)
        self.assertEqual(self.client.get(reverse("device_list")).status_code, 403)
        self.assertEqual(self.client.post(reverse("device_new"), {"code": "ESP32-02", "location": self.display.pk}).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("device_list")).status_code, 200)
        response = self.client.post(reverse("device_new"), {"code": "ESP32-02", "location": self.display.pk})
        self.assertEqual(response.status_code, 200)
        device = SensorDevice.objects.get(code="ESP32-02")
        self.assertIn("Token", response.content.decode())
        self.assertRedirects(self.client.post(reverse("device_assign", args=[device.pk]),
                                              {"location": self.warehouse.pk}), reverse("device_list"))
        self.assertEqual(SensorAssignment.objects.get(device=device, ended_at__isnull=True).location,
                         self.warehouse)

    def test_legacy_partial_cycle_is_invalid_not_fake_average(self):
        legacy = {"reading_id": str(uuid.uuid4()), "temperature_c": 10.0,
                  "humidity_percent": 50.0, "sample_count": 3}
        response = self.client.post(reverse("sensor_ingest"), json.dumps(legacy),
                                    content_type="application/json", HTTP_AUTHORIZATION="Bearer unique-test-device-token")
        self.assertEqual(response.status_code, 201)
        cycle = SensorReading.objects.get()
        self.assertEqual(cycle.status, "INVALIDO")
        self.assertIsNone(cycle.temperature_c)
        self.assertIsNone(cycle.humidity_percent)
        self.assertEqual(cycle.error_code, "INCOMPLETE_LEGACY")




class DeviceConcurrencyTests(TransactionTestCase):
    def test_parallel_retry_creates_one_cycle(self):
        user = get_user_model().objects.create_user(username="parallel-owner@qa.test", password="test-pass")
        UserProfile.objects.create(user=user, role="DUENO")
        location = Location.objects.create(code="S-PAR", name="Zona simultánea")
        device, _ = register_device(user=user, code="ESP32-PAR", location_id=location.pk,
                                    token="parallel-test-device-token")
        cycle_id = str(uuid.uuid4())
        barrier = Barrier(2)

        def send():
            from django.db import close_old_connections, connections
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                reading, created = store_cycle(device=device, cycle_id=cycle_id,
                                               status=SensorReading.Status.VALID, sample_count=4,
                                               temperature_c=12.5, humidity_percent=63.25)
                return reading.pk, created
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: send(), range(2)))
        self.assertEqual(SensorReading.objects.filter(device=device, reading_id=cycle_id).count(), 1)
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sorted(result[1] for result in results), [False, True])
