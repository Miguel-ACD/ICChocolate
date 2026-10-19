"""All inventory writes pass through this service, in one database transaction."""
import hashlib
import json
import uuid
from django.db import IntegrityError, transaction
from .models import Location, Movement, MovementLine, Presentation, Stock, UserProfile


class InventoryError(ValueError):
    pass


def is_owner(user):
    return user.is_authenticated and UserProfile.objects.filter(user=user, role=UserProfile.Role.OWNER).exists()


def _canonical(type_, presentation_id, quantity, source_id, destination_id, reason):
    return {
        "type": type_, "presentation_id": int(presentation_id), "quantity": int(quantity),
        "source_id": int(source_id), "destination_id": int(destination_id) if destination_id else None,
        "reason": reason.strip(),
    }


def register_movement(*, user, type_, presentation_id, quantity, source_id,
                      destination_id=None, reason="", idempotency_key=None):
    """Confirm one complete manual operation. Repeating its key cannot apply stock twice."""
    if not user.is_authenticated or not UserProfile.objects.filter(user=user).exists():
        raise InventoryError("Usuario sin perfil autorizado.")
    if type_ not in Movement.Type.values:
        raise InventoryError("Tipo de movimiento inválido.")
    if type_ == Movement.Type.INITIAL and not is_owner(user):
        raise InventoryError("Solo el dueño puede registrar la carga inicial.")
    try:
        data = _canonical(type_, presentation_id, quantity, source_id, destination_id, reason)
        key = uuid.UUID(str(idempotency_key)) if idempotency_key else uuid.uuid4()
    except (ValueError, TypeError, OverflowError):
        raise InventoryError("La operación contiene datos inválidos.") from None
    if data["quantity"] <= 0 or data["quantity"] > 9_000_000_000_000_000_000:
        raise InventoryError("La cantidad debe ser un entero positivo.")
    if type_ == Movement.Type.TRANSFER:
        if not data["destination_id"] or data["destination_id"] == data["source_id"]:
            raise InventoryError("El traslado requiere una ubicación de destino diferente.")
    elif data["destination_id"] is not None:
        raise InventoryError("Esta operación no admite ubicación de destino.")
    if type_ in (Movement.Type.CONSUMPTION, Movement.Type.WASTE) and not data["reason"]:
        raise InventoryError("El motivo es obligatorio para consumo y merma.")
    request_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    previous = Movement.objects.filter(idempotency_key=key).first()
    if previous:
        if previous.request_hash != request_hash or previous.created_by_id != user.pk:
            raise InventoryError("La clave de esta operación ya corresponde a otro movimiento.")
        return previous

    try:
        with transaction.atomic():
            # This lock serializes every write to a presentation, including new stock rows.
            presentation = Presentation.objects.select_for_update().select_related("product").get(
                pk=data["presentation_id"], active=True, product__active=True)
            source = Location.objects.get(pk=data["source_id"], active=True)
            destination = None
            if data["destination_id"]:
                destination = Location.objects.get(pk=data["destination_id"], active=True)
            q = data["quantity"]
            deltas = [(source, q if type_ in (Movement.Type.INITIAL, Movement.Type.PURCHASE) else -q)]
            if destination:
                deltas.append((destination, q))
            movement = Movement.objects.create(
                idempotency_key=key, request_hash=request_hash, type=type_,
                created_by=user, reason=data["reason"])
            for location, delta in sorted(deltas, key=lambda item: item[0].pk):
                stock, _ = Stock.objects.get_or_create(presentation=presentation, location=location)
                stock = Stock.objects.select_for_update().get(pk=stock.pk)
                new_quantity = stock.quantity + delta
                if new_quantity < 0:
                    raise InventoryError(f"Stock insuficiente en {location.name}: disponible {stock.quantity}.")
                stock.quantity = new_quantity
                stock.save(update_fields=["quantity"])
                MovementLine.objects.create(
                    movement=movement, presentation=presentation, location=location, delta=delta,
                    presentation_snapshot=f"{presentation.product.name} · {presentation.name} ({presentation.unit_description})",
                    location_snapshot=location.name)
            return movement
    except (Presentation.DoesNotExist, Location.DoesNotExist):
        raise InventoryError("La presentación o ubicación no existe o está inactiva.") from None
    except IntegrityError:
        previous = Movement.objects.filter(idempotency_key=key).first()
        if previous and previous.request_hash == request_hash and previous.created_by_id == user.pk:
            return previous
        raise InventoryError("La operación no pudo completarse; inténtala de nuevo.") from None
