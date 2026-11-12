"""Adversarial HTTP and service matrix; every generated method is a separate test."""

import json
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from inventory.device_service import register_device
from inventory.models import Location, Movement, MovementDraft, PhotoDocument, Presentation, Product, SensorReading, Stock, UserProfile
from inventory.services import InventoryError, register_movement


class AbuseMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.owner = users.objects.create_user(username="abuse-owner@example.test", password="OwnerPass!2030")
        cls.employee = users.objects.create_user(username="abuse-worker@example.test", password="WorkerPass!2030")
        cls.guest = users.objects.create_user(username="abuse-guest@example.test", password="GuestPass!2030")
        UserProfile.objects.create(user=cls.owner, role=UserProfile.Role.OWNER)
        UserProfile.objects.create(user=cls.employee, role=UserProfile.Role.EMPLOYEE)
        cls.product = Product.objects.create(code="AB-CHOC", name="Chocolate de prueba")
        cls.presentation = Presentation.objects.create(product=cls.product, code="AB-BARRA", name="Barra de prueba",
            unit_description="Una barra de 100 g", content_value=100, content_unit=Presentation.Unit.GRAM)
        cls.inactive_presentation = Presentation.objects.create(product=cls.product, code="AB-OLD", name="Barra antigua",
            unit_description="Una barra", content_value=100, content_unit=Presentation.Unit.GRAM, active=False)
        cls.source = Location.objects.create(code="AB-ALM", name="Almacén de prueba")
        cls.target = Location.objects.create(code="AB-DIS", name="Mostrador de prueba")
        cls.inactive_location = Location.objects.create(code="AB-OLD", name="Zona antigua", active=False)

    def _resolve(self, value):
        return {
            "$presentation": self.presentation.pk,
            "$inactive_presentation": self.inactive_presentation.pk,
            "$source": self.source.pk,
            "$target": self.target.pk,
            "$inactive_location": self.inactive_location.pk,
        }.get(value, value) if isinstance(value, str) else value

    def _form_payload(self, changes):
        data = {"type": "COMPRA", "presentation": self.presentation.pk, "quantity": "1",
                "source": self.source.pk, "destination": "", "reason": ""}
        data.update({key: self._resolve(value) for key, value in changes.items()})
        return data

    def _service_payload(self, changes):
        data = {"user": self.employee, "type_": "COMPRA", "presentation_id": self.presentation.pk,
                "quantity": 1, "source_id": self.source.pk}
        data.update({key: self._resolve(value) for key, value in changes.items()})
        return data


# A rejected preview must neither reserve stock nor create a draft or movement.
BAD_PREVIEWS = {
    "missing_type": {"type": ""},
    "unknown_type": {"type": "BORRAR"},
    "number_as_type": {"type": "123"},
    "initial_load_by_employee": {"type": "INICIAL"},
    "conversion_in_manual_form": {"type": "CONVERSION"},
    "reversal_in_manual_form": {"type": "REVERSO"},
    "missing_presentation": {"presentation": ""},
    "unknown_presentation": {"presentation": "99999"},
    "letters_as_presentation_id": {"presentation": "barra"},
    "inactive_presentation": {"presentation": "$inactive_presentation"},
    "missing_quantity": {"quantity": ""},
    "zero_quantity": {"quantity": "0"},
    "negative_quantity": {"quantity": "-2"},
    "large_negative_quantity": {"quantity": "-999999"},
    "fractional_quantity": {"quantity": "1.5"},
    "letters_as_quantity": {"quantity": "muchas"},
    "exponential_quantity": {"quantity": "1e3"},
    "boolean_quantity": {"quantity": "True"},
    "quantity_above_limit": {"quantity": "9000000000000000001"},
    "missing_location": {"source": ""},
    "unknown_location": {"source": "99999"},
    "letters_as_location_id": {"source": "almacen"},
    "inactive_location": {"source": "$inactive_location"},
    "transfer_without_destination": {"type": "TRASLADO"},
    "transfer_to_same_location": {"type": "TRASLADO", "destination": "$source"},
    "transfer_to_unknown_location": {"type": "TRASLADO", "destination": "99999"},
    "transfer_to_inactive_location": {"type": "TRASLADO", "destination": "$inactive_location"},
    "purchase_with_destination": {"destination": "$target"},
    "sale_with_destination": {"type": "VENTA", "destination": "$target"},
    "waste_without_reason": {"type": "MERMA", "reason": "   "},
    "consumption_without_reason": {"type": "CONSUMO", "reason": ""},
    "reason_too_long": {"reason": "x" * 501},
}


