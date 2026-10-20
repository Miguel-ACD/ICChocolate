import uuid
from concurrent.futures import ThreadPoolExecutor
from django.contrib.auth import get_user_model
from django.db import connection, connections, close_old_connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from inventory.models import Location, Movement, Presentation, Product, Stock, UserProfile
from inventory.services import InventoryError, register_movement


class InventoryFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(username="owner@example.test", password="safe-demo-pass-123")
        cls.employee = user_model.objects.create_user(username="employee@example.test", password="safe-demo-pass-456")
        UserProfile.objects.create(user=cls.owner, role=UserProfile.Role.OWNER)
        UserProfile.objects.create(user=cls.employee, role=UserProfile.Role.EMPLOYEE)
        cls.product = Product.objects.create(code="BAR", name="Chocolate en barra")
        cls.presentation = Presentation.objects.create(product=cls.product, code="BAR-100", name="Barra", unit_description="Una barra de 100 g", content_value=100, content_unit="G")
        cls.warehouse = Location.objects.create(code="WH", name="Almacén")
        cls.display = Location.objects.create(code="DIS", name="Display")

    def move(self, type_="COMPRA", quantity=5, user=None, **kwargs):
        return register_movement(user=user or self.employee, type_=type_, presentation_id=self.presentation.pk,
                                 quantity=quantity, source_id=self.warehouse.pk, **kwargs)

    def quantity(self, location):
        return Stock.objects.get(presentation=self.presentation, location=location).quantity

    def test_purchase_sale_transfer_and_history(self):
        self.move(quantity=8)
        self.move(type_="VENTA", quantity=2)
        movement = self.move(type_="TRASLADO", quantity=3, destination_id=self.display.pk)
        self.assertEqual(self.quantity(self.warehouse), 3)
        self.assertEqual(self.quantity(self.display), 3)
        self.assertEqual(sum(line.delta for line in movement.lines.all()), 0)
        self.assertEqual(Movement.objects.count(), 3)

    def test_insufficient_sale_rolls_back_everything(self):
        self.move(quantity=2)
        with self.assertRaisesMessage(InventoryError, "Stock insuficiente"):
            self.move(type_="VENTA", quantity=3)
        self.assertEqual(self.quantity(self.warehouse), 2)
        self.assertEqual(Movement.objects.count(), 1)

    def test_transfer_with_insufficient_stock_is_atomic(self):
        self.move(quantity=2)
        with self.assertRaises(InventoryError):
            self.move(type_="TRASLADO", quantity=3, destination_id=self.display.pk)
        self.assertEqual(self.quantity(self.warehouse), 2)
        self.assertFalse(Stock.objects.filter(presentation=self.presentation, location=self.display).exists())
        self.assertEqual(Movement.objects.count(), 1)

    def test_idempotency_key_applies_only_once(self):
        key = uuid.uuid4()
        first = self.move(quantity=4, idempotency_key=key)
        second = self.move(quantity=4, idempotency_key=key)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(self.quantity(self.warehouse), 4)
        with self.assertRaises(InventoryError):
            self.move(quantity=5, idempotency_key=key)

    def test_invalid_or_incomplete_operations(self):
        for kwargs in [
            {"quantity": 0}, {"quantity": -1},
            {"type_": "MERMA", "quantity": 1},
            {"type_": "TRASLADO", "quantity": 1, "destination_id": self.warehouse.pk},
            {"type_": "COMPRA", "quantity": 1, "destination_id": self.display.pk},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(InventoryError):
                self.move(**kwargs)
        self.assertEqual(Movement.objects.count(), 0)

    def test_owner_only_initial_and_product_creation(self):
        with self.assertRaises(InventoryError):
            self.move(type_="INICIAL", quantity=2)
        self.move(type_="INICIAL", quantity=2, user=self.owner)
        self.client.force_login(self.employee)
        response = self.client.post(reverse("product_new"), {
            "code": "P2", "name": "Otro", "presentation_code": "P2-1",
            "presentation_name": "Unidad", "unit_description": "Una unidad", "content_value": "1", "content_unit": "PIEZA"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Product.objects.filter(code="P2").exists())
        self.client.force_login(self.owner)
        response = self.client.post(reverse("product_new"), {
            "code": "P2", "name": "Otro", "presentation_code": "P2-1",
            "presentation_name": "Unidad", "unit_description": "Una unidad", "content_value": "1", "content_unit": "PIEZA"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Product.objects.filter(code="P2").exists())

    def test_web_requires_review_and_rejects_incomplete_form(self):
        self.client.force_login(self.employee)
        incomplete = self.client.post(reverse("movement_new"), {"type": "VENTA", "quantity": "1"})
        self.assertEqual(incomplete.status_code, 200)
        self.assertEqual(Movement.objects.count(), 0)
        valid = self.client.post(reverse("movement_new"), {
            "type": "COMPRA", "presentation": self.presentation.pk,
            "quantity": "3", "source": self.warehouse.pk})
        self.assertRedirects(valid, reverse("movement_confirm"))
        self.assertEqual(Movement.objects.count(), 0)
        confirmed = self.client.post(reverse("movement_confirm"))
        self.assertRedirects(confirmed, reverse("movement_history"))
        self.assertEqual(self.quantity(self.warehouse), 3)

    def test_login_and_persistence_across_requests(self):
        response = self.client.post(reverse("login"), {"username": "employee@example.test", "password": "safe-demo-pass-456"})
        self.assertRedirects(response, reverse("dashboard"))
        self.move(quantity=6)
        response = self.client.get(reverse("inventory"))
        self.assertContains(response, "6")
        self.assertEqual(self.quantity(self.warehouse), 6)

    def test_user_without_profile_cannot_log_in(self):
        get_user_model().objects.create_user(username="unassigned@example.test", password="safe-demo-pass-789")
        response = self.client.post(reverse("login"), {"username": "unassigned@example.test", "password": "safe-demo-pass-789"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_employee_cannot_create_location(self):
        self.client.force_login(self.employee)
        response = self.client.post(reverse("location_new"), {"code": "KITCHEN", "name": "Cocina"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Location.objects.filter(code="KITCHEN").exists())

    def test_alias_is_saved_and_used_for_existing_movements(self):
        self.move(quantity=4)
        self.client.force_login(self.employee)
        dashboard = self.client.get(reverse("dashboard"))
        self.assertContains(dashboard, f'href="{reverse("alias_settings")}"')
        alias_form = self.client.get(reverse("alias_settings"))
        self.assertContains(alias_form, 'class="modal-card alias-modal"')
        self.assertContains(alias_form, 'aria-modal="true"')
        response = self.client.post(reverse("alias_settings"), {
            "alias": "  Ana   Repostera  ", "role": UserProfile.Role.OWNER, "user": self.owner.pk,
        })
        self.assertRedirects(response, reverse("dashboard"))
        self.employee.profile.refresh_from_db()
        self.assertEqual(self.employee.profile.alias, "Ana Repostera")
        self.assertEqual(self.employee.profile.role, UserProfile.Role.EMPLOYEE)
        for page in ("dashboard", "movement_history"):
            rendered = self.client.get(reverse(page))
            self.assertContains(rendered, "Ana Repostera")
            self.assertNotIn("employee@example.test", rendered.content.decode().split("<table", 1)[1])
            self.assertContains(rendered, "<th>Fecha</th>", html=True)
            self.assertContains(rendered, "<th>Hora</th>", html=True)

    def test_alias_validation_does_not_change_database(self):
        self.client.force_login(self.employee)
        response = self.client.post(reverse("alias_settings"), {"alias": " "})
        self.assertEqual(response.status_code, 200)
        self.employee.profile.refresh_from_db()
        self.assertEqual(self.employee.profile.alias, "Usuario")

    def test_product_and_movement_forms_open_as_modals(self):
        self.client.force_login(self.employee)
        movement = self.client.get(reverse("movement_new"))
        self.assertContains(movement, 'role="dialog"')
        self.assertContains(movement, 'aria-modal="true"')
        self.assertContains(movement, 'class="form-stack compact-form"')
        self.assertNotContains(movement, 'Nuevo movimiento</a>')
        incomplete = self.client.post(reverse("movement_new"), {"type": "VENTA"})
        self.assertContains(incomplete, 'role="dialog"')
        self.assertEqual(Movement.objects.count(), 0)
        self.client.force_login(self.owner)
        product = self.client.get(reverse("product_new"))
        self.assertContains(product, 'role="dialog"')
        self.assertContains(product, 'class="form-stack compact-form"')
        invalid = self.client.post(reverse("product_new"), {"code": "INCOMPLETE"})
        self.assertContains(invalid, 'role="dialog"')
        self.assertFalse(Product.objects.filter(code="INCOMPLETE").exists())

    def test_location_form_opens_as_modal_and_validates_before_saving(self):
        self.client.force_login(self.owner)
        inventory = self.client.get(reverse("inventory"))
        self.assertContains(inventory, f'href="{reverse("location_new")}" data-modal-open')
        form = self.client.get(reverse("location_new"))
        self.assertContains(form, 'class="modal-card location-modal"')
        self.assertContains(form, 'aria-modal="true"')
        invalid = self.client.post(reverse("location_new"), {"code": "BOX-1"})
        self.assertContains(invalid, 'role="dialog"')
        self.assertFalse(Location.objects.filter(code="BOX-1").exists())
        valid = self.client.post(reverse("location_new"), {"code": "BOX-1", "name": "Caja de chocolate"})
        self.assertRedirects(valid, reverse("inventory"))
        self.assertTrue(Location.objects.filter(code="BOX-1").exists())

    def test_inventory_has_numbered_pages_and_preserves_search(self):
        for index in range(6):
            product = Product.objects.create(code=f"EXTRA-{index}", name=f"Extra {index}")
            presentation = Presentation.objects.create(
                product=product, code=f"EXTRA-{index}-1", name="Unidad",
                unit_description="Una unidad", content_value=1, content_unit="PIEZA")
            Stock.objects.create(presentation=presentation, location=self.warehouse, quantity=index + 1)
        self.client.force_login(self.employee)
        first = self.client.get(reverse("inventory"), {"q": "Extra"})
        self.assertEqual(len(first.context["stocks"]), 4)
        self.assertContains(first, "?q=Extra&amp;page=2")
        second = self.client.get(reverse("inventory"), {"q": "Extra", "page": 2})
        self.assertEqual(len(second.context["stocks"]), 2)
        self.assertEqual(second.context["page_obj"].number, 2)
        self.assertNotContains(second, "Extra 0")
        self.assertContains(second, "Extra 5")

    def test_dashboard_limits_recent_movements_and_history_uses_numbered_pages(self):
        for _ in range(33):
            self.move(quantity=1)
        self.client.force_login(self.employee)
        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(len(dashboard.context["recent"]), 30)
        self.assertContains(dashboard, "Últimos 30")
        first = self.client.get(reverse("movement_history"))
        self.assertEqual(len(first.context["movements"]), 4)
        self.assertContains(first, '?page=2')
        last = self.client.get(reverse("movement_history"), {"page": 9})
        self.assertEqual(len(last.context["movements"]), 1)
        self.assertEqual(last.context["page_obj"].number, 9)


class ConcurrentSaleTests(TransactionTestCase):
    def test_two_sales_cannot_spend_the_same_unit(self):
        if connection.vendor != "postgresql":
            self.skipTest("Esta comprobación de bloqueo se ejecuta con PostgreSQL.")
        user = get_user_model().objects.create_user(username="concurrent@example.test", password="safe-demo-pass-123")
        UserProfile.objects.create(user=user, role=UserProfile.Role.EMPLOYEE)
        product = Product.objects.create(code="CONCURRENT", name="Producto de prueba")
        presentation = Presentation.objects.create(product=product, code="CONCURRENT-1", name="Unidad", unit_description="Una unidad", content_value=1, content_unit="PIEZA")
        location = Location.objects.create(code="TEST", name="Prueba")
        register_movement(user=user, type_="COMPRA", presentation_id=presentation.pk, quantity=1, source_id=location.pk)

        def sell():
            close_old_connections()
            try:
                register_movement(user=user, type_="VENTA", presentation_id=presentation.pk,
                                  quantity=1, source_id=location.pk)
                return "ok"
            except InventoryError:
                return "rejected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: sell(), range(2)))
        self.assertCountEqual(outcomes, ["ok", "rejected"])
        self.assertEqual(Stock.objects.get(presentation=presentation, location=location).quantity, 0)
        self.assertEqual(Movement.objects.filter(type="VENTA").count(), 1)
