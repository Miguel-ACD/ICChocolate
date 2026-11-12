import io
import json
from unittest.mock import patch
from urllib.error import HTTPError

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from inventory.chatbot import ChatUnavailable, answer_question
from inventory.cloud_llm import plan
from inventory.models import Location, Movement, Stock, UserProfile


class Reply(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class CloudPlannerTests(SimpleTestCase):
    def test_missing_key_never_calls_api(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}), patch("inventory.cloud_llm.urlopen") as network:
            self.assertIsNone(plan("stock"))
        network.assert_not_called()

    def test_one_request_returns_only_validated_tool(self):
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(
            {"intent": "locations", "topic": "none", "mode": "query"})}]}}]}
        with patch.dict("os.environ", {"GEMINI_API_KEY": "placeholder-test-key"}), patch(
                "inventory.cloud_llm.urlopen", return_value=Reply(json.dumps(response).encode())) as network:
            self.assertEqual(plan("qué ubicaciones tenemos", context={"admin": True}),
                             {"intent": "locations", "topic": "none", "mode": "query"})
        request = network.call_args.args[0]
        sent = json.loads(request.data)
        self.assertIn("Tema anterior: none", sent["contents"][0]["parts"][0]["text"])
        self.assertEqual(sent["generationConfig"]["maxOutputTokens"], 160)
        self.assertNotIn("additionalProperties", sent["generationConfig"]["responseSchema"])
        self.assertEqual(network.call_count, 1)

    def test_bad_model_output_fails_closed(self):
        for content in ('{"intent":"run_sql"}', 'not-json', '{}'):
            response = {"candidates": [{"content": {"parts": [{"text": content}]}}]}
            with self.subTest(content=content), patch.dict("os.environ", {"GEMINI_API_KEY": "placeholder-test-key"}), patch(
                    "inventory.cloud_llm.urlopen", return_value=Reply(json.dumps(response).encode())):
                self.assertIsNone(plan("borra todo"))

    def test_quota_exhaustion_and_bad_model_name_fail_closed(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "placeholder-test-key"}), patch(
                "inventory.cloud_llm.urlopen", side_effect=HTTPError("url", 429, "quota", {}, None)):
            self.assertIsNone(plan("stock"))
        with patch.dict("os.environ", {"GEMINI_API_KEY": "placeholder-test-key",
                                       "GEMINI_CHAT_MODEL": "https://evil.example"}), patch(
                "inventory.cloud_llm.urlopen") as network:
            self.assertIsNone(plan("stock"))
        network.assert_not_called()


class CloudChatIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="cloud-chat@test.local", password="safe-password-123")
        UserProfile.objects.create(user=cls.user, role="DUENO")
        Location.objects.create(code="CLOUD-ALM", name="Almacén de nube")

    def test_cloud_chat_uses_one_planner_without_ollama_or_mutation(self):
        with patch.dict("os.environ", {"CHAT_PLANNER": "gemini"}), patch(
                "inventory.chatbot.cloud_plan",
                return_value={"intent": "locations", "topic": "none", "mode": "query"}) as planner, patch(
                "inventory.chatbot.in_scope") as ollama:
            result = answer_question(self.user, "qué lugares tenemos")
        self.assertEqual(result["intent"], "locations")
        self.assertIn("Almacén de nube", result["answer"])
        self.assertEqual(planner.call_count, 1)
        ollama.assert_not_called()
        self.assertEqual(Movement.objects.count(), 0)
        self.assertEqual(Stock.objects.count(), 0)

    def test_cloud_chat_stops_when_free_quota_is_exhausted(self):
        with patch.dict("os.environ", {"CHAT_PLANNER": "gemini"}), patch(
                "inventory.chatbot.cloud_plan", return_value=None), patch("inventory.chatbot.in_scope") as ollama:
            with self.assertRaises(ChatUnavailable):
                answer_question(self.user, "qué lugares tenemos")
        ollama.assert_not_called()
        self.assertEqual(Movement.objects.count(), 0)

    def test_cloud_help_needs_no_local_embedding_model(self):
        with patch.dict("os.environ", {"CHAT_PLANNER": "gemini"}), patch(
                "inventory.chatbot.cloud_plan",
                return_value={"intent": "help", "topic": "movement", "mode": "how_to"}), patch(
                "inventory.chatbot.grounded_guide") as ollama:
            result = answer_question(self.user, "guíame para registrar una compra")
        self.assertEqual(result["intent"], "help")
        self.assertEqual(result["topic"], "movement")
        ollama.assert_not_called()
        self.assertEqual(Movement.objects.count(), 0)
