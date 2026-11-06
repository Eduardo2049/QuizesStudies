"""
Pedidos de IA persistentes, cache no banco e tempo por tentativa (docs/PLANO_ACELY.md, Fase 1).

Cobre:
1. AIJobRepository (modo memória): criar, repetir, concluir, conflito de dono/parâmetros,
   refazer depois de falha e pedido abandonado.
2. HTTP: repetir o mesmo request_id (recarregar a página) não chama a IA de novo nem gasta
   outra cota; pedido ainda rodando responde 202 e aparece em GET /api/quiz/jobs/<id>;
   outro convidado não vê o pedido.
3. Cache de temas no segundo nível (ai_cache) e cota devolvida quando vem do cache.
4. Streaming: modelo parado na fila é abandonado em AI_ATTEMPT_TIMEOUT e o próximo responde.

Roda sem PostgreSQL: os repositórios caem para a memória.
"""
import json
import threading
import time
import unittest
import uuid
from http.server import ThreadingHTTPServer
from unittest.mock import MagicMock, patch

from api.repositories import ai_job_repository as jobs_module
from api.repositories.ai_job_repository import AIJobRepository, JobConflict
from api.services import ai_service
from tests import test_guest_access as guest_tests
from tests.test_guest_access import _fake_generated_quiz


def _guest_http():
    # Pelo módulo: uma classe de teste no nível do módulo faria o unittest rodar os testes dela de novo
    return guest_tests.TestGuestAccessHTTP


def _new_id():
    return str(uuid.uuid4())


class TestAIJobRepository(unittest.TestCase):
    """Modo memória (banco fora). O caminho do PostgreSQL está em test_db_integration."""

    def setUp(self):
        no_db = patch.object(jobs_module, "get_cursor", side_effect=ConnectionError("sem banco"))
        no_db.start()
        self.addCleanup(no_db.stop)
        self.repo = AIJobRepository()

    def test_start_then_repeat_returns_running(self):
        job_id = _new_id()
        created, job = self.repo.start(job_id, "guest", "g1", "generate", "h1")
        self.assertTrue(created)
        created, job = self.repo.start(job_id, "guest", "g1", "generate", "h1")
        self.assertFalse(created)
        self.assertEqual(job["status"], "running")

    def test_finish_then_repeat_returns_result(self):
        job_id = _new_id()
        self.repo.start(job_id, "user", 7, "generate", "h1")
        self.repo.finish(job_id, {"http_status": 201, "data": {"name": "x"}})
        created, job = self.repo.start(job_id, "user", "7", "generate", "h1")
        self.assertFalse(created)
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["result"]["data"]["name"], "x")

    def test_other_owner_or_params_conflict(self):
        job_id = _new_id()
        self.repo.start(job_id, "guest", "g1", "generate", "h1")
        with self.assertRaises(JobConflict):
            self.repo.start(job_id, "guest", "g2", "generate", "h1")
        with self.assertRaises(JobConflict):
            self.repo.start(job_id, "guest", "g1", "generate", "outro")
        with self.assertRaises(JobConflict):
            self.repo.start(job_id, "guest", "g1", "remix", "h1")

    def test_failed_job_runs_again(self):
        job_id = _new_id()
        self.repo.start(job_id, "guest", "g1", "generate", "h1")
        self.repo.fail(job_id, "provedor fora", "QUIZ_ERROR", 422)
        self.assertEqual(self.repo.get(job_id)["status"], "failed")
        created, _job = self.repo.start(job_id, "guest", "g1", "generate", "h1")
        self.assertTrue(created)
        self.assertEqual(self.repo.get(job_id)["status"], "running")

    def test_abandoned_running_job_shows_as_failed(self):
        job_id = _new_id()
        self.repo.start(job_id, "guest", "g1", "generate", "h1")
        self.repo._jobs[job_id]["updated_ts"] -= jobs_module.JOB_STALE_SECONDS + 1
        job = self.repo.get(job_id)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error_code"], "AI_JOB_ABANDONED")

    def test_cache_roundtrip(self):
        self.repo.cache_set("k", {"questions": [1]})
        self.assertEqual(self.repo.cache_get("k"), {"questions": [1]})
        self.assertIsNone(self.repo.cache_get("outra"))


