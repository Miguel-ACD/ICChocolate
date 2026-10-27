"""Phase 2: directed equivalences, atomic conversions, audited reversals and drafts."""
import hashlib
import json
import uuid
from django.db import IntegrityError, transaction
from .models import Equivalence, Location, Movement, MovementDraft, MovementLine, Presentation, Stock, UserProfile
from .services import InventoryError, _whole_number, is_owner, register_movement


def _actor(user):
    if (user is None or not getattr(user, "is_authenticated", False)
            or not getattr(user, "is_active", False)
            or not UserProfile.objects.filter(user=user).exists()):
        raise InventoryError("Usuario sin perfil autorizado.")


def _positive(value):
    try:
        number = _whole_number(value)
    except (ValueError, TypeError, OverflowError):
        raise InventoryError("La cantidad debe ser un entero positivo.") from None
    if not 1 <= number <= 9_000_000_000_000_000_000:
        raise InventoryError("La cantidad debe ser un entero positivo.")
    return number


def _key_and_hash(payload, idempotency_key):
    try:
        key = uuid.UUID(str(idempotency_key)) if idempotency_key else uuid.uuid4()
    except (ValueError, TypeError):
        raise InventoryError("Clave de operación inválida.") from None
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return key, digest


def _previous(key, digest, user):
    previous = Movement.objects.filter(idempotency_key=key).first()
    if previous:
        if previous.request_hash != digest or (previous.confirmed_by_id or previous.created_by_id) != user.pk:
            raise InventoryError("La clave de esta operación ya corresponde a otro movimiento.")
        return previous
    return None


def _content_matches(source, target, source_units, target_units):
    return (source.pk != target.pk and source.product_id == target.product_id
            and source.content_unit == target.content_unit
            and source.content_value * source_units == target.content_value * target_units)


def create_equivalence(*, user, source_id, target_id, source_units, target_units):
    _actor(user)
    if not is_owner(user):
        raise InventoryError("Solo el dueño puede definir equivalencias.")
    source_units, target_units = _positive(source_units), _positive(target_units)
    try:
        source_id, target_id = _whole_number(source_id), _whole_number(target_id)
    except (ValueError, TypeError):
        raise InventoryError("Presentaciones inválidas.") from None
    try:
        with transaction.atomic():
            ids = sorted((source_id, target_id))
            presentations = {item.pk: item for item in Presentation.objects.select_for_update().filter(pk__in=ids, active=True, product__active=True).order_by("pk")}
            source, target = presentations[source_id], presentations[target_id]
            if not _content_matches(source, target, source_units, target_units):
                raise InventoryError("La equivalencia debe conservar exactamente el contenido del mismo producto.")
            return Equivalence.objects.create(source=source, target=target, source_units=source_units,
                                              target_units=target_units, created_by=user)
    except KeyError:
        raise InventoryError("Presentaciones inválidas o inactivas.") from None
    except IntegrityError:
        raise InventoryError("Ya existe una equivalencia activa para ese par.") from None


def deactivate_equivalence(*, user, equivalence_id):
    _actor(user)
    if not is_owner(user):
        raise InventoryError("Solo el dueño puede desactivar equivalencias.")
    with transaction.atomic():
        try:
            rule = Equivalence.objects.select_for_update().get(pk=equivalence_id, active=True)
        except Equivalence.DoesNotExist:
            raise InventoryError("Equivalencia inexistente o inactiva.") from None
        rule.active = False
        rule.save(update_fields=["active"])
        return rule


def _apply_lines(movement, lines):
    """Caller holds all affected presentation locks and the surrounding transaction."""
    for presentation, location, delta, snapshot, location_snapshot in sorted(lines, key=lambda row: (row[0].pk, row[1].pk)):
        stock, _ = Stock.objects.get_or_create(presentation=presentation, location=location)
        stock = Stock.objects.select_for_update().get(pk=stock.pk)
        updated = stock.quantity + delta
        if updated < 0:
            raise InventoryError(f"Stock insuficiente en {location.name}: disponible {stock.quantity}.")
        if updated > 9_000_000_000_000_000_000:
            raise InventoryError("La cantidad supera el límite permitido.")
        stock.quantity = updated
        stock.save(update_fields=["quantity"])
        MovementLine.objects.create(movement=movement, presentation=presentation, location=location,
                                    delta=delta, presentation_snapshot=snapshot, location_snapshot=location_snapshot)


