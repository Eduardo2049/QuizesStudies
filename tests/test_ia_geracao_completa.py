"""
Simulado por tema completo, fiel ao tema e sem parte lenta segurando o resto.

Cobre o que apareceu em produção ("enade computação 2022", 5 questões, convidado):
1. Título: tira "Parte N" e volta ao tema quando a IA troca a prova (ENEM no lugar de ENADE)
   ou esquece o ano; paráfrases do assunto continuam valendo.
2. Prompt: manda seguir a prova e o ano do tema; cada parte recebe um foco diferente.
3. Faltou questão (repetidas entre partes, parte que falhou): um pedido extra só com as que
   faltam, mostrando as que já existem; o simulado sai com o número pedido.
4. Pedido em dobro: se uma parte não responde em AI_HEDGE_AFTER_SECONDS, um segundo pedido vai
   (de preferência a outro provedor) e vale o primeiro que responder.
5. Resultado e resposta da API dizem quantas questões foram pedidas e quantas vieram; a
   mensagem não esconde a diferença; o diagnóstico mostra as últimas gerações.
"""

import json
import threading
import time
import unittest
from unittest.mock import patch

from api.repositories.ai_job_repository import AIJobRepository, summarize_recent_generation
from api.services import ai_service


def _quiz_json(numbers, title="Simulado ENADE Computação 2022") -> str:
    return json.dumps(
        {
            "title": title,
            "questions": [
                {
                    "id": i,
                    "section": "S",
                    "question": f"Questão {n}: qual conceito de computação explica o caso {n}?",
                    "options": ["Primeira opção", "Segunda opção", "Terceira opção", "Quarta opção"],
                    "answer": 0,
                    "explanation": "A primeira opção é a correta pelo conceito central.",
                }
                for i, n in enumerate(numbers, start=1)
            ],
        },
        ensure_ascii=False,
    )