def _preview_test(changes):
    def test(self):
        self.client.force_login(self.employee)
        result = self.client.post(reverse("movement_new"), self._form_payload(changes))
        self.assertEqual(result.status_code, 200)
        self.assertFalse(MovementDraft.objects.exists())
        self.assertFalse(Movement.objects.exists())
        self.assertFalse(Stock.objects.exists())
    return test


for _name, _changes in BAD_PREVIEWS.items():
    setattr(AbuseMatrixTests, f"test_preview_rejects_{_name}", _preview_test(_changes))


# Service calls bypass the browser; they must enforce the same invariants.
BAD_SERVICE_MOVES = {
    "zero_quantity": {"quantity": 0},
    "negative_quantity": {"quantity": -1},
    "excessive_quantity": {"quantity": 9_000_000_000_000_000_001},
    "fractional_quantity": {"quantity": 1.5},
    "decimal_quantity": {"quantity": Decimal("1.0")},
    "boolean_quantity": {"quantity": True},
    "unicode_digit_quantity": {"quantity": "٣"},
    "letters_quantity": {"quantity": "dos"},
    "fractional_string_quantity": {"quantity": "1.5"},
    "unknown_presentation": {"presentation_id": 99999},
    "huge_presentation_id": {"presentation_id": 2**80},
    "boolean_presentation_id": {"presentation_id": True},
    "letters_presentation_id": {"presentation_id": "barra"},
    "inactive_presentation": {"presentation_id": "$inactive_presentation"},
    "unknown_location": {"source_id": 99999},
    "huge_location_id": {"source_id": 2**80},
    "boolean_location_id": {"source_id": False},
    "inactive_location": {"source_id": "$inactive_location"},
    "unknown_type": {"type_": "BORRAR"},
    "initial_load_by_employee": {"type_": "INICIAL"},
    "conversion_as_manual_move": {"type_": "CONVERSION"},
    "sale_without_stock": {"type_": "VENTA"},
    "waste_without_stock": {"type_": "MERMA", "reason": "Roto"},
    "consumption_without_stock": {"type_": "CONSUMO", "reason": "Muestra"},
    "transfer_without_stock": {"type_": "TRASLADO", "destination_id": "$target"},
    "transfer_without_destination": {"type_": "TRASLADO"},
    "transfer_to_same_location": {"type_": "TRASLADO", "destination_id": "$source"},
    "purchase_with_destination": {"destination_id": "$target"},
    "waste_without_reason": {"type_": "MERMA"},
    "consumption_without_reason": {"type_": "CONSUMO"},
    "numeric_reason": {"reason": 123},
    "reason_too_long": {"reason": "x" * 501},
    "bad_idempotency_key": {"idempotency_key": "not-a-uuid"},
}


def _service_test(changes):
    def test(self):
        with self.assertRaises(InventoryError):
            register_movement(**self._service_payload(changes))
        self.assertFalse(Movement.objects.exists())
        self.assertFalse(Stock.objects.exists())
    return test


for _name, _changes in BAD_SERVICE_MOVES.items():
    setattr(AbuseMatrixTests, f"test_service_rejects_{_name}", _service_test(_changes))


ANONYMOUS_PAGES = (
    "dashboard", "inventory", "movement_history", "movement_new", "draft_list", "conversion_new",
    "monitoring", "alert_list", "document_new", "chat_page", "catalog_admin", "equivalence_list",
    "device_list", "alert_rules", "alert_recipients", "user_list", "product_new",
    "presentation_new", "location_new", "location_rename",
)


