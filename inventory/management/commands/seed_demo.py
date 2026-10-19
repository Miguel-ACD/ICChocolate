"""Idempotent fictional catalog and two private demo accounts."""
import os
import uuid
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from inventory.models import Location, Presentation, Product, UserProfile
from inventory.services import register_movement


class Command(BaseCommand):
    help = "Create demo users and fictional stock once, with auditable initial movements."

    @transaction.atomic
    def handle(self, *args, **options):
        owner_email = os.getenv("DEMO_OWNER_EMAIL", "dueno@icchocolate.local")
        employee_email = os.getenv("DEMO_EMPLOYEE_EMAIL", "empleado@icchocolate.local")
        owner_password = os.getenv("DEMO_OWNER_PASSWORD")
        employee_password = os.getenv("DEMO_EMPLOYEE_PASSWORD")
        if not owner_password or not employee_password:
            raise CommandError("Configura DEMO_OWNER_PASSWORD y DEMO_EMPLOYEE_PASSWORD en .env.")
        user_model = get_user_model()
        owner, created = user_model.objects.get_or_create(username=owner_email, defaults={"email": owner_email, "first_name": "Dueño"})
        if created:
            owner.set_password(owner_password)
            owner.save(update_fields=["password"])
        employee, created = user_model.objects.get_or_create(username=employee_email, defaults={"email": employee_email, "first_name": "Empleado"})
        if created:
            employee.set_password(employee_password)
            employee.save(update_fields=["password"])
        UserProfile.objects.get_or_create(user=owner, defaults={"role": UserProfile.Role.OWNER})
        UserProfile.objects.get_or_create(user=employee, defaults={"role": UserProfile.Role.EMPLOYEE})
        warehouse, _ = Location.objects.get_or_create(code="ALMACEN", defaults={"name": "Almacén"})
        display, _ = Location.objects.get_or_create(code="DISPLAY", defaults={"name": "Display"})
        bar, _ = Product.objects.get_or_create(code="CHOC-BARRA", defaults={"name": "Chocolate en barra"})
        powder, _ = Product.objects.get_or_create(code="CHOC-POLVO", defaults={"name": "Chocolate en polvo"})
        chips, _ = Product.objects.get_or_create(code="CHOC-CHISPAS", defaults={"name": "Chispas de chocolate"})
        samples = [
            (bar, "BARRA-100", "Barra 100 g", "Una barra de 100 g", Decimal("100"), display, 24),
            (bar, "CAJA-BARRA-12", "Caja de 12 barras", "Una caja de 12 barras de 100 g", Decimal("1200"), warehouse, 5),
            (powder, "POLVO-1000", "Saco 1 kg", "Un saco de 1000 g", Decimal("1000"), warehouse, 3),
            (powder, "POLVO-100", "Bolsa 100 g", "Una bolsa de 100 g", Decimal("100"), display, 10),
            (chips, "CHISPAS-100", "Bolsa 100 g", "Una bolsa de 100 g", Decimal("100"), display, 15),
        ]
        for product, code, name, unit_description, content, location, quantity in samples:
            presentation, _ = Presentation.objects.get_or_create(code=code, defaults={
                "product": product, "name": name, "unit_description": unit_description,
                "content_value": content, "content_unit": Presentation.Unit.GRAM})
            register_movement(
                user=owner, type_="INICIAL", presentation_id=presentation.pk,
                quantity=quantity, source_id=location.pk,
                reason="Catálogo ficticio de demostración",
                idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f"icchocolate:seed:{code}"))
        self.stdout.write(self.style.SUCCESS("Demo lista: dos usuarios y cinco posiciones iniciales."))
