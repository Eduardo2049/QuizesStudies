"""
OpenRouter só com modelos gratuitos: escolha dos modelos, troca de modelo quando
um falha e leitura tolerante do JSON que os modelos gratuitos devolvem.
"""
import json
import unittest
from unittest.mock import MagicMock, patch

from api.services import ai_service

VALID_JSON = '{"questions": [{"question": "Q?", "options": ["A", "B"], "answer": 0}]}'


def _response(status=200, content=None, raw=""):
    resp = MagicMock()
    resp.status_code = status
    resp.ok = 200 <= status < 300
    resp.text = raw or (json.dumps({"choices": [{"message": {"content": content}}]}) if content is not None else "")
    resp.json.return_value = {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 10}}
    return resp


def _catalog(*models):
    resp = MagicMock()
    resp.json.return_value = {"data": list(models)}
    resp.raise_for_status.return_value = None
    return resp


def _model(model_id, context=128_000, params=("temperature", "max_tokens")):
    return {"id": model_id, "context_length": context, "supported_parameters": list(params),
            "architecture": {"output_modalities": ["text"]}}


class _FreeModelsTestCase(unittest.TestCase):

    def setUp(self):
        self.session = MagicMock()
        patches = [
            patch.object(ai_service, "_get_http_session", return_value=self.session),
            patch.object(ai_service, "_check_daily_ai_budget"),
            patch.object(ai_service, "OPENROUTER_API_KEY", "test-key"),
            patch.object(ai_service, "OPENROUTER_MAX_ATTEMPTS", 4),
            patch.object(ai_service, "OPENROUTER_DISCOVER_FREE_MODELS", True),
            patch.dict(ai_service._free_models_cache, {"fetched_at": 0.0, "models": {}}),
            patch.dict(ai_service._model_cooldown, clear=True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def call(self):
        return ai_service._call_openrouter([{"role": "user", "content": "oi"}], temperature=0.2, max_tokens=100)

    def sent_models(self):
        return [c.kwargs["json"]["model"] for c in self.session.post.call_args_list]


class TestCandidates(_FreeModelsTestCase):

    def test_only_free_models_are_ever_used(self):
        self.session.get.return_value = _catalog(
            _model("vendor/pago"), _model("vendor/gratis:free"), _model("outro/gratis:free"),
        )
        with patch.object(ai_service, "OPENROUTER_FREE_MODELS", ["vendor/pago", "outro/gratis:free"]):
            ids = [m for m, _ in ai_service._free_model_candidates()]
        self.assertEqual(ids, ["outro/gratis:free", "vendor/gratis:free"])

    def test_preferred_models_that_left_the_catalog_are_dropped(self):
        self.session.get.return_value = _catalog(_model("ativo/modelo:free"))
        with patch.object(ai_service, "OPENROUTER_FREE_MODELS", ["removido/modelo:free", "ativo/modelo:free"]):
            ids = [m for m, _ in ai_service._free_model_candidates()]
        self.assertEqual(ids, ["ativo/modelo:free"])

    def test_unsuitable_and_small_context_models_are_skipped(self):
        self.session.get.return_value = _catalog(
            _model("nvidia/rerank-vl:free"), _model("vendor/content-safety:free"),
            _model("vendor/pequeno:free", context=8_000), _model("vendor/bom:free"),
        )
        with patch.object(ai_service, "OPENROUTER_FREE_MODELS", []):
            ids = [m for m, _ in ai_service._free_model_candidates()]
        self.assertEqual(ids, ["vendor/bom:free"])

    def test_catalog_failure_falls_back_to_configured_list(self):
        self.session.get.side_effect = ConnectionError("sem rede")
        with patch.object(ai_service, "OPENROUTER_FREE_MODELS", ["a/um:free", "b/dois:free"]):
            ids = [m for m, _ in ai_service._free_model_candidates()]
        self.assertEqual(ids, ["a/um:free", "b/dois:free"])

    def test_paused_models_go_to_the_end(self):
        with patch.object(ai_service, "OPENROUTER_DISCOVER_FREE_MODELS", False), \
             patch.object(ai_service, "OPENROUTER_FREE_MODELS", ["a/um:free", "b/dois:free"]):
            ai_service._pause_model("a/um:free", 60)
            ids = [m for m, _ in ai_service._free_model_candidates()]
        self.assertEqual(ids, ["b/dois:free", "a/um:free"])


class TestFallback(_FreeModelsTestCase):

    def setUp(self):
        super().setUp()
        for p in (patch.object(ai_service, "OPENROUTER_DISCOVER_FREE_MODELS", False),
                  patch.object(ai_service, "OPENROUTER_FREE_MODELS", ["a/um:free", "b/dois:free"])):
            p.start()
            self.addCleanup(p.stop)

    def test_rate_limited_model_is_skipped_and_paused(self):
        self.session.post.side_effect = [
            _response(429, raw='{"error": {"message": "Rate limit exceeded: free-models-per-min"}}'),
            _response(200, VALID_JSON),
        ]
        content, model, _usage = self.call()
        self.assertEqual(model, "b/dois:free")
        self.assertEqual(json.loads(content)["questions"][0]["answer"], 0)
        self.assertGreater(ai_service._model_cooldown.get("a/um:free", 0), 0)

    def test_invalid_json_moves_to_next_model(self):
        self.session.post.side_effect = [_response(200, "Claro! Aqui está o simulado..."), _response(200, VALID_JSON)]
        _content, model, _usage = self.call()
        self.assertEqual(self.sent_models(), ["a/um:free", "b/dois:free"])
        self.assertEqual(model, "b/dois:free")

    def test_empty_content_moves_to_next_model(self):
        self.session.post.side_effect = [_response(200, None), _response(200, VALID_JSON)]
        _content, model, _usage = self.call()
        self.assertEqual(model, "b/dois:free")

    def test_daily_free_limit_stops_immediately(self):
        self.session.post.side_effect = [
            _response(429, raw='{"error": {"message": "Rate limit exceeded: free-models-per-day"}}'),
            _response(200, VALID_JSON),
        ]
        with self.assertRaises(ai_service.AIServiceError) as ctx:
            self.call()
        self.assertEqual(str(ctx.exception), ai_service.AI_DAILY_LIMIT_MESSAGE)
        self.assertEqual(self.session.post.call_count, 1)

    def test_data_policy_error_is_not_retried(self):
        self.session.post.side_effect = [
            _response(404, raw='{"error": {"message": "No endpoints found matching your data policy"}}'),
            _response(200, VALID_JSON),
        ]
        with self.assertRaises(ai_service.AIServiceError) as ctx:
            self.call()
        self.assertEqual(str(ctx.exception), ai_service.AI_UNAVAILABLE_MESSAGE)
        self.assertEqual(self.session.post.call_count, 1)

    def test_all_models_busy_gives_friendly_message(self):
        self.session.post.side_effect = [_response(429, raw="{}"), _response(503, raw="{}")]
        with self.assertRaises(ai_service.AIServiceError) as ctx:
            self.call()
        self.assertEqual(str(ctx.exception), ai_service.AI_BUSY_MESSAGE)

    def test_missing_key_is_generic(self):
        with patch.object(ai_service, "OPENROUTER_API_KEY", ""):
            with self.assertRaises(ai_service.AIServiceError) as ctx:
                self.call()
        self.assertEqual(str(ctx.exception), ai_service.AI_UNAVAILABLE_MESSAGE)
        self.session.post.assert_not_called()


class TestResponseFormat(_FreeModelsTestCase):

    def test_json_mode_only_for_models_that_support_it(self):
        self.session.get.return_value = _catalog(
            _model("com/json:free", params=("response_format",)), _model("sem/json:free"),
        )
        self.session.post.side_effect = [_response(429, raw="{}"), _response(200, VALID_JSON)]
        with patch.object(ai_service, "OPENROUTER_FREE_MODELS", ["com/json:free", "sem/json:free"]):
            self.call()
        first, second = (c.kwargs["json"] for c in self.session.post.call_args_list)
        self.assertEqual(first.get("response_format"), {"type": "json_object"})
        self.assertNotIn("response_format", second)


class TestReasoning(_FreeModelsTestCase):

    def test_reasoning_models_get_low_effort_and_extra_tokens(self):
        self.session.get.return_value = _catalog(
            _model("pensa/modelo:free", params=("reasoning",)), _model("direto/modelo:free"),
        )
        self.session.post.side_effect = [_response(503, raw="{}"), _response(200, VALID_JSON)]
        with patch.object(ai_service, "OPENROUTER_FREE_MODELS", ["pensa/modelo:free", "direto/modelo:free"]):
            self.call()
        thinking, direct = (c.kwargs["json"] for c in self.session.post.call_args_list)
        self.assertEqual(thinking["reasoning"], {"effort": "low", "exclude": True})
        self.assertGreater(thinking["max_tokens"], 100)
        self.assertNotIn("reasoning", direct)
        self.assertEqual(direct["max_tokens"], 100)

    def test_zdr_account_restriction_is_not_retried(self):
        self.session.post.side_effect = [
            _response(404, raw='{"error": {"message": "0 endpoints available. ZDR violation (account settings)"}}'),
            _response(200, VALID_JSON),
        ]
        with patch.object(ai_service, "OPENROUTER_DISCOVER_FREE_MODELS", False), \
             patch.object(ai_service, "OPENROUTER_FREE_MODELS", ["a/um:free", "b/dois:free"]):
            with self.assertRaises(ai_service.AIServiceError):
                self.call()
        self.assertEqual(self.session.post.call_count, 1)


class TestParseJsonResponse(unittest.TestCase):

    def test_plain_json(self):
        self.assertEqual(ai_service.parse_json_response('{"a": 1}'), {"a": 1})

    def test_code_fence(self):
        self.assertEqual(ai_service.parse_json_response('```json\n{"a": 1}\n```'), {"a": 1})

    def test_think_block_and_surrounding_text(self):
        text = '<think>vou pensar {x}</think>Aqui está: {"a": [1, 2]} Espero ajudar.'
        self.assertEqual(ai_service.parse_json_response(text), {"a": [1, 2]})

    def test_garbage_raises_value_error(self):
        with self.assertRaises(ValueError):
            ai_service.parse_json_response("sem json nenhum")


if __name__ == "__main__":
    unittest.main()
