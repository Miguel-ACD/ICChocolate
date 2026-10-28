"""Authenticated, private photo upload and retrieval; no inventory writes."""

import uuid

from django.core.files.base import ContentFile
from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST

from .models import Location, Movement, PhotoDocument, Presentation
from .photo_service import PhotoError, prepare_photo
from .photo_workflow import confirm_photo_group
from .services import InventoryError, is_owner
from .vision import VisionUnavailable, extract_document
from .views import profile_required


def _save_document(user, image, kind, group_id=None):
    if image is None or kind not in PhotoDocument.Kind.values:
        raise PhotoError("Indica una foto y su tipo.")
    prepared = prepare_photo(image)
    document = PhotoDocument(
        uploaded_by=user, kind=kind, sha256=prepared.sha256,
        byte_size=len(prepared.jpeg), width=prepared.width, height=prepared.height,
    )
    if group_id:
        document.group_id = group_id
    document.image.save(f"{uuid.uuid4().hex}.jpg", ContentFile(prepared.jpeg), save=False)
    try:
        document.save()
    except Exception:
        document.image.delete(save=False)
        raise
    return document


def _accessible_group(request, group_id):
    docs = list(PhotoDocument.objects.filter(group_id=group_id).order_by("created_at", "pk"))
    if not docs:
        return None
    if any(doc.uploaded_by_id != request.user.pk for doc in docs) and not is_owner(request.user):
        return False
    return docs


def _extract_with_fallback(document):
    try:
        extract_document(document)
    except VisionUnavailable as exc:
        document.extraction_status = "ERROR"
        document.extraction_provider = "manual"
        document.extraction_error = str(exc)[:200]
        document.save(update_fields=["extraction_status", "extraction_provider", "extraction_error"])
        return str(exc)
    return None


@login_required
@profile_required
@require_POST
def upload_document(request):
    try:
        document = _save_document(request.user, request.FILES.get("image"), request.POST.get("kind", ""))
    except PhotoError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"id": str(document.pk), "image_url": f"/documentos/{document.pk}/imagen/",
                         "review_url": f"/documentos/{document.group_id}/revisar/",
                         "width": document.width, "height": document.height}, status=201)


@login_required
@profile_required
def document_new(request):
    if request.method == "POST":
        try:
            document = _save_document(request.user, request.FILES.get("image"), request.POST.get("kind", ""))
        except PhotoError as exc:
            messages.error(request, str(exc))
        else:
            error = _extract_with_fallback(document)
            if error:
                messages.warning(request, error)
            return redirect("document_review", group_id=document.group_id)
    return render(request, "inventory/document_new.html", {"owner": is_owner(request.user)})


def _suggested_rows(docs):
    rows = {}
    for doc in docs:
        for item in doc.extraction_items:
            pk = item.get("presentation_id")
            code = item.get("code", "")
            key = pk or code
            if key not in rows:
                rows[key] = {"presentation_id": pk or "", "quantity": item.get("quantity") or "",
                             "code": code, "uncertain": not pk or not item.get("quantity")}
            elif doc.kind == PhotoDocument.Kind.RECEIPT and item.get("quantity"):
                rows[key]["quantity"] = item["quantity"]
                rows[key]["uncertain"] = not pk
    result = list(rows.values())[:40]
    result.extend({"presentation_id": "", "quantity": "", "code": "", "uncertain": False} for _ in range(4))
    return result[:40]


@login_required
@profile_required
def document_review(request, group_id):
    docs = _accessible_group(request, group_id)
    if docs is None:
        raise Http404("No se encontraron fotos.")
    if docs is False:
        return HttpResponseForbidden("No puedes revisar estas fotos.")
    movement = docs[0].movement
    if request.method == "POST" and not movement:
        action = request.POST.get("action", "confirm")
        if action == "add":
            if len(docs) >= 8:
                messages.error(request, "El límite es de ocho fotos por operación.")
            else:
                try:
                    with transaction.atomic():
                        current = list(PhotoDocument.objects.select_for_update().filter(group_id=group_id))
                        if not current or any(doc.movement_id for doc in current):
                            raise PhotoError("Este movimiento ya fue confirmado.")
                        if len(current) >= 8:
                            raise PhotoError("El límite es de ocho fotos por operación.")
                        added = _save_document(request.user, request.FILES.get("image"),
                                               request.POST.get("kind", ""), group_id)
                except PhotoError as exc:
                    messages.error(request, str(exc))
                else:
                    error = _extract_with_fallback(added)
                    messages.warning(request, error) if error else messages.success(request, "Foto añadida.")
            return redirect("document_review", group_id=group_id)
        if action == "extract":
            doc = next((d for d in docs if str(d.pk) == request.POST.get("document_id")), None)
            if doc:
                error = _extract_with_fallback(doc)
                messages.warning(request, error) if error else messages.success(request, "Propuestas actualizadas.")
            return redirect("document_review", group_id=group_id)
        if action == "confirm":
            try:
                count = int(request.POST.get("row_count", "0"))
                if not 1 <= count <= 40:
                    raise InventoryError("El número de renglones es inválido.")
                rows = [{"presentation_id": request.POST.get(f"presentation_{n}"),
                         "quantity": request.POST.get(f"quantity_{n}")}
                        for n in range(count) if request.POST.get(f"presentation_{n}") or request.POST.get(f"quantity_{n}")]
                movement = confirm_photo_group(user=request.user, group_id=group_id,
                    type_=request.POST.get("type", ""), location_id=request.POST.get("location", ""), rows=rows)
            except (InventoryError, ValueError) as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Movimiento con fotos confirmado y guardado.")
                return redirect("movement_history")
    if request.method == "POST" and request.POST.get("action", "confirm") == "confirm" and not movement:
        try:
            count = min(40, max(0, int(request.POST.get("row_count", "0"))))
        except ValueError:
            count = 0
        rows = [{"presentation_id": request.POST.get(f"presentation_{n}", ""),
                 "quantity": request.POST.get(f"quantity_{n}", ""), "code": "", "uncertain": False}
                for n in range(count)]
    else:
        rows = _suggested_rows(docs)
    return render(request, "inventory/document_review.html", {
        "docs": docs, "group_id": group_id, "rows": rows,
        "presentations": Presentation.objects.filter(active=True, product__active=True).select_related("product"),
        "locations": Location.objects.filter(active=True), "movement": movement,
        "owner": is_owner(request.user),
    })


@login_required
@profile_required
@require_GET
def document_image(request, document_id):
    document = get_object_or_404(PhotoDocument, pk=document_id)
    if document.uploaded_by_id != request.user.pk and not is_owner(request.user):
        return HttpResponseForbidden("No puedes ver esta foto.")
    response = FileResponse(document.image.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
