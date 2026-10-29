import uuid
from functools import wraps
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Sum
from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .forms import AliasForm, ConversionForm, EquivalenceForm, LocationForm, LocationRenameForm, MovementForm, PresentationEditForm, PresentationForm, ProductEditForm, ProductForm, ReversalForm, LocationEditForm, UserCreateForm, UserEditForm
from .models import AlertEpisode, Equivalence, Location, Movement, MovementDraft, Presentation, Product, Stock, UserProfile
from .services import InventoryError, is_owner, register_movement
from .phase2 import cancel_draft, confirm_draft, create_draft, create_equivalence, deactivate_equivalence, edit_draft


def profile_required(view):
    @wraps(view)
    def guarded(request, *args, **kwargs):
        if not request.user.is_active or not UserProfile.objects.filter(user=request.user).exists():
            return HttpResponseForbidden("La cuenta no tiene un perfil autorizado.")
        return view(request, *args, **kwargs)
    return guarded


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = AuthenticationForm(request, data=request.POST or None)
    form.fields["username"].label = "Correo electrónico"
    if request.method == "POST" and form.is_valid():
        from django.contrib.auth import login
        if not hasattr(form.get_user(), "profile"):
            form.add_error(None, "La cuenta no tiene un perfil autorizado.")
            return render(request, "inventory/login.html", {"form": form})
        login(request, form.get_user())
        return redirect("dashboard")
    return render(request, "inventory/login.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
@profile_required
def dashboard(request):
    stocks = Stock.objects.select_related("presentation__product", "location").filter(quantity__gt=0)
    total = stocks.aggregate(total=Sum("quantity"))["total"] or 0
    recent = Movement.objects.select_related("created_by__profile").prefetch_related("lines").order_by("-created_at", "-pk")[:30]
    return render(request, "inventory/dashboard.html", {
        "total_units": total, "positions": stocks.count(), "products": Product.objects.filter(active=True).count(),
        "recent": recent, "owner": is_owner(request.user),
        "active_alerts": AlertEpisode.objects.filter(status=AlertEpisode.Status.ACTIVE).count(),
    })


@login_required
@profile_required
def inventory_list(request):
    query = request.GET.get("q", "").strip()[:100]
    stocks = Stock.objects.select_related("presentation__product", "location").order_by(
        "presentation__product__name", "presentation__name", "location__name", "pk")
    if query:
        from django.db.models import Q
        stocks = stocks.filter(Q(presentation__product__name__icontains=query) |
                               Q(presentation__code__icontains=query) | Q(location__name__icontains=query))
    page_obj = Paginator(stocks, 4).get_page(request.GET.get("page"))
    return render(request, "inventory/inventory.html", {
        "stocks": page_obj.object_list, "page_obj": page_obj,
        "page_numbers": page_obj.paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1),
        "query": query, "owner": is_owner(request.user),
    })


@login_required
@profile_required
def movement_new(request):
    form = MovementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            draft = create_draft(
                user=request.user, type_=data["type"], presentation_id=data["presentation"].pk,
                quantity=data["quantity"], source_id=data["source"].pk,
                destination_id=data["destination"].pk if data["destination"] else None,
                reason=data["reason"].strip())
        except InventoryError as exc:
            form.add_error(None, str(exc))
        else:
            request.session["pending_draft_id"] = str(draft.pk)
            request.session["pending_draft_version"] = draft.version
            request.session.pop("pending_movement", None)
            return redirect("movement_confirm")
    return render(request, "inventory/movement_form.html", {"form": form, "owner": is_owner(request.user)})


