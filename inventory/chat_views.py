"""Session-protected web and JSON entry points for local read-only queries."""

import json

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods, require_POST

from .chatbot import ChatInputError, ChatUnavailable, answer_question
from .services import is_owner
from .views import profile_required


def _private(response):
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@profile_required
@require_http_methods(["GET", "POST"])
def chat_page(request):
    question = request.POST.get("question", "") if request.method == "POST" else ""
    answer = None
    error = ""
    status = 200
    if request.method == "POST":
        try:
            answer = answer_question(request.user, question)
        except ChatInputError as exc:
            error = str(exc)
        except (ChatUnavailable, DatabaseError):
            error = "El asistente no está disponible ahora. Inventario y Monitoreo siguen accesibles."
            status = 503
    return _private(render(request, "inventory/chat.html", {
        "question": question[:500], "answer": answer, "error": error, "owner": is_owner(request.user),
    }, status=status))


@login_required
@profile_required
@require_POST
def chat_api(request):
    if not request.content_type.startswith("application/json"):
        return _private(JsonResponse({"error": "Envía JSON."}, status=415))
    if len(request.body) > 4096:
        return _private(JsonResponse({"error": "La solicitud es demasiado grande."}, status=413))
    try:
        payload = json.loads(request.body)
        if not isinstance(payload, dict):
            raise ValueError
        answer = answer_question(request.user, payload.get("question"))
    except (ValueError, TypeError, ChatInputError):
        return _private(JsonResponse({"error": "Escribe una pregunta válida de hasta 500 caracteres."}, status=400))
    except (ChatUnavailable, DatabaseError):
        return _private(JsonResponse({"error": "El asistente no está disponible ahora."}, status=503))
    return _private(JsonResponse(answer))
