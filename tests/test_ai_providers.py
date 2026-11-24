"""
Vários provedores de IA em sequência (docs/ARQUITETURA.md, seção da IA).

Cobre:
1. Sem chave do Groq/Gemini/Cerebras, só o OpenRouter é usado (comportamento de antes).
2. Groq na frente responde sem chegar ao OpenRouter; payload no formato OpenAI com
   resposta em partes e raciocínio baixo no gpt-oss.
3. Limite diário (429 "per day") de um provedor passa ao próximo sem erro para a pessoa e
   pausa o provedor até a virada do dia.
4. Chave recusada (401) pula o provedor; orçamento diário esgotado pula sem fazer o pedido.
5. Modelo que recusa response_format é tentado de novo sem ele.
6. Todos sem cota: a mensagem é a do limite diário.
"""
import json
import time
import unittest
from collections import defaultdict
from unittest.mock import MagicMock, patch

from api.services import ai_service

GOOD_JSON = '{"questions": [{"question": "Q?", "options": ["A", "B"], "answer": 0}]}'


def _stream_ok(content=GOOD_JSON, usage=None):
    resp = MagicMock()
    resp.status_code, resp.ok = 200, True
    resp.headers = {"Content-Type": "text/event-stream"}
    lines = [b"data: " + json.dumps({"choices": [{"delta": {"content": content}}]}).encode()]
    if usage:
        lines.append(b"data: " + json.dumps({"choices": [], "usage": usage}).encode())
    lines.append(b"data: [DONE]")
    resp.iter_lines.side_effect = lambda chunk_size=1024: iter(lines)
    return resp


def _responses_stream_ok(content=GOOD_JSON, usage=None):
    resp = MagicMock()
    resp.status_code, resp.ok = 200, True
    resp.headers = {"Content-Type": "text/event-stream"}
    lines = [
        b"event: response.output_text.delta",
        b"data: " + json.dumps({"type": "response.output_text.delta", "delta": content}).encode(),
        b"event: response.completed",
        b"data: " + json.dumps({"type": "response.completed", "response": {"usage": usage or {}}}).encode(),
    ]
    resp.iter_lines.side_effect = lambda chunk_size=1024: iter(lines)
    return resp


def _error(status, raw):
    resp = MagicMock()
    resp.status_code, resp.ok, resp.text = status, False, raw
    return resp


class FakeBudgetRepo:
    """Contagem em memória com is_blocked/record, como o RateLimitRepository."""

    def __init__(self):
        self.entries = defaultdict(list)

    def is_blocked(self, key, limit, window_seconds):
        used = sum(c for ts, c in self.entries[key] if ts > time.time() - window_seconds)
        return used >= limit, 0

    def record(self, key, cost=1):
        self.entries[key].append((time.time(), cost))

    def check_and_record(self, key, limit, window_seconds, cost=1):
        return True, 0