def _anonymous_test(route):
    def test(self):
        result = self.client.get(reverse(route))
        self.assertEqual(result.status_code, 302)
        self.assertIn("/accounts/login/", result["Location"])
    return test


for _route in ANONYMOUS_PAGES:
    setattr(AbuseMatrixTests, f"test_anonymous_cannot_open_{_route}", _anonymous_test(_route))


EMPLOYEE_DENIED_PAGES = (
    "catalog_admin", "equivalence_list", "equivalence_new", "device_list", "device_new",
    "alert_rules", "alert_recipients", "user_list", "user_new", "product_new",
    "presentation_new", "location_new", "location_rename",
)


def _employee_denied_test(route):
    def test(self):
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get(reverse(route)).status_code, 403)
    return test


for _route in EMPLOYEE_DENIED_PAGES:
    setattr(AbuseMatrixTests, f"test_employee_cannot_open_{_route}", _employee_denied_test(_route))


BAD_LOGINS = (
    ("wrong_owner_password", "abuse-owner@example.test", "bad-password"),
    ("wrong_worker_password", "abuse-worker@example.test", "bad-password"),
    ("unknown_email", "missing@example.test", "OwnerPass!2030"),
    ("numbers_instead_of_email", "12345", "OwnerPass!2030"),
    ("empty_email", "", "OwnerPass!2030"),
    ("empty_password", "abuse-owner@example.test", ""),
    ("swapped_credentials", "abuse-owner@example.test", "WorkerPass!2030"),
    ("case_changed_password", "abuse-owner@example.test", "ownerpass!2030"),
)


def _bad_login_test(email, password):
    def test(self):
        response = self.client.post(reverse("login"), {"username": email, "password": password})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(Movement.objects.exists())
    return test


for _name, _email, _password in BAD_LOGINS:
    setattr(AbuseMatrixTests, f"test_login_rejects_{_name}", _bad_login_test(_email, _password))


class NumericNameTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(username="numeric-owner@example.test", password="StrongPass!2030")
        UserProfile.objects.create(user=cls.owner, role=UserProfile.Role.OWNER)
        cls.product = Product.objects.create(code="NUM-CHOC", name="Chocolate")
        cls.presentation = Presentation.objects.create(product=cls.product, code="NUM-BAR", name="Barra",
            unit_description="Una barra", content_value=100, content_unit=Presentation.Unit.GRAM)
        cls.location = Location.objects.create(code="NUM-ALM", name="Almacén")

    def setUp(self):
        self.client.force_login(self.owner)

    def test_product_name_cannot_be_only_numbers(self):
        response = self.client.post(reverse("product_new"), {"code": "NUM-PROD", "name": "12345",
            "presentation_code": "NUM-PRES", "presentation_name": "Barra", "unit_description": "Una barra",
            "content_value": "100", "content_unit": "G"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(code="NUM-PROD").exists())

    def test_presentation_name_cannot_be_only_numbers(self):
        response = self.client.post(reverse("presentation_new"), {"product": self.product.pk,
            "code": "NUM-PRES", "name": "12345", "unit_description": "Una barra",
            "content_value": "100", "content_unit": "G"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Presentation.objects.filter(code="NUM-PRES").exists())

    def test_location_name_cannot_be_only_numbers(self):
        response = self.client.post(reverse("location_new"), {"code": "NUM-LOC", "name": "12345"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Location.objects.filter(code="NUM-LOC").exists())

    def test_rename_location_cannot_use_only_numbers(self):
        response = self.client.post(reverse("location_rename"), {"location": self.location.pk, "name": "12345"})
        self.assertEqual(response.status_code, 200)
        self.location.refresh_from_db()
        self.assertEqual(self.location.name, "Almacén")

    def test_user_alias_cannot_be_only_numbers(self):
        response = self.client.post(reverse("user_new"), {"email": "number-user@example.test", "alias": "12345",
            "role": "EMPLEADO", "password1": "StrongPass!2030", "password2": "StrongPass!2030"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="number-user@example.test").exists())

    def test_product_edit_rejects_numeric_name(self):
        response = self.client.post(reverse("product_edit", args=[self.product.pk]), {"name": "123", "active": "on"})
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Chocolate")

    def test_presentation_edit_rejects_numeric_name(self):
        response = self.client.post(reverse("presentation_edit", args=[self.presentation.pk]),
            {"name": "123", "unit_description": "Una barra", "active": "on"})
        self.assertEqual(response.status_code, 200)
        self.presentation.refresh_from_db()
        self.assertEqual(self.presentation.name, "Barra")

    def test_location_edit_rejects_numeric_name(self):
        response = self.client.post(reverse("location_edit", args=[self.location.pk]), {"name": "123", "active": "on"})
        self.assertEqual(response.status_code, 200)
        self.location.refresh_from_db()
        self.assertEqual(self.location.name, "Almacén")

    def test_owner_alias_change_rejects_numeric_name(self):
        response = self.client.post(reverse("alias_settings"), {"alias": "123"})
        self.assertEqual(response.status_code, 200)
        self.owner.profile.refresh_from_db()
        self.assertNotEqual(self.owner.profile.alias, "123")


class BoundaryAndControlsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.owner = users.objects.create_user(username="boundary-owner@example.test", password="OwnerPass!2030")
        cls.employee = users.objects.create_user(username="boundary-worker@example.test", password="WorkerPass!2030")
        UserProfile.objects.create(user=cls.owner, role=UserProfile.Role.OWNER)
        UserProfile.objects.create(user=cls.employee, role=UserProfile.Role.EMPLOYEE)
        cls.product = Product.objects.create(code="BC-CHOC", name="Chocolate")
        cls.presentation = Presentation.objects.create(product=cls.product, code="BC-BAR", name="Barra",
            unit_description="Una barra", content_value=100, content_unit=Presentation.Unit.GRAM)
        cls.location = Location.objects.create(code="BC-ALM", name="Almacén")
        cls.device, cls.token = register_device(user=cls.owner, code="ESP32-BC", location_id=cls.location.pk,
            token="boundary-device-token")

    def test_worker_cannot_see_admin_menu_but_can_see_chat(self):
        self.client.force_login(self.employee)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertNotIn("Administrar <span", html)
        self.assertIn('id="chat-launcher"', html)
        self.assertIn('id="chat-form"', html)

    def test_malicious_login_next_does_not_redirect_external(self):
        response = self.client.post(reverse("login") + "?next=https://example.com/", {
            "username": "boundary-owner@example.test", "password": "OwnerPass!2030"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("dashboard"))

    def test_chat_rejects_wrong_content_type(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse("chat_api"), {"question": "Stock"}).status_code, 415)

    def test_chat_rejects_malformed_json(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse("chat_api"), "{", content_type="application/json").status_code, 400)

    def test_chat_rejects_oversized_payload(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse("chat_api"), "x" * 4097, content_type="application/json").status_code, 413)

    def test_chat_rejects_arithmetic_without_inventory_lookup(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("chat_api"), json.dumps({"question": "4+4 stock"}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"], "unsupported")

    def test_photo_upload_requires_image(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse("document_upload"), {"kind": "ETIQUETA"}).status_code, 400)
        self.assertFalse(PhotoDocument.objects.exists())

    def test_photo_upload_rejects_unknown_document_type(self):
        self.client.force_login(self.owner)
        image = SimpleUploadedFile("photo.png", b"invalid", content_type="image/png")
        self.assertEqual(self.client.post(reverse("document_upload"), {"kind": "FACTURA", "image": image}).status_code, 400)
        self.assertFalse(PhotoDocument.objects.exists())

    def test_photo_upload_rejects_corrupt_image(self):
        self.client.force_login(self.owner)
        image = SimpleUploadedFile("photo.png", b"not-a-picture", content_type="image/png")
        self.assertEqual(self.client.post(reverse("document_upload"), {"kind": "ETIQUETA", "image": image}).status_code, 400)
        self.assertFalse(PhotoDocument.objects.exists())

    def test_sensor_rejects_no_token(self):
        response = self.client.post(reverse("sensor_cycle_ingest"), json.dumps(self._cycle()), content_type="application/json")
        self.assertEqual(response.status_code, 401)
        self.assertFalse(SensorReading.objects.exists())

    def test_sensor_rejects_wrong_token(self):
        response = self._send_cycle(self._cycle(), token="wrong-token")
        self.assertEqual(response.status_code, 401)
        self.assertFalse(SensorReading.objects.exists())

    def test_sensor_rejects_negative_temperature(self):
        response = self._send_cycle(dict(self._cycle(), temperatura_c=-1))
        self.assertEqual(response.status_code, 422)
        self.assertFalse(SensorReading.objects.exists())

    def test_sensor_rejects_humidity_above_range(self):
        response = self._send_cycle(dict(self._cycle(), humedad_pct=100))
        self.assertEqual(response.status_code, 422)
        self.assertFalse(SensorReading.objects.exists())

    def test_sensor_rejects_boolean_as_temperature(self):
        response = self._send_cycle(dict(self._cycle(), temperatura_c=True))
        self.assertEqual(response.status_code, 422)
        self.assertFalse(SensorReading.objects.exists())

    def test_sensor_rejects_unknown_json_field(self):
        response = self._send_cycle(dict(self._cycle(), admin=True))
        self.assertEqual(response.status_code, 422)
        self.assertFalse(SensorReading.objects.exists())

    def _cycle(self):
        return {"version": 1, "ciclo_id": str(uuid.uuid4()), "estado": "VALIDO",
                "muestras_validas": 4, "temperatura_c": 25, "humedad_pct": 60}

    def _send_cycle(self, payload, token=None):
        return self.client.post(reverse("sensor_cycle_ingest"), json.dumps(payload), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token or self.token}")

    def test_csrf_blocks_manual_movement(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.employee)
        response = browser.post(reverse("movement_new"), {"type": "COMPRA", "presentation": self.presentation.pk,
            "quantity": "5", "source": self.location.pk})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(MovementDraft.objects.exists())

    def test_csrf_blocks_product_creation(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        response = browser.post(reverse("product_new"), {"code": "HACK", "name": "Hack"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Product.objects.filter(code="HACK").exists())

    def test_csrf_blocks_device_deactivation(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        response = browser.post(reverse("device_toggle", args=[self.device.pk]))
        self.assertEqual(response.status_code, 403)
        self.device.refresh_from_db()
        self.assertTrue(self.device.active)

    def test_csrf_blocks_chat_api(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        response = browser.post(reverse("chat_api"), json.dumps({"question": "stock"}), content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_csrf_blocks_photo_upload(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        response = browser.post(reverse("document_upload"), {"kind": "ETIQUETA"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(PhotoDocument.objects.exists())


OWNER_PAGE_CONTROLS = {
    "monitoring": ('id="device-select"', 'id="sensor-chart"', 'id="chat-launcher"'),
    "alert_list": ("Episodios activos", "Avisos recibidos", "Estado de correos"),
    "document_new": ('type="file"', "Subir y revisar"),
    "catalog_admin": ("Productos", "Presentaciones", "Ubicaciones"),
    "equivalence_list": ("Equivalencias", "Acción"),
    "device_list": ("Dispositivos", "Desactivar"),
    "alert_rules": ("Umbrales", "button-small"),
    "alert_recipients": ("Destinatarios", "button-small"),
    "user_list": ("Usuarios", "button-small"),
    "conversion_new": ("modal-backdrop", "Revisar conversión"),
    "presentation_new": ("modal-backdrop", "Guardar presentación"),
    "location_rename": ("modal-backdrop", "Guardar nombre"),
}


def _owner_controls_test(markers):
    def test(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse(self._testMethodName.removeprefix("test_owner_controls_")))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for marker in markers:
            self.assertIn(marker, html)
    return test


for _route, _markers in OWNER_PAGE_CONTROLS.items():
    setattr(BoundaryAndControlsTests, f"test_owner_controls_{_route}", _owner_controls_test(_markers))
