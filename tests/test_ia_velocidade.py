"""
Velocidade da geração por tema (meta: simulado pronto em até ~10 s com a OpenAI na frente).

Cobre:
1. Perfil de velocidade: OpenAI na frente usa partes de 3 e até 10 ao mesmo tempo; gratuitos,
   partes de 5 e até 3; AI_PART_SIZE/AI_PARALLEL_PARTS mandam; OpenAI pausada volta ao perfil livre.
2. Geração pede raciocínio "none"; gpt-oss vai com "low"; modelo que recusa "none" recebe "low"
   (sem perder o parâmetro); sem raciocínio, o limite de tokens vai sem folga.
3. OPENAI_SERVICE_TIER (Fast mode) só na OpenAI e retirado quando o modelo recusa.
4. Conferência do gabarito por parte, assim que a parte fica pronta (não espera as outras).
5. Prompt enxuto: explicação de 1 a 2 frases e JSON em uma linha, sem o campo "context".
6. Resumo dos tempos para o diagnóstico (média, p90, fatia em até 10 s, por tamanho e provedor).
"""

import json
import threading
import time
import unittest
from unittest.mock import patch

from api.repositories.ai_job_repository import AIJobRepository, summarize_generation_times
from api.services import ai_service

from tests.test_ai_providers import _error, _ProvidersTestCase, _stream_ok


def _quiz_json(qty: int, start: int = 1) -> str:
    return json.dumps(
        {
            "title": "Tema",
            "questions": [
                {
                    "id": i,
                    "section": "S",
                    "question": f"Pergunta número {start + i} sobre o tema proposto?",
                    "options": ["Primeira opção", "Segunda opção", "Terceira opção", "Quarta opção"],
                    "answer": 0,
                    "explanation": "A primeira opção é a correta pelo conceito central.",
                }
                for i in range(1, qty + 1)
            ],
        },
        ensure_ascii=False,
    )


class TestSpeedProfile(_ProvidersTestCase):
    codex_key = "sk-codex-test"

    def test_openai_first_uses_small_parts_all_at_once(self):
        self.assertEqual(ai_service._topic_speed_profile(), (3, 10))

    def test_free_providers_keep_parts_of_five_three_at_a_time(self):
        with patch.object(ai_service, "CODEX_API_KEY", ""):
            self.assertEqual(ai_service._topic_speed_profile(), (5, 3))

    def test_paused_openai_falls_back_to_the_free_profile(self):
        ai_service._provider_pause["codex"] = (time.time() + 600, "x")
        self.assertEqual(ai_service._topic_speed_profile(), (5, 3))

    def test_environment_overrides_the_profile(self):
        with patch.object(ai_service, "AI_PART_SIZE", 4), patch.object(ai_service, "AI_PARALLEL_PARTS", 6):
            self.assertEqual(ai_service._topic_speed_profile(), (4, 6))


class TestReasoningAndServiceTier(_ProvidersTestCase):
    codex_key = "sk-codex-test"

    def call(self, reasoning="low"):
        return ai_service._call_ai(
            [{"role": "user", "content": "Responda em JSON"}], 0.3, 500, timeout=30, reasoning=reasoning
        )

    def test_generation_asks_for_no_reasoning_and_no_token_headroom(self):
        self.session.post.return_value = _stream_ok()
        self.call(reasoning="none")
        payload = self.posted()[0][1]
        self.assertEqual(payload["model"], "gpt-6-luna")
        self.assertEqual(payload["reasoning_effort"], "none")
        self.assertEqual(payload["max_completion_tokens"], 500)

    def test_gpt_oss_never_receives_none(self):
        with patch.object(ai_service, "CODEX_API_KEY", ""):
            self.session.post.return_value = _stream_ok()
            self.call(reasoning="none")
        payload = self.posted()[0][1]
        self.assertEqual(payload["model"], "openai/gpt-oss-120b")
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertEqual(payload["max_tokens"], 750)

    def test_model_refusing_none_gets_low_instead_of_default(self):
        refused = (
            '{"error": {"message": "Unsupported value: \'reasoning_effort\' does not support \'none\' '
            "with this model. Supported values are: 'minimal', 'low', 'medium', and 'high'.\"}}"
        )
        with patch.object(ai_service, "CODEX_MODELS", ["gpt-5-nano"]):
            self.session.post.side_effect = [_error(400, refused), _stream_ok(), _stream_ok()]
            self.call(reasoning="none")
            self.call(reasoning="none")
        efforts = [p["reasoning_effort"] for _u, p in self.posted()]
        self.assertEqual(efforts, ["none", "low", "low"])
        self.assertNotIn("codex:gpt-5-nano", ai_service._no_reasoning_param)

    def test_service_tier_only_on_openai_and_dropped_when_refused(self):
        with (
            patch.object(ai_service, "OPENAI_SERVICE_TIER", "fast"),
            patch.object(ai_service, "_no_service_tier", set()),
        ):
            self.session.post.side_effect = [
                _error(400, '{"error": {"message": "Invalid value for service_tier for this model."}}'),
                _stream_ok(),
            ]
            _c, model, _u, provider = self.call()
        self.assertEqual((provider, model), ("OpenAI", "gpt-6-luna"))
        self.assertEqual(self.posted()[0][1]["service_tier"], "fast")
        self.assertNotIn("service_tier", self.posted()[1][1])

    def test_service_tier_is_not_sent_to_other_providers(self):
        with patch.object(ai_service, "OPENAI_SERVICE_TIER", "fast"), patch.object(ai_service, "CODEX_API_KEY", ""):
            self.session.post.return_value = _stream_ok()
            self.call()
        self.assertNotIn("service_tier", self.posted()[0][1])


