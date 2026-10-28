"""
Testes do endurecimento para produção.

Cobre:
1. Login não devolve o token no JSON (só sob pedido explícito de cliente de API).
2. POST de outro site (Origin/Sec-Fetch-Site) é recusado; mesmo site e clientes sem navegador passam.
3. Erros de IA não expõem nomes de variáveis, arquivo .env ou resposta bruta do modelo.
4. Teto diário global de chamadas à IA.
5. Estouro da cota de tokens por IP vira 429, não erro interno.
"""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from api.middleware.http_middleware import HTTPMiddleware


class _FakeHandler:
    def __init__(self, headers):
        self.headers = headers
        self.client_address = ("10.0.0.1", 1234)


class TestCrossSiteDetection(unittest.TestCase):

    def test_same_origin_post_passes(self):
        h = _FakeHandler({"Origin": "https://quiz.study", "Host": "quiz.study", "Sec-Fetch-Site": "same-origin"})
        self.assertFalse(HTTPMiddleware.is_cross_site_request(h))

    def test_other_site_post_is_blocked(self):
        h = _FakeHandler({"Origin": "https://site-malicioso.com", "Host": "quiz.study"})
        self.assertTrue(HTTPMiddleware.is_cross_site_request(h))

    def test_sec_fetch_site_cross_site_is_blocked(self):
        h = _FakeHandler({"Sec-Fetch-Site": "cross-site", "Host": "quiz.study"})
        self.assertTrue(HTTPMiddleware.is_cross_site_request(h))

    def test_null_origin_is_blocked(self):
        h = _FakeHandler({"Origin": "null", "Host": "quiz.study"})
        self.assertTrue(HTTPMiddleware.is_cross_site_request(h))

    def test_non_browser_client_passes(self):
        h = _FakeHandler({"Host": "quiz.study"})
        self.assertFalse(HTTPMiddleware.is_cross_site_request(h))

    def test_allowed_origin_passes(self):
        h = _FakeHandler({"Origin": "https://app.parceiro.com", "Host": "quiz.study", "Sec-Fetch-Site": "cross-site"})
        with patch("api.middleware.http_middleware.ALLOWED_ORIGINS", ["https://app.parceiro.com"]):
            self.assertFalse(HTTPMiddleware.is_cross_site_request(h))


class TestAIErrorsDoNotLeakConfig(unittest.TestCase):

    def test_missing_key_message_is_generic(self):
        from api.services import ai_service

        with patch.object(ai_service, "GEMINI_API_KEY", ""), patch.object(ai_service, "OPENROUTER_API_KEY", ""):
            with self.assertRaises(ai_service.AIServiceError) as ctx:
                ai_service.generate_quiz_by_topic("Juros compostos", num_questions=1)
        message = str(ctx.exception)
        self.assertNotIn("GEMINI_API_KEY", message)
        self.assertNotIn(".env", message)
        self.assertEqual(message, ai_service.AI_UNAVAILABLE_MESSAGE)

    def test_invalid_key_and_credits_are_generic(self):
        from api.services.ai_service import _format_user_friendly_error, AI_UNAVAILABLE_MESSAGE

        self.assertEqual(_format_user_friendly_error(401, '{"error":{"message":"invalid api key"}}'), AI_UNAVAILABLE_MESSAGE)
        self.assertEqual(_format_user_friendly_error(402, '{"error":{"message":"insufficient credits"}}'), AI_UNAVAILABLE_MESSAGE)

    def test_daily_global_cap_blocks_calls(self):
        from api.services import ai_service

        class _Repo:
            def check_and_record(self, *_args, **_kwargs):
                return False, 3600

        with patch.object(ai_service, "AI_DAILY_CALL_LIMIT", 5), patch.object(ai_service, "rate_limit_repo", _Repo()):
            with self.assertRaises(ai_service.AIServiceError) as ctx:
                ai_service._check_daily_ai_budget()
        self.assertEqual(str(ctx.exception), ai_service.AI_DAILY_LIMIT_MESSAGE)

    def test_daily_cap_zero_disables(self):
        from api.services import ai_service

        with patch.object(ai_service, "AI_DAILY_CALL_LIMIT", 0):
            ai_service._check_daily_ai_budget()  # não lança


