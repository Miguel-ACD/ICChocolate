import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from inventory.models import Equivalence, Location, Movement, MovementDraft, MovementLine, Presentation, Product, Stock, UserProfile
from inventory.phase2 import (cancel_draft, confirm_draft, convert_presentation, create_draft,
                              create_equivalence, deactivate_equivalence, edit_draft, reverse_movement)
from inventory.services import InventoryError, register_movement


class Phase2Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.owner = users.objects.create_user(username="phase2-owner@example.test", password="strong-test-pass-1")
        cls.employee = users.objects.create_user(username="phase2-employee@example.test", password="strong-test-pass-2")
        cls.other = users.objects.create_user(username="phase2-other@example.test", password="strong-test-pass-3")
        UserProfile.objects.create(user=cls.owner, role="DUENO")
        UserProfile.objects.create(user=cls.employee, role="EMPLEADO")
        UserProfile.objects.create(user=cls.other, role="EMPLEADO")
        cls.product = Product.objects.create(code="P2-CHOC", name="Chocolate")
        cls.box = Presentation.objects.create(product=cls.product, code="P2-BOX", name="Caja de 12", unit_description="Caja de doce barras", content_value=1200, content_unit="G")
        cls.bar = Presentation.objects.create(product=cls.product, code="P2-BAR", name="Barra", unit_description="Barra de 100 g", content_value=100, content_unit="G")
        cls.other_product = Product.objects.create(code="P2-OTHER", name="Otro")
        cls.other_presentation = Presentation.objects.create(product=cls.other_product, code="P2-OTHER-1", name="Otro", unit_description="Una", content_value=100, content_unit="G")
        cls.store = Location.objects.create(code="P2-STORE", name="Almacén")
        cls.display = Location.objects.create(code="P2-DISPLAY", name="Display")

    def stock(self, presentation, location=None):
        return Stock.objects.filter(presentation=presentation, location=location or self.store).values_list("quantity", flat=True).first() or 0

    def buy(self, presentation=None, quantity=5):
        return register_movement(user=self.employee, type_="COMPRA", presentation_id=(presentation or self.box).pk,
                                 quantity=quantity, source_id=self.store.pk)

    def rule(self):
        return create_equivalence(user=self.owner, source_id=self.box.pk, target_id=self.bar.pk,
                                  source_units=1, target_units=12)

    def test_equivalence_requires_owner_same_product_exact_content_and_direction(self):
        with self.assertRaises(InventoryError):
            create_equivalence(user=self.employee, source_id=self.box.pk, target_id=self.bar.pk, source_units=1, target_units=12)
        for target, target_units in ((self.bar, 11), (self.other_presentation, 12)):
            with self.subTest(target=target.code), self.assertRaises(InventoryError):
                create_equivalence(user=self.owner, source_id=self.box.pk, target_id=target.pk,
                                   source_units=1, target_units=target_units)
        rule = self.rule()
        self.assertTrue(rule.active)
        self.assertFalse(Equivalence.objects.filter(source=self.bar, target=self.box).exists())
        with self.assertRaises(InventoryError):
            self.rule()

    def test_conversion_keeps_content_and_ledger_in_one_location(self):
        rule = self.rule()
        self.buy()
        key = uuid.uuid4()
        first = convert_presentation(user=self.employee, equivalence_id=rule.pk, multiples=1,
                                     location_id=self.store.pk, idempotency_key=key)
        again = convert_presentation(user=self.employee, equivalence_id=rule.pk, multiples=1,
                                     location_id=self.store.pk, idempotency_key=key)
        self.assertEqual(first.pk, again.pk)
        self.assertEqual((self.stock(self.box), self.stock(self.bar)), (4, 12))
        self.assertEqual(first.equivalence_snapshot["target_units"], 12)
        self.assertEqual(sorted(first.lines.values_list("delta", flat=True)), [-1, 12])
        for presentation in (self.box, self.bar):
            self.assertEqual(self.stock(presentation), sum(MovementLine.objects.filter(
                presentation=presentation, location=self.store).values_list("delta", flat=True)))
        with self.assertRaises(InventoryError):
            convert_presentation(user=self.employee, equivalence_id=rule.pk, multiples=2,
                                 location_id=self.store.pk, idempotency_key=key)

    def test_conversion_insufficient_stock_and_failure_on_second_line_rollback(self):
        rule = self.rule()
        self.buy(quantity=1)
        before = Movement.objects.count()
        with self.assertRaisesMessage(InventoryError, "Stock insuficiente"):
            convert_presentation(user=self.employee, equivalence_id=rule.pk, multiples=2, location_id=self.store.pk)
        self.assertEqual(Movement.objects.count(), before)
        self.assertEqual((self.stock(self.box), self.stock(self.bar)), (1, 0))
        real_create = MovementLine.objects.create
        calls = 0
        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Fallo de prueba al guardar el segundo detalle")
            return real_create(*args, **kwargs)
        with patch("inventory.phase2.MovementLine.objects.create", side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                convert_presentation(user=self.employee, equivalence_id=rule.pk, multiples=1, location_id=self.store.pk)
        self.assertEqual(Movement.objects.count(), before)
        self.assertEqual((self.stock(self.box), self.stock(self.bar)), (1, 0))

    def test_deactivated_rule_keeps_history_and_cannot_be_used_again(self):
        rule = self.rule()
        self.buy(quantity=1)
        movement = convert_presentation(user=self.employee, equivalence_id=rule.pk, multiples=1, location_id=self.store.pk)
        deactivate_equivalence(user=self.owner, equivalence_id=rule.pk)
        movement.refresh_from_db()
        self.assertEqual(movement.equivalence_snapshot["source_units"], 1)
        with self.assertRaises(InventoryError):
            convert_presentation(user=self.employee, equivalence_id=rule.pk, multiples=1, location_id=self.store.pk)
        self.assertEqual((self.stock(self.box), self.stock(self.bar)), (0, 12))

    def test_reversal_is_owner_only_traced_and_exactly_once(self):
        self.buy(presentation=self.bar, quantity=10)
        sale = register_movement(user=self.employee, type_="VENTA", presentation_id=self.bar.pk,
                                 quantity=4, source_id=self.store.pk)
        with self.assertRaises(InventoryError):
            reverse_movement(user=self.employee, movement_id=sale.pk, reason="Venta equivocada")
        key = uuid.uuid4()
        reversal = reverse_movement(user=self.owner, movement_id=sale.pk, reason="Venta equivocada", idempotency_key=key)
        self.assertEqual(reversal.pk, reverse_movement(user=self.owner, movement_id=sale.pk, reason="Venta equivocada", idempotency_key=key).pk)
        self.assertEqual(reversal.reversal_of_id, sale.pk)
        self.assertEqual(self.stock(self.bar), 10)
        self.assertEqual(reversal.lines.get().delta, 4)
        with self.assertRaises(InventoryError):
            reverse_movement(user=self.owner, movement_id=sale.pk, reason="Otra vez")
        with self.assertRaises(InventoryError):
            reverse_movement(user=self.owner, movement_id=reversal.pk, reason="No permitido")
        self.assertEqual(Movement.objects.count(), 3)

    def test_reversal_rejects_negative_balance_without_partial_write(self):
        purchase = self.buy(presentation=self.bar, quantity=4)
        register_movement(user=self.employee, type_="VENTA", presentation_id=self.bar.pk,
                          quantity=4, source_id=self.store.pk)
        before = Movement.objects.count()
        with self.assertRaisesMessage(InventoryError, "Stock insuficiente"):
            reverse_movement(user=self.owner, movement_id=purchase.pk, reason="Compra errónea")
        self.assertEqual(Movement.objects.count(), before)
        self.assertEqual(self.stock(self.bar), 0)

    def test_draft_edit_version_cancel_and_owner_confirmation(self):
        draft = create_draft(user=self.employee, type_="COMPRA", presentation_id=self.bar.pk,
                             quantity=2, source_id=self.store.pk)
        self.assertEqual(self.stock(self.bar), 0)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse("draft_cancel", args=[draft.pk]), {"version": 1}).status_code, 403)
        with self.assertRaises(InventoryError):
            edit_draft(user=self.other, draft_id=draft.pk, expected_version=1, type_="COMPRA",
                       presentation_id=self.bar.pk, quantity=4, source_id=self.store.pk)
        updated = edit_draft(user=self.employee, draft_id=draft.pk, expected_version=1, type_="COMPRA",
                             presentation_id=self.bar.pk, quantity=3, source_id=self.store.pk)
        self.assertEqual(updated.version, 2)
        with self.assertRaises(InventoryError):
            confirm_draft(user=self.owner, draft_id=draft.pk, expected_version=1)
        movement = confirm_draft(user=self.owner, draft_id=draft.pk, expected_version=2)
        self.assertEqual(movement.pk, confirm_draft(user=self.owner, draft_id=draft.pk, expected_version=2).pk)
        self.assertEqual(self.stock(self.bar), 3)
        draft.refresh_from_db()
        self.assertEqual(draft.status, MovementDraft.Status.CONFIRMED)
        self.assertEqual(draft.created_by, self.employee)
        self.assertEqual(movement.created_by, self.employee)
        self.assertEqual(movement.confirmed_by, self.owner)
        other_draft = create_draft(user=self.employee, type_="VENTA", presentation_id=self.bar.pk,
                                   quantity=1, source_id=self.store.pk)
        cancel_draft(user=self.employee, draft_id=other_draft.pk, expected_version=1)
        with self.assertRaises(InventoryError):
            confirm_draft(user=self.employee, draft_id=other_draft.pk, expected_version=1)
        self.assertEqual(self.stock(self.bar), 3)

    def test_web_conversion_reversal_and_permissions(self):
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get(reverse("equivalence_new")).status_code, 403)
        self.assertEqual(self.client.post(reverse("equivalence_disable", args=[999])).status_code, 403)
        self.assertEqual(self.client.get(reverse("reversal_new", args=[uuid.uuid4()])).status_code, 403)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("equivalence_new"), {
            "source": self.box.pk, "target": self.bar.pk, "source_units": 1, "target_units": 12})
        self.assertRedirects(response, reverse("equivalence_list"))
        rule = Equivalence.objects.get()
        self.buy(quantity=1)
        self.client.force_login(self.employee)
        response = self.client.post(reverse("conversion_new"), {"equivalence": rule.pk, "multiples": 1, "location": self.store.pk})
        self.assertRedirects(response, reverse("movement_confirm"))
        self.assertEqual(self.stock(self.bar), 0)
        self.assertRedirects(self.client.post(reverse("movement_confirm")), reverse("movement_history"))
        self.assertEqual((self.stock(self.box), self.stock(self.bar)), (0, 12))
        self.client.force_login(self.owner)
        conversion = Movement.objects.get(type="CONVERSION")
        response = self.client.post(reverse("reversal_new", args=[conversion.pk]), {"reason": "Se cerró mal la caja"})
        self.assertRedirects(response, reverse("movement_confirm"))
        self.assertRedirects(self.client.post(reverse("movement_confirm")), reverse("movement_history"))
        self.assertEqual((self.stock(self.box), self.stock(self.bar)), (1, 0))
        self.assertEqual(Movement.objects.filter(type="REVERSO").count(), 1)

    def test_location_rename_preserves_movement_snapshot(self):
        self.buy(presentation=self.bar, quantity=1)
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get(reverse("location_rename")).status_code, 403)
        self.client.force_login(self.owner)
        self.assertRedirects(self.client.post(reverse("location_rename"), {
            "location": self.store.pk, "name": "Nueva zona"}), reverse("inventory"))
        self.assertEqual(self.store.pk, Location.objects.get(name="Nueva zona").pk)
        self.assertEqual(MovementLine.objects.get().location_snapshot, "Almacén")

    def test_web_draft_edit_stale_version_and_cancel(self):
        self.client.force_login(self.employee)
        self.assertRedirects(self.client.post(reverse("movement_new"), {
            "type": "COMPRA", "presentation": self.bar.pk, "quantity": 2, "source": self.store.pk,
        }), reverse("movement_confirm"))
        draft_id = self.client.session["pending_draft_id"]
        self.assertEqual(self.stock(self.bar), 0)
        self.assertRedirects(self.client.post(reverse("draft_edit", args=[draft_id]), {
            "version": 1, "type": "COMPRA", "presentation": self.bar.pk, "quantity": 3,
            "source": self.store.pk, "destination": "", "reason": "",
        }), reverse("movement_confirm_id", args=[draft_id]))
        stale = self.client.post(reverse("movement_confirm_id", args=[draft_id]), {"version": 1})
        self.assertEqual(stale.status_code, 200)
        self.assertEqual(self.stock(self.bar), 0)
        self.assertRedirects(self.client.post(reverse("movement_confirm_id", args=[draft_id]), {"version": 2}),
                             reverse("movement_history"))
        self.assertEqual(self.stock(self.bar), 3)
        self.assertEqual(Movement.objects.count(), 1)
        self.assertRedirects(self.client.post(reverse("movement_new"), {
            "type": "VENTA", "presentation": self.bar.pk, "quantity": 1, "source": self.store.pk,
        }), reverse("movement_confirm"))
        cancel_id = self.client.session["pending_draft_id"]
        self.assertRedirects(self.client.post(reverse("draft_cancel", args=[cancel_id]), {"version": 1}), reverse("draft_list"))
        self.assertEqual(self.stock(self.bar), 3)
        self.assertEqual(MovementDraft.objects.get(pk=cancel_id).status, "CANCELADO")

    def test_catalog_edit_permissions_stock_guard_and_history(self):
        purchase = self.buy(presentation=self.bar, quantity=2)
        self.client.force_login(self.employee)
        for name, arg in (("catalog_admin", None), ("product_edit", self.product.pk),
                          ("presentation_edit", self.bar.pk), ("location_edit", self.store.pk)):
            url = reverse(name, args=[arg] if arg else None)
            self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse("product_edit", args=[self.product.pk]), {
            "name": "Nuevo nombre", "description": "", "active": "",
        }).status_code, 200)
        self.assertEqual(self.client.post(reverse("presentation_edit", args=[self.bar.pk]), {
            "name": "Nuevo nombre", "unit_description": "Barra", "active": "",
        }).status_code, 200)
        self.assertEqual(self.client.post(reverse("location_edit", args=[self.store.pk]), {
            "name": "Nuevo nombre", "active": "",
        }).status_code, 200)
        self.assertRedirects(self.client.post(reverse("presentation_edit", args=[self.bar.pk]), {
            "name": "Barra renombrada", "unit_description": "Barra de 100 g", "active": "on",
        }), reverse("catalog_admin"))
        self.bar.refresh_from_db()
        self.assertEqual(self.bar.content_value, 100)
        self.assertEqual(self.bar.content_unit, "G")
        self.assertIn("Barra", purchase.lines.get().presentation_snapshot)
        self.assertNotIn("renombrada", purchase.lines.get().presentation_snapshot)
        self.assertEqual(self.stock(self.bar), 2)


    def test_user_management_preserves_history_and_blocks_employee(self):
        self.client.force_login(self.employee)
        for name in ("user_list", "user_new"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("user_new"), {
            "email": "new-worker@example.test", "alias": "Nueva persona", "role": "EMPLEADO",
            "password1": "fresh-demo-password-2026", "password2": "fresh-demo-password-2026",
        })
        self.assertRedirects(response, reverse("user_list"))
        profile = UserProfile.objects.get(user__username="new-worker@example.test")
        self.assertEqual(profile.role, UserProfile.Role.EMPLOYEE)
        self.client.force_login(profile.user)
        self.assertEqual(self.client.get(reverse("inventory")).status_code, 200)
        self.assertEqual(self.client.get(reverse("user_edit", args=[profile.pk])).status_code, 403)
        movement = register_movement(user=profile.user, type_="COMPRA", presentation_id=self.bar.pk,
                                     quantity=1, source_id=self.store.pk)
        self.client.force_login(self.owner)
        self.assertRedirects(self.client.post(reverse("user_edit", args=[profile.pk]), {
            "alias": "Nueva persona", "role": "EMPLEADO", "active": "",
        }), reverse("user_list"))
        profile.user.refresh_from_db()
        self.assertFalse(profile.user.is_active)
        self.assertTrue(Movement.objects.filter(pk=movement.pk, created_by=profile.user).exists())
        self.client.logout()
        self.assertEqual(self.client.post(reverse("login"), {
            "username": "new-worker@example.test", "password": "fresh-demo-password-2026",
        }).status_code, 200)

    def test_owner_cannot_disable_self_or_change_presentation_meaning(self):
        self.buy(presentation=self.bar, quantity=1)
        self.client.force_login(self.owner)
        owner_profile = self.owner.profile
        response = self.client.post(reverse("user_edit", args=[owner_profile.pk]), {
            "alias": "Dueño", "role": "EMPLEADO", "active": "",
        })
        self.assertEqual(response.status_code, 200)
        owner_profile.refresh_from_db()
        self.assertEqual(owner_profile.role, UserProfile.Role.OWNER)
        self.assertTrue(get_user_model().objects.get(pk=self.owner.pk).is_active)
        response = self.client.post(reverse("presentation_edit", args=[self.bar.pk]), {
            "name": "Barra", "unit_description": "Ahora 200 g", "active": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.bar.refresh_from_db()
        self.assertEqual(self.bar.unit_description, "Barra de 100 g")



class ConcurrentConversions(TransactionTestCase):
    def test_two_conversions_cannot_spend_same_box(self):
        if connection.vendor != "postgresql":
            self.skipTest("La concurrencia se verifica en PostgreSQL.")
        users = get_user_model()
        owner = users.objects.create_user(username="concurrent-owner@example.test", password="strong-test-pass-1")
        employee = users.objects.create_user(username="concurrent-employee@example.test", password="strong-test-pass-2")
        UserProfile.objects.create(user=owner, role="DUENO")
        UserProfile.objects.create(user=employee, role="EMPLEADO")
        product = Product.objects.create(code="C-CONCURRENT", name="Chocolate")
        box = Presentation.objects.create(product=product, code="C-BOX", name="Caja", unit_description="Caja", content_value=1200, content_unit="G")
        bar = Presentation.objects.create(product=product, code="C-BAR", name="Barra", unit_description="Barra", content_value=100, content_unit="G")
        location = Location.objects.create(code="C-LOC", name="Almacén")
        rule = create_equivalence(user=owner, source_id=box.pk, target_id=bar.pk, source_units=1, target_units=12)
        register_movement(user=employee, type_="COMPRA", presentation_id=box.pk, quantity=1, source_id=location.pk)
        def attempt():
            try:
                movement = convert_presentation(user=employee, equivalence_id=rule.pk, multiples=1, location_id=location.pk)
                return str(movement.pk)
            except InventoryError:
                return "RECHAZADA"
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(sum(result != "RECHAZADA" for result in results), 1)
        self.assertEqual(Stock.objects.get(presentation=box, location=location).quantity, 0)
        self.assertEqual(Stock.objects.get(presentation=bar, location=location).quantity, 12)
        self.assertEqual(Movement.objects.filter(type="CONVERSION").count(), 1)