class TestTopicGenerationFlow(unittest.TestCase):
    def setUp(self):
        patches = [
            patch.object(ai_service, "ai_configured", return_value=True),
            patch.object(ai_service, "check_ai_token_quota"),
            patch.object(ai_service.ai_job_repo, "cache_get", return_value=None),
            patch.object(ai_service.ai_job_repo, "cache_set"),
            patch.dict(ai_service._quiz_generation_cache, clear=True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_prompt_is_compact(self):
        prompt = ai_service._build_topic_prompt("Física", 3, "Médio", "", "pt-BR")
        self.assertIn("1 a 2 frases", prompt)
        self.assertIn("uma linha só", prompt)
        self.assertNotIn('"context"', prompt)
        self.assertNotIn("2 a 4 frases", prompt)

    def test_generation_uses_no_reasoning_and_check_uses_default(self):
        calls = []

        def fake_call_ai(messages, temperature, max_tokens, timeout=75, prefer_different_from=None, **kwargs):
            content = messages[-1]["content"]
            calls.append(("check" if "revisor rigoroso" in content else "generate", kwargs.get("reasoning")))
            if "revisor rigoroso" in content:
                return json.dumps({"answers": [{"id": i, "answer": 0} for i in range(1, 4)]}), "m", {}, "OpenAI"
            return _quiz_json(3), "m", {}, "OpenAI"

        with (
            patch.object(ai_service, "_topic_speed_profile", return_value=(3, 10)),
            patch.object(ai_service, "_call_ai", side_effect=fake_call_ai),
        ):
            result = ai_service.generate_quiz_by_topic("Ótica geométrica", num_questions=3, cross_check=True)
        self.assertEqual(calls, [("generate", "none"), ("check", None)])
        self.assertEqual(result["verified_count"], 3)

    def test_each_part_is_checked_as_soon_as_it_is_ready(self):
        # A parte 2 só termina depois que a parte 1 já foi conferida: com a conferência no fim
        # (comportamento antigo), isso nunca aconteceria e o teste estouraria o tempo.
        first_part_checked = threading.Event()
        calls = []
        lock = threading.Lock()

        def fake_call_ai(messages, temperature, max_tokens, timeout=75, prefer_different_from=None, **kwargs):
            content = messages[-1]["content"]
            if "revisor rigoroso" in content:
                ids = [int(x) for x in __import__("re").findall(r'"id": (\d+)', content)]
                is_first = '"Pergunta número 2' in content
                with lock:
                    calls.append(("check", is_first))
                if is_first:
                    first_part_checked.set()
                return json.dumps({"answers": [{"id": i, "answer": 0} for i in ids]}), "m", {}, "OpenAI"
            part = 1 if "parte 1 de" in content else 2
            with lock:
                calls.append(("generate", part))
            if part == 2:
                self.assertTrue(first_part_checked.wait(5), "a parte 1 não foi conferida antes de a 2 acabar")
                return _quiz_json(3, start=10), "m", {}, "OpenAI"
            return _quiz_json(3), "m", {}, "OpenAI"

        with (
            patch.object(ai_service, "_topic_speed_profile", return_value=(3, 10)),
            patch.object(ai_service, "_call_ai", side_effect=fake_call_ai),
        ):
            result = ai_service.generate_quiz_by_topic("Ondulatória", num_questions=6, cross_check=True)
        self.assertEqual(len(result["questions"]), 6)
        self.assertEqual(result["verified_count"], 6)
        self.assertEqual(sum(1 for kind, _ in calls if kind == "check"), 2)
        self.assertEqual([q["id"] for q in result["questions"]], [1, 2, 3, 4, 5, 6])

    def test_thirty_questions_run_as_ten_parts_at_once(self):
        active = 0
        peak = 0
        lock = threading.Lock()
        counter = {"n": 0}

        def fake_call_ai(messages, temperature, max_tokens, timeout=75, prefer_different_from=None, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                counter["n"] += 1
                start = counter["n"] * 10
            time.sleep(0.05)
            with lock:
                active -= 1
            return _quiz_json(3, start=start), "m", {}, "OpenAI"

        with (
            patch.object(ai_service, "_topic_speed_profile", return_value=(3, 10)),
            patch.object(ai_service, "_call_ai", side_effect=fake_call_ai),
        ):
            result = ai_service.generate_quiz_by_topic("Termologia", num_questions=30)
        self.assertEqual(len(result["questions"]), 30)
        self.assertEqual(result["parts"], {"done": 10, "total": 10})
        self.assertGreaterEqual(peak, 8)

    def test_prefer_different_never_puts_openrouter_ahead_of_openai(self):
        called_providers = []

        def fake_compatible(provider, messages, temperature, max_tokens, deadline, reasoning="low"):
            called_providers.append(provider.name)
            return _quiz_json(1), "gpt-6-luna", {"total_tokens": 100}

        with (
            patch.object(ai_service, "AI_PROVIDERS", ["codex", "openrouter"]),
            patch.object(ai_service, "CODEX_API_KEY", "sk-test"),
            patch.object(ai_service, "OPENROUTER_API_KEY", "sk-or-test"),
            patch.object(ai_service, "_provider_pause", {}),
            patch.object(ai_service, "_check_daily_ai_budget"),
            patch.object(ai_service, "_call_compatible", side_effect=fake_compatible),
            patch.object(ai_service, "_call_openrouter", side_effect=AssertionError("não deveria chamar openrouter")),
        ):
            _c, _m, _u, prov = ai_service._call_ai(
                [{"role": "user", "content": "ok"}], 0.0, 200, timeout=15, prefer_different_from="OpenAI"
            )
        self.assertEqual(prov, "OpenAI")
        self.assertEqual(called_providers, ["codex"])

    def test_within_budget_uses_single_batched_get_usages_call(self):
        calls = []

        class BatchRepo:
            def get_usages(self, keys, window_seconds):
                calls.append(list(keys))
                return {keys[0]: 10, keys[1]: 500}

            def is_blocked(self, *args, **kwargs):
                raise AssertionError("não deveria chamar is_blocked quando get_usages existe")

        provider = ai_service.Provider(
            "codex", "OpenAI", "https://api.openai.com/v1", "sk-test", ("gpt-6-luna",),
            daily_requests=500, daily_tokens=500_000,
        )
        with patch.object(ai_service, "rate_limit_repo", BatchRepo()):
            self.assertTrue(ai_service._within_budget(provider, "gpt-6-luna"))
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]), 2)


