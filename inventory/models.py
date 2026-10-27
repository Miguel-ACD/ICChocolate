import uuid
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class UserProfile(models.Model):
    class Role(models.TextChoices):
        OWNER = "DUENO", "Dueño"
        EMPLOYEE = "EMPLEADO", "Empleado"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="profile")
    role = models.CharField(max_length=8, choices=Role.choices)
    alias = models.CharField(max_length=40, default="Usuario")

    def __str__(self):
        return f"{self.alias} ({self.get_role_display()})"


class Product(models.Model):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("code"), name="product_code_ci_unique")]

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
        constraints = [
            models.CheckConstraint(condition=Q(content_value__gt=0), name="presentation_positive_content"),
            models.UniqueConstraint(Lower("code"), name="presentation_code_ci_unique"),
        ]

    def __str__(self):
        return f"{self.product.name} · {self.name}"


class Equivalence(models.Model):
    """Directed, immutable content-equivalent conversion rule."""

    source = models.ForeignKey(Presentation, on_delete=models.PROTECT, related_name="conversion_sources")
    target = models.ForeignKey(Presentation, on_delete=models.PROTECT, related_name="conversion_targets")
    source_units = models.BigIntegerField(validators=[MinValueValidator(1)])
    target_units = models.BigIntegerField(validators=[MinValueValidator(1)])
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(source_units__gt=0), name="equivalence_source_positive"),
            models.CheckConstraint(condition=Q(target_units__gt=0), name="equivalence_target_positive"),
            models.CheckConstraint(condition=~Q(source=models.F("target")), name="equivalence_distinct_presentations"),
            models.UniqueConstraint(fields=["source", "target"], condition=Q(active=True), name="unique_active_equivalence_pair"),
        ]

    def __str__(self):
        return f"{self.source.code} {self.source_units} → {self.target.code} {self.target_units}"


class Location(models.Model):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=100)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("code"), name="location_code_ci_unique")]

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
        CONVERSION = "CONVERSION", "Conversión"
        REVERSAL = "REVERSO", "Reverso"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.UUIDField(unique=True)
    request_hash = models.CharField(max_length=64)
    type = models.CharField(max_length=10, choices=Type.choices)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="confirmed_movements")
    equivalence = models.ForeignKey(Equivalence, on_delete=models.PROTECT, null=True, blank=True)
    equivalence_snapshot = models.JSONField(null=True, blank=True)
    reversal_of = models.OneToOneField("self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversal")
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class MovementDraft(models.Model):
    class Status(models.TextChoices):
        DRAFT = "BORRADOR", "Borrador"
        CONFIRMED = "CONFIRMADO", "Confirmado"
        CANCELLED = "CANCELADO", "Cancelado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    type = models.CharField(max_length=10, choices=Movement.Type.choices)
    presentation = models.ForeignKey(Presentation, on_delete=models.PROTECT, null=True, blank=True)
    quantity = models.BigIntegerField()
    source = models.ForeignKey(Location, on_delete=models.PROTECT)
    destination = models.ForeignKey(Location, on_delete=models.PROTECT, null=True, blank=True, related_name="destination_drafts")
    equivalence = models.ForeignKey(Equivalence, on_delete=models.PROTECT, null=True, blank=True)
    reversal_of = models.ForeignKey(Movement, on_delete=models.PROTECT, null=True, blank=True, related_name="reversal_drafts")
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveIntegerField(default=1)
    movement = models.OneToOneField(Movement, on_delete=models.PROTECT, null=True, blank=True, related_name="source_draft")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


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


class SensorReading(models.Model):
    """One averaged DHT11 transmission; reading_id makes HTTP retries harmless."""

    reading_id = models.UUIDField(unique=True)
    temperature_c = models.DecimalField(max_digits=4, decimal_places=2)
    humidity_percent = models.DecimalField(max_digits=5, decimal_places=2)
    sample_count = models.PositiveSmallIntegerField()
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-received_at", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(temperature_c__gte=0, temperature_c__lte=50), name="dht_temperature_range"),
            models.CheckConstraint(condition=Q(humidity_percent__gte=20, humidity_percent__lte=90), name="dht_humidity_range"),
            models.CheckConstraint(condition=Q(sample_count__gte=1, sample_count__lte=4), name="dht_sample_count_range"),
        ]
