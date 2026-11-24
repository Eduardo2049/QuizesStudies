"""
Qualidade da IA (docs/ARQUITETURA.md, seção da IA): qualidade, validação e conferência de gabarito.

Valida:
1. Gabarito fora do intervalo é reprovado (não mascarado para 0).
2. Alternativas repetidas (mesmo com caixa/acento diferente) são reprovadas.
3. Idioma errado (enunciado em inglês quando pediu pt-BR, ou em português quando pediu en) é reprovado.
4. Conferência por segundo modelo (temperatura 0, sem gabarito): descarta questões em desacordo,
   marca as concordantes com verified=True e registra verified_count.
5. Preferência por segundo provedor (prefer_different_from) em _call_ai.
6. Política AI_CROSS_CHECK (account | all | off).
7. parse_and_structure_questions_with_ai valida e deduplica questões baseadas no documento.
"""
import json
import unittest
from unittest.mock import patch

from api.services import ai_service


class TestQuestionServerValidation(unittest.TestCase):
    def test_rejects_answer_out_of_range(self):
        item = {
            "question": "Qual é a capital do Brasil?",
            "options": ["São Paulo", "Brasília", "Rio de Janeiro", "Salvador"],
            "answer": 5,
            "explanation": "Brasília é a capital federal desde 1960.",
        }
        ok, reason = ai_service.validate_question(item, language="pt-BR")
        self.assertFalse(ok)
        self.assertEqual(reason, "answer_out_of_range")

        # No parser de tema, uma questão com gabarito fora do intervalo sai do simulado
        payload = json.dumps({
            "title": "Geografia",
            "questions": [
                item,
                {
                    "question": "Qual rio banha a cidade de Manaus?",
                    "options": ["Rio Negro", "Rio Tietê", "Rio Doce", "Rio Paraná"],
                    "answer": 0,
                    "explanation": "Manaus fica às margens do Rio Negro.",
                },
            ],
        }, ensure_ascii=False)
        _title, questions = ai_service._parse_topic_questions(payload, "Geografia", language="pt-BR")
        self.assertEqual(len(questions), 1)
        self.assertIn("Manaus", questions[0]["question"])

    def test_rejects_duplicate_options(self):
        item = {
            "question": "Qual alternativa descreve o uso correto da crase?",
            "options": ["Antes de palavra feminina", "antes de palavra feminina!", "Antes de verbo", "Antes de pronome"],
            "answer": 0,
            "explanation": "A crase ocorre antes de palavras femininas que aceitam artigo.",
        }
        ok, reason = ai_service.validate_question(item, language="pt-BR")
        self.assertFalse(ok)
        self.assertEqual(reason, "duplicate_options")

    def test_rejects_wrong_language_both_directions(self):
        en_question = {
            "question": "Which of the following statements about this protocol is correct according to the standard?",
            "options": ["It uses stateless requests", "It requires binary frames", "It blocks caching", "It skips headers"],
            "answer": 0,
            "explanation": "HTTP is stateless.",
        }
        ok_pt, reason_pt = ai_service.validate_question(en_question, language="pt-BR")
        self.assertFalse(ok_pt)
        self.assertEqual(reason_pt, "wrong_language")

        ok_en, reason_en = ai_service.validate_question(en_question, language="en")
        self.assertTrue(ok_en, f"deveria aceitar em inglês, mas retornou {reason_en}")

        pt_question = {
            "question": "Segundo a Constituição Federal, qual alternativa está correta sobre os direitos fundamentais?",
            "options": ["São aplicáveis de forma imediata", "Dependem sempre de decreto", "Valem apenas para empresas", "Não admitem garantias"],
            "answer": 0,
            "explanation": "Os direitos fundamentais têm aplicação imediata.",
        }
        ok_en_wrong, reason_en_wrong = ai_service.validate_question(pt_question, language="en")
        self.assertFalse(ok_en_wrong)
        self.assertEqual(reason_en_wrong, "wrong_language")


