"""Bounded, local, read-only answers over trusted inventory queries.

The user's text selects one of a few fixed queries. It is never SQL, code, or a
prompt sent to a model. Conversations are not stored.
"""

import re
import unicodedata
import os
from urllib.parse import quote

from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import AlertEpisode, AlertRule, Location, Movement, Presentation, Product, SensorDevice, SensorReading, Stock, UserProfile


MAX_QUESTION = 500
MAX_CATALOG = 200


class ChatInputError(ValueError):
    pass


class ChatUnavailable(RuntimeError):
    pass


def _normal(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold())
                   if not unicodedata.combining(c))


def _has(text, words):
    return any(re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text) for word in words)


def _stamp(value):
    return timezone.localtime(value).strftime("%d/%m/%Y %H:%M:%S")


def _result(text, intent, now, sources=(), stale=False):
    return {"answer": text, "intent": intent, "as_of": timezone.localtime(now).isoformat(),
            "sources": list(sources), "stale": stale}


def _source(label, url):
    return {"label": label, "url": url}


def _match_exact(text, rows):
    """Match whole codes, keeping POLVO-100 distinct from POLVO-1000."""
    return [row for row in rows if re.search(r"(?<![\w-])" + re.escape(_normal(row.code)) + r"(?![\w-])", text)]


def _stock_answer(text, now):
    presentations = list(Presentation.objects.filter(active=True, product__active=True)
                         .select_related("product").order_by("code")[:MAX_CATALOG + 1])
    if len(presentations) > MAX_CATALOG:
        return _result("El catálogo es demasiado grande para buscar por nombre. Indica el código exacto de la presentación.", "ambiguous", now)
    exact = _match_exact(text, presentations)
    if len(exact) > 1:
        return _result("Mencionaste varias presentaciones. Pregunta por un código a la vez.", "ambiguous", now)
    selected = exact[0] if exact else None
    if not selected:
        named = [p for p in presentations if len(_normal(p.name)) >= 4 and _normal(p.name) in text]
        if len(named) == 1:
            selected = named[0]
        elif len(named) > 1:
            options = ", ".join(p.code for p in named[:10])
            return _result(f"Hay varias presentaciones posibles: {options}. Indica el código exacto.", "ambiguous", now)
    if not selected:
        products = list(Product.objects.filter(active=True).order_by("code")[:MAX_CATALOG + 1])
        matched = [p for p in products if (_normal(p.code) in text or
                   (len(_normal(p.name)) >= 4 and _normal(p.name) in text))]
        if len(matched) > 1:
            return _result("Hay varios productos posibles. Indica el código de la presentación.", "ambiguous", now)
        if matched:
            options = [p for p in presentations if p.product_id == matched[0].pk]
            if len(options) > 1:
                codes = ", ".join(p.code for p in options[:10])
                return _result(f"{matched[0].name} tiene varias presentaciones: {codes}. Indica una.", "ambiguous", now)
            if options:
                selected = options[0]
    if not selected and re.search(r"(?<!\w)[a-z]+(?:-[a-z0-9]+)+(?!\w)", text):
        return _result("No encuentro ese código activo en el catálogo. Compruébalo en Inventario.", "not_found", now,
                       [_source("Inventario", "/inventario/")])
    if selected:
        locations = list(Location.objects.filter(active=True).order_by("code")[:MAX_CATALOG + 1])
        location_matches = _match_exact(text, locations)
        if not location_matches:
            location_matches = [loc for loc in locations if len(_normal(loc.name)) >= 4 and _normal(loc.name) in text]
        if len(location_matches) > 1:
            return _result("Se mencionan varias ubicaciones; indica solo una.", "ambiguous", now)
        stocks = list(Stock.objects.filter(presentation=selected).select_related("location").order_by("location__name")[:MAX_CATALOG + 1])
        if location_matches:
            stocks = [stock for stock in stocks if stock.location_id == location_matches[0].pk]
        total = sum(stock.quantity for stock in stocks)
        unit = selected.unit_description
        if _has(text, ("unidad", "representa", "contiene")):
            answer = f"Una unidad de {selected.code} ({selected.product.name} · {selected.name}) representa: {unit}."
            if _has(text, ("stock", "existencia", "disponible", "cuanto", "cuantas", "cuantos")):
                answer += f" Hay {total} unidades registradas."
        else:
            detail = "; ".join(f"{stock.location.name}: {stock.quantity}" for stock in stocks) or "sin unidades registradas"
            answer = f"{selected.code} ({selected.product.name} · {selected.name}): {total} unidades. {detail}. Una unidad: {unit}."
        return _result(answer, "stock", now, [_source(f"Inventario · {selected.code}", f"/inventario/?q={quote(selected.code)}")])
    if _has(text, ("unidad", "representa", "contiene")):
        return _result("Indica el código de la presentación para explicar qué representa una unidad.", "ambiguous", now)
    positions = list(Stock.objects.select_related("presentation__product", "location")
                     .order_by("presentation__code", "location__code")[:10])
    total_positions = Stock.objects.count()
    total_units = Stock.objects.aggregate(total=Sum("quantity"))["total"] or 0
    if not positions:
        answer = "No hay existencias registradas."
    else:
        detail = "; ".join(f"{s.presentation.code} en {s.location.name}: {s.quantity}" for s in positions)
        answer = f"Inventario: {total_units} unidades en {total_positions} posiciones. {detail}."
        if total_positions > len(positions):
            answer += " Se muestran solo las primeras 10 posiciones."
    return _result(answer, "stock", now, [_source("Inventario", "/inventario/")])


