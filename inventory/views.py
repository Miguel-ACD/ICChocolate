import uuid
from functools import wraps
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from .forms import LocationForm, MovementForm, ProductForm
from .models import Location, Movement, Presentation, Product, Stock, UserProfile
from .services import InventoryError, is_owner, register_movement


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
    recent = Movement.objects.select_related("created_by").prefetch_related("lines")[:5]
    return render(request, "inventory/dashboard.html", {
        "total_units": total, "positions": stocks.count(), "products": Product.objects.filter(active=True).count(),
        "recent": recent, "owner": is_owner(request.user),
    })


@login_required
@profile_required
def inventory_list(request):
    query = request.GET.get("q", "").strip()[:100]
    stocks = Stock.objects.select_related("presentation__product", "location").order_by(
        "presentation__product__name", "presentation__name", "location__name")
    if query:
        from django.db.models import Q
        stocks = stocks.filter(Q(presentation__product__name__icontains=query) |
                               Q(presentation__code__icontains=query) | Q(location__name__icontains=query))
    return render(request, "inventory/inventory.html", {"stocks": stocks, "query": query, "owner": is_owner(request.user)})


@login_required
@profile_required
def movement_new(request):
    form = MovementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        request.session["pending_movement"] = {
            "type": data["type"], "presentation_id": data["presentation"].pk,
            "quantity": data["quantity"], "source_id": data["source"].pk,
            "destination_id": data["destination"].pk if data["destination"] else None,
            "reason": data["reason"].strip(), "key": str(uuid.uuid4()),
        }
        return redirect("movement_confirm")
    return render(request, "inventory/movement_form.html", {"form": form, "owner": is_owner(request.user)})


@login_required
@profile_required
def movement_confirm(request):
    pending = request.session.get("pending_movement")
    if not pending:
        return redirect("movement_new")
    try:
        presentation = Presentation.objects.select_related("product").get(pk=pending["presentation_id"])
        source = Location.objects.get(pk=pending["source_id"])
        destination = Location.objects.get(pk=pending["destination_id"]) if pending["destination_id"] else None
    except (Presentation.DoesNotExist, Location.DoesNotExist):
        request.session.pop("pending_movement", None)
        messages.error(request, "La presentación o ubicación ya no está disponible.")
        return redirect("movement_new")
    if request.method == "POST":
        try:
            register_movement(
                user=request.user, type_=pending["type"], presentation_id=presentation.pk,
                quantity=pending["quantity"], source_id=source.pk,
                destination_id=destination.pk if destination else None,
                reason=pending["reason"], idempotency_key=pending["key"])
        except InventoryError as exc:
            messages.error(request, str(exc))
        else:
            request.session.pop("pending_movement", None)
            messages.success(request, "Movimiento confirmado y guardado.")
            return redirect("movement_history")
    return render(request, "inventory/movement_confirm.html", {
        "pending": pending, "type_label": Movement.Type(pending["type"]).label,
        "presentation": presentation, "source": source, "destination": destination,
        "owner": is_owner(request.user),
    })


@login_required
@profile_required
def movement_history(request):
    movements = Movement.objects.select_related("created_by").prefetch_related("lines")[:100]
    return render(request, "inventory/history.html", {"movements": movements, "owner": is_owner(request.user)})


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