def convert_presentation(*, user, equivalence_id, multiples, location_id, idempotency_key=None, draft_created_by=None):
    _actor(user)
    multiples = _positive(multiples)
    try:
        equivalence_id, location_id = _whole_number(equivalence_id), _whole_number(location_id)
    except (ValueError, TypeError):
        raise InventoryError("Equivalencia o ubicación inválida.") from None
    payload = {"type": "CONVERSION", "equivalence_id": equivalence_id, "multiples": multiples, "location_id": location_id}
    key, digest = _key_and_hash(payload, idempotency_key)
    previous = _previous(key, digest, user)
    if previous:
        return previous
    try:
        with transaction.atomic():
            rule = Equivalence.objects.select_for_update().select_related("source__product", "target__product").get(pk=equivalence_id, active=True)
            locked = list(Presentation.objects.select_for_update().filter(pk__in=sorted((rule.source_id, rule.target_id))).order_by("pk"))
            if len(locked) != 2 or not all(p.active and p.product.active for p in locked):
                raise InventoryError("Presentación inactiva.")
            source, target = rule.source, rule.target
            if not _content_matches(source, target, rule.source_units, rule.target_units):
                raise InventoryError("La equivalencia ya no conserva el contenido.")
            location = Location.objects.get(pk=location_id, active=True)
            source_quantity, target_quantity = rule.source_units * multiples, rule.target_units * multiples
            if max(source_quantity, target_quantity) > 9_000_000_000_000_000_000:
                raise InventoryError("La cantidad supera el límite permitido.")
            movement = Movement.objects.create(idempotency_key=key, request_hash=digest, type=Movement.Type.CONVERSION,
                                               created_by=draft_created_by or user, confirmed_by=user, equivalence=rule,
                                               equivalence_snapshot={"source_units": rule.source_units, "target_units": rule.target_units,
                                                                     "source_content": str(source.content_value), "target_content": str(target.content_value),
                                                                     "content_unit": source.content_unit})
            _apply_lines(movement, [
                (source, location, -source_quantity, f"{source.product.name} · {source.name} ({source.unit_description})", location.name),
                (target, location, target_quantity, f"{target.product.name} · {target.name} ({target.unit_description})", location.name),
            ])
            return movement
    except (Equivalence.DoesNotExist, Location.DoesNotExist):
        raise InventoryError("Equivalencia o ubicación inexistente o inactiva.") from None
    except IntegrityError:
        previous = _previous(key, digest, user)
        if previous:
            return previous
        raise InventoryError("La conversión no pudo completarse.") from None


def reverse_movement(*, user, movement_id, reason, idempotency_key=None):
    _actor(user)
    if not is_owner(user):
        raise InventoryError("Solo el dueño puede reversar movimientos.")
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 500:
        raise InventoryError("El motivo del reverso es obligatorio y debe tener hasta 500 caracteres.")
    reason = reason.strip()
    try:
        original_id = uuid.UUID(str(movement_id))
    except (ValueError, TypeError):
        raise InventoryError("Movimiento original inválido.") from None
    payload = {"type": "REVERSO", "original_id": str(original_id), "reason": reason}
    key, digest = _key_and_hash(payload, idempotency_key)
    previous = _previous(key, digest, user)
    if previous:
        return previous
    try:
        with transaction.atomic():
            original = Movement.objects.select_for_update().get(pk=original_id)
            previous = _previous(key, digest, user)
            if previous:
                return previous
            if original.type == Movement.Type.REVERSAL or Movement.objects.filter(reversal_of=original).exists():
                raise InventoryError("Este movimiento ya fue reversado o es un reverso.")
            original_lines = list(original.lines.select_related("presentation", "location"))
            list(Presentation.objects.select_for_update().filter(pk__in=sorted({line.presentation_id for line in original_lines})).order_by("pk"))
            movement = Movement.objects.create(idempotency_key=key, request_hash=digest, type=Movement.Type.REVERSAL,
                                               created_by=user, confirmed_by=user, reversal_of=original, reason=reason)
            _apply_lines(movement, [(line.presentation, line.location, -line.delta,
                                     line.presentation_snapshot, line.location_snapshot) for line in original_lines])
            return movement
    except Movement.DoesNotExist:
        raise InventoryError("Movimiento original inexistente.") from None
    except IntegrityError:
        previous = _previous(key, digest, user)
        if previous:
            return previous
        raise InventoryError("El reverso no pudo completarse.") from None


