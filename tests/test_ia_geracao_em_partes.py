"""
Testes da Fase 3 (docs/PLANO_ACELY.md): geração em partes com progresso.

Valida:
1. Divisão em partes de até 5 questões para pedidos > 5 (e chamada única para <= 5).
2. Execução paralela limitada a 3 workers simultâneos (TOPIC_CHUNK_MAX_WORKERS).
3. Registro de progresso via callback on_progress(done, total) e em AIJobRepository.
4. Remoção de enunciados repetidos entre partes (normalizando acentos, caixa e pontuação)
   e renumeração sequencial 1..N.
5. Resiliência quando parte isolada falha mas outras entregam questões válidas, e
   propagação de erro quando todas as partes falham.
"""
import json
import threading
import time
import unittest
from unittest.mock import patch

from api.repositories.ai_job_repository import AIJobRepository
from api.services import ai_service


def _make_part_payload(prefix: str, count: int, duplicate_first: str | None = None) -> str:
    questions = []
    for i in range(1, count + 1):
        text = duplicate_first if (i == 1 and duplicate_first) else f"{prefix} questão {i}?"
        questions.append({
            "id": i,
            "section": f"Seção {prefix}",
            "context": "",
            "question": text,
            "options": ["Opção A", "Opção B", "Opção C", "Opção D"],
            "answer": 1,
            "explanation": f"Explicação da questão {prefix}-{i}.",
        })
    return json.dumps({"title": f"Simulado {prefix}", "questions": questions}, ensure_ascii=False)


class TestChunkPlanningAndDedup(unittest.TestCase):
    def test_plan_question_chunks(self):
        self.assertEqual(ai_service._plan_question_chunks(3), [3])
        self.assertEqual(ai_service._plan_question_chunks(5), [5])
        self.assertEqual(ai_service._plan_question_chunks(8), [5, 3])
        self.assertEqual(ai_service._plan_question_chunks(12), [5, 5, 2])
        self.assertEqual(ai_service._plan_question_chunks(20), [5, 5, 5, 5])

    def test_deduplicate_questions_normalizes_and_renumbers(self):
        raw = [
            {"id": 1, "question_number": 1, "question": "O que é Crase?", "options": ["A", "B"], "answer": 0},
            {"id": 2, "question_number": 2, "question": "  o que e crase?! ", "options": ["A", "B"], "answer": 0},
            {"id": 3, "question_number": 3, "question": "Qual o uso do acento grave?", "options": ["A", "B"], "answer": 1},
        ]
        deduped = ai_service._deduplicate_questions(raw)
        self.assertEqual(len(deduped), 2)
        self.assertEqual([q["id"] for q in deduped], [1, 2])
        self.assertEqual([q["question_number"] for q in deduped], [1, 2])
        self.assertEqual(deduped[0]["question"], "O que é Crase?")
        self.assertEqual(deduped[1]["question"], "Qual o uso do acento grave?")


