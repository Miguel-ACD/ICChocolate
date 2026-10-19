"""Black-box regressions for hostile inputs and complete web workflows."""
import random
import uuid
from concurrent.futures import ThreadPoolExecutor

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from inventory.models import Location, Movement, MovementLine, Presentation, Product, Stock, UserProfile
from inventory.services import InventoryError, register_movement


class WorkflowRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.owner = users.objects.create_user(username="owner@qa.test", password="strong-demo-password-1")
        cls.employee = users.objects.create_user(username="employee@qa.test", password="strong-demo-password-2")
        cls.other = users.objects.create_user(username="other@qa.test", password="strong-demo-password-3")
        UserProfile.objects.create(user=cls.owner, role="DUENO")
        UserProfile.objects.create(user=cls.employee, role="EMPLEADO")
        UserProfile.objects.create(user=cls.other, role="EMPLEADO")
        cls.product = Product.objects.create(code="QA-CHOC", name="Chocolate QA")
        cls.presentation = Presentation.objects.create(
            product=cls.product, code="QA-BARRA", name="Barra QA",
            unit_description="Una barra de 100 g", content_value=100, content_unit="G")
        cls.source = Location.objects.create(code="QA-ALM", name="Almacén QA")
        cls.target = Location.objects.create(code="QA-DIS", name="Display QA")

    def move(self, type_="COMPRA", quantity=1, user=None, **extra):
        return register_movement(user=user or self.employee, type_=type_,
                                 presentation_id=self.presentation.pk, quantity=quantity,
                                 source_id=self.source.pk, **extra)

    def form_data(self, **changes):
        data = {"type": "COMPRA", "presentation": self.presentation.pk,
                "quantity": "2", "source": self.source.pk, "destination": "", "reason": ""}
        data.update(changes)
        return data

    def test_manual_workflow_keeps_ledger_and_permissions(self):
        self.client.force_login(self.owner)
        product_response = self.client.post(reverse("product_new"), {
            "code": "NUEVO", "name": "Nuevo chocolate", "description": "Para QA",
            "presentation_code": "NUEVO-100", "presentation_name": "Barra 100 g",
            "unit_description": "Una barra", "content_value": "100", "content_unit": "G"})
        self.assertRedirects(product_response, reverse("inventory"))
        new_presentation = Presentation.objects.get(code="NUEVO-100")
        self.assertFalse(Stock.objects.filter(presentation=new_presentation).exists())
        self.client.force_login(self.employee)
        operations = [
            ("COMPRA", 8, self.source.pk, None, ""),
            ("VENTA", 2, self.source.pk, None, ""),
            ("CONSUMO", 1, self.source.pk, None, "Muestra de cocina"),
            ("MERMA", 1, self.source.pk, None, "Empaque roto"),
            ("TRASLADO", 3, self.source.pk, self.target.pk, ""),
        ]
        for kind, amount, source, target, reason in operations:
            with self.subTest(kind=kind):
                preview = self.client.post(reverse("movement_new"), self.form_data(
                    type=kind, quantity=str(amount), source=source,
                    destination=target or "", reason=reason))
                self.assertRedirects(preview, reverse("movement_confirm"))
                before = Movement.objects.count()
                self.assertEqual(self.client.get(reverse("movement_confirm")).status_code, 200)
                self.assertEqual(Movement.objects.count(), before)
                self.assertRedirects(self.client.post(reverse("movement_confirm")), reverse("movement_history"))
        self.assertEqual(Stock.objects.get(presentation=self.presentation, location=self.source).quantity, 1)
        self.assertEqual(Stock.objects.get(presentation=self.presentation, location=self.target).quantity, 3)
        self.assertEqual(Movement.objects.count(), 5)
        self.assertEqual(sum(MovementLine.objects.values_list("delta", flat=True)), 4)
        self.assertEqual(Movement.objects.filter(created_by=self.employee).count(), 5)

    def test_sale_at_zero_and_over_available_never_creates_history(self):
        for amount in (1, 10):
            with self.subTest(amount=amount), self.assertRaisesMessage(InventoryError, "Stock insuficiente"):
                self.move(type_="VENTA", quantity=amount)
        self.assertEqual(Movement.objects.count(), 0)
        self.assertEqual(Stock.objects.filter(presentation=self.presentation).count(), 0)

    def test_preview_becomes_stale_when_another_user_sells(self):
        self.move(quantity=2)
        self.client.force_login(self.employee)
        self.assertRedirects(self.client.post(reverse("movement_new"), self.form_data(type="VENTA")), reverse("movement_confirm"))
        self.move(type_="VENTA", quantity=1, user=self.other)
        response = self.client.post(reverse("movement_confirm"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stock insuficiente")
        self.assertEqual(Stock.objects.get(presentation=self.presentation, location=self.source).quantity, 1)
        self.assertEqual(Movement.objects.count(), 2)

    def test_preview_rechecks_inactive_catalog_and_location(self):
        self.client.force_login(self.employee)
        for entity in (self.presentation, self.source):
            with self.subTest(entity=entity):
                entity.active = True
                entity.save(update_fields=["active"])
                self.assertRedirects(self.client.post(reverse("movement_new"), self.form_data()), reverse("movement_confirm"))
                entity.active = False
                entity.save(update_fields=["active"])
                response = self.client.post(reverse("movement_confirm"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "inactiva")
                self.assertEqual(Movement.objects.count(), 0)
                entity.active = True
                entity.save(update_fields=["active"])

    def test_hostile_forms_cannot_enter_review(self):
        self.client.force_login(self.employee)
        bad = [
            {"type": "INICIAL"}, {"type": "BORRADO"}, {"presentation": "999999"},
            {"quantity": "0"}, {"quantity": "-4"}, {"quantity": "1.5"},
            {"source": "999999"}, {"type": "MERMA", "reason": "   "},
            {"type": "TRASLADO", "destination": ""},
            {"type": "TRASLADO", "destination": self.source.pk},
            {"type": "COMPRA", "destination": self.target.pk},
        ]
        for change in bad:
            with self.subTest(change=change):
                self.client.session.pop("pending_movement", None)
                response = self.client.post(reverse("movement_new"), self.form_data(**change))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(Movement.objects.count(), 0)

    def test_service_rejects_noninteger_and_malformed_inputs_without_writes(self):
        bad = [True, 1.5, "1.5", 0, -1, 9_000_000_000_000_000_001]
        for amount in bad:
            with self.subTest(amount=amount), self.assertRaises(InventoryError):
                self.move(quantity=amount)
        for reason in (None, 23, "x" * 501):
            with self.subTest(reason=reason), self.assertRaises(InventoryError):
                self.move(type_="MERMA", reason=reason)
        self.assertEqual(Movement.objects.count(), 0)

    def test_idempotency_key_cannot_be_reused_by_other_user(self):
        key = uuid.uuid4()
        first = self.move(quantity=3, idempotency_key=key)
        with self.assertRaises(InventoryError):
            self.move(quantity=3, user=self.other, idempotency_key=key)
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(first.created_by, self.employee)

    def test_deactivated_user_cannot_write_via_service(self):
        self.employee.is_active = False
        self.employee.save(update_fields=["is_active"])
        with self.assertRaisesMessage(InventoryError, "sin perfil autorizado"):
            self.move(quantity=2)
        self.assertEqual(Movement.objects.count(), 0)

    def test_missing_actor_cannot_write_via_service(self):
        with self.assertRaisesMessage(InventoryError, "sin perfil autorizado"):
            register_movement(user=None, type_="COMPRA", presentation_id=self.presentation.pk,
                              quantity=2, source_id=self.source.pk)
        self.assertEqual(Movement.objects.count(), 0)

    def test_double_web_confirmation_creates_only_one_movement(self):
        self.client.force_login(self.employee)
        self.client.post(reverse("movement_new"), self.form_data())
        self.client.post(reverse("movement_confirm"))
        second = self.client.post(reverse("movement_confirm"))
        self.assertRedirects(second, reverse("movement_new"))
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(Stock.objects.get(presentation=self.presentation, location=self.source).quantity, 2)

    def test_catalog_creation_is_atomic_and_duplicate_codes_are_rejected(self):
        self.client.force_login(self.owner)
        payload = {"code": "QA-CHOC", "name": "Duplicado", "presentation_code": "NEW-1",
                   "presentation_name": "Unidad", "unit_description": "Una", "content_value": "1", "content_unit": "PIEZA"}
        response = self.client.post(reverse("product_new"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Presentation.objects.filter(code="NEW-1").exists())
        payload["code"] = "NEW"
        payload["presentation_code"] = "qa-barra"
        response = self.client.post(reverse("product_new"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(code="NEW").exists())

    def test_database_enforces_case_insensitive_catalog_codes(self):
        for model, code, defaults in (
            (Product, "qa-choc", {"name": "Duplicado"}),
            (Presentation, "qa-barra", {"product": self.product, "name": "Duplicado",
                                        "unit_description": "Una", "content_value": 1, "content_unit": "PIEZA"}),
            (Location, "qa-alm", {"name": "Duplicada"}),
        ):
            with self.subTest(model=model.__name__), self.assertRaises(IntegrityError), transaction.atomic():
                model.objects.create(code=code, **defaults)

    def test_anonymous_and_profileless_users_cannot_access_private_pages(self):
        for name in ("dashboard", "inventory", "movement_new", "movement_confirm",
                     "movement_history", "product_new", "location_new"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 302)
        unassigned = get_user_model().objects.create_user(username="noprofile@qa.test", password="strong-demo-password")
        self.client.force_login(unassigned)
        for name in ("dashboard", "inventory", "movement_history"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_employee_cannot_open_owner_pages_or_post_catalog_changes(self):
        self.client.force_login(self.employee)
        for name, data in (("product_new", {"code": "FORBIDDEN"}),
                           ("location_new", {"code": "FORBIDDEN", "name": "Forbidden"})):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
                self.assertEqual(self.client.post(reverse(name), data).status_code, 403)
        self.assertFalse(Product.objects.filter(code="FORBIDDEN").exists())
        self.assertFalse(Location.objects.filter(code="FORBIDDEN").exists())

    def test_csrf_blocks_state_changes_without_token(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.employee)
        response = browser.post(reverse("movement_new"), self.form_data())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Movement.objects.count(), 0)

    def test_history_uses_snapshots_after_names_change(self):
        self.move(quantity=2)
        self.presentation.name = "Nombre cambiado"
        self.presentation.save(update_fields=["name"])
        self.source.name = "Zona cambiada"
        self.source.save(update_fields=["name"])
        self.client.force_login(self.employee)
        page = self.client.get(reverse("movement_history"))
        self.assertContains(page, "Barra QA")
        self.assertContains(page, "Almacén QA")
        self.assertNotContains(page, "Nombre cambiado")

    def test_database_rejects_direct_negative_stock(self):
        self.move(quantity=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Stock.objects.filter(presentation=self.presentation, location=self.source).update(quantity=-1)
        self.assertEqual(Stock.objects.get(presentation=self.presentation, location=self.source).quantity, 1)

    def test_deterministic_random_sequence_matches_confirmed_ledger(self):
        rng = random.Random(20261019)
        self.move(quantity=25)
        for _ in range(70):
            balances = {loc.pk: (Stock.objects.filter(presentation=self.presentation, location=loc)
                                 .values_list("quantity", flat=True).first() or 0)
                        for loc in (self.source, self.target)}
            kind = rng.choice(["COMPRA", "VENTA", "MERMA", "TRASLADO"])
            origin = rng.choice([self.source, self.target])
            amount = rng.randint(1, 6)
            destination = self.target if origin == self.source else self.source
            kwargs = {"user": self.employee, "type_": kind, "presentation_id": self.presentation.pk,
                      "source_id": origin.pk, "quantity": amount,
                      "reason": "Prueba" if kind == "MERMA" else ""}
            if kind == "TRASLADO":
                kwargs["destination_id"] = destination.pk
            before = Movement.objects.count()
            try:
                register_movement(**kwargs)
            except InventoryError:
                self.assertLess(balances[origin.pk], amount)
                self.assertEqual(Movement.objects.count(), before)
            ledger = {loc.pk: sum(MovementLine.objects.filter(presentation=self.presentation, location=loc)
                                  .values_list("delta", flat=True)) for loc in (self.source, self.target)}
            actual = {loc.pk: (Stock.objects.filter(presentation=self.presentation, location=loc)
                               .values_list("quantity", flat=True).first() or 0)
                      for loc in (self.source, self.target)}
            self.assertEqual(actual, ledger)
            self.assertTrue(all(value >= 0 for value in actual.values()))


class ConcurrentIdempotencyTests(TransactionTestCase):
    def test_two_retries_with_same_key_apply_once(self):
        if connection.vendor != "postgresql":
            self.skipTest("El bloqueo concurrente se verifica en PostgreSQL.")
        user = get_user_model().objects.create_user(username="retry@qa.test", password="strong-demo-password")
        UserProfile.objects.create(user=user, role="EMPLEADO")
        product = Product.objects.create(code="RETRY", name="Prueba de reintento")
        presentation = Presentation.objects.create(product=product, code="RETRY-1", name="Unidad", unit_description="Una unidad", content_value=1, content_unit="PIEZA")
        location = Location.objects.create(code="RETRY-LOC", name="Prueba")
        key = uuid.uuid4()

        def attempt():
            try:
                movement = register_movement(user=user, type_="COMPRA", presentation_id=presentation.pk,
                                             quantity=4, source_id=location.pk, idempotency_key=key)
                return movement.pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(Stock.objects.get(presentation=presentation, location=location).quantity, 4)
