"""REST API views consumed by the React Native / Expo Go mobile app."""

import json

from django.db import DatabaseError

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from inventory.models import (
    AlertEpisode, ExpoPushToken, Movement, PhotoDocument,
    Presentation, SensorReading, Stock, UserProfile,
)
from inventory.photo_service import PhotoError, prepare_photo
from inventory.document_views import _save_document
from inventory.vision import VisionUnavailable, extract_document
from inventory.chatbot import ChatInputError, ChatUnavailable, answer_question

from .serializers import (
    AlertEpisodeSerializer, ExpoPushTokenSerializer, MovementSerializer,
    SensorReadingSerializer, StockSerializer,
)


# ──────────────────────────────────────────────────
# Stock (read-only)
# ──────────────────────────────────────────────────
class StockViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Stock.objects.select_related(
        "presentation__product", "location"
    ).order_by("presentation__code", "location__code")
    serializer_class = StockSerializer
    permission_classes = [permissions.IsAuthenticated]


# ──────────────────────────────────────────────────
# Movements (read-only)
# ──────────────────────────────────────────────────
class MovementViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Movement.objects.select_related(
        "created_by__profile"
    ).prefetch_related("lines").order_by("-created_at", "-pk")
    serializer_class = MovementSerializer
    permission_classes = [permissions.IsAuthenticated]


# ──────────────────────────────────────────────────
# Sensor readings (read-only, last 50)
# ──────────────────────────────────────────────────
class SensorReadingViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SensorReadingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SensorReading.objects.select_related("device").order_by(
            "-received_at", "-pk"
        )[:50]


# ──────────────────────────────────────────────────
# Alert episodes (read-only)
# ──────────────────────────────────────────────────
class AlertEpisodeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AlertEpisode.objects.select_related("device").order_by(
        "-started_at", "-pk"
    )
    serializer_class = AlertEpisodeSerializer
    permission_classes = [permissions.IsAuthenticated]