class TestHandlerHardening(unittest.TestCase):
    """Servidor real em processo, sem banco."""

    @classmethod
    def setUpClass(cls):
        import api.handlers.quiz_handler as qh

        cls.qh = qh
        cls.patches = [patch.object(qh, "_ensure_migrations", lambda: None)]
        for p in cls.patches:
            p.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), qh.QuizHandler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        for p in cls.patches:
            p.stop()

    def _post(self, path, payload, headers=None):
        h = {"Content-Type": "application/json", **(headers or {})}
        req = urllib.request.Request(self.base + path, data=json.dumps(payload).encode(), headers=h, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, resp.headers, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, e.headers, json.loads(e.read())

    def test_login_hides_token_unless_requested(self):
        fake = {"status": "success", "message": "ok", "data": {"token": "segredo", "user": {"id": 1}}}
        with patch.object(self.qh.AuthController, "login", return_value=fake):
            status, headers, body = self._post("/api/auth/login", {"username": "a", "password": "b"})
            self.assertEqual(status, 200)
            self.assertNotIn("token", body["data"])
            self.assertNotIn("token", body)
            self.assertIn("ifuture_session=segredo", headers.get("Set-Cookie", ""))

            status, _, body = self._post("/api/auth/login", {"username": "a", "password": "b", "return_token": True})
            self.assertEqual(body["data"]["token"], "segredo")

    def test_cross_site_post_is_rejected(self):
        status, _, body = self._post("/api/guest/start", {}, headers={"Origin": "https://site-malicioso.com"})
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "CROSS_SITE_REQUEST")

    def test_ai_token_quota_becomes_429(self):
        from api.services.ai_service import AIQuotaExceededError

        with patch.object(self.qh.QuizHandler, "_require_user_or_guest", lambda self: ({"id": 1, "role": "student"}, None)), \
             patch.object(self.qh.QuizController, "generate_quiz_by_topic",
                          side_effect=AIQuotaExceededError("cota", retry_after=120)):
            self.qh._rl_generate._requests.clear()
            status, headers, body = self._post("/api/quiz/generate", {"topic": "Juros"})
        self.assertEqual(status, 429)
        self.assertEqual(headers.get("Retry-After"), "120")


class TestGuestImport(unittest.TestCase):

    def test_sanitize_drops_invalid_questions_and_caps_sizes(self):
        from api.services.import_service import sanitize_imported_quiz

        quiz = sanitize_imported_quiz({
            "label": "Juros" * 100,
            "questions": [
                {"question": "Quanto é 2+2?", "options": ["3", "4"], "answer": 1},
                {"question": "Sem gabarito", "options": ["a", "b"]},
                {"question": "Gabarito fora", "options": ["a", "b"], "answer": 5},
                {"question": "Booleano não vale", "options": ["a", "b"], "answer": True},
                {"question": "Uma opção só", "options": ["a"], "answer": 0},
                "lixo",
            ],
        })
        self.assertEqual(len(quiz["questions"]), 1)
        self.assertLessEqual(len(quiz["label"]), 120)
        self.assertIsNone(sanitize_imported_quiz({"questions": []}))
        self.assertIsNone(sanitize_imported_quiz("texto"))

    def test_import_saves_private_quizzes_for_user(self):
        from unittest.mock import MagicMock
        from api.services.import_service import QuizImportService

        repo = MagicMock()
        repo.name_exists.side_effect = [True, False]
        repo.save_quiz.return_value = {"name": "juros-1", "label": "Juros"}
        result = QuizImportService(repo).import_for_user(7, [
            {"label": "Juros", "questions": [{"question": "Q?", "options": ["a", "b"], "answer": 0}]},
            {"label": "Vazio", "questions": []},
        ])
        self.assertEqual(result["imported"], 1)
        self.assertEqual(result["skipped"], 1)
        kwargs = repo.save_quiz.call_args.kwargs
        self.assertEqual(kwargs["created_by"], 7)
        self.assertFalse(kwargs["is_public"])
        self.assertEqual(kwargs["name"], "juros-1")

    def test_import_rejects_too_many(self):
        from unittest.mock import MagicMock
        from api.exceptions.quiz_exceptions import QuizAPIException
        from api.services.import_service import QuizImportService

        with self.assertRaises(QuizAPIException):
            QuizImportService(MagicMock()).import_for_user(1, [{}] * 21)


class TestAccountRights(unittest.TestCase):

    def _service(self, record):
        from unittest.mock import MagicMock
        from api.services.auth_service import AuthService

        repo = MagicMock()
        repo.find_by_username.return_value = record
        return AuthService(repository=repo), repo

    def test_delete_requires_correct_password(self):
        from api.exceptions.quiz_exceptions import QuizAPIException
        from api.services.auth_service import hash_password

        pwd_hash, salt = hash_password("SenhaCerta123")
        service, repo = self._service({"id": 3, "salt": salt, "password_hash": pwd_hash})
        user = {"id": 3, "username": "aluno", "role": "student"}
        with self.assertRaises(QuizAPIException) as ctx:
            service.delete_account(user, "errada")
        self.assertEqual(ctx.exception.status_code, 403)  # 401 derrubaria a sessão
        repo.delete_user_and_data.assert_not_called()
        service.delete_account(user, "SenhaCerta123")
        repo.delete_user_and_data.assert_called_once_with(3)

    def test_admin_cannot_self_delete(self):
        from api.exceptions.quiz_exceptions import QuizAPIException

        service, repo = self._service(None)
        with self.assertRaises(QuizAPIException):
            service.delete_account({"id": 1, "username": "admin", "role": "admin"}, "x")
        repo.delete_user_and_data.assert_not_called()


