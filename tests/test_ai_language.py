"""
Idioma do conteúdo gerado pela IA: o cliente envia "language" e o prompt
pede as questões nesse idioma (padrão pt-BR).
"""
import unittest
from unittest.mock import patch

from api.services import ai_service


class _PromptCaptured(Exception):
    pass


def _capture_prompt(store):
    def fake_call(messages, **_kwargs):
        store.append(messages[-1]["content"])
        raise _PromptCaptured()
    return fake_call


class TestNormalizeLanguage(unittest.TestCase):

    def test_supported_codes_pass_through(self):
        self.assertEqual(ai_service.normalize_language("pt-BR"), "pt-BR")
        self.assertEqual(ai_service.normalize_language("en"), "en")

    def test_regional_variants_map_to_base(self):
        self.assertEqual(ai_service.normalize_language("en-US"), "en")
        self.assertEqual(ai_service.normalize_language("pt-PT"), "pt-BR")
        self.assertEqual(ai_service.normalize_language("PT"), "pt-BR")

    def test_unknown_or_empty_falls_back_to_portuguese(self):
        for value in ("", None, "xx", "fr-FR", "<script>"):
            self.assertEqual(ai_service.normalize_language(value), "pt-BR")


class TestPromptLanguage(unittest.TestCase):

    def setUp(self):
        self.prompts = []
        patches = [
            patch.object(ai_service, "_call_openrouter", side_effect=_capture_prompt(self.prompts)),
            patch.object(ai_service, "check_ai_token_quota", return_value=0),
            patch.object(ai_service, "GEMINI_API_KEY", "test-key"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_topic_prompt_uses_requested_language(self):
        with self.assertRaises(_PromptCaptured):
            ai_service.generate_quiz_by_topic("Idioma teste en", num_questions=1, language="en")
        self.assertIn("inglês (English, en)", self.prompts[-1])
        self.assertNotIn("Português do Brasil", self.prompts[-1])

    def test_topic_prompt_defaults_to_portuguese(self):
        with self.assertRaises(_PromptCaptured):
            ai_service.generate_quiz_by_topic("Idioma teste pt", num_questions=1)
        self.assertIn("Português do Brasil (pt-BR)", self.prompts[-1])

    def test_remix_prompt_uses_requested_language(self):
        question = {"section": "Lógica", "question": "Quanto é 2+2?", "options": ["3", "4", "5", "6"]}
        with self.assertRaises(_PromptCaptured):
            ai_service.remix_questions_by_ai([question], language="en")
        self.assertIn("inglês (English, en)", self.prompts[-1])

    def test_file_prompt_uses_requested_language(self):
        with self.assertRaises(_PromptCaptured):
            ai_service.parse_and_structure_questions_with_ai("Texto de estudo sobre frações.", language="en")
        self.assertIn("inglês (English, en)", self.prompts[-1])


if __name__ == "__main__":
    unittest.main()
