"""Twenty-five attempts to skip screens, corrupt names and forge stock changes."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory.models import Location, Movement, MovementDraft, Presentation, Product, Stock, UserProfile


class FlowBreakerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(username="flow-breaker@test.local", password="safe-password-123")
        UserProfile.objects.create(user=cls.owner, role="DUENO")
        cls.product = Product.objects.create(code="FLOW-QA", name="Producto real")
        cls.presentation = Presentation.objects.create(
            product=cls.product, code="FLOW-100", name="Barra real",
            unit_description="Una barra", content_value=100, content_unit="G")
        cls.location = Location.objects.create(code="FLOW-ALM", name="Almacén real")

    def setUp(self):
        self.client.force_login(self.owner)

    def unchanged(self):
        self.assertEqual(Movement.objects.count(), 0)
        self.assertEqual(MovementDraft.objects.count(), 0)
        self.assertEqual(Stock.objects.count(), 0)
        self.assertEqual(Product.objects.get(pk=self.product.pk).name, "Producto real")
        self.assertEqual(Presentation.objects.get(pk=self.presentation.pk).name, "Barra real")
        self.assertEqual(Location.objects.get(pk=self.location.pk).name, "Almacén real")


BAD_SESSION_IDS = ["not-a-uuid", "00000000", {}, [], 5, "00000000-0000-0000-0000-zzzzzzzzzzzz"]
for index, value in enumerate(BAD_SESSION_IDS):
    def test_session(self, value=value):
        session = self.client.session
        session["pending_draft_id"] = value
        session["pending_draft_version"] = 1
        session.save()
        response = self.client.post(reverse("movement_confirm"), {"version": "1"})
        self.assertRedirects(response, reverse("movement_new"))
        self.assertNotIn("pending_draft_id", self.client.session)
        self.unchanged()
    setattr(FlowBreakerTests, f"test_flow_forged_session_{index:02d}", test_session)


BAD_NAMES = ["", " ", "\t\n", "123456", "!!!", "\u200b", "\r\n"]
for index, value in enumerate(BAD_NAMES):
    def test_rename(self, value=value):
        response = self.client.post(reverse("location_rename"), {"location": self.location.pk, "name": value})
        self.assertEqual(response.status_code, 200)
        self.unchanged()
    setattr(FlowBreakerTests, f"test_flow_bad_rename_{index:02d}", test_rename)


EDIT_CASES = [
    ("product_edit", "product", {"name": "", "description": "", "active": "on"}),
    ("product_edit", "product", {"name": "999", "description": "", "active": "on"}),
    ("product_edit", "product", {"name": "\u200b", "description": "", "active": "on"}),
    ("presentation_edit", "presentation", {"name": "", "unit_description": "Una barra", "active": "on"}),
    ("presentation_edit", "presentation", {"name": "123", "unit_description": "Una barra", "active": "on"}),
    ("location_edit", "location", {"name": "", "active": "on"}),
    ("location_edit", "location", {"name": "456", "active": "on"}),
]
for index, (route, object_name, payload) in enumerate(EDIT_CASES):
    def test_edit(self, route=route, object_name=object_name, payload=payload):
        target = getattr(self, object_name)
        response = self.client.post(reverse(route, args=[target.pk]), payload)
        self.assertEqual(response.status_code, 200)
        self.unchanged()
    setattr(FlowBreakerTests, f"test_flow_bad_edit_{index:02d}", test_edit)


BAD_MOVEMENTS = [
    {"quantity": "-1"}, {"quantity": "0"}, {"quantity": "1.5"},
    {"quantity": "one"}, {"type": "DELETE_ALL"},
]
for index, changes in enumerate(BAD_MOVEMENTS):
    def test_movement(self, changes=changes):
        payload = {"type": "COMPRA", "presentation": self.presentation.pk,
                   "quantity": "1", "source": self.location.pk, "destination": "", "reason": ""}
        payload.update(changes)
        response = self.client.post(reverse("movement_new"), payload)
        self.assertEqual(response.status_code, 200)
        self.unchanged()
    setattr(FlowBreakerTests, f"test_flow_bad_movement_{index:02d}", test_movement)
