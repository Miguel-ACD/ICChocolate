"""One bounded Gemini request to choose a read-only chat tool in AWS."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .local_llm import FORMAT, INTENTS, MODES, SYSTEM, TOPICS

RESPONSE_SCHEMA = {key: value for key, value in FORMAT.items() if key != "additionalProperties"}


def plan(question, context=None):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    model = os.environ.get("GEMINI_CHAT_MODEL", "gemini-3.5-flash-lite")
    if not model or not all(character.isalnum() or character in ".-_" for character in model):
        return None
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": (
            f"Tema anterior: {context if isinstance(context, str) and context in TOPICS else 'none'}\n"
            f"Pregunta: {question}"
        )}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
            "maxOutputTokens": 160,
            "thinkingConfig": {"thinkingLevel": "low"},
        },
    }
    request = Request(endpoint, data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json", "X-goog-api-key": key,
    })
    try:
        with urlopen(request, timeout=40) as response:
            if response.status != 200:
                return None
            payload = json.load(response)
        content = "".join(part.get("text", "") for part in payload["candidates"][0]["content"]["parts"])
        choice = json.loads(content)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        return None
    if not isinstance(choice, dict) or choice.get("intent") not in INTENTS:
        return None
    topic = choice.get("topic", "none")
    mode = choice.get("mode", "query")
    return {
        "intent": choice["intent"],
        "topic": topic if topic in TOPICS else "none",
        "mode": mode if mode in MODES else "outside",
    }