@login_required
@profile_required
def movement_confirm(request, draft_id=None):
    if draft_id is None:
        draft_id = request.session.get("pending_draft_id")
    if not draft_id:
        return redirect("movement_new")
    draft = MovementDraft.objects.select_related("presentation__product", "source", "destination", "equivalence__target").filter(pk=draft_id).first()
    if draft is None or draft.status == MovementDraft.Status.CANCELLED:
        return redirect("movement_new")
    if draft.created_by_id != request.user.pk and not is_owner(request.user):
        return HttpResponseForbidden("No puedes revisar este borrador.")
    if draft.status == MovementDraft.Status.CONFIRMED:
        return redirect("movement_history")
    if request.method == "POST":
        fallback = request.session.get("pending_draft_version") if str(draft.pk) == request.session.get("pending_draft_id") else None
        try:
            expected_version = int(request.POST.get("version", fallback))
            confirm_draft(user=request.user, draft_id=draft.pk, expected_version=expected_version)
        except (InventoryError, TypeError, ValueError) as exc:
            messages.error(request, str(exc))
        else:
            if str(draft.pk) == request.session.get("pending_draft_id"):
                request.session.pop("pending_draft_id", None)
                request.session.pop("pending_draft_version", None)
            messages.success(request, "Movimiento confirmado y guardado.")
            return redirect("movement_history")
    original = draft.reversal_of if draft.type == Movement.Type.REVERSAL else None
    return render(request, "inventory/movement_confirm.html", {
        "draft": draft, "pending": draft, "type_label": Movement.Type(draft.type).label,
        "presentation": draft.presentation, "source": draft.source, "destination": draft.destination,
        "equivalence": draft.equivalence, "original": original,
        "owner": is_owner(request.user),
    })


@login_required
@profile_required
def movement_history(request):
    movements = Movement.objects.select_related("created_by__profile", "confirmed_by__profile").prefetch_related("lines").annotate(
        already_reversed=Exists(Movement.objects.filter(reversal_of_id=OuterRef("pk")))).order_by("-created_at", "-pk")
    movement_id = request.GET.get("movement")
    if movement_id:
        try:
            movement_id = uuid.UUID(movement_id)
        except (ValueError, TypeError, AttributeError):
            return HttpResponseBadRequest("Identificador de movimiento inválido.")
        movements = movements.filter(pk=movement_id)
    page_obj = Paginator(movements, 4).get_page(request.GET.get("page"))
    return render(request, "inventory/history.html", {
        "movements": page_obj.object_list, "page_obj": page_obj,
        "page_numbers": page_obj.paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1),
        "owner": is_owner(request.user),
    })