class TestGoogleLogin(unittest.TestCase):

    def test_safe_next_blocks_external(self):
        from api.services.google_auth_service import safe_next

        self.assertEqual(safe_next("//evil.com"), "/")
        self.assertEqual(safe_next("https://evil.com"), "/")
        self.assertEqual(safe_next("/\\evil.com"), "/")
        self.assertEqual(safe_next("/login"), "/")
        self.assertEqual(safe_next("/?abrir=criar"), "/?abrir=criar")

    def test_state_cookie_roundtrip(self):
        from api.services.google_auth_service import build_state_cookie_value, parse_state_cookie

        state, value = build_state_cookie_value("/?abrir=criar")
        self.assertEqual(parse_state_cookie(value), (state, "/?abrir=criar"))
        self.assertEqual(parse_state_cookie(None), (None, "/"))

    def _fake_http(self, profile):
        class _Resp:
            def __init__(self, code, body):
                self.status_code, self._body = code, body
            def json(self):
                return self._body

        class _Http:
            def post(self, *a, **k):
                return _Resp(200, {"access_token": "tok"})
            def get(self, *a, **k):
                return _Resp(200, profile)
        return _Http()

    def test_unverified_email_is_refused(self):
        from unittest.mock import MagicMock
        from api.exceptions.quiz_exceptions import QuizAPIException
        from api.services import google_auth_service as g

        with patch.object(g, "GOOGLE_CLIENT_ID", "id"), patch.object(g, "GOOGLE_CLIENT_SECRET", "s"):
            svc = g.GoogleAuthService(MagicMock(), http=self._fake_http({"email": "a@b.com", "email_verified": False}))
            with self.assertRaises(QuizAPIException) as ctx:
                svc.login_with_code("code", "https://x/cb")
        self.assertEqual(ctx.exception.error_code, "GOOGLE_EMAIL_UNVERIFIED")

    def test_new_google_user_is_created_and_logged_in(self):
        import datetime
        from unittest.mock import MagicMock
        from api.services import google_auth_service as g

        auth = MagicMock()
        auth.repo.find_by_email.return_value = None
        auth.repo.find_by_username.side_effect = lambda n: {"id": 1} if n == "maria" else None
        auth.repo.create_user.return_value = {"id": 9, "username": "maria2", "email": "maria@gmail.com", "role": "student"}
        auth.repo.create_session.return_value = {"expires_at": datetime.datetime(2026, 11, 3)}
        with patch.object(g, "GOOGLE_CLIENT_ID", "id"), patch.object(g, "GOOGLE_CLIENT_SECRET", "s"):
            svc = g.GoogleAuthService(auth, http=self._fake_http({"email": "Maria@gmail.com", "email_verified": True}))
            result = svc.login_with_code("code", "https://x/cb")
        self.assertEqual(auth.repo.create_user.call_args.args[0], "maria2")
        self.assertEqual(result["user"]["id"], 9)
        self.assertTrue(result["token"])


class TestPublicPages(TestHandlerHardening):
    """Reaproveita o servidor em processo do TestHandlerHardening."""

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def test_legal_pages_and_404(self):
        status, body = self._get("/termos")
        self.assertEqual(status, 200)
        self.assertIn("Termos de uso", body)
        status, body = self._get("/privacidade")
        self.assertEqual(status, 200)
        self.assertIn("Política de privacidade", body)
        status, body = self._get("/pagina-que-nao-existe")
        self.assertEqual(status, 404)
        self.assertIn("Página não encontrada", body)
        status, body = self._get("/api/rota-inexistente")
        self.assertEqual(status, 404)
        self.assertIn('"status": "error"', body)

    def test_google_disabled_redirects_to_login(self):
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            opener.open(self.base + "/api/auth/google/start")
            self.fail("esperava redirecionamento")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            self.assertEqual(e.headers.get("Location"), "/login?erro=google_indisponivel")

    def test_import_requires_account(self):
        status, _, body = self._post("/api/quizzes/import", {"quizzes": []})
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
