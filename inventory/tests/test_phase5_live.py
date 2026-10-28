"""Opt-in Gemini check against a real phone photo; always uses a temporary test DB."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from inventory.models import Movement, PhotoDocument, Presentation, Product, Stock, UserProfile
from inventory.photo_service import prepare_photo
from inventory.vision import VisionUnavailable, extract_document


PHOTO = Path(__file__).resolve().parents[2] / "materials" / "fase5_pruebas" / "fotos_celular" / "1-1000128881.jpg"


@skipUnless(os.environ.get("PHASE5_LIVE_GEMINI") == "1", "Prueba externa opcional")
class LiveGeminiPhotoTests(TestCase):
    def test_real_api_proposes_four_receipt_lines_without_creating_stock(self):
        if not os.environ.get("GEMINI_API_KEY"):
            self.skipTest("Falta clave privada de Gemini")
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            user = get_user_model().objects.create_user(username="vision-live@example.local")
            UserProfile.objects.create(user=user, role=UserProfile.Role.EMPLOYEE)
            product = Product.objects.create(code="CHOC", name="Chocolate")
            for code in ("BARRA-100", "CAJA-BARRA-12", "POLVO-100", "POLVO-1000"):
                Presentation.objects.create(product=product, code=code, name=code,
                                            unit_description="demo", content_value=100, content_unit="G")
            with PHOTO.open("rb") as source:
                prepared = prepare_photo(source)
            document = PhotoDocument(uploaded_by=user, kind=PhotoDocument.Kind.RECEIPT,
                                     sha256=prepared.sha256, byte_size=len(prepared.jpeg),
                                     width=prepared.width, height=prepared.height)
            document.image.save("boleta_demo.jpg", ContentFile(prepared.jpeg), save=True)
            try:
                items = extract_document(document)
            except VisionUnavailable as exc:
                if "cuota gratuita" in str(exc) or "HTTP 503" in str(exc) or "conectar" in str(exc):
                    self.skipTest(f"Proveedor temporalmente no disponible: {exc}")
                raise
            found = {item["code"]: item["quantity"] for item in items}
            self.assertEqual(found, {"BARRA-100": 2, "CAJA-BARRA-12": 1,
                                     "POLVO-100": 3, "POLVO-1000": 1})
            self.assertEqual(document.extraction_status, "LISTO")
            self.assertEqual(Movement.objects.count(), 0)
            self.assertEqual(Stock.objects.count(), 0)