class TestCrossCheckVerification(unittest.TestCase):
    def setUp(self):
        with ai_service._quiz_cache_lock:
            ai_service._quiz_generation_cache.clear()
        ai_service.ai_job_repo.reset()

    def test_cross_check_discards_disagreed_and_marks_verified(self):
        generated_payload = json.dumps({
            "title": "Simulado de Matemática",
            "questions": [
                {
                    "id": 1,
                    "section": "Aritmética",
                    "question": "Qual é o resultado de 7 multiplicado por 8?",
                    "options": ["54", "56", "58", "64"],
                    "answer": 1,
                    "explanation": "7 x 8 = 56.",
                },
                {
                    "id": 2,
                    "section": "Aritmética",
                    "question": "Qual é a raiz quadrada exata de 81?",
                    "options": ["7", "8", "9", "10"],
                    "answer": 0,  # gabarito errado de propósito (deveria ser 2 -> "9")
                    "explanation": "Explicação incorreta.",
                },
            ],
        }, ensure_ascii=False)
        cross_check_payload = json.dumps({
            "answers": [
                {"id": 1, "answer": 1},  # concorda
                {"id": 2, "answer": 2},  # discorda
            ]
        })

        calls = []

        def fake_call_ai(messages, temperature, max_tokens, timeout=75, prefer_different_from=None):
            calls.append({
                "prompt": messages[0]["content"],
                "temperature": temperature,
                "prefer_different_from": prefer_different_from,
            })
            if len(calls) == 1:
                return generated_payload, "model-a", {"total_tokens": 300}, "Groq"
            return cross_check_payload, "model-b", {"total_tokens": 120}, "Gemini"

        with patch.object(ai_service, "ai_configured", return_value=True), \
             patch.object(ai_service, "check_ai_token_quota", return_value=100), \
             patch.object(ai_service, "_call_ai", side_effect=fake_call_ai):
            result = ai_service.generate_quiz_by_topic(
                topic="Matemática Básica",
                num_questions=2,
                cross_check=True,
            )

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["temperature"], 0.0)
        self.assertEqual(calls[1]["prefer_different_from"], "Groq")
        # O prompt de conferência não pode vazar o gabarito nem a explicação
        self.assertNotIn("Explicação incorreta", calls[1]["prompt"])
        self.assertEqual(len(result["questions"]), 1)
        self.assertTrue(result["questions"][0]["verified"])
        self.assertEqual(result["verified_count"], 1)
        self.assertEqual(result["usage"]["total_tokens"], 420)

    def test_cross_check_policy_account_all_off(self):
        with patch.object(ai_service, "AI_CROSS_CHECK", "account"):
            self.assertTrue(ai_service.should_cross_check(has_account=True))
            self.assertFalse(ai_service.should_cross_check(has_account=False))
        with patch.object(ai_service, "AI_CROSS_CHECK", "all"):
            self.assertTrue(ai_service.should_cross_check(has_account=True))
            self.assertTrue(ai_service.should_cross_check(has_account=False))
        with patch.object(ai_service, "AI_CROSS_CHECK", "off"):
            self.assertFalse(ai_service.should_cross_check(has_account=True))
            self.assertFalse(ai_service.should_cross_check(has_account=False))

    def test_parse_material_validates_and_grounds_in_document(self):
        raw_payload = json.dumps({
            "questions": [
                {
                    "id": 1,
                    "section": "Biologia",
                    "question": "Qual organela é responsável pela respiração celular segundo o texto?",
                    "options": ["Mitocôndria", "Ribossomo", "Lisossomo", "Vacúolo"],
                    "answer": 0,
                    "explanation": "O material indica que a mitocôndria realiza a respiração celular.",
                },
                {
                    "id": 2,
                    "section": "Biologia",
                    "question": "Questão inválida com gabarito fora do intervalo?",
                    "options": ["Opção 1", "Opção 2"],
                    "answer": 9,
                    "explanation": "Inválida.",
                },
            ]
        }, ensure_ascii=False)

        captured_prompt = []

        def fake_call_ai(messages, temperature, max_tokens, timeout=75, prefer_different_from=None):
            captured_prompt.append(messages[0]["content"])
            return raw_payload, "model-a", {"total_tokens": 200}, "Groq"

        with patch.object(ai_service, "check_ai_token_quota", return_value=100), \
             patch.object(ai_service, "_call_ai", side_effect=fake_call_ai):
            questions = ai_service.parse_and_structure_questions_with_ai(
                "A mitocôndria é a organela responsável pela respiração celular e produção de ATP.",
                num_questions=2,
                language="pt-BR",
            )

        self.assertIn("estritamente no documento enviado", captured_prompt[0])
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["answer"], 0)


if __name__ == "__main__":
    unittest.main()
