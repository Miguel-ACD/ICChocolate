"""Authenticated alert history and owner-only rules and recipients."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET
from .alerts import change_rule
from .alert_mail import smtp_ready
from .models import AlertEpisode, AlertNotification, AlertRule, SensorDevice, UserProfile
from .services import InventoryError, is_owner


class ThresholdForm(forms.Form):
    threshold_c = forms.DecimalField(label="Umbral de temperatura (°C)", max_digits=6, decimal_places=2,
                                     min_value=0, max_value=50)


class RecipientForm(forms.Form):
    alert_email = forms.EmailField(label="Correo de alertas", required=False)
    receives_alert_email = forms.BooleanField(label="Recibir alertas por correo", required=False)

    def clean(self):
        values = super().clean()
        email = values.get("alert_email", "")
        if values.get("receives_alert_email") and (not email or email.lower().endswith(".local")):
            raise forms.ValidationError("Indica una dirección real para activar el correo.")
        return values


def _profile_ok(request):
    return request.user.is_active and UserProfile.objects.filter(user=request.user).exists()


@login_required
@require_GET
def alert_list(request):
    if not _profile_ok(request):
        return HttpResponseForbidden("Cuenta sin perfil autorizado.")
    notifications = AlertNotification.objects.filter(user=request.user, channel=AlertNotification.Channel.WEB).select_related(
        "episode__device").order_by("-created_at", "-pk")
    page = Paginator(notifications, 30).get_page(request.GET.get("page"))
    active = AlertEpisode.objects.filter(status=AlertEpisode.Status.ACTIVE).select_related("device").order_by("device__code")
    return render(request, "inventory/alerts.html", {
        "notifications": page.object_list, "page_obj": page, "active": active,
        "owner": is_owner(request.user), "smtp_ready": smtp_ready(),
        "email_notifications": AlertNotification.objects.filter(channel=AlertNotification.Channel.EMAIL).select_related("episode__device", "user").order_by("-created_at", "-pk")[:30] if is_owner(request.user) else [],
    })


@login_required
@require_GET
def alert_rules(request):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede administrar umbrales.")
    devices = SensorDevice.objects.order_by("code")
    current = {rule.device_id: rule for rule in AlertRule.objects.filter(ended_at__isnull=True)}
    return render(request, "inventory/alert_rules.html", {
        "rows": [(device, current.get(device.pk)) for device in devices], "owner": True,
    })


@login_required
def alert_rule_edit(request, device_id):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede administrar umbrales.")
    device = get_object_or_404(SensorDevice, pk=device_id)
    current = AlertRule.objects.filter(device=device, ended_at__isnull=True).first()
    form = ThresholdForm(request.POST or None, initial={"threshold_c": current.threshold_c if current else 10})
    if request.method == "POST" and form.is_valid():
        try:
            change_rule(user=request.user, device_id=device.pk, threshold_c=form.cleaned_data["threshold_c"])
        except InventoryError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Umbral actualizado. La próxima lectura válida inicia la evaluación nueva.")
            return redirect("alert_rules")
    return render(request, "inventory/simple_form.html", {
        "form": form, "title": f"Umbral de {device.code}",
        "description": "Los 10 °C son una regla de demostración, no una recomendación general de conservación.",
        "submit_label": "Guardar umbral", "owner": True,
    })


@login_required
@require_GET
def alert_recipients(request):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede administrar destinatarios.")
    profiles = UserProfile.objects.select_related("user").order_by("user__username")
    return render(request, "inventory/alert_recipients.html", {"profiles": profiles, "owner": True})


@login_required
def alert_recipient_edit(request, profile_id):
    if not is_owner(request.user):
        return HttpResponseForbidden("Solo el dueño puede administrar destinatarios.")
    profile = get_object_or_404(UserProfile, pk=profile_id)
    form = RecipientForm(request.POST or None, initial={
        "alert_email": profile.alert_email, "receives_alert_email": profile.receives_alert_email,
    })
    if request.method == "POST" and form.is_valid():
        profile.alert_email = form.cleaned_data["alert_email"]
        profile.receives_alert_email = form.cleaned_data["receives_alert_email"]
        profile.save(update_fields=["alert_email", "receives_alert_email"])
        messages.success(request, "Destinatario actualizado.")
        return redirect("alert_recipients")
    return render(request, "inventory/simple_form.html", {
        "form": form, "title": f"Correo de {profile.alias}",
        "description": "Las alertas web siguen visibles aunque el correo esté desactivado.",
        "submit_label": "Guardar destinatario", "owner": True,
    })