class TestGenerationStats(unittest.TestCase):
    def test_summary_numbers(self):
        stats = summarize_generation_times(
            [(6.0, 5, "OpenAI"), (8.0, 10, "OpenAI"), (12.0, 30, "Groq"), (-1, 5, "x"), (900, 5, "x")]
        )
        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["avg"], 8.7)
        self.assertEqual(stats["p90"], 12.0)
        self.assertEqual(stats["within_target_pct"], 67)
        self.assertEqual([b["label"] for b in stats["by_size"]], ["até 5", "6 a 10", "21 a 30"])

    def test_empty_summary(self):
        stats = summarize_generation_times([])
        self.assertEqual(stats["count"], 0)
        self.assertIsNone(stats["avg"])
        self.assertIsNone(stats["within_target_pct"])

    def test_memory_fallback_skips_ready_made_results(self):
        repo = AIJobRepository()
        with patch("api.repositories.ai_job_repository.get_cursor", side_effect=RuntimeError("sem banco")):
            for job_id, cached in (
                ("11111111-1111-4111-8111-111111111111", False),
                ("22222222-2222-4222-8222-222222222222", True),
            ):
                repo.start(job_id, "guest", "g", "generate", "h")
                repo.finish(job_id, {"data": {"question_count": 5, "provider": "OpenAI", "cached": cached}})
            stats = repo.generation_stats(24)
        self.assertEqual(stats["count"], 1)

    def test_diagnostics_include_generation_time_and_profile(self):
        with patch.object(ai_service.ai_job_repo, "generation_stats", return_value={"count": 2, "avg": 7.5}):
            diag = ai_service.ai_diagnostics()
        self.assertEqual(diag["generation_time"]["avg"], 7.5)
        self.assertIn("part_size", diag["speed_profile"])


if __name__ == "__main__":
    unittest.main()