def _movement_answer(text, now):
    purchase = _has(text, ("compra", "compras", "entrada", "entradas"))
    sale = _has(text, ("venta", "ventas", "salida", "salidas"))
    if purchase and sale:
        return _result("Indica si deseas ver compras o ventas; una clase de movimiento por pregunta.", "ambiguous", now)
    movements = Movement.objects.select_related("created_by__profile", "confirmed_by__profile").prefetch_related("lines")
    catalog = list(Presentation.objects.filter(active=True, product__active=True).order_by("code")[:MAX_CATALOG + 1])
    exact = _match_exact(text, catalog)
    if len(exact) > 1:
        return _result("Mencionaste varias presentaciones. Indica un código por pregunta.", "ambiguous", now)
    if exact:
        movements = movements.filter(lines__presentation=exact[0]).distinct()
    if purchase:
        movements = movements.filter(type=Movement.Type.PURCHASE)
    if sale:
        movements = movements.filter(type=Movement.Type.SALE)
    rows = list(movements.order_by("-created_at", "-pk")[:5])
    if not rows:
        return _result("No hay movimientos registrados para esa consulta.", "movements", now,
                       [_source("Historial", "/movimientos/")])
    parts = []
    for movement in rows:
        lines = list(movement.lines.all())[:10]
        detail = ", ".join(f"{line.presentation_snapshot}: {line.delta:+d} en {line.location_snapshot}" for line in lines)
        if movement.lines.count() > len(lines):
            detail += ", más renglones"
        parts.append(f"{movement.get_type_display()} {str(movement.pk)[:8]} ({_stamp(movement.created_at)}): {detail}")
    return _result("Últimos movimientos: " + "; ".join(parts) + ".", "movements", now,
                   [_source(f"Movimiento {str(movement.pk)[:8]}", f"/movimientos/?movement={movement.pk}") for movement in rows])


def _device_answer(text, now):
    devices = list(SensorDevice.objects.filter(active=True).order_by("code")[:21])
    if not devices:
        return _result("No hay sensores activos registrados.", "sensor", now,
                       [_source("Monitoreo", "/monitoreo/")], stale=True)
    exact = _match_exact(text, devices)
    if len(exact) > 1 or (not exact and len(devices) > 1):
        options = ", ".join(device.code for device in devices[:10])
        return _result(f"Hay varios sensores: {options}. Indica el código del dispositivo.", "ambiguous", now)
    device = exact[0] if exact else devices[0]
    latest = SensorReading.objects.filter(device=device, status=SensorReading.Status.VALID).select_related(
        "assignment__location").annotate(effective_at=Coalesce("cycle_started_at", "received_at")).order_by(
        "-effective_at", "-pk").first()
    url = f"/monitoreo/?device={quote(device.code)}"
    if not latest:
        return _result(f"{device.code} no tiene mediciones válidas registradas.", "sensor", now,
                       [_source(f"Monitoreo · {device.code}", url)], stale=True)
    age = (now - latest.effective_at).total_seconds()
    stale = age > 180
    zone = latest.assignment.location.name if latest.assignment else "zona no registrada"
    warning = "Es una medición antigua; no describe necesariamente el estado actual." if stale else "Medición reciente."
    answer = (f"{device.code} en {zone}: {latest.temperature_c} °C y {latest.humidity_percent} % de humedad. "
              f"Ciclo {latest.reading_id}, medido {_stamp(latest.effective_at)}, recibido {_stamp(latest.received_at)}. {warning}")
    return _result(answer, "sensor", now, [_source(f"Monitoreo · {device.code}", url)], stale=stale)


