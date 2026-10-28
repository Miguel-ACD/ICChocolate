from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from inventory.local_ocr import propose_catalog_codes
from inventory.models import Movement, PhotoDocument, Stock, UserProfile
from inventory.photo_service import PhotoError, prepare_photo
from scripts.evaluate_gemini_vision import score as score_vision


def image_upload(format_="PNG", size=(2000, 1000)):
    image = Image.new("RGB", size, "white")
    output = BytesIO()
    image.save(output, format_)
    return SimpleUploadedFile("foto.png", output.getvalue(), content_type="image/png")


class PhotoFoundationTests(SimpleTestCase):
    def test_png_is_reencoded_as_bounded_jpeg(self):
        result = prepare_photo(image_upload())
        self.assertEqual((result.width, result.height), (1600, 800))
        self.assertEqual(len(result.sha256), 64)
        with Image.open(BytesIO(result.jpeg)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertFalse(image.getexif())

    def test_empty_corrupt_and_oversize_rejected(self):
        for data in (b"", b"not an image", b"x" * (5 * 1024 * 1024 + 1)):
            with self.subTest(size=len(data)), self.assertRaises(PhotoError):
                prepare_photo(SimpleUploadedFile("photo.jpg", data))

    def test_large_pixel_count_rejected(self):
        with self.assertRaisesRegex(PhotoError, "20 megapíxeles"):
            prepare_photo(image_upload(size=(5000, 5000)))

    def test_label_does_not_invent_purchase_quantity(self):
        proposals = propose_catalog_codes("POLVO-1000  CONTENIDO NETO 1 kg", {"POLVO-1000", "POLVO-100"})
        self.assertEqual(proposals, [{"code": "POLVO-1000", "quantity": None}])

    def test_receipt_with_multiple_codes_and_explicit_quantities(self):
        text = "02 BARRA-100  Barra chocolate\n01 CAJA-BARRA-12\n03 POLVO-100\n01 POLVO-1000"
        result = propose_catalog_codes(text, {"BARRA-100", "CAJA-BARRA-12", "POLVO-100", "POLVO-1000"})
        self.assertEqual({item["code"]: item["quantity"] for item in result},
                         {"BARRA-100": 2, "CAJA-BARRA-12": 1, "POLVO-100": 3, "POLVO-1000": 1})

    def test_vision_score_separates_receipt_quantity_and_label_hallucination(self):
        receipt = score_vision([{"codigo": "BARRA-100", "cantidad": 2}], {"BARRA-100": 2})
        self.assertEqual((receipt["codes_correct"], receipt["receipt_quantities_correct"]), (1, 1))
        label = score_vision([{"codigo": "POLVO-100", "cantidad": 100}], {"POLVO-100": None})
        self.assertEqual(label["label_quantity_violations"], 1)
        self.assertEqual(label["receipt_quantities_expected"], 0)


class PhotoUploadIntegrationTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media.cleanup)
        self.user = get_user_model().objects.create_user(username="photo@example.local", password="safe-test-password")
        UserProfile.objects.create(user=self.user, role=UserProfile.Role.EMPLOYEE)

    def test_authenticated_upload_and_private_retrieval_without_stock_change(self):
        before_movements = Movement.objects.count()
        before_stocks = Stock.objects.count()
        denied = self.client.post(reverse("document_upload"), {"kind": "ETIQUETA", "image": image_upload()})
        self.assertEqual(denied.status_code, 302)
        self.client.force_login(self.user)
        response = self.client.post(reverse("document_upload"), {"kind": "ETIQUETA", "image": image_upload()})
        self.assertEqual(response.status_code, 201)
        document = PhotoDocument.objects.get(pk=response.json()["id"])
        self.assertEqual(document.uploaded_by, self.user)
        self.assertEqual((document.width, document.height), (1600, 800))
        self.assertNotIn("foto.png", document.image.name)
        image_response = self.client.get(reverse("document_image", args=[document.pk]))
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response["Cache-Control"], "private, no-store")
        self.assertTrue(b"".join(image_response.streaming_content).startswith(b"\xff\xd8"))
        self.client.logout()
        self.assertEqual(self.client.get(reverse("document_image", args=[document.pk])).status_code, 302)
        self.assertEqual(Movement.objects.count(), before_movements)
        self.assertEqual(Stock.objects.count(), before_stocks)

    def test_invalid_image_does_not_leave_document(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("document_upload"), {
            "kind": "BOLETA", "image": SimpleUploadedFile("bad.jpg", b"not an image")})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PhotoDocument.objects.exists())
