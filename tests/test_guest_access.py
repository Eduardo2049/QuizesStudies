"""
Testes do acesso sem login (home aberta) e da cota gratuita de IA do convidado.

Cobre:
1. GuestService: reserva atômica, devolução em falha, teto por IP e reserva preguiçosa.
2. Home (/) servida sem redirecionar para /login.
3. Endpoints de IA: visitante recebe AUTH_REQUIRED; convidado usa até o limite e
   recebe GUEST_AI_LIMIT_REACHED; falha do provedor devolve o uso.
4. Upload sem conta: arquivo com gabarito não usa IA nem consome cota.
5. Cookie de convidado: HttpOnly, SameSite=Lax e valores fora do formato ignorados.

Roda sem PostgreSQL: o servidor sobe em processo com um repositório de contagem em
memória e a IA é simulada.
"""
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from collections import defaultdict
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from api.exceptions.quiz_exceptions import GuestAILimitReached
from api.services.guest_service import GuestService, GUEST_COOKIE_NAME


class FakeRateRepo:
    """Contagem em memória com a mesma interface usada pelo GuestService."""

    def __init__(self):
        self.entries = defaultdict(list)
        self.lock = threading.Lock()

    def _used(self, key, window):
        cutoff = time.time() - window
        return sum(cost for ts, cost in self.entries[key] if ts > cutoff)

    def check_and_record(self, key, limit, window_seconds, cost=1):
        with self.lock:
            if self._used(key, window_seconds) + cost > limit:
                return False, window_seconds
            self.entries[key].append((time.time(), cost))
            return True, 0

    def record(self, key, cost=1):
        with self.lock:
            self.entries[key].append((time.time(), cost))

    def get_usage(self, key, window_seconds):
        with self.lock:
            return self._used(key, window_seconds)


class TestGuestService(unittest.TestCase):

    def setUp(self):
        self.repo = FakeRateRepo()
        self.service = GuestService(repo=self.repo, limit=3, ip_limit=5, window_seconds=3600)
        self.gid = GuestService.new_guest_id()

    def test_guest_id_format(self):
        self.assertTrue(GuestService.is_valid_guest_id(self.gid))
        self.assertFalse(GuestService.is_valid_guest_id(None))
        self.assertFalse(GuestService.is_valid_guest_id("curto"))
        self.assertFalse(GuestService.is_valid_guest_id("a" * 40 + ";Path=/"))

    def test_reserve_until_limit_then_blocks(self):
        for _ in range(3):
            self.service.reservation(self.gid, "10.0.0.1").acquire()
        with self.assertRaises(GuestAILimitReached) as ctx:
            self.service.reservation(self.gid, "10.0.0.1").acquire()
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.error_code, "GUEST_AI_LIMIT_REACHED")
        self.assertEqual(self.service.status(self.gid, "10.0.0.1")["remaining"], 0)

    def test_refund_returns_the_use(self):
        reservation = self.service.reservation(self.gid, "10.0.0.1")
        reservation.acquire()
        self.assertEqual(self.service.status(self.gid, "10.0.0.1")["remaining"], 2)
        reservation.refund()
        self.assertEqual(self.service.status(self.gid, "10.0.0.1")["remaining"], 3)
        reservation.refund()  # segunda devolução não faz nada
        self.assertEqual(self.service.status(self.gid, "10.0.0.1")["remaining"], 3)

    def test_acquire_is_idempotent_and_lazy(self):
        reservation = self.service.reservation(self.gid, "10.0.0.1")
        self.assertFalse(reservation.acquired)
        self.assertEqual(self.service.status(self.gid, "10.0.0.1")["used"], 0)
        reservation.acquire()
        reservation.acquire()
        self.assertEqual(self.service.status(self.gid, "10.0.0.1")["used"], 1)

    def test_ip_cap_blocks_cookie_cycling(self):
        """Apagar o cookie gera um novo id, mas o teto por IP continua valendo."""
        for _ in range(5):
            self.service.reservation(GuestService.new_guest_id(), "10.0.0.9").acquire()
        fresh = GuestService.new_guest_id()
        with self.assertRaises(GuestAILimitReached):
            self.service.reservation(fresh, "10.0.0.9").acquire()
        # o uso do id novo foi devolvido ao bater no teto do IP
        self.assertEqual(self.service.status(fresh, "10.0.0.10")["used"], 0)
        # outro IP não é afetado
        self.service.reservation(fresh, "10.0.0.10").acquire()

    def test_zero_limit_disables_guest_ai(self):
        service = GuestService(repo=self.repo, limit=0, ip_limit=5, window_seconds=3600)
        with self.assertRaises(GuestAILimitReached):
            service.reservation(self.gid, "10.0.0.1").acquire()


def _fake_generated_quiz(**_kwargs):
    return {
        "title": "Juros compostos",
        "questions": [
            {"id": 1, "section": "Geral", "question": "Quanto é 2+2?", "options": ["3", "4"], "answer": 1,
             "context": "", "explanation": "Soma simples."}
        ],
        "usage": {},
        "model": "fake",
        "provider": "fake",
    }