def _alert_answer(text, now):
    if _has(text, ("umbral", "limite")):
        devices = list(SensorDevice.objects.filter(active=True).order_by("code")[:21])
        exact = _match_exact(text, devices)
        if len(exact) > 1 or (not exact and len(devices) > 1):
            options = ", ".join(device.code for device in devices[:10])
            return _result(f"Hay varios sensores: {options}. Indica el código del dispositivo.", "ambiguous", now)
        if not devices:
            return _result("No hay sensores activos registrados.", "alerts", now,
                           [_source("Alertas", "/alertas/")])
        device = exact[0] if exact else devices[0]
        rule = AlertRule.objects.filter(device=device, ended_at__isnull=True).first()
        if not rule:
            return _result(f"{device.code} no tiene un umbral vigente registrado.", "alerts", now,
                           [_source("Alertas", "/alertas/")])
        return _result(f"Umbral vigente de {device.code}: {rule.threshold_c} °C, versión {rule.version}, desde {_stamp(rule.started_at)}. La humedad no tiene umbral inicial.",
                       "alerts", now, [_source(f"Monitoreo · {device.code}", f"/monitoreo/?device={quote(device.code)}")])
    history = _has(text, ("historial", "anteriores", "pasadas"))
    queryset = AlertEpisode.objects.select_related("device").order_by("-started_at", "-pk")
    if not history:
        queryset = queryset.filter(status=AlertEpisode.Status.ACTIVE)
    rows = list(queryset[:5])
    if not rows:
        answer = "No hay alertas registradas." if history else "No hay alertas térmicas activas."
    else:
        parts = [f"{e.device.code} en {e.location_snapshot}: {e.get_status_display().lower()}, desde {_stamp(e.started_at)}, umbral {e.threshold_snapshot} °C"
                 for e in rows]
        answer = ("Últimas alertas: " if history else "Alertas activas: ") + "; ".join(parts) + "."
        if len(rows) == 5:
            answer += " Se muestran como máximo cinco; consulta el historial para más detalles."
    sources = ([_source(f"Episodio {e.pk}", f"/alertas/?episode={e.pk}") for e in rows]
               if rows else [_source("Alertas", "/alertas/")])
    return _result(answer, "alerts", now, sources)


def answer_question(user, question, *, now=None):
    if os.environ.get("CHATBOT_ENABLED", "1") != "1":
        raise ChatUnavailable("El asistente local no está disponible.")
    if not user or not user.is_authenticated or not user.is_active or not UserProfile.objects.filter(user=user).exists():
        raise ChatInputError("La cuenta no tiene permiso para consultar el asistente.")
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION:
        raise ChatInputError("Escribe una pregunta de hasta 500 caracteres.")
    now = now or timezone.now()
    text = _normal(question.strip())
    if _has(text, ("registra", "registrar", "vende", "vender", "comprar", "modifica", "modificar",
                   "cambia", "cambiar", "actualiza", "actualizar", "borra", "borrar", "elimina", "eliminar",
                   "crea", "crear", "desactiva", "desactivar", "ignora", "agrega", "agregar", "descuenta",
                   "descontar", "suma", "resta", "ajusta", "ajustar", "configura", "configurar",
                   "pon", "poner", "sube", "baja", "reduce", "incrementa", "olvida")) or re.search(r"^(?:por favor\s+)?compra\b|\bhaz(?:me)?\s+una\s+compra\b", text):
        return _result("Este asistente solo consulta. Para cambiar datos usa los formularios de la aplicación.", "blocked_write", now)
    if re.search(r"\bhaz(?:me)?\s+(?:una\s+)?(?:venta|salida|entrada)\b", text):
        return _result("Este asistente solo consulta. Para cambiar datos usa los formularios de la aplicación.", "blocked_write", now)
    if _has(text, ("alerta", "alertas", "umbral")):
        return _alert_answer(text, now)
    if _has(text, ("temperatura", "humedad", "sensor", "sensores", "medicion", "mediciones", "lectura", "lecturas", "ambiente")):
        return _device_answer(text, now)
    if _has(text, ("movimiento", "movimientos", "historial", "venta", "ventas", "compra", "compras")):
        return _movement_answer(text, now)
    if _has(text, ("stock", "inventario", "existencia", "existencias", "disponible", "disponibles", "unidad", "unidades",
                   "producto", "productos", "presentacion", "presentaciones", "cuanto", "cuantos", "cuantas", "contiene", "representa")):
        return _stock_answer(text, now)
    return _result("Puedo consultar inventario, presentaciones, movimientos, mediciones y alertas. Por ejemplo: «¿Cuánto stock hay de BARRA-100?». Indica un código si hay varias presentaciones.", "unsupported", now)