@login_required
@profile_required
def alias_settings(request):
    form = AliasForm(request.POST or None, instance=request.user.profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Alias actualizado.")
        return redirect("dashboard")
    return render(request, "inventory/alias_form.html", {"form": form, "owner": is_owner(request.user)})


@login_required
@profile_required
def product_new(request):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede crear productos.")
    form = ProductForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            with transaction.atomic():
                product = Product.objects.create(code=d["code"], name=d["name"], description=d["description"])
                Presentation.objects.create(product=product, code=d["presentation_code"], name=d["presentation_name"],
                                            unit_description=d["unit_description"], content_value=d["content_value"],
                                            content_unit=d["content_unit"])
        except IntegrityError:
            form.add_error(None, "El código del producto o presentación ya existe.")
        else:
            messages.success(request, "Producto creado. Registra una compra manual para cargar existencias.")
            return redirect("inventory")
    return render(request, "inventory/product_form.html", {"form": form, "owner": True})


@login_required
@profile_required
def location_new(request):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede crear ubicaciones.")
    form = LocationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            Location.objects.create(**form.cleaned_data)
        except IntegrityError:
            form.add_error(None, "El código de ubicación ya existe.")
        else:
            messages.success(request, "Ubicación creada.")
            return redirect("inventory")
    return render(request, "inventory/location_form.html", {"form": form, "owner": True})


def health(request):
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok", "database": "ok"})
    except Exception:
        return JsonResponse({"status": "unavailable", "database": "unavailable"}, status=503)

@login_required
@profile_required
def draft_list(request):
    drafts = MovementDraft.objects.select_related("created_by__profile", "presentation", "equivalence", "reversal_of").order_by("-updated_at")
    if not is_owner(request.user):
        drafts = drafts.filter(created_by=request.user)
    return render(request, "inventory/drafts.html", {"drafts": drafts[:100], "owner": is_owner(request.user)})


@login_required
@profile_required
def draft_edit(request, draft_id):
    draft = get_object_or_404(MovementDraft, pk=draft_id)
    if draft.created_by_id != request.user.pk and not is_owner(request.user):
        return HttpResponseForbidden("No puedes editar este borrador.")
    if draft.status != MovementDraft.Status.DRAFT:
        return redirect("draft_list")
    if draft.type == Movement.Type.CONVERSION:
        form_class = ConversionForm
        initial = {"equivalence": draft.equivalence_id, "multiples": draft.quantity, "location": draft.source_id}
    elif draft.type == Movement.Type.REVERSAL:
        form_class = ReversalForm
        initial = {"reason": draft.reason}
    else:
        form_class = MovementForm
        initial = {"type": draft.type, "presentation": draft.presentation_id, "quantity": draft.quantity,
                   "source": draft.source_id, "destination": draft.destination_id, "reason": draft.reason}
    form = form_class(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        if draft.type == Movement.Type.CONVERSION:
            fields = dict(type_=Movement.Type.CONVERSION, equivalence_id=data["equivalence"].pk,
                          quantity=data["multiples"], source_id=data["location"].pk)
        elif draft.type == Movement.Type.REVERSAL:
            fields = dict(type_=Movement.Type.REVERSAL, reversal_of_id=draft.reversal_of_id, reason=data["reason"])
        else:
            fields = dict(type_=data["type"], presentation_id=data["presentation"].pk,
                          quantity=data["quantity"], source_id=data["source"].pk,
                          destination_id=data["destination"].pk if data["destination"] else None,
                          reason=data["reason"])
        try:
            updated = edit_draft(user=request.user, draft_id=draft.pk,
                                 expected_version=request.POST.get("version"), **fields)
        except InventoryError as exc:
            form.add_error(None, str(exc))
        else:
            request.session["pending_draft_id"] = str(updated.pk)
            request.session["pending_draft_version"] = updated.version
            return redirect("movement_confirm_id", draft_id=updated.pk)
    return render(request, "inventory/simple_form.html", {
        "form": form, "title": "Editar borrador", "description": "Los cambios no alteran el stock hasta confirmar.",
        "submit_label": "Guardar y revisar", "version": draft.version, "owner": is_owner(request.user),
    })


@login_required
@profile_required
@require_POST
def draft_cancel(request, draft_id):
    draft = get_object_or_404(MovementDraft, pk=draft_id)
    if draft.created_by_id != request.user.pk and not is_owner(request.user):
        return HttpResponseForbidden("No puedes cancelar este borrador.")
    try:
        cancel_draft(user=request.user, draft_id=draft_id, expected_version=request.POST.get("version"))
    except InventoryError as exc:
        messages.error(request, str(exc))
    else:
        if str(draft_id) == request.session.get("pending_draft_id"):
            request.session.pop("pending_draft_id", None)
            request.session.pop("pending_draft_version", None)
        messages.success(request, "Borrador cancelado.")
    return redirect("draft_list")


@login_required
@profile_required
def conversion_new(request):
    form = ConversionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            draft = create_draft(user=request.user, type_=Movement.Type.CONVERSION,
                                 equivalence_id=data["equivalence"].pk, quantity=data["multiples"],
                                 source_id=data["location"].pk)
        except InventoryError as exc:
            form.add_error(None, str(exc))
        else:
            request.session["pending_draft_id"] = str(draft.pk)
            request.session["pending_draft_version"] = draft.version
            return redirect("movement_confirm")
    return render(request, "inventory/simple_form.html", {
        "form": form, "title": "Convertir presentaciones", "description": "El origen y destino permanecen en la misma ubicación.",
        "submit_label": "Revisar conversión", "owner": is_owner(request.user),
    })


@login_required
@profile_required
def reversal_new(request, movement_id):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede reversar movimientos.")
    original = get_object_or_404(Movement, pk=movement_id)
    if original.type == Movement.Type.REVERSAL or Movement.objects.filter(reversal_of=original).exists():
        messages.error(request, "Este movimiento ya fue reversado o es un reverso.")
        return redirect("movement_history")
    form = ReversalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            draft = create_draft(user=request.user, type_=Movement.Type.REVERSAL,
                                 reversal_of_id=original.pk, reason=form.cleaned_data["reason"])
        except InventoryError as exc:
            form.add_error(None, str(exc))
        else:
            request.session["pending_draft_id"] = str(draft.pk)
            request.session["pending_draft_version"] = draft.version
            return redirect("movement_confirm")
    return render(request, "inventory/simple_form.html", {
        "form": form, "title": "Corregir movimiento", "description": "Se creará un reverso completo con motivo. Después podrás registrar la operación correcta.",
        "submit_label": "Revisar reverso", "original": original, "owner": True,
    })


@login_required
@profile_required
def equivalence_list(request):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede administrar equivalencias.")
    rules = Equivalence.objects.select_related("source", "target", "created_by").order_by("-created_at")
    return render(request, "inventory/equivalences.html", {"rules": rules, "owner": True})


@login_required
@profile_required
def equivalence_new(request):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede definir equivalencias.")
    form = EquivalenceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            create_equivalence(user=request.user, source_id=data["source"].pk, target_id=data["target"].pk,
                               source_units=data["source_units"], target_units=data["target_units"])
        except InventoryError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Equivalencia registrada.")
            return redirect("equivalence_list")
    return render(request, "inventory/simple_form.html", {
        "form": form, "title": "Definir equivalencia", "description": "El contenido total debe ser exactamente igual y del mismo producto.",
        "submit_label": "Guardar equivalencia", "owner": True,
    })


@login_required
@profile_required
@require_POST
def equivalence_disable(request, equivalence_id):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede administrar equivalencias.")
    try:
        deactivate_equivalence(user=request.user, equivalence_id=equivalence_id)
    except InventoryError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Equivalencia desactivada. Las conversiones anteriores conservan su regla original.")
    return redirect("equivalence_list")


@login_required
@profile_required
def presentation_new(request):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede crear presentaciones.")
    form = PresentationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            Presentation.objects.create(**form.cleaned_data)
        except IntegrityError:
            form.add_error(None, "El código de presentación ya existe.")
        else:
            messages.success(request, "Presentación creada. Su stock inicial es cero.")
            return redirect("inventory")
    return render(request, "inventory/simple_form.html", {
        "form": form, "title": "Crear presentación", "description": "Una unidad debe tener un contenido y una descripción claros.",
        "submit_label": "Guardar presentación", "owner": True,
    })


@login_required
@profile_required
def location_rename(request):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede renombrar ubicaciones.")
    form = LocationRenameForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        location = form.cleaned_data["location"]
        location.name = form.cleaned_data["name"].strip()
        location.save(update_fields=["name"])
        messages.success(request, "Ubicación renombrada. El historial conserva el nombre anterior.")
        return redirect("inventory")
    return render(request, "inventory/simple_form.html", {
        "form": form, "title": "Renombrar ubicación", "description": "El identificador y el historial no cambian.",
        "submit_label": "Guardar nombre", "owner": True,
    })

@login_required
@profile_required
def catalog_admin(request):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede administrar el catálogo.")
    return render(request, "inventory/catalog_admin.html", {
        "products": Product.objects.all(), "presentations": Presentation.objects.select_related("product"),
        "locations": Location.objects.all(), "owner": True,
    })


@login_required
@profile_required
def product_edit(request, product_id):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede modificar productos.")
    product = get_object_or_404(Product, pk=product_id)
    form = ProductEditForm(request.POST or None, initial={"name": product.name, "description": product.description, "active": product.active})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        if not data["active"] and Stock.objects.filter(presentation__product=product, quantity__gt=0).exists():
            form.add_error("active", "Traslada o agota las existencias antes de desactivar el producto.")
        else:
            product.name, product.description, product.active = data["name"].strip(), data["description"], data["active"]
            product.save(update_fields=["name", "description", "active"])
            messages.success(request, "Producto actualizado; el historial conserva sus nombres anteriores.")
            return redirect("catalog_admin")
    return render(request, "inventory/simple_form.html", {"form": form, "title": "Editar producto", "description": "El código y el historial no cambian.", "submit_label": "Guardar producto", "owner": True})


@login_required
@profile_required
def presentation_edit(request, presentation_id):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede modificar presentaciones.")
    presentation = get_object_or_404(Presentation, pk=presentation_id)
    form = PresentationEditForm(request.POST or None, initial={"name": presentation.name,
                                                       "unit_description": presentation.unit_description,
                                                       "active": presentation.active})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        if not data["active"] and Stock.objects.filter(presentation=presentation, quantity__gt=0).exists():
            form.add_error("active", "Traslada o agota las existencias antes de desactivar la presentación.")
        elif (data["unit_description"].strip() != presentation.unit_description
              and presentation.movementline_set.exists()):
            form.add_error("unit_description", "Una presentación con historial no puede cambiar el significado de su unidad.")
        else:
            presentation.name, presentation.unit_description, presentation.active = data["name"].strip(), data["unit_description"].strip(), data["active"]
            presentation.save(update_fields=["name", "unit_description", "active"])
            messages.success(request, "Presentación actualizada. Su contenido y unidad no se modificaron.")
            return redirect("catalog_admin")
    return render(request, "inventory/simple_form.html", {"form": form, "title": "Editar presentación", "description": "Contenido y unidad son inmutables; crea otra presentación si cambian.", "submit_label": "Guardar presentación", "owner": True})


@login_required
@profile_required
def location_edit(request, location_id):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede modificar ubicaciones.")
    location = get_object_or_404(Location, pk=location_id)
    form = LocationEditForm(request.POST or None, initial={"name": location.name, "active": location.active})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        if not data["active"] and Stock.objects.filter(location=location, quantity__gt=0).exists():
            form.add_error("active", "Traslada o agota las existencias antes de desactivar la ubicación.")
        else:
            location.name, location.active = data["name"].strip(), data["active"]
            location.save(update_fields=["name", "active"])
            messages.success(request, "Ubicación actualizada; el historial conserva su nombre anterior.")
            return redirect("catalog_admin")
    return render(request, "inventory/simple_form.html", {"form": form, "title": "Editar ubicación", "description": "No puede desactivarse si aún contiene existencias.", "submit_label": "Guardar ubicación", "owner": True})

@login_required
@profile_required
def user_list(request):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede administrar usuarios.")
    return render(request, "inventory/users.html", {
        "profiles": UserProfile.objects.select_related("user").order_by("user__username"), "owner": True,
    })


@login_required
@profile_required
def user_new(request):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede crear usuarios.")
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        from django.contrib.auth import get_user_model
        data = form.cleaned_data
        try:
            with transaction.atomic():
                user = get_user_model().objects.create_user(username=data["email"], email=data["email"],
                                                           password=data["password1"])
                UserProfile.objects.create(user=user, alias=data["alias"].strip(), role=data["role"])
        except IntegrityError:
            form.add_error("email", "La cuenta ya existe.")
        else:
            messages.success(request, "Usuario creado. Comunica la contraseña inicial de forma privada.")
            return redirect("user_list")
    return render(request, "inventory/simple_form.html", {"form": form, "title": "Crear usuario", "description": "El perfil limita las operaciones disponibles.", "submit_label": "Crear cuenta", "owner": True})


@login_required
@profile_required
def user_edit(request, profile_id):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede administrar usuarios.")
    profile = get_object_or_404(UserProfile.objects.select_related("user"), pk=profile_id)
    form = UserEditForm(request.POST or None, initial={"alias": profile.alias, "role": profile.role,
                                                   "active": profile.user.is_active})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        if profile.user_id == request.user.pk and (not data["active"] or data["role"] != UserProfile.Role.OWNER):
            form.add_error(None, "No puedes desactivar tu propia cuenta de dueño ni cambiar su perfil.")
        else:
            with transaction.atomic():
                owners = list(UserProfile.objects.select_for_update().filter(
                    role=UserProfile.Role.OWNER, user__is_active=True).order_by("pk"))
                locked = UserProfile.objects.select_for_update().select_related("user").get(pk=profile.pk)
                if not request.user.is_active:
                    form.add_error(None, "Tu cuenta ya no está activa.")
                if locked.role == UserProfile.Role.OWNER and locked.user.is_active and (
                        data["role"] != UserProfile.Role.OWNER or not data["active"]):
                    if len(owners) <= 1:
                        form.add_error(None, "Debe quedar al menos un dueño activo.")
                if form.is_valid():
                    locked.alias, locked.role = data["alias"].strip(), data["role"]
                    locked.save(update_fields=["alias", "role"])
                    locked.user.is_active = data["active"]
                    locked.user.save(update_fields=["is_active"])
                    messages.success(request, "Usuario actualizado.")
                    return redirect("user_list")
    return render(request, "inventory/simple_form.html", {"form": form, "title": "Editar usuario", "description": f"Cuenta: {profile.user.username}", "submit_label": "Guardar usuario", "owner": True})
