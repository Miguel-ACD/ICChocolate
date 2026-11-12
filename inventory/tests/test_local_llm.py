"""The local model may select a fixed query, never provide data or commands."""

import io
import json
from unittest.mock import patch
from urllib.error import URLError

from django.test import SimpleTestCase

from inventory.local_llm import classify, plan


class _Reply(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class LocalLLMTests(SimpleTestCase):
    def test_disabled_model_does_not_call_network(self):
        with patch.dict("os.environ", {"OLLAMA_CHAT_ENABLED": "0"}), patch("inventory.local_llm.urlopen") as request:
            self.assertIsNone(classify("stock"))
        request.assert_not_called()

    def test_only_known_intents_are_accepted(self):
        with patch.dict("os.environ", {"OLLAMA_CHAT_ENABLED": "1"}):
            for intent in ("catalog", "stock", "locations", "movements", "sensor", "alerts", "help", "identity", "unsupported"):
                with self.subTest(intent=intent), patch("inventory.local_llm.urlopen", return_value=_Reply(
                        json.dumps({"response": json.dumps({"intent": intent})}).encode())):
                    self.assertEqual(classify("pregunta"), intent)
            for response in ('{"intent":"run_sql"}', '{"intent":"stock","answer":"inventado"}',
                             'this is not json', '{}'):
                with self.subTest(response=response), patch("inventory.local_llm.urlopen", return_value=_Reply(
                        json.dumps({"response": response}).encode())):
                    expected = "stock" if '"intent":"stock"' in response else None
                    self.assertEqual(classify("pregunta"), expected)

    def test_transport_failure_and_untrusted_endpoint_fall_back(self):
        with patch.dict("os.environ", {"OLLAMA_CHAT_ENABLED": "1", "OLLAMA_URL": "https://example.com"}), patch(
                "inventory.local_llm.urlopen") as request:
            self.assertIsNone(classify("stock"))
        request.assert_not_called()
        with patch.dict("os.environ", {"OLLAMA_CHAT_ENABLED": "1"}), patch(
                "inventory.local_llm.urlopen", side_effect=URLError("offline")):
            self.assertIsNone(classify("stock"))

    def test_plan_accepts_only_allowlisted_topic_and_context(self):
        reply = json.dumps({"response": json.dumps({"intent": "help", "topic": "remove"})}).encode()
        with patch.dict("os.environ", {"OLLAMA_CHAT_ENABLED": "1"}), patch(
                "inventory.local_llm.urlopen", return_value=_Reply(reply)) as request:
            self.assertEqual(plan("¿Cómo retiro una barra?", context="product"),
                             {"intent": "help", "topic": "remove", "mode": "query"})
        sent = json.loads(request.call_args.args[0].data)
        self.assertIn("Tema anterior: product", sent["prompt"])
        self.assertEqual(sent["format"]["additionalProperties"], False)