SAMPLE_TXT = """1. Quanto é 2 + 2?
a) 3
b) 4
c) 5
d) 6
Resposta: B

2. Qual a capital do Brasil?
a) São Paulo
b) Rio de Janeiro
c) Brasília
d) Salvador
Resposta: C
"""


class TestGuestAccessHTTP(unittest.TestCase):
    """Sobe o handler real em processo, sem banco, com a IA simulada."""

    @classmethod
    def setUpClass(cls):
        import api.handlers.quiz_handler as qh

        cls.qh = qh
        cls.patches = [
            patch.object(qh, "_ensure_migrations", lambda: None),
            patch.object(qh.QuizHandler, "_get_current_user_or_none", lambda self: None),
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
        # Cota isolada por teste e limites de rajada zerados
        self.guest_service = GuestService(repo=FakeRateRepo(), limit=2, ip_limit=10, window_seconds=3600)
        self.svc_patch = patch.object(self.qh, "guest_service", self.guest_service)
        self.svc_patch.start()
        self.limiters = (self.qh._rl_generate, self.qh._rl_remix, self.qh._rl_upload,
                         self.qh._rl_read, self.qh._rl_guest_start)
        self.saved_repos = [limiter.repo for limiter in self.limiters]
        for limiter in self.limiters:
            limiter._requests.clear()
            limiter.repo = None

    def tearDown(self):
        self.svc_patch.stop()
        for limiter, repo in zip(self.limiters, self.saved_repos):
            limiter.repo = repo

    # ── helpers ──────────────────────────────────────────────────────────────
    def _request(self, path, method="GET", data=None, headers=None, raw_body=None):
        h = dict(headers or {})
        body = raw_body
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=body, headers=h, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                content = resp.read()
                return resp.status, resp.headers, content
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def _json(self, content):
        return json.loads(content.decode("utf-8"))

    def _start_guest(self):
        status, headers, content = self._request("/api/guest/start", method="POST")
        self.assertEqual(status, 200)
        cookie_header = headers.get("Set-Cookie", "")
        self.assertIn(f"{GUEST_COOKIE_NAME}=", cookie_header)
        value = cookie_header.split(";", 1)[0]
        return value, cookie_header, self._json(content)

    # ── home aberta ──────────────────────────────────────────────────────────
    def test_home_is_served_without_login(self):
        status, headers, content = self._request("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn(b'id="accessModal"', content)

    def test_guest_status_for_visitor(self):
        status, _, content = self._request("/api/guest/status")
        self.assertEqual(status, 200)
        data = self._json(content)["data"]
        self.assertFalse(data["active"])
        self.assertEqual(data["ai"]["limit"], 2)
        self.assertEqual(data["ai"]["remaining"], 2)

    # ── IA para visitante e convidado ────────────────────────────────────────
    def test_visitor_needs_account_or_guest_for_ai(self):
        status, _, content = self._request("/api/quiz/generate", method="POST", data={"topic": "Juros"})
        self.assertEqual(status, 401)
        self.assertEqual(self._json(content)["error"], "AUTH_REQUIRED")

        status, _, content = self._request(
            "/api/quiz/remix-mistakes", method="POST", data={"questions": [{"question": "x"}]}
        )
        self.assertEqual(status, 401)
        self.assertEqual(self._json(content)["error"], "AUTH_REQUIRED")

    def test_guest_cookie_attributes(self):
        _, cookie_header, data = self._start_guest()
        self.assertIn("HttpOnly", cookie_header)
        self.assertIn("SameSite=Lax", cookie_header)
        self.assertTrue(data["data"]["active"])

    def test_invalid_guest_cookie_is_ignored(self):
        status, _, content = self._request(
            "/api/quiz/generate", method="POST", data={"topic": "Juros"},
            headers={"Cookie": f"{GUEST_COOKIE_NAME}=nao-e-um-id-valido"},
        )
        self.assertEqual(status, 401)
        self.assertEqual(self._json(content)["error"], "AUTH_REQUIRED")

    @patch("api.services.ai_service.generate_quiz_by_topic", side_effect=_fake_generated_quiz)
    def test_guest_uses_ai_until_limit(self, _mock_ai):
        cookie, _, _ = self._start_guest()
        headers = {"Cookie": cookie}

        for expected_remaining in (1, 0):
            status, _, content = self._request(
                "/api/quiz/generate", method="POST", data={"topic": "Juros compostos"}, headers=headers
            )
            self.assertEqual(status, 201)
            data = self._json(content)["data"]
            self.assertTrue(data["local_only"])
            self.assertEqual(data["guest_ai"]["remaining"], expected_remaining)

        status, _, content = self._request(
            "/api/quiz/generate", method="POST", data={"topic": "Juros compostos"}, headers=headers
        )
        self.assertEqual(status, 403)
        self.assertEqual(self._json(content)["error"], "GUEST_AI_LIMIT_REACHED")

        status, _, content = self._request("/api/guest/status", headers=headers)
        self.assertEqual(self._json(content)["data"]["ai"]["remaining"], 0)

    def test_ai_failure_does_not_consume_quota(self):
        from api.services.ai_service import AIServiceError

        cookie, _, _ = self._start_guest()
        with patch("api.services.ai_service.generate_quiz_by_topic", side_effect=AIServiceError("provedor fora")):
            status, _, _ = self._request(
                "/api/quiz/generate", method="POST", data={"topic": "Juros"}, headers={"Cookie": cookie}
            )
        self.assertEqual(status, 422)
        status, _, content = self._request("/api/guest/status", headers={"Cookie": cookie})
        self.assertEqual(self._json(content)["data"]["ai"]["remaining"], 2)

    def test_invalid_payload_does_not_consume_quota(self):
        cookie, _, _ = self._start_guest()
        status, _, _ = self._request(
            "/api/quiz/generate", method="POST", data={"topic": "  "}, headers={"Cookie": cookie}
        )
        self.assertEqual(status, 400)
        status, _, content = self._request("/api/guest/status", headers={"Cookie": cookie})
        self.assertEqual(self._json(content)["data"]["ai"]["remaining"], 2)

    @patch("api.services.ai_service.remix_questions_by_ai", return_value=[{"id": 1, "question": "Nova", "options": ["a", "b"], "answer": 0}])
    def test_guest_remix_consumes_quota(self, _mock_remix):
        cookie, _, _ = self._start_guest()
        status, _, content = self._request(
            "/api/quiz/remix-mistakes", method="POST",
            data={"questions": [{"question": "Quanto é 2+2?", "options": ["3", "4"], "answer": 1}]},
            headers={"Cookie": cookie},
        )
        self.assertEqual(status, 200)
        self.assertEqual(self._json(content)["data"]["guest_ai"]["remaining"], 1)

    # ── upload sem conta ─────────────────────────────────────────────────────
    def _multipart(self, filename, text):
        boundary = "----quizstudyboundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: text/plain\r\n\r\n"
        ).encode("utf-8") + text.encode("utf-8") + f"\r\n--{boundary}--\r\n".encode("utf-8")
        return body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    def test_visitor_upload_with_answer_key_needs_no_ai(self):
        body, headers = self._multipart("prova.txt", SAMPLE_TXT)
        status, _, content = self._request("/api/upload", method="POST", raw_body=body, headers=headers)
        self.assertEqual(status, 201)
        data = self._json(content)["data"]
        self.assertTrue(data["local_only"])
        self.assertFalse(data["ai_generated"])
        self.assertEqual(data["question_count"], 2)

    def test_visitor_upload_that_needs_ai_asks_for_access(self):
        body, headers = self._multipart("resumo.txt", "Texto corrido de estudo sem questões numeradas.")
        with patch("api.services.upload_service.OPENROUTER_API_KEY", "fake-key"):
            status, _, content = self._request("/api/upload", method="POST", raw_body=body, headers=headers)
        self.assertEqual(status, 401)
        self.assertEqual(self._json(content)["error"], "AUTH_REQUIRED")

    def test_guest_upload_that_needs_ai_uses_quota(self):
        cookie, _, _ = self._start_guest()
        body, headers = self._multipart("resumo.txt", "Texto corrido de estudo sem questões numeradas.")
        headers["Cookie"] = cookie
        generated = [
            {"id": 1, "section": "Geral", "question": "Pergunta?", "options": ["a", "b", "c", "d"], "answer": 2,
             "context": ""},
        ]
        with patch("api.services.upload_service.OPENROUTER_API_KEY", "fake-key"), \
             patch("api.services.upload_service.parse_and_structure_questions_with_ai", return_value=generated):
            status, _, content = self._request("/api/upload", method="POST", raw_body=body, headers=headers)
        self.assertEqual(status, 201)
        data = self._json(content)["data"]
        self.assertTrue(data["ai_generated"])
        self.assertEqual(data["guest_ai"]["remaining"], 1)


class TestClientIpBehindVercel(unittest.TestCase):
    """Na Vercel, um CF-Connecting-IP forjado pelo cliente não pode trocar o IP usado nos limites."""

    class _Handler:
        def __init__(self, headers):
            self.headers = headers
            self.client_address = ("10.1.1.1", 5555)

    def test_spoofed_cf_header_is_ignored_on_vercel(self):
        from api.middleware.http_middleware import HTTPMiddleware

        handler = self._Handler({
            "CF-Connecting-IP": "6.6.6.6",
            "x-vercel-forwarded-for": "200.100.50.25",
            "X-Forwarded-For": "200.100.50.25",
        })
        with patch("api.utils.config.TRUST_PROXY", True), patch.dict("os.environ", {"VERCEL": "1"}):
            self.assertEqual(HTTPMiddleware.get_client_ip(handler), "200.100.50.25")

    def test_cloudflare_header_still_used_when_self_hosted(self):
        from api.middleware.http_middleware import HTTPMiddleware

        handler = self._Handler({"CF-Connecting-IP": "177.10.20.30", "X-Forwarded-For": "1.2.3.4"})
        with patch("api.utils.config.TRUST_PROXY", True), patch.dict("os.environ", {"VERCEL": ""}):
            self.assertEqual(HTTPMiddleware.get_client_ip(handler), "177.10.20.30")


if __name__ == "__main__":
    unittest.main()