class _ProvidersTestCase(unittest.TestCase):
    codex_key = ""
    groq_key = "gsk-test"
    gemini_key = "gem-test"

    def setUp(self):
        self.session = MagicMock()
        self.budget = FakeBudgetRepo()
        patches = [
            patch.object(ai_service, "_get_http_session", return_value=self.session),
            patch.object(ai_service, "_check_daily_ai_budget"),
            patch.object(ai_service, "rate_limit_repo", self.budget),
            patch.object(ai_service, "AI_PROVIDERS", ["codex", "groq", "gemini", "cerebras", "openrouter"]),
            patch.object(ai_service, "CODEX_API_KEY", self.codex_key),
            patch.object(ai_service, "CODEX_BASE_URL", "https://api.openai.com/v1"),
            patch.object(ai_service, "CODEX_MODELS", ["gpt-6-luna", "gpt-4o-mini"]),
            # Datas de desligamento fixas nos testes (a tabela real muda com o tempo)
            patch.dict(ai_service.OPENAI_MODEL_SHUTDOWNS, {}, clear=True),
            patch.object(ai_service, "CODEX_API_MODE", "auto"),
            patch.object(ai_service, "GROQ_API_KEY", self.groq_key),
            patch.object(ai_service, "GROQ_MODELS", ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]),
            patch.object(ai_service, "GEMINI_API_KEY", self.gemini_key),
            patch.object(ai_service, "GEMINI_MODELS", ["gemini-3.5-flash-lite"]),
            patch.object(ai_service, "CEREBRAS_API_KEY", ""),
            patch.object(ai_service, "OPENROUTER_API_KEY", "sk-or-test"),
            patch.dict(ai_service._model_cooldown, clear=True),
            patch.dict(ai_service._provider_pause, clear=True),
            patch.object(ai_service, "_no_reasoning_param", set()),
            patch.object(ai_service, "_no_json_mode", set()),
            patch.object(ai_service, "_no_temperature_param", set()),
            patch.object(ai_service, "_force_responses_api", set()),
            patch.object(ai_service, "_force_chat_api", set()),
            patch.object(ai_service, "_no_stream", set()),
            patch.object(ai_service, "_setup_logged", True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.openrouter = patch.object(
            ai_service, "_call_openrouter", return_value=(GOOD_JSON, "free/model:free", {})
        ).start()
        self.addCleanup(patch.stopall)

    def call(self):
        return ai_service._call_ai([{"role": "user", "content": "Responda em JSON"}], 0.3, 500, timeout=30)

    def posted(self):
        return [(c.args[0], c.kwargs["json"]) for c in self.session.post.call_args_list]


class TestOnlyOpenRouter(_ProvidersTestCase):
    groq_key = ""
    gemini_key = ""

    def test_without_other_keys_behaves_like_before(self):
        content, model, _usage, provider = self.call()
        self.assertEqual((content, model, provider), (GOOD_JSON, "free/model:free", "OpenRouter"))
        self.session.post.assert_not_called()
        self.assertEqual([p.name for p in ai_service._configured_providers()], ["openrouter"])

    def test_no_provider_at_all(self):
        with patch.object(ai_service, "OPENROUTER_API_KEY", ""):
            self.assertFalse(ai_service.ai_configured())
            with self.assertRaises(ai_service.AIServiceError):
                self.call()


class TestProviderOrder(_ProvidersTestCase):

    def test_groq_answers_first(self):
        self.session.post.return_value = _stream_ok(usage={"total_tokens": 1200})
        content, model, _usage, provider = self.call()
        self.assertEqual((provider, model, content), ("Groq", "openai/gpt-oss-120b", GOOD_JSON))
        self.openrouter.assert_not_called()
        url, payload = self.posted()[0]
        self.assertEqual(url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertEqual(payload["max_tokens"], 750)
        self.assertNotIn("response_format", payload)
        headers = self.session.post.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer gsk-test")
        # Tokens usados entram no orçamento do modelo
        self.assertEqual(sum(c for _, c in self.budget.entries["ai_budget:groq:openai/gpt-oss-120b:tokens"]), 1200)

    def test_daily_limit_moves_to_next_provider_and_pauses(self):
        daily = '{"error": {"message": "Rate limit reached ... tokens per day (TPD): Limit 200000"}}'
        self.session.post.side_effect = [_error(429, daily), _error(429, daily), _stream_ok()]
        _c, model, _u, provider = self.call()
        self.assertEqual((provider, model), ("Gemini", "gemini-3.5-flash-lite"))
        url, payload = self.posted()[2]
        self.assertTrue(url.startswith("https://generativelanguage.googleapis.com/v1beta/openai"))
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertIn("groq", ai_service._provider_pause)

        # Próximo pedido vai direto ao Gemini, sem tentar o Groq
        self.session.post.reset_mock(side_effect=True)
        self.session.post.return_value = _stream_ok()
        _c, _m, _u, provider = self.call()
        self.assertEqual(provider, "Gemini")
        self.assertEqual(len(self.session.post.call_args_list), 1)

    def test_rejected_key_skips_provider(self):
        self.session.post.side_effect = [_error(401, '{"error": "invalid api key"}'), _stream_ok()]
        _c, _m, _u, provider = self.call()
        self.assertEqual(provider, "Gemini")

    def test_spent_budget_skips_without_request(self):
        for model in ("openai/gpt-oss-120b", "openai/gpt-oss-20b"):
            self.budget.record(f"ai_budget:groq:{model}:tokens", ai_service.GROQ_DAILY_TOKENS)
        self.session.post.return_value = _stream_ok()
        _c, _m, _u, provider = self.call()
        self.assertEqual(provider, "Gemini")
        self.assertEqual(len(self.session.post.call_args_list), 1)

    def test_model_that_rejects_json_mode_is_retried_without_it(self):
        with patch.object(ai_service, "GROQ_API_KEY", ""):
            self.session.post.side_effect = [
                _error(400, '{"error": {"message": "response_format is not supported"}}'), _stream_ok()]
            _c, _m, _u, provider = self.call()
        self.assertEqual(provider, "Gemini")
        first, second = (payload for _url, payload in self.posted())
        self.assertIn("response_format", first)
        self.assertNotIn("response_format", second)

    def test_falls_back_to_openrouter(self):
        self.session.post.return_value = _error(503, "unavailable")
        _c, model, _u, provider = self.call()
        self.assertEqual((provider, model), ("OpenRouter", "free/model:free"))
        self.assertFalse(self.openrouter.call_args.kwargs["count_budget"])

    def test_everyone_out_of_quota_reports_daily_limit(self):
        daily = '{"error": {"message": "requests per day exceeded"}}'
        self.session.post.return_value = _error(429, daily)
        self.openrouter.side_effect = ai_service.AIServiceError(ai_service.AI_DAILY_LIMIT_MESSAGE)
        with self.assertRaises(ai_service.AIServiceError) as ctx:
            self.call()
        self.assertEqual(str(ctx.exception), ai_service.AI_DAILY_LIMIT_MESSAGE)
        # Todos pausados: o próximo pedido nem chega aos provedores
        self.session.post.reset_mock()
        with self.assertRaises(ai_service.AIServiceError):
            self.call()
        self.session.post.assert_not_called()


class TestGenerateUsesProviderName(_ProvidersTestCase):

    def test_topic_quiz_records_provider(self):
        self.session.post.return_value = _stream_ok(json.dumps({"title": "T", "questions": [
            {"question": "Q?", "options": ["A", "B", "C", "D"], "answer": 2, "explanation": "C."}]}))
        with patch.object(ai_service, "check_ai_token_quota"), \
             patch.object(ai_service.ai_job_repo, "cache_get", return_value=None), \
             patch.object(ai_service.ai_job_repo, "cache_set"):
            result = ai_service.generate_quiz_by_topic("Tema multiprovedor único", num_questions=1)
        self.assertEqual(result["provider"], "Groq")
        self.assertEqual(result["questions"][0]["answer"], 2)


def _json_ok(content=GOOD_JSON, usage=None):
    """Resposta inteira (sem streaming), como a OpenAI manda com "stream": false."""
    resp = MagicMock()
    resp.status_code, resp.ok = 200, True
    resp.headers = {"Content-Type": "application/json"}
    resp.json.return_value = {"choices": [{"message": {"content": content}}], "usage": usage or {}}
    return resp


class TestCodexProvider(_ProvidersTestCase):
    codex_key = "sk-codex-test"

    def test_codex_runs_first_via_chat_completions(self):
        self.session.post.return_value = _stream_ok(usage={"total_tokens": 900})
        content, model, _usage, provider = self.call()
        self.assertEqual((provider, model, content), ("OpenAI", "gpt-6-luna", GOOD_JSON))
        url, payload = self.posted()[0]
        self.assertEqual(url, "https://api.openai.com/v1/chat/completions")
        self.assertEqual(payload["max_completion_tokens"], 750)
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertTrue(payload["stream"])
        # Modelo de raciocínio da OpenAI só aceita a temperatura padrão: nem é enviada
        self.assertNotIn("temperature", payload)
        self.assertEqual(self.session.post.call_args.kwargs["headers"]["Authorization"], "Bearer sk-codex-test")
        self.assertEqual(sum(c for _, c in self.budget.entries["ai_budget:codex:gpt-6-luna:tokens"]), 900)

    def test_codex_model_uses_responses_api(self):
        with patch.object(ai_service, "CODEX_MODELS", ["gpt-5-codex-mini"]):
            self.session.post.return_value = _responses_stream_ok(usage={"total_tokens": 640})
            content, model, _usage, provider = self.call()
        self.assertEqual((provider, model, content), ("OpenAI", "gpt-5-codex-mini", GOOD_JSON))
        url, payload = self.posted()[0]
        self.assertEqual(url, "https://api.openai.com/v1/responses")
        self.assertEqual(payload["max_output_tokens"], 750)
        self.assertEqual(payload["reasoning"], {"effort": "low"})
        self.assertEqual(payload["text"], {"format": {"type": "json_object"}})
        self.assertEqual(sum(c for _, c in self.budget.entries["ai_budget:codex:gpt-5-codex-mini:tokens"]), 640)

    def test_auto_mode_switches_from_chat_to_responses_on_404(self):
        with patch.object(ai_service, "CODEX_MODELS", ["gpt-6-luna"]):
            self.session.post.side_effect = [
                _error(404, '{"error": {"message": "This is not a chat model. Use /v1/responses instead."}}'),
                _responses_stream_ok(),
            ]
            _c, model, _u, provider = self.call()
        self.assertEqual((provider, model), ("OpenAI", "gpt-6-luna"))
        self.assertEqual(self.posted()[0][0], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(self.posted()[1][0], "https://api.openai.com/v1/responses")

    def test_model_rejecting_temperature_is_retried_without_it(self):
        with patch.object(ai_service, "CODEX_MODELS", ["gpt-4o-mini"]):
            self.session.post.side_effect = [
                _error(400, '{"error": {"message": "Unsupported parameter: temperature"}}'),
                _stream_ok(),
            ]
            _c, _m, _u, provider = self.call()
        self.assertEqual(provider, "OpenAI")
        self.assertIn("temperature", self.posted()[0][1])
        self.assertNotIn("temperature", self.posted()[1][1])

    def test_unverified_org_gets_the_whole_answer_without_streaming(self):
        refused = (
            '{"error": {"message": "Your organization must be verified to stream this model. Please go to: '
            'https://platform.openai.com/settings/organization/general and click on Verify Organization.", '
            '"type": "invalid_request_error", "param": "stream", "code": "unsupported_value"}}'
        )
        self.session.post.side_effect = [_error(400, refused), _json_ok(), _json_ok()]
        _c, model, _u, provider = self.call()
        self.assertEqual((provider, model), ("OpenAI", "gpt-6-luna"))
        self.assertTrue(self.posted()[0][1]["stream"])
        self.assertFalse(self.posted()[1][1]["stream"])
        self.assertFalse(self.session.post.call_args_list[1].kwargs["stream"])
        # Os próximos pedidos do mesmo modelo já vão sem streaming, sem gastar um 400
        self.call()
        self.assertEqual(self.session.post.call_count, 3)
        self.assertFalse(self.posted()[2][1]["stream"])

    def test_account_without_credits_skips_openai_after_one_call(self):
        no_credits = (
            '{"error": {"message": "You exceeded your current quota, please check your plan and billing '
            'details.", "type": "insufficient_quota", "code": "insufficient_quota"}}'
        )
        self.session.post.side_effect = [_error(429, no_credits), _stream_ok()]
        with patch.object(ai_service, "_log_ops") as log:
            _c, model, _u, provider = self.call()
        self.assertEqual((provider, model), ("Groq", "openai/gpt-oss-120b"))
        # Não tenta o gpt-4o-mini: a conta inteira está sem crédito
        self.assertEqual([p["model"] for _u, p in self.posted()], ["gpt-6-luna", "openai/gpt-oss-120b"])
        self.assertIn("codex", ai_service._provider_pause)
        logged = " ".join(str(c.args[0]) for c in log.call_args_list)
        self.assertIn("sem créditos", logged)
        self.assertIn("insufficient_quota", logged)

    def test_missing_model_moves_to_the_next_openai_model(self):
        missing = (
            '{"error": {"message": "The model `gpt-6-luna` does not exist or you do not have access to it.", '
            '"type": "invalid_request_error", "code": "model_not_found"}}'
        )
        self.session.post.side_effect = [_error(404, missing), _stream_ok()]
        _c, model, _u, provider = self.call()
        self.assertEqual((provider, model), ("OpenAI", "gpt-4o-mini"))
        self.assertGreater(ai_service._model_cooldown["codex:gpt-6-luna"], time.time() + 5 * 3600)

    def test_retired_model_is_skipped_without_a_request(self):
        with patch.dict(ai_service.OPENAI_MODEL_SHUTDOWNS, {"gpt-6-luna": "2020-01-01"}):
            self.session.post.return_value = _stream_ok()
            _c, model, _u, provider = self.call()
        self.assertEqual((provider, model), ("OpenAI", "gpt-4o-mini"))
        self.assertEqual([p["model"] for _u, p in self.posted()], ["gpt-4o-mini"])

    def test_invalid_key_log_names_the_real_variable(self):
        self.session.post.side_effect = [
            _error(401, '{"error": {"message": "Incorrect API key provided: sk-proj-abcd****wxyz", '
                        '"code": "invalid_api_key"}}'),
            _stream_ok(),
        ]
        with patch.object(ai_service, "_log_ops") as log:
            self.call()
        logged = " ".join(str(c.args[0]) for c in log.call_args_list)
        self.assertIn("OPENAI_API_KEY", logged)
        self.assertNotIn("sk-proj-abcd", logged)

    def test_codex_failure_falls_back_to_free_providers(self):
        self.session.post.side_effect = [
            _error(401, '{"error": {"message": "Incorrect API key provided"}}'),
            _stream_ok(),
        ]
        _c, model, _u, provider = self.call()
        self.assertEqual((provider, model), ("Groq", "openai/gpt-oss-120b"))

    def test_openai_alias_and_priority_order(self):
        from api.utils.config import _parse_ai_providers, _split_ai_providers

        self.assertEqual(_parse_ai_providers("openai"), ["codex"])
        self.assertEqual(_parse_ai_providers("openai,google,groq"), ["codex", "gemini", "groq"])
        self.assertEqual(_parse_ai_providers("openai,codex,openrouter"), ["codex", "openrouter"])
        self.assertEqual(_split_ai_providers("opeanai, groq"), (["groq"], ["opeanai"]))


class TestAIDiagnostics(_ProvidersTestCase):
    codex_key = "sk-codex-test"

    def test_warns_when_key_is_set_but_provider_is_out_of_the_order(self):
        with patch.object(ai_service, "AI_PROVIDERS", ["groq", "openrouter"]):
            warnings = ai_service.ai_setup_warnings()
        self.assertTrue(any("OPENAI_API_KEY" in w and "AI_PROVIDERS" in w for w in warnings), warnings)

    def test_warns_about_unknown_names_legacy_variable_and_expiring_models(self):
        soon = (time.gmtime(time.time() + 10 * 86400))
        with patch.object(ai_service, "AI_PROVIDERS_IGNORED", ["opeanai"]), \
             patch.object(ai_service, "CODEX_MODELS_SOURCE", "CODEX_MODELS"), \
             patch.dict(ai_service.OPENAI_MODEL_SHUTDOWNS, {"gpt-4o-mini": time.strftime("%Y-%m-%d", soon)}):
            warnings = " | ".join(ai_service.ai_setup_warnings())
        self.assertIn("opeanai", warnings)
        self.assertIn("CODEX_MODELS", warnings)
        self.assertIn("gpt-4o-mini: sai do ar", warnings)

    def test_warns_when_every_openai_model_is_retired(self):
        with patch.dict(ai_service.OPENAI_MODEL_SHUTDOWNS, {"gpt-6-luna": "2020-01-01", "gpt-4o-mini": "2020-01-01"}):
            warnings = " | ".join(ai_service.ai_setup_warnings())
        self.assertIn("nenhum modelo de OPENAI_MODELS está ativo", warnings)

    def test_low_daily_cap_is_flagged(self):
        with patch.object(ai_service, "AI_DAILY_CALL_LIMIT", 40):
            warnings = " | ".join(ai_service.ai_setup_warnings())
        self.assertIn("AI_DAILY_CALL_LIMIT=40", warnings)

    def test_diagnostics_lists_order_and_never_exposes_keys(self):
        diag = ai_service.ai_diagnostics()
        self.assertEqual(diag["order"][0], "openai")
        openai = next(p for p in diag["providers"] if p["name"] == "openai")
        self.assertTrue(openai["has_key"])
        self.assertEqual(openai["key_env"], "OPENAI_API_KEY")
        self.assertEqual([m["id"] for m in openai["models"]], ["gpt-6-luna", "gpt-4o-mini"])
        dumped = json.dumps(diag)
        for secret in ("sk-codex-test", "gsk-test", "gem-test", "sk-or-test"):
            self.assertNotIn(secret, dumped)

    def test_probe_reports_each_provider(self):
        # Os provedores são testados ao mesmo tempo: a resposta depende do endereço, não da ordem
        def answer(url, **kwargs):
            if url.startswith("https://api.openai.com"):
                return _error(429, '{"error": {"message": "quota", "code": "insufficient_quota"}}')
            return _stream_ok('{"ok": true}')

        self.session.post.side_effect = answer
        results = {r["provider"]: r for r in ai_service.probe_ai_providers()}
        self.assertFalse(results["openai"]["ok"])
        self.assertTrue(any("sem créditos" in line for line in results["openai"]["log"]))
        self.assertTrue(results["groq"]["ok"])
        self.assertEqual(results["groq"]["model"], "openai/gpt-oss-120b")
        self.assertTrue(results["gemini"]["ok"])
        self.assertTrue(results["openrouter"]["ok"])

    def test_error_summary_redacts_keys(self):
        summary = ai_service._provider_error_summary(
            '{"error": {"message": "Incorrect API key provided: sk-proj-123456789", "code": "invalid_api_key"}}'
        )
        self.assertEqual(summary, "invalid_api_key: Incorrect API key provided: [chave]")
        self.assertEqual(ai_service._provider_error_summary("<html><b>Bad gateway</b></html>"), "Bad gateway")


class TestAIUserRateLimitPerMinute(unittest.TestCase):

    def test_limits_ai_calls_per_minute_per_user_and_isolates_users(self):
        from api.handlers import quiz_handler

        limiter = quiz_handler.RateLimiter(limit=2, window_seconds=60, repo=None)
        user_a = {"id": 101}
        user_b = {"id": 202}
        with patch.object(quiz_handler, "AI_USER_REQUESTS_PER_MINUTE", 2), \
             patch.object(quiz_handler, "_rl_ai_user_per_minute", limiter):
            quiz_handler.QuizHandler._enforce_ai_user_rpm(user_a, None, "10.0.0.1")
            quiz_handler.QuizHandler._enforce_ai_user_rpm(user_a, None, "10.0.0.1")
            with self.assertRaises(ai_service.AIQuotaExceededError) as ctx:
                quiz_handler.QuizHandler._enforce_ai_user_rpm(user_a, None, "10.0.0.1")
            self.assertGreater(ctx.exception.retry_after, 0)
            self.assertIn("2 usos de IA por minuto", str(ctx.exception))
            # Outro usuário no mesmo IP mantém sua própria cota por minuto
            quiz_handler.QuizHandler._enforce_ai_user_rpm(user_b, None, "10.0.0.1")

    def test_refund_gives_the_minute_slot_back(self):
        from api.handlers import quiz_handler

        limiter = quiz_handler.RateLimiter(limit=1, window_seconds=60, repo=None)
        quota = MagicMock()
        with patch.object(quiz_handler, "AI_USER_REQUESTS_PER_MINUTE", 1), \
             patch.object(quiz_handler, "_rl_ai_user_per_minute", limiter):
            key = quiz_handler.QuizHandler._enforce_ai_user_rpm({"id": 7}, None, "10.0.0.1")
            quiz_handler.AIUseReservation(quota, key).refund()
            quota.refund.assert_called_once()
            # A vaga voltou: o próximo pedido no mesmo minuto passa
            quiz_handler.QuizHandler._enforce_ai_user_rpm({"id": 7}, None, "10.0.0.1")
            with self.assertRaises(ai_service.AIQuotaExceededError):
                quiz_handler.QuizHandler._enforce_ai_user_rpm({"id": 7}, None, "10.0.0.1")

    def test_default_per_minute_limit_is_ten(self):
        import importlib
        import os

        from api.utils import config

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AI_USER_REQUESTS_PER_MINUTE", None)
            reloaded = importlib.reload(config)
            self.assertEqual(reloaded.AI_USER_REQUESTS_PER_MINUTE, 10)
        importlib.reload(config)

    def test_zero_disables_per_minute_user_limit(self):
        from api.handlers import quiz_handler

        limiter = quiz_handler.RateLimiter(limit=1, window_seconds=60, repo=None)
        with patch.object(quiz_handler, "AI_USER_REQUESTS_PER_MINUTE", 0), \
             patch.object(quiz_handler, "_rl_ai_user_per_minute", limiter):
            for _ in range(5):
                quiz_handler.QuizHandler._enforce_ai_user_rpm({"id": 1}, None, "10.0.0.1")


if __name__ == "__main__":
    unittest.main()
