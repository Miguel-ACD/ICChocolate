import io
import json
from unittest.mock import patch

from django.test import SimpleTestCase

from inventory.chat_scope import APP_AREAS, GUIDE_AREAS, OTHER_AREAS, grounded_guide, in_scope


class _Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ChatScopeTests(SimpleTestCase):
    def _vectors(self, query):
        vectors = [[1.0, 0.0]] * len(APP_AREAS) + [[0.0, 1.0]] * len(OTHER_AREAS) + [query]
        return _Reply(json.dumps({"embeddings": vectors}).encode())

    def test_semantic_contrast_accepts_app_and_rejects_other_topics(self):
        with patch.dict("os.environ", {"OLLAMA_CHAT_ENABLED": "1"}):
            with patch("inventory.chat_scope.urlopen", return_value=self._vectors([1.0, 0.0])):
                self.assertTrue(in_scope("¿Qué tenemos?"))
            with patch("inventory.chat_scope.urlopen", return_value=self._vectors([0.0, 1.0])):
                self.assertFalse(in_scope("¿Qué tenemos?"))

    def test_malformed_embeddings_and_untrusted_endpoint_fail_closed(self):
        with patch.dict("os.environ", {"OLLAMA_CHAT_ENABLED": "1"}):
            with patch("inventory.chat_scope.urlopen", return_value=_Reply(b'{"embeddings": []}')):
                self.assertIsNone(in_scope("stock"))
            with patch("inventory.chat_scope.urlopen", return_value=self._vectors([float("nan"), 0.0])):
                self.assertIsNone(in_scope("stock"))
        with patch.dict("os.environ", {"OLLAMA_CHAT_ENABLED": "1", "OLLAMA_URL": "https://example.com"}), patch(
                "inventory.chat_scope.urlopen") as network:
            self.assertIsNone(in_scope("stock"))
        network.assert_not_called()

    def test_guide_choice_is_grounded_or_corrected_by_group_similarity(self):
        topics = list(GUIDE_AREAS)
        vectors = [[1.0, 0.0] if topic == "alert" else [0.0, 1.0] if topic == "remove"
                   else [0.0, 0.0] for topic in topics]
        with patch("inventory.chat_scope._embed", return_value=vectors + [[1.0, 0.0]]):
            self.assertEqual(grounded_guide("cambiar umbral", "remove"), "alert")
            self.assertEqual(grounded_guide("cambiar umbral", "alert"), "alert")
