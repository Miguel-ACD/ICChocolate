"""Atomic human confirmation of a photographed multi-line purchase or sale."""

import hashlib
import json
import uuid

from django.db import IntegrityError, transaction

from .models import Location, Movement, MovementLine, PhotoDocument, Presentation, Stock, UserProfile
from .services import InventoryError, _whole_number, is_owner


def confirm_photo_group(*, user, group_id, type_, location_id, rows):
    if not user or not user.is_authenticated or not user.is_active or not UserProfile.objects.filter(user=user).exists():
        raise InventoryError("Usuario sin perfil autorizado.")
    if type_ not in (Movement.Type.PURCHASE, Movement.Type.SALE):
        raise InventoryError("Solo se admite compra o venta con fotos.")
    try:
        group_id = uuid.UUID(str(group_id))
        location_id = _whole_number(location_id)
        cleaned = [(_whole_number(row["presentation_id"]), _whole_number(row["quantity"])) for row in rows]
    except (ValueError, TypeError, KeyError, OverflowError):
        raise InventoryError("Revisa la ubicación y todos los renglones.") from None
    if not cleaned or len(cleaned) > 40 or len({pk for pk, _ in cleaned}) != len(cleaned):
        raise InventoryError("Indica entre 1 y 40 presentaciones diferentes.")
    if any(not 0 < qty <= 9_000_000_000_000_000_000 for _, qty in cleaned):
        raise InventoryError("Cada cantidad debe ser un entero positivo.")
    cleaned.sort()
    canonical = {"type": type_, "location_id": location_id, "rows": cleaned, "group_id": str(group_id)}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    try:
        with transaction.atomic():
            docs = list(PhotoDocument.objects.select_for_update().filter(group_id=group_id).order_by("pk"))
            if not docs:
                raise InventoryError("No se encontraron fotos para esta operación.")
            if len(docs) > 8:
                raise InventoryError("El límite es de ocho fotos por operación.")
            if any(doc.uploaded_by_id != user.pk for doc in docs) and not is_owner(user):
                raise InventoryError("No puedes confirmar fotos de otra cuenta.")
            previous = Movement.objects.filter(idempotency_key=group_id).first()
            if previous:
                if previous.request_hash == digest and all(doc.movement_id == previous.pk for doc in docs):
                    return previous
                raise InventoryError("Esta operación ya fue confirmada con otros datos.")
            if any(doc.movement_id for doc in docs):
                raise InventoryError("Una foto de esta operación ya fue confirmada.")
            if len({doc.sha256 for doc in docs}) != len(docs) or PhotoDocument.objects.filter(
                    sha256__in=[doc.sha256 for doc in docs], movement__isnull=False).exists():
                raise InventoryError("Una de estas fotos ya se utilizó en un movimiento confirmado.")
            location = Location.objects.get(pk=location_id, active=True)
            presentations = list(Presentation.objects.select_for_update().select_related("product")
                                 .filter(pk__in=[pk for pk, _ in cleaned], active=True,
                                         product__active=True).order_by("pk"))
            if len(presentations) != len(cleaned):
                raise InventoryError("Una presentación ya no está disponible.")
            by_id = {p.pk: p for p in presentations}
            movement = Movement.objects.create(
                idempotency_key=group_id, request_hash=digest, type=type_,
                created_by=docs[0].uploaded_by, confirmed_by=user, reason="Registro revisado con fotografías")
            for presentation_id, quantity in cleaned:
                presentation = by_id[presentation_id]
                stock, _ = Stock.objects.get_or_create(presentation=presentation, location=location)
                stock = Stock.objects.select_for_update().get(pk=stock.pk)
                delta = quantity if type_ == Movement.Type.PURCHASE else -quantity
                if stock.quantity + delta < 0:
                    raise InventoryError(f"Stock insuficiente para {presentation.code}: disponible {stock.quantity}.")
                stock.quantity += delta
                stock.save(update_fields=["quantity"])
                MovementLine.objects.create(
                    movement=movement, presentation=presentation, location=location, delta=delta,
                    presentation_snapshot=f"{presentation.product.name} · {presentation.name} ({presentation.unit_description})",
                    location_snapshot=location.name)
            PhotoDocument.objects.filter(pk__in=[doc.pk for doc in docs]).update(movement=movement)
            return movement
    except Location.DoesNotExist:
        raise InventoryError("La ubicación no existe o está inactiva.") from None
    except IntegrityError:
        raise InventoryError("Una foto u operación ya fue utilizada; revisa el historial.") from None
