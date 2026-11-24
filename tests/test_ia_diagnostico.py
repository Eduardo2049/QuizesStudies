"""
Diagnóstico da IA para o admin e devolução da vaga do limite por minuto.

Cobre:
1. GET /api/admin/ia: 401 sem login, 403 para quem não é admin, 200 para o admin, sem chaves.
2. POST /api/admin/ia/teste: só admin, devolve o resultado por provedor e respeita o CSRF.
3. Resultado pronto (tema de exemplo) devolve a vaga do minuto: com limite 1 por minuto,
   o convidado gera duas vezes seguidas sem levar 429.
"""

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from api.services.guest_service import GUEST_COOKIE_NAME, GuestService


class FakeRateRepo:
    """Janela em memória com o mesmo contrato do RateLimitRepository."""

    def __init__(self):
        self.entries = {}

    def check_and_record(self, key, limit, window_seconds, cost=1):
        used = sum(self.entries.get(key, []))
        if used + cost > limit:
            return False, 60
        self.entries.setdefault(key, []).append(cost)
        return True, 0

    def is_blocked(self, key, limit, window_seconds):
        return sum(self.entries.get(key, [])) >= limit, 60

    def record(self, key, cost=1):
        self.entries.setdefault(key, []).append(cost)

    def get_usage(self, key, window_seconds):
        return sum(self.entries.get(key, []))


class _HTTPCase(unittest.TestCase):
    user = None

    @classmethod
    def setUpClass(cls):
        import api.handlers.quiz_handler as qh

        cls.qh = qh
        cls.patches = [
            patch.object(qh, "_ensure_migrations", lambda: None),
            patch.object(qh.QuizHandler, "_get_current_user_or_none", lambda self: cls.user),
        ]
        for p in cls.patches:
            p.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), qh.QuizHandler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        for p in cls.patches:
            p.stop()

    def setUp(self):
        self.limiters = (
            self.qh._rl_generate,
            self.qh._rl_ai_user_per_minute,
            self.qh._rl_read,
            self.qh._rl_guest_start,
            self.qh._rl_ai_probe,
        )
        self.saved_repos = [limiter.repo for limiter in self.limiters]
        for limiter in self.limiters:
            limiter._requests.clear()
            limiter.repo = None

    def tearDown(self):
        for limiter, repo in zip(self.limiters, self.saved_repos, strict=True):
            limiter.repo = repo

    def _request(self, path, method="GET", data=None, headers=None):
        h = dict(headers or {})
        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=body, headers=h, method=method)  # noqa: S310
        try:
            with urllib.request.urlopen(req) as resp:  # noqa: S310 - servidor local do teste
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()


def _auth_as(user):
    """Simula a sessão: _require_authenticated_user devolve `user` ou responde 401."""
    from api.exceptions.quiz_exceptions import QuizAPIException

    def fake(self):
        if not user:
            raise QuizAPIException("Autenticação necessária", 401)
        return user

    return fake


class TestAdminAIDiagnosticsHTTP(_HTTPCase):
    def _get_as(self, user):
        with patch.object(self.qh.QuizHandler, "_require_authenticated_user", _auth_as(user)):
            return self._request("/api/admin/ia")

    def test_requires_login(self):
        status, _h, _c = self._get_as(None)
        self.assertEqual(status, 401)

    def test_regular_user_is_refused(self):
        status, _h, content = self._get_as({"id": 5, "role": "student", "username": "aluno"})
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(content)["error"], "FORBIDDEN")

    def test_admin_sees_order_and_no_keys(self):
        from api.services import ai_service

        with (
            patch.object(ai_service, "CODEX_API_KEY", "sk-segredo-do-admin"),
            patch.object(ai_service, "AI_PROVIDERS", ["codex", "openrouter"]),
        ):
            status, headers, content = self._get_as({"id": 1, "role": "admin", "username": "admin"})
        self.assertEqual(status, 200)
        self.assertIn("no-store", headers.get("Cache-Control", ""))
        data = json.loads(content)["data"]
        self.assertEqual(data["order"], ["openai", "openrouter"])
        self.assertTrue(next(p for p in data["providers"] if p["name"] == "openai")["has_key"])
        self.assertNotIn(b"sk-segredo-do-admin", content)

    def test_probe_is_admin_only_and_returns_results(self):
        fake_results = [{"provider": "openai", "ok": False, "message": "x", "seconds": 0.1, "log": []}]
        with patch.object(self.qh, "probe_ai_providers", return_value=fake_results) as probe:
            with patch.object(
                self.qh.QuizHandler, "_require_authenticated_user", _auth_as({"id": 5, "role": "student"})
            ):
                status, _h, _c = self._request("/api/admin/ia/teste", method="POST", data={})
            self.assertEqual(status, 403)
            probe.assert_not_called()
            with patch.object(self.qh.QuizHandler, "_require_authenticated_user", _auth_as({"id": 1, "role": "admin"})):
                status, _h, content = self._request("/api/admin/ia/teste", method="POST", data={})
        self.assertEqual(status, 200)
        data = json.loads(content)["data"]
        self.assertEqual(data["results"], fake_results)
        self.assertIn("providers", data["diagnostics"])

    def test_probe_from_another_site_is_refused(self):
        with (
            patch.object(self.qh, "probe_ai_providers") as probe,
            patch.object(self.qh.QuizHandler, "_require_authenticated_user", _auth_as({"id": 1, "role": "admin"})),
        ):
            status, _h, _c = self._request(
                "/api/admin/ia/teste",
                method="POST",
                data={},
                headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
            )
        self.assertEqual(status, 403)
        probe.assert_not_called()


class TestMinuteSlotRefundHTTP(_HTTPCase):
    def setUp(self):
        super().setUp()
        self.guest_service = GuestService(repo=FakeRateRepo(), limit=5, ip_limit=20, window_seconds=3600)
        self.svc_patch = patch.object(self.qh, "guest_service", self.guest_service)
        self.svc_patch.start()
        self.addCleanup(self.svc_patch.stop)

    def _start_guest(self):
        status, headers, _content = self._request("/api/guest/start", method="POST")
        self.assertEqual(status, 200)
        cookie = headers.get("Set-Cookie", "")
        self.assertIn(f"{GUEST_COOKIE_NAME}=", cookie)
        return cookie.split(";", 1)[0]

    def test_ready_made_result_gives_the_minute_slot_back(self):
        cookie = self._start_guest()
        payload = {"topic": "Juros simples e compostos", "num_questions": 5, "difficulty": "Médio", "language": "pt-BR"}
        with patch.object(self.qh, "AI_USER_REQUESTS_PER_MINUTE", 1):
            for _ in range(3):
                status, _h, content = self._request(
                    "/api/quiz/generate", method="POST", data=payload, headers={"Cookie": cookie}
                )
                self.assertEqual(status, 201, content)
                data = json.loads(content)["data"]
                self.assertTrue(data.get("cached"))
                self.assertEqual(data.get("model"), "preset")
        # A cota do convidado também voltou a cada vez
        self.assertEqual(data["guest_ai"]["remaining"], 5)


if __name__ == "__main__":
    unittest.main()
