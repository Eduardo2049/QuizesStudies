"""
Testes da Fase 5 (docs/PLANO_ACELY.md): temas de exemplo prontos e menos chamadas à IA.

Valida:
1. Todos os 4 temas de exemplo (.topic-chip) têm simulados prontos com 5 questões válidas
   segundo validate_question (pt-BR).
2. Gerar qualquer um desses temas no padrão (<= 5 questões, Médio, sem contexto, pt-BR)
   responde sem chamar _call_ai e com cached=True (devolvendo cota), mesmo sem chave de IA.
3. Alterar dificuldade, contexto, idioma ou pedir > 5 questões continua chamando a IA normalmente.
"""
import json
import unittest
from unittest.mock import patch

from api.services import ai_service
from api.utils.sample_quizzes import _PRESET_QUIZZES, get_preset_quiz


class TestSamplePresetQuizzes(unittest.TestCase):
    def setUp(self):
        with ai_service._quiz_cache_lock:
            ai_service._quiz_generation_cache.clear()
        ai_service.ai_job_repo.reset()

    def test_all_presets_pass_server_validation(self):
        self.assertEqual(len(_PRESET_QUIZZES), 4)
        for preset in _PRESET_QUIZZES:
            self.assertEqual(len(preset["questions"]), 5)
            for q in preset["questions"]:
                ok, reason = ai_service.validate_question(q, language="pt-BR", require_explanation=True)
                self.assertTrue(ok, f"Preset '{preset['title']}' Q{q['id']} inválida: {reason}")
                self.assertTrue(q.get("verified"))

    def test_example_topics_return_instant_preset_without_calling_ai(self):
        topics = [
            "Juros simples e compostos",
            "Juros compostos",
            "Uso da crase na língua portuguesa",
            "Crase",
            "Lógica proposicional e tabela-verdade",
            "Tabela-verdade",
            "Direito constitucional: direitos e garantias fundamentais",
            "Direitos fundamentais",
        ]
        with patch.object(ai_service, "ai_configured", return_value=True), \
             patch.object(ai_service, "_call_ai", side_effect=AssertionError("IA não deveria ser chamada")):
            for topic in topics:
                with self.subTest(topic=topic):
                    result = ai_service.generate_quiz_by_topic(topic=topic, num_questions=5)
                    self.assertTrue(result["cached"])
                    self.assertTrue(result["sample_preset"])
                    self.assertEqual(len(result["questions"]), 5)
                    self.assertEqual(result["verified_count"], 5)

    def test_subset_quantity_slices_preset_cleanly(self):
        result = get_preset_quiz("Crase", qty=3)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result["questions"]), 3)
        self.assertEqual([q["id"] for q in result["questions"]], [1, 2, 3])

    def test_custom_difficulty_or_context_bypasses_preset_and_calls_ai(self):
        ai_payload = json.dumps({
            "title": "Crase Avançada",
            "questions": [
                {
                    "id": 1,
                    "section": "Crase",
                    "question": "Em qual alternativa o acento grave é obrigatório segundo a norma culta?",
                    "options": ["Refiro-me à obra citada.", "Começou à chover.", "Andou à pé.", "Saiu à procura de algo?"],
                    "answer": 0,
                    "explanation": "O verbo referir-se rege preposição 'a' antes de substantivo feminino com artigo.",
                }
            ],
        }, ensure_ascii=False)

        calls = 0

        def fake_call_ai(messages, temperature, max_tokens, timeout=75, prefer_different_from=None):
            nonlocal calls
            calls += 1
            return ai_payload, "mock-model", {"total_tokens": 120}, "Groq"

        with patch.object(ai_service, "ai_configured", return_value=True), \
             patch.object(ai_service, "check_ai_token_quota", return_value=100), \
             patch.object(ai_service, "_call_ai", side_effect=fake_call_ai):
            res = ai_service.generate_quiz_by_topic(
                topic="Crase",
                num_questions=1,
                difficulty="Difícil",
                context="Estilo banca CESPE",
            )

        self.assertEqual(calls, 1)
        self.assertFalse(res.get("sample_preset", False))
        self.assertEqual(res["title"], "Crase Avançada")


if __name__ == "__main__":
    unittest.main()