class _GenerationCase(unittest.TestCase):
    def setUp(self):
        patches = [
            patch.object(ai_service, "ai_configured", return_value=True),
            patch.object(ai_service, "check_ai_token_quota"),
            patch.object(ai_service.ai_job_repo, "cache_get", return_value=None),
            patch.object(ai_service.ai_job_repo, "cache_set"),
            patch.dict(ai_service._quiz_generation_cache, clear=True),
            patch.object(ai_service, "_topic_speed_profile", return_value=(3, 10)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)


class TestQuizTitle(unittest.TestCase):
    topic = "enade computação 2022"

    def test_wrong_exam_falls_back_to_the_topic(self):
        title = ai_service._clean_quiz_title("Simulado ENEM Computação 2022 - Parte 1", self.topic)
        self.assertEqual(title, "Simulado: ENADE Computação 2022")

    def test_part_number_is_removed(self):
        for raw in (
            "Simulado ENADE de Computação 2022 (Parte 2 de 3)",
            "Simulado ENADE de Computação 2022 - Parte 1",
            "Parte 3: Simulado ENADE de Computação 2022",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(ai_service._clean_quiz_title(raw, self.topic), "Simulado ENADE de Computação 2022")

    def test_missing_year_or_exam_falls_back(self):
        self.assertEqual(
            ai_service._clean_quiz_title("Simulado ENADE de Computação", self.topic),
            "Simulado: ENADE Computação 2022",
        )
        self.assertEqual(
            ai_service._clean_quiz_title("Banco de Dados e Redes 2022", self.topic),
            "Simulado: ENADE Computação 2022",
        )

    def test_words_containing_part_are_kept(self):
        self.assertEqual(
            ai_service._clean_quiz_title("Apart 3 Estudos ENADE 2022", self.topic), "Apart 3 Estudos ENADE 2022"
        )

    def test_paraphrase_of_the_subject_is_kept(self):
        self.assertEqual(
            ai_service._clean_quiz_title("Simulado de Lógica Proposicional", "Raciocínio Lógico"),
            "Simulado de Lógica Proposicional",
        )

    def test_english_topic_title(self):
        self.assertEqual(ai_service._clean_quiz_title("", "ENADE 2022", "en"), "Quiz: ENADE 2022")


class TestTopicPrompt(unittest.TestCase):
    def test_prompt_keeps_the_exam_named_in_the_topic(self):
        prompt = ai_service._build_topic_prompt("enade computação 2022", 3, "Difícil", "", "pt-BR")
        self.assertIn("O tema cita ENADE 2022", prompt)
        self.assertIn("Não troque por outra prova", prompt)
        self.assertIn("sem mencionar partes", prompt)
        self.assertNotIn("ENEM", prompt)  # citar outra prova como exemplo puxaria a IA para ela

    def test_topic_without_exam_keeps_the_generic_rule(self):
        prompt = ai_service._build_topic_prompt("Ótica geométrica", 3, "Médio", "", "pt-BR")
        self.assertNotIn("O tema cita", prompt)
        self.assertIn("Não troque por outra prova", prompt)

    def test_each_part_gets_a_different_focus(self):
        prompts = [
            ai_service._build_topic_prompt("enade computação 2022", 3, "Difícil", "", "pt-BR", i, 3)
            for i in (1, 2, 3)
        ]
        focuses = [p.split("Nesta parte, priorize ", 1)[1].split(",")[0] for p in prompts]
        self.assertEqual(len(set(focuses)), 3)
        self.assertIn("parte 2 de 3", prompts[1])

    def test_single_part_has_no_part_text(self):
        prompt = ai_service._build_topic_prompt("enade computação 2022", 5, "Difícil", "", "pt-BR")
        self.assertNotIn("Esta é a parte", prompt)


class TestCompleteQuiz(_GenerationCase):
    def test_duplicates_between_parts_are_replaced_by_a_top_up(self):
        # O caso de produção: 5 pedidas em partes de 3 + 2, a parte 2 repete duas da parte 1
        prompts = []
        lock = threading.Lock()

        def fake_call_ai(messages, temperature, max_tokens, timeout=75, prefer_different_from=None, **kwargs):
            content = messages[-1]["content"]
            with lock:
                prompts.append(content)
            if "Não repita" in content:
                return _quiz_json([7, 8]), "gpt-6-luna", {}, "OpenAI"
            if "parte 2 de 2" in content:
                return _quiz_json([1, 2]), "gpt-6-luna", {}, "OpenAI"
            return _quiz_json([1, 2, 3], title="Simulado ENEM Computação 2022 - Parte 1"), "gpt-6-luna", {}, "OpenAI"

        with patch.object(ai_service, "_call_ai", side_effect=fake_call_ai):
            result = ai_service.generate_quiz_by_topic("enade computação 2022", num_questions=5, difficulty="Difícil")

        self.assertEqual(len(result["questions"]), 5)
        self.assertEqual([q["id"] for q in result["questions"]], [1, 2, 3, 4, 5])
        self.assertEqual(result["title"], "Simulado: ENADE Computação 2022")
        self.assertEqual(result["requested"], 5)
        gen = result["generation"]
        self.assertEqual(gen["delivered"], 5)
        self.assertEqual(gen["duplicates_removed"], 2)
        self.assertTrue(gen["topup"])
        topup_prompt = next(p for p in prompts if "Não repita" in p)
        self.assertIn("exatamente 2 questões", topup_prompt)
        self.assertIn("Questão 1:", topup_prompt)
        ai_service.ai_job_repo.cache_set.assert_called_once()

    def test_failed_part_is_covered_by_the_top_up(self):
        def fake_call_ai(messages, temperature, max_tokens, timeout=75, prefer_different_from=None, **kwargs):
            content = messages[-1]["content"]
            if "Não repita" in content:
                return _quiz_json([4, 5]), "m", {}, "OpenAI"
            if "parte 2 de 2" in content:
                raise ai_service.AIServiceError("O serviço de IA está ocupado agora.")
            return _quiz_json([1, 2, 3]), "m", {}, "OpenAI"

        with patch.object(ai_service, "_call_ai", side_effect=fake_call_ai):
            result = ai_service.generate_quiz_by_topic("enade computação 2022", num_questions=5)
        self.assertEqual(len(result["questions"]), 5)
        self.assertEqual(result["generation"]["failed_parts"], 1)
        self.assertEqual(result["generation"]["errors"], ["O serviço de IA está ocupado agora."])

    def test_incomplete_result_is_returned_but_not_cached(self):
        def fake_call_ai(messages, temperature, max_tokens, timeout=75, prefer_different_from=None, **kwargs):
            content = messages[-1]["content"]
            if "Não repita" in content:
                raise ai_service.AIServiceError("O serviço de IA está ocupado agora.")
            if "parte 2 de 2" in content:
                return _quiz_json([1, 2]), "m", {}, "OpenAI"
            return _quiz_json([1, 2, 3]), "m", {}, "OpenAI"

        with patch.object(ai_service, "_call_ai", side_effect=fake_call_ai):
            result = ai_service.generate_quiz_by_topic("enade computação 2022", num_questions=5)
        self.assertEqual(len(result["questions"]), 3)
        self.assertEqual(result["generation"]["delivered"], 3)
        ai_service.ai_job_repo.cache_set.assert_not_called()

    def test_top_up_is_skipped_when_time_is_up(self):
        calls = []

        def fake_call_ai(messages, temperature, max_tokens, timeout=75, prefer_different_from=None, **kwargs):
            calls.append(messages[-1]["content"])
            return _quiz_json([1, 2, 3]), "m", {}, "OpenAI"

        with (
            patch.object(ai_service, "_call_ai", side_effect=fake_call_ai),
            patch.object(ai_service, "_TOPUP_TIME_BUDGET_SECONDS", 0),
        ):
            result = ai_service.generate_quiz_by_topic("enade computação 2022", num_questions=5)
        self.assertEqual(len(result["questions"]), 3)
        self.assertFalse(result["generation"]["topup"])
        self.assertEqual(len(calls), 2)


class TestHedgedRequest(_GenerationCase):
    def test_slow_part_gets_a_second_request_and_the_fastest_wins(self):
        calls = []
        lock = threading.Lock()
        release = threading.Event()
        self.addCleanup(release.set)

        def fake_call_ai(messages, temperature, max_tokens, timeout=75, prefer_different_from=None, **kwargs):
            with lock:
                calls.append(prefer_different_from)
                first = len(calls) == 1
            if first:
                release.wait(5)  # o primeiro pedido fica preso
                return _quiz_json([1, 2, 3]), "lento", {}, "OpenAI"
            return _quiz_json([1, 2, 3]), "rapido", {}, "Groq"

        openai = ai_service.Provider("codex", "OpenAI", "https://api.openai.com/v1", "sk-x", ("gpt-6-luna",))
        started = time.monotonic()
        with (
            patch.object(ai_service, "_call_ai", side_effect=fake_call_ai),
            patch.object(ai_service, "AI_HEDGE_AFTER_SECONDS", 0.1),
            patch.object(ai_service, "_configured_providers", return_value=[openai]),
        ):
            result = ai_service.generate_quiz_by_topic("enade computação 2022", num_questions=3)
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(result["model"], "rapido")
        self.assertEqual(result["generation"]["hedged_parts"], 1)
        self.assertEqual(calls[1], openai.label)

    def test_fast_part_makes_a_single_request(self):
        calls = []

        def fake_call_ai(messages, temperature, max_tokens, timeout=75, prefer_different_from=None, **kwargs):
            calls.append(1)
            return _quiz_json([1, 2, 3]), "m", {}, "OpenAI"

        with (
            patch.object(ai_service, "_call_ai", side_effect=fake_call_ai),
            patch.object(ai_service, "AI_HEDGE_AFTER_SECONDS", 5),
        ):
            result = ai_service.generate_quiz_by_topic("enade computação 2022", num_questions=3)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["generation"]["hedged_parts"], 0)

    def test_both_requests_failing_raises_the_error(self):
        def fake_call_ai(messages, temperature, max_tokens, timeout=75, prefer_different_from=None, **kwargs):
            time.sleep(0.2)
            raise ai_service.AIServiceError("O serviço de IA está ocupado agora.")

        with (
            patch.object(ai_service, "_call_ai", side_effect=fake_call_ai),
            patch.object(ai_service, "AI_HEDGE_AFTER_SECONDS", 0.05),
        ):
            with self.assertRaises(ai_service.AIServiceError):
                ai_service.generate_quiz_by_topic("enade computação 2022", num_questions=3)


class TestControllerMessage(unittest.TestCase):
    def _run(self, delivered: int, requested: int):
        from api.controllers.quiz_controller import QuizController

        questions = [
            {"id": i, "question_number": i, "section": "S", "question": f"Q{i}?", "options": ["a", "b"],
             "answer": 0, "explanation": "e", "context": ""}
            for i in range(1, delivered + 1)
        ]
        fake = {"title": "Simulado: ENADE Computação 2022", "questions": questions, "requested": requested,
                "generation": {"requested": requested, "delivered": delivered}, "model": "m", "provider": "OpenAI"}
        controller = QuizController.__new__(QuizController)
        with patch("api.services.ai_service.generate_quiz_by_topic", return_value=fake):
            return controller.generate_quiz_by_topic("enade computação 2022", num_questions=requested, persist=False)

    def test_short_quiz_says_how_many_came(self):
        data = self._run(3, 5)["data"]
        self.assertEqual(data["question_count"], 3)
        self.assertEqual(data["requested_count"], 5)
        self.assertIn("com 3 de 5 questões pedidas", data["message"])
        self.assertEqual(data["generation"]["delivered"], 3)

    def test_complete_quiz_keeps_the_usual_message(self):
        data = self._run(5, 5)["data"]
        self.assertIn("gerado com 5 questões.", data["message"])


class TestRecentGenerations(unittest.TestCase):
    def test_summary_of_one_generation(self):
        item = summarize_recent_generation(12.34, {
            "question_count": "3", "provider": "OpenAI", "model": "gpt-6-luna",
            "generation": {"requested": 5, "parts": 2, "failed_parts": 1, "duplicates_removed": 2,
                           "discarded": {"cross_check": 1, "invalid_options_count": 1}, "topup": True,
                           "hedged_parts": 1, "errors": ["ocupado"]},
        })
        self.assertEqual(item["seconds"], 12.3)
        self.assertEqual((item["delivered"], item["requested"]), (3, 5))
        self.assertEqual(item["discarded"], 2)
        self.assertTrue(item["topup"])
        self.assertEqual(item["errors"], ["ocupado"])

    def test_old_results_without_telemetry(self):
        item = summarize_recent_generation(4, {"question_count": 5, "provider": "Groq"})
        self.assertEqual((item["delivered"], item["requested"], item["parts"]), (5, 5, 0))

    def test_memory_fallback_lists_the_latest_first(self):
        repo = AIJobRepository()
        with patch("api.repositories.ai_job_repository.get_cursor", side_effect=RuntimeError("sem banco")):
            for n, job_id in enumerate(("11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222")):
                repo.start(job_id, "guest", "g", "generate", "h")
                repo._jobs[job_id]["created_ts"] = time.time() - 100 + n
                repo.finish(job_id, {"data": {"question_count": 3 + n, "provider": "OpenAI",
                                              "generation": {"requested": 5}}})
            stats = repo.generation_stats(24)
        self.assertEqual([r["delivered"] for r in stats["recent"]], [4, 3])
        self.assertEqual(stats["recent"][0]["requested"], 5)


class TestDifficultCompleteAndFastGuest(_GenerationCase):
    def test_difficult_questions_receive_higher_max_tokens_headroom(self):
        self.assertGreaterEqual(ai_service._topic_part_max_tokens(3, "Difícil"), 1950)
        self.assertGreaterEqual(ai_service._topic_part_max_tokens(2, "Difícil"), 1600)
        self.assertGreater(
            ai_service._topic_part_max_tokens(5, "Difícil"),
            ai_service._topic_part_max_tokens(5, "Médio"),
        )

    def test_topup_splits_missing_5_of_8_into_parallel_chunks_and_delivers_8(self):
        call_index = 0
        lock = threading.Lock()
        topup_qtys: list[int] = []

        def fake_part(clean_topic, qty, diff, context_str, lang, client_ip=None,
                      part_index=None, total_parts=None, cross_check=False, avoid_questions=None):
            nonlocal call_index
            with lock:
                call_index += 1
                idx = call_index
                if avoid_questions:
                    topup_qtys.append(qty)
            # Nas 3 partes iniciais ([3, 3, 2]), 2 falham (deixando só 3 de 8)
            if not avoid_questions and idx in (2, 3):
                raise ai_service.AIServiceError("resposta cortada")
            start = idx * 10
            qs = json.loads(_quiz_json(range(start, start + qty)))["questions"]
            return {
                "title": "Simulado ENADE Computação 2022",
                "questions": qs,
                "usage": {"total_tokens": 300},
                "model": "gpt-6-luna",
                "provider": "OpenAI",
                "verified_count": 0,
                "requested": qty,
                "discarded": {},
                "hedged": False,
                "seconds": 1.0,
            }

        with patch.object(ai_service, "_generate_topic_part", side_effect=fake_part):
            res = ai_service.generate_quiz_by_topic(
                topic="enade computação 2022",
                num_questions=8,
                difficulty="Difícil",
            )

        self.assertEqual(len(res["questions"]), 8)
        self.assertEqual(res["generation"]["delivered"], 8)
        self.assertTrue(res["generation"]["topup"])
        # As 5 questões que faltaram foram divididas em [3, 2] em vez de 1 chamada grande de 5
        self.assertEqual(sorted(topup_qtys), [2, 3])

    def test_guest_status_uses_single_batch_query_and_skips_new_guest_key(self):
        from api.services.guest_service import GuestService

        class _CountingRepo:
            def __init__(self):
                self.batch_calls = []
                self.single_calls = []

            def get_usages(self, keys, window_seconds):
                self.batch_calls.append(list(keys))
                return {k: 1 if ":id:" in k else 2 for k in keys}

            def get_usage(self, key, window_seconds):
                self.single_calls.append(key)
                return 0

        repo = _CountingRepo()
        svc = GuestService(repo=repo, limit=3, ip_limit=10, window_seconds=86400)

        # Convidado existente: 1 única consulta em lote (ip + guest_id)
        st = svc.status("guest-abc", "1.2.3.4")
        self.assertEqual(len(repo.batch_calls), 1)
        self.assertEqual(len(repo.single_calls), 0)
        self.assertEqual(st["used"], 1)
        self.assertEqual(st["remaining"], 2)

        # Convidado recém-criado: pula guest_key e consulta só o IP
        st_new = svc.status("guest-novo", "1.2.3.4", is_new=True)
        self.assertEqual(len(repo.batch_calls), 1)
        self.assertEqual(repo.single_calls, ["guest_ai:ip:1.2.3.4"])
        self.assertEqual(st_new["used"], 0)
        self.assertEqual(st_new["remaining"], 3)


if __name__ == "__main__":
    unittest.main()