# ──────────────────────────────────────────────────
# Photo upload  →  saves photo + runs Gemini vision
# ──────────────────────────────────────────────────
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def upload_photo(request):
    """
    Accepts multipart/form-data with `image` (file) and `kind` (BOLETA|ETIQUETA|OTRO).
    Saves the photo, then tries Gemini extraction automatically.
    Returns the document id, review URL and extraction results.
    """
    image = request.FILES.get("image")
    kind = request.data.get("kind", "")
    if not image or kind not in PhotoDocument.Kind.values:
        return Response(
            {"error": "Envía una imagen y un tipo válido (BOLETA, ETIQUETA, OTRO)."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        document = _save_document(request.user, image, kind)
    except PhotoError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # Run Gemini vision analysis automatically (same logic as web "Analizar con IA")
    extraction_error = None
    try:
        extract_document(document)
    except VisionUnavailable as exc:
        extraction_error = str(exc)

    # Reload to get updated extraction fields
    document.refresh_from_db()
    return Response({
        "id": str(document.pk),
        "group_id": str(document.group_id),
        "review_url": f"/documentos/{document.group_id}/revisar/",
        "extraction_status": document.extraction_status,
        "extraction_items": document.extraction_items,
        "extraction_error": extraction_error or "",
    }, status=status.HTTP_201_CREATED)


# ──────────────────────────────────────────────────
# Chat with AI assistant
# ──────────────────────────────────────────────────
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def chat(request):
    """
    Accepts JSON {"question": "...", "context": "..."}.
    Forwards to the same chatbot used by the web UI.
    """
    question = request.data.get("question", "")
    context = request.data.get("context")
    try:
        result = answer_question(request.user, question, context=context)
    except ChatInputError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except (ChatUnavailable, DatabaseError):
        return Response(
            {"error": "El asistente no está disponible ahora."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response(result)


# ──────────────────────────────────────────────────
# Expo push token registration
# ──────────────────────────────────────────────────
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def register_expo_token(request):
    """
    Accepts {"token": "ExponentPushToken[...]"}.
    Creates or reassigns the token to the authenticated user.
    """
    token = request.data.get("token", "").strip()
    if not token or not token.startswith("ExponentPushToken["):
        return Response(
            {"error": "Token de Expo inválido."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    obj, created = ExpoPushToken.objects.update_or_create(
        token=token, defaults={"user": request.user}
    )
    return Response({"detail": "Token registrado.", "id": obj.pk})


# ──────────────────────────────────────────────────
# Mobile Dashboard summary (all-in-one metrics)
# ──────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def dashboard_summary(request):
    """Returns essential metrics for the mobile app home screen in a single fast call."""
    from django.db.models import Sum
    from inventory.models import Product

    stocks = Stock.objects.filter(quantity__gt=0)
    total_units = stocks.aggregate(total=Sum("quantity"))["total"] or 0
    positions_count = stocks.count()
    products_count = Product.objects.filter(active=True).count()
    alerts_count = AlertEpisode.objects.filter(status=AlertEpisode.Status.ACTIVE).count()

    latest_reading = SensorReading.objects.filter(
        status=SensorReading.Status.VALID
    ).select_related("device", "assignment__location").order_by("-received_at", "-pk").first()

    sensor_data = None
    if latest_reading:
        sensor_data = {
            "device": latest_reading.device.code,
            "temperature_c": float(latest_reading.temperature_c),
            "humidity_percent": float(latest_reading.humidity_percent),
            "location": latest_reading.assignment.location.name if latest_reading.assignment else "Zona general",
            "received_at": latest_reading.received_at.isoformat(),
            "is_alert": latest_reading.temperature_c > 10.0,
        }

    alias = "Usuario"
    role = "EMPLEADO"
    if hasattr(request.user, "profile"):
        alias = request.user.profile.alias
        role = request.user.profile.role

    recent_movements = list(
        Movement.objects.select_related("created_by__profile")
        .prefetch_related("lines").order_by("-created_at", "-pk")[:5]
    )

    movements_data = []
    for m in recent_movements:
        lines_summary = ", ".join(f"{line.presentation_snapshot} ({line.delta:+d})" for line in m.lines.all()[:2])
        movements_data.append({
            "id": str(m.pk),
            "type": m.type,
            "type_label": m.get_type_display(),
            "created_at": m.created_at.isoformat(),
            "lines_summary": lines_summary or m.reason,
            "author": m.created_by.profile.alias if hasattr(m.created_by, "profile") else m.created_by.username,
        })

    return Response({
        "user": {
            "alias": alias,
            "role": role,
            "email": request.user.email or request.user.username,
        },
        "stats": {
            "total_units": total_units,
            "positions_count": positions_count,
            "products_count": products_count,
            "active_alerts_count": alerts_count,
        },
        "sensor": sensor_data,
        "recent_movements": movements_data,
    })


# ──────────────────────────────────────────────────
# Mobile Monitoring API (device selector + readings)
# ──────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def monitoring_data(request):
    """Returns sensor devices list and latest readings for the selected device."""
    from django.utils import timezone
    from django.db.models.functions import Coalesce
    from inventory.models import AlertEpisode, AlertRule, SensorAssignment, SensorDevice, SensorReading

    devices_qs = SensorDevice.objects.order_by("code")
    devices_list = []
    for d in devices_qs:
        assign = SensorAssignment.objects.filter(device=d, ended_at__isnull=True).select_related("location").first()
        devices_list.append({
            "id": d.id,
            "code": d.code,
            "active": d.active,
            "location": assign.location.name if assign else "Sin zona asignada",
        })

    code = request.GET.get("device")
    selected_device = None
    if code:
        selected_device = devices_qs.filter(code=code).first()
    if not selected_device:
        selected_device = devices_qs.first()

    if not selected_device:
        return Response({
            "devices": [],
            "selected_device": None,
            "readings": [],
            "chart_points": [],
        })

    now = timezone.now()
    cycles_qs = SensorReading.objects.filter(device=selected_device).order_by("-received_at", "-pk")
    latest_cycle = cycles_qs.first()
    latest_valid = cycles_qs.filter(status=SensorReading.Status.VALID).annotate(
        effective_at=Coalesce("cycle_started_at", "received_at")
    ).order_by("-effective_at", "-pk").first()

    assign = SensorAssignment.objects.filter(device=selected_device, ended_at__isnull=True).select_related("location").first()
    rule = AlertRule.objects.filter(device=selected_device, ended_at__isnull=True).first()
    active_alert = AlertEpisode.objects.filter(device=selected_device, status=AlertEpisode.Status.ACTIVE).first()

    fresh = bool(latest_valid and (now - latest_valid.effective_at).total_seconds() <= 180)
    communicating = bool(latest_cycle and (now - latest_cycle.received_at).total_seconds() <= 180)

    # 30 lecturas más recientes para la tabla
    recent_readings = []
    for r in cycles_qs[:30]:
        recent_readings.append({
            "id": r.id,
            "reading_id": r.reading_id,
            "status": r.status,
            "status_label": r.get_status_display(),
            "valid_samples": r.sample_count,
            "temperature_c": float(r.temperature_c) if r.temperature_c is not None else None,
            "humidity_percent": float(r.humidity_percent) if r.humidity_percent is not None else None,
            "received_at": r.received_at.isoformat(),
        })

    # Puntos para el gráfico (últimos 20 válidos en orden cronológico)
    chart_cycles = list(cycles_qs.filter(status=SensorReading.Status.VALID)[:20])
    chart_points = [
        {
            "time": c.received_at.strftime("%H:%M"),
            "temperature": float(c.temperature_c),
            "humidity": float(c.humidity_percent),
        }
        for c in reversed(chart_cycles)
    ]

    return Response({
        "devices": devices_list,
        "selected_device": {
            "id": selected_device.id,
            "code": selected_device.code,
            "active": selected_device.active,
            "location": assign.location.name if assign else "Sin zona",
        },
        "status": {
            "communicating": communicating,
            "fresh": fresh,
            "threshold_c": float(rule.threshold_c) if rule else 10.0,
            "has_alert": bool(active_alert),
            "latest_temp": float(latest_valid.temperature_c) if latest_valid else None,
            "latest_hum": float(latest_valid.humidity_percent) if latest_valid else None,
            "latest_time": latest_valid.received_at.isoformat() if latest_valid else None,
        },
        "readings": recent_readings,
        "chart_points": chart_points,
    })


# ──────────────────────────────────────────────────
# Catálogo para formularios móviles (presentaciones, ubicaciones, equivalencias)
# ──────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def catalog_data(request):
    from inventory.models import Equivalence, Location, Presentation
    presentations = [
        {
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "product_name": p.product.name,
            "content_value": float(p.content_value) if p.content_value is not None else 0,
            "content_unit": p.content_unit,
            "full_label": f"{p.product.name} · {p.name} ({p.code})",
        }
        for p in Presentation.objects.filter(active=True, product__active=True).select_related("product")
    ]
    locations = [
        {"id": loc.id, "code": loc.code, "name": loc.name}
        for loc in Location.objects.filter(active=True)
    ]
    equivalences = [
        {
            "id": eq.id,
            "source_id": eq.source.id,
            "source_code": eq.source.code,
            "source_name": f"{eq.source.product.name} · {eq.source.name}",
            "source_units": eq.source_units,
            "target_id": eq.target.id,
            "target_code": eq.target.code,
            "target_name": f"{eq.target.product.name} · {eq.target.name}",
            "target_units": eq.target_units,
            "label": f"{eq.source.code} ({eq.source_units} ud) ➔ {eq.target.code} ({eq.target_units} uds)",
        }
        for eq in Equivalence.objects.filter(active=True).select_related("source__product", "target__product")
    ]
    movement_types = [
        {"code": "COMPRA", "label": "🛒 Compra / Ingreso"},
        {"code": "VENTA", "label": "💰 Venta"},
        {"code": "TRASLADO", "label": "🔄 Traslado entre ubicaciones"},
        {"code": "MERMA", "label": "⚠️ Merma (daño/vencimiento)"},
        {"code": "CONSUMO", "label": "🍴 Consumo interno / degustación"},
        {"code": "AJUSTE", "label": "⚙️ Ajuste de inventario"},
    ]
    return Response({
        "presentations": presentations,
        "locations": locations,
        "equivalences": equivalences,
        "movement_types": movement_types,
    })


# ──────────────────────────────────────────────────
# Borradores de Movimientos (MovementDraft)
# ──────────────────────────────────────────────────
@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def drafts_view(request):
    from inventory.models import MovementDraft
    from inventory.phase2 import create_draft
    from inventory.services import InventoryError, is_owner

    if request.method == "GET":
        qs = MovementDraft.objects.filter(
            status=MovementDraft.Status.DRAFT
        ).select_related("presentation__product", "source", "destination", "equivalence__source", "equivalence__target", "created_by__profile").order_by("-updated_at")

        if not is_owner(request.user):
            qs = qs.filter(created_by=request.user)

        drafts = []
        for d in qs[:50]:
            alias = getattr(getattr(d.created_by, "profile", None), "alias", "") or d.created_by.username
            eq_label = None
            if d.equivalence:
                eq_label = f"{d.equivalence.source.code} ({d.equivalence.source_units}) ➔ {d.equivalence.target.code} ({d.equivalence.target_units})"

            drafts.append({
                "id": str(d.id),
                "version": d.version,
                "type": d.type,
                "type_label": d.get_type_display(),
                "presentation_id": d.presentation.id if d.presentation else None,
                "presentation_code": d.presentation.code if d.presentation else "",
                "presentation_name": f"{d.presentation.product.name} · {d.presentation.name}" if d.presentation else "",
                "quantity": d.quantity,
                "source_id": d.source.id if d.source else None,
                "source_name": d.source.name if d.source else "",
                "destination_id": d.destination.id if d.destination else None,
                "destination_name": d.destination.name if d.destination else "",
                "equivalence_id": d.equivalence.id if d.equivalence else None,
                "equivalence_label": eq_label,
                "reason": d.reason,
                "created_by_alias": alias,
                "created_at": d.created_at.isoformat(),
                "updated_at": d.updated_at.isoformat(),
            })
        return Response({"drafts": drafts})

    elif request.method == "POST":
        data = request.data
        type_ = data.get("type", "").strip()
        reason = data.get("reason", "").strip()

        try:
            if type_ == "CONVERSION":
                eq_id = data.get("equivalence_id")
                multiples = int(data.get("quantity", 1))
                location_id = data.get("source_id") or data.get("location_id")
                if not eq_id or not location_id:
                    return Response({"error": "Indica la equivalencia y la ubicación."}, status=status.HTTP_400_BAD_REQUEST)
                draft = create_draft(
                    user=request.user,
                    type_="CONVERSION",
                    equivalence_id=eq_id,
                    quantity=multiples,
                    source_id=location_id,
                )
            else:
                pres_id = data.get("presentation_id")
                qty = int(data.get("quantity", 0))
                source_id = data.get("source_id")
                dest_id = data.get("destination_id")
                if not pres_id or not source_id:
                    return Response({"error": "Indica la presentación y ubicación de origen."}, status=status.HTTP_400_BAD_REQUEST)
                draft = create_draft(
                    user=request.user,
                    type_=type_,
                    presentation_id=pres_id,
                    quantity=qty,
                    source_id=source_id,
                    destination_id=dest_id if dest_id else None,
                    reason=reason,
                )
        except (InventoryError, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "success": True,
            "draft_id": str(draft.id),
            "version": draft.version,
            "message": "Borrador creado correctamente. Listo para revisar y confirmar.",
        }, status=status.HTTP_201_CREATED)


# ──────────────────────────────────────────────────
# Confirmar o Cancelar Borrador
# ──────────────────────────────────────────────────
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def draft_confirm(request, draft_id):
    import uuid
    from inventory.models import MovementDraft
    from inventory.phase2 import confirm_draft
    from inventory.services import InventoryError

    try:
        draft = MovementDraft.objects.get(pk=uuid.UUID(str(draft_id)))
    except (MovementDraft.DoesNotExist, ValueError):
        return Response({"error": "Borrador no encontrado."}, status=status.HTTP_404_NOT_FOUND)

    expected_version = request.data.get("version", draft.version)
    try:
        movement = confirm_draft(user=request.user, draft_id=draft.pk, expected_version=expected_version)
    except InventoryError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        "success": True,
        "movement_id": str(movement.id),
        "message": f"Movimiento {movement.get_type_display()} confirmado e inventario actualizado.",
    })


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def draft_cancel(request, draft_id):
    import uuid
    from inventory.models import MovementDraft
    from inventory.phase2 import cancel_draft
    from inventory.services import InventoryError

    try:
        draft = MovementDraft.objects.get(pk=uuid.UUID(str(draft_id)))
    except (MovementDraft.DoesNotExist, ValueError):
        return Response({"error": "Borrador no encontrado."}, status=status.HTTP_404_NOT_FOUND)

    expected_version = request.data.get("version", draft.version)
    try:
        cancel_draft(user=request.user, draft_id=draft.pk, expected_version=expected_version)
    except InventoryError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        "success": True,
        "message": "Borrador cancelado correctamente.",
    })


# ──────────────────────────────────────────────────
# Confirmación de Grupo de Fotos con Renglones
# ──────────────────────────────────────────────────
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def photo_confirm(request):
    import uuid
    from inventory.photo_workflow import confirm_photo_group
    from inventory.services import InventoryError

    group_id = request.data.get("group_id")
    type_ = request.data.get("type", "COMPRA")
    location_id = request.data.get("location_id")
    rows = request.data.get("rows", [])

    if not group_id or not location_id or not rows:
        return Response({
            "error": "Indica group_id, ubicación y al menos un renglón con presentación y cantidad."
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        movement = confirm_photo_group(
            user=request.user,
            group_id=uuid.UUID(str(group_id)),
            type_=type_,
            location_id=location_id,
            rows=rows,
        )
    except (InventoryError, ValueError) as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        "success": True,
        "movement_id": str(movement.id),
        "message": f"Movimiento {movement.get_type_display()} con fotografía confirmado y guardado.",
    })