def _draft_values(*, type_, presentation_id=None, quantity=1, source_id=None,
                  destination_id=None, reason="", equivalence_id=None, reversal_of_id=None):
    if not isinstance(reason, str) or len(reason.strip()) > 500:
        raise InventoryError("Motivo inválido.")
    reason = reason.strip()
    if type_ == Movement.Type.REVERSAL:
        if not reason:
            raise InventoryError("El motivo del reverso es obligatorio.")
        try:
            original = Movement.objects.get(pk=uuid.UUID(str(reversal_of_id)))
            first_line = original.lines.first()
            if not first_line or original.type == Movement.Type.REVERSAL:
                raise InventoryError("Movimiento no reversible.")
            return dict(type=type_, presentation=None, quantity=1, source=first_line.location,
                        destination=None, equivalence=None, reversal_of=original, reason=reason)
        except (ValueError, TypeError, Movement.DoesNotExist):
            raise InventoryError("Movimiento original inválido.") from None
    q = _positive(quantity)
    try:
        source = Location.objects.get(pk=_whole_number(source_id), active=True)
    except (ValueError, TypeError, Location.DoesNotExist):
        raise InventoryError("Ubicación inexistente o inactiva.") from None
    if type_ == Movement.Type.CONVERSION:
        try:
            rule = Equivalence.objects.select_related("source").get(pk=_whole_number(equivalence_id), active=True)
        except (ValueError, TypeError, Equivalence.DoesNotExist):
            raise InventoryError("Equivalencia inexistente o inactiva.") from None
        return dict(type=type_, presentation=rule.source, quantity=q, source=source,
                    destination=None, equivalence=rule, reversal_of=None, reason="")
    if type_ not in (Movement.Type.PURCHASE, Movement.Type.SALE, Movement.Type.CONSUMPTION,
                     Movement.Type.WASTE, Movement.Type.TRANSFER, Movement.Type.INITIAL):
        raise InventoryError("Tipo de movimiento inválido.")
    try:
        presentation = Presentation.objects.get(pk=_whole_number(presentation_id), active=True, product__active=True)
        destination = Location.objects.get(pk=_whole_number(destination_id), active=True) if destination_id not in (None, "") else None
    except (ValueError, TypeError, Presentation.DoesNotExist, Location.DoesNotExist):
        raise InventoryError("Presentación o destino inexistente o inactivo.") from None
    if type_ == Movement.Type.TRANSFER and (destination is None or destination.pk == source.pk):
        raise InventoryError("El traslado requiere un destino diferente.")
    if type_ != Movement.Type.TRANSFER and destination is not None:
        raise InventoryError("Esta operación no admite destino.")
    if type_ in (Movement.Type.CONSUMPTION, Movement.Type.WASTE) and not reason:
        raise InventoryError("El motivo es obligatorio.")
    return dict(type=type_, presentation=presentation, quantity=q, source=source,
                destination=destination, equivalence=None, reversal_of=None, reason=reason)


def create_draft(*, user, **fields):
    _actor(user)
    if fields.get("type_") in (Movement.Type.INITIAL, Movement.Type.REVERSAL) and not is_owner(user):
        raise InventoryError("Solo el dueño puede preparar esta operación.")
    values = _draft_values(**fields)
    return MovementDraft.objects.create(created_by=user, **values)


def edit_draft(*, user, draft_id, expected_version, **fields):
    _actor(user)
    with transaction.atomic():
        draft = MovementDraft.objects.select_for_update().get(pk=draft_id)
        if draft.created_by_id != user.pk and not is_owner(user):
            raise InventoryError("No puedes editar este borrador.")
        if draft.status != MovementDraft.Status.DRAFT or draft.version != _positive(expected_version):
            raise InventoryError("El borrador cambió o ya no está editable.")
        if fields.get("type_") in (Movement.Type.INITIAL, Movement.Type.REVERSAL) and not is_owner(user):
            raise InventoryError("Solo el dueño puede preparar esta operación.")
        values = _draft_values(**fields)
        for name, value in values.items():
            setattr(draft, name, value)
        draft.version += 1
        draft.save()
        return draft


def cancel_draft(*, user, draft_id, expected_version):
    _actor(user)
    with transaction.atomic():
        draft = MovementDraft.objects.select_for_update().get(pk=draft_id)
        if draft.created_by_id != user.pk and not is_owner(user):
            raise InventoryError("No puedes cancelar este borrador.")
        if draft.status != MovementDraft.Status.DRAFT or draft.version != _positive(expected_version):
            raise InventoryError("El borrador cambió o ya no está editable.")
        draft.status = MovementDraft.Status.CANCELLED
        draft.version += 1
        draft.save(update_fields=["status", "version", "updated_at"])
        return draft


def confirm_draft(*, user, draft_id, expected_version):
    _actor(user)
    with transaction.atomic():
        draft = MovementDraft.objects.select_for_update().get(pk=draft_id)
        if draft.created_by_id != user.pk and not is_owner(user):
            raise InventoryError("No puedes confirmar este borrador.")
        if draft.status == MovementDraft.Status.CONFIRMED:
            return draft.movement
        if draft.status != MovementDraft.Status.DRAFT or draft.version != _positive(expected_version):
            raise InventoryError("El borrador cambió o ya no está confirmable.")
        if draft.type == Movement.Type.CONVERSION:
            movement = convert_presentation(user=user, equivalence_id=draft.equivalence_id,
                                            multiples=draft.quantity, location_id=draft.source_id,
                                            idempotency_key=draft.pk, draft_created_by=draft.created_by)
        elif draft.type == Movement.Type.REVERSAL:
            movement = reverse_movement(user=user, movement_id=draft.reversal_of_id,
                                        reason=draft.reason, idempotency_key=draft.pk)
        else:
            movement = register_movement(user=user, type_=draft.type, presentation_id=draft.presentation_id,
                                         quantity=draft.quantity, source_id=draft.source_id,
                                         destination_id=draft.destination_id, reason=draft.reason,
                                         idempotency_key=draft.pk, draft_created_by=draft.created_by)
        draft.movement = movement
        draft.status = MovementDraft.Status.CONFIRMED
        draft.version += 1
        draft.save(update_fields=["movement", "status", "version", "updated_at"])
        return movement
