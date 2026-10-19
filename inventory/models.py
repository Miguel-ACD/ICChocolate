import uuid
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class UserProfile(models.Model):
    class Role(models.TextChoices):
        OWNER = "DUENO", "Dueño"
        EMPLOYEE = "EMPLEADO", "Empleado"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="profile")
    role = models.CharField(max_length=8, choices=Role.choices)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


class Product(models.Model):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Presentation(models.Model):
    class Unit(models.TextChoices):
        GRAM = "G", "g"
        MILLILITER = "ML", "ml"
        PIECE = "PIEZA", "pieza"

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="presentations")
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=150)
    unit_description = models.CharField(max_length=200)
    content_value = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0.001)])
    content_unit = models.CharField(max_length=5, choices=Unit.choices)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["product__name", "name"]
        constraints = [models.CheckConstraint(condition=Q(content_value__gt=0), name="presentation_positive_content")]

    def __str__(self):
        return f"{self.product.name} · {self.name}"


class Location(models.Model):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=100)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Stock(models.Model):
    presentation = models.ForeignKey(Presentation, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    quantity = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["presentation", "location"], name="unique_stock_position"),
            models.CheckConstraint(condition=Q(quantity__gte=0), name="stock_nonnegative"),
        ]


class Movement(models.Model):
    class Type(models.TextChoices):
        INITIAL = "INICIAL", "Carga inicial"
        PURCHASE = "COMPRA", "Compra / entrada"
        SALE = "VENTA", "Venta"
        CONSUMPTION = "CONSUMO", "Consumo"
        WASTE = "MERMA", "Merma"
        TRANSFER = "TRASLADO", "Traslado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.UUIDField(unique=True)
    request_hash = models.CharField(max_length=64)
    type = models.CharField(max_length=10, choices=Type.choices)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class MovementLine(models.Model):
    movement = models.ForeignKey(Movement, on_delete=models.PROTECT, related_name="lines")
    presentation = models.ForeignKey(Presentation, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    delta = models.BigIntegerField()
    presentation_snapshot = models.CharField(max_length=250)
    location_snapshot = models.CharField(max_length=100)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~Q(delta=0), name="movement_line_nonzero"),
            models.UniqueConstraint(fields=["movement", "presentation", "location"], name="unique_movement_position"),
        ]