class TestParallelChunkedGeneration(unittest.TestCase):
    def setUp(self):
        with ai_service._quiz_cache_lock:
            ai_service._quiz_generation_cache.clear()
        ai_service.ai_job_repo.reset()

    def test_20_questions_splits_into_4_parts_with_max_3_workers_and_progress(self):
        active = 0
        max_active = 0
        prompts_seen = []
        lock = threading.Lock()

        def fake_call_ai(messages, temperature, max_tokens, timeout=75):
            nonlocal active, max_active
            prompt = messages[0]["content"]
            with lock:
                active += 1
                max_active = max(max_active, active)
                prompts_seen.append(prompt)
            time.sleep(0.03)
            # Identifica o número da parte no prompt ("parte X de 4")
            part_tag = "P"
            for idx in range(1, 5):
                if f"parte {idx} de 4" in prompt:
                    part_tag = f"Parte{idx}"
                    break
            with lock:
                active -= 1
            return (
                _make_part_payload(part_tag, 5),
                "mock-model",
                {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
                "mock-provider",
            )

        progress_events = []
        with patch.object(ai_service, "ai_configured", return_value=True), \
             patch.object(ai_service, "check_ai_token_quota", return_value=100), \
             patch.object(ai_service, "_call_ai", side_effect=fake_call_ai):
            result = ai_service.generate_quiz_by_topic(
                topic="Direito Constitucional Avançado",
                num_questions=20,
                difficulty="Médio",
                on_progress=lambda done, total: progress_events.append((done, total)),
            )

        self.assertEqual(len(result["questions"]), 20)
        self.assertEqual([q["id"] for q in result["questions"]], list(range(1, 21)))
        self.assertEqual(result["parts"], {"done": 4, "total": 4})
        self.assertEqual(result["usage"], {"prompt_tokens": 400, "completion_tokens": 800, "total_tokens": 1200})
        self.assertLessEqual(max_active, ai_service.TOPIC_CHUNK_MAX_WORKERS)
        self.assertEqual(progress_events[0], (0, 4))
        self.assertEqual(progress_events[-1], (4, 4))
        self.assertEqual(len(progress_events), 5)
        self.assertEqual(len(prompts_seen), 4)
        for idx in range(1, 5):
            self.assertTrue(any(f"parte {idx} de 4" in p for p in prompts_seen))

    def test_deduplicates_repeated_questions_across_parts(self):
        def fake_call_ai(messages, temperature, max_tokens, timeout=75):
            prompt = messages[0]["content"]
            if "parte 1 de 2" in prompt:
                payload = _make_part_payload("P1", 5, duplicate_first="Qual é a capital do Brasil?")
            else:
                payload = _make_part_payload("P2", 5, duplicate_first="qual e a capital do brasil")
            return payload, "mock-model", {"total_tokens": 150}, "mock"

        with patch.object(ai_service, "ai_configured", return_value=True), \
             patch.object(ai_service, "check_ai_token_quota", return_value=100), \
             patch.object(ai_service, "_call_ai", side_effect=fake_call_ai):
            result = ai_service.generate_quiz_by_topic(topic="Geografia do Brasil", num_questions=10)

        self.assertEqual(len(result["questions"]), 9)
        self.assertEqual([q["id"] for q in result["questions"]], list(range(1, 10)))

    def test_partial_part_failure_still_returns_valid_questions(self):
        def fake_call_ai(messages, temperature, max_tokens, timeout=75):
            prompt = messages[0]["content"]
            if "parte 2 de 3" in prompt:
                raise ai_service.AIServiceError("timeout na parte 2")
            tag = "P1" if "parte 1 de 3" in prompt else "P3"
            return _make_part_payload(tag, 5), "mock-model", {"total_tokens": 100}, "mock"

        with patch.object(ai_service, "ai_configured", return_value=True), \
             patch.object(ai_service, "check_ai_token_quota", return_value=100), \
             patch.object(ai_service, "_call_ai", side_effect=fake_call_ai):
            result = ai_service.generate_quiz_by_topic(topic="Física Mecânica", num_questions=15)

        self.assertEqual(len(result["questions"]), 10)
        self.assertEqual(result["parts"], {"done": 2, "total": 3})

    def test_all_parts_fail_raises_ai_service_error(self):
        with patch.object(ai_service, "ai_configured", return_value=True), \
             patch.object(ai_service, "check_ai_token_quota", return_value=100), \
             patch.object(ai_service, "_call_ai", side_effect=ai_service.AIServiceError("indisponível")):
            with self.assertRaises(ai_service.AIServiceError):
                ai_service.generate_quiz_by_topic(topic="Química Orgânica", num_questions=10)

    def test_five_or_fewer_questions_uses_single_call(self):
        calls = 0

        def fake_call_ai(messages, temperature, max_tokens, timeout=75):
            nonlocal calls
            calls += 1
            self.assertNotIn("parte 1 de", messages[0]["content"])
            return _make_part_payload("Single", 5), "mock-model", {"total_tokens": 120}, "mock"

        with patch.object(ai_service, "ai_configured", return_value=True), \
             patch.object(ai_service, "check_ai_token_quota", return_value=100), \
             patch.object(ai_service, "_call_ai", side_effect=fake_call_ai):
            result = ai_service.generate_quiz_by_topic(topic="Lógica", num_questions=5)

        self.assertEqual(calls, 1)
        self.assertEqual(len(result["questions"]), 5)
        self.assertNotIn("parts", result)


class TestAIJobProgressRepository(unittest.TestCase):
    def test_update_progress_persists_in_memory_and_resets_on_retry(self):
        repo = AIJobRepository()
        job_id = "11111111-2222-4333-8444-555555555555"

        with patch("api.repositories.ai_job_repository.get_cursor", side_effect=RuntimeError("no db")):
            created, _ = repo.start(job_id, "user", "42", "generate", "hash-abc")
            self.assertTrue(created)

            repo.update_progress(job_id, 2, 4)
            job = repo.get(job_id)
            self.assertEqual(job["status"], "running")
            self.assertEqual(job["progress"], {"done": 2, "total": 4})

            repo.fail(job_id, "falhou")
            created_again, _ = repo.start(job_id, "user", "42", "generate", "hash-abc")
            self.assertTrue(created_again)
            restarted = repo.get(job_id)
            self.assertIsNone(restarted["progress"])


if __name__ == "__main__":
    unittest.main()
