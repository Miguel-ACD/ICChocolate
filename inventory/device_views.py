"""Web pages for monitoring and owner-managed ESP32 devices."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .device_service import assign_device, register_device, rotate_device_token, set_device_active
from .models import AlertEpisode, AlertRule, Location, SensorAssignment, SensorDevice, SensorReading, UserProfile
from .services import InventoryError, is_owner


class DeviceCreateForm(forms.Form):
    code = forms.CharField(label="Código del dispositivo", max_length=40)
    location = forms.ModelChoiceField(label="Zona inicial", queryset=Location.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = Location.objects.filter(active=True)


class DeviceAssignForm(forms.Form):
    location = forms.ModelChoiceField(label="Nueva zona", queryset=Location.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = Location.objects.filter(active=True)


@login_required
def monitoring(request):
    if not request.user.is_active or not UserProfile.objects.filter(user=request.user).exists():
        return HttpResponseForbidden("Cuenta sin perfil autorizado.")
    devices = SensorDevice.objects.order_by("code")
    code = request.GET.get("device", "ESP32-01")
    device = devices.filter(code=code).first() or (devices.first() if "device" not in request.GET else None)
    if request.GET.get("device") and device is None:
        return render(request, "inventory/monitoring.html", {
            "devices": devices, "device": None, "cycles": [], "owner": is_owner(request.user),
        }, status=404)
    cycles = SensorReading.objects.none()
    latest_valid = None
    latest_cycle = None
    assignment = None
    alert_rule = None
    active_alert = None
    if device:
        cycles = SensorReading.objects.filter(device=device).select_related("assignment__location").order_by("-received_at", "-pk")
        latest_cycle = cycles.first()
        latest_valid = cycles.filter(status=SensorReading.Status.VALID).annotate(
            effective_at=Coalesce("cycle_started_at", "received_at")).order_by("-effective_at", "-pk").first()
        assignment = SensorAssignment.objects.filter(device=device, ended_at__isnull=True).select_related("location").first()
        alert_rule = AlertRule.objects.filter(device=device, ended_at__isnull=True).first()
        active_alert = AlertEpisode.objects.filter(device=device, status=AlertEpisode.Status.ACTIVE).first()
    from django.utils import timezone
    now = timezone.now()
    fresh = latest_valid and (now - latest_valid.effective_at).total_seconds() <= 180
    communicating = latest_cycle and (now - latest_cycle.received_at).total_seconds() <= 180
    return render(request, "inventory/monitoring.html", {
        "devices": devices, "device": device, "cycles": cycles[:100], "latest_valid": latest_valid,
        "latest_cycle": latest_cycle, "assignment": assignment, "fresh": fresh,
        "communicating": communicating, "owner": is_owner(request.user),
        "alert_rule": alert_rule, "active_alert": active_alert,
    })


@login_required
def device_list(request):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede administrar dispositivos.")
    devices = SensorDevice.objects.order_by("code")
    current = {item.device_id: item for item in SensorAssignment.objects.filter(
        ended_at__isnull=True).select_related("location")}
    return render(request, "inventory/devices.html", {"device_rows": [(device, current.get(device.pk)) for device in devices], "owner": True})


@login_required
def device_new(request):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede registrar dispositivos.")
    form = DeviceCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            device, token = register_device(user=request.user, code=form.cleaned_data["code"],
                                            location_id=form.cleaned_data["location"].pk)
        except InventoryError as exc:
            form.add_error(None, str(exc))
        else:
            return render(request, "inventory/device_token.html", {
                "device": device, "token": token, "owner": True,
            })
    return render(request, "inventory/simple_form.html", {
        "form": form, "title": "Registrar ESP32", "description": "Se generará un token único que se mostrará una sola vez.",
        "submit_label": "Registrar dispositivo", "owner": True,
    })


@login_required
def device_assign(request, device_id):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede asignar dispositivos.")
    device = get_object_or_404(SensorDevice, pk=device_id)
    form = DeviceAssignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            assign_device(user=request.user, device_id=device.pk, location_id=form.cleaned_data["location"].pk)
        except InventoryError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Zona actualizada. Las lecturas anteriores conservan su asignación.")
            return redirect("device_list")
    return render(request, "inventory/simple_form.html", {
        "form": form, "title": f"Asignar {device.code}", "description": "Las mediciones anteriores permanecen en su zona original.",
        "submit_label": "Guardar zona", "owner": True,
    })


@login_required
@require_POST
def device_toggle(request, device_id):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede cambiar dispositivos.")
    device = get_object_or_404(SensorDevice, pk=device_id)
    try:
        set_device_active(user=request.user, device_id=device.pk, active=not device.active)
    except InventoryError as exc:
        messages.error(request, str(exc))
    return redirect("device_list")


@login_required
@require_POST
def device_rotate(request, device_id):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede rotar tokens.")
    device = get_object_or_404(SensorDevice, pk=device_id)
    try:
        token = rotate_device_token(user=request.user, device_id=device.pk)
    except InventoryError as exc:
        messages.error(request, str(exc))
        return redirect("device_list")
    return render(request, "inventory/device_token.html", {"device": device, "token": token, "owner": True})