class TestAIJobsHTTP(unittest.TestCase):
    """Servidor real em processo, sem banco, com a IA simulada (como em test_guest_access)."""

    @classmethod
    def setUpClass(cls):
        _guest_http().setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        _guest_http().tearDownClass.__func__(cls)

    def _request(self, *args, **kwargs):
        return _guest_http()._request(self, *args, **kwargs)

    def _json(self, content):
        return _guest_http()._json(self, content)

    def _start_guest(self):
        return _guest_http()._start_guest(self)

    def setUp(self):
        _guest_http().setUp(self)
        self.repo_patch = patch.object(self.qh, "ai_job_repo", AIJobRepository())
        self.repo_patch.start()

    def tearDown(self):
        self.repo_patch.stop()
        _guest_http().tearDown(self)

    def _generate(self, cookie, request_id, topic="Juros compostos"):
        return self._request(
            "/api/quiz/generate", method="POST", headers={"Cookie": cookie},
            data={"topic": topic, "num_questions": 1, "request_id": request_id},
        )

    def _remaining(self, cookie):
        _s, _h, content = self._request("/api/guest/status", headers={"Cookie": cookie})
        return self._json(content)["data"]["ai"]["remaining"]

    def test_repeating_request_id_does_not_call_ai_or_charge_again(self):
        cookie, _hdr, _ = self._start_guest()
        request_id = _new_id()
        with patch("api.services.ai_service.generate_quiz_by_topic", side_effect=_fake_generated_quiz) as ai:
            first = self._generate(cookie, request_id)
            second = self._generate(cookie, request_id)
        self.assertEqual(first[0], 201)
        self.assertEqual(second[0], 201)
        self.assertEqual(ai.call_count, 1)
        body = self._json(second[2])
        self.assertTrue(body["data"]["replayed"])
        self.assertEqual(body["data"]["questions"][0]["question"], "Quanto é 2+2?")
        self.assertEqual(body["data"]["guest_ai"]["remaining"], 1)
        self.assertEqual(self._remaining(cookie), 1)

    def test_running_request_answers_202_and_job_route_shows_progress(self):
        cookie, _hdr, _ = self._start_guest()
        request_id = _new_id()
        release = threading.Event()
        entered = threading.Event()

        def slow_ai(**kwargs):
            entered.set()
            release.wait(5)
            return _fake_generated_quiz(**kwargs)

        results = {}
        with patch("api.services.ai_service.generate_quiz_by_topic", side_effect=slow_ai) as ai:
            worker = threading.Thread(target=lambda: results.setdefault("first", self._generate(cookie, request_id)))
            worker.start()
            self.assertTrue(entered.wait(5))

            # A página foi recarregada: o mesmo pedido volta como "ainda rodando"
            status, _h, content = self._generate(cookie, request_id)
            self.assertEqual(status, 202)
            self.assertEqual(self._json(content)["data"]["status"], "running")

            status, _h, content = self._request(f"/api/quiz/jobs/{request_id}", headers={"Cookie": cookie})
            self.assertEqual(status, 200)
            self.assertEqual(self._json(content)["data"]["status"], "running")

            release.set()
            worker.join(5)

        self.assertEqual(results["first"][0], 201)
        self.assertEqual(ai.call_count, 1)
        status, _h, content = self._request(f"/api/quiz/jobs/{request_id}", headers={"Cookie": cookie})
        info = self._json(content)["data"]
        self.assertEqual(info["status"], "done")
        self.assertEqual(info["result"]["label"], "Juros compostos")
        self.assertEqual(self._remaining(cookie), 1)

    def test_failed_job_reports_error_and_refunds(self):
        from api.services.ai_service import AIServiceError
        cookie, _hdr, _ = self._start_guest()
        request_id = _new_id()
        with patch("api.services.ai_service.generate_quiz_by_topic", side_effect=AIServiceError("provedor fora")):
            status, _h, _c = self._generate(cookie, request_id)
        self.assertEqual(status, 422)
        status, _h, content = self._request(f"/api/quiz/jobs/{request_id}", headers={"Cookie": cookie})
        info = self._json(content)["data"]
        self.assertEqual(info["status"], "failed")
        self.assertIn("provedor fora", info["message"])
        self.assertEqual(self._remaining(cookie), 2)

    def test_other_guest_cannot_see_the_job(self):
        cookie, _hdr, _ = self._start_guest()
        other, _hdr2, _ = self._start_guest()
        request_id = _new_id()
        with patch("api.services.ai_service.generate_quiz_by_topic", side_effect=_fake_generated_quiz):
            self._generate(cookie, request_id)
        status, _h, _c = self._request(f"/api/quiz/jobs/{request_id}", headers={"Cookie": other})
        self.assertEqual(status, 404)
        # Reusar o id de outra pessoa não devolve o simulado dela
        with patch("api.services.ai_service.generate_quiz_by_topic", side_effect=_fake_generated_quiz):
            status, _h, _c = self._generate(other, request_id)
        self.assertEqual(status, 409)

    def test_invalid_request_id_is_rejected_without_charging(self):
        cookie, _hdr, _ = self._start_guest()
        with patch("api.services.ai_service.generate_quiz_by_topic", side_effect=_fake_generated_quiz) as ai:
            status, _h, _c = self._generate(cookie, "nao-e-uuid")
        self.assertEqual(status, 400)
        self.assertEqual(ai.call_count, 0)
        self.assertEqual(self._remaining(cookie), 2)

    def test_cached_topic_does_not_use_guest_quota(self):
        cookie, _hdr, _ = self._start_guest()
        cached = {**_fake_generated_quiz(), "cached": True}
        with patch("api.services.ai_service.generate_quiz_by_topic", return_value=cached):
            status, _h, _c = self._generate(cookie, _new_id())
        self.assertEqual(status, 201)
        self.assertEqual(self._remaining(cookie), 2)

    def test_request_without_id_still_works(self):
        cookie, _hdr, _ = self._start_guest()
        with patch("api.services.ai_service.generate_quiz_by_topic", side_effect=_fake_generated_quiz):
            status, _h, _c = self._request(
                "/api/quiz/generate", method="POST", headers={"Cookie": cookie},
                data={"topic": "Sem id", "num_questions": 1},
            )
        self.assertEqual(status, 201)


