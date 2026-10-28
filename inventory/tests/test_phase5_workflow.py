from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from inventory.models import Location, Movement, PhotoDocument, Presentation, Product, Stock, UserProfile
from inventory.photo_workflow import confirm_photo_group
from inventory.services import InventoryError
from inventory.vision import VisionUnavailable, normalize_items


PHOTO_FIXTURES = Path(__file__).resolve().parents[2] / "materials" / "fase5_pruebas" / "fotos_celular"


def photo(color="white"):
    output = BytesIO()
    Image.new("RGB", (80, 60), color).save(output, "PNG")
    return SimpleUploadedFile("camera.png", output.getvalue(), content_type="image/png")


class VisionValidationTests(SimpleTestCase):
    def test_label_quantity_is_always_discarded_and_unknown_code_is_reviewable(self):
        items = normalize_items([{"codigo": "BARRA-100", "cantidad": 100},
                                 {"codigo": "DESCONOCIDO", "cantidad": 2}],
                                PhotoDocument.Kind.LABEL, {"BARRA-100": 7})
        self.assertEqual(items[0]["quantity"], None)
        self.assertEqual(items[1]["presentation_id"], None)

    def test_invalid_response_is_rejected(self):
        with self.assertRaises(VisionUnavailable):
            normalize_items({"items": []}, PhotoDocument.Kind.RECEIPT, {})


class PhotoWorkflowTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.media_settings = override_settings(MEDIA_ROOT=self.media.name)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.addCleanup(self.media.cleanup)
        self.user = get_user_model().objects.create_user(username="photos@example.local", password="test-password")
        UserProfile.objects.create(user=self.user, role=UserProfile.Role.EMPLOYEE)
        self.other = get_user_model().objects.create_user(username="other@example.local", password="test-password")
        UserProfile.objects.create(user=self.other, role=UserProfile.Role.EMPLOYEE)
        self.product = Product.objects.create(code="CHOC", name="Chocolate")
        self.bar = Presentation.objects.create(product=self.product, code="BARRA-100", name="Barra",
                                               unit_description="100 g", content_value=100, content_unit="G")
        self.box = Presentation.objects.create(product=self.product, code="CAJA-BARRA-12", name="Caja",
                                               unit_description="12 barras", content_value=1200, content_unit="G")
        self.location = Location.objects.create(code="ALM", name="Almacén")
        self.client.force_login(self.user)

    def upload(self, kind="BOLETA", color="white"):
        response = self.client.post(reverse("document_upload"), {"kind": kind, "image": photo(color)})
        self.assertEqual(response.status_code, 201)
        return PhotoDocument.objects.get(pk=response.json()["id"])

    def test_multiline_purchase_and_sale_with_photo_and_idempotency(self):
        receipt = self.upload()
        group = receipt.group_id
        args = dict(user=self.user, group_id=group, type_=Movement.Type.PURCHASE,
                    location_id=self.location.pk, rows=[
                        {"presentation_id": self.bar.pk, "quantity": 2},
                        {"presentation_id": self.box.pk, "quantity": 1}])
        self.assertEqual(Movement.objects.count(), 0)
        first = confirm_photo_group(**args)
        self.assertEqual(first.lines.count(), 2)
        self.assertEqual(Stock.objects.get(presentation=self.bar).quantity, 2)
        self.assertEqual(Stock.objects.get(presentation=self.box).quantity, 1)
        self.assertEqual(confirm_photo_group(**args).pk, first.pk)
        self.assertEqual(Movement.objects.count(), 1)
        sale_photo = self.upload(color="blue")
        confirm_photo_group(user=self.user, group_id=sale_photo.group_id, type_=Movement.Type.SALE,
                            location_id=self.location.pk, rows=[{"presentation_id": self.bar.pk, "quantity": 1}])
        self.assertEqual(Stock.objects.get(presentation=self.bar).quantity, 1)
        self.assertEqual(Movement.objects.count(), 2)

    def test_sale_without_stock_rolls_back_every_line_and_photo(self):
        doc = self.upload()
        with self.assertRaisesRegex(InventoryError, "Stock insuficiente"):
            confirm_photo_group(user=self.user, group_id=doc.group_id, type_=Movement.Type.SALE,
                location_id=self.location.pk, rows=[{"presentation_id": self.bar.pk, "quantity": 1}])
        self.assertEqual(Movement.objects.count(), 0)
        doc.refresh_from_db()
        self.assertIsNone(doc.movement_id)

    def test_confirmed_exact_duplicate_photo_is_blocked(self):
        one = self.upload()
        args = dict(user=self.user, type_=Movement.Type.PURCHASE, location_id=self.location.pk,
                    rows=[{"presentation_id": self.bar.pk, "quantity": 1}])
        confirm_photo_group(group_id=one.group_id, **args)
        two = self.upload()
        with self.assertRaisesRegex(InventoryError, "ya se utilizó"):
            confirm_photo_group(group_id=two.group_id, **args)
        self.assertEqual(Movement.objects.count(), 1)

    def test_foreign_user_cannot_view_or_confirm(self):
        doc = self.upload()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("document_image", args=[doc.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("document_review", args=[doc.group_id])).status_code, 403)
        with self.assertRaisesRegex(InventoryError, "otra cuenta"):
            confirm_photo_group(user=self.other, group_id=doc.group_id, type_=Movement.Type.PURCHASE,
                location_id=self.location.pk, rows=[{"presentation_id": self.bar.pk, "quantity": 1}])

    def test_mobile_form_with_gemini_failure_uses_manual_review(self):
        with patch("inventory.document_views.extract_document", side_effect=VisionUnavailable("Cuota gratuita agotada")):
            response = self.client.post(reverse("document_new"), {"kind": "BOLETA", "image": photo()})
        self.assertEqual(response.status_code, 302)
        doc = PhotoDocument.objects.get(uploaded_by=self.user)
        self.assertEqual(doc.extraction_status, "ERROR")
        page = self.client.get(reverse("document_review", args=[doc.group_id]))
        self.assertContains(page, "Cuota gratuita agotada")
        self.assertContains(page, "capture=\"environment\"")
        response = self.client.post(reverse("document_review", args=[doc.group_id]), {
            "action": "confirm", "type": "COMPRA", "location": self.location.pk,
            "row_count": "1", "presentation_0": self.bar.pk, "quantity_0": "3"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Stock.objects.get(presentation=self.bar).quantity, 3)
        self.assertEqual(PhotoDocument.objects.get(pk=doc.pk).movement.confirmed_by, self.user)

    def test_multiple_photos_one_movement(self):
        first = self.upload(kind="BOLETA")
        with patch("inventory.document_views.extract_document", return_value=[]):
            response = self.client.post(reverse("document_review", args=[first.group_id]), {
                "action": "add", "kind": "ETIQUETA", "image": photo("green")})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PhotoDocument.objects.filter(group_id=first.group_id).count(), 2)
        movement = confirm_photo_group(user=self.user, group_id=first.group_id, type_=Movement.Type.PURCHASE,
            location_id=self.location.pk, rows=[{"presentation_id": self.bar.pk, "quantity": 1}])
        self.assertEqual(movement.photos.count(), 2)

    def test_actual_phone_receipt_upload_ai_proposals_and_reviewed_confirmation(self):
        for code, name, grams in [("POLVO-100", "Polvo bolsa", 100), ("POLVO-1000", "Polvo saco", 1000)]:
            Presentation.objects.create(product=self.product, code=code, name=name,
                                        unit_description=f"{grams} g", content_value=grams, content_unit="G")
        image_path = PHOTO_FIXTURES / "1-1000128881.jpg"
        self.assertTrue(image_path.exists())
        response_body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"items": [
            {"codigo": "BARRA-100", "cantidad": 2},
            {"codigo": "CAJA-BARRA-12", "cantidad": 1},
            {"codigo": "POLVO-100", "cantidad": 3},
            {"codigo": "POLVO-1000", "cantidad": 1},
        ]})}]}}]}
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, *args): return json.dumps(response_body).encode()
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-test-key"}), patch(
                "inventory.vision.urlopen", return_value=FakeResponse()) as call:
            with image_path.open("rb") as image:
                uploaded = SimpleUploadedFile(image_path.name, image.read(), content_type="image/jpeg")
            response = self.client.post(reverse("document_new"), {"kind": "BOLETA", "image": uploaded})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(call.call_count, 1)
        doc = PhotoDocument.objects.get(uploaded_by=self.user)
        self.assertEqual(doc.extraction_status, "LISTO")
        self.assertEqual(len(doc.extraction_items), 4)
        page = self.client.get(reverse("document_review", args=[doc.group_id]))
        self.assertContains(page, "BARRA-100")
        self.assertEqual(Movement.objects.count(), 0)
        rows = [("BARRA-100", 2), ("CAJA-BARRA-12", 1), ("POLVO-100", 3), ("POLVO-1000", 1)]
        post = {"action": "confirm", "type": "COMPRA", "location": self.location.pk, "row_count": "4"}
        for n, (code, qty) in enumerate(rows):
            post[f"presentation_{n}"] = Presentation.objects.get(code=code).pk
            post[f"quantity_{n}"] = qty
        self.assertEqual(self.client.post(reverse("document_review", args=[doc.group_id]), post).status_code, 302)
        self.assertEqual(Movement.objects.get().lines.count(), 4)
        self.assertEqual(Stock.objects.get(presentation__code="POLVO-100").quantity, 3)

    def test_invalid_row_or_duplicate_presentation_does_not_change_stock(self):
        doc = self.upload()
        for rows in ([{"presentation_id": self.bar.pk, "quantity": "1.5"}],
                     [{"presentation_id": self.bar.pk, "quantity": 1},
                      {"presentation_id": self.bar.pk, "quantity": 2}]):
            with self.assertRaises(InventoryError):
                confirm_photo_group(user=self.user, group_id=doc.group_id, type_=Movement.Type.PURCHASE,
                                    location_id=self.location.pk, rows=rows)
        self.assertEqual(Movement.objects.count(), 0)