class TestTopicCacheInDatabase(unittest.TestCase):
    """O segundo nível (ai_cache) responde quando a memória do processo não tem o tema."""

    def test_second_level_cache_skips_ai(self):
        repo = AIJobRepository()
        content = json.dumps({"title": "Cache", "questions": [
            {"question": "Q?", "options": ["A", "B"], "answer": 1, "explanation": "B."}]})
        with patch.object(ai_service, "ai_job_repo", repo), \
             patch.object(ai_service, "OPENROUTER_API_KEY", "k"), \
             patch.object(ai_service, "check_ai_token_quota"), \
             patch.object(ai_service, "_call_openrouter", return_value=(content, "m", {})) as call:
            first = ai_service.generate_quiz_by_topic("Tema do cache em banco", num_questions=1)
            ai_service._quiz_generation_cache.clear()  # outra instância da Vercel
            second = ai_service.generate_quiz_by_topic("Tema do cache em banco", num_questions=1)
        self.assertEqual(call.call_count, 1)
        self.assertFalse(first.get("cached"))
        self.assertTrue(second["cached"])
        self.assertEqual(second["questions"][0]["answer"], 1)


def _stream_response(lines, delay=0.0):
    resp = MagicMock()
    resp.status_code = 200
    resp.ok = True
    resp.headers = {"Content-Type": "text/event-stream"}

    def iter_lines(chunk_size=1024):
        for line in lines:
            if delay:
                time.sleep(delay)
            yield line
    resp.iter_lines.side_effect = iter_lines
    return resp


def _sse(content):
    chunk = {"choices": [{"delta": {"content": content}}]}
    return b"data: " + json.dumps(chunk).encode()


class TestStreamingAndAttemptTimeout(unittest.TestCase):

    def test_stream_is_joined(self):
        resp = _stream_response([b": OPENROUTER PROCESSING", _sse('{"a":'), b"", _sse(" 1}"),
                                 b'data: {"usage": {"total_tokens": 9}, "choices": []}', b"data: [DONE]"])
        data = ai_service._read_chat_response(resp, attempt_timeout=5, deadline=time.monotonic() + 10)
        self.assertEqual(data["choices"][0]["message"]["content"], '{"a": 1}')
        self.assertEqual(data["usage"], {"total_tokens": 9})

    def test_queue_keepalives_do_not_count_as_answer(self):
        resp = _stream_response([b": OPENROUTER PROCESSING"] * 5, delay=0.05)
        with self.assertRaises(ai_service._AttemptTimeout):
            ai_service._read_chat_response(resp, attempt_timeout=0.1, deadline=time.monotonic() + 10)

    def test_slow_but_writing_model_is_not_cut(self):
        resp = _stream_response([_sse('{"ok"'), _sse(": true"), _sse("}")], delay=0.06)
        data = ai_service._read_chat_response(resp, attempt_timeout=0.1, deadline=time.monotonic() + 10)
        self.assertEqual(data["choices"][0]["message"]["content"], '{"ok": true}')

    def test_error_inside_stream(self):
        resp = _stream_response([b'data: {"error": {"message": "provider down"}}'])
        with self.assertRaises(ai_service._StreamError):
            ai_service._read_chat_response(resp, attempt_timeout=5, deadline=time.monotonic() + 10)

    def test_stalled_model_is_abandoned_and_next_answers(self):
        session = MagicMock()
        stalled = _stream_response([b": OPENROUTER PROCESSING"] * 10, delay=0.05)
        good = _stream_response([_sse('{"questions": []}'), b"data: [DONE]"])
        session.post.side_effect = [stalled, good]
        with patch.object(ai_service, "_get_http_session", return_value=session), \
             patch.object(ai_service, "_check_daily_ai_budget"), \
             patch.object(ai_service, "OPENROUTER_API_KEY", "k"), \
             patch.object(ai_service, "OPENROUTER_DISCOVER_FREE_MODELS", False), \
             patch.object(ai_service, "OPENROUTER_FREE_MODELS", ["lento/modelo:free", "rapido/modelo:free"]), \
             patch.object(ai_service, "AI_ATTEMPT_TIMEOUT", 0.1), \
             patch.dict(ai_service._model_cooldown, clear=True):
            content, model, _usage = ai_service._call_openrouter(
                [{"role": "user", "content": "oi"}], temperature=0.2, max_tokens=50, timeout=30)
        self.assertEqual(model, "rapido/modelo:free")
        self.assertEqual(content, '{"questions": []}')
        first_call = session.post.call_args_list[0]
        self.assertTrue(first_call.kwargs["json"]["stream"])
        self.assertTrue(first_call.kwargs["stream"])
        stalled.close.assert_called()


if __name__ == "__main__":
    unittest.main()
